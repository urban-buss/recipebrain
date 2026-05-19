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
from recipebrain.settings import ImagesConfig, Settings
from recipebrain.snapshot import create_snapshot
from recipebrain.sources.base import RawRecipe, SourceAdapter
from recipebrain.transform import (
    build_recipe_images_rows,
    build_recipe_ingredients_rows,
    build_recipe_row,
    build_recipe_steps_rows,
    build_tag_rows_from_classification,
    build_tag_rows_from_keywords,
)
from recipebrain.writer import (
    append_table,
    read_table,
    update_table_row,
    write_schema_version,
    write_table,
)

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


def _get_existing_tags(output_dir: Path) -> tuple[dict[str, int], int]:
    """Load existing tag keys with IDs and determine the next tag ID.

    Returns:
        Tuple of (existing_tags dict key→id, next_tag_id).
    """
    try:
        table = read_table("tags", output_dir)
        if table.num_rows == 0:
            return {}, 1
        keys = table.column("key").to_pylist()
        ids = table.column("id").to_pylist()
        tag_dict = dict(zip(keys, ids, strict=False))
        next_id = max(ids) + 1
        return tag_dict, next_id
    except Exception:
        return {}, 1


# Static source metadata. The "language" field represents the primary/default
# language for each source — the actual languages fetched are controlled by
# SourceConfig.languages in the settings.
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
    pages). Logs warnings for quality issues but only hard-rejects clearly
    broken pages.

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

    # Ingredient quality heuristics (warn but don't reject)
    if raw.ingredients_raw:
        _warn_on_suspicious_ingredients(raw.ingredients_raw, url)

    return True


_INGREDIENT_NAV_KEYWORDS: frozenset[str] = frozenset(
    {
        "hauptmenü",
        "menu schliessen",
        "jetzt entdecken",
        "jetzt weiterstöbern",
        "werbung buchen",
    }
)


def _warn_on_suspicious_ingredients(ingredients: list[str], url: str) -> None:
    """Log a warning if ingredient data looks like navigation text.

    Heuristics:
    - Average length > 150 chars (real ingredients are typically < 80)
    - Contains known navigation keywords
    - No items contain recognisable quantity patterns

    Examples:
        >>> import logging; logging.disable(logging.CRITICAL)
        >>> _warn_on_suspicious_ingredients(["200 g Mehl", "3 Eier"], "http://x")
        >>> _warn_on_suspicious_ingredients(["ShopHauptmenü..."], "http://x")
    """
    avg_len = sum(len(i) for i in ingredients) / len(ingredients)
    if avg_len > 150:
        logger.warning(
            "ETL: suspicious ingredients at %s — avg length %.0f chars (expected < 80)",
            url,
            avg_len,
        )
        return

    combined = " ".join(ingredients).lower()
    if any(kw in combined for kw in _INGREDIENT_NAV_KEYWORDS):
        logger.warning(
            "ETL: suspicious ingredients at %s — contains navigation keywords",
            url,
        )
        return

    # Check for quantity patterns (at least 20% of items should have one)
    if len(ingredients) >= 3:
        qty_count = sum(1 for item in ingredients if any(c.isdigit() for c in item))
        if qty_count / len(ingredients) < 0.2:
            logger.warning(
                "ETL: suspicious ingredients at %s — only %d/%d items contain numbers",
                url,
                qty_count,
                len(ingredients),
            )


def _seed_lookup_tables(
    output_dir: Path, adapters: list[SourceAdapter], settings: Settings | None = None
) -> None:
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
                # Use configured primary language if available
                source_cfg = settings.sources.get(adapter.key) if settings else None
                language = source_cfg.language if source_cfg else meta["language"]
                source_rows.append(
                    {
                        "id": meta["id"],
                        "key": adapter.key,
                        "display_name": meta["display_name"],
                        "base_url": meta["base_url"],
                        "language": language,
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
    _seed_lookup_tables(output_dir, adapters, settings)

    results = []

    for adapter in adapters:
        source_cfg = settings.sources.get(adapter.key)
        allowed_languages = source_cfg.languages if source_cfg else ["de"]
        result = _run_source(
            adapter,
            output_dir,
            limit=limit,
            batch_size=batch_size,
            images_config=settings.images,
            allowed_languages=allowed_languages,
        )
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
    *,
    tag_rows: list[dict] | None = None,
    recipe_tag_rows: list[dict] | None = None,
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
    if tag_rows:
        append_table("tags", tag_rows, output_dir)
    if recipe_tag_rows:
        append_table("recipe_tags", recipe_tag_rows, output_dir)

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


def _start_etl_run(
    source_key: str,
    started_at: datetime,
    batch_size: int | None,
    limit: int | None,
    output_dir: Path,
) -> int:
    """Write an initial 'running' etl_runs row at source start.

    Returns the assigned run ID for subsequent updates.
    """
    effective_batch = batch_size if batch_size is not None else _DEFAULT_BATCH_SIZE
    run_id = _next_run_id(output_dir)

    run_row = {
        "id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "source": source_key,
        "discovered": 0,
        "fetched": 0,
        "skipped": 0,
        "errors": 0,
        "soft_deleted": 0,
        "validation_skipped": 0,
        "batch_size": effective_batch,
        "limit": limit,
        "error_summary": None,
        "status": "running",
    }
    try:
        append_table("etl_runs", [run_row], output_dir)
    except Exception:
        logger.warning("ETL: failed to write initial etl_runs for %s", source_key, exc_info=True)
    return run_id


def _update_etl_run_progress(
    run_id: int,
    result: EtlResult,
    output_dir: Path,
) -> None:
    """Update counters on an in-progress etl_runs row after a batch flush."""
    updates = {
        "discovered": result.discovered,
        "fetched": result.fetched,
        "skipped": result.skipped,
        "errors": result.errors,
        "validation_skipped": result.validation_skipped,
    }
    try:
        update_table_row("etl_runs", run_id, updates, output_dir)
    except Exception:
        logger.warning("ETL: failed to update etl_runs progress for run %d", run_id, exc_info=True)


def _finish_etl_run(
    run_id: int,
    result: EtlResult,
    t0: float,
    status: str,
    output_dir: Path,
) -> None:
    """Finalize an etl_runs row with final counters, status, and timestamps."""
    finished_at = datetime.now(UTC)
    duration = time.monotonic() - t0
    error_summary = "; ".join(result.error_details[:10]) if result.error_details else None

    updates = {
        "finished_at": finished_at,
        "duration_seconds": round(duration, 2),
        "discovered": result.discovered,
        "fetched": result.fetched,
        "skipped": result.skipped,
        "errors": result.errors,
        "soft_deleted": result.soft_deleted,
        "validation_skipped": result.validation_skipped,
        "error_summary": error_summary,
        "status": status,
    }
    try:
        update_table_row("etl_runs", run_id, updates, output_dir)
    except Exception:
        logger.warning("ETL: failed to finalize etl_runs for run %d", run_id, exc_info=True)


def _detect_interrupted_runs(source_key: str, output_dir: Path) -> list[dict]:
    """Find previous runs for this source that are still marked 'running'.

    These indicate a crashed/interrupted run whose progress was already
    flushed to the recipes table (and thus will be skipped on resumption).
    """
    try:
        table = read_table("etl_runs", output_dir)
    except (DataStaleError, Exception):
        return []

    rows = table.to_pylist()
    return [r for r in rows if r.get("source") == source_key and r.get("status") == "running"]


def _run_source(
    adapter: SourceAdapter,
    output_dir: Path,
    *,
    limit: int | None = None,
    batch_size: int | None = None,
    images_config: ImagesConfig | None = None,
    allowed_languages: list[str] | None = None,
) -> EtlResult:
    """Run ETL for a single source adapter.

    Args:
        adapter: The source adapter to run.
        output_dir: Directory for Parquet output.
        limit: If set, stop after fetching this many new recipes.
        batch_size: If set, flush to Parquet every N recipes. Useful for
            long-running scrapes so partial progress is saved to disk.
        allowed_languages: If set, skip recipes whose language is not in
            this list. Safety net for language filtering.
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    interrupted = False

    result = EtlResult(source=adapter.key)
    source_id = _get_source_id(adapter)
    existing_urls = _get_existing_urls(output_dir)
    next_id = _next_recipe_id(output_dir)
    existing_tags, next_tag_id = _get_existing_tags(output_dir)

    # Detect previous interrupted runs for this source (indicates resumption)
    stale_runs = _detect_interrupted_runs(adapter.key, output_dir)
    if stale_runs:
        for stale in stale_runs:
            logger.info(
                "ETL: marking stale run %d for %s as 'crashed' (started %s)",
                stale["id"],
                adapter.key,
                stale.get("started_at"),
            )
            _finish_etl_run(stale["id"], EtlResult(source=adapter.key), t0, "crashed", output_dir)
        logger.info(
            "ETL: resuming %s — %d URLs already processed from previous run(s)",
            adapter.key,
            len(existing_urls),
        )

    # Write initial "running" row immediately (visible even if process crashes)
    run_id = _start_etl_run(adapter.key, started_at, batch_size, limit, output_dir)

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
        _finish_etl_run(run_id, result, t0, "failed", output_dir)
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

            # Language safety net — skip recipes not in allowed languages
            if allowed_languages and raw.language not in allowed_languages:
                result.skipped += 1
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
                        raw.image_urls,
                        recipe_id,
                        output_dir,
                        adapter._http,
                        config=images_config,
                    )
                except Exception as exc:
                    logger.warning("ETL: image download failed for recipe %d: %s", recipe_id, exc)

            images_rows.extend(
                build_recipe_images_rows(
                    recipe_id,
                    raw.image_urls,
                    local_paths=local_paths,
                    captions=raw.image_captions or None,
                )
            )
            ingredients_rows.extend(recipe_ingredient_rows)
            result.fetched += 1

            # Flush batch to disk periodically
            if effective_batch and len(recipe_rows) >= effective_batch:
                # Build tags from this batch's keywords
                kw_pairs = [(r["id"], r.get("original_keywords") or []) for r in recipe_rows]
                batch_tags, batch_rt = build_tag_rows_from_keywords(
                    kw_pairs, existing_tags, next_tag_id
                )
                # Track state across batches
                for t in batch_tags:
                    existing_tags[t["key"]] = t["id"]
                if batch_tags:
                    next_tag_id = batch_tags[-1]["id"] + 1

                # Build tags from computed classification fields
                cls_tags, cls_rt = build_tag_rows_from_classification(
                    recipe_rows, existing_tags, next_tag_id
                )
                for t in cls_tags:
                    existing_tags[t["key"]] = t["id"]
                if cls_tags:
                    next_tag_id = cls_tags[-1]["id"] + 1

                _flush_rows(
                    recipe_rows,
                    steps_rows,
                    images_rows,
                    ingredients_rows,
                    output_dir,
                    adapter.key,
                    tag_rows=batch_tags + cls_tags,
                    recipe_tag_rows=batch_rt + cls_rt,
                )

                # Update run progress after each batch flush
                _update_etl_run_progress(run_id, result, output_dir)
    except KeyboardInterrupt:
        interrupted = True
        logger.warning("ETL: interrupted — flushing %d buffered recipes to disk", len(recipe_rows))
    finally:
        # Build tags from remaining rows
        kw_pairs = [(r["id"], r.get("original_keywords") or []) for r in recipe_rows]
        remaining_tags, remaining_rt = build_tag_rows_from_keywords(
            kw_pairs, existing_tags, next_tag_id
        )
        for t in remaining_tags:
            existing_tags[t["key"]] = t["id"]
        if remaining_tags:
            next_tag_id = remaining_tags[-1]["id"] + 1

        # Build tags from computed classification fields
        cls_tags, cls_rt = build_tag_rows_from_classification(
            recipe_rows, existing_tags, next_tag_id
        )
        for t in cls_tags:
            existing_tags[t["key"]] = t["id"]

        # Always write remaining rows, even on Ctrl+C
        _flush_rows(
            recipe_rows,
            steps_rows,
            images_rows,
            ingredients_rows,
            output_dir,
            adapter.key,
            tag_rows=remaining_tags + cls_tags,
            recipe_tag_rows=remaining_rt + cls_rt,
        )

    # Soft-delete recipes whose URLs are no longer discovered
    try:
        deleted = _reconcile_deleted(source_id, set(urls), output_dir)
        if deleted:
            logger.info("ETL: soft-deleted %d recipes from %s", deleted, adapter.key)
        result.soft_deleted = deleted
    except Exception as exc:
        logger.warning("ETL: reconcile_deleted failed for %s: %s", adapter.key, exc)

    # Determine run status
    if interrupted:
        run_status = "interrupted"
    elif result.errors > 0 and result.fetched == 0:
        run_status = "failed"
    elif result.errors > 0:
        run_status = "partial"
    else:
        run_status = "success"

    _finish_etl_run(run_id, result, t0, run_status, output_dir)

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
