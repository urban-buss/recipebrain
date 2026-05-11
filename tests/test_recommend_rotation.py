"""Tests for recipebrain.recommend.rotation — rotation suggestions."""

from __future__ import annotations

import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from recipebrain.recommend.rotation import suggest_rotation
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


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    long_ago = datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC)
    recent = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=3)
    _write_recipes(
        tmp_path,
        [
            {
                "id": 1,
                "title": "Loved Old Classic",
                "owner_rating": 5,
                "times_cooked": 10,
                "last_cooked_at": long_ago,
            },
            {
                "id": 2,
                "title": "Recent Favourite",
                "owner_rating": 5,
                "times_cooked": 2,
                "last_cooked_at": recent,
            },
            {
                "id": 3,
                "title": "Never Cooked Gem",
                "owner_rating": 4,
                "times_cooked": 0,
                "last_cooked_at": None,
            },
            {
                "id": 4,
                "title": "Low Rated",
                "owner_rating": 2,
                "times_cooked": 1,
                "last_cooked_at": long_ago,
            },
            {
                "id": 5,
                "title": "Archived Good",
                "owner_rating": 5,
                "status": "archived",
            },
        ],
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestRotation:
    def test_returns_list(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir)
        assert isinstance(results, list)

    def test_excludes_low_rated(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir, min_rating=4)
        ids = {r["id"] for r in results}
        assert 4 not in ids  # rating 2

    def test_excludes_archived(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir)
        ids = {r["id"] for r in results}
        assert 5 not in ids

    def test_old_recipe_ranks_higher_than_recent(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir, min_rating=5, limit=10)
        by_id = {r["id"]: r for r in results}
        # Recipe 1 (cooked long ago) should score higher than recipe 2 (cooked recently)
        if 1 in by_id and 2 in by_id:
            assert by_id[1]["score"] > by_id[2]["score"]

    def test_never_cooked_gets_bonus(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir, min_rating=4, limit=10)
        by_id = {r["id"]: r for r in results}
        # Recipe 3 never cooked should have high freshness
        if 3 in by_id:
            assert by_id[3]["days_since_cooked"] is None
            assert by_id[3]["score"] > 0

    def test_respects_limit(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir, limit=1)
        assert len(results) <= 1

    def test_scores_sorted_descending(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_keys(self, data_dir: Path) -> None:
        results = suggest_rotation(data_dir, limit=1)
        if results:
            expected = {
                "id",
                "title",
                "owner_rating",
                "times_cooked",
                "last_cooked_at",
                "days_since_cooked",
                "score",
            }
            assert set(results[0].keys()) == expected

    def test_empty_when_no_rated(self, tmp_path: Path) -> None:
        _write_recipes(
            tmp_path,
            [
                {"id": 1, "title": "Unrated", "owner_rating": None},
            ],
        )
        results = suggest_rotation(tmp_path, min_rating=4)
        assert results == []
