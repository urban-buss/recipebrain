# Configuration Overview

Recipebrain configuration uses TOML files with a layered precedence system.

## Precedence (highest wins)

1. **CLI arguments** — `--config`
2. **`recipebrain.local.toml`** — machine-specific overrides (gitignored)
3. **`recipebrain.toml`** — project defaults (checked in)
4. **Built-in defaults** — in `settings.py` dataclasses

## Local Overrides

Create `recipebrain.local.toml` at the project root (gitignored). Use for secrets and machine-specific paths:

```toml
# recipebrain.local.toml — machine-specific overrides (gitignored)

[paths]
output_dir = "output"

[scraping]
user_agent = "recipebrain/0.0.1 (personal; your-email@example.com)"
```

## Configuration Sections

| Section | Purpose | Details |
|---------|---------|---------|
| `[paths]` | Data and output directories | `output_dir`, `dossier_dir`, `inbox_dir`, `snapshot_dir` |
| `[scraping]` | HTTP politeness settings | `rate_limit_seconds`, `user_agent`, `timeout_seconds`, `respect_robots_txt` |
| `[sources.<name>]` | Per-source adapter config | `enabled`, `language` |
| `[promotions]` | Promotion data sources | `enabled`, `adapter`, `refresh_interval_hours` |
| `[pantry]` | Pantry tracking | `expiry_warning_days` |
| `[cellarbrain]` | Cross-server wine pairing bridge | `enabled`, `mcp_endpoint` |
| `[mcp]` | MCP server settings | `transport`, `host`, `port` |

## Example Configuration

```toml
# ── Paths ──────────────────────────────────────────────────────────────────────
[paths]
output_dir = "output"
dossier_dir = "dossiers/recipes"
inbox_dir = "inbox"
snapshot_dir = "snapshots"

# ── Scraping ───────────────────────────────────────────────────────────────────
[scraping]
rate_limit_seconds = 2.0
user_agent = "recipebrain/0.0.1 (personal use)"
respect_robots_txt = true
timeout_seconds = 30

# ── Sources ────────────────────────────────────────────────────────────────────
[sources.fooby]
enabled = true
language = "de"

[sources.migusto]
enabled = true
language = "de"

[sources.swissmilk]
enabled = false
language = "de"

[sources.schweizerfleisch]
enabled = false
language = "de"

# ── Promotions ─────────────────────────────────────────────────────────────────
[promotions]
enabled = true
adapter = "profital"
refresh_interval_hours = 168  # weekly

# ── Pantry ─────────────────────────────────────────────────────────────────────
[pantry]
expiry_warning_days = 3

# ── Cellarbrain ────────────────────────────────────────────────────────────────
[cellarbrain]
enabled = false
# mcp_endpoint = "stdio"

# ── MCP ────────────────────────────────────────────────────────────────────────
[mcp]
transport = "stdio"
# host = "localhost"
# port = 8002
```

## Security

- Secrets belong in `recipebrain.local.toml` (gitignored), never in `recipebrain.toml`.
- Never commit API keys, tokens, or passwords.
- TLS verification is never disabled.
- HTTP timeouts are always set (default: 30s).

## Next Steps

- [ETL](../modules/etl.md) — Run the pipeline with custom config
- [Logging](../operations/logging.md) — Configure logging in detail
