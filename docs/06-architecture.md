# Architecture

Recipebrain follows the same architectural shape as cellarbrain. Where a
cellarbrain module ports cleanly, we say so explicitly so the v1 build can
move fast.

## High-Level Pipeline

```
┌──────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐
│   Sources    │──▶│   Scrapers   │──▶│  Transform  │──▶│   Writer     │
│ (Fooby, …)   │   │  (per-site)  │   │ (normalise) │   │  (Parquet)   │
└──────────────┘   └──────────────┘   └─────────────┘   └──────┬───────┘
                                                               │
┌──────────────┐   ┌──────────────┐                            │
│  Promotion   │──▶│  Promotion   │────────────────────────────┤
│   sources    │   │  scrapers    │                            │
└──────────────┘   └──────────────┘                            │
                                                               ▼
                                                       ┌───────────────┐
┌──────────────┐                                       │   Markdown    │
│  Own recipe  │──────────────────────────────────────▶│   Dossiers    │
│   inputs     │                                       │  (per recipe) │
└──────────────┘                                       └───────┬───────┘
                                                               │
                          ┌────────────────────────────────────┤
                          ▼                                    ▼
                   ┌──────────────┐                    ┌──────────────┐
                   │   DuckDB     │◀───────────────────│  MCP Server  │
                   │  Query Layer │                    │   (tools)    │
                   └──────────────┘                    └──────┬───────┘
                                                              │
                                                              ▼
                                                   ┌────────────────────┐
                                                   │  Chat Client (LLM) │
                                                   │  + cellarbrain MCP │
                                                   └────────────────────┘
```

## Module Layout

```
recipebrain/
├── pyproject.toml
├── recipebrain.toml                 # main config
├── recipebrain.local.toml           # secrets, host paths
├── src/recipebrain/
│   ├── __init__.py
│   ├── settings.py                  # dataclasses + TOML loader
│   ├── cli.py                       # subcommands
│   ├── mcp_server.py                # MCP entrypoint
│   │
│   ├── sources/                     # one module per recipe source
│   │   ├── __init__.py
│   │   ├── base.py                  # SourceAdapter ABC
│   │   ├── jsonld_recipe.py         # generic schema.org/Recipe parser
│   │   ├── fooby.py
│   │   ├── migusto.py
│   │   ├── swissmilk.py
│   │   └── schweizerfleisch.py
│   │
│   ├── promotions/                  # one module per retailer (or aggregator)
│   │   ├── __init__.py
│   │   ├── base.py                  # PromotionAdapter ABC
│   │   ├── profital.py              # aggregator first
│   │   ├── migros.py                # fallbacks per retailer
│   │   ├── coop.py
│   │   ├── denner.py
│   │   └── topcc.py
│   │
│   ├── parse/                       # generic field parsers
│   │   ├── duration.py              # ISO 8601 + DE strings ("ca. 30 Min.")
│   │   ├── quantity.py              # "200 g", "2 EL", "eine Prise"
│   │   ├── ingredient_line.py       # "200 g Pouletbrust, in Würfeln" → struct
│   │   └── language.py
│   │
│   ├── normalise/
│   │   ├── ingredients.py           # raw → canonical ingredient_id
│   │   ├── tags.py
│   │   └── units.py
│   │
│   ├── transform.py                 # row builders per entity (cellarbrain pattern)
│   ├── writer.py                    # SCHEMAS dict + Parquet write
│   ├── markdown.py                  # dossier render/parse
│   ├── dossier_ops.py               # safe path ops, fences, ALLOWED_SECTIONS
│   ├── query.py                     # DuckDB views + SQL validator
│   ├── recommend/
│   │   ├── pantry.py                # suggest_for_pantry scoring
│   │   ├── rotation.py
│   │   ├── promotions.py
│   │   ├── wine_bridge.py           # cellarbrain interop
│   │   └── easy.py
│   ├── shopping.py                  # list composition + grouping
│   ├── ingest_own/
│   │   ├── markdown.py
│   │   ├── url.py                   # one-shot scrape via JSON-LD
│   │   └── text.py                  # LLM-assisted structuring (optional)
│   ├── pantry.py
│   ├── cooklog.py
│   ├── snapshot.py                  # pre-ETL snapshot
│   └── migrations/                  # schema migrations
│       ├── __init__.py
│       └── m001_initial.py
│
├── tests/
│   └── (one test file per source module + helpers)
│
├── output/                          # Parquet datasets (gitignored)
├── dossiers/                        # Markdown dossiers
│   └── recipes/
├── inbox/                           # drop folder for own recipes
├── snapshots/                       # pre-ETL backups
└── docs/                            # the docs you're reading
```

## Reuse Map (from cellarbrain)

| cellarbrain module          | Recipebrain equivalent           | Reuse level             |
|-----------------------------|----------------------------------|-------------------------|
| `writer.SCHEMAS` pattern    | `writer.py`                      | Pattern, not code       |
| `dossier_ops.py`            | `dossier_ops.py`                 | Port verbatim + tweak   |
| `markdown.py` fences        | `markdown.py`                    | Port pattern            |
| `query.py` + `validate_sql` | `query.py`                       | Port verbatim           |
| `migrate.py` framework      | `migrations/`                    | Port verbatim           |
| `mcp_server.py` skeleton    | `mcp_server.py`                  | Port skeleton + tools   |
| `snapshot` pattern          | `snapshot.py`                    | Port pattern            |
| `email_poll/` IMAP          | (n/a v1)                         | Could be reused for newsletter recipes in v2 |
| `vinocell_parsers.py`       | `sources/<site>.py` modules      | Pattern, per-source     |
| `parsers.py`                | `parse/`                         | Pattern only            |
| Sommelier engine            | (n/a v1)                         | Pairing tags come from cellarbrain |
| Settings dataclass + TOML   | `settings.py`                    | Port verbatim           |
| CLI subparser layout        | `cli.py`                         | Port pattern            |

About 60% of the v1 codebase is structural reuse — the genuinely new work is:
the source/promotion adapters, ingredient normalisation, and the
recommendation scoring functions.

## Operating Modes

### Local-only (default, recommended)

- Scraping + parsing + normalisation: deterministic Python (no LLM needed)
- Ingredient parsing: regex + dictionary
- Pairing: comes from cellarbrain (which can be local-only too)
- LLM (local Ollama / LM Studio): used only by the MCP host as the conversational layer
- Privacy: nothing leaves the machine

### Hybrid (opt-in per session)

- Local for queries and parsing
- Cloud LLM (Anthropic / OpenAI / etc.) for the chat layer when answer quality matters
- LLM-assisted ingredient extraction from messy own-recipe text → cloud
- Promotion → ingredient matching for unknowns → cloud, cached locally afterwards
- Default off, requires `recipebrain.local.toml` to declare a provider

### Full-cloud

- Same as hybrid, but the MCP host runs a cloud LLM by default
- All data still stays local; only individual tool calls' arguments + returns
  travel to the cloud LLM
- Same posture as cellarbrain — the *data* never leaves the machine

## Settings Layout (proposed)

```toml
# recipebrain.toml
[paths]
output_dir = "output"
dossier_dir = "dossiers"
inbox_dir  = "inbox"
snapshot_dir = "snapshots"

[scraping]
user_agent = "recipebrain/0.1 (personal use; contact: you@example.com)"
rate_limit_seconds = 2.0
respect_robots = true
download_images = false

[sources.fooby]
enabled = true
languages = ["de"]
[sources.migusto]
enabled = true
languages = ["de"]
[sources.swissmilk]
enabled = true
languages = ["de"]
[sources.schweizerfleisch]
enabled = true
languages = ["de"]

[promotions]
aggregator = "profital"        # or "per-retailer"
refresh_cron = "0 6 * * 1"     # Monday 06:00
[promotions.retailers]
migros = true
coop = true
denner = true
topcc = true

[pantry]
staples = ["salt", "pepper", "olive-oil", "water", "butter"]

[cellarbrain]
enabled = true
mcp_command = "cellarbrain mcp"  # how to launch cellarbrain MCP from chat host
# (recipebrain itself does NOT call cellarbrain in v1 — see MCP doc)

[mcp]
expose_query_recipes = true
default_search_limit = 10
```

## ETL Cadence & Idempotency

| Job                | Cadence       | Idempotent | Snapshot? |
|--------------------|---------------|------------|-----------|
| Recipe full scrape | Monthly / on-demand | Yes (content_hash dedup) | Yes |
| Recipe incremental | Weekly        | Yes        | Yes       |
| Promotion refresh  | Weekly (Mon)  | Yes (overwrite by valid_from) | No |
| Own-recipe ingest  | On-demand     | Yes (uuid) | No        |
| Cook log append    | On-demand     | Yes (PK)   | No        |
| Recompute derived  | After any ETL | Yes        | No        |

All ETL writes go through the snapshot wrapper (cellarbrain pattern):
copy current Parquet → snapshot dir → write new → on failure, restore.

## Failure Modes & Degradation

| Failure                        | Behaviour                                       |
|--------------------------------|-------------------------------------------------|
| One source's HTML changed      | Source's parser logs + skips that recipe; ETL continues with other sources |
| Promotion source down          | Old promotions remain queryable; `valid_to` filters automatically hide stale ones |
| Cellarbrain MCP not running    | `suggest_for_wine` and `cellar_pairing` return a graceful "cellarbrain not available" message |
| Ingredient unresolvable        | Stored with `ingredient_id = NULL`; `raw_text` preserved; surfaced in `recipebrain validate` for review |
| Promotion product unmappable   | Stored without `promotion_ingredient_map` row; `validate` reports unmapped products |

## Security Invariants

Same posture as cellarbrain:

- `dossier_ops.resolve_dossier_path` uses `Path.is_relative_to()` — no traversal
- `query.validate_sql` rejects all DML/DDL — SELECT only
- MCP tools never `eval`/`exec` user input
- Scrapers verify TLS, bound response sizes, time out aggressively
- No secrets in `recipebrain.toml`; secrets live in `recipebrain.local.toml`
  (gitignored)

## Build Phasing

A pragmatic v1 → v2 split:

**v1 (MVP — useful for daily dinner decisions)**
- Schemas + writer + DuckDB views
- JSON-LD generic parser + Fooby + Migusto adapters
- Profital promotion adapter (or one retailer if Profital doesn't pan out)
- Ingredient normalisation: deterministic + small seed dictionary
- MCP tools: 1, 2, 3, 4, 7, 9, 12, 14, 15 (search, read, pantry, rotation, easy, log, current promotions, query, stats)
- Own recipes via Markdown drop only
- Dossier render + edit fences
- CLI: `etl`, `promotions refresh`, `ingest`, `validate`, `mcp`

**v1.5 — wine bridge & shopping**
- Tools 5, 6, 8, 13 (`suggest_for_wine`, `suggest_for_promotions`, `shopping_list`, `cellar_pairing`)
- Pairing tags wired to cellarbrain's vocabulary
- Swissmilk + Schweizer Fleisch adapters

**v2 — comfort & growth**
- Photo OCR for own recipes
- LLM-assisted ingredient extraction
- Per-retailer promotion adapters as Profital fallbacks
- Menüs (multi-course)
- Nutrition opportunistic capture
- Newsletter ingestion via `email_poll/` (port from cellarbrain)
