---
description: "Triage and fix all open issues in the issues/ folder, one by one"
agent: agent
---
# Fix Issues

Work through all open issues in the `issues/` folder, fixing each one systematically. **Each issue is investigated, planned, fixed, tested, and committed independently before moving to the next.**

## 1. Discover

List all `.md` files in the `issues/` folder (excluding `_resolved/` and `_not-an-issue/`). If no issues exist, report "No open issues" and stop.

## 2. Fix Each Issue (Sequential)

Process issues **one at a time**. Complete every sub-step for the current issue before starting the next. Never batch multiple issues into a single commit or mix investigation across issues.

### 2a. Investigate

Deep-dive into the issue before writing any code:

- Read the full issue document carefully.
- Identify the affected modules, reproduction steps, and expected behaviour.
- **Trace the code path**: read the relevant source files, follow function calls, understand data flow.
- **Reproduce the problem** mentally or via a quick test — confirm you understand *why* it fails.
- Check existing tests: what's covered, what's missing, what's passing incorrectly.
- Look at related code (callers, sibling modules, shared utilities) for context and side-effects.
- Check git history if the issue might be a regression.

### 2b. Root Cause Analysis

Before planning a fix, articulate:

- **What** is the exact bug or deficiency?
- **Where** in the code does it originate (file, function, line)?
- **Why** does the current code behave incorrectly? (logic error, missing case, wrong assumption, etc.)
- **Impact**: what else could be affected by the same root cause?

Write this up concisely. Do not skip this step — a wrong diagnosis leads to a wrong fix.

### 2c. Plan

Create a detailed implementation plan:

- Proposed fix: describe the code change at a logic level.
- Files to create or modify (source and tests).
- **Test plan**:
  - Regression test that would have caught this bug.
  - Edge cases (None, empty, boundary values, related scenarios).
  - Any existing tests that need updating.
- Side-effects or risks of the change.
- Documentation updates if the fix changes behaviour.

Present the plan, then proceed to implementation.

### 2d. Implement

- Apply the fix following project conventions (see `implement.prompt.md`).
- Write or update tests in the matching `tests/test_<module>.py` file.
- Keep changes minimal and focused — fix the root cause, don't refactor unrelated code.

### 2e. Test

Run the full relevant test suite — not just the new tests:

```
pytest tests/test_<module>.py -v
```

If multiple modules are affected, run all of them:

```
pytest tests/test_<module1>.py tests/test_<module2>.py -v
```

Then run the full test suite to check for regressions:

```
pytest
```

**All tests must pass before committing.** If tests fail, diagnose, fix, and re-run until green.

### 2f. Commit

Stage and commit the fix with a descriptive message:

```
git add -A
git commit -m "fix(<scope>): <short description>" -m "<details of what was wrong and how it was fixed>"
```

### 2g. Resolve

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

### 2h. Next

Move to the next issue and repeat from step 2a. Do **not** carry assumptions from the previous issue — investigate each one fresh.

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
- One-line summary per issue (filename → root cause → fix applied)
- CI status (pass/fail)
- Any follow-up items or caveats
