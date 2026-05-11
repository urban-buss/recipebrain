"""Tests for recipebrain.snapshot — backup and restore."""

from __future__ import annotations

from pathlib import Path

import pytest

from recipebrain.snapshot import (
    _parse_timestamp,
    create_snapshot,
    list_snapshots,
    restore_snapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_parquet_files(directory: Path, names: list[str] | None = None) -> list[Path]:
    """Create dummy .parquet files for testing."""
    directory.mkdir(parents=True, exist_ok=True)
    file_names = names or ["recipes.parquet", "recipe_ingredients.parquet"]
    paths = []
    for name in file_names:
        p = directory / name
        p.write_bytes(b"PAR1dummy")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# TestCreateSnapshot
# ---------------------------------------------------------------------------


class TestCreateSnapshot:
    def test_creates_snapshot_dir(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        result = create_snapshot(output, snaps, label="pre-etl")
        assert result is not None
        assert result.exists()
        assert "pre-etl" in result.name

    def test_copies_parquet_files(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        result = create_snapshot(output, snaps)
        assert result is not None
        files = list(result.glob("*.parquet"))
        assert len(files) == 2

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        output.mkdir()
        snaps = tmp_path / "snapshots"
        result = create_snapshot(output, snaps)
        assert result is None

    def test_unique_names(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        r1 = create_snapshot(output, snaps, label="first")
        r2 = create_snapshot(output, snaps, label="second")
        assert r1 is not None
        assert r2 is not None
        assert r1.name != r2.name


# ---------------------------------------------------------------------------
# TestListSnapshots
# ---------------------------------------------------------------------------


class TestListSnapshots:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert list_snapshots(tmp_path / "nonexistent") == []

    def test_lists_snapshots(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        create_snapshot(output, snaps, label="first")
        create_snapshot(output, snaps, label="second")
        result = list_snapshots(snaps)
        assert len(result) == 2
        assert all("name" in s for s in result)
        assert all("file_count" in s for s in result)

    def test_sorted_most_recent_first(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        create_snapshot(output, snaps, label="aaa")
        create_snapshot(output, snaps, label="zzz")
        result = list_snapshots(snaps)
        # Most recent (zzz) should come first since names are timestamp-based
        assert result[0]["name"] > result[1]["name"]


# ---------------------------------------------------------------------------
# TestRestoreSnapshot
# ---------------------------------------------------------------------------


class TestRestoreSnapshot:
    def test_restores_files(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        snaps = tmp_path / "snapshots"
        _create_parquet_files(output)
        snap = create_snapshot(output, snaps, label="backup")
        assert snap is not None

        # Delete original
        for f in output.glob("*.parquet"):
            f.unlink()
        assert len(list(output.glob("*.parquet"))) == 0

        # Restore
        count = restore_snapshot(snap, output)
        assert count == 2
        assert len(list(output.glob("*.parquet"))) == 2

    def test_missing_snapshot_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            restore_snapshot(tmp_path / "nonexistent", tmp_path / "output")

    def test_empty_snapshot(self, tmp_path: Path) -> None:
        snap = tmp_path / "empty_snap"
        snap.mkdir()
        count = restore_snapshot(snap, tmp_path / "output")
        assert count == 0


# ---------------------------------------------------------------------------
# TestParseTimestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_valid_name(self) -> None:
        assert _parse_timestamp("20240601_120000_pre-etl") == "2024-06-01T12:00:00"

    def test_no_label(self) -> None:
        assert _parse_timestamp("20240601_120000") == "2024-06-01T12:00:00"

    def test_invalid(self) -> None:
        assert _parse_timestamp("not-a-timestamp") is None
