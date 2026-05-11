"""Health check system for recipebrain data and configuration.

Runs a suite of checks and returns a structured report. Used by the
``recipebrain doctor`` CLI command.
"""

from __future__ import annotations

import enum
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from recipebrain.writer import SCHEMAS, compute_schema_hash, read_schema_version


class Severity(enum.Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single health check."""

    name: str
    severity: Severity
    message: str


@dataclass
class DoctorReport:
    """Aggregated results of all health checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.severity == Severity.OK for c in self.checks)

    @property
    def worst(self) -> Severity:
        if not self.checks:
            return Severity.OK
        severities = {Severity.ERROR: 2, Severity.WARN: 1, Severity.OK: 0}
        return max(self.checks, key=lambda c: severities[c.severity]).severity


def run_doctor(output_dir: Path, snapshot_dir: Path, dossier_dir: Path) -> DoctorReport:
    """Run all health checks and return a report.

    Args:
        output_dir: Path to the Parquet data directory.
        snapshot_dir: Path to the snapshot directory.
        dossier_dir: Path to the dossier directory.
    """
    report = DoctorReport()
    report.checks.append(_check_output_dir(output_dir))
    report.checks.append(_check_parquet_files(output_dir))
    report.checks.append(_check_schema_version(output_dir))
    report.checks.append(_check_snapshots(snapshot_dir))
    report.checks.append(_check_dossiers(dossier_dir))
    report.checks.append(_check_disk_usage(output_dir))
    return report


def _check_output_dir(output_dir: Path) -> CheckResult:
    if not output_dir.exists():
        return CheckResult("output_dir", Severity.ERROR, f"Missing: {output_dir}")
    return CheckResult("output_dir", Severity.OK, f"Exists: {output_dir}")


def _check_parquet_files(output_dir: Path) -> CheckResult:
    if not output_dir.exists():
        return CheckResult("parquet_files", Severity.ERROR, "Output directory missing")
    present = []
    missing = []
    for entity in sorted(SCHEMAS):
        path = output_dir / f"{entity}.parquet"
        if path.exists():
            present.append(entity)
        else:
            missing.append(entity)
    if not present:
        return CheckResult("parquet_files", Severity.WARN, "No parquet files found — run ETL first")
    if missing:
        return CheckResult(
            "parquet_files",
            Severity.WARN,
            f"{len(present)} present, {len(missing)} missing: {', '.join(missing)}",
        )
    return CheckResult("parquet_files", Severity.OK, f"All {len(present)} entities present")


def _check_schema_version(output_dir: Path) -> CheckResult:
    stored = read_schema_version(output_dir)
    if stored is None:
        return CheckResult(
            "schema_version", Severity.WARN, "No schema version sidecar — run ETL to generate"
        )
    current = compute_schema_hash()
    if stored != current:
        return CheckResult(
            "schema_version",
            Severity.ERROR,
            f"Mismatch: data={stored[:8]}… code={current[:8]}… — re-run ETL or restore snapshot",
        )
    return CheckResult("schema_version", Severity.OK, f"Matches: {current[:8]}…")


def _check_snapshots(snapshot_dir: Path) -> CheckResult:
    if not snapshot_dir.exists():
        return CheckResult("snapshots", Severity.WARN, "Snapshot directory missing")
    snaps = [d for d in snapshot_dir.iterdir() if d.is_dir()]
    if not snaps:
        return CheckResult("snapshots", Severity.WARN, "No snapshots — consider creating one")
    return CheckResult("snapshots", Severity.OK, f"{len(snaps)} snapshot(s) available")


def _check_dossiers(dossier_dir: Path) -> CheckResult:
    if not dossier_dir.exists():
        return CheckResult("dossiers", Severity.OK, "Dossier directory not yet created")
    md_files = list(dossier_dir.rglob("*.md"))
    return CheckResult("dossiers", Severity.OK, f"{len(md_files)} dossier file(s)")


def _check_disk_usage(output_dir: Path) -> CheckResult:
    if not output_dir.exists():
        return CheckResult("disk_usage", Severity.OK, "No data directory")
    total_bytes = sum(f.stat().st_size for f in output_dir.glob("*.parquet"))
    total_mb = total_bytes / (1024 * 1024)
    disk = shutil.disk_usage(output_dir)
    free_mb = disk.free / (1024 * 1024)
    if free_mb < 100:
        return CheckResult(
            "disk_usage",
            Severity.WARN,
            f"Data: {total_mb:.1f} MB, free disk: {free_mb:.0f} MB (low)",
        )
    return CheckResult(
        "disk_usage", Severity.OK, f"Data: {total_mb:.1f} MB, free disk: {free_mb:.0f} MB"
    )
