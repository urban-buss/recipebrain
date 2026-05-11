"""Tests for recipebrain.info — system information report."""

from __future__ import annotations

from recipebrain import __version__
from recipebrain.info import InfoReport, format_info, gather_info
from recipebrain.writer import SCHEMAS, write_table


class TestGatherInfo:
    def test_basic_report(self, tmp_path):
        report = gather_info(tmp_path)
        assert report.version == __version__
        assert report.python_version
        assert report.parquet_entities == len(SCHEMAS)
        assert report.parquet_files_present == 0

    def test_counts_present_files(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        write_table("recipes", [{"id": 1, "title": "X"}], tmp_path)
        report = gather_info(tmp_path)
        assert report.parquet_files_present == 2
        assert report.total_data_mb > 0

    def test_handles_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        report = gather_info(missing)
        assert report.parquet_files_present == 0
        assert report.total_data_mb == 0.0


class TestFormatInfo:
    def test_contains_version(self):
        report = InfoReport(
            version="1.2.3",
            python_version="3.12.0",
            platform="test",
            output_dir="/tmp",
            parquet_entities=14,
            parquet_files_present=5,
            total_data_mb=1.5,
            schema_count=14,
        )
        text = format_info(report)
        assert "1.2.3" in text
        assert "3.12.0" in text
        assert "5/14" in text
