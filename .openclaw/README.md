# Recipebrain — OpenClaw Skills

AI meal-planning skills for a Swiss household via the recipebrain MCP server. Each skill is self-contained, short (<80 lines), designed for small/local LLMs.

## Installation & Onboarding

### Step 1 — Install recipebrain

```bash
pip install recipebrain
```

### Step 2 — Run ETL once

```bash
recipebrain etl
```

> **Note:** Real ETL is not yet implemented in v0.0.1. This step will work once source adapters are built.

### Step 3 — Install skills into your OpenClaw directory

```bash
recipebrain install-skills
```

This copies bundled skill files to `~/.openclaw/skills/recipebrain/`. To install to a custom location:

```bash
recipebrain install-skills -t /path/to/skills/dir
```

Use `--force` to overwrite existing files when upgrading.

### Step 4 — Configure the MCP server

Add to your OpenClaw config (`~/.openclaw/openclaw.json` or equivalent):

```json
{
  "mcpServers": {
    "recipebrain": {
      "command": "recipebrain",
      "args": ["-d", "/path/to/output", "mcp"],
      "env": {}
    }
  }
}
```

Replace `/path/to/output` with your ETL output directory.

### Step 5 — Verify

OpenClaw should now discover all 8 skills. Test with:
- "What can I cook tonight?" → triggers `tonight` skill
- "What goes with this Barbera?" → triggers `wine-pairing` skill

## Skills

| Skill | User Intent | Description |
|-------|-------------|-------------|
| [tonight](./tonight/) | "What should I cook tonight?" | Meal suggestion engine (pantry + promos + rotation) |
| [pantry](./pantry/) | "Use what's in the fridge" | Pantry-driven recipe suggestions |
| [wine-pairing](./wine-pairing/) | "What goes with this wine?" | Recipe↔wine pairing (bridges cellarbrain) |
| [rotation](./rotation/) | "Surprise me with something I forgot" | Rediscover recipes not cooked recently |
| [shopping](./shopping/) | "Plan & shop with this week's promos" | Promotion-aware shopping list |
| [recipe-info](./recipe-info/) | "Tell me about recipe #N" | Recipe lookup and detail display |
| [add-recipe](./add-recipe/) | "Save this recipe" | Create a new recipe from title, ingredients, and steps |
| [manage](./manage/) | "Run ETL / refresh / health check" | System maintenance and data refresh |

## Companion: cellarbrain

The `wine-pairing` skill calls into cellarbrain's MCP server via the host. Both servers should be configured in the same OpenClaw instance for full meal-planning + wine-pairing functionality.

```json
{
  "mcpServers": {
    "recipebrain": { "command": "recipebrain", "args": ["mcp"] },
    "cellarbrain": { "command": "cellarbrain", "args": ["-d", "output", "mcp"] }
  }
}
```

## Updating

```bash
pip install --upgrade recipebrain && recipebrain install-skills --force
```

Skills are backward-compatible — new versions may use new MCP tools but never remove existing ones.
