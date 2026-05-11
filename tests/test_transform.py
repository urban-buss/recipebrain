"""Tests for the transform layer (RawRecipe → Parquet-ready dicts)."""

from __future__ import annotations

import pytest

from recipebrain.sources.base import RawRecipe
from recipebrain.transform import (
    _compute_content_hash,
    _extract_external_id,
    _parse_iso_duration,
    _parse_servings,
    build_recipe_images_rows,
    build_recipe_ingredients_rows,
    build_recipe_row,
    build_recipe_steps_rows,
    normalise_title,
)


def _full_raw_recipe() -> RawRecipe:
    return RawRecipe(
        title="Pouletbrust mit Lauch und Reis",
        description="Ein einfaches Alltagsgericht.",
        ingredients_raw=["400 g Pouletbrust", "2 Stangen Lauch", "200 g Reis"],
        steps_raw=["Reis kochen.", "Poulet braten.", "Lauch dünsten."],
        yield_amount="4 Portionen",
        prep_time="PT15M",
        cook_time="PT25M",
        image_urls=["https://img.ch/1.jpg", "https://img.ch/2.jpg"],
        keywords=["quick", "weeknight"],
        source_url="https://fooby.ch/de/rezepte/pouletbrust-12345",
        language="de",
    )


class TestBuildRecipeRow:
    def test_full_recipe(self):
        raw = _full_raw_recipe()
        row = build_recipe_row(raw, source_id=1, recipe_id=42)

        assert row["id"] == 42
        assert row["source_id"] == 1
        assert row["source_external_id"] == "pouletbrust-12345"
        assert row["source_url"] == "https://fooby.ch/de/rezepte/pouletbrust-12345"
        assert row["title"] == "Pouletbrust mit Lauch und Reis"
        assert row["title_normalised"] == "pouletbrust mit lauch und reis"
        assert row["language"] == "de"
        assert row["description"] == "Ein einfaches Alltagsgericht."
        assert row["servings"] == 4
        assert row["prep_minutes"] == 15
        assert row["cook_minutes"] == 25
        assert row["total_minutes"] == 40
        assert row["primary_image_url"] == "https://img.ch/1.jpg"
        assert row["original_keywords"] == ["quick", "weeknight"]
        assert row["status"] == "active"
        assert row["content_hash"] is not None
        assert row["scraped_at"] is not None
        assert row["updated_at"] is not None

    def test_missing_optional_fields(self):
        raw = RawRecipe(title="Minimal")
        row = build_recipe_row(raw, source_id=1, recipe_id=1)

        assert row["title"] == "Minimal"
        assert row["servings"] is None
        assert row["prep_minutes"] is None
        assert row["cook_minutes"] is None
        assert row["total_minutes"] is None
        assert row["primary_image_url"] is None
        assert row["original_keywords"] == []
        assert row["description"] == ""

    def test_total_minutes_with_only_prep(self):
        raw = RawRecipe(title="Test", prep_time="PT20M")
        row = build_recipe_row(raw, source_id=1, recipe_id=1)
        assert row["prep_minutes"] == 20
        assert row["cook_minutes"] is None
        assert row["total_minutes"] == 20

    def test_total_minutes_with_only_cook(self):
        raw = RawRecipe(title="Test", cook_time="PT45M")
        row = build_recipe_row(raw, source_id=1, recipe_id=1)
        assert row["prep_minutes"] is None
        assert row["cook_minutes"] == 45
        assert row["total_minutes"] == 45


class TestBuildRecipeSteps:
    def test_builds_numbered_steps(self):
        rows = build_recipe_steps_rows(10, ["Step one.", "Step two.", "Step three."])
        assert len(rows) == 3
        assert rows[0] == {"recipe_id": 10, "step_no": 1, "text": "Step one.", "image_url": None}
        assert rows[2]["step_no"] == 3

    def test_empty_steps(self):
        assert build_recipe_steps_rows(10, []) == []


class TestBuildRecipeImages:
    def test_builds_sequenced_images(self):
        urls = ["https://img.ch/a.jpg", "https://img.ch/b.jpg"]
        rows = build_recipe_images_rows(10, urls)
        assert len(rows) == 2
        assert rows[0]["seq"] == 1
        assert rows[0]["url"] == "https://img.ch/a.jpg"
        assert rows[1]["seq"] == 2

    def test_empty_images(self):
        assert build_recipe_images_rows(10, []) == []


class TestBuildRecipeIngredients:
    def test_builds_raw_ingredients(self):
        ingredients = ["400 g Pouletbrust", "2 Stangen Lauch"]
        rows = build_recipe_ingredients_rows(10, ingredients)
        assert len(rows) == 2
        assert rows[0]["recipe_id"] == 10
        assert rows[0]["seq"] == 1
        assert rows[0]["raw_text"] == "400 g Pouletbrust"
        assert rows[0]["optional"] is False

    def test_empty_ingredients(self):
        assert build_recipe_ingredients_rows(10, []) == []

    def test_parses_quantity_and_unit(self):
        rows = build_recipe_ingredients_rows(1, ["200 g Butter"])
        assert rows[0]["quantity"] == 200.0
        assert rows[0]["unit"] == "g"

    def test_links_known_ingredient(self):
        rows = build_recipe_ingredients_rows(1, ["200 g Pouletbrust"])
        assert rows[0]["ingredient_id"] is not None  # chicken-breast ID

    def test_unknown_ingredient_id_is_none(self):
        rows = build_recipe_ingredients_rows(1, ["1 Xylophon"])
        assert rows[0]["ingredient_id"] is None

    def test_extracts_prep_note(self):
        rows = build_recipe_ingredients_rows(1, ["200 g Pouletbrust, in Würfeln"])
        assert rows[0]["prep_note"] == "in Würfeln"


class TestParseIsoDuration:
    @pytest.mark.parametrize(
        ("iso", "expected"),
        [
            ("PT15M", 15),
            ("PT1H30M", 90),
            ("PT2H", 120),
            ("PT0H45M", 45),
            ("PT1H", 60),
            ("PT90M", 90),
            ("PT1H0M30S", 61),  # 30 seconds rounds up
            ("PT0H0M45S", 1),  # 45 seconds rounds up
            ("PT0H0M10S", None),  # 10 seconds rounds to 0 → None
            ("", None),
            ("   ", None),
            ("not a duration", None),
            ("P1D", None),  # days not supported
        ],
    )
    def test_parse(self, iso, expected):
        assert _parse_iso_duration(iso) == expected


class TestNormaliseTitle:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Crème Brûlée", "creme brulee"),
            ("POULET BRUST", "poulet brust"),
            ("  extra   spaces  ", "extra spaces"),
            ("Zürich Geschnetzeltes", "zurich geschnetzeltes"),
            ("", ""),
        ],
    )
    def test_normalise(self, title, expected):
        assert normalise_title(title) == expected


class TestComputeContentHash:
    def test_same_input_same_hash(self):
        raw = _full_raw_recipe()
        assert _compute_content_hash(raw) == _compute_content_hash(raw)

    def test_different_title_different_hash(self):
        raw1 = _full_raw_recipe()
        raw2 = _full_raw_recipe()
        raw2.title = "Different Title"
        assert _compute_content_hash(raw1) != _compute_content_hash(raw2)

    def test_different_ingredients_different_hash(self):
        raw1 = _full_raw_recipe()
        raw2 = _full_raw_recipe()
        raw2.ingredients_raw = ["something else"]
        assert _compute_content_hash(raw1) != _compute_content_hash(raw2)

    def test_hash_is_hex_sha256(self):
        raw = _full_raw_recipe()
        h = _compute_content_hash(raw)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestExtractExternalId:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://fooby.ch/de/rezepte/pouletbrust-12345", "pouletbrust-12345"),
            ("https://migusto.migros.ch/de/rezepte/pasta-carbonara.html", "pasta-carbonara"),
            ("https://example.com/recipe/test.htm", "test"),
            ("https://example.com/a/b/c/", "c"),
            ("", ""),
            ("https://example.com/", "example.com"),
        ],
    )
    def test_extract(self, url, expected):
        assert _extract_external_id(url) == expected


class TestParseServings:
    @pytest.mark.parametrize(
        ("yield_str", "expected"),
        [
            ("4 Portionen", 4),
            ("6", 6),
            ("für 2 Personen", 2),
            ("", None),
            ("keine Zahl", None),
        ],
    )
    def test_parse(self, yield_str, expected):
        assert _parse_servings(yield_str) == expected
