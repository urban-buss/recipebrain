---
name: rotation
description: "Suggest forgotten or rarely-cooked recipes to add variety."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# Recipe Rotation

Rediscover recipes you haven't cooked in a while. Adds variety to meal planning.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## Workflow

### 1. Get Rotation Suggestions

`suggest_rotation(limit=5)` — returns recipes sorted by staleness (longest since last cooked, or never cooked but bookmarked).

### 2. Present Options

Show last-cooked date (or "never tried") and brief description.

### 3. Check History

`cook_history(recipe_id)` — see when and how it went last time.

### 4. Deep-Dive

`read_recipe(recipe_id)` for the user's pick.

### 5. Act on Choice

- `pin_recipe(recipe_id)` — save to cook-next pinboard for later
- `log_cook(recipe_id)` — record after cooking
- `star_recipe(recipe_id)` — mark as favourite if rediscovered

## Presentation

Per pick: **Title** (id) — last cooked date — prep time — key ingredients.

## Tools

| Tool | Purpose |
|------|---------|
| `suggest_rotation` | Staleness-ranked suggestions |
| `read_recipe` | Full recipe details |
| `cook_history` | Past cook events for context |
| `log_cook` | Record a cook event |
| `pin_recipe` | Save to cook-next pinboard |
| `star_recipe` | Mark as favourite |
