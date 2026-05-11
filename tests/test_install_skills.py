from __future__ import annotations

import pytest

import recipebrain.skills as skills_mod


@pytest.fixture
def fake_skills_dir(tmp_path, monkeypatch):
    """Create a fake bundled skills directory and patch SKILLS_DIR."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "README.md").write_text("# Bundled Skills")

    for skill in ["tonight", "pantry", "shopping"]:
        skill_dir = skills_dir / skill
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill}\n---\n# {skill}")

    monkeypatch.setattr(skills_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(skills_mod, "SKILL_NAMES", ["tonight", "pantry", "shopping"])
    return skills_dir


def test_install_to_target(tmp_path, fake_skills_dir):
    """Test installing skills to a custom target directory."""
    from recipebrain.install_skills import install

    target = tmp_path / "install_target"
    count = install(target=target)
    assert count > 0
    # Check SKILL.md files were copied
    skill_files = list(target.rglob("SKILL.md"))
    assert len(skill_files) == 3


def test_install_copies_readme(tmp_path, fake_skills_dir):
    """Test that README.md is copied."""
    from recipebrain.install_skills import install

    target = tmp_path / "install_target"
    install(target=target)
    assert (target / "README.md").exists()
    assert (target / "README.md").read_text() == "# Bundled Skills"


def test_install_no_overwrite_without_force(tmp_path, fake_skills_dir):
    """Test that existing files are not overwritten without --force."""
    from recipebrain.install_skills import install

    target = tmp_path / "install_target"

    # First install
    count1 = install(target=target, force=False)
    assert count1 > 0

    # Write custom content to an installed file
    tonight_skill = target / "tonight" / "SKILL.md"
    tonight_skill.write_text("custom content")

    # Second install without force — should not overwrite
    count2 = install(target=target, force=False)
    assert count2 == 0
    assert tonight_skill.read_text() == "custom content"


def test_install_with_force_overwrites(tmp_path, fake_skills_dir):
    """Test that --force overwrites existing files."""
    from recipebrain.install_skills import install

    target = tmp_path / "install_target"

    # First install
    install(target=target)
    tonight_skill = target / "tonight" / "SKILL.md"
    tonight_skill.write_text("custom content")

    # Force install — should overwrite
    count = install(target=target, force=True)
    assert count > 0
    assert tonight_skill.read_text() != "custom content"


def test_install_returns_negative_when_no_skills(tmp_path, monkeypatch):
    """Test that install returns -1 when no bundled skills exist."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", empty_dir)

    from recipebrain.install_skills import install

    target = tmp_path / "install_target"
    count = install(target=target)
    assert count == -1
