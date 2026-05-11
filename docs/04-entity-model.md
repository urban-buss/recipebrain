# Entity Model

Parquet schemas are the source of truth. This document defines the v1 entity
set, columns, types, and foreign-key relationships. Mirrors cellarbrain's
`writer.SCHEMAS` pattern.

## Entity Overview

```
recipes ──┬─< recipe_ingredients >── ingredients
          ├─< recipe_tags >── tags
          ├─< recipe_steps
          ├─< recipe_images
          ├─< cook_log
          └── sources

ingredients ──< promotion_ingredient_map >── promotions ──── retailers

pantry ── ingredients
```

Legend: `──<` = one-to-many, `>──` = many-to-one.

## Tables

### `sources`

Where a recipe came from.

| column        | type     | notes                                              |
|---------------|----------|----------------------------------------------------|
| id            | int32    | PK                                                 |
| key           | string   | stable slug, e.g. `fooby`, `migusto`, `own`        |
| display_name  | string   | "Fooby"                                            |
| base_url      | string   | "https://fooby.ch"                                 |
| language      | string   | primary language (`de`, `fr`, `it`, `mixed`)      |
| kind          | string   | `scraped` \| `own` \| `imported`                   |

Seeded at install time. New sources require a code change (parser module).

### `recipes`

Core entity. One row per recipe.

| column            | type        | notes                                                              |
|-------------------|-------------|--------------------------------------------------------------------|
| id                | int32       | PK                                                                 |
| source_id         | int32       | FK → sources                                                       |
| source_external_id| string      | stable ID at the source (URL slug or numeric); unique per source   |
| source_url        | string      | original URL                                                       |
| title             | string      | "Pouletbrust mit Lauch und Reis"                                   |
| title_normalised  | string      | lowercased, accent-stripped, for search                            |
| language          | string      | `de`, `fr`, `it`, `en`                                             |
| description       | string      | short blurb                                                        |
| servings          | int16       | default servings                                                   |
| prep_minutes      | int16       | nullable                                                           |
| cook_minutes      | int16       | nullable                                                           |
| total_minutes     | int16       | computed if missing                                                |
| difficulty        | string      | `easy` \| `medium` \| `advanced` \| null                          |
| cuisine           | string      | normalised, e.g. `swiss`, `italian`, `asian`                       |
| course            | string      | `starter` \| `main` \| `dessert` \| `side` \| `bake` \| `drink`   |
| primary_image_url | string      | nullable                                                           |
| original_keywords | list<str>   | raw tags from source, untouched                                    |
| owner_rating      | int8        | 1..5, nullable, set by user                                        |
| times_cooked      | int32       | denormalised from cook_log (recomputed in ETL)                     |
| last_cooked_at    | timestamp   | denormalised, nullable                                             |
| scraped_at        | timestamp   | first seen                                                         |
| updated_at        | timestamp   | last refresh                                                       |
| content_hash      | string      | sha256 of normalised content for change detection                  |
| status            | string      | `active` \| `archived` \| `draft`                                  |

Constraints: `(source_id, source_external_id)` unique.

### `recipe_steps`

Ordered cooking steps, one row per step.

| column     | type   | notes                              |
|------------|--------|------------------------------------|
| recipe_id  | int32  | FK                                 |
| step_no    | int16  | 1-based                            |
| text       | string |                                    |
| image_url  | string | nullable, per-step photo if any    |

PK: `(recipe_id, step_no)`.

### `recipe_images`

| column     | type   | notes                                |
|------------|--------|--------------------------------------|
| recipe_id  | int32  | FK                                   |
| seq        | int16  |                                      |
| url        | string |                                      |
| local_path | string | nullable, populated if downloaded    |
| caption    | string | nullable                             |

### `ingredients`

Canonical ingredient catalogue. Denormalised lookup, deduped across recipes
and retailers.

| column           | type      | notes                                                         |
|------------------|-----------|---------------------------------------------------------------|
| id               | int32     | PK                                                            |
| key              | string    | stable slug, e.g. `chicken-breast`, `cream-double`, `pasta-penne` |
| display_de       | string    | "Pouletbrust"                                                 |
| display_fr       | string    | "Blanc de poulet"                                             |
| display_it       | string    | nullable                                                      |
| display_en       | string    | "Chicken breast"                                              |
| category         | string    | `meat`, `dairy`, `vegetable`, `pantry`, `spice`, `bakery`, … |
| sub_category     | string    | nullable, e.g. `poultry`, `cheese-aged`                       |
| default_unit     | string    | preferred unit when scaling (`g`, `ml`, `pcs`, `tbsp`, …)    |
| density_g_per_ml | float64   | nullable, used for unit conversion                            |
| pairing_tags     | list<str> | tags compatible with cellarbrain's food-pairing model         |
| aliases          | list<str> | free synonyms for fuzzy matching                              |

`pairing_tags` is the bridge to cellarbrain — values must come from the
shared vocabulary used by cellarbrain's food catalogue.

### `recipe_ingredients`

Join table with quantity.

| column         | type      | notes                                                  |
|----------------|-----------|--------------------------------------------------------|
| recipe_id      | int32     | FK                                                     |
| seq            | int16     | preserves source ordering                              |
| ingredient_id  | int32     | FK; nullable if unresolved (raw text only)             |
| raw_text       | string    | original line, e.g. "200 g Pouletbrust, in Würfeln"   |
| quantity       | float64   | nullable                                               |
| unit           | string    | `g`, `ml`, `pcs`, `tbsp`, `tsp`, `pinch`, … nullable  |
| prep_note      | string    | "in Würfeln", "fein gehackt", nullable                 |
| optional       | bool      |                                                        |
| group_label    | string    | nullable, e.g. "Für die Sauce"                         |

PK: `(recipe_id, seq)`.

### `tags`

User- and source-defined tags, normalised.

| column     | type   | notes                                                   |
|------------|--------|---------------------------------------------------------|
| id         | int32  | PK                                                      |
| key        | string | slug, e.g. `weeknight`, `dinner-party`, `vegetarian`    |
| display    | string | "Weeknight"                                             |
| facet      | string | `occasion` \| `dietary` \| `season` \| `mood` \| `free` |

### `recipe_tags`

| column    | type  |
|-----------|-------|
| recipe_id | int32 |
| tag_id    | int32 |

PK: `(recipe_id, tag_id)`.

### `cook_log`

One row per cook event.

| column       | type      | notes                              |
|--------------|-----------|------------------------------------|
| id           | int64     | PK                                 |
| recipe_id    | int32     | FK                                 |
| cooked_on    | date      |                                    |
| servings     | int16     | actual servings cooked             |
| rating       | int8      | 1..5, nullable                     |
| notes        | string    | free text, nullable                |
| logged_at    | timestamp | when recorded                      |

### `pantry`

Lightweight current state. Snapshot semantics (current ≠ history).

| column          | type      | notes                                          |
|-----------------|-----------|------------------------------------------------|
| ingredient_id   | int32     | PK                                             |
| approx_quantity | float64   | nullable                                       |
| unit            | string    | nullable                                       |
| location        | string    | `fridge` \| `freezer` \| `pantry` \| `garden` |
| updated_at      | timestamp |                                                |
| note            | string    | nullable, e.g. "expires Friday"                |

History is intentionally not modelled in v1 — pantry is best-effort.

### `retailers`

| column       | type   | notes                                       |
|--------------|--------|---------------------------------------------|
| id           | int32  | PK                                          |
| key          | string | `migros`, `coop`, `denner`, `topcc`         |
| display_name | string |                                             |
| base_url     | string |                                             |

### `promotions`

| column         | type      | notes                                              |
|----------------|-----------|----------------------------------------------------|
| id             | int64     | PK                                                 |
| retailer_id    | int32     | FK                                                 |
| product_name   | string    | as advertised                                      |
| brand          | string    | nullable                                           |
| pack_size      | string    | "600 g", "2 × 1 l"                                 |
| pack_quantity  | float64   | numeric pack size if parseable                     |
| pack_unit      | string    | `g`, `ml`, `pcs`                                   |
| price_chf      | float64   | promotional price                                  |
| regular_price_chf | float64 | nullable                                          |
| discount_pct   | float64   | nullable, computed if both prices present          |
| valid_from     | date      |                                                    |
| valid_to       | date      |                                                    |
| source_url     | string    | leaflet page or product page                       |
| scraped_at     | timestamp |                                                    |

### `promotion_ingredient_map`

Maps a promoted product to a canonical ingredient. Manually curated +
LLM-assisted, growing over time.

| column          | type    | notes                                                    |
|-----------------|---------|----------------------------------------------------------|
| promotion_id    | int64   | FK                                                       |
| ingredient_id   | int32   | FK                                                       |
| confidence      | float32 | 0..1                                                     |
| match_method    | string  | `exact` \| `alias` \| `llm` \| `manual`                  |
| reviewed        | bool    | true once a human confirms                               |

PK: `(promotion_id, ingredient_id)`.

## Computed / Derived Fields

Recomputed by ETL, never edited directly:

- `recipes.times_cooked` — `count(cook_log)` per recipe
- `recipes.last_cooked_at` — `max(cooked_on)` per recipe
- `recipes.total_minutes` — `prep_minutes + cook_minutes` if missing
- `promotions.discount_pct` — `(regular - price) / regular * 100`
- A view `recipe_pairing_tags` aggregating `ingredients.pairing_tags` per recipe
  — this is the primary join surface against cellarbrain

## Foreign-Key Summary

| from                                     | to                                |
|------------------------------------------|-----------------------------------|
| recipes.source_id                        | sources.id                        |
| recipe_steps.recipe_id                   | recipes.id                        |
| recipe_images.recipe_id                  | recipes.id                        |
| recipe_ingredients.recipe_id             | recipes.id                        |
| recipe_ingredients.ingredient_id         | ingredients.id                    |
| recipe_tags.recipe_id                    | recipes.id                        |
| recipe_tags.tag_id                       | tags.id                           |
| cook_log.recipe_id                       | recipes.id                        |
| pantry.ingredient_id                     | ingredients.id                    |
| promotions.retailer_id                   | retailers.id                      |
| promotion_ingredient_map.promotion_id    | promotions.id                     |
| promotion_ingredient_map.ingredient_id   | ingredients.id                    |

## DuckDB Views (planned)

Equivalent to cellarbrain's query layer.

- `v_recipe_full` — recipes joined with cook stats, primary image, primary cuisine/course
- `v_recipe_ingredients_resolved` — recipe_ingredients with ingredient names already joined
- `v_recipe_pairing_tags` — recipe_id × pairing_tag (exploded), for cellarbrain joins
- `v_active_promotions` — promotions where `today` between `valid_from` and `valid_to`
- `v_promoted_ingredients` — active promotions joined to ingredients with best price per ingredient
- `v_pantry_coverage(recipe_id)` — for a given recipe, fraction of ingredients covered by pantry

## Identity & Deduplication Rules

- A recipe is identified by `(source_id, source_external_id)`.
- Cross-source duplicates (same dish on Fooby and Migusto) are **not** merged in v1
  — they are surfaced together by the search layer instead.
- Own recipes use `source_id = sources.key='own'`, `source_external_id = uuid`.
- Edits to scraped recipes are stored as overlay fields; original scrape preserved
  in `recipes.content_hash` history (mechanism TBD — likely a `recipe_revisions`
  table in v2).

## Open Modelling Questions

- **Menüs / multi-course meals** — first-class `menus` + `menu_items` tables, or
  just a tag + ordered list in a recipe note? Defer to v2 unless UC-6 demands it.
- **Substitutions** — modelled per-ingredient ("can replace X with Y") or via tags?
- **Seasonality** — store as ingredient attribute (`available_months`) or as a tag
  on recipes (`spring`, `summer`)? Probably both, with derivation from ingredients.
- **Nutrition** — out of scope for v1 (NFR), but the JSON-LD usually contains it.
  Decision: capture into a `recipe_nutrition` table opportunistically, expose later.
