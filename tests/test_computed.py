"""Tests for the computed recipe tag module."""

from __future__ import annotations

from recipebrain.computed import (
    build_computed_tags,
    compute_cooking_method,
    compute_dietary_flags,
    compute_food_groups,
    compute_primary_protein,
    compute_taste_profile,
    compute_weight_class,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingredient_row(
    ingredient_id: int | None = None,
    quantity: float | None = None,
    raw_text: str = "",
) -> dict:
    """Build a minimal ingredient row dict for testing."""
    return {
        "ingredient_id": ingredient_id,
        "quantity": quantity,
        "raw_text": raw_text,
        "unit": "g",
    }


# Catalogue ID reference (from normalise/ingredients.py SEED_CATALOGUE):
#   1  = chicken-breast  (meat/poultry)
#   3  = beef-minced     (meat/beef)
#   5  = pork-chop       (meat/pork)
#   7  = sausage-bratwurst (meat/sausage)
#  10  = salmon-fillet   (fish/oily-fish)
#  11  = shrimp          (fish/shellfish)
#  20  = butter          (dairy/fat)
#  21  = cream           (dairy/cream)
#  23  = cheese-gruyere  (dairy/cheese-hard)
#  40  = onion           (vegetable/allium)
#  42  = carrot          (vegetable/root)
#  82  = sugar           (pantry/sweetener)


# ---------------------------------------------------------------------------
# compute_primary_protein
# ---------------------------------------------------------------------------


class TestComputePrimaryProtein:
    """compute_primary_protein — protein classification from ingredients."""

    def test_single_poultry(self):
        rows = [_ingredient_row(ingredient_id=1, quantity=200)]
        assert compute_primary_protein(rows) == "poultry"

    def test_single_beef(self):
        rows = [_ingredient_row(ingredient_id=3, quantity=500)]
        assert compute_primary_protein(rows) == "beef"

    def test_single_pork(self):
        rows = [_ingredient_row(ingredient_id=5, quantity=300)]
        assert compute_primary_protein(rows) == "pork"

    def test_single_fish(self):
        rows = [_ingredient_row(ingredient_id=10, quantity=200)]
        assert compute_primary_protein(rows) == "fish"

    def test_single_seafood(self):
        rows = [_ingredient_row(ingredient_id=11, quantity=200)]
        assert compute_primary_protein(rows) == "seafood"

    def test_single_sausage(self):
        rows = [_ingredient_row(ingredient_id=7, quantity=200)]
        assert compute_primary_protein(rows) == "sausage"

    def test_no_meat_no_dairy_returns_none(self):
        rows = [_ingredient_row(ingredient_id=42)]  # carrot
        assert compute_primary_protein(rows) is None

    def test_no_meat_with_dairy_returns_none(self):
        rows = [
            _ingredient_row(ingredient_id=42),  # carrot
            _ingredient_row(ingredient_id=20),  # butter
        ]
        assert compute_primary_protein(rows) is None

    def test_cheese_dominant_returns_none(self):
        rows = [
            _ingredient_row(ingredient_id=23, quantity=400),  # gruyère
            _ingredient_row(ingredient_id=40),  # onion
        ]
        assert compute_primary_protein(rows) is None

    def test_mixed_proteins(self):
        rows = [
            _ingredient_row(ingredient_id=1, quantity=200),  # chicken
            _ingredient_row(ingredient_id=10, quantity=200),  # salmon
        ]
        assert compute_primary_protein(rows) == "mixed"

    def test_mixed_with_dominant_protein(self):
        rows = [
            _ingredient_row(ingredient_id=1, quantity=500),  # chicken dominant
            _ingredient_row(ingredient_id=10, quantity=100),  # salmon minor
        ]
        assert compute_primary_protein(rows) == "poultry"

    def test_unresolved_ingredients_returns_none(self):
        rows = [_ingredient_row(ingredient_id=None)]
        assert compute_primary_protein(rows) is None

    def test_unresolved_meat_raw_text_fallback(self):
        """Unresolved ingredient with meat keyword in raw_text → 'meat'."""
        rows = [_ingredient_row(ingredient_id=None, raw_text="800 g Pouletschenkel-Steaks")]
        assert compute_primary_protein(rows) == "meat"

    def test_unresolved_fish_raw_text_fallback(self):
        """Unresolved ingredient with fish keyword in raw_text → 'fish'."""
        rows = [_ingredient_row(ingredient_id=None, raw_text="250 g Lachsfilet ohne Haut")]
        assert compute_primary_protein(rows) == "fish"

    def test_unresolved_meat_and_fish_raw_text_mixed(self):
        """Unresolved ingredients with both meat and fish → 'mixed'."""
        rows = [
            _ingredient_row(ingredient_id=None, raw_text="500 g Poulet"),
            _ingredient_row(ingredient_id=None, raw_text="200 g Crevetten"),
        ]
        assert compute_primary_protein(rows) == "mixed"

    def test_resolved_veggie_with_unresolved_meat_fallback(self):
        """Resolved vegetables + unresolved meat raw text → 'meat'."""
        rows = [
            _ingredient_row(ingredient_id=40),  # onion (resolved)
            _ingredient_row(ingredient_id=None, raw_text="800 g Rindfleisch"),
        ]
        assert compute_primary_protein(rows) == "meat"

    def test_unresolved_no_meat_keywords_returns_none(self):
        """Unresolved ingredient without meat/fish keywords → None."""
        rows = [_ingredient_row(ingredient_id=None, raw_text="2 cm Ingwer")]
        assert compute_primary_protein(rows) is None

    def test_empty_ingredients(self):
        assert compute_primary_protein([]) is None

    def test_vegetables_with_meat(self):
        rows = [
            _ingredient_row(ingredient_id=40),  # onion
            _ingredient_row(ingredient_id=42),  # carrot
            _ingredient_row(ingredient_id=3, quantity=500),  # beef
        ]
        assert compute_primary_protein(rows) == "beef"


# ---------------------------------------------------------------------------
# compute_taste_profile
# ---------------------------------------------------------------------------


class TestComputeTasteProfile:
    """compute_taste_profile — sweet vs savoury classification."""

    def test_dessert_course_is_sweet(self):
        assert compute_taste_profile("dessert", [], []) == "sweet"

    def test_bake_course_is_sweet(self):
        assert compute_taste_profile("bake", [], []) == "sweet"

    def test_main_course_default_savoury(self):
        assert compute_taste_profile("main", [], []) == "savoury"

    def test_none_course_default_savoury(self):
        assert compute_taste_profile(None, [], []) == "savoury"

    def test_sweet_keyword_without_meat(self):
        rows = [_ingredient_row(ingredient_id=82)]  # sugar
        assert compute_taste_profile("main", rows, ["Kuchen"]) == "sweet"

    def test_sweet_keyword_with_meat_is_sweet_savoury(self):
        rows = [_ingredient_row(ingredient_id=1)]  # chicken
        assert compute_taste_profile("main", rows, ["süss"]) == "sweet-savoury"

    def test_sweet_ingredient_dominance(self):
        rows = [
            _ingredient_row(ingredient_id=82),  # sugar
        ]
        assert compute_taste_profile("main", rows, []) == "sweet"

    def test_savoury_with_vegetables(self):
        rows = [
            _ingredient_row(ingredient_id=40),  # onion
            _ingredient_row(ingredient_id=42),  # carrot
        ]
        assert compute_taste_profile("main", rows, []) == "savoury"


# ---------------------------------------------------------------------------
# compute_weight_class
# ---------------------------------------------------------------------------


class TestComputeWeightClass:
    """compute_weight_class — light / medium / heavy."""

    def test_starter_is_light(self):
        assert compute_weight_class("starter", None, [], []) == "light"

    def test_side_is_light(self):
        assert compute_weight_class("side", None, [], []) == "light"

    def test_long_cook_with_red_meat_is_heavy(self):
        rows = [_ingredient_row(ingredient_id=3)]  # beef
        assert compute_weight_class("main", 90, rows, [], "beef") == "heavy"

    def test_default_main_is_medium(self):
        assert compute_weight_class("main", 30, [], []) == "medium"

    def test_heavy_keywords_with_long_cook(self):
        assert compute_weight_class("main", 90, [], ["Eintopf"]) == "heavy"

    def test_light_keywords_with_no_protein(self):
        assert compute_weight_class("main", 15, [], ["Salat"], None) == "light"

    def test_none_course_medium(self):
        assert compute_weight_class(None, 30, [], []) == "medium"


# ---------------------------------------------------------------------------
# compute_cooking_method
# ---------------------------------------------------------------------------


class TestComputeCookingMethod:
    """compute_cooking_method — derived from step text."""

    def test_grill_detected(self):
        assert compute_cooking_method(["Fleisch grillieren"], []) == "grilled"

    def test_ofen_is_baked(self):
        assert compute_cooking_method(["Im Ofen 20 Min. backen"], []) == "baked"

    def test_braten_is_fried(self):
        assert compute_cooking_method(["Poulet in der Pfanne braten"], []) == "fried"

    def test_schmoren_is_braised(self):
        assert compute_cooking_method(["Fleisch 2 Stunden schmoren lassen"], []) == "braised"

    def test_dampfgaren_is_steamed(self):
        assert compute_cooking_method(["Gemüse dampfgaren"], []) == "steamed"

    def test_no_steps_is_none(self):
        assert compute_cooking_method([], []) is None

    def test_keyword_detection(self):
        assert compute_cooking_method([], ["BBQ"]) == "grilled"

    def test_most_frequent_method_wins(self):
        steps = [
            "Im Ofen backen.",
            "Nochmals im Ofen überbacken.",
            "Kurz braten.",
        ]
        assert compute_cooking_method(steps, []) == "baked"

    def test_raw_detected(self):
        assert compute_cooking_method(["Tartare anrichten"], []) == "raw"


# ---------------------------------------------------------------------------
# compute_dietary_flags
# ---------------------------------------------------------------------------


class TestComputeDietaryFlags:
    """compute_dietary_flags — multi-valued dietary classification."""

    def test_empty_ingredients_quick(self):
        flags = compute_dietary_flags([], total_minutes=20)
        assert "vegetarian" in flags
        assert "vegan" in flags
        assert "dairy-free" in flags
        assert "quick" in flags

    def test_meat_removes_vegetarian(self):
        rows = [_ingredient_row(ingredient_id=1)]  # chicken
        flags = compute_dietary_flags(rows, total_minutes=60)
        assert "vegetarian" not in flags
        assert "vegan" not in flags
        assert "quick" not in flags

    def test_dairy_removes_vegan_and_dairy_free(self):
        rows = [_ingredient_row(ingredient_id=20)]  # butter
        flags = compute_dietary_flags(rows)
        assert "vegetarian" in flags
        assert "vegan" not in flags
        assert "dairy-free" not in flags

    def test_fish_removes_vegetarian(self):
        rows = [_ingredient_row(ingredient_id=10)]  # salmon
        flags = compute_dietary_flags(rows)
        assert "vegetarian" not in flags
        assert "vegan" not in flags

    def test_quick_threshold_30_minutes(self):
        flags = compute_dietary_flags([], total_minutes=30)
        assert "quick" in flags

    def test_not_quick_over_30_minutes(self):
        flags = compute_dietary_flags([], total_minutes=31)
        assert "quick" not in flags

    def test_no_total_minutes_no_quick(self):
        flags = compute_dietary_flags([], total_minutes=None)
        assert "quick" not in flags

    def test_flags_are_sorted(self):
        flags = compute_dietary_flags([], total_minutes=20)
        assert flags == sorted(flags)

    def test_vegetables_only_is_vegan(self):
        rows = [
            _ingredient_row(ingredient_id=40),  # onion
            _ingredient_row(ingredient_id=42),  # carrot
        ]
        flags = compute_dietary_flags(rows)
        assert "vegetarian" in flags
        assert "vegan" in flags
        assert "dairy-free" in flags

    def test_unresolved_ingredients_returns_empty(self):
        """When ingredients exist but none resolved, don't falsely claim vegan."""
        rows = [_ingredient_row(ingredient_id=None)]
        flags = compute_dietary_flags(rows)
        assert flags == []

    def test_unresolved_ingredients_with_quick(self):
        """Unresolved ingredients still allow the quick flag."""
        rows = [_ingredient_row(ingredient_id=None)]
        flags = compute_dietary_flags(rows, total_minutes=20)
        assert flags == ["quick"]

    def test_unresolved_meat_raw_text_not_vegetarian(self):
        """Unresolved ingredient with meat keyword should NOT be vegetarian."""
        rows = [
            _ingredient_row(ingredient_id=None, raw_text="800 g Pouletschenkel-Steaks"),
        ]
        flags = compute_dietary_flags(rows)
        assert "vegetarian" not in flags
        assert "vegan" not in flags

    def test_unresolved_fish_raw_text_not_vegetarian(self):
        """Unresolved ingredient with fish keyword should NOT be vegetarian."""
        rows = [
            _ingredient_row(ingredient_id=None, raw_text="600 g Dorschfilet"),
        ]
        flags = compute_dietary_flags(rows)
        assert "vegetarian" not in flags
        assert "vegan" not in flags

    def test_resolved_veggie_with_unresolved_meat_not_vegetarian(self):
        """Resolved veggies + unresolved meat raw text → not vegetarian."""
        rows = [
            _ingredient_row(ingredient_id=40),  # onion (resolved)
            _ingredient_row(ingredient_id=84),  # olive oil (resolved)
            _ingredient_row(ingredient_id=None, raw_text="500 g Rindfleisch"),
        ]
        flags = compute_dietary_flags(rows)
        assert "vegetarian" not in flags
        assert "vegan" not in flags
        assert "dairy-free" in flags

    def test_resolved_veggie_with_unresolved_non_meat_is_vegan(self):
        """Resolved veggies + unresolved non-meat raw text → still vegan."""
        rows = [
            _ingredient_row(ingredient_id=40),  # onion (resolved)
            _ingredient_row(ingredient_id=None, raw_text="2 cm Ingwer"),
        ]
        flags = compute_dietary_flags(rows)
        assert "vegetarian" in flags
        assert "vegan" in flags


# ---------------------------------------------------------------------------
# compute_food_groups
# ---------------------------------------------------------------------------


class TestComputeFoodGroups:
    """compute_food_groups — true food-group tags only."""

    def test_poultry_adds_pairing_tags(self):
        rows = [_ingredient_row(ingredient_id=1)]  # chicken — pairing_tags include "poultry"
        groups = compute_food_groups(rows, "grilled", "light")
        assert "poultry" in groups
        # Cooking method and weight class are NOT mixed into food_groups —
        # they live in their own scalar columns + computed_tags.
        assert "grilled" not in groups
        assert "light" not in groups

    def test_cooking_method_not_added(self):
        """Cooking method must not pollute food_groups (issue #042)."""
        groups = compute_food_groups([], "braised", None)
        assert "braised" not in groups
        assert groups == []

    def test_weight_class_not_added(self):
        """Weight class must not pollute food_groups (issue #042)."""
        groups = compute_food_groups([], None, "heavy")
        assert "heavy" not in groups
        assert groups == []

    def test_empty_ingredients_no_method_no_weight(self):
        groups = compute_food_groups([], None, None)
        assert groups == []

    def test_results_sorted(self):
        rows = [_ingredient_row(ingredient_id=1)]  # chicken
        groups = compute_food_groups(rows, "grilled", "light")
        assert groups == sorted(groups)

    def test_non_vocab_tags_filtered(self):
        """Pairing tags outside the food-group vocab are dropped.

        Carrot's pairing_tags ("root-veg", "sweet") are not food groups —
        "sweet" is now a taste descriptor, not a food group.
        """
        rows = [_ingredient_row(ingredient_id=42)]  # carrot
        groups = compute_food_groups(rows, None, None)
        assert "root-veg" not in groups
        assert "sweet" not in groups
        assert groups == []


# ---------------------------------------------------------------------------
# build_computed_tags
# ---------------------------------------------------------------------------


class TestBuildComputedTags:
    """build_computed_tags — aggregated bag of all computed values."""

    def test_full_aggregation(self):
        tags = build_computed_tags(
            primary_protein="poultry",
            taste_profile="savoury",
            weight_class="light",
            cooking_method="grilled",
            dietary_flags=["dairy-free", "quick"],
            course="main",
            cuisine="swiss",
            difficulty="easy",
        )
        assert "poultry" in tags
        assert "savoury" in tags
        assert "light" in tags
        assert "grilled" in tags
        assert "dairy-free" in tags
        assert "quick" in tags
        assert "main" in tags
        assert "swiss" in tags
        assert "easy" in tags

    def test_deduplication(self):
        tags = build_computed_tags(
            "light",
            "savoury",
            "light",
            None,
            [],
            "main",
            None,
            None,
        )
        assert tags.count("light") == 1

    def test_none_values_excluded(self):
        tags = build_computed_tags(None, None, None, None, [], None, None, None)
        assert tags == []

    def test_sorted(self):
        tags = build_computed_tags(
            "poultry",
            "savoury",
            "light",
            "grilled",
            ["quick"],
            "main",
            "swiss",
            "easy",
        )
        assert tags == sorted(tags)

    def test_dietary_flags_included(self):
        tags = build_computed_tags(
            None,
            None,
            None,
            None,
            ["vegetarian", "vegan", "dairy-free"],
            None,
            None,
            None,
        )
        assert "vegetarian" in tags
        assert "vegan" in tags

    def test_food_groups_included(self):
        """food_groups members must be re-aggregated into computed_tags (issue #042)."""
        tags = build_computed_tags(
            None,
            None,
            None,
            None,
            [],
            None,
            None,
            None,
            ["cheese", "poultry"],
        )
        assert "cheese" in tags
        assert "poultry" in tags

    def test_food_groups_default_none(self):
        """Omitting food_groups must keep prior behaviour."""
        tags = build_computed_tags("poultry", None, None, None, [], None, None, None)
        assert tags == ["poultry"]

    def test_food_groups_deduplicated_with_protein(self):
        """Overlap between food_groups and primary_protein must be deduplicated."""
        tags = build_computed_tags(
            "poultry",
            None,
            None,
            None,
            [],
            None,
            None,
            None,
            ["poultry", "cheese"],
        )
        assert tags.count("poultry") == 1
        assert "cheese" in tags
