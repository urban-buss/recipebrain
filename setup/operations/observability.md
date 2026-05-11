# Observability

The EventCollector captures every MCP tool invocation in-memory for monitoring and debugging.

## Architecture

```
MCP Tool Call → @log_tool_call decorator → EventCollector (deque, max 1000 events)
                                                     ↓
                                          Dashboard API (/api/stats, /api/events, /api/tools)
```

## ToolEvent Record

| Field | Type | Description |
|-------|------|-------------|
| `tool` | str | Tool name (e.g. `find_recipe`, `log_cook`) |
| `started_at` | datetime | Invocation start time |
| `duration_ms` | float | Execution time in milliseconds |
| `success` | bool | Whether the call succeeded |
| `error` | str \| None | Error message (on failure) |

## EventCollector API

```python
from recipebrain.observability import collector

# Summary statistics
collector.stats()
# {"total_calls": 42, "errors": 2, "avg_duration_ms": 28.5}

# Recent events (newest first)
events = collector.recent(50)

# Access individual events
for e in events:
    print(f"{e.tool}: {e.duration_ms:.1f}ms {'✓' if e.success else '✗'}")
```

## Dashboard Integration

The observability dashboard reads directly from the collector:

```bash
recipebrain dashboard
# Open http://127.0.0.1:8777
```

See [Dashboard](../modules/dashboard.md) for endpoints and UI details.

## Metrics Available

| Metric | Source |
|--------|--------|
| Total calls | `collector.stats()["total_calls"]` |
| Error count | `collector.stats()["errors"]` |
| Average latency | `collector.stats()["avg_duration_ms"]` |
| Per-tool breakdown | Dashboard `/api/tools` endpoint |
| Recent events | Dashboard `/api/events?n=50` endpoint |

## Limitations

- **In-memory only** — events are lost when the process restarts
- **Max 1000 events** — older events are evicted (FIFO)
- **Single-process** — no cross-process aggregation

For persistent analytics, export events from the dashboard API to an external store.

## Next Steps

- [Dashboard](../modules/dashboard.md) — Web UI for observability
- [Health Monitoring](health-monitoring.md) — Doctor checks
- [Logging](logging.md) — Structured logging
