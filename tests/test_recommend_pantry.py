"""Tests for recipebrain.recommend.pantry — pantry coverage suggestions."""

from __future__ import annotations

import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from recipebrain.recommend.pantry import PANTRY_STAPLES, suggest_for_pantry
from recipebrain.writer import SCHEMAS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_recipes(tmp_path: Path, rows: list[dict]) -> None:
    defaults: dict = {
        "source_id": 1,
        "source_external_id": "x",
        "source_url": "http://x",
        "title_normalised": "",
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
    filled = [{**defaults, **r} for r in rows]
    cols: dict[str, list] = {}
    for key in SCHEMAS["recipes"].names:
        cols[key] = [r.get(key) for r in filled]
    table = pa.table(cols, schema=SCHEMAS["recipes"])
    pq.write_table(table, tmp_path / "recipes.parquet")


def _write_ingredients_catalogue(tmp_path: Path, rows: list[dict]) -> None:
    defaults: dict = {
        "display_de": "",
        "display_fr": "",
        "display_it": None,
        "display_en": "",
        "category": "misc",
        "sub_category": None,
        "default_unit": "g",
        "density_g_per_ml": None,
        "pairing_tags": [],
        "aliases": [],
    }
    filled = [{**defaults, **r} for r in rows]
    cols: dict[str, list] = {}
    for key in SCHEMAS["ingredients"].names:
        cols[key] = [r.get(key) for r in filled]
    table = pa.table(cols, schema=SCHEMAS["ingredients"])
    pq.write_table(table, tmp_path / "ingredients.parquet")


def _write_recipe_ingredients(tmp_path: Path, rows: list[dict]) -> None:
    defaults: dict = {
        "ingredient_id": None,
        "raw_text": "ingredient",
        "quantity": None,
        "unit": None,
        "prep_note": None,
        "optional": False,
        "group_label": None,
    }
    filled = [{**defaults, **r} for r in rows]
    cols: dict[str, list] = {}
    for key in SCHEMAS["recipe_ingredients"].names:
        cols[key] = [r.get(key) for r in filled]
    table = pa.table(cols, schema=SCHEMAS["recipe_ingredients"])
    pq.write_table(table, tmp_path / "recipe_ingredients.parquet")


def _write_pantry(tmp_path: Path, rows: list[dict]) -> None:
    defaults: dict = {
        "approx_quantity": None,
        "unit": None,
        "location": "fridge",
        "updated_at": datetime.datetime(2024, 6, 1),
        "note": None,
    }
    filled = [{**defaults, **r} for r in rows]
    cols: dict[str, list] = {}
    for key in SCHEMAS["pantry"].names:
        cols[key] = [r.get(key) for r in filled]
    table = pa.table(cols, schema=SCHEMAS["pantry"])
    pq.write_table(table, tmp_path / "pantry.parquet")


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    # Ingredient catalogue
    _write_ingredients_catalogue(
        tmp_path,
        [
            {"id": 1, "key": "chicken-breast"},
            {"id": 2, "key": "cream-double"},
            {"id": 3, "key": "leek"},
            {"id": 4, "key": "rice"},
            {"id": 5, "key": "tomato"},
            {"id": 6, "key": "mozzarella"},
            {"id": 7, "key": "basil"},
        ],
    )

    # Recipes
    _write_recipes(
        tmp_path,
        [
            {"id": 1, "title": "Chicken & Leek"},
            {"id": 2, "title": "Caprese Salad"},
            {"id": 3, "title": "Mystery Dish"},
        ],
    )

    # Recipe ingredients (linked by ingredient_id)
    _write_recipe_ingredients(
        tmp_path,
        [
            {"recipe_id": 1, "seq": 1, "ingredient_id": 1},  # chicken-breast
            {"recipe_id": 1, "seq": 2, "ingredient_id": 2},  # cream-double
            {"recipe_id": 1, "seq": 3, "ingredient_id": 3},  # leek
            {"recipe_id": 2, "seq": 1, "ingredient_id": 5},  # tomato
            {"recipe_id": 2, "seq": 2, "ingredient_id": 6},  # mozzarella
            {"recipe_id": 2, "seq": 3, "ingredient_id": 7},  # basil
            {"recipe_id": 3, "seq": 1, "ingredient_id": 1},  # chicken-breast
            {"recipe_id": 3, "seq": 2, "ingredient_id": 5},  # tomato
        ],
    )

    # Pantry: has chicken-breast and tomato
    _write_pantry(
        tmp_path,
        [
            {"ingredient_id": 1},  # chicken-breast
            {"ingredient_id": 5},  # tomato
        ],
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestForPantry:
    def test_returns_list(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir)
        assert isinstance(results, list)

    def test_full_coverage_ranks_highest(self, data_dir: Path) -> None:
        """Recipe 3 has 2 ingredients both in pantry → full coverage."""
        results = suggest_for_pantry(data_dir, limit=10)
        if results:
            assert results[0]["id"] == 3
            assert results[0]["coverage_score"] == 1.0

    def test_missing_ok_filters(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir, missing_ok=0, limit=10)
        for r in results:
            assert r["missing"] == 0

    def test_extra_ingredients_boost_coverage(self, data_dir: Path) -> None:
        # Without extras, recipe 2 has 1/3 coverage (tomato only)
        base = suggest_for_pantry(data_dir, missing_ok=5, limit=10)
        r2_base = next((r for r in base if r["id"] == 2), None)

        # With mozzarella and basil as extras
        boosted = suggest_for_pantry(
            data_dir, extra_ingredients=["mozzarella", "basil"], missing_ok=5, limit=10
        )
        r2_boosted = next((r for r in boosted if r["id"] == 2), None)

        assert r2_base is not None
        assert r2_boosted is not None
        assert r2_boosted["coverage_score"] > r2_base["coverage_score"]

    def test_respects_limit(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir, limit=1)
        assert len(results) <= 1

    def test_scores_sorted_descending(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir, missing_ok=5, limit=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_keys(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir, missing_ok=5, limit=1)
        if results:
            expected = {
                "id",
                "title",
                "total_minutes",
                "ingredient_count",
                "covered",
                "missing",
                "missing_ingredients",
                "coverage_score",
                "score",
            }
            assert set(results[0].keys()) == expected

    def test_no_pantry_file(self, tmp_path: Path) -> None:
        """Works even when pantry.parquet doesn't exist."""
        _write_recipes(tmp_path, [{"id": 1, "title": "Test"}])
        _write_recipe_ingredients(tmp_path, [{"recipe_id": 1, "seq": 1}])
        _write_ingredients_catalogue(tmp_path, [{"id": 1, "key": "something"}])
        results = suggest_for_pantry(tmp_path, missing_ok=5, limit=10)
        assert isinstance(results, list)

    def test_max_total_minutes(self, data_dir: Path) -> None:
        results = suggest_for_pantry(data_dir, max_total_minutes=10, limit=10)
        # All fixtures have total_minutes=30, so nothing should match
        assert results == []


class TestPantryStaples:
    def test_staples_defined(self) -> None:
        assert "salt" in PANTRY_STAPLES
        assert "pepper" in PANTRY_STAPLES
        assert "olive-oil" in PANTRY_STAPLES
