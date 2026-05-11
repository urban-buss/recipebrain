# Release Process

How to version, tag, and publish a new Recipebrain release.

The automated workflow is available as a Copilot prompt: `.github/prompts/release.prompt.md` (invoke with `/release` in chat). This document describes the process it follows.

---

## Versioning

Recipebrain follows [Semantic Versioning](https://semver.org/):

| Bump | When | Example |
|------|------|---------|
| **MAJOR** | Breaking changes to CLI, MCP tools, or config format | `1.0.0` → `2.0.0` |
| **MINOR** | New features, new MCP tools, new source adapters | `0.1.0` → `0.2.0` |
| **PATCH** | Bug fixes, parser corrections, documentation | `0.1.0` → `0.1.1` |

Version is defined in two places (both must be updated):
- `pyproject.toml` → `version = "X.Y.Z"`
- `src/recipebrain/__init__.py` → `__version__ = "X.Y.Z"`

---

## Branching Model

Development uses a `local_*` branch convention:

```
main  ←  feature-branch  ←  local_feature-branch
                ↑
          (squash merge, single commit)
```

- **`local_*` branches** — Working branches with many WIP commits.
- **Feature branches** — Clean branches with a single squash commit, ready for PR.
- **`main`** — Always releasable. Tags trigger PyPI publish.

---

## Release Steps

### Step 1: CI Validation

Before any release work, the full CI pipeline must pass locally:

| Check | Command | Blocking? |
|-------|---------|-----------|
| Lint | `ruff check .` | Yes — auto-fix and commit |
| Format | `ruff format --check .` | Yes — auto-fix and commit |
| Type check | `mypy src/recipebrain` | No (non-blocking, matches CI) |
| Tests | `pytest --cov=recipebrain --cov-report=term-missing` | Yes |
| Smoke test | `python -c "import recipebrain; print(recipebrain.__version__)"` | Yes |
| CLI entry point | `recipebrain --help` | Yes |
| Skills sync | `python .github/tools/sync-skills.py && git diff --exit-code src/recipebrain/skills/` | Yes |

If lint/format issues are found, they are fixed automatically and committed:
```bash
ruff check --fix .
ruff format .
git add -A && git commit -m "style: auto-fix lint/format issues"
```

If tests fail, the failure must be diagnosed and fixed before proceeding.

### Step 2: Version Bump

Compare the current version against `main`:

```bash
git show main:pyproject.toml | grep version
```

If the version is **unchanged** from main, bump the patch number:
- `0.0.1` → `0.0.2`
- Update both `pyproject.toml` and `src/recipebrain/__init__.py`
- Commit: `git commit -m "chore: bump version to 0.0.2"`

If the version was already bumped (e.g. for a planned minor release), skip this step.

### Step 3: Squash Merge to Feature Branch

All commits from the local working branch are squashed into a single commit on the clean feature branch:

```bash
# Determine branches
git branch --show-current          # → local_fix-search
# Target: fix-search (strip "local_" prefix)

# Create/reset feature branch from main
git checkout -B fix-search main

# Squash merge all work
git merge --squash local_fix-search

# Single conventional commit
git commit -m "fix(mcp): normalise diacritic queries in find_recipe" \
  -m "- Strip diacritics from search query to match title_normalised column
- Add E2E MCP test suite
- Update .gitignore for .github/issues/"
```

The commit message must:
- Use **conventional commit** format (`feat`, `fix`, `chore`, `refactor`)
- Summarise the overall change in the subject line (≤72 chars)
- List individual changes as bullet points in the body

After squashing, switch back to the local branch for continued work:
```bash
git checkout local_fix-search
```

### Step 4: Generate PyPI Test Prompt

A versioned test prompt is generated in `.prompts/` (gitignored) based on the actual diff:

```bash
git diff main..fix-search --stat
git diff main..fix-search -- src/
```

The prompt (`test-pypi-install-v0.0.2.prompt.md`) includes:
- **Environment setup** — clean venv, install from PyPI, verify metadata
- **New feature tests** — specific test steps for each changed/added feature
- **Regression tests** — verify modified modules still work correctly
- **Core functionality tests** — CLI smoke tests, imports, ETL dry run, MCP startup
- **Upgrade path** — `pip install --upgrade`, migration checks, data compatibility
- **Summary table** — pass/fail checklist

This prompt can be run after PyPI publication to validate the published package.

### Step 5: Push and Publish

```bash
# Push the feature branch
git push origin fix-search

# Create PR to main (via GitHub UI or CLI)
gh pr create --base main --head fix-search --title "fix(mcp): normalise diacritic queries"

# After PR is merged to main:
git checkout main && git pull
git tag -a v0.0.2 -m "Release v0.0.2"
git push origin v0.0.2
```

The `v*` tag triggers the `.github/workflows/publish.yml` workflow which:
1. Builds sdist + wheel via `python -m build`
2. Authenticates to PyPI via OIDC (Trusted Publishers — no API token needed)
3. Uploads via `pypa/gh-action-pypi-publish`

### Step 6: Post-Publish Verification

Run the generated test prompt (`.prompts/test-pypi-install-v0.0.2.prompt.md`) in a clean environment to verify the published package works correctly.

---

## Quick Reference

```
/release              ← Run the automated release prompt
/ci                   ← Run CI checks only (no release)
```

---

## Prerequisites

Before your first release:
1. PyPI account with 2FA enabled
2. Trusted Publisher configured on PyPI (see [pypi.md](pypi.md))
3. GitHub environment `pypi` created in repo settings
4. `.prompts/` directory exists and is in `.gitignore`

---

## Next Steps

- [PyPI Setup](pypi.md) — Trusted Publisher configuration and troubleshooting
- [Building](../development/building.md) — Build packages locally
