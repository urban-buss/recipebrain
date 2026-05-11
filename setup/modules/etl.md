# ETL Pipeline

Scrape Swiss recipe websites, parse structured data, and write normalised Parquet tables.

## Prerequisites

- Recipebrain installed ([Installation](../getting-started/installation.md))
- Internet access (scrapes live recipe sites)
- Configuration: `recipebrain.toml` with desired sources enabled

## Available Sources

| Source | Website | Language | Default |
|--------|---------|----------|---------|
| `fooby` | fooby.ch | de | enabled |
| `migusto` | migusto.migros.ch | de | enabled |
| `swissmilk` | swissmilk.ch | de | disabled |
| `schweizerfleisch` | schweizerfleisch.ch | de | disabled |

## Running ETL

### First Run (small batch)

```bash
recipebrain etl --source fooby --limit 10
```

### All Enabled Sources

```bash
recipebrain etl
```

### Specific Source, Unlimited

```bash
recipebrain etl --source migusto
```

### With Limit

```bash
recipebrain etl --limit 50
```

**What it creates:**

| Output | Location | Description |
|--------|----------|-------------|
| Parquet tables | `output/*.parquet` | recipes, recipe_ingredients, recipe_steps, sources, ingredients, tags, recipe_tags, cook_log, pinned_recipes, pantry, promotions, retailers |
| Recipe dossiers | `dossiers/recipes/*.md` | Per-recipe Markdown files (agent-editable sections) |

## How It Works

1. **Discover** — Source adapter enumerates recipe URLs (sitemap or listing pages)
2. **Skip** — URLs already present in the recipes table are skipped (append-only)
3. **Fetch** — Download recipe pages (rate-limited per `[scraping]` config)
4. **Parse** — Extract JSON-LD via `extruct`; fall back to HTML scraping
5. **Transform** — Normalise into entity rows (recipes, ingredients, steps)
6. **Write** — Append new rows to Parquet files

> **Note:** ETL is append-only. Existing recipes are never modified or deleted by subsequent runs.

## Validating Output

```bash
recipebrain validate
```

Checks: table existence, row counts, schema conformance.

## Snapshot Before ETL

Create a backup before large scrapes:

```bash
recipebrain snapshot create --label "pre-etl"
```

Restore if needed:

```bash
recipebrain snapshot list
recipebrain snapshot restore <snapshot-name>
```

## Debugging

### Verbose CLI

The ETL command prints a summary after each source:

```
  fooby: discovered=150 fetched=10 skipped=140 errors=0
```

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `httpx.TimeoutException` | Network timeout | Check connection; increase `[scraping] timeout_seconds` |
| `No sources processed` | All sources disabled | Enable sources in `recipebrain.toml` |
| `Rate limit` | Too-fast scraping | Default 2s delay is safe; don't lower it |
| JSON-LD extraction fails | Site structure changed | Check for adapter updates; file an issue |

### Inspect Parquet Directly

```bash
python3 -c "
import pyarrow.parquet as pq
table = pq.read_table('output/recipes.parquet')
print(f'Schema: {table.schema}')
print(f'Rows: {table.num_rows}')
print(table.to_pandas().head())
"
```

## MCP Refresh

The MCP server also exposes `refresh_source` for on-demand scraping by AI agents. See [MCP Server](mcp-server.md).

## Next Steps

- [CLI](cli.md) — Query data via the command line
- [Configuration](../configuration/overview.md) — TOML settings for ETL behaviour
- [MCP Server](mcp-server.md) — Expose data to AI agents
