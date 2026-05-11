# Web Dashboard

Local web UI for observability metrics and MCP tool usage monitoring.

## Prerequisites

```bash
pip install -e "."  # Core dependencies include starlette
```

The MCP server must have been used (to generate tool events for display).

## Running

```bash
# Default: http://127.0.0.1:8777
recipebrain dashboard

# Custom host/port
recipebrain dashboard --host 0.0.0.0 --port 9000
```

## Endpoints

### JSON API

| Endpoint | Description |
|----------|-------------|
| `/api/stats` | Summary statistics (total calls, error count, avg latency) |
| `/api/events?n=50` | Most recent tool events |
| `/api/tools` | Per-tool call counts and average latency |

### HTML Dashboard

| Page | URL | Description |
|------|-----|-------------|
| Overview | `/` | Self-contained HTML page with inline charts |

## Monitoring Features

### Overview (`/`)

- **KPI Cards**: Total calls, error rate %, average latency
- **Recent Events**: Last N tool invocations with timing and status
- **Per-Tool Breakdown**: Call counts and average latency per MCP tool

### In-Memory Collector

The dashboard reads from the `EventCollector` which keeps the last 1000 events in-memory. Events are recorded automatically when any MCP tool is invoked.

No persistent storage is required — the dashboard shows a live snapshot of recent activity.

## Architecture

```
MCP Tool Call → @log_tool_call decorator → EventCollector (deque, 1000 events)
                                                     ↓
                                            Dashboard (Starlette)
                                            GET /api/stats → JSONResponse
                                            GET /api/events → JSONResponse
                                            GET / → HTML dashboard
```

## Next Steps

- [Observability](../operations/observability.md) — EventCollector details
- [MCP Server](mcp-server.md) — Tool invocation source
