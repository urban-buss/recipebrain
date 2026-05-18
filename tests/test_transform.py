"""Tests for the transform layer (RawRecipe → Parquet-ready dicts)."""

from __future__ import annotations

import pytest

from recipebrain.sources.base import RawIngredientGroup, RawRecipe
from recipebrain.transform import (
    _compute_content_hash,
    _extract_external_id,
    _infer_difficulty,
    _normalise_course,
    _normalise_cuisine,
    _normalise_difficulty,
    _parse_iso_duration,
    _parse_servings,
    build_recipe_images_rows,
    build_recipe_ingredients_rows,
    build_recipe_row,
    build_recipe_steps_rows,
    extract_classification,
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
        category="Hauptgericht",
        cuisine="Swiss",
    )


class TestBuildRecipeRow:
    def test_full_recipe(self):
        raw = _full_raw_recipe()
        row = build_recipe_row(raw, source_id=1, recipe_id=42)

        assert row["id"] == 42
        assert row["source_id"] == 1
        assert row["source_external_id"] == "pouletbrust-12345-de"
        assert row["source_url"] == "https://fooby.ch/de/rezepte/pouletbrust-12345"
        assert row["title"] == "Pouletbrust mit Lauch und Reis"
        assert row["title_normalised"] == "pouletbrust mit lauch und reis"
        assert row["language"] == "de"
        assert row["description"] == "Ein einfaches Alltagsgericht."
        assert row["servings"] == 4
        assert row["prep_minutes"] == 15
        assert row["cook_minutes"] == 25
        assert row["total_minutes"] == 40
        assert row["difficulty"] == "medium"  # inferred from 40 min total
        assert row["cuisine"] == "swiss"
        assert row["course"] == "main"
        assert row["primary_image_url"] == "https://img.ch/1.jpg"
        assert row["original_keywords"] == ["quick", "weeknight"]
        assert row["status"] == "active"
        assert row["content_hash"] is not None
        assert row["scraped_at"] is not None
        assert row["updated_at"] is not None
        # Computed tag columns present (values depend on ingredient resolution)
        assert "primary_protein" in row
        assert "taste_profile" in row
        assert "weight_class" in row
        assert "cooking_method" in row
        assert isinstance(row["dietary_flags"], list)
        assert isinstance(row["food_groups"], list)
        assert isinstance(row["computed_tags"], list)

    def test_missing_optional_fields(self):
        raw = RawRecipe(title="Minimal")
        row = build_recipe_row(raw, source_id=1, recipe_id=1)

        assert row["title"] == "Minimal"
        assert row["servings"] is None
        assert row["prep_minutes"] is None
        assert row["cook_minutes"] is None
        assert row["total_minutes"] is None
        assert row["difficulty"] is None
        assert row["cuisine"] is None
        assert row["course"] is None
        assert row["primary_image_url"] is None
        assert row["original_keywords"] == []
        assert row["description"] == ""
        # Computed tags default when no ingredients provided
        assert row["primary_protein"] is None
        assert row["taste_profile"] == "savoury"
        assert isinstance(row["dietary_flags"], list)
        assert isinstance(row["computed_tags"], list)

    def test_computed_tags_with_ingredients(self):
        raw = _full_raw_recipe()
        ing_rows = build_recipe_ingredients_rows(
            recipe_id=42,
            ingredients_raw=raw.ingredients_raw,
        )
        row = build_recipe_row(raw, source_id=1, recipe_id=42, ingredient_rows=ing_rows)
        # With actual ingredients resolved, computed tags should be populated
        assert isinstance(row["computed_tags"], list)
        assert isinstance(row["food_groups"], list)
        assert row["taste_profile"] in ("sweet", "savoury", "sweet-savoury")
        assert row["weight_class"] in ("light", "medium", "heavy")

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
        assert rows[0]["local_path"] is None
        assert rows[1]["seq"] == 2

    def test_empty_images(self):
        assert build_recipe_images_rows(10, []) == []

    def test_with_local_paths(self):
        urls = ["https://img.ch/a.jpg", "https://img.ch/b.jpg"]
        paths = ["images/10_001_abc.jpg", "images/10_002_def.jpg"]
        rows = build_recipe_images_rows(10, urls, local_paths=paths)
        assert rows[0]["local_path"] == "images/10_001_abc.jpg"
        assert rows[1]["local_path"] == "images/10_002_def.jpg"

    def test_with_partial_local_paths(self):
        urls = ["https://img.ch/a.jpg", "https://img.ch/b.jpg"]
        paths = ["images/10_001_abc.jpg", None]
        rows = build_recipe_images_rows(10, urls, local_paths=paths)
        assert rows[0]["local_path"] == "images/10_001_abc.jpg"
        assert rows[1]["local_path"] is None

    def test_local_paths_none_defaults_to_null(self):
        urls = ["https://img.ch/a.jpg"]
        rows = build_recipe_images_rows(10, urls, local_paths=None)
        assert rows[0]["local_path"] is None


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

    def test_group_label_populated_from_ingredient_groups(self):
        groups = [
            RawIngredientGroup(label="Für den Teig", items=["200 g Mehl", "3 Eier"]),
            RawIngredientGroup(label="Für die Sauce", items=["2 dl Rahm"]),
        ]
        rows = build_recipe_ingredients_rows(1, ingredient_groups=groups)
        assert len(rows) == 3
        assert rows[0]["group_label"] == "Für den Teig"
        assert rows[0]["raw_text"] == "200 g Mehl"
        assert rows[0]["seq"] == 1
        assert rows[1]["group_label"] == "Für den Teig"
        assert rows[1]["raw_text"] == "3 Eier"
        assert rows[1]["seq"] == 2
        assert rows[2]["group_label"] == "Für die Sauce"
        assert rows[2]["raw_text"] == "2 dl Rahm"
        assert rows[2]["seq"] == 3

    def test_group_label_none_when_no_label(self):
        groups = [
            RawIngredientGroup(label=None, items=["200 g Mehl", "3 Eier"]),
        ]
        rows = build_recipe_ingredients_rows(1, ingredient_groups=groups)
        assert rows[0]["group_label"] is None
        assert rows[1]["group_label"] is None

    def test_fallback_to_ingredients_raw_when_no_groups(self):
        rows = build_recipe_ingredients_rows(1, ["200 g Mehl", "3 Eier"])
        assert len(rows) == 2
        assert rows[0]["group_label"] is None

    def test_ingredient_groups_take_priority_over_raw(self):
        groups = [
            RawIngredientGroup(label="Teig", items=["200 g Mehl"]),
        ]
        rows = build_recipe_ingredients_rows(1, ["ignored"], ingredient_groups=groups)
        assert len(rows) == 1
        assert rows[0]["raw_text"] == "200 g Mehl"
        assert rows[0]["group_label"] == "Teig"

    def test_empty_groups_returns_empty(self):
        assert build_recipe_ingredients_rows(1, ingredient_groups=[]) == []
        assert build_recipe_ingredients_rows(1, []) == []
        assert build_recipe_ingredients_rows(1) == []

    def test_optional_flag_detected(self):
        rows = build_recipe_ingredients_rows(1, ["evt. 2 dl Rahm"])
        assert rows[0]["optional"] is True

    def test_optional_flag_false_for_regular(self):
        rows = build_recipe_ingredients_rows(1, ["200 g Mehl"])
        assert rows[0]["optional"] is False

    def test_optional_nach_belieben(self):
        rows = build_recipe_ingredients_rows(1, ["Schnittlauch, nach Belieben"])
        assert rows[0]["optional"] is True


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

    def test_different_language_different_hash(self):
        raw1 = _full_raw_recipe()
        raw2 = _full_raw_recipe()
        raw2.language = "fr"
        assert _compute_content_hash(raw1) != _compute_content_hash(raw2)

    def test_hash_is_hex_sha256(self):
        raw = _full_raw_recipe()
        h = _compute_content_hash(raw)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestExtractExternalId:
    @pytest.mark.parametrize(
        ("url", "language", "expected"),
        [
            ("https://fooby.ch/de/rezepte/pouletbrust-12345", "de", "pouletbrust-12345-de"),
            ("https://fooby.ch/fr/recettes/pouletbrust-12345", "fr", "pouletbrust-12345-fr"),
            (
                "https://migusto.migros.ch/de/rezepte/pasta-carbonara.html",
                "de",
                "pasta-carbonara-de",
            ),
            ("https://example.com/recipe/test.htm", "en", "test-en"),
            ("https://example.com/a/b/c/", "de", "c-de"),
            ("", "de", ""),
            ("https://example.com/", "de", "example.com-de"),
            # Slug already ends with language suffix — no double-append
            (
                "https://bettybossi.ch/fr/Rezept/ShowRezept/BB_ABRE120801_0002A-40-fr",
                "fr",
                "BB_ABRE120801_0002A-40-fr",
            ),
            (
                "https://bettybossi.ch/de/Rezept/ShowRezept/BB_ABRE120801_0002A-40-de",
                "de",
                "BB_ABRE120801_0002A-40-de",
            ),
            # No language provided — backward compat
            ("https://fooby.ch/de/rezepte/pouletbrust-12345", None, "pouletbrust-12345"),
            ("https://migusto.migros.ch/de/rezepte/pasta-carbonara.html", None, "pasta-carbonara"),
        ],
    )
    def test_extract(self, url, language, expected):
        assert _extract_external_id(url, language) == expected


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


class TestNormaliseCourse:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Hauptgericht", "main"),
            ("hauptgericht", "main"),
            ("Hauptspeise", "main"),
            ("Hauptgerichte", "main"),
            ("plat principal", "main"),
            ("Main Course", "main"),
            ("Dessert", "dessert"),
            ("Vorspeise", "starter"),
            ("Suppe", "starter"),
            ("Salat", "starter"),
            ("Apéro", "starter"),
            ("Fingerfood", "starter"),
            ("Beilage", "side"),
            ("Snack", "side"),
            ("Znüni", "side"),
            ("Zvieri", "side"),
            ("Backen", "bake"),
            ("Kuchen", "bake"),
            ("Brot", "bake"),
            ("Getränk", "drink"),
            ("Smoothie", "drink"),
            ("Cocktail", "drink"),
            ("", None),
            ("Unknown Category", None),
        ],
    )
    def test_normalise(self, raw, expected):
        assert _normalise_course(raw) == expected


class TestNormaliseCuisine:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Swiss", "swiss"),
            ("Italian", "italian"),
            ("ASIAN", "asian"),
            ("  French  ", "french"),
            ("", None),
            ("milchprodukte, käse, eier", None),
            ("familien-gerichte, geflügel, gemüse", None),
        ],
    )
    def test_normalise(self, raw, expected):
        assert _normalise_cuisine(raw) == expected


class TestNormaliseDifficulty:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("easy", "easy"),
            ("Einfach", "easy"),
            ("medium", "medium"),
            ("Mittel", "medium"),
            ("advanced", "advanced"),
            ("Schwer", "advanced"),
            ("", None),
            ("unknown", None),
        ],
    )
    def test_normalise(self, raw, expected):
        assert _normalise_difficulty(raw) == expected


class TestInferDifficulty:
    def test_explicit_value_takes_priority(self):
        assert _infer_difficulty("Einfach", 90) == "easy"

    def test_infer_easy_from_time(self):
        assert _infer_difficulty("", 25) == "easy"

    def test_infer_medium_from_time(self):
        assert _infer_difficulty("", 45) == "medium"

    def test_infer_advanced_from_time(self):
        assert _infer_difficulty("", 90) == "advanced"

    def test_boundary_30_is_easy(self):
        assert _infer_difficulty("", 30) == "easy"

    def test_boundary_60_is_medium(self):
        assert _infer_difficulty("", 60) == "medium"

    def test_no_data_returns_none(self):
        assert _infer_difficulty("", None) is None


class TestExtractClassification:
    def test_recipe_category_maps_to_course(self):
        result = extract_classification({"recipeCategory": "Hauptgericht"})
        assert result == {"course": "main", "cuisine": None, "difficulty": None}

    def test_category_key_also_accepted(self):
        result = extract_classification({"category": "Dessert"})
        assert result["course"] == "dessert"

    def test_recipe_category_takes_priority_over_category(self):
        result = extract_classification({"recipeCategory": "Hauptgericht", "category": "Dessert"})
        assert result["course"] == "main"

    def test_recipe_cuisine_normalised(self):
        result = extract_classification({"recipeCuisine": "Swiss"})
        assert result == {"course": None, "cuisine": "swiss", "difficulty": None}

    def test_cuisine_key_also_accepted(self):
        result = extract_classification({"cuisine": "Italian"})
        assert result["cuisine"] == "italian"

    def test_explicit_difficulty(self):
        result = extract_classification({"difficulty": "Einfach"})
        assert result["difficulty"] == "easy"

    def test_difficulty_inferred_from_total_minutes(self):
        result = extract_classification({"total_minutes": 90})
        assert result["difficulty"] == "advanced"

    def test_explicit_difficulty_beats_total_minutes(self):
        result = extract_classification({"difficulty": "easy", "total_minutes": 120})
        assert result["difficulty"] == "easy"

    def test_keyword_fallback_for_difficulty(self):
        result = extract_classification({"keywords": ["einfach", "Schweizer Küche"]})
        assert result["difficulty"] == "easy"

    def test_keyword_fallback_for_course(self):
        result = extract_classification({"keywords": ["Dessert", "süss"]})
        assert result["course"] == "dessert"

    def test_keyword_fallback_for_course_new_terms(self):
        result = extract_classification({"keywords": ["familien-gerichte", "suppe"]})
        assert result["course"] == "starter"

    def test_explicit_category_beats_keyword(self):
        result = extract_classification(
            {
                "recipeCategory": "Hauptgericht",
                "keywords": ["Dessert"],
            }
        )
        assert result["course"] == "main"

    def test_explicit_difficulty_beats_keyword(self):
        result = extract_classification(
            {
                "difficulty": "medium",
                "keywords": ["einfach"],
            }
        )
        assert result["difficulty"] == "medium"

    def test_full_example(self):
        result = extract_classification(
            {
                "recipeCategory": "Hauptgericht",
                "recipeCuisine": "Swiss",
                "keywords": ["einfach", "Schweizer Küche"],
            }
        )
        assert result == {"course": "main", "cuisine": "swiss", "difficulty": "easy"}

    def test_empty_dict(self):
        result = extract_classification({})
        assert result == {"course": None, "cuisine": None, "difficulty": None}

    def test_empty_strings(self):
        result = extract_classification(
            {
                "recipeCategory": "",
                "recipeCuisine": "",
                "difficulty": "",
            }
        )
        assert result == {"course": None, "cuisine": None, "difficulty": None}

    def test_no_keywords_key(self):
        result = extract_classification({"recipeCategory": "Vorspeise"})
        assert result["course"] == "starter"

    def test_keywords_none(self):
        result = extract_classification({"keywords": None})
        assert result == {"course": None, "cuisine": None, "difficulty": None}

    def test_raw_recipe_basic(self):
        raw = RawRecipe(
            title="Grilled Chicken Salad",
            ingredients_raw=["200g Pouletbrust"],
            steps_raw=["Poulet grillieren"],
            category="Hauptgericht",
        )
        result = extract_classification(raw)
        assert result == {"course": "main", "cuisine": None, "difficulty": None}

    def test_raw_recipe_full_classification(self):
        raw = RawRecipe(
            title="Fondue",
            ingredients_raw=[],
            steps_raw=[],
            category="Hauptgericht",
            cuisine="Swiss",
            difficulty="Einfach",
            keywords=["Schweizer Küche"],
        )
        result = extract_classification(raw)
        assert result == {"course": "main", "cuisine": "swiss", "difficulty": "easy"}

    def test_raw_recipe_empty_fields(self):
        raw = RawRecipe(title="Minimal")
        result = extract_classification(raw)
        assert result == {"course": None, "cuisine": None, "difficulty": None}

    def test_raw_recipe_keyword_fallback(self):
        raw = RawRecipe(
            title="Mystery Dish",
            ingredients_raw=[],
            steps_raw=[],
            keywords=["Dessert", "einfach"],
        )
        result = extract_classification(raw)
        assert result["course"] == "dessert"
        assert result["difficulty"] == "easy"
