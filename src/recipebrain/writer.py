"""Parquet writer and schema definitions.

All Parquet schemas are defined in SCHEMAS as pa.Schema objects.
When adding a new entity or column, update the schema dict first —
the writer enforces schema conformance.

Follows the cellarbrain writer pattern: SCHEMAS dict defines the
canonical schema per entity, write_table/append_table enforce conformance,
read_table returns typed PyArrow tables.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from recipebrain.exceptions import DataStaleError

# ---------------------------------------------------------------------------
# Schema definitions — source of truth for all Parquet datasets
# ---------------------------------------------------------------------------

SCHEMAS: dict[str, pa.Schema] = {
    "sources": pa.schema(
        [
            ("id", pa.int32()),
            ("key", pa.string()),
            ("display_name", pa.string()),
            ("base_url", pa.string()),
            ("language", pa.string()),
            ("kind", pa.string()),
        ]
    ),
    "recipes": pa.schema(
        [
            ("id", pa.int32()),
            ("source_id", pa.int32()),
            ("source_external_id", pa.string()),
            ("source_url", pa.string()),
            ("title", pa.string()),
            ("title_normalised", pa.string()),
            ("language", pa.string()),
            ("description", pa.string()),
            ("servings", pa.int16()),
            ("prep_minutes", pa.int16()),
            ("cook_minutes", pa.int16()),
            ("total_minutes", pa.int16()),
            ("difficulty", pa.string()),
            ("cuisine", pa.string()),
            ("course", pa.string()),
            ("primary_image_url", pa.string()),
            ("original_keywords", pa.list_(pa.string())),
            ("owner_rating", pa.int8()),
            ("starred", pa.bool_()),
            ("times_cooked", pa.int32()),
            ("last_cooked_at", pa.timestamp("us")),
            ("scraped_at", pa.timestamp("us")),
            ("updated_at", pa.timestamp("us")),
            ("content_hash", pa.string()),
            ("status", pa.string()),
            ("primary_protein", pa.string()),
            ("taste_profile", pa.string()),
            ("weight_class", pa.string()),
            ("cooking_method", pa.string()),
            ("dietary_flags", pa.list_(pa.string())),
            ("food_groups", pa.list_(pa.string())),
            ("computed_tags", pa.list_(pa.string())),
        ]
    ),
    "recipe_steps": pa.schema(
        [
            ("recipe_id", pa.int32()),
            ("step_no", pa.int16()),
            ("text", pa.string()),
            ("image_url", pa.string()),
        ]
    ),
    "recipe_images": pa.schema(
        [
            ("recipe_id", pa.int32()),
            ("seq", pa.int16()),
            ("url", pa.string()),
            ("local_path", pa.string()),
            ("caption", pa.string()),
        ]
    ),
    "ingredients": pa.schema(
        [
            ("id", pa.int32()),
            ("key", pa.string()),
            ("display_de", pa.string()),
            ("display_fr", pa.string()),
            ("display_it", pa.string()),
            ("display_en", pa.string()),
            ("category", pa.string()),
            ("sub_category", pa.string()),
            ("default_unit", pa.string()),
            ("density_g_per_ml", pa.float64()),
            ("pairing_tags", pa.list_(pa.string())),
            ("aliases", pa.list_(pa.string())),
        ]
    ),
    "recipe_ingredients": pa.schema(
        [
            ("recipe_id", pa.int32()),
            ("seq", pa.int16()),
            ("ingredient_id", pa.int32()),
            ("raw_text", pa.string()),
            ("quantity", pa.float64()),
            ("unit", pa.string()),
            ("prep_note", pa.string()),
            ("optional", pa.bool_()),
            ("group_label", pa.string()),
        ]
    ),
    "tags": pa.schema(
        [
            ("id", pa.int32()),
            ("key", pa.string()),
            ("display", pa.string()),
            ("facet", pa.string()),
        ]
    ),
    "recipe_tags": pa.schema(
        [
            ("recipe_id", pa.int32()),
            ("tag_id", pa.int32()),
        ]
    ),
    "cook_log": pa.schema(
        [
            ("id", pa.int64()),
            ("recipe_id", pa.int32()),
            ("cooked_on", pa.date32()),
            ("servings", pa.int16()),
            ("scale_factor", pa.float64()),
            ("rating", pa.int8()),
            ("notes", pa.string()),
            ("logged_at", pa.timestamp("us")),
        ]
    ),
    "pantry": pa.schema(
        [
            ("ingredient_id", pa.int32()),
            ("approx_quantity", pa.float64()),
            ("unit", pa.string()),
            ("location", pa.string()),
            ("updated_at", pa.timestamp("us")),
            ("note", pa.string()),
        ]
    ),
    "retailers": pa.schema(
        [
            ("id", pa.int32()),
            ("key", pa.string()),
            ("display_name", pa.string()),
            ("base_url", pa.string()),
        ]
    ),
    "promotions": pa.schema(
        [
            ("id", pa.int64()),
            ("retailer_id", pa.int32()),
            ("product_name", pa.string()),
            ("brand", pa.string()),
            ("pack_size", pa.string()),
            ("pack_quantity", pa.float64()),
            ("pack_unit", pa.string()),
            ("price_chf", pa.float64()),
            ("regular_price_chf", pa.float64()),
            ("discount_pct", pa.float64()),
            ("valid_from", pa.date32()),
            ("valid_to", pa.date32()),
            ("source_url", pa.string()),
            ("scraped_at", pa.timestamp("us")),
        ]
    ),
    "promotion_ingredient_map": pa.schema(
        [
            ("promotion_id", pa.int64()),
            ("ingredient_id", pa.int32()),
            ("confidence", pa.float32()),
            ("match_method", pa.string()),
            ("reviewed", pa.bool_()),
        ]
    ),
    "pinned_recipes": pa.schema(
        [
            ("id", pa.int32()),
            ("recipe_id", pa.int32()),
            ("pinned_at", pa.timestamp("us")),
            ("target_date", pa.date32()),
            ("note", pa.string()),
            ("status", pa.string()),
        ]
    ),
    "etl_runs": pa.schema(
        [
            ("id", pa.int64()),
            ("started_at", pa.timestamp("us")),
            ("finished_at", pa.timestamp("us")),
            ("duration_seconds", pa.float64()),
            ("source", pa.string()),
            ("discovered", pa.int32()),
            ("fetched", pa.int32()),
            ("skipped", pa.int32()),
            ("errors", pa.int32()),
            ("soft_deleted", pa.int32()),
            ("batch_size", pa.int16()),
            ("limit", pa.int32()),
            ("error_summary", pa.string()),
            ("status", pa.string()),
        ]
    ),
}


# ---------------------------------------------------------------------------
# Write / Read API
# ---------------------------------------------------------------------------


def _parquet_path(entity: str, output_dir: Path) -> Path:
    """Return the canonical parquet file path for an entity."""
    return output_dir / f"{entity}.parquet"


def _validate_entity(entity: str) -> pa.Schema:
    """Validate that an entity name is known and return its schema."""
    if entity not in SCHEMAS:
        raise ValueError(f"Unknown entity '{entity}'. Known: {sorted(SCHEMAS.keys())}")
    return SCHEMAS[entity]


def _build_table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    """Build a PyArrow table from rows, enforcing schema conformance.

    Missing columns are filled with nulls. Extra columns are rejected.
    """
    schema_names = set(schema.names)
    if rows:
        row_names = set(rows[0].keys())
        extra = row_names - schema_names
        if extra:
            raise ValueError(f"Unexpected columns: {sorted(extra)}")

    # Build column arrays respecting schema order and types
    arrays = []
    for field in schema:
        values = [row.get(field.name) for row in rows]
        arrays.append(pa.array(values, type=field.type))

    return pa.table(arrays, schema=schema)


def write_table(entity: str, rows: list[dict], output_dir: Path) -> Path:
    """Write rows to a Parquet file, overwriting any existing data.

    Validates rows against SCHEMAS[entity]. Creates output_dir if needed.

    Returns:
        Path to the written parquet file.

    Raises:
        ValueError: If entity is unknown or rows contain invalid columns.
    """
    schema = _validate_entity(entity)
    table = _build_table(rows, schema)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = _parquet_path(entity, output_dir)
    pq.write_table(table, path)
    return path


def append_table(entity: str, rows: list[dict], output_dir: Path) -> Path:
    """Append rows to an existing Parquet file, or create if it doesn't exist.

    Does NOT deduplicate — caller is responsible for ensuring no duplicates
    unless the entity has a primary key that the ETL layer manages.

    Returns:
        Path to the written parquet file.
    """
    schema = _validate_entity(entity)
    new_table = _build_table(rows, schema)

    path = _parquet_path(entity, output_dir)
    if path.exists():
        existing = pq.read_table(path, schema=schema)
        combined = pa.concat_tables([existing, new_table], promote_options="default")
    else:
        combined = new_table

    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(combined, path)
    return path


def read_table(entity: str, output_dir: Path) -> pa.Table:
    """Read a Parquet dataset for the given entity.

    Returns:
        The PyArrow table.

    Raises:
        DataStaleError: If the parquet file does not exist.
        ValueError: If entity is unknown.
    """
    _validate_entity(entity)
    path = _parquet_path(entity, output_dir)
    if not path.exists():
        raise DataStaleError(f"Parquet file missing for entity '{entity}': {path}")
    return pq.read_table(path)


# ---------------------------------------------------------------------------
# Schema version sidecar
# ---------------------------------------------------------------------------

_SCHEMA_VERSION_FILE = ".schema_version.json"


def compute_schema_hash() -> str:
    """Compute a deterministic hash of the current SCHEMAS definitions."""
    parts: list[str] = []
    for entity in sorted(SCHEMAS):
        schema = SCHEMAS[entity]
        for fld in schema:
            parts.append(f"{entity}.{fld.name}:{fld.type}")
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return digest


def write_schema_version(output_dir: Path) -> Path:
    """Write a schema version sidecar file to the output directory.

    Returns:
        Path to the written sidecar file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / _SCHEMA_VERSION_FILE
    payload = {"schema_hash": compute_schema_hash(), "entity_count": len(SCHEMAS)}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def read_schema_version(output_dir: Path) -> str | None:
    """Read the schema hash from the sidecar file, or None if missing."""
    path = output_dir / _SCHEMA_VERSION_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("schema_hash")
    except (json.JSONDecodeError, KeyError):
        return None


def seed_empty_tables(output_dir: Path) -> list[Path]:
    """Create empty Parquet files for all entities that don't yet exist.

    Returns:
        Paths of newly created files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for entity, schema in SCHEMAS.items():
        path = _parquet_path(entity, output_dir)
        if path.exists():
            continue
        table = pa.table({f.name: pa.array([], type=f.type) for f in schema}, schema=schema)
        pq.write_table(table, path)
        created.append(path)
    return created
