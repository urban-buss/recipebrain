---
name: manage
description: "Run ETL, refresh promotions, validate data, check system health."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# System Management

Maintain the recipebrain installation: ETL runs, promotion refresh, validation, health checks.

## Owner Context

Switzerland, CHF. Operations skill — no recipe presentation needed.

## Workflow: Run ETL

Hand off to CLI:
```
recipebrain etl [--source fooby|migusto|...]
```

Or via MCP: `refresh_source(source)` for async refresh, then `refresh_status(job_id)` to poll.

After ETL: `server_stats()` to verify freshness and record counts.

## Workflow: Refresh Promotions

Hand off to CLI:
```
recipebrain promotions refresh
```

After refresh: `current_promotions(limit=5)` to spot-check.

## Workflow: Validate Data

Hand off to CLI:
```
recipebrain validate
```

Reports schema conformance, orphaned records, missing FK references.

## Workflow: Health Check

1. `server_stats()` — version, ETL freshness, table row counts
2. Check for: stale data (>7 days), empty tables, pending migrations

## Workflow: Quick Cook Log

CLI shortcut (no MCP server required):
```
recipebrain log <recipe_id> [--rating N] [--notes "..."] [--servings N] [--scale-factor F]
```

## Tools

| Tool | Purpose |
|------|---------|
| `server_stats` | Version, freshness, diagnostics |
| `current_promotions` | Spot-check after refresh |
| `refresh_source` | Trigger async ETL for a source |
| `refresh_status` | Check status of a refresh job |
