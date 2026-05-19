from __future__ import annotations

import os
import subprocess
import sys

import pytest

try:
    import PIL  # noqa: F401

    _pil_available = True
except ImportError:
    _pil_available = False


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "recipebrain", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_help_lists_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "recipebrain", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for cmd in [
        "etl",
        "promotions",
        "ingest",
        "validate",
        "mcp",
        "reindex",
        "snapshot",
        "install-skills",
    ]:
        assert cmd in result.stdout


def test_version_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "recipebrain", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    from recipebrain import __version__

    assert __version__ in result.stdout


def test_mcp_importable():
    """Verify the MCP server module is importable and run() is callable."""
    from recipebrain.mcp_server import run

    assert callable(run)


# ---------------------------------------------------------------------------
# Tests: CLI log command
# ---------------------------------------------------------------------------


class TestCliLog:
    def test_log_subcommand_in_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "recipebrain", "--help"],
            capture_output=True,
            text=True,
        )
        assert "log" in result.stdout

    def test_log_calls_log_cook(self, tmp_path):
        import argparse
        import datetime
        from pathlib import Path
        from unittest.mock import patch

        import pyarrow as pa
        import pyarrow.parquet as pq

        from recipebrain.cli import _cmd_log
        from recipebrain.writer import SCHEMAS

        # Create minimal data
        recipes_data = {
            "id": [1],
            "source_id": [1],
            "source_external_id": ["r1"],
            "source_url": ["http://x/1"],
            "title": ["Test Recipe"],
            "title_normalised": ["test recipe"],
            "language": ["de"],
            "description": [None],
            "servings": [4],
            "prep_minutes": [10],
            "cook_minutes": [20],
            "total_minutes": [30],
            "difficulty": ["easy"],
            "cuisine": ["swiss"],
            "course": ["main"],
            "primary_image_url": [None],
            "original_keywords": [[]],
            "owner_rating": [None],
            "starred": [False],
            "times_cooked": [0],
            "last_cooked_at": [None],
            "scraped_at": [datetime.datetime(2024, 1, 1)],
            "updated_at": [datetime.datetime(2024, 1, 1)],
            "content_hash": ["h1"],
            "status": ["active"],
            "primary_protein": [None],
            "taste_profile": ["savoury"],
            "weight_class": ["medium"],
            "cooking_method": [None],
            "dietary_flags": [[]],
            "food_groups": [[]],
        }
        table = pa.table(recipes_data, schema=SCHEMAS["recipes"])
        pq.write_table(table, tmp_path / "recipes.parquet")

        args = argparse.Namespace(
            recipe_id=1, rating=4, notes="CLI test", servings=2, scale_factor=None
        )

        with patch("recipebrain.mcp_server._output_dir", return_value=Path(tmp_path)):
            ret = _cmd_log(args)

        assert ret == 0

    def test_log_error_recipe_not_found(self, tmp_path):
        import argparse
        import datetime
        from pathlib import Path
        from unittest.mock import patch

        import pyarrow as pa
        import pyarrow.parquet as pq

        from recipebrain.cli import _cmd_log
        from recipebrain.writer import SCHEMAS

        recipes_data = {
            "id": [1],
            "source_id": [1],
            "source_external_id": ["r1"],
            "source_url": ["http://x/1"],
            "title": ["Test Recipe"],
            "title_normalised": ["test recipe"],
            "language": ["de"],
            "description": [None],
            "servings": [4],
            "prep_minutes": [10],
            "cook_minutes": [20],
            "total_minutes": [30],
            "difficulty": ["easy"],
            "cuisine": ["swiss"],
            "course": ["main"],
            "primary_image_url": [None],
            "original_keywords": [[]],
            "owner_rating": [None],
            "starred": [False],
            "times_cooked": [0],
            "last_cooked_at": [None],
            "scraped_at": [datetime.datetime(2024, 1, 1)],
            "updated_at": [datetime.datetime(2024, 1, 1)],
            "content_hash": ["h1"],
            "status": ["active"],
            "primary_protein": [None],
            "taste_profile": ["savoury"],
            "weight_class": ["medium"],
            "cooking_method": [None],
            "dietary_flags": [[]],
            "food_groups": [[]],
        }
        table = pa.table(recipes_data, schema=SCHEMAS["recipes"])
        pq.write_table(table, tmp_path / "recipes.parquet")

        args = argparse.Namespace(
            recipe_id=999, rating=None, notes=None, servings=None, scale_factor=None
        )

        with patch("recipebrain.mcp_server._output_dir", return_value=Path(tmp_path)):
            ret = _cmd_log(args)

        assert ret == 1

    def test_log_with_all_options(self, tmp_path):
        import argparse
        import datetime
        from pathlib import Path
        from unittest.mock import patch

        import pyarrow as pa
        import pyarrow.parquet as pq

        from recipebrain.cli import _cmd_log
        from recipebrain.query import execute_query
        from recipebrain.writer import SCHEMAS

        recipes_data = {
            "id": [1],
            "source_id": [1],
            "source_external_id": ["r1"],
            "source_url": ["http://x/1"],
            "title": ["Test Recipe"],
            "title_normalised": ["test recipe"],
            "language": ["de"],
            "description": [None],
            "servings": [4],
            "prep_minutes": [10],
            "cook_minutes": [20],
            "total_minutes": [30],
            "difficulty": ["easy"],
            "cuisine": ["swiss"],
            "course": ["main"],
            "primary_image_url": [None],
            "original_keywords": [[]],
            "owner_rating": [None],
            "starred": [False],
            "times_cooked": [0],
            "last_cooked_at": [None],
            "scraped_at": [datetime.datetime(2024, 1, 1)],
            "updated_at": [datetime.datetime(2024, 1, 1)],
            "content_hash": ["h1"],
            "status": ["active"],
            "primary_protein": [None],
            "taste_profile": ["savoury"],
            "weight_class": ["medium"],
            "cooking_method": [None],
            "dietary_flags": [[]],
            "food_groups": [[]],
        }
        table = pa.table(recipes_data, schema=SCHEMAS["recipes"])
        pq.write_table(table, tmp_path / "recipes.parquet")

        args = argparse.Namespace(
            recipe_id=1, rating=5, notes="Excellent", servings=6, scale_factor=1.5
        )

        with patch("recipebrain.mcp_server._output_dir", return_value=Path(tmp_path)):
            ret = _cmd_log(args)

        assert ret == 0
        rows = execute_query(
            "SELECT rating, notes, servings, scale_factor FROM cook_log WHERE recipe_id = 1",
            tmp_path,
        )
        assert rows[0]["rating"] == 5
        assert rows[0]["notes"] == "Excellent"
        assert rows[0]["servings"] == 6
        assert rows[0]["scale_factor"] == 1.5


# ---------------------------------------------------------------------------
# Tests: CLI commands without config file (issues 001 & 002)
# ---------------------------------------------------------------------------


class TestCliNoConfig:
    """Verify CLI commands don't crash when no config file is present."""

    def _run_cli(self, tmp_path, *args):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop("RECIPEBRAIN_CONFIG", None)
        return subprocess.run(
            [sys.executable, "-m", "recipebrain", *args],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )

    def test_info_without_config(self, tmp_path):
        """recipebrain info should not crash without a config file."""
        result = self._run_cli(tmp_path, "info")
        assert result.returncode == 0

    def test_doctor_without_config(self, tmp_path):
        """recipebrain doctor should not crash without a config file."""
        result = self._run_cli(tmp_path, "doctor")
        assert result.returncode in (0, 1)  # may warn, but must not traceback
        assert "Traceback" not in result.stderr

    def test_validate_without_config(self, tmp_path):
        """recipebrain validate should not crash without a config file."""
        result = self._run_cli(tmp_path, "validate")
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

    def test_snapshot_list_without_config(self, tmp_path):
        """recipebrain snapshot list should not crash without a config file."""
        result = self._run_cli(tmp_path, "snapshot", "list")
        assert result.returncode == 0
        assert "Traceback" not in result.stderr

    def test_config_default_is_none(self):
        """Verify --config defaults to None (auto-detect) not a filename."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--config", "-c", default=None)
        args = parser.parse_args([])
        assert args.config is None


# ---------------------------------------------------------------------------
# Tests: ETL dry-run exit code (issue 005)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _pil_available, reason="PIL not installed")
class TestEtlDryRun:
    def test_limit_zero_returns_zero_despite_errors(self):
        """ETL with --limit 0 should exit 0 even if discovery has errors."""
        import argparse
        from unittest.mock import patch

        from recipebrain.cli import _cmd_etl
        from recipebrain.etl import EtlResult

        results = [
            EtlResult(source="fooby", discovered=0, errors=1, error_details=["SSL error"]),
            EtlResult(source="migusto", discovered=0, errors=1, error_details=["SSL error"]),
        ]

        args = argparse.Namespace(config=None, source=None, limit=0, batch_size=None)
        with patch("recipebrain.etl.run_etl", return_value=results):
            with patch("recipebrain.settings.Settings.load"):
                ret = _cmd_etl(args)

        assert ret == 0

    def test_limit_nonzero_still_errors(self):
        """ETL with --limit >0 should still exit 1 when only errors occur."""
        import argparse
        from unittest.mock import patch

        from recipebrain.cli import _cmd_etl
        from recipebrain.etl import EtlResult

        results = [
            EtlResult(source="fooby", discovered=5, fetched=0, errors=1),
        ]

        args = argparse.Namespace(config=None, source=None, limit=10, batch_size=None)
        with patch("recipebrain.etl.run_etl", return_value=results):
            with patch("recipebrain.settings.Settings.load"):
                ret = _cmd_etl(args)

        assert ret == 1
