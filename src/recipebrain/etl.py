"""ETL orchestrator: discover → fetch → transform → write.

Connects source adapters to the transform layer and Parquet writer,
running the full pipeline for one or more recipe sources.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from recipebrain.query import invalidate_connection
from recipebrain.settings import Settings
from recipebrain.snapshot import create_snapshot
from recipebrain.sources.base import SourceAdapter
from recipebrain.transform import (
    build_recipe_images_rows,
    build_recipe_ingredients_rows,
    build_recipe_row,
    build_recipe_steps_rows,
)
from recipebrain.writer import append_table, read_table, write_schema_version, write_table

logger = logging.getLogger(__name__)


@dataclass
class EtlResult:
    """Summary of an ETL run."""

    source: str
    discovered: int = 0
    fetched: int = 0
    skipped: int = 0
    errors: int = 0
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
        adapters.append(adapter_cls(settings))

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


def _get_source_id(adapter: SourceAdapter) -> int:
    """Map adapter key to a source ID. Simple sequential assignment."""
    source_ids = {
        "fooby": 1,
        "migusto": 2,
        "swissmilk": 3,
        "schweizerfleisch": 4,
    }
    return source_ids.get(adapter.key, 99)


def _get_existing_urls(output_dir: Path) -> set[str]:
    """Load existing source URLs to skip already-scraped recipes."""
    try:
        table = read_table("recipes", output_dir)
        return set(table.column("source_url").to_pylist())
    except Exception:
        return set()


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
        return result

    logger.info("ETL: found %d URLs from %s", len(urls), adapter.key)

    # Fetch & transform each recipe
    recipe_rows: list[dict] = []
    steps_rows: list[dict] = []
    images_rows: list[dict] = []
    ingredients_rows: list[dict] = []

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

        recipe_id = next_id
        next_id += 1

        recipe_rows.append(build_recipe_row(raw, source_id=source_id, recipe_id=recipe_id))
        steps_rows.extend(build_recipe_steps_rows(recipe_id, raw.steps_raw))
        images_rows.extend(build_recipe_images_rows(recipe_id, raw.image_urls))
        ingredients_rows.extend(build_recipe_ingredients_rows(recipe_id, raw.ingredients_raw))
        result.fetched += 1

        # Flush batch to disk periodically
        if batch_size and len(recipe_rows) >= batch_size:
            _flush_rows(
                recipe_rows,
                steps_rows,
                images_rows,
                ingredients_rows,
                output_dir,
                adapter.key,
            )

    # Write remaining rows
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
