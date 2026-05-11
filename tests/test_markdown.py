"""Tests for recipebrain.markdown — dossier rendering."""

from __future__ import annotations

from recipebrain.markdown import (
    render_dossier,
    render_ingredients,
    render_metadata,
    render_source,
    render_steps,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _minimal_recipe(**overrides: object) -> dict:
    base: dict = {
        "title": "Test Recipe",
        "source_url": "https://fooby.ch/test",
        "servings": 4,
        "total_minutes": 30,
        "difficulty": "easy",
        "course": "main",
        "cuisine": "swiss",
        "language": "de",
        "description": "A tasty test recipe.",
        "source_external_id": "test-123",
        "source_id": 1,
    }
    base.update(overrides)
    return base


def _make_ingredient(**overrides: object) -> dict:
    base: dict = {
        "raw_text": "200 g Mehl",
        "quantity": 200.0,
        "unit": "g",
        "prep_note": None,
        "optional": False,
        "group_label": None,
    }
    base.update(overrides)
    return base


def _make_step(step_no: int, text: str) -> dict:
    return {"step_no": step_no, "text": text}


# ---------------------------------------------------------------------------
# TestRenderMetadata
# ---------------------------------------------------------------------------


class TestRenderMetadata:
    def test_all_fields(self) -> None:
        recipe = _minimal_recipe()
        result = render_metadata(recipe)
        assert result.startswith("## Metadata")
        assert "**Source:** https://fooby.ch/test" in result
        assert "**Servings:** 4" in result
        assert "**Total time:** 30 min" in result
        assert "**Difficulty:** easy" in result
        assert "**Course:** main" in result
        assert "**Cuisine:** swiss" in result
        assert "**Language:** de" in result

    def test_missing_fields_omitted(self) -> None:
        recipe = _minimal_recipe(difficulty=None, cuisine=None)
        result = render_metadata(recipe)
        assert "Difficulty" not in result
        assert "Cuisine" not in result

    def test_empty_string_omitted(self) -> None:
        recipe = _minimal_recipe(difficulty="", course="  ")
        result = render_metadata(recipe)
        assert "Difficulty" not in result
        assert "Course" not in result


# ---------------------------------------------------------------------------
# TestRenderSource
# ---------------------------------------------------------------------------


class TestRenderSource:
    def test_full_source(self) -> None:
        recipe = _minimal_recipe()
        result = render_source(recipe)
        assert result.startswith("## Source")
        assert "**URL:** https://fooby.ch/test" in result
        assert "**External ID:** test-123" in result
        assert "**Source ID:** 1" in result

    def test_no_url(self) -> None:
        recipe = _minimal_recipe(source_url=None)
        result = render_source(recipe)
        assert "URL" not in result


# ---------------------------------------------------------------------------
# TestRenderIngredients
# ---------------------------------------------------------------------------


class TestRenderIngredients:
    def test_simple_list(self) -> None:
        ings = [_make_ingredient(raw_text="200 g Mehl"), _make_ingredient(raw_text="3 Eier")]
        result = render_ingredients(ings)
        assert "## Ingredients" in result
        assert "- 200 g Mehl" in result
        assert "- 3 Eier" in result

    def test_with_groups(self) -> None:
        ings = [
            _make_ingredient(raw_text="200 g Mehl", group_label="Für den Teig"),
            _make_ingredient(raw_text="100 ml Milch", group_label="Für den Teig"),
            _make_ingredient(raw_text="50 g Zucker", group_label="Für die Sauce"),
        ]
        result = render_ingredients(ings)
        assert "**Für den Teig**" in result
        assert "**Für die Sauce**" in result

    def test_optional_marker(self) -> None:
        ings = [_make_ingredient(raw_text="Petersilie", optional=True)]
        result = render_ingredients(ings)
        assert "*(optional)*" in result

    def test_prep_note_appended(self) -> None:
        ings = [_make_ingredient(raw_text="200 g Poulet", prep_note="in Würfeln")]
        result = render_ingredients(ings)
        assert "200 g Poulet, in Würfeln" in result

    def test_prep_note_not_duplicated(self) -> None:
        ings = [_make_ingredient(raw_text="200 g Poulet, in Würfeln", prep_note="in Würfeln")]
        result = render_ingredients(ings)
        # Should NOT appear twice
        assert result.count("in Würfeln") == 1

    def test_fallback_to_qty_unit(self) -> None:
        ings = [_make_ingredient(raw_text="", quantity=500.0, unit="ml")]
        result = render_ingredients(ings)
        assert "- 500.0 ml" in result

    def test_empty_list(self) -> None:
        result = render_ingredients([])
        assert "## Ingredients" in result


# ---------------------------------------------------------------------------
# TestRenderSteps
# ---------------------------------------------------------------------------


class TestRenderSteps:
    def test_ordered_list(self) -> None:
        steps = [_make_step(1, "Preheat oven."), _make_step(2, "Mix flour.")]
        result = render_steps(steps)
        assert "## Steps" in result
        assert "1. Preheat oven." in result
        assert "2. Mix flour." in result

    def test_empty_steps(self) -> None:
        result = render_steps([])
        assert "## Steps" in result


# ---------------------------------------------------------------------------
# TestRenderDossier
# ---------------------------------------------------------------------------


class TestRenderDossier:
    def test_full_dossier(self) -> None:
        recipe = _minimal_recipe()
        ings = [_make_ingredient(raw_text="200 g Mehl")]
        steps = [_make_step(1, "Mix.")]
        result = render_dossier(recipe, ings, steps)

        assert result.startswith("# Test Recipe")
        assert "## Metadata" in result
        assert "## Source" in result
        assert "## Ingredients" in result
        assert "## Steps" in result
        assert "## Notes" in result
        assert "## Cook log" in result

    def test_no_ingredients_or_steps(self) -> None:
        recipe = _minimal_recipe()
        result = render_dossier(recipe)
        assert "## Ingredients" not in result
        assert "## Steps" not in result

    def test_description_included(self) -> None:
        recipe = _minimal_recipe(description="Delicious and easy.")
        result = render_dossier(recipe)
        assert "Delicious and easy." in result

    def test_no_description(self) -> None:
        recipe = _minimal_recipe(description=None)
        result = render_dossier(recipe)
        assert "# Test Recipe\n\n## Metadata" in result

    def test_default_title(self) -> None:
        result = render_dossier({})
        assert "# Untitled Recipe" in result

    def test_ends_with_newline(self) -> None:
        result = render_dossier(_minimal_recipe())
        assert result.endswith("\n")
