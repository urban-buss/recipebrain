---
name: pantry
description: "Suggest recipes using ingredients currently in the pantry/fridge."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# Use What's in the Fridge

Suggest recipes that maximise use of available pantry ingredients.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## Workflow

### 1. Update Pantry (if user provides items)

`update_pantry(items=[...])` — add or refresh items the user mentions.

### 2. Suggest Recipes

`suggest_for_pantry(limit=5)` — returns recipes ranked by ingredient coverage.

### 3. Present Results

Show coverage percentage per recipe: "You have 4/6 ingredients."

### 4. Deep-Dive

`read_recipe(recipe_id)` for the user's chosen recipe. Highlight missing ingredients.

### 5. Act on Choice

- `pin_recipe(recipe_id)` — save to cook-next pinboard
- `log_cook(recipe_id)` — record after cooking
- `star_recipe(recipe_id)` — mark as favourite

## Presentation

Per pick: **Title** (id) — coverage % — missing ingredients — prep time.

## Tools

| Tool | Purpose |
|------|---------|
| `update_pantry` | Add/refresh pantry items |
| `suggest_for_pantry` | Pantry-coverage-ranked suggestions |
| `read_recipe` | Full recipe details |
| `pin_recipe` | Save to cook-next pinboard |
| `log_cook` | Record a cook event |
| `star_recipe` | Mark as favourite |
