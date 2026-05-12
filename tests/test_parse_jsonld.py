"""Tests for the generic JSON-LD recipe parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from recipebrain.parse.jsonld import (
    extract_recipes,
    parse_recipe,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractRecipes:
    def test_extracts_recipe_from_html(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")
        recipes = extract_recipes(html)
        assert len(recipes) == 1
        assert recipes[0]["name"] == "Pouletbrust mit Lauch und Reis"

    def test_returns_empty_for_no_jsonld(self):
        html = "<html><body><p>No recipe here</p></body></html>"
        assert extract_recipes(html) == []

    def test_returns_empty_for_non_recipe_jsonld(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Example"}
        </script>
        </head><body></body></html>
        """
        assert extract_recipes(html) == []

    def test_handles_graph_wrapper(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@graph": [
            {"@type": "Recipe", "name": "Nested Recipe"}
        ]}
        </script>
        </head><body></body></html>
        """
        recipes = extract_recipes(html)
        assert len(recipes) == 1
        assert recipes[0]["name"] == "Nested Recipe"

    def test_handles_malformed_html(self):
        html = "<not valid at all>>><<<"
        assert extract_recipes(html) == []


class TestParseRecipe:
    def test_parses_full_recipe(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")
        data = extract_recipes(html)[0]
        recipe = parse_recipe(data, source_url="https://fooby.ch/de/rezepte/test", language="de")

        assert recipe.title == "Pouletbrust mit Lauch und Reis"
        assert "Alltagsgericht" in recipe.description
        assert len(recipe.ingredients_raw) == 6
        assert recipe.ingredients_raw[0] == "400 g Pouletbrust"
        assert len(recipe.steps_raw) == 6
        assert recipe.steps_raw[0] == "Reis nach Packungsanleitung kochen."
        assert recipe.yield_amount == "4 Portionen"
        assert recipe.prep_time == "PT15M"
        assert recipe.cook_time == "PT25M"
        assert len(recipe.image_urls) == 2
        assert recipe.source_url == "https://fooby.ch/de/rezepte/test"
        assert recipe.language == "de"

    def test_parses_keywords_from_comma_string(self):
        data = {
            "name": "Test",
            "keywords": "quick, easy, pasta",
        }
        recipe = parse_recipe(data)
        assert recipe.keywords == ["quick", "easy", "pasta"]

    def test_parses_keywords_from_list(self):
        data = {
            "name": "Test",
            "keywords": ["quick", "easy"],
        }
        recipe = parse_recipe(data)
        assert recipe.keywords == ["quick", "easy"]

    def test_raises_on_missing_name(self):
        with pytest.raises(ValueError, match="missing required 'name'"):
            parse_recipe({})

    def test_raises_on_empty_name(self):
        with pytest.raises(ValueError, match="missing required 'name'"):
            parse_recipe({"name": "   "})

    def test_handles_missing_optional_fields(self):
        recipe = parse_recipe({"name": "Minimal Recipe"})
        assert recipe.title == "Minimal Recipe"
        assert recipe.description == ""
        assert recipe.ingredients_raw == []
        assert recipe.steps_raw == []
        assert recipe.yield_amount == ""
        assert recipe.prep_time == ""
        assert recipe.cook_time == ""
        assert recipe.image_urls == []
        assert recipe.keywords == []
        assert recipe.category == ""
        assert recipe.cuisine == ""

    def test_extracts_recipe_category(self):
        data = {
            "name": "Test",
            "recipeCategory": "Hauptgericht",
        }
        recipe = parse_recipe(data)
        assert recipe.category == "Hauptgericht"

    def test_extracts_recipe_cuisine(self):
        data = {
            "name": "Test",
            "recipeCuisine": "Swiss",
        }
        recipe = parse_recipe(data)
        assert recipe.cuisine == "Swiss"

    def test_category_and_cuisine_from_fixture(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")
        data = extract_recipes(html)[0]
        recipe = parse_recipe(data, source_url="https://fooby.ch/de/rezepte/test")
        assert recipe.category == "Hauptgericht"
        assert recipe.cuisine == "Swiss"

    def test_handles_string_instructions(self):
        data = {
            "name": "Test",
            "recipeInstructions": "Step one.\nStep two.\nStep three.",
        }
        recipe = parse_recipe(data)
        assert recipe.steps_raw == ["Step one.", "Step two.", "Step three."]

    def test_handles_howto_section(self):
        data = {
            "name": "Test",
            "recipeInstructions": [
                {
                    "@type": "HowToSection",
                    "name": "Sauce",
                    "itemListElement": [
                        {"@type": "HowToStep", "text": "Make the sauce."},
                        {"@type": "HowToStep", "text": "Reduce it."},
                    ],
                }
            ],
        }
        recipe = parse_recipe(data)
        assert recipe.steps_raw == ["Make the sauce.", "Reduce it."]

    def test_handles_image_as_string(self):
        data = {"name": "Test", "image": "https://example.com/img.jpg"}
        recipe = parse_recipe(data)
        assert recipe.image_urls == ["https://example.com/img.jpg"]

    def test_handles_image_as_dict(self):
        data = {"name": "Test", "image": {"url": "https://example.com/img.jpg"}}
        recipe = parse_recipe(data)
        assert recipe.image_urls == ["https://example.com/img.jpg"]

    def test_handles_yield_as_int(self):
        data = {"name": "Test", "recipeYield": 4}
        recipe = parse_recipe(data)
        assert recipe.yield_amount == "4"

    def test_handles_yield_as_list(self):
        data = {"name": "Test", "recipeYield": ["4 servings", "4"]}
        recipe = parse_recipe(data)
        assert recipe.yield_amount == "4 servings"
