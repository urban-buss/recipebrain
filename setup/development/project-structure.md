# Project Structure

Annotated source tree for the Recipebrain codebase.

```
recipebrain/
├── src/recipebrain/            # Source code (installed as editable package)
│   ├── __init__.py
│   ├── __main__.py             # python -m recipebrain entry
│   ├── cli.py                  # CLI entry point — all subcommands
│   ├── mcp_server.py           # MCP server (FastMCP, stdio)
│   ├── settings.py             # Configuration dataclasses + TOML loader
│   ├── etl.py                  # ETL orchestrator (discover → fetch → transform → write)
│   ├── transform.py            # Raw recipe → normalised entities
│   ├── writer.py               # Parquet writer with explicit schemas
│   ├── query.py                # DuckDB query layer (SQL validation, execution)
│   ├── validate.py             # Parquet integrity validation
│   ├── dossier_ops.py          # Recipe dossier read/write operations
│   ├── markdown.py             # Dossier Markdown generation
│   ├── doctor.py               # Health checks (data, config, snapshots)
│   ├── info.py                 # System info and data summary
│   ├── snapshot.py             # Create/list/restore data snapshots
│   ├── dashboard.py            # Observability web UI (Starlette)
│   ├── observability.py        # In-memory tool event collector
│   ├── log.py                  # Logging setup
│   ├── exceptions.py           # Custom exception classes
│   ├── install_skills.py       # Install OpenClaw skills to ~/.openclaw/
│   ├── sources/                # Recipe source adapters
│   │   ├── base.py             # SourceAdapter protocol
│   │   ├── fooby.py            # fooby.ch adapter
│   │   ├── migusto.py          # migusto.migros.ch adapter
│   │   ├── swissmilk.py        # swissmilk.ch adapter
│   │   └── schweizerfleisch.py # schweizerfleisch.ch adapter
│   ├── parse/                  # Parsers
│   │   ├── jsonld.py           # JSON-LD recipe extraction (extruct)
│   │   └── ingredient_line.py  # Ingredient text → structured data
│   ├── normalise/              # Normalisation logic
│   │   └── ingredients.py      # Ingredient key/unit normalisation
│   ├── recommend/              # Recommendation engines
│   │   ├── easy.py             # Quick weeknight suggestions
│   │   ├── frequency.py        # Frequency-based recommendations
│   │   ├── pantry.py           # Pantry-coverage-based suggestions
│   │   └── rotation.py         # Rotation/rediscovery suggestions
│   ├── promotions/             # Promotion adapters
│   ├── ingest_own/             # User-submitted recipe ingestion
│   ├── migrations/             # Schema migration scripts
│   └── skills/                 # OpenClaw agent skill files
│       ├── add-recipe/
│       ├── manage/
│       ├── pantry/
│       ├── recipe-info/
│       ├── rotation/
│       ├── shopping/
│       ├── tonight/
│       └── wine-pairing/
├── tests/                      # Test suite (pytest)
│   ├── conftest.py             # Shared fixtures
│   ├── dataset_factory.py      # Test data builder helpers
│   ├── test_*.py               # One file per source module
│   └── fixtures/               # Saved HTML fixtures for scraper tests
├── docs/                       # Reference documentation
│   ├── 01-vision-and-usecases.md
│   ├── 02-requirements.md
│   ├── 03-data-sources.md
│   ├── 04-entity-model.md
│   ├── 05-mcp-tools.md
│   ├── 06-architecture.md
│   └── decisions/              # Architecture decision records
├── dossiers/recipes/           # Per-recipe Markdown dossiers
├── output/                     # Generated output (Parquet files)
├── snapshots/                  # Data snapshots (pre-ETL backups)
├── inbox/                      # Incoming files for ingestion
├── .github/                    # Workflows, agent definitions, instructions
├── .vscode/                    # VS Code workspace configuration
├── recipebrain.toml.example    # Example configuration (copy to recipebrain.toml)
├── recipebrain.toml            # Project configuration (gitignored: local.toml)
├── pyproject.toml              # Package metadata, build config, dependencies
└── recipebrain.code-workspace  # VS Code workspace file
```

## Key Entry Points

| File | Purpose |
|------|---------|
| `cli.py` | CLI entry point — all subcommands dispatch from here |
| `mcp_server.py` | MCP server — `@mcp.tool()` decorated functions |
| `settings.py` | Configuration dataclasses + TOML loader |
| `etl.py` | ETL orchestrator (source discovery, fetch, transform, write) |
| `transform.py` | Raw recipe → normalised entity rows |
| `writer.py` | Parquet writer — `SCHEMAS` dict defines all table schemas |
| `query.py` | DuckDB read-only query layer |

## Data Flow

```
Source websites → sources/*.py (discover + fetch)
                  → parse/jsonld.py (extract JSON-LD)
                  → parse/ingredient_line.py (parse ingredients)
                  → transform.py (normalise entities)
                  → writer.py (write Parquet)
                  → query.py (DuckDB read)
                  → mcp_server.py (expose to agents)
```

## Next Steps

- [Testing](testing.md) — Run and write tests
- [Building](building.md) — Build distribution packages
