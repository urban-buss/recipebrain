---
name: shopping
description: "Plan meals around current promotions and generate a shopping list."
metadata: {"openclaw": {"requires": {"bins": ["recipebrain"]}}}
---

# Promotion-Aware Shopping

Plan meals using this week's retailer promotions, then build a meal plan.

## Owner Context

Switzerland, CHF, German recipe sources — translate when presenting. Retailers: Migros, Coop, Denner, TopCC.

## Workflow

### 1. Check Current Promotions

`current_promotions(retailer="all", limit=20)` — shows this week's deals.

### 2. Find Recipes Using Promoted Ingredients

`find_recipe(query="<promoted ingredient>", limit=5)` — search for recipes that use discounted items.

### 3. User Selects Meals

Present options; user picks meals for the week.

### 4. Pin Selected Meals

`pin_recipe(recipe_id, target_date?, note?)` — add to the cook-next pinboard with optional dates.

### 5. Review Pinboard

`list_pinned()` — review the current meal plan.

### 6. After Cooking

`log_cook(recipe_id)` — record cook events; auto-transitions pins to "cooked".

## Presentation

Show promotions with price + discount. Group recipe suggestions by promoted ingredient. Pinboard shows planned meals with dates.

> **Note:** `shopping_list` (ingredient aggregation) and `suggest_for_promotions` (auto-matching) are planned for v2.

## Tools

| Tool | Purpose |
|------|---------|
| `current_promotions` | This week's retailer deals |
| `find_recipe` | Search recipes by ingredient/keyword |
| `read_recipe` | Recipe details for selected meals |
| `pin_recipe` | Add to cook-next pinboard with date |
| `list_pinned` | Review current meal plan |
| `log_cook` | Record cook event (auto-transitions pins) |
