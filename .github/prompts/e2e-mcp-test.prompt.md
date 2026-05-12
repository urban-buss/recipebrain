---
description: "Run full E2E MCP testing: install recipebrain, smoke-test MCP server, execute all testing scenarios via tool calls, document defects, and produce a testing report"
agent: agent
tools: ["terminal", "file", "search"]
---
# E2E MCP Testing Suite

Run a complete end-to-end test of the recipebrain MCP server by acting as an MCP client. You will install, validate, exercise every tool, document defects, and produce a final report.

Read [analysis/26-e2e-mcp-testing-via-subagents.md](../../analysis/26-e2e-mcp-testing-via-subagents.md) for the full testing concept and scenario definitions.

---

## Phase 1: Install & Setup

1. Install recipebrain in editable mode with dev dependencies:
   ```
   pip install -e ".[dev]"
   ```
2. Verify the package is importable:
   ```
   python -c "import recipebrain; print(recipebrain.__version__)"
   ```
3. Verify CLI entry point:
   ```
   recipebrain --help
   ```

## Phase 2: MCP Server Smoke Test

1. Verify the MCP server module loads and tools are registered:
   ```
   python -c "from recipebrain.mcp_server import mcp; print(f'{len(mcp._tool_manager._tools)} tools registered')"
   ```
2. List all registered tools and verify the count matches expectations (25+ tools).
3. Verify MCP resources and prompts are registered:
   ```python
   python -c "
   from recipebrain.mcp_server import mcp
   tools = list(mcp._tool_manager._tools.keys())
   print(f'Tools ({len(tools)}):')
   for t in sorted(tools):
       print(f'  - {t}')
   "
   ```

## Phase 3: Prepare Test Dataset

Create a temporary test dataset to exercise tools against. Use the existing test patterns:

```python
python -c "
import tempfile, sys
from pathlib import Path
sys.path.insert(0, 'tests')
from test_mcp_server import *
# The test fixtures create a valid dataset — verify this works
print('Test infrastructure OK')
"
```

Alternatively, if real data exists in `output/`, use it. If neither is available, run a minimal ETL or create a synthetic dataset using the writer module.

## Phase 4: Execute Testing Scenarios

Work through **every scenario** from the analysis document by directly calling MCP tool functions. For each scenario, use this approach:

1. Import the tool function from `recipebrain.mcp_server`
2. Patch `_output_dir` to point at the test dataset
3. Call the tool with the specified arguments
4. Validate the response matches expected behavior

### Category 1: Discovery & Search

| Scenario | Call | Pass Criteria |
|----------|------|---------------|
| S1.1 | `find_recipe(course="main", max_total_minutes=30)` | Returns only main courses ≤30 min |
| S1.2 | `find_recipe(query="...")` → `read_recipe(id)` | Chaining works; details complete |
| S1.3 | `list_starred()` | Returns only starred recipes |
| S1.4 | `find_recipe(tags=["..."])` | Tag filter works |
| S1.5 | `current_promotions()` | Promotions render as table |
| S1.6 | `query_recipes("SELECT id, title FROM recipes LIMIT 5")` | Valid SQL executes |
| S1.7 | `server_stats()` | Counts are accurate |

### Category 2: Recommendations

| Scenario | Call | Pass Criteria |
|----------|------|---------------|
| S2.1 | `suggest_for_pantry(missing_ok=3)` | Returns ranked results with coverage |
| S2.2 | `suggest_rotation(min_rating=4, not_cooked_in_days=90)` | Only old, high-rated recipes |
| S2.3 | `suggest_easy(max_total_minutes=25)` | Respects time constraint |

### Category 3: Write Operations

| Scenario | Call | Pass Criteria |
|----------|------|---------------|
| S3.1 | `log_cook(recipe_id=X, rating=4)` | Event persisted; stats updated |
| S3.2 | `star_recipe(recipe_id=X)` | Flag set; visible in list_starred |
| S3.3 | `rate_recipe(recipe_id=X, rating=5)` | owner_rating updated |
| S3.4 | `add_recipe(title, ingredients, steps)` | New recipe searchable |
| S3.5 | `tag_recipe(recipe_id=X, tags=[...])` | Tags stored; searchable |
| S3.6 | `annotate_recipe(recipe_id=X, section="notes", content="...")` | Dossier updated |

### Category 4: Multi-Step Workflows

Execute these as sequential tool calls, verifying state between steps:

- **S4.1 Meal plan:** `suggest_easy` → `pin_recipe` → `list_pinned` → `log_cook` → verify auto-unpin
- **S4.2 New recipe lifecycle:** `add_recipe` → `find_recipe` → `read_recipe` → `tag_recipe` → `log_cook`
- **S4.3 Rating evolution:** `log_cook(rating=3)` → `log_cook(rating=5)` → verify latest wins
- **S4.4 Pin lifecycle:** `pin_recipe` → duplicate rejected → `unpin_recipe` → re-pin allowed
- **S4.5 Batch operations:** `batch_tag` → `find_recipe(tags=...)` → `batch_annotate` → `read_recipe`

### Category 5: Security & Edge Cases

| Scenario | Call | Pass Criteria |
|----------|------|---------------|
| S5.1 | `query_recipes("DROP TABLE recipes")` | Rejected with error |
| S5.2 | `annotate_recipe(recipe_id=X, section="ingredients", ...)` | Protected section rejected |
| S5.3 | Tools with None/empty args | Graceful error, no crash |
| S5.4 | `find_recipe(limit=99999)` | Handled gracefully |
| S5.5 | `read_recipe(recipe_id=999999)` | "not found" error |
| S5.6 | `add_recipe(title="Züri-Gschnätzlets")` | Unicode preserved |
| S5.7 | `log_cook(recipe_id=999)` | Error for missing recipe |
| S5.8 | `rate_recipe(recipe_id=1, rating=6)` | Out-of-range rejected |

## Phase 5: Document Defects

For every scenario that **fails or behaves unexpectedly**:

1. Create `.github/issues/` folder if it doesn't exist
2. Create one file per defect: `NNN-short-slug.md`
3. Use this format:

```markdown
# <Title>

**Status:** open
**Severity:** critical | high | medium | low
**Component:** mcp | query | recommend | dossier | writer
**Scenario:** <scenario ID from above, e.g. S3.1>

## Description

<What went wrong>

## Tool Call

```python
<exact call that triggered the issue>
```

## Expected

<what should have happened>

## Actual

<what actually happened, including full output>

## Analysis

<root cause if determinable>
```

## Phase 6: Testing Report

Once all scenarios are executed, create `analysis/27-e2e-mcp-test-report.md` with:

### Report Structure

```markdown
# E2E MCP Test Report — <date>

## Summary

- **Total scenarios:** <N>
- **Passed:** <N> (X%)
- **Failed:** <N> (X%)
- **Skipped:** <N> (reason)
- **Defects filed:** <N>

## Environment

- recipebrain version: <version>
- Python version: <version>
- OS: <os>
- Dataset: <synthetic / real / test fixture>

## Results by Category

### Category 1: Discovery & Search

| ID | Scenario | Status | Notes |
|----|----------|--------|-------|
| S1.1 | Find by course + time | ✅ Pass / ❌ Fail | <brief note> |
...

### Category 2: Recommendations
...

### Category 3: Write Operations
...

### Category 4: Multi-Step Workflows
...

### Category 5: Security & Edge Cases
...

## Behaviour Assessment

Rate each tool on a scale of 1-5:

| Tool | Correctness | Error Handling | Response Format | Composability |
|------|-------------|----------------|-----------------|---------------|
| find_recipe | X/5 | X/5 | X/5 | X/5 |
| read_recipe | X/5 | X/5 | X/5 | X/5 |
...

## Recommendations

1. <Priority fix>
2. <Improvement>
...
```

---

## Execution Rules

- **Do NOT skip scenarios.** Every scenario must be attempted.
- **Do NOT assume pass.** Actually execute the tool call and inspect output.
- **Fresh state per mutation test.** If state from a previous test could interfere, note it.
- **Capture full output.** Include actual tool responses in the report for failed tests.
- **Be honest.** If something is ambiguous, mark it as "⚠️ Partial" not "✅ Pass".
