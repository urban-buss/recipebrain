# Logging

Configure structured logging for Recipebrain.

## Default Behaviour

By default, recipebrain uses Python's standard logging at WARNING level. The MCP server suppresses console output (stdout is reserved for JSON-RPC transport).

## Setup

Logging is initialised via `recipebrain.log.setup_logging()` at CLI startup. It configures:

- Console handler (stderr) with a human-readable format
- Optional file handler for persistent logs

## Log Levels

| Level | Use Case |
|-------|----------|
| DEBUG | Parser decisions, HTTP requests, individual write operations |
| INFO | ETL progress, source summaries, tool invocations |
| WARNING | Slow tool calls, missing optional data, deprecations |
| ERROR | Failed scrapes, query errors, validation failures |

## MCP Server Logging

When running `recipebrain mcp`:
- Console output goes to stderr (stdout is the JSON-RPC transport)
- Tool invocations are tracked by the EventCollector (in-memory)
- Use the dashboard (`recipebrain dashboard`) to view metrics

## Observability Integration

Every MCP tool call is automatically captured by the `EventCollector`:

```python
@dataclass(frozen=True)
class ToolEvent:
    tool: str           # Tool name
    started_at: datetime
    duration_ms: float
    success: bool
    error: str | None
```

The last 1000 events are kept in-memory and accessible via the dashboard API.

## Next Steps

- [Observability](observability.md) — EventCollector and dashboard metrics
- [Dashboard](../modules/dashboard.md) — Web UI for observability
