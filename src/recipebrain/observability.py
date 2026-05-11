"""Observability layer for MCP tool instrumentation.

Provides a decorator that logs tool call timing and errors, and an in-memory
event collector for optional persistence to Parquet.
"""

from __future__ import annotations

import functools
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

__all__ = ["EventCollector", "ToolEvent", "collector", "log_tool_call"]

logger = logging.getLogger(__name__)

_MAX_EVENTS = 1000


@dataclass(frozen=True)
class ToolEvent:
    """A single MCP tool invocation record."""

    tool: str
    started_at: datetime
    duration_ms: float
    success: bool
    error: str | None = None


class EventCollector:
    """Thread-safe ring buffer of recent tool events."""

    def __init__(self, maxlen: int = _MAX_EVENTS) -> None:
        self._events: deque[ToolEvent] = deque(maxlen=maxlen)
        self._lock = Lock()

    def record(self, event: ToolEvent) -> None:
        with self._lock:
            self._events.append(event)

    def recent(self, n: int = 20) -> list[ToolEvent]:
        with self._lock:
            items = list(self._events)
        return items[-n:]

    def stats(self) -> dict[str, object]:
        """Return summary statistics across all recorded events."""
        with self._lock:
            items = list(self._events)
        if not items:
            return {"total": 0, "success": 0, "error": 0}
        successes = sum(1 for e in items if e.success)
        durations = [e.duration_ms for e in items]
        return {
            "total": len(items),
            "success": successes,
            "error": len(items) - successes,
            "avg_ms": round(sum(durations) / len(durations), 1),
            "max_ms": round(max(durations), 1),
        }


# Module-level singleton
collector = EventCollector()


def log_tool_call(fn):
    """Decorator that records timing and errors for MCP tool functions."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        tool_name = fn.__name__
        started = datetime.now(tz=UTC)
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            duration = (time.perf_counter() - t0) * 1000
            collector.record(
                ToolEvent(
                    tool=tool_name,
                    started_at=started,
                    duration_ms=duration,
                    success=True,
                )
            )
            logger.debug("tool=%s duration=%.1fms ok", tool_name, duration)
            return result
        except Exception as exc:
            duration = (time.perf_counter() - t0) * 1000
            collector.record(
                ToolEvent(
                    tool=tool_name,
                    started_at=started,
                    duration_ms=duration,
                    success=False,
                    error=str(exc),
                )
            )
            logger.warning("tool=%s duration=%.1fms error=%s", tool_name, duration, exc)
            raise

    return wrapper
