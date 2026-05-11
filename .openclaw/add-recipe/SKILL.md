---
name: add-recipe
description: "Save a new recipe by entering title, ingredients, and steps."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# Add a Recipe

Create a new personal recipe in the knowledge base.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## Workflow

### 1. Gather Recipe Details

Collect from the user:
- **title** (required)
- **ingredients** (required) — list of strings like `"200g Mehl"`, `"2 dl Rahm"`
- **steps** (required) — list of instruction strings
- **servings**, **prep_minutes**, **cook_minutes**, **difficulty** — optional
- **notes** — optional personal notes (saved to dossier)

Ingredients are parsed automatically: `"200g Pouletbrust, in Würfeln"` → quantity=200, unit=g, prep_note="in Würfeln".

### 2. Create

`add_recipe(title, ingredients, steps, servings?, prep_minutes?, cook_minutes?, difficulty?, notes?)` — returns the new recipe ID.

### 3. Follow-Up

After creation, offer to:
- `tag_recipe(recipe_id, tags)` — categorise with tags like `weeknight`, `meal-prep`
- `star_recipe(recipe_id)` — mark as favourite
- `pin_recipe(recipe_id)` — add to cook-next pinboard
- `annotate_recipe(recipe_id, section, content)` — add notes, variations, or pairings
- `read_recipe(recipe_id)` — verify the stored recipe

## Presentation

After creation, show: title, ingredient count, step count, new ID.

## Tools

| Tool | Purpose |
|------|---------|
| `add_recipe` | Create recipe from title + ingredients + steps |
| `tag_recipe` | Add user tags to the new recipe |
| `star_recipe` | Mark as favourite |
| `pin_recipe` | Add to cook-next pinboard |
| `annotate_recipe` | Add notes, variations, or pairings to dossier |
| `read_recipe` | Verify stored recipe |
