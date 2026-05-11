# Testing the MCP Server

How to verify the MCP server starts correctly, test individual tools, and run automated tests.

## Prerequisites

- Parquet data in `output/` (run ETL first)
- `pip install -e .` (editable install)

## 1. Verify the Server Starts

```bash
recipebrain mcp
# Ctrl+C to stop — no output means it started successfully (stdio transport)
```

## 2. Smoke-Test via CLI Commands

These CLI commands exercise the same data layer the MCP server uses:

```bash
# Verify Parquet data exists and is queryable
recipebrain info
recipebrain validate

# Verify basic recipe search (via MCP tool directly in tests)
pytest tests/test_mcp_server.py -v -k "test_find_recipe"
```

## 3. Test with MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) provides a web UI for interactive tool testing:

```bash
npx @modelcontextprotocol/inspector recipebrain mcp
```

This opens a browser UI where you can browse available tools, call them with parameters, and inspect responses.

## 4. Automated Tests (pytest)

### MCP tool unit tests

```bash
pytest tests/test_mcp_server.py -v
```

These tests create a temporary Parquet dataset, import the MCP tool functions directly, and verify responses — no running server needed.

### Run a specific test

```bash
pytest tests/test_mcp_server.py::TestFindRecipe -v
pytest tests/test_mcp_server.py -k "test_log_cook" -v
```

### Run all tests

```bash
pytest tests/ -v
```

## 5. Manual Tool Testing (Python REPL)

```python
from recipebrain.mcp_server import find_recipe, read_recipe, query_recipes

# Search
print(find_recipe(query="poulet"))

# Read full recipe
print(read_recipe(recipe_id=1))

# SQL query
print(query_recipes("SELECT count(*) AS total FROM recipes"))
```

## 6. Verify in VS Code Copilot

1. Ensure `.vscode/mcp.json` exists with the recipebrain server configured
2. Reload VS Code window (`Ctrl+Shift+P` → "Developer: Reload Window")
3. Open Copilot Chat and try: "What recipes do I have?"
4. Copilot should invoke the `find_recipe` or `query_recipes` tool

## Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| "Error: No parquet files" | ETL not run | `recipebrain etl --source fooby --limit 5` |
| Server exits immediately | Python import error | Check `pip install -e .` succeeded |
| Tools not visible in Copilot | `.vscode/mcp.json` missing | Create it (see [MCP Server](../modules/mcp-server.md)) |
| "QueryError" on tool calls | Parquet schema mismatch | Re-run ETL or check writer schemas |

## Next Steps

- [MCP Server](../modules/mcp-server.md) — Full tool reference
- [VS Code Debugging](vscode-debugging.md) — Debug tool calls
