---
description: "Stage changes and create a well-formed conventional commit"
agent: agent
---
# Commit

Create a well-formed commit for the current changes. Follow these steps:

## 1. Review Changes

```
git status
git diff --stat
```

Examine the staged and unstaged changes to understand what was modified.

## 2. Verify Quality

Before committing, ensure:

- `ruff check .` passes (no lint errors)
- `ruff format --check .` passes (formatting clean)
- `pytest` passes (no broken tests)
- No `.memories/` files are staged — if found, unstage them immediately

## 3. Stage Files

Stage the relevant files logically. Group related changes into a single commit. If changes span unrelated concerns, suggest splitting into multiple commits.

**Never stage:**
- `.memories/` files
- `recipebrain.local.toml`
- `output/` directory contents

## 4. Commit Message

Use conventional commit format:

```
<type>(<scope>): <short summary>

<optional body explaining what and why>
```

### Types
- `feat` — new feature or capability
- `fix` — bug fix
- `refactor` — code restructuring without behaviour change
- `test` — adding or updating tests
- `docs` — documentation changes
- `chore` — build, CI, tooling changes
- `perf` — performance improvement

### Scopes
- `sources` — recipe source adapters
- `promotions` — promotion adapters
- `mcp` — MCP server/tools
- `query` — DuckDB query layer
- `transform` — data transformation
- `normalise` — ingredient normalisation
- `dossier` — recipe dossiers
- `cli` — CLI commands
- `skills` — OpenClaw skills

## 5. Execute

Run the commit directly — do not ask for approval:

```
git commit -m "<message>"
```

Do **not** push unless explicitly asked.
