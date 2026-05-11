"""Observability dashboard — Starlette app serving tool usage, errors, and latency.

Provides a lightweight web UI backed by the in-memory ``EventCollector``.
Endpoints serve JSON data and a self-contained HTML page with inline charts.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from recipebrain.observability import collector

# ---------------------------------------------------------------------------
# JSON API endpoints
# ---------------------------------------------------------------------------


async def api_stats(request: Request) -> JSONResponse:
    """Return summary statistics across all tool events."""
    return JSONResponse(collector.stats())


async def api_events(request: Request) -> JSONResponse:
    """Return the most recent tool events."""
    n = int(request.query_params.get("n", "50"))
    events = collector.recent(n)
    return JSONResponse(
        [
            {
                "tool": e.tool,
                "started_at": e.started_at.isoformat(),
                "duration_ms": round(e.duration_ms, 1),
                "success": e.success,
                "error": e.error,
            }
            for e in events
        ]
    )


async def api_tools(request: Request) -> JSONResponse:
    """Return per-tool breakdown of call counts and average latency."""
    events = collector.recent(1000)
    tools: dict[str, dict] = {}
    for e in events:
        t = tools.setdefault(e.tool, {"calls": 0, "errors": 0, "total_ms": 0.0})
        t["calls"] += 1
        if not e.success:
            t["errors"] += 1
        t["total_ms"] += e.duration_ms

    result = []
    for name, data in sorted(tools.items()):
        avg = data["total_ms"] / data["calls"] if data["calls"] else 0
        result.append(
            {
                "tool": name,
                "calls": data["calls"],
                "errors": data["errors"],
                "avg_ms": round(avg, 1),
            }
        )
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# HTML dashboard page
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>recipebrain — observability</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 1rem; }
  h1 { font-size: 1.4rem; margin-bottom: 1rem; color: #58a6ff; }
  h2 { font-size: 1.1rem; margin: 1rem 0 .5rem; color: #8b949e; }
  .cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
          padding: 1rem; min-width: 140px; }
  .card .label { font-size: .75rem; color: #8b949e; text-transform: uppercase; }
  .card .value { font-size: 1.8rem; font-weight: 600; margin-top: .25rem; }
  .card .value.ok { color: #3fb950; }
  .card .value.err { color: #f85149; }
  .card .value.neutral { color: #58a6ff; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 1rem; }
  th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-size: .75rem; text-transform: uppercase; }
  td { font-size: .85rem; }
  .bar-container { width: 100%; background: #21262d; border-radius: 3px; height: 18px; }
  .bar { background: #58a6ff; height: 100%; border-radius: 3px;
         font-size: .7rem; line-height: 18px; padding-left: 4px; color: #fff;
         white-space: nowrap; overflow: hidden; }
  .err-bar { background: #f85149; }
  .events td.ok { color: #3fb950; }
  .events td.err { color: #f85149; }
  .refresh { font-size: .75rem; color: #8b949e; cursor: pointer; margin-left: .5rem; }
  .refresh:hover { color: #58a6ff; }
  #auto-refresh { margin-left: .5rem; }
</style>
</head>
<body>
<h1>recipebrain observability
  <span class="refresh" onclick="loadAll()">↻ refresh</span>
  <label id="auto-refresh"><input type="checkbox" id="auto-cb" checked> auto (5s)</label>
</h1>

<div class="cards" id="cards"></div>

<h2>Per-tool breakdown</h2>
<table id="tools-table">
  <thead><tr><th>Tool</th><th>Calls</th><th>Errors</th><th>Avg ms</th><th>Latency</th></tr></thead>
  <tbody></tbody>
</table>

<h2>Recent events</h2>
<table class="events" id="events-table">
  <thead><tr><th>Time</th><th>Tool</th><th>Duration</th><th>Status</th><th>Error</th></tr></thead>
  <tbody></tbody>
</table>

<script>
async function loadAll() {
  const [stats, tools, events] = await Promise.all([
    fetch('/api/stats').then(r => r.json()),
    fetch('/api/tools').then(r => r.json()),
    fetch('/api/events?n=50').then(r => r.json()),
  ]);
  renderCards(stats);
  renderTools(tools, stats);
  renderEvents(events);
}

function renderCards(s) {
  const c = document.getElementById('cards');
  const card = (l, v, cls) =>
    `<div class="card"><div class="label">${l}</div>` +
    `<div class="value ${cls}">${v}</div></div>`;
  c.innerHTML = [
    card('Total calls', s.total, 'neutral'),
    card('Successes', s.success, 'ok'),
    card('Errors', s.error, 'err'),
    card('Avg latency', (s.avg_ms ?? '—') + 'ms', 'neutral'),
    card('Max latency', (s.max_ms ?? '—') + 'ms', 'neutral'),
  ].join('');
}

function renderTools(tools, stats) {
  const tbody = document.querySelector('#tools-table tbody');
  const maxCalls = Math.max(1, ...tools.map(t => t.calls));
  tbody.innerHTML = tools.map(t => {
    const w = Math.round(t.calls / maxCalls * 100);
    const errW = t.errors ? Math.round(t.errors / maxCalls * 100) : 0;
    return `<tr>
      <td>${t.tool}</td><td>${t.calls}</td><td>${t.errors}</td><td>${t.avg_ms}</td>
      <td><div class="bar-container">
        <div class="bar" style="width:${w}%">${t.calls}</div>
      </div></td></tr>`;
  }).join('');
}

function renderEvents(events) {
  const tbody = document.querySelector('#events-table tbody');
  tbody.innerHTML = events.slice().reverse().map(e => {
    const t = new Date(e.started_at).toLocaleTimeString();
    const cls = e.success ? 'ok' : 'err';
    return `<tr>
      <td>${t}</td><td>${e.tool}</td><td>${e.duration_ms}ms</td>
      <td class="${cls}">${e.success ? '✓' : '✗'}</td>
      <td>${e.error || ''}</td></tr>`;
  }).join('');
}

loadAll();
let timer = setInterval(loadAll, 5000);
document.getElementById('auto-cb').addEventListener('change', e => {
  if (e.target.checked) { timer = setInterval(loadAll, 5000); }
  else { clearInterval(timer); }
});
</script>
</body>
</html>
"""


async def dashboard_page(request: Request) -> HTMLResponse:
    """Serve the self-contained HTML dashboard."""
    return HTMLResponse(_DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# Starlette app
# ---------------------------------------------------------------------------

routes = [
    Route("/", dashboard_page),
    Route("/api/stats", api_stats),
    Route("/api/events", api_events),
    Route("/api/tools", api_tools),
]

app = Starlette(routes=routes)


def run_dashboard(host: str = "127.0.0.1", port: int = 8777) -> None:
    """Start the dashboard server with uvicorn."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
