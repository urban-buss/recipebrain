"""Tests for the observability dashboard."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from recipebrain.dashboard import app
from recipebrain.observability import ToolEvent, collector


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_collector():
    """Reset the collector before each test."""
    collector._events.clear()
    yield
    collector._events.clear()


def _record_events() -> None:
    """Populate the collector with sample events."""
    collector.record(
        ToolEvent(
            tool="find_recipe",
            started_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            duration_ms=15.5,
            success=True,
        )
    )
    collector.record(
        ToolEvent(
            tool="find_recipe",
            started_at=datetime(2025, 1, 1, 12, 1, 0, tzinfo=UTC),
            duration_ms=22.3,
            success=True,
        )
    )
    collector.record(
        ToolEvent(
            tool="log_cook",
            started_at=datetime(2025, 1, 1, 12, 2, 0, tzinfo=UTC),
            duration_ms=50.0,
            success=False,
            error="Recipe not found",
        )
    )


class TestDashboardPage:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "recipebrain" in resp.text

    def test_contains_chart_elements(self, client):
        resp = client.get("/")
        assert "api/stats" in resp.text
        assert "api/events" in resp.text
        assert "api/tools" in resp.text


class TestApiStats:
    def test_empty_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_stats_with_events(self, client):
        _record_events()
        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total"] == 3
        assert data["success"] == 2
        assert data["error"] == 1
        assert "avg_ms" in data
        assert "max_ms" in data


class TestApiEvents:
    def test_empty_events(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_events(self, client):
        _record_events()
        resp = client.get("/api/events?n=10")
        data = resp.json()
        assert len(data) == 3
        assert data[0]["tool"] == "find_recipe"
        assert data[2]["error"] == "Recipe not found"
        assert data[0]["success"] is True

    def test_respects_n_param(self, client):
        _record_events()
        resp = client.get("/api/events?n=1")
        data = resp.json()
        assert len(data) == 1


class TestApiTools:
    def test_empty_tools(self, client):
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_per_tool_breakdown(self, client):
        _record_events()
        resp = client.get("/api/tools")
        data = resp.json()
        assert len(data) == 2

        find = next(t for t in data if t["tool"] == "find_recipe")
        assert find["calls"] == 2
        assert find["errors"] == 0
        assert find["avg_ms"] > 0

        log = next(t for t in data if t["tool"] == "log_cook")
        assert log["calls"] == 1
        assert log["errors"] == 1
