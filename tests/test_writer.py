"""Tests for the Parquet writer and schema definitions."""

from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pytest

from recipebrain.query import DataStaleError
from recipebrain.writer import (
    SCHEMAS,
    _build_table,
    append_table,
    compute_schema_hash,
    read_schema_version,
    read_table,
    seed_empty_tables,
    write_schema_version,
    write_table,
)


class TestSchemas:
    def test_all_schemas_are_pa_schema(self):
        for name, schema in SCHEMAS.items():
            assert isinstance(schema, pa.Schema), f"{name} is not a pa.Schema"

    def test_expected_entities_present(self):
        expected = {
            "sources",
            "recipes",
            "recipe_steps",
            "recipe_images",
            "ingredients",
            "recipe_ingredients",
            "tags",
            "recipe_tags",
            "cook_log",
            "pantry",
            "retailers",
            "promotions",
            "promotion_ingredient_map",
            "pinned_recipes",
            "etl_runs",
        }
        assert expected == set(SCHEMAS.keys())

    def test_recipes_has_expected_columns(self):
        names = SCHEMAS["recipes"].names
        assert "id" in names
        assert "title" in names
        assert "source_url" in names
        assert "original_keywords" in names


class TestBuildTable:
    def test_builds_table_from_rows(self):
        rows = [
            {
                "id": 1,
                "key": "fooby",
                "display_name": "Fooby",
                "base_url": "https://fooby.ch",
                "language": "de",
                "kind": "scraped",
            },
        ]
        table = _build_table(rows, SCHEMAS["sources"])
        assert table.num_rows == 1
        assert table.column("key")[0].as_py() == "fooby"

    def test_fills_missing_columns_with_null(self):
        rows = [{"id": 1, "key": "test"}]
        table = _build_table(rows, SCHEMAS["sources"])
        assert table.num_rows == 1
        assert table.column("display_name")[0].as_py() is None

    def test_rejects_extra_columns(self):
        rows = [{"id": 1, "key": "test", "bogus_column": "bad"}]
        with pytest.raises(ValueError, match="Unexpected columns"):
            _build_table(rows, SCHEMAS["sources"])

    def test_empty_rows_produces_empty_table(self):
        table = _build_table([], SCHEMAS["sources"])
        assert table.num_rows == 0
        assert table.schema == SCHEMAS["sources"]


class TestWriteTable:
    def test_write_and_read_roundtrip(self, tmp_path):
        rows = [
            {
                "id": 1,
                "key": "fooby",
                "display_name": "Fooby",
                "base_url": "https://fooby.ch",
                "language": "de",
                "kind": "scraped",
            },
            {
                "id": 2,
                "key": "migusto",
                "display_name": "Migusto",
                "base_url": "https://migusto.migros.ch",
                "language": "de",
                "kind": "scraped",
            },
        ]
        path = write_table("sources", rows, tmp_path)

        assert path.exists()
        assert path.name == "sources.parquet"

        table = read_table("sources", tmp_path)
        assert table.num_rows == 2
        assert table.column("key")[0].as_py() == "fooby"
        assert table.column("key")[1].as_py() == "migusto"

    def test_write_creates_output_dir(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        write_table("sources", [{"id": 1, "key": "x"}], nested)
        assert (nested / "sources.parquet").exists()

    def test_write_overwrites_existing(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "old"}], tmp_path)
        write_table("sources", [{"id": 2, "key": "new"}], tmp_path)

        table = read_table("sources", tmp_path)
        assert table.num_rows == 1
        assert table.column("key")[0].as_py() == "new"

    def test_write_unknown_entity_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown entity"):
            write_table("nonexistent", [{"id": 1}], tmp_path)

    def test_write_with_list_column(self, tmp_path):
        rows = [
            {
                "id": 1,
                "key": "chicken",
                "display_de": "Huhn",
                "pairing_tags": ["poultry", "white-meat"],
                "aliases": ["poulet", "chicken"],
            },
        ]
        write_table("ingredients", rows, tmp_path)
        table = read_table("ingredients", tmp_path)
        assert table.column("pairing_tags")[0].as_py() == ["poultry", "white-meat"]

    def test_write_with_date_and_timestamp(self, tmp_path):
        rows = [
            {
                "id": 1,
                "recipe_id": 10,
                "cooked_on": date(2025, 3, 15),
                "servings": 4,
                "scale_factor": None,
                "rating": 5,
                "notes": "great",
                "logged_at": datetime(2025, 3, 15, 19, 0),
            },
        ]
        write_table("cook_log", rows, tmp_path)
        table = read_table("cook_log", tmp_path)
        assert table.column("cooked_on")[0].as_py() == date(2025, 3, 15)


class TestAppendTable:
    def test_append_creates_if_missing(self, tmp_path):
        rows = [{"id": 1, "key": "fooby"}]
        append_table("sources", rows, tmp_path)

        table = read_table("sources", tmp_path)
        assert table.num_rows == 1

    def test_append_adds_to_existing(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        append_table("sources", [{"id": 2, "key": "migusto"}], tmp_path)

        table = read_table("sources", tmp_path)
        assert table.num_rows == 2

    def test_append_does_not_deduplicate(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        append_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)

        table = read_table("sources", tmp_path)
        assert table.num_rows == 2


class TestReadTable:
    def test_raises_data_stale_on_missing_file(self, tmp_path):
        with pytest.raises(DataStaleError, match="Parquet file missing"):
            read_table("sources", tmp_path)

    def test_raises_value_error_on_unknown_entity(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown entity"):
            read_table("bogus", tmp_path)


class TestSchemaVersion:
    def test_compute_hash_is_deterministic(self):
        h1 = compute_schema_hash()
        h2 = compute_schema_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_write_and_read_roundtrip(self, tmp_path):
        write_schema_version(tmp_path)
        stored = read_schema_version(tmp_path)
        assert stored == compute_schema_hash()

    def test_read_returns_none_when_missing(self, tmp_path):
        assert read_schema_version(tmp_path) is None

    def test_read_returns_none_on_corrupt_file(self, tmp_path):
        (tmp_path / ".schema_version.json").write_text("not json", encoding="utf-8")
        assert read_schema_version(tmp_path) is None


class TestSeedEmptyTables:
    def test_creates_all_entities(self, tmp_path):
        created = seed_empty_tables(tmp_path)
        assert len(created) == len(SCHEMAS)
        for entity in SCHEMAS:
            path = tmp_path / f"{entity}.parquet"
            assert path.exists()
            table = read_table(entity, tmp_path)
            assert table.num_rows == 0

    def test_skips_existing_files(self, tmp_path):
        write_table("recipes", [{"id": 1, "title": "X"}], tmp_path)
        created = seed_empty_tables(tmp_path)
        assert not any(p.name == "recipes.parquet" for p in created)
        assert len(created) == len(SCHEMAS) - 1
        # Existing data is preserved
        assert read_table("recipes", tmp_path).num_rows == 1

    def test_creates_output_dir_if_missing(self, tmp_path):
        out = tmp_path / "new_output"
        seed_empty_tables(out)
        assert out.is_dir()
