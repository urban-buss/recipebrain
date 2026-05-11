"""Tests for recipebrain.validate — data integrity checks."""

from __future__ import annotations

import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from recipebrain.validate import ValidationResult, validate
from recipebrain.writer import SCHEMAS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_table(tmp_path: Path, entity: str, rows: list[dict]) -> None:
    schema = SCHEMAS[entity]
    cols: dict[str, list] = {}
    for name in schema.names:
        cols[name] = [r.get(name) for r in rows]
    table = pa.table(cols, schema=schema)
    pq.write_table(table, tmp_path / f"{entity}.parquet")


def _make_recipe(**overrides: object) -> dict:
    defaults: dict = {
        "id": 1,
        "source_id": 1,
        "source_external_id": "r1",
        "source_url": "http://x",
        "title": "Test Recipe",
        "title_normalised": "test recipe",
        "language": "de",
        "description": "",
        "servings": 4,
        "prep_minutes": None,
        "cook_minutes": None,
        "total_minutes": 30,
        "difficulty": "easy",
        "cuisine": "swiss",
        "course": "main",
        "primary_image_url": None,
        "original_keywords": [],
        "owner_rating": None,
        "starred": False,
        "times_cooked": 0,
        "last_cooked_at": None,
        "scraped_at": datetime.datetime(2024, 1, 1),
        "updated_at": datetime.datetime(2024, 1, 1),
        "content_hash": "h",
        "status": "active",
    }
    defaults.update(overrides)
    return defaults


def _make_source(**overrides: object) -> dict:
    defaults: dict = {
        "id": 1,
        "key": "fooby",
        "display_name": "Fooby",
        "base_url": "https://fooby.ch",
        "language": "de",
        "kind": "scraped",
    }
    defaults.update(overrides)
    return defaults


def _good_dataset(tmp_path: Path) -> None:
    """Write a complete, valid minimal dataset."""
    _write_table(tmp_path, "sources", [_make_source()])
    _write_table(tmp_path, "recipes", [_make_recipe()])
    _write_table(
        tmp_path,
        "recipe_ingredients",
        [
            {
                "recipe_id": 1,
                "seq": 1,
                "ingredient_id": None,
                "raw_text": "200 g Mehl",
                "quantity": 200.0,
                "unit": "g",
                "prep_note": None,
                "optional": False,
                "group_label": None,
            },
        ],
    )
    _write_table(
        tmp_path,
        "recipe_steps",
        [
            {"recipe_id": 1, "step_no": 1, "text": "Mix.", "image_url": None},
        ],
    )


# ---------------------------------------------------------------------------
# TestValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_ok_when_empty(self) -> None:
        r = ValidationResult()
        assert r.ok

    def test_not_ok_with_issues(self) -> None:
        r = ValidationResult()
        r.add("something wrong")
        assert not r.ok

    def test_check_increments(self) -> None:
        r = ValidationResult()
        r.check("test1")
        r.check("test2")
        assert r.checks_run == 2


# ---------------------------------------------------------------------------
# TestValidate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_good_dataset_passes(self, tmp_path: Path) -> None:
        _good_dataset(tmp_path)
        result = validate(tmp_path)
        assert result.ok
        assert result.checks_run >= 4

    def test_missing_parquet_files(self, tmp_path: Path) -> None:
        result = validate(tmp_path)
        assert not result.ok
        assert any("Missing Parquet" in i for i in result.issues)

    def test_missing_recipe_title(self, tmp_path: Path) -> None:
        _write_table(tmp_path, "sources", [_make_source()])
        _write_table(tmp_path, "recipes", [_make_recipe(title="")])
        _write_table(tmp_path, "recipe_ingredients", [])
        _write_table(tmp_path, "recipe_steps", [])
        result = validate(tmp_path)
        assert any("missing required field" in i for i in result.issues)

    def test_orphan_ingredient_fk(self, tmp_path: Path) -> None:
        _write_table(tmp_path, "sources", [_make_source()])
        _write_table(tmp_path, "recipes", [_make_recipe()])
        _write_table(
            tmp_path,
            "recipe_ingredients",
            [
                {
                    "recipe_id": 999,
                    "seq": 1,
                    "ingredient_id": None,
                    "raw_text": "x",
                    "quantity": None,
                    "unit": None,
                    "prep_note": None,
                    "optional": False,
                    "group_label": None,
                },
            ],
        )
        _write_table(tmp_path, "recipe_steps", [])
        result = validate(tmp_path)
        assert any("recipe_ingredients references missing" in i for i in result.issues)

    def test_orphan_step_fk(self, tmp_path: Path) -> None:
        _write_table(tmp_path, "sources", [_make_source()])
        _write_table(tmp_path, "recipes", [_make_recipe()])
        _write_table(tmp_path, "recipe_ingredients", [])
        _write_table(
            tmp_path,
            "recipe_steps",
            [
                {"recipe_id": 999, "step_no": 1, "text": "x", "image_url": None},
            ],
        )
        result = validate(tmp_path)
        assert any("recipe_steps references missing" in i for i in result.issues)

    def test_duplicate_recipes(self, tmp_path: Path) -> None:
        _write_table(tmp_path, "sources", [_make_source()])
        _write_table(
            tmp_path,
            "recipes",
            [
                _make_recipe(id=1),
                _make_recipe(id=2),  # same source_id + source_external_id
            ],
        )
        _write_table(tmp_path, "recipe_ingredients", [])
        _write_table(tmp_path, "recipe_steps", [])
        result = validate(tmp_path)
        assert any("Duplicate recipe" in i for i in result.issues)

    def test_orphan_cook_log(self, tmp_path: Path) -> None:
        _write_table(tmp_path, "sources", [_make_source()])
        _write_table(tmp_path, "recipes", [_make_recipe()])
        _write_table(tmp_path, "recipe_ingredients", [])
        _write_table(tmp_path, "recipe_steps", [])
        _write_table(
            tmp_path,
            "cook_log",
            [
                {
                    "id": 1,
                    "recipe_id": 999,
                    "cooked_on": datetime.date(2024, 6, 1),
                    "servings": 4,
                    "scale_factor": None,
                    "rating": None,
                    "notes": None,
                    "logged_at": datetime.datetime(2024, 6, 1),
                },
            ],
        )
        result = validate(tmp_path)
        assert any("cook_log references missing" in i for i in result.issues)
