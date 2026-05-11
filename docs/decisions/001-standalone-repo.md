# ADR-001: Standalone Repository

## Status

Accepted

## Context

recipebrain shares architectural patterns with cellarbrain (dossier_ops, query validator, snapshot, migrate framework, MCP skeleton, settings/TOML, CLI skeleton) but solves a different problem domain (recipes vs. wine) with different optional dependencies (extruct, selectolax vs. sentence-transformers, faiss) and a different release cadence.

Embedding recipebrain within the cellarbrain repo would create coupling in CI, versioning, and dependencies that doesn't match the problem structure.

## Decision

recipebrain lives in its own repository with no Python dependency on cellarbrain. Interop between the two systems happens exclusively via MCP at runtime, orchestrated by the chat host (OpenClaw or equivalent).

## Consequences

- **Copy-paste of stable patterns:** dossier_ops, query validator, snapshot, migrate framework, MCP skeleton are copied from cellarbrain with an attribution header (`# Adapted from cellarbrain/<file> @ <commit>`).
- **Independent release cadence:** recipebrain can ship v1 without waiting for cellarbrain changes.
- **No shared library** until 3+ "*brain" projects exist that would justify extraction.
- **Duplication cost:** bug fixes in shared patterns must be manually ported. Acceptable given the small surface area and stable nature of these modules.
