"""Tests for recipebrain.init — data directory scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest

from recipebrain.init import InitResult, init_data_dir


class TestInitDataDir:
    """Happy-path and edge-case tests for init_data_dir()."""

    def test_creates_fresh_directory(self, tmp_path: Path):
        target = tmp_path / "mydata"
        result = init_data_dir(target)

        assert isinstance(result, InitResult)
        assert result.root == target.resolve()
        assert result.config_written is True
        assert result.config_path == target.resolve() / "recipebrain.toml"
        assert result.config_path.exists()

        for subdir in ["output", "dossiers/recipes", "inbox", "snapshots"]:
            assert (target / subdir).is_dir()

    def test_config_is_valid_toml(self, tmp_path: Path):
        import tomllib

        target = tmp_path / "data"
        init_data_dir(target)
        text = (target / "recipebrain.toml").read_text(encoding="utf-8")
        parsed = tomllib.loads(text)
        assert parsed["paths"]["output_dir"] == "output"
        assert parsed["paths"]["dossier_dir"] == "dossiers/recipes"
        assert parsed["paths"]["inbox_dir"] == "inbox"
        assert parsed["paths"]["snapshot_dir"] == "snapshots"

    def test_existing_dir_is_ok(self, tmp_path: Path):
        target = tmp_path / "existing"
        target.mkdir()
        result = init_data_dir(target)
        assert result.root == target.resolve()
        assert result.config_written is True

    def test_subdirs_already_exist(self, tmp_path: Path):
        target = tmp_path / "partial"
        target.mkdir()
        (target / "output").mkdir()
        (target / "inbox").mkdir()

        result = init_data_dir(target)

        # Pre-existing dirs should NOT appear in dirs_created
        created_names = {d.name for d in result.dirs_created}
        assert "output" not in created_names
        assert "inbox" not in created_names
        # But missing ones should
        assert "snapshots" in created_names

    def test_existing_toml_without_force_raises(self, tmp_path: Path):
        target = tmp_path / "hasconfig"
        target.mkdir()
        (target / "recipebrain.toml").write_text("# old", encoding="utf-8")

        with pytest.raises(FileExistsError, match="already exists"):
            init_data_dir(target)

    def test_existing_toml_with_force_overwrites(self, tmp_path: Path):
        target = tmp_path / "overwrite"
        target.mkdir()
        (target / "recipebrain.toml").write_text("# old", encoding="utf-8")

        result = init_data_dir(target, force=True)
        assert result.config_written is True
        content = result.config_path.read_text(encoding="utf-8")
        assert "[paths]" in content
        assert "# old" not in content

    def test_path_is_file_raises(self, tmp_path: Path):
        blocker = tmp_path / "notadir"
        blocker.write_text("oops", encoding="utf-8")

        with pytest.raises(FileExistsError, match="not a directory"):
            init_data_dir(blocker)

    def test_nested_path_creates_parents(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c"
        result = init_data_dir(target)
        assert target.is_dir()
        assert result.config_path.exists()


class TestCmdInit:
    """Integration tests for the CLI init subcommand."""

    def test_init_in_help(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "recipebrain", "--help"],
            capture_output=True,
            text=True,
        )
        assert "init" in result.stdout

    def test_init_fresh_dir(self, tmp_path: Path):
        import argparse

        from recipebrain.cli import _cmd_init

        target = tmp_path / "fresh"
        args = argparse.Namespace(path=str(target), force=False)
        rc = _cmd_init(args)
        assert rc == 0
        assert (target / "recipebrain.toml").exists()

    def test_init_existing_toml_fails(self, tmp_path: Path):
        import argparse

        from recipebrain.cli import _cmd_init

        target = tmp_path / "existing"
        target.mkdir()
        (target / "recipebrain.toml").write_text("# old", encoding="utf-8")

        args = argparse.Namespace(path=str(target), force=False)
        rc = _cmd_init(args)
        assert rc == 1

    def test_init_existing_toml_force(self, tmp_path: Path):
        import argparse

        from recipebrain.cli import _cmd_init

        target = tmp_path / "forced"
        target.mkdir()
        (target / "recipebrain.toml").write_text("# old", encoding="utf-8")

        args = argparse.Namespace(path=str(target), force=True)
        rc = _cmd_init(args)
        assert rc == 0
        content = (target / "recipebrain.toml").read_text(encoding="utf-8")
        assert "[paths]" in content
