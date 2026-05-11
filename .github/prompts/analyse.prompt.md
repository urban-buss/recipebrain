---
description: "Analyse code, architecture, data flow, or issues in the recipebrain codebase"
mode: "agent"
---
# Analyse

Perform a structured analysis of the recipebrain codebase. Adapt scope based on the user's request.

## Analysis Types

### Code Analysis
- Examine module structure, dependencies, and coupling
- Identify code smells, duplication, or inconsistencies
- Check adherence to project conventions (see `.github/copilot-instructions.md`)
- Review error handling patterns

### Architecture Analysis
- Map data flow: scrape → parse → transform → write → query → MCP
- Identify missing components vs. the design in `docs/06-architecture.md`
- Check alignment with entity model in `docs/04-entity-model.md`
- Evaluate MCP tool coverage vs. `docs/05-mcp-tools.md`

### Test Coverage Analysis
- Identify modules lacking test coverage
- Find untested edge cases or error paths
- Suggest high-value tests to add

### Security Analysis
- Verify security invariants from copilot-instructions.md
- Check for path traversal, SQL injection, missing timeouts
- Ensure no `eval()`, `exec()`, disabled TLS, or hardcoded secrets

### Dependency Analysis
- Review `pyproject.toml` dependencies for version constraints
- Identify unused or missing dependencies
- Check for known vulnerabilities (if tools available)

## Output Format

Present findings as:

1. **Summary** — one-paragraph overview
2. **Findings** — numbered list, each with severity (critical/high/medium/low)
3. **Recommendations** — actionable next steps, prioritised

If the analysis reveals issues worth tracking, suggest creating files in `.github/issues/`.
