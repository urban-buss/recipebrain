# User Interaction Requirements

This document covers the personal recipe experience: how a user tracks what
they cook, expresses preferences, plans meals, and adds their own recipes.
These features turn recipebrain from a passive recipe database into a personal
cooking knowledge base that learns the user's habits and tastes.

## Current State

| Feature | Status | Notes |
|---------|--------|-------|
| Cook log (`log_cook`) | ✅ Done | Appends to `cook_log` Parquet; per-cook rating + notes + `scale_factor` |
| Denormalised stats | ✅ Done | `log_cook` updates `times_cooked`, `last_cooked_at`, `owner_rating` inline |
| Star / favourite | ✅ Done | `star_recipe` toggle + `list_starred` + `find_recipe(starred_only=True)` |
| Explicit rating | ✅ Done | `rate_recipe` sets `owner_rating` directly (1–5, or None to clear) |
| Pin / cook-next | ✅ Done | `pinned_recipes` table + `pin_recipe` / `list_pinned` / `unpin_recipe`; auto-transition on `log_cook` |
| Own recipes | ✅ Done | `add_recipe(title, ingredients, steps, ...)` with ingredient parsing |
| Recipe modifications | ✅ Done | `annotate_recipe` writes to dossier; `read_recipe` merges dossier notes |
| Cook history in `read_recipe` | ✅ Done | `read_recipe` includes "## Cook History" section; standalone `cook_history` tool |
| Tags | ✅ Done | `tag_recipe` with slug normalisation; `find_recipe(tags=[...])` filter |
| CLI cook log | ✅ Done | `recipebrain log <id> [--rating N] [--notes "..."] [--servings N] [--scale-factor F]` |

---

## FR-8 — Cook History & Stats

### FR-8.1 — Enriched Cook Log

The existing `log_cook` tool records individual cook events. Extend it:

- **FR-8.1.1** `log_cook` should accept optional `scale_factor` (e.g. "I doubled it")
  in addition to `servings`, to distinguish "recipe says 4, I made 8" from
  "recipe says 4, I made 4 but the recipe itself is for 2".
- **FR-8.1.2** After logging, update the denormalised fields on `recipes`:
  - `times_cooked` ← `COUNT(*)` from `cook_log` for that recipe
  - `last_cooked_at` ← `MAX(cooked_on)` from `cook_log`
  - `owner_rating` ← latest non-null `rating` from `cook_log` (most recent
    opinion wins), or average — TBD, see OQ-1.
- **FR-8.1.3** `log_cook` should also accept `photo_path` (string, optional) —
  stored in cook_log, resolved relative to dossier directory. *v2*.

### FR-8.2 — Cook History View

- **FR-8.2.1** `read_recipe` must include a "## Cook History" section showing
  recent cook events (date, rating, notes) from `cook_log`.
- **FR-8.2.2** New MCP tool `cook_history(recipe_id?, limit?)` returns a
  formatted log of recent cook events. Without `recipe_id`, shows the global
  recent history across all recipes.
- **FR-8.2.3** `server_stats` should include "cooked this week / this month"
  counts.

### FR-8.3 — CLI Cook Log

- **FR-8.3.1** `recipebrain log <recipe_id> [--rating N] [--notes "..."] [--servings N] [--scale-factor F]` as a
  CLI shortcut for quick cook logging without the MCP server running.

---

## FR-9 — Favourites & Rating

### FR-9.1 — Star / Unstar Recipes

A simple boolean favourite flag, separate from the 1–5 rating.

- **FR-9.1.1** New column `recipes.starred` (boolean, default `false`).
- **FR-9.1.2** New MCP tool `star_recipe(recipe_id, starred=True)` — toggle.
- **FR-9.1.3** `find_recipe` gains a `starred_only: bool = False` filter.
- **FR-9.1.4** New MCP tool `list_starred(limit?)` — shortcut for finding all
  starred recipes.

### FR-9.2 — Explicit Rating

`owner_rating` exists on the schema but has no write path. Fix this:

- **FR-9.2.1** New MCP tool `rate_recipe(recipe_id, rating)` — sets
  `recipes.owner_rating` directly (1–5 scale). This is the "considered opinion"
  rating, distinct from the quick per-cook rating in `log_cook`.
- **FR-9.2.2** `rate_recipe` can also be called with `rating=None` to clear.
- **FR-9.2.3** If a user has never called `rate_recipe` explicitly, `owner_rating`
  may be auto-derived from `cook_log` ratings (see FR-8.1.2). An explicit
  `rate_recipe` call always takes precedence.

### FR-9.3 — Tags as Preferences

- **FR-9.3.1** New MCP tool `tag_recipe(recipe_id, tags: list[str])` — adds
  user tags to `recipe_tags`. Tags like `weeknight`, `meal-prep`, `guests`,
  `comfort-food` let the user express preferences beyond a numeric rating.
- **FR-9.3.2** `find_recipe` gains a `tags: list[str]` filter.
- **FR-9.3.3** Tags are free-form strings normalised to lowercase slugs. New
  tags are auto-created in the `tags` table on first use.

---

## FR-10 — Pinboard / Cook Next

A lightweight "intent to cook" list — not a full meal planner.

### FR-10.1 — Pin Entity

New table `pinned_recipes`:

| column     | type      | notes |
|------------|-----------|-------|
| id         | int32     | PK |
| recipe_id  | int32     | FK → recipes |
| pinned_at  | timestamp | when pinned |
| target_date| date      | optional: "want to cook on this date" |
| note       | string    | optional: "for Saturday dinner with guests" |
| status     | string    | `pinned` \| `cooked` \| `dismissed` |

### FR-10.2 — MCP Tools

- **FR-10.2.1** `pin_recipe(recipe_id, target_date?, note?)` — add to pinboard.
- **FR-10.2.2** `list_pinned(include_done=False)` — show current pins, ordered
  by `target_date` (nulls last), then `pinned_at`.
- **FR-10.2.3** `unpin_recipe(recipe_id)` — set status to `dismissed`.
- **FR-10.2.4** When `log_cook` is called for a pinned recipe, auto-transition
  the pin to `status='cooked'`.

### FR-10.3 — Integration with Suggestions

- **FR-10.3.1** `suggest_for_pantry`, `suggest_easy`, and `suggest_rotation`
  should deprioritise (but not exclude) already-pinned recipes to avoid
  redundant suggestions.
- **FR-10.3.2** `shopping_list` (when implemented) should accept `pinned=True`
  to generate a shopping list for all currently pinned recipes.

---

## FR-11 — Own Recipes & Modifications

### FR-11.1 — Add Own Recipe

- **FR-11.1.1** MCP tool `add_recipe(title, ingredients, steps, servings?,
  prep_minutes?, cook_minutes?, difficulty?, tags?, notes?)` — creates a new
  recipe with `source_id` pointing to the `own` source.
- **FR-11.1.2** Ingredients are accepted as a list of free-text strings (same
  format as scraped `ingredients_raw`). The ingredient parser normalises them.
- **FR-11.1.3** Steps are accepted as a list of strings.
- **FR-11.1.4** Returns the new recipe ID so the user can immediately
  `read_recipe`, `star_recipe`, or `pin_recipe` it.
- **FR-11.1.5** `status` defaults to `active` (no review workflow in v1 — the
  user is the author).

### FR-11.2 — Add Recipe from URL

- **FR-11.2.1** `add_recipe_from_url(url)` — one-shot scrape of any URL.
  Attempts JSON-LD extraction first, falls back to LLM-assisted parsing. *v2*.
- **FR-11.2.2** Creates recipe with `source.kind = 'imported'`, preserves
  original URL.

### FR-11.3 — Edit / Annotate Existing Recipes

Users should be able to personalise scraped recipes without losing the original.

- **FR-11.3.1** MCP tool `annotate_recipe(recipe_id, section, content)` —
  writes to the recipe's dossier file using the existing dossier system.
  `section` is one of the allowed sections: `notes`, `cook_log`, `tags`,
  `pairings`, `variations`.
- **FR-11.3.2** `read_recipe` must merge dossier notes into the output when a
  dossier file exists for the recipe.
- **FR-11.3.3** Variation support: `annotate_recipe(recipe_id, section='variations',
  content="Use mascarpone instead of cream cheese")` appends to the variations
  section. These are displayed alongside the original recipe in `read_recipe`.

### FR-11.4 — Delete Own Recipes

- **FR-11.4.1** CLI-only: `recipebrain delete-recipe <id>` — only allowed for
  `source.kind = 'own'`. Scraped recipes cannot be deleted (they'll be
  re-scraped).
- **FR-11.4.2** Soft-delete: sets `recipes.status = 'deleted'`. Query layer
  excludes deleted recipes by default.

---

## Schema Changes Required

### New columns on `recipes`

| column   | type    | default | notes |
|----------|---------|---------|-------|
| starred  | bool    | false   | FR-9.1 favourite flag |

### New table: `pinned_recipes`

See FR-10.1 above.

### Extended `cook_log`

| column       | type   | notes |
|--------------|--------|-------|
| scale_factor | float  | optional, e.g. 2.0 for "doubled" |

---

## MCP Tool Summary

All tools from this spec are implemented (22 total public tools on the MCP server).

| # | Tool | Type | Status |
|---|------|------|--------|
| 18 | `star_recipe` | write | ✅ Done |
| 19 | `rate_recipe` | write | ✅ Done |
| 20 | `cook_history` | read | ✅ Done |
| 21 | `pin_recipe` | write | ✅ Done |
| 22 | `list_pinned` | read | ✅ Done |
| 23 | `unpin_recipe` | write | ✅ Done |
| 24 | `add_recipe` | write | ✅ Done |
| 25 | `tag_recipe` | write | ✅ Done |
| 26 | `list_starred` | read | ✅ Done |
| 27 | `annotate_recipe` | write | ✅ Done |
| 28 | `add_recipe_from_url` | write | v2 — not yet implemented |

### Updated existing tools

| Tool | Change | Status |
|------|--------|--------|
| `log_cook` | Added `scale_factor` param; triggers inline denorm update; auto-transitions pins to `cooked` | ✅ Done |
| `read_recipe` | Merges cook history + dossier notes into output | ✅ Done |
| `find_recipe` | Added `starred_only` and `tags` filters | ✅ Done |
| `server_stats` | Added cook counts (this week / month) | ✅ Done |

---

## Denormalisation Strategy

After any write to `cook_log` or `starred` / `owner_rating`, the affected
recipe's denormalised fields must be updated. Two options:

1. **Inline** — the MCP tool computes and writes the update immediately.
   Simpler, no background job, but `log_cook` becomes slower.
2. **Deferred** — a lightweight recompute runs periodically or on next read.
   More complex, but keeps writes fast.

**Decision**: inline (option 1). `log_cook`, `star_recipe`, and `rate_recipe`
all update denormalised fields immediately via `_update_recipe_fields()`. The
Parquet read-modify-write for a single recipe row is fast enough. Deferred
recompute can be added later if write latency becomes a problem.

---

## Implementation Order

All phases complete.

### Phase 1 — Core interaction loop ✅

1. ✅ `star_recipe` / `rate_recipe`
2. ✅ `cook_history`
3. ✅ Enrich `read_recipe` with cook history
4. ✅ Denorm update in `log_cook` (+ `scale_factor` param)

### Phase 2 — Planning ✅

5. ✅ `pinned_recipes` schema + `pin_recipe` / `list_pinned` / `unpin_recipe`
6. ✅ Auto-cooked transition on `log_cook`

### Phase 3 — Own recipes ✅

7. ✅ `add_recipe` MCP tool (with ingredient parsing)
8. ✅ `annotate_recipe` (connect dossier system)
9. ✅ Enrich `read_recipe` with dossier notes

### Phase 4 — Polish ✅

10. ✅ `tag_recipe` + `find_recipe` tag/starred filters
11. ✅ `list_starred`
12. ✅ CLI `log` command (`recipebrain log`)

---

## Open Questions

- **OQ-1** — ~~`owner_rating` derivation~~ **Resolved**: latest non-null
  `cook_log` rating wins (most recent opinion). An explicit `rate_recipe` call
  sets `owner_rating` directly and takes precedence.
- **OQ-2** — ~~Pinboard ordering~~ **Resolved**: date-based sorting
  (`target_date` nulls last, then `pinned_at`). No manual drag-and-drop.
- **OQ-3** — ~~Star vs. multiple lists~~ **Resolved**: simple boolean
  `starred` flag + free-form tags via `tag_recipe`. Tags cover the multi-list
  use case (`weeknight`, `guests`, `comfort-food`).
- **OQ-4** — ~~Recipe variations~~ **Resolved**: free-text notes in the
  dossier `variations` section via `annotate_recipe`. Appended, not
  structured. Displayed in `read_recipe` output.
