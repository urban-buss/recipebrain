"""Custom build hook: sync .openclaw/ skills before packaging."""

from __future__ import annotations

import pathlib
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

REPO_ROOT = pathlib.Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / ".openclaw"
DST_DIR = REPO_ROOT / "src" / "recipebrain" / "skills"
SKIP = {"_archive", "__pycache__"}


def _sync_skills() -> None:
    """One-way sync .openclaw/ -> src/recipebrain/skills/."""
    if not SRC_DIR.is_dir():
        return

    DST_DIR.mkdir(parents=True, exist_ok=True)

    readme = SRC_DIR / "README.md"
    if readme.is_file():
        shutil.copy2(readme, DST_DIR / "README.md")

    for child in sorted(SRC_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name in SKIP or child.name.startswith("."):
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.is_file():
            continue
        dst_skill_dir = DST_DIR / child.name
        dst_skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_file, dst_skill_dir / "SKILL.md")


class SyncSkillsBuildPy(build_py):
    """Run skill sync before build_py."""

    def run(self) -> None:
        _sync_skills()
        super().run()


class SyncSkillsSdist(sdist):
    """Run skill sync before sdist."""

    def run(self) -> None:
        _sync_skills()
        super().run()


setup(
    cmdclass={
        "build_py": SyncSkillsBuildPy,
        "sdist": SyncSkillsSdist,
    },
)
