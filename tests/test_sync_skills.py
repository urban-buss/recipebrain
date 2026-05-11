from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def skills_source(tmp_path):
    """Create a fake .openclaw/ directory with skills."""
    openclaw = tmp_path / ".openclaw"
    openclaw.mkdir()
    (openclaw / "README.md").write_text("# Skills README")

    for skill in ["tonight", "pantry", "shopping"]:
        skill_dir = openclaw / skill
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill}\n---\n# {skill}")

    # _archive should be skipped
    archive = openclaw / "_archive"
    archive.mkdir()
    (archive / "SKILL.md").write_text("should be skipped")

    # hidden dir should be skipped
    hidden = openclaw / ".hidden"
    hidden.mkdir()
    (hidden / "SKILL.md").write_text("should be skipped")

    return openclaw


@pytest.fixture
def skills_dest(tmp_path):
    """Target directory for synced skills."""
    dst = tmp_path / "skills"
    dst.mkdir()
    return dst


def test_sync_copies_readme(skills_source, skills_dest, monkeypatch):
    import importlib

    # Load the sync script as a module
    script_path = Path(__file__).parent.parent / ".github" / "tools" / "sync-skills.py"
    spec = importlib.util.spec_from_file_location("sync_skills_script", script_path)
    mod = importlib.util.module_from_spec(spec)

    # Monkeypatch the module-level constants before exec
    monkeypatch.setattr(mod, "__name__", "sync_skills_script")
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SRC_DIR", skills_source)
    monkeypatch.setattr(mod, "DST_DIR", skills_dest)

    mod.sync()

    assert (skills_dest / "README.md").exists()
    assert (skills_dest / "README.md").read_text() == "# Skills README"


def test_sync_copies_skill_files(skills_source, skills_dest, monkeypatch):
    import importlib

    script_path = Path(__file__).parent.parent / ".github" / "tools" / "sync-skills.py"
    spec = importlib.util.spec_from_file_location("sync_skills_script", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SRC_DIR", skills_source)
    monkeypatch.setattr(mod, "DST_DIR", skills_dest)

    mod.sync()

    for skill in ["tonight", "pantry", "shopping"]:
        assert (skills_dest / skill / "SKILL.md").exists()


def test_sync_skips_archive(skills_source, skills_dest, monkeypatch):
    import importlib

    script_path = Path(__file__).parent.parent / ".github" / "tools" / "sync-skills.py"
    spec = importlib.util.spec_from_file_location("sync_skills_script", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SRC_DIR", skills_source)
    monkeypatch.setattr(mod, "DST_DIR", skills_dest)

    mod.sync()

    assert not (skills_dest / "_archive").exists()


def test_sync_skips_hidden(skills_source, skills_dest, monkeypatch):
    import importlib

    script_path = Path(__file__).parent.parent / ".github" / "tools" / "sync-skills.py"
    spec = importlib.util.spec_from_file_location("sync_skills_script", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SRC_DIR", skills_source)
    monkeypatch.setattr(mod, "DST_DIR", skills_dest)

    mod.sync()

    assert not (skills_dest / ".hidden").exists()


def test_sync_idempotent(skills_source, skills_dest, monkeypatch):
    import importlib

    script_path = Path(__file__).parent.parent / ".github" / "tools" / "sync-skills.py"
    spec = importlib.util.spec_from_file_location("sync_skills_script", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SRC_DIR", skills_source)
    monkeypatch.setattr(mod, "DST_DIR", skills_dest)

    # Run twice — no errors
    mod.sync()
    mod.sync()

    for skill in ["tonight", "pantry", "shopping"]:
        assert (skills_dest / skill / "SKILL.md").exists()
