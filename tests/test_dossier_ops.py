"""Tests for dossier_ops module."""

from __future__ import annotations

from pathlib import Path

import pytest

from recipebrain.dossier_ops import (
    ALLOWED_SECTIONS,
    PROTECTED_SECTIONS,
    append_to_section,
    list_sections,
    read_dossier,
    read_section,
    resolve_dossier_path,
    update_section,
    write_dossier,
)
from recipebrain.exceptions import ProtectedSectionError, RecipeNotFoundError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_DOSSIER = """\
# Zürcher Geschnetzeltes

A classic Zurich dish.

## Metadata

- Source: fooby.ch
- ID: 42

## Ingredients

- 400g Kalbsgeschnetzeltes
- 2 dl Rahm
- 1 Zwiebel

## Steps

1. Fleisch anbraten
2. Rahm dazugeben

## Notes

Great with Rösti as a side dish.

## Cook Log

- 2024-01-15: Made for dinner, rating 5/5
"""


@pytest.fixture()
def dossier_dir(tmp_path: Path) -> Path:
    """Create a temp dossier directory with a sample dossier."""
    d = tmp_path / "dossiers" / "recipes"
    d.mkdir(parents=True)
    (d / "42.md").write_text(_SAMPLE_DOSSIER, encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Tests: resolve_dossier_path
# ---------------------------------------------------------------------------


class TestResolveDossierPath:
    def test_valid_integer_id(self, tmp_path: Path) -> None:
        result = resolve_dossier_path(42, tmp_path)
        assert result == (tmp_path / "42.md").resolve()

    def test_valid_string_id(self, tmp_path: Path) -> None:
        result = resolve_dossier_path("my-recipe-123", tmp_path)
        assert result.name == "my-recipe-123.md"

    def test_path_traversal_dots(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid recipe_id"):
            resolve_dossier_path("../../../etc/passwd", tmp_path)

    def test_path_traversal_slash(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid recipe_id"):
            resolve_dossier_path("foo/bar", tmp_path)

    def test_empty_id(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid recipe_id"):
            resolve_dossier_path("", tmp_path)

    def test_whitespace_id(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid recipe_id"):
            resolve_dossier_path("   ", tmp_path)

    def test_id_with_spaces(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid recipe_id"):
            resolve_dossier_path("bad name", tmp_path)

    def test_underscore_id(self, tmp_path: Path) -> None:
        result = resolve_dossier_path("recipe_42", tmp_path)
        assert result.name == "recipe_42.md"


# ---------------------------------------------------------------------------
# Tests: read_dossier
# ---------------------------------------------------------------------------


class TestReadDossier:
    def test_read_existing(self, dossier_dir: Path) -> None:
        content = read_dossier(42, dossier_dir)
        assert "Zürcher Geschnetzeltes" in content
        assert "## Ingredients" in content

    def test_read_not_found(self, dossier_dir: Path) -> None:
        with pytest.raises(RecipeNotFoundError):
            read_dossier(999, dossier_dir)


# ---------------------------------------------------------------------------
# Tests: read_section
# ---------------------------------------------------------------------------


class TestReadSection:
    def test_read_notes(self, dossier_dir: Path) -> None:
        result = read_section(42, "Notes", dossier_dir)
        assert result is not None
        assert "Rösti" in result

    def test_read_ingredients(self, dossier_dir: Path) -> None:
        result = read_section(42, "Ingredients", dossier_dir)
        assert result is not None
        assert "Kalbsgeschnetzeltes" in result

    def test_read_nonexistent_section(self, dossier_dir: Path) -> None:
        result = read_section(42, "Nonexistent", dossier_dir)
        assert result is None

    def test_case_insensitive(self, dossier_dir: Path) -> None:
        result = read_section(42, "notes", dossier_dir)
        assert result is not None
        assert "Rösti" in result

    def test_cook_log_section(self, dossier_dir: Path) -> None:
        result = read_section(42, "Cook Log", dossier_dir)
        assert result is not None
        assert "2024-01-15" in result


# ---------------------------------------------------------------------------
# Tests: list_sections
# ---------------------------------------------------------------------------


class TestListSections:
    def test_list_all(self, dossier_dir: Path) -> None:
        sections = list_sections(42, dossier_dir)
        assert "Metadata" in sections
        assert "Ingredients" in sections
        assert "Steps" in sections
        assert "Notes" in sections
        assert "Cook Log" in sections


# ---------------------------------------------------------------------------
# Tests: write_dossier
# ---------------------------------------------------------------------------


class TestWriteDossier:
    def test_write_new(self, tmp_path: Path) -> None:
        d = tmp_path / "dossiers"
        content = "# New Recipe\n\nHello world.\n"
        path = write_dossier(100, content, d)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == content

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "deep" / "nested" / "dir"
        write_dossier(1, "# Test\n", d)
        assert (d / "1.md").exists()

    def test_overwrite_existing(self, dossier_dir: Path) -> None:
        new_content = "# Updated\n\nNew content.\n"
        write_dossier(42, new_content, dossier_dir)
        assert read_dossier(42, dossier_dir) == new_content


# ---------------------------------------------------------------------------
# Tests: update_section
# ---------------------------------------------------------------------------


class TestUpdateSection:
    def test_update_notes(self, dossier_dir: Path) -> None:
        update_section(42, "Notes", "Updated notes content.", dossier_dir)
        result = read_section(42, "Notes", dossier_dir)
        assert result is not None
        assert "Updated notes content." in result
        # Original content should be gone
        assert "Rösti" not in result

    def test_update_preserves_other_sections(self, dossier_dir: Path) -> None:
        update_section(42, "Notes", "New notes.", dossier_dir)
        # Other sections should still be there
        ingredients = read_section(42, "Ingredients", dossier_dir)
        assert ingredients is not None
        assert "Kalbsgeschnetzeltes" in ingredients

    def test_update_protected_section_raises(self, dossier_dir: Path) -> None:
        with pytest.raises(ProtectedSectionError):
            update_section(42, "Ingredients", "hacked!", dossier_dir)

    def test_update_protected_steps_raises(self, dossier_dir: Path) -> None:
        with pytest.raises(ProtectedSectionError):
            update_section(42, "Steps", "hacked!", dossier_dir)

    def test_update_nonexistent_section_appends(self, dossier_dir: Path) -> None:
        update_section(42, "Pairings", "Goes well with Pinot Noir.", dossier_dir)
        result = read_section(42, "Pairings", dossier_dir)
        assert result is not None
        assert "Pinot Noir" in result

    def test_update_case_insensitive_protection(self, dossier_dir: Path) -> None:
        with pytest.raises(ProtectedSectionError):
            update_section(42, "INGREDIENTS", "hacked!", dossier_dir)


# ---------------------------------------------------------------------------
# Tests: append_to_section
# ---------------------------------------------------------------------------


class TestAppendToSection:
    def test_append_to_cook_log(self, dossier_dir: Path) -> None:
        append_to_section(42, "Cook Log", "- 2024-06-15: Dinner, rating 4/5", dossier_dir)
        result = read_section(42, "Cook Log", dossier_dir)
        assert result is not None
        assert "2024-01-15" in result  # Original still there
        assert "2024-06-15" in result  # New entry added

    def test_append_to_nonexistent_creates(self, dossier_dir: Path) -> None:
        append_to_section(42, "Variations", "Try with chicken instead.", dossier_dir)
        result = read_section(42, "Variations", dossier_dir)
        assert result is not None
        assert "chicken" in result

    def test_append_to_protected_raises(self, dossier_dir: Path) -> None:
        with pytest.raises(ProtectedSectionError):
            append_to_section(42, "Steps", "3. Serve.", dossier_dir)

    def test_append_not_found(self, dossier_dir: Path) -> None:
        with pytest.raises(RecipeNotFoundError):
            append_to_section(999, "Notes", "test", dossier_dir)


# ---------------------------------------------------------------------------
# Tests: constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_allowed_sections_exist(self) -> None:
        assert "notes" in ALLOWED_SECTIONS
        assert "cook_log" in ALLOWED_SECTIONS
        assert "tags" in ALLOWED_SECTIONS

    def test_protected_sections_exist(self) -> None:
        assert "ingredients" in PROTECTED_SECTIONS
        assert "steps" in PROTECTED_SECTIONS
        assert "metadata" in PROTECTED_SECTIONS

    def test_no_overlap(self) -> None:
        assert ALLOWED_SECTIONS.isdisjoint(PROTECTED_SECTIONS)
