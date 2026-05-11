"""Install bundled OpenClaw skills to the user's skills directory.

Usage (CLI):
    recipebrain install-skills [--target DIR] [--force]

Usage (Python):
    from recipebrain.install_skills import install
    installed = install(target=Path("~/.openclaw/skills/recipebrain/"), force=True)
"""

from __future__ import annotations

from pathlib import Path


def _default_target() -> Path:
    return Path.home() / ".openclaw" / "skills" / "recipebrain"


def install(target: Path | None = None, force: bool = False) -> int:
    """Copy bundled skill files to target directory.

    Returns the number of files copied, or -1 if no bundled skills found.
    """
    from recipebrain.skills import SKILL_NAMES, SKILLS_DIR, install_skills

    if target is None:
        target = _default_target()

    # Check that bundled skills exist (at least one SKILL.md present)
    has_skills = any((SKILLS_DIR / name / "SKILL.md").is_file() for name in SKILL_NAMES)
    if not has_skills:
        print(
            "No bundled skills found. Run `python .github/tools/sync-skills.py` first, "
            "or install the published wheel."
        )
        return -1

    installed = install_skills(target, force=force)
    return len(installed)
