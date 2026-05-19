---
description: "Prepare a patch release: version bump, squash merge to a meaningful feature branch"
agent: agent
---
# Release Patch

Prepare the current local branch for a patch release. Execute all steps in order — stop and report if any step fails.

## 1. Verify Local Branch

Confirm the current branch matches the `local_*` pattern:

```
git branch --show-current
```

If the branch does **not** start with `local_`, stop and inform the user.

## 2. Bump Patch Version (if needed)

Compare the current version in `pyproject.toml` against the `main` branch:

```
git show main:pyproject.toml | Select-String 'version'
```

If the local version is **unchanged** from main, bump to the next patch:
- Read current version from `pyproject.toml` (e.g. `0.0.11`)
- Increment patch → `0.0.12`
- Update `version = "..."` in `pyproject.toml`
- Update `__version__` in `src/recipebrain/__init__.py` if it exists there
- Commit:
  ```
  git add pyproject.toml src/recipebrain/__init__.py
  git commit -m "chore: bump version to <NEW_VERSION>"
  ```

If the version was already bumped, skip this step.

## 3. Review Commits

List all commits on the local branch that are not yet on main:

```
git log main..HEAD --oneline
```

Read through all commit messages to understand the scope of changes.

## 4. Derive Feature Branch Name

Based on the commit messages from step 3, choose a **meaningful, kebab-case branch name** that summarises the body of work (e.g. `fix-etl-metadata`, `add-promotion-caching`, `refactor-query-layer`).

Create the feature branch from main:

```
git checkout -B <feature-branch> main
```

## 5. Squash Merge

Squash all work from the local branch into a single commit on the new feature branch:

```
git merge --squash local_<name>
```

Craft a meaningful commit message based on the consolidated changes:

```
git commit -m "<type>(<scope>): <summary>" -m "<body with bullet points of key changes>"
```

The commit message must:
- Use conventional commit format (`feat`, `fix`, `chore`, `refactor`, etc.)
- Summarise the overall change in the subject line
- List individual changes as bullet points in the body
- **Do NOT** quote any issue IDs (e.g. `#061`) or analysis document IDs — those are internal

## 6. Final State

Stay on the new feature branch (do **not** switch back to the local branch).

Print a summary:

```
Release Preparation Complete
─────────────────────────────
Version:        <NEW_VERSION>
Feature branch: <feature-branch>
Squash commit:  <short hash + subject>

Next steps:
  1. git push origin <feature-branch>
  2. Create PR to main
  3. After merge: git tag -a v<NEW_VERSION> -m "Release v<NEW_VERSION>"
  4. git push origin v<NEW_VERSION>  (triggers PyPI publish)
```
