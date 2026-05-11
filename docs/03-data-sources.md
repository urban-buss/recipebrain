# Data Sources

## Recipe Sources (Swiss)

Priority order for v1. Each gets its own parser module in `src/recipebrain/sources/`.

| # | Source | URL | Language | Notes |
|---|--------|-----|----------|-------|
| 1 | **Fooby** (Coop) | https://fooby.ch/de.html | DE / FR / IT | Large catalogue, strong photos, well-structured pages |
| 2 | **Migusto** (Migros) | https://migusto.migros.ch/de.html | DE / FR / IT | High-quality recipes, often paired with Migros products |
| 3 | **Swissmilk** | https://www.swissmilk.ch/de/rezepte-kochideen/ | DE / FR | Dairy-focused but very broad |
| 4 | **Schweizer Fleisch** | https://schweizerfleisch.ch/rezepte | DE / FR / IT | Meat-focused, useful for pairing with reds in cellarbrain |
| 5 | **Betty Bossi** (Coop) | https://www.bettybossi.ch/de/rezepte/ | DE / FR | Major Swiss recipe platform, very large catalogue, JSON-LD available |

### Acquisition strategy per source

For each source we need to determine:
1. **Listing strategy** — sitemap.xml, category pages, search API, or RSS?
2. **Detail page parser** — does it expose [schema.org Recipe](https://schema.org/Recipe) JSON-LD? (Most modern Swiss recipe sites do — easy win.)
3. **Pagination / discovery** — full crawl, or incremental "what's new since X"?
4. **Image handling** — store URLs only, or download for offline use?
5. **Refresh cadence** — weekly is enough for v1.
6. **Robots / ToS** — verify scraping for personal use is acceptable.

### Schema.org JSON-LD probe

Before writing custom HTML parsers, check each site for embedded
`<script type="application/ld+json">` blocks with `"@type": "Recipe"`.
This typically gives us, in one shot:
- name, description, image, author
- recipeIngredient (list of strings)
- recipeInstructions (list or HowToStep array)
- prepTime / cookTime / totalTime (ISO 8601 durations)
- recipeYield, recipeCategory, recipeCuisine, keywords
- nutrition (often present)

**Plan:** start with a generic JSON-LD parser. Per-site overrides only where needed.

## Promotion Sources (Swiss food retailers)

| # | Retailer | Likely sources to evaluate |
|---|----------|----------------------------|
| 1 | **Migros** | Public weekly leaflet (PDF); migros.ch product pages with `Aktion` flag; potentially Migros API used by their app |
| 2 | **Coop** | Coop.ch leaflet; Profital.ch aggregator; Coop@home product feed |
| 3 | **Denner** | Denner weekly Aktionen page; PDF leaflet |
| 4 | **TopCC** | topcc.ch Aktionen page (cash-and-carry, weekly leaflet) |

### Aggregator alternatives

Worth evaluating before building 4 separate scrapers:
- **Profital** — aggregates leaflets from many CH retailers
- **Bring!** — shopping list app, has promotion integrations (API access?)
- **Blattabock / Aktionis.ch** — third-party comparison sites

If one aggregator covers all four retailers cleanly, that becomes the v1 source
and per-retailer scrapers move to v2.

### Promotion → ingredient mapping

The hard problem is matching a promoted product to a canonical ingredient.

> *"M-Classic Pouletbrust IP-SUISSE 600 g"* → `chicken-breast` (qty 600 g, unit g)
> *"Crème entière UHT 35% 2.5 dl"* → `cream-double` (qty 250, unit ml)
> *"Penne Rigate Garofalo 500 g"* → `pasta-penne` (qty 500, unit g)

Approach:
1. Maintain a canonical ingredient catalogue (own dictionary, possibly seeded from Open Food Facts CH)
2. Per-retailer product → ingredient lookup table, grown over time
3. LLM-assisted matching for unknowns, with human confirmation before persisting

## Own-Recipe Inputs

| Mode | Pipeline |
|------|----------|
| **Markdown file** | Drop into `inbox/`, validator + parser → dossier |
| **Arbitrary URL** | Try JSON-LD; fall back to LLM-assisted extraction; manual review |
| **Photo of recipe card** *(v2)* | OCR (e.g. Tesseract or cloud OCR) → LLM structuring → manual review |
| **Voice / chat dictation** *(v2)* | MCP tool that accepts a free-form description and returns a structured recipe for confirmation |

## Storage Layout (proposed, mirrors cellarbrain)

```
recipebrain/
├── output/
│   ├── recipes.parquet
│   ├── ingredients.parquet
│   ├── recipe_ingredients.parquet      # join table with qty + unit + prep note
│   ├── tags.parquet
│   ├── recipe_tags.parquet
│   ├── sources.parquet                 # fooby, migusto, swissmilk, …
│   ├── cook_log.parquet
│   ├── pantry.parquet
│   ├── promotions.parquet
│   ├── retailers.parquet
│   └── promotion_ingredient_map.parquet
├── dossiers/
│   └── recipes/
│       └── 0042-pouletbrust-mit-lauch.md
├── inbox/                              # own-recipe drop folder
└── snapshots/                          # pre-ETL snapshots (cellarbrain pattern)
```

## Initial Validation Tasks

Before writing any code, validate the riskiest assumptions:

1. **JSON-LD coverage** — manually check 5 recipes per source. Is JSON-LD present and complete?
2. **Robots / ToS** — fetch each site's `robots.txt` and ToS page; document what's allowed.
3. **Promotion source** — test Profital coverage for all 4 retailers; if good, skip per-retailer scraping for v1.
4. **Ingredient normalisation** — sample 50 ingredients from each source; assess how messy the strings are. Decide regex-first vs. LLM-first.
5. **Language overlap** — check whether DE and FR variants of the same Fooby/Migusto recipe share a stable ID we can use to deduplicate.
