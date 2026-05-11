---
description: "Implement a feature or fix following recipebrain conventions, including tests"
mode: "agent"
---
# Implement

You are implementing a feature or fix in the recipebrain codebase. Follow this workflow:

## 1. Understand

- Read the relevant docs in `docs/` (entity model, architecture, MCP tools)
- Identify which modules are affected
- Check existing patterns in similar code

## 2. Plan

Before writing code, outline:

- Which files will be created or modified
- What the public API / interface looks like
- What tests are needed (happy path, edge cases, error cases)

Present the plan to the user for confirmation before proceeding.

## 3. Implement

Follow project conventions:

- `from __future__ import annotations` at the top of every module
- Union syntax: `str | None` (never `Optional[str]`)
- Built-in generics: `list`, `dict`, `tuple`
- Private helpers: `_leading_underscore`
- Module-level docstring explaining purpose
- Imports ordered: stdlib → third-party → local

### Key patterns by module type:

| Module | Pattern |
|--------|---------|
| Source adapter | Implement `SourceAdapter` (discover + fetch) |
| Promotion adapter | Implement `PromotionAdapter` (fetch_current) |
| MCP tool | Thin wrapper in `mcp_server.py`, data access only |
| Parser | Return `None` for optional fields, raise `ValueError` for required |
| Query | Use `QueryError` / `DataStaleError` |
| Writer | Update `writer.SCHEMAS` first if adding columns |

## 4. Test

Write tests in the matching `tests/test_<module>.py` file:

- Use `tmp_path` for file I/O
- Group in classes: `class TestFeatureName:`
- Use `@pytest.mark.parametrize` for data-driven tests
- Cover: happy path, edge cases (None, empty), error cases

## 5. Validate

Run the full check suite:

```
ruff check .
ruff format --check .
pytest --cov=recipebrain --cov-report=term-missing
```

All checks must pass before considering the task complete.
