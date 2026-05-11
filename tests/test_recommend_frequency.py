"""Tests for cooking frequency and churn analysis."""

from __future__ import annotations

import datetime

from recipebrain.recommend.frequency import (
    CookingTrend,
    format_trends,
    monthly_trends,
    top_recipes,
    weekly_trends,
)
from recipebrain.writer import write_table


def _seed_cook_log(tmp_path, entries: list[dict] | None = None) -> None:
    """Write cook_log and minimal recipes for testing."""
    today = datetime.date.today()
    if entries is None:
        entries = [
            {"id": 1, "recipe_id": 1, "cooked_on": today - datetime.timedelta(days=1)},
            {"id": 2, "recipe_id": 2, "cooked_on": today - datetime.timedelta(days=2)},
            {"id": 3, "recipe_id": 1, "cooked_on": today - datetime.timedelta(days=8)},
            {"id": 4, "recipe_id": 3, "cooked_on": today - datetime.timedelta(days=35)},
            {"id": 5, "recipe_id": 1, "cooked_on": today - datetime.timedelta(days=60)},
        ]
    write_table("cook_log", entries, tmp_path)
    write_table(
        "recipes",
        [
            {"id": 1, "title": "Pasta"},
            {"id": 2, "title": "Salad"},
            {"id": 3, "title": "Soup"},
        ],
        tmp_path,
    )


class TestWeeklyTrends:
    def test_returns_trends(self, tmp_path):
        _seed_cook_log(tmp_path)
        trends = weekly_trends(tmp_path, weeks=12)
        assert len(trends) > 0
        assert all(isinstance(t, CookingTrend) for t in trends)

    def test_empty_cook_log(self, tmp_path):
        write_table("cook_log", [], tmp_path)
        trends = weekly_trends(tmp_path, weeks=4)
        assert trends == []

    def test_cook_count_sums_correctly(self, tmp_path):
        _seed_cook_log(tmp_path)
        trends = weekly_trends(tmp_path, weeks=12)
        total = sum(t.cook_count for t in trends)
        assert total >= 4  # at least the recent entries


class TestMonthlyTrends:
    def test_returns_trends(self, tmp_path):
        _seed_cook_log(tmp_path)
        trends = monthly_trends(tmp_path, months=6)
        assert len(trends) > 0

    def test_empty_cook_log(self, tmp_path):
        write_table("cook_log", [], tmp_path)
        trends = monthly_trends(tmp_path, months=6)
        assert trends == []


class TestTopRecipes:
    def test_returns_ranked_list(self, tmp_path):
        _seed_cook_log(tmp_path)
        top = top_recipes(tmp_path, limit=5)
        assert len(top) >= 1
        # Most cooked recipe should be first
        assert top[0]["cook_count"] >= top[-1]["cook_count"]

    def test_includes_title(self, tmp_path):
        _seed_cook_log(tmp_path)
        top = top_recipes(tmp_path, limit=5)
        assert top[0]["title"] is not None

    def test_empty_cook_log(self, tmp_path):
        write_table("cook_log", [], tmp_path)
        write_table("recipes", [], tmp_path)
        top = top_recipes(tmp_path, limit=5)
        assert top == []


class TestFormatTrends:
    def test_format_with_data(self):
        trends = [
            CookingTrend(period="2025-W01", cook_count=3, unique_recipes=2),
            CookingTrend(period="2025-W02", cook_count=5, unique_recipes=4),
        ]
        output = format_trends(trends, label="Week")
        assert "Week" in output
        assert "2025-W01" in output
        assert "| 3 |" in output

    def test_format_empty(self):
        assert format_trends([]) == "No cooking data found."
