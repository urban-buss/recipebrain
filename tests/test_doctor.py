"""Tests for recipebrain.doctor — health check system."""

from __future__ import annotations

from recipebrain.doctor import DoctorReport, Severity, run_doctor
from recipebrain.writer import write_schema_version, write_table


class TestRunDoctor:
    def test_all_ok_with_data(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()
        dossiers = tmp_path / "dossiers"
        dossiers.mkdir()

        write_table("sources", [{"id": 1, "key": "fooby"}], output)
        write_table("recipes", [{"id": 1, "title": "X"}], output)
        write_schema_version(output)
        (snapshots / "20250101_000000_test").mkdir()

        report = run_doctor(output, snapshots, dossiers)
        assert _has_check(report, "output_dir", Severity.OK)
        assert _has_check(report, "schema_version", Severity.OK)

    def test_missing_output_dir(self, tmp_path):
        report = run_doctor(tmp_path / "missing", tmp_path / "snapshots", tmp_path / "dossiers")
        assert _has_check(report, "output_dir", Severity.ERROR)
        assert not report.ok

    def test_no_parquet_files(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        report = run_doctor(output, tmp_path / "snapshots", tmp_path / "dossiers")
        assert _has_check(report, "parquet_files", Severity.WARN)

    def test_schema_mismatch(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        import json

        (output / ".schema_version.json").write_text(
            json.dumps({"schema_hash": "stale", "entity_count": 14}),
            encoding="utf-8",
        )
        report = run_doctor(output, tmp_path / "snapshots", tmp_path / "dossiers")
        assert _has_check(report, "schema_version", Severity.ERROR)

    def test_no_snapshots(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        report = run_doctor(output, tmp_path / "snapshots", tmp_path / "dossiers")
        assert _has_check(report, "snapshots", Severity.WARN)

    def test_dossier_counting(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        dossiers = tmp_path / "dossiers"
        dossiers.mkdir()
        (dossiers / "recipe.md").write_text("# Test", encoding="utf-8")
        report = run_doctor(output, tmp_path / "snapshots", dossiers)
        check = _find_check(report, "dossiers")
        assert check is not None
        assert "1 dossier" in check.message


class TestDoctorReport:
    def test_ok_when_all_ok(self):
        report = DoctorReport(
            checks=[
                _make_check("a", Severity.OK),
                _make_check("b", Severity.OK),
            ]
        )
        assert report.ok

    def test_not_ok_with_error(self):
        report = DoctorReport(
            checks=[
                _make_check("a", Severity.OK),
                _make_check("b", Severity.ERROR),
            ]
        )
        assert not report.ok
        assert report.worst == Severity.ERROR

    def test_worst_is_warn(self):
        report = DoctorReport(
            checks=[
                _make_check("a", Severity.OK),
                _make_check("b", Severity.WARN),
            ]
        )
        assert report.worst == Severity.WARN


# Helpers


def _make_check(name: str, severity: Severity) -> object:
    from recipebrain.doctor import CheckResult

    return CheckResult(name=name, severity=severity, message="test")


def _has_check(report: DoctorReport, name: str, severity: Severity) -> bool:
    return any(c.name == name and c.severity == severity for c in report.checks)


def _find_check(report: DoctorReport, name: str):
    return next((c for c in report.checks if c.name == name), None)
