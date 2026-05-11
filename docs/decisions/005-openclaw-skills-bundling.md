# ADR-005: OpenClaw Skills Bundling

## Status

Accepted

## Context

Skills are short, version-locked Markdown files designed to sit alongside MCP servers in an OpenClaw host. They evolve in lockstep with the MCP tool surface — a new tool means a new or updated skill, and removing a tool would break a skill.

Distributing skills separately (e.g., as a second package, or requiring users to clone the repo) creates version drift: users could have skills that reference tools that don't exist in their installed version.

## Decision

1. **Source of truth:** `.openclaw/` at the repo root. Developers edit skills here.
2. **Pre-build sync:** `.github/tools/sync-skills.py` copies `.openclaw/` → `src/recipebrain/skills/` so they ship inside the wheel as package data.
3. **User install:** `recipebrain install-skills` copies bundled skills from the installed package to `~/.openclaw/skills/recipebrain/` (or a custom target).
4. **CI integration:** the sync script runs before `pytest` and before `python -m build` in CI.

Pattern adapted from cellarbrain.

## Consequences

- **Version-locked:** skills always match the installed tool surface.
- **Simple distribution:** `pip install recipebrain` gets you everything.
- **Gitignore complexity:** `src/recipebrain/skills/*` is gitignored (generated), but `.gitkeep` is tracked. CI must run sync before tests.
- **Dev workflow:** developers must run `python .github/tools/sync-skills.py` after editing `.openclaw/` skills before testing locally.
