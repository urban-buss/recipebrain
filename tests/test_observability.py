"""Tests for recipebrain.observability — tool instrumentation."""

from __future__ import annotations

from datetime import UTC, datetime

from recipebrain.observability import EventCollector, ToolEvent, log_tool_call


class TestToolEvent:
    def test_creation(self):
        ev = ToolEvent(
            tool="find_recipe",
            started_at=datetime.now(tz=UTC),
            duration_ms=42.5,
            success=True,
        )
        assert ev.tool == "find_recipe"
        assert ev.error is None


class TestEventCollector:
    def test_record_and_recent(self):
        c = EventCollector(maxlen=10)
        ev = ToolEvent(tool="t", started_at=datetime.now(tz=UTC), duration_ms=1.0, success=True)
        c.record(ev)
        assert len(c.recent()) == 1
        assert c.recent()[0].tool == "t"

    def test_maxlen_enforced(self):
        c = EventCollector(maxlen=3)
        for i in range(5):
            c.record(
                ToolEvent(
                    tool=f"t{i}",
                    started_at=datetime.now(tz=UTC),
                    duration_ms=1.0,
                    success=True,
                )
            )
        assert len(c.recent(10)) == 3
        assert c.recent(10)[0].tool == "t2"

    def test_stats_empty(self):
        c = EventCollector()
        s = c.stats()
        assert s["total"] == 0

    def test_stats_populated(self):
        c = EventCollector()
        c.record(
            ToolEvent(
                tool="a",
                started_at=datetime.now(tz=UTC),
                duration_ms=10.0,
                success=True,
            )
        )
        c.record(
            ToolEvent(
                tool="b",
                started_at=datetime.now(tz=UTC),
                duration_ms=20.0,
                success=False,
                error="boom",
            )
        )
        s = c.stats()
        assert s["total"] == 2
        assert s["success"] == 1
        assert s["error"] == 1
        assert s["avg_ms"] == 15.0
        assert s["max_ms"] == 20.0


class TestLogToolCall:
    def test_decorates_successful_call(self):
        c = EventCollector()
        # Monkey-patch the module-level collector for this test
        import recipebrain.observability as obs

        original = obs.collector
        obs.collector = c

        @log_tool_call
        def my_tool(x: int) -> int:
            return x * 2

        result = my_tool(5)
        assert result == 10
        assert len(c.recent()) == 1
        assert c.recent()[0].success is True
        obs.collector = original

    def test_decorates_failing_call(self):
        c = EventCollector()
        import recipebrain.observability as obs

        original = obs.collector
        obs.collector = c

        @log_tool_call
        def bad_tool():
            raise ValueError("nope")

        import pytest

        with pytest.raises(ValueError, match="nope"):
            bad_tool()

        assert len(c.recent()) == 1
        assert c.recent()[0].success is False
        assert c.recent()[0].error == "nope"
        obs.collector = original
