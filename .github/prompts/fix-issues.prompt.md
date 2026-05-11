---
description: "Triage and fix all open issues in the issues/ folder, one by one"
mode: "agent"
---
# Fix Issues

Work through all open issues in the `issues/` folder, fixing each one systematically.

## 1. Discover

List all `.md` files in the `issues/` folder (excluding `_resolved/`). If no issues exist, report "No open issues" and stop.

## 2. Fix Each Issue

Iterate through every issue file. For each one, complete **all** sub-steps before moving to the next:

### 2a. Understand

- Read the full issue document carefully.
- Identify the affected modules, reproduction steps, and expected behaviour.
- Check related source files and tests to build context.

### 2b. Plan

Before writing code, outline:

- Root cause analysis
- Which files will be created or modified
- What tests are needed (regression test covering the issue + edge cases)
- Any documentation updates required

Present the plan briefly, then proceed.

### 2c. Implement & Test

- Apply the fix following project conventions (see `implement.prompt.md`).
- Write or update tests in the matching `tests/test_<module>.py` file.
- Run the relevant tests to confirm the fix:

```
pytest tests/test_<module>.py -v
```

All targeted tests must pass before proceeding.

### 2d. Commit

Stage and commit the changes with a descriptive message:

```
git add -A
git commit -m "fix(<scope>): <short description>" -m "<details of what was wrong and how it was fixed>"
```

### 2e. Resolve

- Move the issue file to `issues/_resolved/`:

```
mkdir -p issues/_resolved
git mv issues/<filename>.md issues/_resolved/<filename>.md
```

- Prepend `[RESOLVED] ` to the document's H1 title inside the file.
- Commit the move:

```
git add -A
git commit -m "docs: resolve issue <filename>"
```

### 2f. Next

Move to the next issue and repeat from step 2a.

## 3. CI Validation

Once all issues are resolved, run the full CI pipeline:

```
ruff check .
ruff format --check .
pytest --collect-only -q
pytest --cov=recipebrain --cov-report=term-missing -W error::pytest.PytestCollectionWarning
python -c "import recipebrain; print(recipebrain.__version__)"
recipebrain --help
```

All checks must pass. If any fail, diagnose and fix before finishing.

## 4. Summary

Print a final report:

- Number of issues resolved
- One-line summary per issue (filename → what was fixed)
- CI status (pass/fail)
- Any follow-up items or caveats
