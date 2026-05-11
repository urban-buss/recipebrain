# Testing

How to run the test suite, write tests, and perform smoke testing.

## Prerequisites

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

### All Unit Tests

```bash
pytest tests/ -v
```

Unit tests run in-memory using temporary directories — no network access needed.

### Useful Options

| Command | Purpose |
|---------|---------|
| `pytest -x` | Stop on first failure |
| `pytest --tb=short` | Shorter tracebacks |
| `pytest -k "test_fooby"` | Run tests matching name pattern |
| `pytest -k "TestFoobyAdapter"` | Run a specific test class |
| `pytest tests/test_sources_fooby.py` | Run a single test file |
| `pytest tests/test_mcp_server.py::TestFindRecipe::test_basic` | Run a single test |
| `pytest --co` | List tests without running (collect only) |
| `pytest -x --pdb` | Drop into debugger on first failure |
| `pytest --cov=recipebrain` | Run with coverage report |

### VS Code Test Runner

With pytest enabled in `.vscode/settings.json`, the Test Explorer discovers all tests automatically:

1. Open the **Testing** panel (beaker icon in sidebar)
2. Click the play button next to any test, class, or file
3. Click the debug button to run with breakpoints

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures (tmp datasets, settings)
├── dataset_factory.py               # Test data builder helpers
├── test_cli.py                      # CLI entry point tests
├── test_dashboard.py                # Dashboard endpoints
├── test_dataset_factory.py          # Factory self-tests
├── test_doctor.py                   # Health check tests
├── test_dossier_ops.py              # Dossier read/write/resolve
├── test_etl.py                      # ETL orchestrator
├── test_info.py                     # Info command
├── test_install_skills.py           # Skill installation
├── test_log.py                      # Logging setup
├── test_markdown.py                 # Markdown generation
├── test_mcp_server.py               # MCP tool functions
├── test_normalise_ingredients.py    # Ingredient normalisation
├── test_observability.py            # Event collector
├── test_parse_ingredient_line.py    # Ingredient parsing
├── test_parse_jsonld.py             # JSON-LD extraction
├── test_query.py                    # DuckDB query layer
├── test_recommend_easy.py           # Easy recipe suggestions
├── test_recommend_frequency.py      # Frequency recommendations
├── test_recommend_pantry.py         # Pantry-based suggestions
├── test_recommend_rotation.py       # Rotation suggestions
├── test_settings.py                 # TOML config loading
├── test_snapshot.py                 # Snapshot create/restore
├── test_sources_fooby.py            # Fooby adapter
├── test_sources_migusto.py          # Migusto adapter
├── test_sources_schweizerfleisch.py # Schweizerfleisch adapter
├── test_sources_swissmilk.py        # Swissmilk adapter
├── test_transform.py                # Entity transformation
├── test_validate.py                 # Validation checks
├── test_writer.py                   # Parquet writer + schemas
└── fixtures/                        # Saved HTML fixtures for scraper tests
```

## Writing Tests

Follow these conventions:

```python
"""Tests for the fooby source adapter."""
from __future__ import annotations

import pytest

from recipebrain.sources.fooby import FoobyAdapter


class TestFoobyAdapter:
    """Tests for FoobyAdapter."""

    def test_parse_recipe_from_fixture(self, fooby_html_fixture):
        adapter = FoobyAdapter()
        result = adapter.parse(fooby_html_fixture)
        assert result.title
        assert len(result.ingredients) > 0

    def test_empty_html_returns_none(self):
        adapter = FoobyAdapter()
        result = adapter.parse("")
        assert result is None

    @pytest.mark.parametrize("url,expected", [
        ("https://fooby.ch/de/rezepte/123", True),
        ("https://other.ch/recipe", False),
    ])
    def test_can_handle(self, url, expected):
        adapter = FoobyAdapter()
        assert adapter.can_handle(url) == expected
```

Key conventions:
- One test file per source module (`test_<module>.py`)
- Group related tests in classes (`class TestXxx:`)
- Use `tmp_path` fixture for all file I/O
- Use `pytest.raises()` for expected errors
- Use `@pytest.mark.parametrize` for data-driven tests
- Shared fixtures and data builders in `conftest.py` / `dataset_factory.py`
- HTML fixtures in `tests/fixtures/` for deterministic scraper tests

## Code Quality

```bash
# Linting
ruff check src/ tests/
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/

# Type checking (optional, via Pylance in VS Code)
mypy src/recipebrain/
```

## Next Steps

- [Building](building.md) — Build distribution packages
- [VS Code Debugging](../operations/vscode-debugging.md) — Debug configurations
