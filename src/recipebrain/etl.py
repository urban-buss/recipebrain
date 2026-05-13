"""ETL orchestrator: discover → fetch → transform → write.

Connects source adapters to the transform layer and Parquet writer,
running the full pipeline for one or more recipe sources.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from recipebrain.exceptions import DataStaleError
from recipebrain.images import download_recipe_images
from recipebrain.query import invalidate_connection
from recipebrain.settings import Settings
from recipebrain.snapshot import create_snapshot
from recipebrain.sources.base import RawRecipe, SourceAdapter
from recipebrain.transform import (
    build_recipe_images_rows,
    build_recipe_ingredients_rows,
    build_recipe_row,
    build_recipe_steps_rows,
)
from recipebrain.writer import append_table, read_table, write_schema_version, write_table

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 20


@dataclass
class EtlResult:
    """Summary of an ETL run."""

    source: str
    discovered: int = 0
    fetched: int = 0
    skipped: int = 0
    errors: int = 0
    soft_deleted: int = 0
    validation_skipped: int = 0
    error_details: list[str] = field(default_factory=list)


def _get_source_adapters(settings: Settings, source_filter: str | None) -> list[SourceAdapter]:
    """Instantiate enabled source adapters, optionally filtered by key."""
    from recipebrain.sources.bettybossi import BettybossiAdapter
    from recipebrain.sources.fooby import FoobyAdapter
    from recipebrain.sources.migusto import MigustoAdapter
    from recipebrain.sources.schweizerfleisch import SchweizerfleischAdapter
    from recipebrain.sources.swissmilk import SwissmilkAdapter

    registry: dict[str, type[SourceAdapter]] = {
        "bettybossi": BettybossiAdapter,
        "fooby": FoobyAdapter,
        "migusto": MigustoAdapter,
        "swissmilk": SwissmilkAdapter,
        "schweizerfleisch": SchweizerfleischAdapter,
    }

    adapters = []
    for key, adapter_cls in registry.items():
        if source_filter and key != source_filter:
            continue
        source_cfg = settings.sources.get(key)
        if source_cfg and not source_cfg.enabled:
            continue
        adapters.append(adapter_cls(settings))  # type: ignore[call-arg]

    return adapters


def _next_recipe_id(output_dir: Path) -> int:
    """Determine the next available recipe ID from existing data."""
    try:
        table = read_table("recipes", output_dir)
        if table.num_rows == 0:
            return 1
        return int(table.column("id").to_pylist()[-1]) + 1
    except Exception:
        return 1


_SOURCE_METADATA: dict[str, dict] = {
    "bettybossi": {
        "id": 1,
        "display_name": "Betty Bossi",
        "base_url": "https://www.bettybossi.ch",
        "language": "de",
    },
    "fooby": {
        "id": 2,
        "display_name": "Fooby",
        "base_url": "https://fooby.ch",
        "language": "de",
    },
    "migusto": {
        "id": 3,
        "display_name": "Migusto",
        "base_url": "https://migusto.migros.ch",
        "language": "de",
    },
    "swissmilk": {
        "id": 4,
        "display_name": "Swissmilk",
        "base_url": "https://www.swissmilk.ch",
        "language": "de",
    },
    "schweizerfleisch": {
        "id": 5,
        "display_name": "Schweizer Fleisch",
        "base_url": "https://www.schweizerfleisch.ch",
        "language": "de",
    },
}


def _get_source_id(adapter: SourceAdapter) -> int:
    """Map adapter key to a source ID. Simple sequential assignment."""
    meta = _SOURCE_METADATA.get(adapter.key)
    return meta["id"] if meta else 99


def _next_run_id(output_dir: Path) -> int:
    """Determine the next available etl_runs ID from existing data."""
    try:
        table = read_table("etl_runs", output_dir)
        if table.num_rows == 0:
            return 1
        return int(table.column("id").to_pylist()[-1]) + 1
    except DataStaleError:
        return 1
    except Exception:
        logger.warning("ETL: failed to read etl_runs for next ID, defaulting to 1", exc_info=True)
        return 1


def _get_existing_urls(output_dir: Path) -> set[str]:
    """Load existing source URLs to skip already-scraped recipes."""
    try:
        table = read_table("recipes", output_dir)
        return set(table.column("source_url").to_pylist())
    except Exception:
        return set()


def _validate_recipe_content(raw: RawRecipe, url: str) -> bool:
    """Check whether a raw recipe has sufficient content to be ingested.

    Rejects recipes with empty ingredients AND empty steps (likely non-recipe
    pages). Logs a warning for recipes with empty description but still allows
    ingestion.

    Returns:
        True if the recipe should be ingested, False if it should be skipped.
    """
    has_ingredients = bool(raw.ingredients_raw)
    has_steps = bool(raw.steps_raw)

    if not has_ingredients and not has_steps:
        logger.warning("ETL: skipping %s — empty ingredients and steps (likely not a recipe)", url)
        return False

    if not raw.description:
        logger.warning("ETL: recipe %s has empty description — ingesting anyway", url)

    return True


def _seed_lookup_tables(output_dir: Path, adapters: list[SourceAdapter]) -> None:
    """Write seed data to lookup tables if they are empty or missing.

    Ensures that ``sources.parquet`` contains metadata for all adapters
    being run and that ``ingredients.parquet`` contains the canonical
    seed catalogue. Idempotent — only writes when the table has zero rows
    or does not yet exist.
    """
    from recipebrain.normalise.ingredients import catalogue_to_rows

    # Seed sources
    try:
        sources_table = read_table("sources", output_dir)
        sources_empty = sources_table.num_rows == 0
    except Exception:
        sources_empty = True

    if sources_empty:
        source_rows = []
        for adapter in adapters:
            meta = _SOURCE_METADATA.get(adapter.key)
            if meta:
                source_rows.append(
                    {
                        "id": meta["id"],
                        "key": adapter.key,
                        "display_name": meta["display_name"],
                        "base_url": meta["base_url"],
                        "language": meta["language"],
                        "kind": "scraped",
                    }
                )
        if source_rows:
            write_table("sources", source_rows, output_dir)
            logger.info("ETL: seeded sources table with %d entries", len(source_rows))

    # Seed ingredients
    try:
        ingredients_table = read_table("ingredients", output_dir)
        ingredients_empty = ingredients_table.num_rows == 0
    except Exception:
        ingredients_empty = True

    if ingredients_empty:
        rows = catalogue_to_rows()
        if rows:
            write_table("ingredients", rows, output_dir)
            logger.info("ETL: seeded ingredients table with %d entries", len(rows))


def run_etl(
    settings: Settings,
    source_filter: str | None = None,
    limit: int | None = None,
    batch_size: int | None = None,
) -> list[EtlResult]:
    """Run the ETL pipeline for enabled sources.

    Args:
        settings: Application settings.
        source_filter: If set, only run this source adapter key.
        limit: If set, cap the number of new recipes fetched per source.
        batch_size: If set, flush to Parquet every N recipes (saves progress
            for long-running scrapes).

    Returns:
        List of EtlResult, one per source processed.
    """
    output_dir = Path(settings.paths.output_dir)
    snapshot_dir = Path(settings.paths.snapshot_dir)

    # Pre-ETL backup — protects against data loss during scraping
    try:
        snap = create_snapshot(output_dir, snapshot_dir, label="pre-etl")
        if snap:
            logger.info("ETL: pre-ETL snapshot created at %s", snap)
    except Exception:
        logger.warning("ETL: failed to create pre-ETL snapshot — continuing anyway")

    adapters = _get_source_adapters(settings, source_filter)

    if not adapters:
        logger.warning("No source adapters to run (filter=%s)", source_filter)
        return []

    # Seed lookup tables (sources, ingredients) before scraping
    _seed_lookup_tables(output_dir, adapters)

    results = []

    for adapter in adapters:
        result = _run_source(adapter, output_dir, limit=limit, batch_size=batch_size)
        results.append(result)

        # Clean up adapter resources
        if hasattr(adapter, "close"):
            adapter.close()

    # Write schema version sidecar after successful ETL
    if any(r.fetched > 0 for r in results):
        write_schema_version(output_dir)
        invalidate_connection(output_dir)

    return results


def _flush_rows(
    recipe_rows: list[dict],
    steps_rows: list[dict],
    images_rows: list[dict],
    ingredients_rows: list[dict],
    output_dir: Path,
    adapter_key: str,
) -> None:
    """Write accumulated rows to Parquet files and clear the lists."""
    if recipe_rows:
        append_table("recipes", recipe_rows, output_dir)
        logger.info("ETL: flushed %d recipes from %s", len(recipe_rows), adapter_key)
    if steps_rows:
        append_table("recipe_steps", steps_rows, output_dir)
    if images_rows:
        append_table("recipe_images", images_rows, output_dir)
    if ingredients_rows:
        append_table("recipe_ingredients", ingredients_rows, output_dir)

    recipe_rows.clear()
    steps_rows.clear()
    images_rows.clear()
    ingredients_rows.clear()


def _log_etl_run(
    result: EtlResult,
    started_at: datetime,
    t0: float,
    batch_size: int | None,
    limit: int | None,
    status: str,
    output_dir: Path,
) -> None:
    """Persist an ETL run log row to the etl_runs table."""
    effective_batch = batch_size if batch_size is not None else _DEFAULT_BATCH_SIZE
    finished_at = datetime.now(UTC)
    duration = time.monotonic() - t0
    error_summary = "; ".join(result.error_details[:10]) if result.error_details else None

    run_row = {
        "id": _next_run_id(output_dir),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration, 2),
        "source": result.source,
        "discovered": result.discovered,
        "fetched": result.fetched,
        "skipped": result.skipped,
        "errors": result.errors,
        "soft_deleted": result.soft_deleted,
        "validation_skipped": result.validation_skipped,
        "batch_size": effective_batch,
        "limit": limit,
        "error_summary": error_summary,
        "status": status,
    }
    try:
        append_table("etl_runs", [run_row], output_dir)
    except Exception:
        logger.warning("ETL: failed to write etl_runs log for %s", result.source, exc_info=True)


def _run_source(
    adapter: SourceAdapter,
    output_dir: Path,
    *,
    limit: int | None = None,
    batch_size: int | None = None,
) -> EtlResult:
    """Run ETL for a single source adapter.

    Args:
        adapter: The source adapter to run.
        output_dir: Directory for Parquet output.
        limit: If set, stop after fetching this many new recipes.
        batch_size: If set, flush to Parquet every N recipes. Useful for
            long-running scrapes so partial progress is saved to disk.
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    interrupted = False

    result = EtlResult(source=adapter.key)
    source_id = _get_source_id(adapter)
    existing_urls = _get_existing_urls(output_dir)
    next_id = _next_recipe_id(output_dir)

    logger.info("ETL: discovering recipes from %s", adapter.key)

    # Discover URLs
    urls: list[str] = []
    try:
        urls = list(adapter.discover())
        result.discovered = len(urls)
    except Exception as exc:
        logger.error("ETL: discovery failed for %s: %s", adapter.key, exc)
        result.errors += 1
        result.error_details.append(f"Discovery failed: {exc}")
        _log_etl_run(result, started_at, t0, batch_size, limit, "failed", output_dir)
        return result

    logger.info("ETL: found %d URLs from %s", len(urls), adapter.key)

    # Fetch & transform each recipe
    recipe_rows: list[dict] = []
    steps_rows: list[dict] = []
    images_rows: list[dict] = []
    ingredients_rows: list[dict] = []

    effective_batch = batch_size if batch_size is not None else _DEFAULT_BATCH_SIZE

    try:
        for url in urls:
            if limit is not None and result.fetched >= limit:
                break

            if url in existing_urls:
                result.skipped += 1
                continue

            try:
                raw = adapter.fetch(url)
            except Exception as exc:
                logger.warning("ETL: fetch failed for %s: %s", url, exc)
                result.errors += 1
                result.error_details.append(f"Fetch failed ({url}): {exc}")
                continue

            if not _validate_recipe_content(raw, url):
                result.validation_skipped += 1
                continue

            recipe_id = next_id
            next_id += 1

            # Build ingredient rows first — needed for computed tags
            recipe_ingredient_rows = build_recipe_ingredients_rows(
                recipe_id,
                raw.ingredients_raw,
                ingredient_groups=raw.ingredient_groups or None,
            )

            recipe_rows.append(
                build_recipe_row(
                    raw,
                    source_id=source_id,
                    recipe_id=recipe_id,
                    ingredient_rows=recipe_ingredient_rows,
                )
            )
            steps_rows.extend(build_recipe_steps_rows(recipe_id, raw.steps_raw))

            # Download images to local storage
            local_paths: list[str | None] | None = None
            if raw.image_urls and hasattr(adapter, "_http"):
                try:
                    local_paths = download_recipe_images(
                        raw.image_urls, recipe_id, output_dir, adapter._http
                    )
                except Exception as exc:
                    logger.warning("ETL: image download failed for recipe %d: %s", recipe_id, exc)

            images_rows.extend(
                build_recipe_images_rows(recipe_id, raw.image_urls, local_paths=local_paths)
            )
            ingredients_rows.extend(recipe_ingredient_rows)
            result.fetched += 1

            # Flush batch to disk periodically
            if effective_batch and len(recipe_rows) >= effective_batch:
                _flush_rows(
                    recipe_rows,
                    steps_rows,
                    images_rows,
                    ingredients_rows,
                    output_dir,
                    adapter.key,
                )
    except KeyboardInterrupt:
        interrupted = True
        logger.warning("ETL: interrupted — flushing %d buffered recipes to disk", len(recipe_rows))
    finally:
        # Always write remaining rows, even on Ctrl+C
        _flush_rows(
            recipe_rows,
            steps_rows,
            images_rows,
            ingredients_rows,
            output_dir,
            adapter.key,
        )

    # Soft-delete recipes whose URLs are no longer discovered
    deleted = _reconcile_deleted(source_id, set(urls), output_dir)
    if deleted:
        logger.info("ETL: soft-deleted %d recipes from %s", deleted, adapter.key)
    result.soft_deleted = deleted

    # Determine run status
    if interrupted:
        run_status = "interrupted"
    elif result.errors > 0 and result.fetched == 0:
        run_status = "failed"
    elif result.errors > 0:
        run_status = "partial"
    else:
        run_status = "success"

    _log_etl_run(result, started_at, t0, batch_size, limit, run_status, output_dir)

    return result


def _reconcile_deleted(source_id: int, discovered_urls: set[str], output_dir: Path) -> int:
    """Mark recipes as 'deleted' when their source URL is no longer discovered.

    Only affects recipes with ``status='active'`` that belong to the given
    source and whose ``source_url`` is absent from *discovered_urls*.

    Returns:
        Number of recipes soft-deleted.
    """
    try:
        table = read_table("recipes", output_dir)
    except Exception:
        return 0

    rows = table.to_pylist()
    count = 0
    changed = False
    for row in rows:
        if (
            row["source_id"] == source_id
            and row["status"] == "active"
            and row["source_url"] not in discovered_urls
        ):
            row["status"] = "deleted"
            count += 1
            changed = True

    if changed:
        write_table("recipes", rows, output_dir)

    return count
