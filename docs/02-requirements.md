# Requirements

## Functional Requirements

### FR-1 — Recipe Ingestion

- **FR-1.1** Scrape recipes from supported Swiss sites (see [03-data-sources.md](03-data-sources.md))
- **FR-1.2** Parse structured recipe data: title, source, language, servings, prep/cook time,
  difficulty, ingredients (qty + unit + name), steps, images, original tags
- **FR-1.3** Normalise ingredients to a canonical form (e.g. *"Zwiebel, fein gehackt"* → `onion` + qty + prep note)
- **FR-1.4** Detect and skip duplicates (same recipe scraped from multiple sources or re-scraped)
- **FR-1.5** Store original source URL + scrape timestamp for provenance
- **FR-1.6** Re-fetch on demand to refresh changed recipes

### FR-2 — Own Recipes

- **FR-2.1** Add a recipe via free-form Markdown
- **FR-2.2** Add a recipe via URL (one-shot scrape, even from unsupported sites — best-effort)
- **FR-2.3** Add a recipe via photo (OCR + LLM structuring) — *v2*
- **FR-2.4** Edit any recipe (own or scraped) — edits stored as overlay, original preserved
- **FR-2.5** Tag recipes manually (cuisine, occasion, dietary, custom)

### FR-3 — Promotion Ingestion

- **FR-3.1** Pull current weekly promotions from Migros, Coop, Denner, TopCC
- **FR-3.2** Match promoted products to canonical ingredients (e.g. *"Optigal Pouletbrust"* → `chicken-breast`)
- **FR-3.3** Track promotion validity period (start/end date)
- **FR-3.4** Refresh promotions weekly (cadence configurable)

### FR-4 — Cook Log

- **FR-4.1** Record when a recipe was cooked (date, servings, rating, notes)
- **FR-4.2** Quick-log via MCP tool ("I cooked recipe #42 tonight, 4★")
- **FR-4.3** Compute "last cooked" and "times cooked" per recipe

### FR-5 — Pantry / Fridge State

- **FR-5.1** Maintain a lightweight pantry list (free-text or structured)
- **FR-5.2** Update via MCP ("we're out of cream", "bought 1kg potatoes")
- **FR-5.3** No strict inventory accounting — best-effort hints, not a system of record

### FR-6 — Search & Recommendation (MCP tools)

- **FR-6.1** `find_recipe` — full-text + tag + ingredient + time filters
- **FR-6.2** `suggest_for_pantry` — recipes ranked by ingredient coverage of current pantry
- **FR-6.3** `suggest_rotation` — highly-rated recipes not cooked in N months
- **FR-6.4** `suggest_for_wine` — recipes matching food-pairing tags from cellarbrain
- **FR-6.5** `suggest_for_promotions` — recipes whose key ingredients are on sale this week
- **FR-6.6** `read_recipe` — fetch full dossier
- **FR-6.7** `log_cook` — record a cook event
- **FR-6.8** `shopping_list` — scaled, deduplicated, grouped, with current prices

### FR-7 — Cellarbrain Interop

- **FR-7.1** Expose recipes' food-pairing tags in a format cellarbrain can consume
- **FR-7.2** Optional: call cellarbrain MCP from recipebrain to enrich a recipe with
  "wines from my cellar that pair" at suggestion time

## Non-Functional Requirements

### NFR-1 — Privacy & Locality
- All data stored locally (Parquet + Markdown, like cellarbrain)
- Works fully offline once recipes are scraped (no cloud LLM required for queries)
- Cloud LLM use is opt-in per session

### NFR-2 — Language
- German (CH/DE) as primary recipe language
- French as secondary (Migusto, Fooby publish FR variants)
- English supported for own recipes
- Ingredient normalisation must handle DE ↔ FR ↔ EN synonyms

### NFR-3 — Politeness to Sources
- Respect `robots.txt` and rate-limit scraping (≤ 1 req / 2 s per host)
- Cache aggressively, only re-fetch when needed
- Identify with a clear `User-Agent` (e.g. `recipebrain/0.1 (personal-use)`)
- Store only what's needed — link back to source for full content where reasonable

### NFR-4 — Maintainability
- One source = one parser module (mirrors cellarbrain's `vinocell_parsers.py` pattern)
- Schema-first: Parquet schemas in `writer.SCHEMAS` are the source of truth
- Migrations framework for schema evolution

### NFR-5 — Reliability
- Scrapers degrade gracefully when site HTML changes (log + skip, never crash the pipeline)
- All ETL runs are idempotent
- Snapshot before every full run (cellarbrain pattern)

### NFR-6 — Performance
- ≤ 5 s response time for any MCP suggestion query on a collection of ≤ 5 000 recipes
- Full re-scrape of all sources ≤ 30 min
- Promotion refresh ≤ 5 min

## Out of Scope (v1)

- Mobile clients
- Multi-user / family sharing with conflict resolution
- Automated grocery ordering
- Nutrition / macro analysis
- Smart-fridge / IoT integration
- Voice interface (delegated to the MCP host's own voice features)

## Open Questions

- **Q1** — Recipe sites' terms of use: which explicitly forbid scraping for personal use?
- **Q2** — Promotion data: official APIs vs. scraping the weekly leaflet PDF vs. third-party aggregators (e.g. Profital, Bring!)?
- **Q3** — Ingredient normalisation: build our own dictionary, reuse Open Food Facts, or hybrid?
- **Q4** — How to represent "Menü" (multi-course meal plans) — first-class entity or composition of recipes?
- **Q5** — Local LLM strong enough for ingredient parsing, or fall back to deterministic regex parsers à la cellarbrain?
