---
name: tonight
description: "Suggest what to cook tonight based on pantry, promotions, and cook history."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# What to Cook Tonight

Recommend a meal using pantry contents, current promotions, and rotation scoring.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## 1. Check What's Already Planned

`list_pinned()` — check if there's already a pinned recipe for tonight.

## 2. Map the Request

| User says | Strategy |
|-----------|----------|
| "quick dinner", "something easy" | `suggest_easy(max_minutes=30)` — fast recipes |
| "use what I have" | `suggest_for_pantry` — pantry-first |
| "something different" | `suggest_rotation` — least-recently-cooked |
| "what's on sale" | `current_promotions` then `find_recipe` by ingredient |
| generic "what to cook?" | `suggest_easy` + `suggest_for_pantry` combined |

## 3. Filter by Preferences

Check if user has starred recipes or tags to narrow results:
- `find_recipe(starred_only=True)` — favourites
- `find_recipe(tags=["weeknight"])` — tagged for tonight

## 4. Recommend

Call the appropriate tool with `limit=5`. Present top 3-5 options.

## 5. Deep-Dive (optional)

`read_recipe(recipe_id)` for the user's pick — full ingredients, steps, cook history, personal notes.

## 6. After Deciding

- `log_cook(recipe_id, rating?, notes?)` — record the cook event
- `pin_recipe(recipe_id)` — "I'll cook this later" if not tonight

## Presentation

Per pick: **Title** (id) — prep time — key ingredients — source. Flag promoted ingredients.

## Tools

| Tool | Purpose |
|------|---------|
| `list_pinned` | Check existing meal plans |
| `suggest_for_pantry` | Pantry-first suggestions |
| `suggest_easy` | Quick/easy recipes |
| `suggest_rotation` | Least-recently-cooked |
| `current_promotions` | This week's deals |
| `find_recipe` | Search with filters (tags, starred, difficulty) |
| `read_recipe` | Full recipe details with dossier notes |
| `cook_history` | Recent cook events for context |
| `log_cook` | Record a cook event |
| `pin_recipe` | Save to cook-next pinboard |
