---
applyTo: "**"
---
# Recipebrain — Copilot Workspace Instructions

## Project Overview

Recipebrain is a CLI toolkit and MCP server that scrapes Swiss recipe websites, normalises ingredients, tracks promotions, and exposes a personal recipe knowledge base via DuckDB/Parquet and MCP tools. Python 3.11+, MIT license. Companion to cellarbrain (wine cellar manager) — interop via MCP at runtime, no Python coupling.

## Knowledge Base

Detailed documentation lives in `docs/`. Consult these pages for architecture, data model, and subsystem behaviour:

| Topic | File |
|-------|------|
| Vision & use cases | `docs/01-vision-and-usecases.md` |
| Requirements | `docs/02-requirements.md` |
| Data sources (recipe + promotion) | `docs/03-data-sources.md` |
| Entity model (Parquet schemas, views) | `docs/04-entity-model.md` |
| MCP tools (15 tools, resources) | `docs/05-mcp-tools.md` |
| Architecture & build phasing | `docs/06-architecture.md` |
| Architecture decisions | `docs/decisions/001-*` through `005-*` |
| Full index | `docs/index.md` |

## Coding Conventions

### Python Style

- `from __future__ import annotations` at the top of every module.
- Union syntax: `str | None`, never `Optional[str]`. Built-in generics: `list`, `dict`, `tuple`.
- Private helpers: `_leading_underscore`.
- Module-level docstring explaining purpose, then stdlib → third-party → local imports.
- Parsers include `Examples:` in docstrings showing input → output.

### Type Aliases

```python
Lookup = dict[str, int]              # display_value → id
CompositeLookup = dict[tuple, int]   # composite_key → id
```

### Error Patterns

- Parsers: return `None` for optional missing fields, raise `ValueError` for required.
- Query layer: `QueryError` for SQL validation/execution, `DataStaleError` for missing Parquet.
- Dossier ops: `RecipeNotFoundError`, `ProtectedSectionError`.
- No defensive error handling for scenarios that cannot occur.

### Writer Schemas

All Parquet schemas are defined in `writer.SCHEMAS` as `pa.Schema` objects. When adding a new entity or column, update the schema dict first — the writer enforces schema conformance.

## Testing Conventions (pytest)

- Tests live in `tests/`, one file per source module.
- Group related tests in classes: `class TestFoobyAdapter:`.
- Shared fixtures in `conftest.py`.
- Test data builders: helper functions like `_make_dataset`, `_minimal_recipe` create temp Parquet datasets.
- Use `tmp_path` for all file I/O in tests; never write to the real `output/` directory.
- Use `pytest.raises(ValueError)` for expected failures.
- Use `@pytest.mark.parametrize` for data-driven tests; direct assertions for simple cases.

## Security Invariants

- `dossier_ops.resolve_dossier_path` uses `is_relative_to()` to prevent path traversal.
- `query.validate_sql` rejects INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE.
- Scrapers respect `robots.txt` and enforce rate-limiting per `settings.scraping`.
- No `eval()` or `exec()` anywhere in the codebase.
- TLS verification is never disabled.
- HTTP timeouts are always set (default: 30s from settings).
- Secrets live in `recipebrain.local.toml` (gitignored), never in main config.

## Always Write Tests

Every code change must include corresponding test updates. Never submit production code without tests. When adding or modifying functionality:

- Add unit tests in the matching `tests/test_<module>.py` file.
- Cover the happy path, edge cases (None, empty string), and error cases.
- If a change touches multiple modules (e.g. parser + transform + writer), add tests for each.
- Run `pytest` before considering any task complete.

## Common Tasks

### Adding a recipe source adapter
1. Create `src/recipebrain/sources/<name>.py` implementing `SourceAdapter`.
2. Implement `discover()` (URL enumeration) and `fetch()` (page → `RawRecipe`).
3. Prefer JSON-LD extraction via `extruct`; fall back to HTML only when JSON-LD is missing.
4. Add tests in `tests/test_sources_<name>.py` with saved HTML fixtures.
5. Register in source config when registry is implemented.
6. Run `pytest` and `recipebrain validate`.

### Adding a promotion adapter
1. Create `src/recipebrain/promotions/<name>.py` implementing `PromotionAdapter`.
2. Implement `fetch_current()` → `Iterable[RawPromotion]`.
3. Add tests in `tests/test_promotions_<name>.py`.
4. Run `pytest`.

### Adding a new MCP tool
1. Define in `mcp_server.py` with appropriate decorator.
2. Keep the tool thin — data access only, return formatted strings.
3. Handle exceptions from `query`/`dossier_ops`, return `f"Error: {exc}"`.
4. Add tests in `tests/test_mcp_server.py` using a temp Parquet dataset.
5. Update the tools table in `docs/05-mcp-tools.md`.

### Adding a schema migration
1. Create `src/recipebrain/migrations/m00N_description.py`.
2. Import and register in `migrations/__init__.py`.
3. Add tests in `tests/test_migrations.py`.
4. Run `pytest`.

### Running the project
```bash
pip install -e ".[dev]"       # editable install with dev deps
pytest                        # unit tests
recipebrain etl               # run ETL pipeline (once implemented)
recipebrain promotions refresh # refresh promotion data
recipebrain mcp               # start MCP server
recipebrain validate          # check data integrity
recipebrain install-skills    # install OpenClaw skills
```

## Memory System

The workspace includes a self-learning memory system that captures lessons across conversations.

### When to Write Memories

Write a memory file in `.memories/` when:
- You make a mistake and the user corrects you
- You discover an efficiency trick or shortcut
- The user provides explicit guidance or preferences
- You observe unexpected tool/API behavior
- You identify a recurring pattern worth codifying

### Format

Filename: `YYYY-MM-DD_<category>_<short-slug>.md`.

Frontmatter must include `severity: low|medium|high`.

### Reading Rule

Before non-trivial tasks, scan `.memories/INDEX.md` (if it exists) or `.memories/` filenames for relevant lessons. Only read full content when a filename is clearly relevant.

### Git Safety

- **Never** commit `.memories/` — refuse any `git add` or `git add -f` targeting memory files.
- Before commits, verify with `git status` that no `.memories/` paths are staged.
- If `.memories/` is missing from `.gitignore`, add it before proceeding.

### Secrets

Never write secrets, tokens, passwords, or API keys to memory files. Redact or skip entirely.

## Companion Project

[cellarbrain](https://github.com/<owner>/cellarbrain) — Swiss wine cellar manager. Recipebrain pairs with cellarbrain via MCP: recipebrain handles recipes and meal planning, cellarbrain handles wine. The `wine-pairing` skill and `cellar_pairing` MCP tool bridge the two systems at runtime through the MCP host.
