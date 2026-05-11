# MCP Server

The MCP (Model Context Protocol) server exposes the recipe knowledge base to AI agents.

## Prerequisites

- ETL must have been run at least once (Parquet data in `output/`)

## Transports

### stdio (default)

```bash
recipebrain mcp
```

Default transport for Claude Desktop and VS Code Copilot. Communicates over stdin/stdout via JSON-RPC. No visible output — use Ctrl+C to stop.

## Client Configuration

### VS Code (Copilot)

The workspace includes `.vscode/mcp.json`:

```json
{
  "servers": {
    "recipebrain": {
      "command": "${command:python.interpreterPath}",
      "args": ["-m", "recipebrain", "mcp"],
      "env": {}
    }
  }
}
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "recipebrain": {
      "command": "/path/to/recipebrain/.venv/bin/recipebrain",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

### OpenClaw (or other MCP clients)

```json
{
  "mcpServers": {
    "recipebrain": {
      "command": "/path/to/recipebrain/.venv/bin/recipebrain",
      "args": ["-c", "/path/to/recipebrain/recipebrain.toml", "mcp"],
      "env": {}
    }
  }
}
```

## Available Tools

### Search & Discovery

| Tool | Parameters | Description |
|------|-----------|-------------|
| `find_recipe` | `query?, language?, max_total_minutes?, difficulty?, course?, starred_only?, tags?, limit?` | Search recipes by text, filters, or tags |
| `read_recipe` | `recipe_id` | Full recipe details with ingredients, steps, cook history |
| `query_recipes` | `sql, limit?` | Read-only DuckDB SQL against recipe tables |
| `list_starred` | `limit?` | List all starred/favourite recipes |

### Recommendations

| Tool | Parameters | Description |
|------|-----------|-------------|
| `suggest_for_pantry` | `extra_ingredients?, missing_ok?, max_total_minutes?, limit?` | Recipes matching current pantry |
| `suggest_rotation` | `min_rating?, not_cooked_in_days?, limit?` | High-rated recipes not cooked recently |
| `suggest_easy` | `max_total_minutes?, max_ingredients?, avoid_recent_days?, limit?` | Quick weeknight recipes |

### Cook Logging & Planning

| Tool | Parameters | Description |
|------|-----------|-------------|
| `log_cook` | `recipe_id, cooked_on?, servings?, scale_factor?, rating?, notes?` | Record a cook event |
| `cook_history` | `recipe_id?, limit?` | View recent cook events |
| `pin_recipe` | `recipe_id, target_date?, note?` | Pin to cook-next board |
| `list_pinned` | `include_done?` | Show pinned recipes |
| `unpin_recipe` | `recipe_id` | Dismiss a pinned recipe |

### Recipe Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `star_recipe` | `recipe_id, starred?` | Star/unstar a recipe |
| `rate_recipe` | `recipe_id, rating?` | Set owner rating (1–5) |
| `add_recipe` | `title, ingredients, steps, servings?, ...` | Add a user-created recipe |
| `annotate_recipe` | `recipe_id, section, content` | Write to dossier section |
| `tag_recipe` | `recipe_id, tags` | Add tags to a recipe |
| `batch_annotate` | `recipe_ids, section, content` | Annotate multiple recipes |
| `batch_tag` | `recipe_ids, tags` | Tag multiple recipes |

### Pantry & Promotions

| Tool | Parameters | Description |
|------|-----------|-------------|
| `update_pantry` | `additions?, removals?, location?, note?` | Add/remove pantry items |
| `current_promotions` | `retailer?, ingredient?, min_discount_pct?, limit?` | Browse current promotions |

### Data Refresh

| Tool | Parameters | Description |
|------|-----------|-------------|
| `refresh_source` | `source?, limit?` | Trigger ETL from within an agent session |
| `refresh_status` | `job_id?` | Check background refresh job status |

## MCP Resources

| URI | Description |
|-----|-------------|
| `recipe://list` | All active recipes with basic metadata (JSON) |
| `recipe://stats` | Collection statistics (total, active, starred, avg time) |
| `recipe://starred` | Starred recipes (JSON) |
| `recipe://pinned` | Currently pinned recipes (JSON) |

## MCP Prompts

| Prompt | Description |
|--------|-------------|
| `recipe_qa` | System prompt for recipe Q&A with embedded collection stats |
| `meal_plan` | System prompt for weekly meal planning with pantry + pinned context |

## Debugging

### Verify Data Exists

```bash
dir output\*.parquet        # Windows
ls output/*.parquet         # macOS/Linux
recipebrain validate
recipebrain info
```

### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector recipebrain mcp
```

Opens a browser UI to browse tools, call them interactively, and inspect responses.

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Tools return "Error: No parquet files" | ETL not run | Run `recipebrain etl --limit 5` first |
| MCP not available in Copilot | Server not configured | Check `.vscode/mcp.json` exists |
| Timeout on large queries | Too many rows | Use `limit` parameter or narrow filters |

## Next Steps

- [ETL](etl.md) — Populate data before using MCP
- [Agent Skills](agent-skills.md) — OpenClaw skill workflows
- [MCP Testing](../operations/mcp-testing.md) — Verification steps
