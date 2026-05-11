---
description: "Run full CI checks locally: lint, format, typecheck, tests, and smoke-test"
mode: "agent"
---
# Local CI

Run the full CI pipeline locally and report results. Follow these steps in order:

## 1. Lint & Format

```
ruff check .
ruff format --check .
```

Fix any issues found before proceeding.

## 2. Type Check

```
mypy src/recipebrain
```

Report errors but continue (typecheck is non-blocking, matching CI config).

## 3. Unit Tests

```
pytest --cov=recipebrain --cov-report=term-missing
```

All tests must pass. Report coverage summary.

## 4. Smoke Test

Verify the package is importable and CLI entry point works:

```
python -c "import recipebrain; print(recipebrain.__version__)"
recipebrain --help
```

If the MCP server module is available, also verify it loads without error:

```
python -c "from recipebrain.mcp_server import mcp; print(f'{len(mcp._tool_manager._tools)} tools registered')"
```

## 5. Skills Sync Check

Verify skills are in sync:

```
python .github/tools/sync-skills.py
git diff --exit-code src/recipebrain/skills/
```

If the diff is non-empty, skills are out of sync — flag this.

## Report

Summarize pass/fail status for each step. If everything passes, confirm the branch is CI-ready.
