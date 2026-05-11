---
description: "Prepare a patch release: CI check, version bump, squash merge, and generate PyPI test prompt"
mode: "agent"
---
# Release Patch

Prepare the current branch for a patch release. Execute all steps in order — stop and report if any step fails unrecoverably.

## 1. Run CI Checks

Run the full local CI pipeline (lint, format, typecheck, tests, smoke-test) as defined in [ci.prompt.md](ci.prompt.md).

```
ruff check .
ruff format --check .
mypy src/recipebrain
pytest --cov=recipebrain --cov-report=term-missing -W error::pytest.PytestCollectionWarning
python -c "import recipebrain; print(recipebrain.__version__)"
recipebrain --help
python .github/tools/sync-skills.py
git diff --exit-code src/recipebrain/skills/
```

If any lint or format errors are found, **fix them automatically**, stage, and commit:
```
git add -A
git commit -m "style: auto-fix lint/format issues"
```

If tests fail, diagnose the root cause, fix, and commit before proceeding.

## 2. Bump Patch Version

Compare the current version in `pyproject.toml` against the `main` branch:

```
git show main:pyproject.toml | Select-String 'version'
```

If the local version is **unchanged** from main, bump to the next patch:
- Read current version from `pyproject.toml` (e.g. `0.0.1`)
- Increment patch → `0.0.2`
- Update `version = "..."` in `pyproject.toml`
- Update `__version__` in `src/recipebrain/__init__.py` if it exists there
- Commit:
  ```
  git add pyproject.toml src/recipebrain/__init__.py
  git commit -m "chore: bump version to <NEW_VERSION>"
  ```

If the version was already bumped, skip this step.

## 3. Squash Merge to Feature Branch

Determine the current branch name. It should match `local_*` pattern:

```
git branch --show-current
```

Derive the target feature branch name by stripping the `local_` prefix (e.g. `local_fix-search` → `fix-search`).

Then squash all commits from this local branch into a single commit on the feature branch:

```
# Count commits ahead of main
git log main..HEAD --oneline

# Switch to (or create) the feature branch from main
git checkout -B <feature-branch> main

# Squash merge all work from the local branch
git merge --squash local_<name>

# Craft a meaningful commit message summarising ALL changes
git commit -m "<type>(<scope>): <summary>" -m "<body with bullet points of key changes>"
```

The commit message must:
- Use conventional commit format (`feat`, `fix`, `chore`, `refactor`, etc.)
- Summarise the overall change in the subject line
- List individual changes as bullet points in the body
- Reference any notable fixes or features

After the squash commit, switch back to the local branch:
```
git checkout local_<name>
```

## 4. Generate PyPI Test Prompt

Analyse all changes included in this release:

```
git log main..<feature-branch> --oneline
git diff main..<feature-branch> --stat
git diff main..<feature-branch> -- src/
```

Then create a new file `.prompts/test-pypi-install-v<NEW_VERSION>.prompt.md` with:

### Structure of the generated prompt:

```markdown
---
mode: agent
description: "End-to-end verification of recipebrain v<NEW_VERSION> installed from PyPI"
---

# Test recipebrain v<NEW_VERSION> PyPI Installation

## Environment Setup
- Create fresh venv
- pip install recipebrain==<NEW_VERSION>
- Verify version, license, dependencies

## New Feature Tests
(For each changed/added feature in this release, write specific test steps)

## Regression Tests
(For each module that was modified, write steps to verify existing functionality still works)

## Core Functionality Tests
- CLI smoke tests (--version, --help, info, doctor, validate, snapshot list)
- Import all core modules
- ETL dry run with minimal config
- MCP server startup test
- Entry point verification

## Upgrade Path
- pip install --upgrade recipebrain
- Verify version changed
- Run migrations if any schema changes
- Verify existing data still loads

## Summary Table
| # | Test | Result |
|---|------|--------|
```

Include specific test commands for every feature that changed in this release. Do not use generic placeholders — derive actual test cases from the diff.

## 5. Final Report

Print a summary:

```
Release Preparation Complete
─────────────────────────────
Version:        <NEW_VERSION>
Feature branch: <feature-branch>
Squash commit:  <short hash + subject>
Test prompt:    .prompts/test-pypi-install-v<NEW_VERSION>.prompt.md

Next steps:
  1. git push origin <feature-branch>
  2. Create PR to main
  3. After merge: git tag -a v<NEW_VERSION> -m "Release v<NEW_VERSION>"
  4. git push origin v<NEW_VERSION>  (triggers PyPI publish)
```
