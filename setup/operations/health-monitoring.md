# Health Monitoring

Use `recipebrain doctor` for comprehensive health checks.

## Quick Check

```bash
# Run all health checks
recipebrain doctor

# Validate data integrity
recipebrain validate

# Show system info
recipebrain info
```

## Doctor Checks

The `doctor` command runs multiple checks and reports status:

| Check | What It Verifies |
|-------|-----------------|
| Output directory | Parquet files exist in `output/` |
| Schema conformance | Tables match expected schemas |
| Data freshness | ETL has been run (not stale) |
| Snapshot health | Snapshot directory accessible |
| Dossier integrity | Dossier files are well-formed |
| Config validity | `recipebrain.toml` parses correctly |

### Output Format

```
  ✓ output_directory: 8 parquet files found
  ✓ schema_conformance: all tables match schemas
  ! data_freshness: last ETL was 14 days ago
  ✓ snapshot_health: 5 snapshots available
  ✓ dossier_integrity: all dossiers valid
  ✓ config_valid: configuration loaded successfully

WARN: some checks need attention.
```

Severity levels: `✓` OK, `!` Warning, `✗` Error.

## Automated Health Check

```powershell
# PowerShell one-liner
recipebrain doctor; recipebrain validate; recipebrain info
```

## Data Freshness

Check when ETL was last run:

```bash
recipebrain info
```

The info output shows the most recent `scraped_at` timestamp across all recipes.

## Disk Usage

```powershell
# Windows
Get-ChildItem output\*.parquet | Measure-Object -Property Length -Sum

# macOS/Linux
du -sh output/
```

## Next Steps

- [Observability](observability.md) — Tool invocation metrics
- [Logging](logging.md) — Configure log levels
