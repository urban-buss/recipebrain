---
name: wine-pairing
description: "Suggest recipes that pair with a wine, or find wines for a dish (bridges cellarbrain)."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain", "cellarbrain"]}}}
---

# Wine-Recipe Pairing

Find recipes for a wine (or wines for a recipe). Bridges recipebrain ↔ cellarbrain.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting.

## Workflow A: Wine → Recipes

### 1. Get Wine Context

User names a wine or grape. Call cellarbrain's `cellar_pairing` (via host) to get pairing keywords.

### 2. Find Matching Recipes

`find_recipe(query="<pairing keywords>", tags=["<cuisine>"], limit=5)` — search by flavour profile.

### 3. Present

Show recipe + why it pairs (weight, acidity, flavour bridge).

### 4. Save Pairing Notes

`annotate_recipe(recipe_id, section="pairings", content="Pairs well with ...")` — save the pairing for future reference.

## Workflow B: Recipe → Wines

### 1. Identify Recipe

`find_recipe(query)` or `read_recipe(recipe_id)` to get dish profile (cuisine, course, ingredients).

### 2. Ask Cellarbrain

Host calls cellarbrain's `pair_wine(dish="...")` to get wine suggestions from the cellar.

### 3. Present

Show wine picks with pairing rationale.

### 4. Save Pairing Notes

`annotate_recipe(recipe_id, section="pairings", content="Recommended: ...")` — record for next time.

## Presentation

Per pick: **Recipe/Wine** — pairing rationale — prep time or drinking window.

> **Note:** `suggest_for_wine` (auto wine-recipe matching) is planned for v2.

## Tools

| Tool | Purpose |
|------|---------|
| `find_recipe` | Search recipes by query, tags, difficulty |
| `read_recipe` | Full recipe details with dossier notes |
| `annotate_recipe` | Save pairing notes to recipe dossier |
| `cellar_pairing` | Cellarbrain wine-pairing bridge (host-orchestrated) |
