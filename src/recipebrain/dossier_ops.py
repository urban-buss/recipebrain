"""Recipe dossier operations: path resolution, read/write, section management.

Provides safe path handling for per-recipe Markdown dossier files. Each recipe
gets a Markdown file in the dossier directory. Sections within a dossier can
be read and updated individually, with protected sections guarded against
accidental modification.

Adapted from cellarbrain/dossier_ops pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

from recipebrain.exceptions import ProtectedSectionError, RecipeNotFoundError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sections that can be read/written via MCP tools
ALLOWED_SECTIONS = frozenset(
    {
        "notes",
        "cook_log",
        "tags",
        "pairings",
        "variations",
    }
)

# Sections that cannot be modified via the MCP interface
PROTECTED_SECTIONS = frozenset(
    {
        "ingredients",
        "steps",
        "metadata",
        "source",
    }
)

_SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def resolve_dossier_path(
    recipe_id: int | str,
    dossier_dir: Path,
) -> Path:
    """Resolve the dossier file path for a recipe, preventing path traversal.

    Args:
        recipe_id: Recipe identifier (used as filename stem).
        dossier_dir: Base directory for dossier files.

    Returns:
        Absolute path to the dossier Markdown file.

    Raises:
        ValueError: If the resolved path escapes the dossier directory.
    """
    # Sanitise: only allow alphanumeric, hyphens, underscores
    safe_id = str(recipe_id).strip()
    if not safe_id or not re.match(r"^[\w-]+$", safe_id):
        raise ValueError(f"Invalid recipe_id for dossier path: {recipe_id!r}")

    resolved = (dossier_dir / f"{safe_id}.md").resolve()
    base = dossier_dir.resolve()

    if not resolved.is_relative_to(base):
        raise ValueError(f"Path traversal detected: {recipe_id!r}")

    return resolved


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def read_dossier(recipe_id: int | str, dossier_dir: Path) -> str:
    """Read the full Markdown dossier for a recipe.

    Args:
        recipe_id: Recipe identifier.
        dossier_dir: Base directory for dossiers.

    Returns:
        The full Markdown content.

    Raises:
        RecipeNotFoundError: If the dossier file does not exist.
    """
    path = resolve_dossier_path(recipe_id, dossier_dir)
    if not path.exists():
        raise RecipeNotFoundError(f"No dossier found for recipe {recipe_id}")
    return path.read_text(encoding="utf-8")


def read_section(recipe_id: int | str, section: str, dossier_dir: Path) -> str | None:
    """Read a specific section from a recipe dossier.

    Sections are delimited by `## Section Name` headers. Returns the content
    between the section header and the next section header (or end of file).

    Args:
        recipe_id: Recipe identifier.
        section: Section name (case-insensitive match).
        dossier_dir: Base directory for dossiers.

    Returns:
        Section content (without the header), or None if section not found.

    Raises:
        RecipeNotFoundError: If the dossier file does not exist.
    """
    content = read_dossier(recipe_id, dossier_dir)
    return _extract_section(content, section)


def list_sections(recipe_id: int | str, dossier_dir: Path) -> list[str]:
    """List all section names in a recipe dossier.

    Returns:
        List of section header names.

    Raises:
        RecipeNotFoundError: If the dossier file does not exist.
    """
    content = read_dossier(recipe_id, dossier_dir)
    return _SECTION_PATTERN.findall(content)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def write_dossier(recipe_id: int | str, content: str, dossier_dir: Path) -> Path:
    """Write a full Markdown dossier for a recipe.

    Creates the dossier directory and file if they don't exist.

    Args:
        recipe_id: Recipe identifier.
        content: Full Markdown content to write.
        dossier_dir: Base directory for dossiers.

    Returns:
        Path to the written file.
    """
    path = resolve_dossier_path(recipe_id, dossier_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def update_section(
    recipe_id: int | str,
    section: str,
    new_content: str,
    dossier_dir: Path,
) -> Path:
    """Update a specific section in a recipe dossier.

    Replaces the content of the named section. If the section doesn't exist,
    appends it to the end of the file.

    Args:
        recipe_id: Recipe identifier.
        section: Section name to update.
        new_content: New content for the section (without header).
        dossier_dir: Base directory for dossiers.

    Returns:
        Path to the updated file.

    Raises:
        RecipeNotFoundError: If the dossier doesn't exist.
        ProtectedSectionError: If the section is protected.
    """
    normalised = section.strip().lower()
    if normalised in PROTECTED_SECTIONS:
        raise ProtectedSectionError(
            f"Section '{section}' is protected and cannot be modified via this interface."
        )

    content = read_dossier(recipe_id, dossier_dir)
    updated = _replace_section(content, section, new_content)
    return write_dossier(recipe_id, updated, dossier_dir)


def append_to_section(
    recipe_id: int | str,
    section: str,
    text: str,
    dossier_dir: Path,
) -> Path:
    """Append text to a section in a recipe dossier.

    If the section doesn't exist, creates it with the given text.

    Args:
        recipe_id: Recipe identifier.
        section: Section name to append to.
        text: Text to append.
        dossier_dir: Base directory for dossiers.

    Returns:
        Path to the updated file.

    Raises:
        RecipeNotFoundError: If the dossier doesn't exist.
        ProtectedSectionError: If the section is protected.
    """
    normalised = section.strip().lower()
    if normalised in PROTECTED_SECTIONS:
        raise ProtectedSectionError(
            f"Section '{section}' is protected and cannot be modified via this interface."
        )

    content = read_dossier(recipe_id, dossier_dir)
    existing = _extract_section(content, section)

    if existing is None:
        # Append new section at end
        new_content = f"\n\n## {section}\n\n{text}\n"
        updated = content.rstrip() + new_content
    else:
        # Append to existing section
        new_section_content = existing.rstrip() + "\n" + text + "\n"
        updated = _replace_section(content, section, new_section_content)

    return write_dossier(recipe_id, updated, dossier_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_section(content: str, section: str) -> str | None:
    """Extract section content between its header and the next header/EOF."""
    lines = content.split("\n")
    target = section.strip().lower()
    start_idx = None

    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.+)$", line)
        if m and m.group(1).strip().lower() == target:
            start_idx = i + 1
            break

    if start_idx is None:
        return None

    # Find end (next ## header or end of file)
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if re.match(r"^##\s+", lines[i]):
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx])


def _replace_section(content: str, section: str, new_content: str) -> str:
    """Replace section content, or append section if not found."""
    lines = content.split("\n")
    target = section.strip().lower()
    start_idx = None

    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.+)$", line)
        if m and m.group(1).strip().lower() == target:
            start_idx = i
            break

    if start_idx is None:
        # Section doesn't exist — append
        return content.rstrip() + f"\n\n## {section}\n\n{new_content.strip()}\n"

    # Find end of section
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if re.match(r"^##\s+", lines[i]):
            end_idx = i
            break

    # Rebuild: before + header + new content + after
    before = lines[:start_idx]
    header = lines[start_idx]
    after = lines[end_idx:]

    rebuilt = before + [header] + [new_content.strip()] + [""] + after
    return "\n".join(rebuilt)
