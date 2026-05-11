# Agent Skills

Architecture and available skills for AI agents connecting via MCP.

## Architecture: MCP = Data, Agent = Reasoning

The MCP server provides **deterministic data operations**. All reasoning belongs in the agent:

| Task | Where |
|------|-------|
| Execute SQL query | MCP (`query_recipes`) |
| Decide what to cook tonight | Agent (LLM reasoning) |
| Read a recipe | MCP (`read_recipe`) |
| Adapt a recipe for guests | Agent (LLM writing) |
| Search recipes by text | MCP (`find_recipe`) |
| Plan a weekly meal schedule | Agent (calls MCP tools + applies planning rules) |

## Dossier Section Ownership

Sections have strict ownership:

| Owner | Sections |
|-------|----------|
| **ETL** (read-only) | Recipe data from source (title, ingredients, steps) |
| **Agent** (writeable) | `notes`, `variations`, `pairings`, `tags`, `cook_log` |

## Available Skills

| Skill | Directory | Purpose |
|-------|-----------|---------|
| `recipe-info` | `skills/recipe-info/` | Find and display recipe details |
| `tonight` | `skills/tonight/` | Quick weeknight dinner suggestions |
| `rotation` | `skills/rotation/` | Rediscover favourites not cooked recently |
| `pantry` | `skills/pantry/` | Suggest recipes based on what's in the fridge |
| `shopping` | `skills/shopping/` | Generate shopping lists from pinned recipes |
| `add-recipe` | `skills/add-recipe/` | Help the user add their own recipe |
| `manage` | `skills/manage/` | Star, rate, tag, annotate recipes |
| `wine-pairing` | `skills/wine-pairing/` | Bridge to cellarbrain for food-wine pairing |

## Installing Skills

```bash
# Install to ~/.openclaw/skills/recipebrain/
recipebrain install-skills

# Force overwrite existing
recipebrain install-skills --force

# Custom target directory
recipebrain install-skills --target /path/to/skills
```

## Efficiency Tips

- Use `find_recipe` with filters instead of raw SQL for text search
- Use `suggest_for_pantry` instead of manual ingredient matching
- Use `list_pinned` to check the current meal plan before suggesting
- Use `cook_history` to avoid recommending recently-cooked dishes
- Batch operations: `batch_annotate` and `batch_tag` for multi-recipe updates

## Cellarbrain Integration

The `wine-pairing` skill bridges recipebrain and cellarbrain via the MCP host. The host orchestrates both servers at runtime — no direct Python coupling between the projects.

When enabled:
1. Agent identifies a recipe/meal
2. Calls cellarbrain's `suggest_wines` MCP tool with food description
3. Returns pairing suggestions from the user's actual cellar

Configure in `recipebrain.toml`:
```toml
[cellarbrain]
enabled = true
```

## Creating Custom Skills

Create a skill in `.openclaw/<skill-name>/SKILL.md`:

```markdown
---
name: my-recipe-skill
description: "Description of what this skill does"
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# My Custom Skill

## MCP Tools Used
| Tool | Purpose |
|---|---|
| `find_recipe` | ... |
| `read_recipe` | ... |

## Workflow
1. ...
```

## Next Steps

- [MCP Server](mcp-server.md) — Full tool reference
- [MCP Testing](../operations/mcp-testing.md) — Verify tools work
