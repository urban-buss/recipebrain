from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_config_pointer(tmp_path, monkeypatch):
    """Prevent the real ~/.config/recipebrain/config-path from interfering."""
    monkeypatch.setattr(
        "recipebrain.settings._CONFIG_PATH_FILE", tmp_path / "no-such" / "config-path"
    )


def test_settings_load_defaults(tmp_path, monkeypatch):
    from pathlib import Path

    from recipebrain.settings import Settings

    # Ensure no config files exist in CWD
    monkeypatch.chdir(tmp_path)
    settings = Settings.load(None)
    assert settings is not None
    assert settings.paths is not None
    # Paths should be absolute (anchored to CWD when no config found)
    assert Path(settings.paths.output_dir).is_absolute()


def test_settings_paths_defaults(tmp_path, monkeypatch):
    from pathlib import Path

    from recipebrain.settings import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings.load(None)
    # All path fields should be absolute
    assert Path(settings.paths.dossier_dir).is_absolute()
    assert Path(settings.paths.inbox_dir).is_absolute()
    assert Path(settings.paths.snapshot_dir).is_absolute()


def test_settings_scraping_defaults(tmp_path, monkeypatch):
    from recipebrain.settings import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings.load(None)
    assert settings.scraping.rate_limit_seconds == 2.0
    assert settings.scraping.respect_robots_txt is True
    assert settings.scraping.timeout_seconds == 30


def test_settings_load_from_file(tmp_path):

    from recipebrain.settings import Settings

    toml_file = tmp_path / "test.toml"
    toml_file.write_text(
        '[paths]\noutput_dir = "custom_output"\n[scraping]\nrate_limit_seconds = 5.0\n'
    )
    settings = Settings.load(toml_file)
    # Relative path anchored to config file's parent directory
    assert settings.paths.output_dir == str((tmp_path / "custom_output").resolve())
    assert settings.scraping.rate_limit_seconds == 5.0


def test_settings_frozen():
    from recipebrain.settings import Settings

    settings = Settings.load(None)
    with pytest.raises(AttributeError):
        settings.paths = None  # type: ignore[misc]
    with pytest.raises(AttributeError):
        settings.paths.output_dir = "x"  # type: ignore[misc]


class TestPathAnchoring:
    """Paths loaded from TOML are anchored to the config file's parent dir."""

    def test_relative_paths_anchored_to_config_parent(self, tmp_path):
        from pathlib import Path

        from recipebrain.settings import Settings

        # Config lives in a subdirectory — relative paths anchor there
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        toml_file = config_dir / "recipebrain.toml"
        toml_file.write_text(
            "[paths]\n"
            'output_dir = "output"\n'
            'dossier_dir = "dossiers/recipes"\n'
            'inbox_dir = "inbox"\n'
            'snapshot_dir = "snapshots"\n'
        )

        settings = Settings.load(toml_file)

        # All paths should be absolute and rooted in the config's parent
        assert Path(settings.paths.output_dir).is_absolute()
        assert settings.paths.output_dir == str((config_dir / "output").resolve())
        assert settings.paths.dossier_dir == str((config_dir / "dossiers" / "recipes").resolve())
        assert settings.paths.inbox_dir == str((config_dir / "inbox").resolve())
        assert settings.paths.snapshot_dir == str((config_dir / "snapshots").resolve())

    def test_absolute_paths_pass_through(self, tmp_path):

        from recipebrain.settings import Settings

        abs_output = str(tmp_path / "abs_output")
        toml_file = tmp_path / "recipebrain.toml"
        # Use forward slashes or escaped backslashes for valid TOML
        toml_value = abs_output.replace("\\", "/")
        toml_file.write_text(f'[paths]\noutput_dir = "{toml_value}"\n')

        settings = Settings.load(toml_file)

        # Absolute path stored as-is (resolved but still pointing to same location)
        assert settings.paths.output_dir == str((tmp_path / "abs_output").resolve())

    def test_cwd_does_not_affect_resolution(self, tmp_path, monkeypatch):

        from recipebrain.settings import Settings

        # Config lives in one dir
        config_dir = tmp_path / "config_home"
        config_dir.mkdir()
        toml_file = config_dir / "recipebrain.toml"
        toml_file.write_text('[paths]\noutput_dir = "data"\n')

        # CWD is somewhere else entirely
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)

        settings = Settings.load(toml_file)

        # Path anchored to config parent, NOT to CWD
        assert settings.paths.output_dir == str((config_dir / "data").resolve())
        assert settings.paths.output_dir != str((other_dir / "data").resolve())

    def test_missing_config_anchors_to_cwd(self, tmp_path, monkeypatch):

        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)
        settings = Settings.load(None)

        # Falls back to CWD-anchored defaults
        assert settings.paths.output_dir == str((tmp_path / "output").resolve())


class TestConfigResolution:
    """Config file resolution: explicit path > env var > local > default."""

    def test_explicit_path_takes_priority(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        # Create both default and local files
        (tmp_path / "recipebrain.toml").write_text("[scraping]\nrate_limit_seconds = 1.0\n")
        (tmp_path / "recipebrain.local.toml").write_text("[scraping]\nrate_limit_seconds = 2.0\n")
        explicit = tmp_path / "custom.toml"
        explicit.write_text("[scraping]\nrate_limit_seconds = 9.0\n")

        settings = Settings.load(explicit)
        assert settings.scraping.rate_limit_seconds == 9.0

    def test_explicit_path_not_found_raises(self, tmp_path):
        from recipebrain.settings import Settings

        with pytest.raises(FileNotFoundError):
            Settings.load(tmp_path / "nonexistent.toml")

    def test_env_var_takes_priority_over_files(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        (tmp_path / "recipebrain.toml").write_text("[scraping]\nrate_limit_seconds = 1.0\n")
        (tmp_path / "recipebrain.local.toml").write_text("[scraping]\nrate_limit_seconds = 2.0\n")
        env_cfg = tmp_path / "env.toml"
        env_cfg.write_text("[scraping]\nrate_limit_seconds = 7.0\n")
        monkeypatch.setenv("RECIPEBRAIN_CONFIG", str(env_cfg))

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 7.0

    def test_env_var_missing_file_raises(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("RECIPEBRAIN_CONFIG", str(tmp_path / "missing.toml"))

        with pytest.raises(FileNotFoundError, match="RECIPEBRAIN_CONFIG"):
            Settings.load(None)

    def test_local_toml_preferred_over_default(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        (tmp_path / "recipebrain.toml").write_text("[scraping]\nrate_limit_seconds = 1.0\n")
        (tmp_path / "recipebrain.local.toml").write_text("[scraping]\nrate_limit_seconds = 5.0\n")

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 5.0

    def test_default_toml_used_when_no_local(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        (tmp_path / "recipebrain.toml").write_text("[scraping]\nrate_limit_seconds = 3.0\n")

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 3.0

    def test_builtin_defaults_when_no_files(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 2.0


class TestConfigPathPointer:
    """User-level config pointer at ~/.config/recipebrain/config-path."""

    def test_pointer_file_used_when_no_cwd_config(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        # Create a config somewhere outside CWD
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = data_dir / "recipebrain.toml"
        cfg.write_text("[scraping]\nrate_limit_seconds = 42.0\n")

        # Write a pointer to it
        fake_user_config = tmp_path / "fake_config_home"
        pointer = fake_user_config / "config-path"
        fake_user_config.mkdir(parents=True)
        pointer.write_text(str(cfg), encoding="utf-8")
        monkeypatch.setattr("recipebrain.settings._CONFIG_PATH_FILE", pointer)

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 42.0

    def test_cwd_config_takes_priority_over_pointer(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        # CWD has a config
        (tmp_path / "recipebrain.toml").write_text("[scraping]\nrate_limit_seconds = 1.0\n")

        # Pointer points elsewhere
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = data_dir / "recipebrain.toml"
        cfg.write_text("[scraping]\nrate_limit_seconds = 99.0\n")
        fake_user_config = tmp_path / "fake_config_home"
        pointer = fake_user_config / "config-path"
        fake_user_config.mkdir(parents=True)
        pointer.write_text(str(cfg), encoding="utf-8")
        monkeypatch.setattr("recipebrain.settings._CONFIG_PATH_FILE", pointer)

        settings = Settings.load(None)
        # CWD config wins
        assert settings.scraping.rate_limit_seconds == 1.0

    def test_pointer_to_missing_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        fake_user_config = tmp_path / "fake_config_home"
        pointer = fake_user_config / "config-path"
        fake_user_config.mkdir(parents=True)
        pointer.write_text(str(tmp_path / "nonexistent.toml"), encoding="utf-8")
        monkeypatch.setattr("recipebrain.settings._CONFIG_PATH_FILE", pointer)

        # Should fall through to defaults, not raise
        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 2.0

    def test_no_pointer_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        # Point at non-existent pointer file
        fake_user_config = tmp_path / "no_such_dir"
        pointer = fake_user_config / "config-path"
        monkeypatch.setattr("recipebrain.settings._CONFIG_PATH_FILE", pointer)

        settings = Settings.load(None)
        assert settings.scraping.rate_limit_seconds == 2.0

    def test_pointer_paths_anchored_to_config_parent(self, tmp_path, monkeypatch):
        """Paths in the pointed-to config resolve relative to its parent."""
        from recipebrain.settings import Settings

        monkeypatch.chdir(tmp_path)

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = data_dir / "recipebrain.toml"
        cfg.write_text('[paths]\noutput_dir = "output"\n')

        fake_user_config = tmp_path / "fake_config_home"
        pointer = fake_user_config / "config-path"
        fake_user_config.mkdir(parents=True)
        pointer.write_text(str(cfg), encoding="utf-8")
        monkeypatch.setattr("recipebrain.settings._CONFIG_PATH_FILE", pointer)

        settings = Settings.load(None)
        assert settings.paths.output_dir == str((data_dir / "output").resolve())
