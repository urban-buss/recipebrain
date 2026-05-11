# CLI Commands

Command-line interface for scraping, querying, validating, and managing recipe data.

## ETL (Scraping)

```bash
# All enabled sources
recipebrain etl

# Specific source with limit
recipebrain etl --source fooby --limit 20
recipebrain etl --source migusto --limit 50

# Custom config
recipebrain -c my-config.toml etl --source swissmilk
```

## Validation

```bash
recipebrain validate
```

Checks table existence, schema conformance, and row integrity.

## Info

```bash
recipebrain info
```

Shows version, environment, data directory contents, recipe counts by source.

## Doctor (Health Checks)

```bash
recipebrain doctor
```

Runs comprehensive checks: data freshness, snapshot health, dossier integrity, config validity.

## Snapshots

```bash
# Create a snapshot
recipebrain snapshot create --label "pre-etl"

# List snapshots
recipebrain snapshot list

# Restore a snapshot
recipebrain snapshot restore 20260511_073123_pre-etl
```

## MCP Server

```bash
recipebrain mcp
```

Starts the MCP server (stdio transport). See [MCP Server](mcp-server.md).

## Cook Logging

```bash
# Log a cook event
recipebrain log 42 --rating 4 --notes "Added extra garlic"

# With servings and scale
recipebrain log 42 --servings 6 --scale-factor 1.5
```

## Dashboard

```bash
# Start on default port 8777
recipebrain dashboard

# Custom host/port
recipebrain dashboard --host 0.0.0.0 --port 9000
```

## Install Skills

```bash
# Install to default location (~/.openclaw/skills/recipebrain/)
recipebrain install-skills

# Custom target
recipebrain install-skills --target /path/to/skills

# Force overwrite
recipebrain install-skills --force
```

## Global Options

| Flag | Effect |
|------|--------|
| `--config CONFIG`, `-c` | Custom TOML config file (default: `recipebrain.toml`) |
| `--version` | Show version and exit |
| `--help`, `-h` | Show help |

## Full Command Summary

| Command | Description |
|---------|-------------|
| `etl` | Run ETL pipeline (scrape + parse + write) |
| `promotions refresh` | Refresh promotion data |
| `ingest <target>` | Ingest a recipe from file or URL |
| `validate` | Check data integrity |
| `mcp` | Start MCP server |
| `reindex` | Rebuild search indexes |
| `doctor` | Run health checks |
| `info` | Show version and data summary |
| `snapshot` | Create/list/restore data snapshots |
| `install-skills` | Install OpenClaw skills |
| `log <recipe_id>` | Log a cook event |
| `dashboard` | Start observability web UI |

## Next Steps

- [ETL](etl.md) — Detailed ETL documentation
- [MCP Server](mcp-server.md) — Connect AI agents
