---
description: "Run full CI checks locally: lint, format, typecheck, tests, and smoke-test"
agent: agent
---
# Local CI

Run the full CI pipeline locally. All steps are **blocking** — every step must pass with zero errors and zero warnings unless explicitly overridden by the user. Follow these steps in order:

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

All type errors must be resolved before proceeding.

## 3. Test Collection Check

```
pytest --collect-only -q
```

Verify there are no collection errors (missing fixtures, bad imports) and no `PytestCollectionWarning`. If any are found, fix them before proceeding.

## 4. Unit Tests

```
pytest --cov=recipebrain --cov-report=term-missing -W error::pytest.PytestCollectionWarning
```

All tests must pass with zero errors and zero warnings. Report coverage summary.

## 5. Smoke Test

Verify the package is importable and CLI entry point works:

```
python -c "import recipebrain; print(recipebrain.__version__)"
recipebrain --help
```

If the MCP server module is available, also verify it loads without error:

```
python -c "from recipebrain.mcp_server import mcp; print(f'{len(mcp._tool_manager._tools)} tools registered')"
```

## 6. Skills Sync Check

Verify skills are in sync:

```
python .github/tools/sync-skills.py
git diff --exit-code src/recipebrain/skills/
```

If the diff is non-empty, skills are out of sync — fix before proceeding.

## Fix & Retest

If any step produces errors or warnings, fix the issues and re-run the failing step(s) until they pass cleanly.

## Commit

Once all steps pass with zero errors and zero warnings, commit all changes:

```
git add -A
git commit -m "<descriptive message summarizing the fixes>"
```

## Report

Summarize pass/fail status for each step. Confirm all checks passed and changes were committed.
