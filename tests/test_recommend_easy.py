"""Tests for recipebrain.recommend.easy — weeknight quick-pick suggestions."""

from __future__ import annotations

import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from recipebrain.recommend.easy import suggest_easy
from recipebrain.writer import SCHEMAS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_recipes(tmp_path: Path, rows: list[dict]) -> None:
    """Write recipe rows to a Parquet file, filling defaults for missing cols."""
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


def _write_ingredients(tmp_path: Path, rows: list[dict]) -> None:
    """Write recipe_ingredients rows to a Parquet file."""
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


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Set up a temp dir with recipes + ingredients for easy-recommend tests."""
    _write_recipes(
        tmp_path,
        [
            {"id": 1, "title": "Quick Pasta", "total_minutes": 15, "difficulty": "easy"},
            {"id": 2, "title": "Slow Braise", "total_minutes": 120, "difficulty": "advanced"},
            {"id": 3, "title": "Simple Salad", "total_minutes": 10, "difficulty": "easy"},
            {
                "id": 4,
                "title": "Recent Stir Fry",
                "total_minutes": 20,
                "difficulty": "easy",
                "last_cooked_at": datetime.datetime.now(tz=datetime.UTC),
            },
            {"id": 5, "title": "Medium Soup", "total_minutes": 25, "difficulty": "medium"},
            {"id": 6, "title": "Archived Recipe", "total_minutes": 10, "status": "archived"},
        ],
    )
    # Ingredients: recipe 1 has 3, recipe 3 has 2, recipe 4 has 5, recipe 5 has 7
    ings = []
    for seq in range(1, 4):
        ings.append({"recipe_id": 1, "seq": seq})
    for seq in range(1, 3):
        ings.append({"recipe_id": 3, "seq": seq})
    for seq in range(1, 6):
        ings.append({"recipe_id": 4, "seq": seq})
    for seq in range(1, 8):
        ings.append({"recipe_id": 5, "seq": seq})
    # recipe 2 has 12 ingredients (too many)
    for seq in range(1, 13):
        ings.append({"recipe_id": 2, "seq": seq})
    _write_ingredients(tmp_path, ings)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestEasy:
    def test_returns_list(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir)
        assert isinstance(results, list)

    def test_excludes_slow_recipes(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, max_total_minutes=30)
        ids = {r["id"] for r in results}
        assert 2 not in ids  # 120 min

    def test_excludes_archived(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir)
        ids = {r["id"] for r in results}
        assert 6 not in ids

    def test_excludes_too_many_ingredients(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, max_ingredients=8)
        ids = {r["id"] for r in results}
        assert 2 not in ids  # 12 ingredients

    def test_respects_limit(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, limit=2)
        assert len(results) <= 2

    def test_scores_sorted_descending(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_faster_recipe_scores_higher(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, max_total_minutes=30, limit=10)
        by_id = {r["id"]: r for r in results}
        # Simple Salad (10 min) should score higher than Medium Soup (25 min)
        if 3 in by_id and 5 in by_id:
            assert by_id[3]["score"] >= by_id[5]["score"]

    def test_recently_cooked_penalised(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, limit=10)
        by_id = {r["id"]: r for r in results}
        # Recipe 4 was recently cooked, recipe 1 was not
        if 1 in by_id and 4 in by_id:
            assert by_id[1]["score"] > by_id[4]["score"]

    def test_result_keys(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, limit=1)
        if results:
            expected = {
                "id",
                "title",
                "total_minutes",
                "difficulty",
                "ingredient_count",
                "last_cooked_at",
                "score",
            }
            assert set(results[0].keys()) == expected

    def test_custom_time_limit(self, data_dir: Path) -> None:
        results = suggest_easy(data_dir, max_total_minutes=12, limit=10)
        for r in results:
            assert r["total_minutes"] <= 12

    def test_empty_when_no_match(self, tmp_path: Path) -> None:
        _write_recipes(
            tmp_path,
            [
                {"id": 1, "title": "Slow", "total_minutes": 180, "difficulty": "advanced"},
            ],
        )
        _write_ingredients(tmp_path, [{"recipe_id": 1, "seq": 1}])
        results = suggest_easy(tmp_path, max_total_minutes=10)
        assert results == []
