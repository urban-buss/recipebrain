# Quick Start

Get from zero to a working recipe collection in 5 minutes.

## Prerequisites

- Python 3.11+ installed ([details](prerequisites.md))
- Internet access (for scraping recipe sources)

## Steps

```bash
# 1. Clone and enter
git clone https://github.com/urban-buss/recipebrain.git
cd recipebrain

# 2. Create venv and install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Run ETL (scrape a few recipes to start)
recipebrain etl --source fooby --limit 10

# 4. Verify
recipebrain validate && recipebrain info

# 5. Start MCP server (for AI agent use)
recipebrain mcp
```

## Verify

After step 4 you should see output like:

```
All checks passed (N checks).
```

And `recipebrain info` shows a summary of scraped recipes, ingredients, and sources.

## What Just Happened?

1. **ETL** discovered recipe URLs on fooby.ch, fetched pages, extracted JSON-LD, parsed ingredients, and wrote normalised Parquet tables to `output/`.
2. **Validate** checked primary key uniqueness, foreign key integrity, and schema conformance.
3. **Info** summarised the data layer: recipe counts, source breakdown, table sizes.

## Next Steps

- [Installation options](installation.md) — PyPI or source
- [ETL module](../modules/etl.md) — Source options, full scrape, limits
- [MCP server](../modules/mcp-server.md) — Connect AI agents
- [Configuration](../configuration/overview.md) — TOML settings
