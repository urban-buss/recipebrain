# Fresh Install Validation

Agent prompt for validating a fresh PyPI install end-to-end.

Copy-paste this prompt into a fresh agent session:

---

```
You are validating a fresh install of the "recipebrain" Python package from PyPI.
Follow these steps exactly and report the result of each step.

### Step 1 — Create a clean environment

```bash
mkdir recipebrain-test && cd recipebrain-test
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

### Step 2 — Install from PyPI

```bash
pip install "recipebrain[dev]"
recipebrain --version
```

Report the installed version.

### Step 3 — Run ETL (small batch)

```bash
recipebrain etl --source fooby --limit 5
```

Report: success?, recipe count, files created in `output/`.

### Step 4 — Validate

```bash
recipebrain validate
```

Report pass/fail.

### Step 5 — Run pytest

```bash
pytest
```

Report pass/fail counts.

### Step 6 — Doctor check

```bash
recipebrain doctor
```

Report all check results.

### Step 7 — Verify MCP server

```bash
recipebrain mcp   # Ctrl+C to stop
```

Confirm it starts without errors.

### Step 8 — Test a recipe search

```python
from recipebrain.mcp_server import find_recipe
print(find_recipe(limit=3))
```

Report whether results are returned.

### Summary

Report overall status: all steps passed / which failed.
```
