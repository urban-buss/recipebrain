---
name: recipe-info
description: "Look up a recipe by name, ID, keyword, tag, or favourites and display full details."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# Recipe Information

Look up and display full recipe details — ingredients, steps, cook history, personal notes.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## Workflow

### 1. Find Recipe

| User wants | Action |
|-----------|--------|
| Search by name/keyword | `find_recipe(query="...", limit=5)` |
| Filter by tag | `find_recipe(tags=["weeknight", "quick"])` |
| Show favourites | `find_recipe(starred_only=True)` or `list_starred()` |
| Filter by difficulty/time | `find_recipe(difficulty="easy", max_total_minutes=30)` |

### 2. Present Matches

Show brief list: title, source, prep time. Let user pick if multiple.

### 3. Full Details

`read_recipe(recipe_id)` — full ingredients, steps, cook history, and personal dossier notes (notes, variations, pairings, tags).

### 4. Cook History

`cook_history(recipe_id)` — detailed log of past cook events with dates, ratings, and notes.

### 5. Personal Actions

- `star_recipe(recipe_id)` / `rate_recipe(recipe_id, rating)` — express preference
- `tag_recipe(recipe_id, tags)` — categorise with user tags
- `annotate_recipe(recipe_id, section, content)` — add personal notes, variations, or pairings
- `pin_recipe(recipe_id)` — add to cook-next pinboard

## Presentation

Structured recipe card: title, source, times, servings, ingredients (bulleted), steps (numbered), cook history, personal notes, tags.

## Tools

| Tool | Purpose |
|------|---------|
| `find_recipe` | Search by query, tags, starred, difficulty, time |
| `read_recipe` | Full recipe details with dossier notes |
| `cook_history` | Past cook events for a recipe |
| `list_starred` | All favourite recipes |
| `star_recipe` | Toggle favourite |
| `rate_recipe` | Set 1–5 rating |
| `tag_recipe` | Add user tags |
| `annotate_recipe` | Add notes, variations, or pairings |
| `pin_recipe` | Add to cook-next pinboard |
