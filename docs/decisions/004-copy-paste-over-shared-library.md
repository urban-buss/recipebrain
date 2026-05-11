# ADR-004: Copy-Paste Over Shared Library

## Status

Accepted

## Context

The following modules originate in cellarbrain and are needed in recipebrain with only minor adaptations:

- `dossier_ops` — path resolution, read/write, section management
- `query` — SQL validation (DML/DDL rejection), DuckDB execution
- `snapshot` — point-in-time data backup
- `migrate` — schema migration framework
- `mcp_server` — MCP server skeleton with tool registration
- `settings` — TOML-based configuration with dataclass tree
- `cli` — argparse-based CLI with subcommands
- `writer` — Parquet writer with schema enforcement

Each represents ~50-200 lines of stable, well-tested code.

## Decision

Copy-paste with attribution header (`# Adapted from cellarbrain/<file> @ <commit>`). Do not extract a shared library until at least three projects use the same code.

## Consequences

- **No coupling:** recipebrain can diverge freely (different error types, different schema shapes, different CLI commands).
- **Duplication:** bug fixes in shared patterns must be manually ported between repos. Acceptable given:
  - Small surface area (~1000 lines total across all shared patterns)
  - Stable code (these modules rarely change after initial implementation)
  - Different domain objects (recipes vs. wines) that will diverge
- **Future extraction:** if a third "*brain" project emerges, extract a `brainlib` package at that point.
