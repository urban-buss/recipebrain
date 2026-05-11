# VS Code Debugging

Debug configurations for stepping through Recipebrain CLI commands, tests, and the MCP server.

## launch.json

Add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "ETL (Fooby, limit 5)",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["etl", "--source", "fooby", "--limit", "5"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "ETL (All Sources)",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["etl"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Validate",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["validate"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Doctor",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["doctor"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Info",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["info"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "MCP Server (stdio)",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["mcp"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Dashboard",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["dashboard", "--port", "8777"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Snapshot Create",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["snapshot", "create", "--label", "debug"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "Install Skills",
      "type": "debugpy",
      "request": "launch",
      "module": "recipebrain",
      "args": ["install-skills", "--force"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    },
    {
      "name": "pytest (Current File)",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}", "-v", "--tb=short"],
      "cwd": "${workspaceFolder}",
      "console": "integratedTerminal"
    }
  ]
}
```

## Using Debug Configurations

1. Open the **Run and Debug** panel (`Ctrl+Shift+D`)
2. Select a configuration from the dropdown
3. Press F5 to start debugging
4. Set breakpoints in source files by clicking the gutter

## Tips

- **Breakpoints in source adapters** — Set breakpoints in `sources/fooby.py` to inspect parsed HTML/JSON-LD
- **Breakpoints in MCP tools** — Set breakpoints in `mcp_server.py` tool functions
- **Variable inspection** — Hover over Parquet table objects to see schema and row counts
- **Watch expressions** — Add `rows[0]` or `result.to_pylist()` to inspect data

## Debugging Tests

1. Open a test file in the editor
2. Click the debug icon (🐛) next to any test in the Testing panel
3. Or use the "pytest (Current File)" launch configuration

## Next Steps

- [Testing](../development/testing.md) — Test runner options
- [MCP Testing](mcp-testing.md) — Verify MCP server
