from __future__ import annotations

import subprocess
import sys


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
    assert "0.0.1" in result.stdout


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
