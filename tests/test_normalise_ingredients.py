"""Tests for ingredient normalisation."""

from __future__ import annotations

import pytest

from recipebrain.normalise.ingredients import (
    SEED_CATALOGUE,
    CanonicalIngredient,
    all_keys,
    catalogue_to_rows,
    get_ingredient,
    get_ingredient_id,
    normalise_ingredient,
)

# ---------------------------------------------------------------------------
# Tests: normalise_ingredient
# ---------------------------------------------------------------------------


class TestNormaliseIngredient:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Pouletbrust", "chicken-breast"),
            ("pouletbrust", "chicken-breast"),
            ("POULETBRUST", "chicken-breast"),
            ("Zwiebel", "onion"),
            ("Zwiebeln", "onion"),
            ("Knoblauch", "garlic"),
            ("Rüebli", "carrot"),
            ("Karotte", "carrot"),
            ("Kartoffel", "potato"),
            ("Kartoffeln", "potato"),
            ("Rahm", "cream"),
            ("Vollrahm", "cream"),
            ("Sahne", "cream"),
            ("Butter", "butter"),
            ("Salz", "salt"),
            ("Pfeffer", "pepper-black"),
            ("Mehl", "flour"),
            ("Olivenöl", "olive-oil"),
            ("Reis", "rice"),
            ("Spaghetti", "pasta"),
            ("Gruyère", "cheese-gruyere"),
            ("Gruyere", "cheese-gruyere"),  # accent-stripped match
            ("Emmentaler", "cheese-emmental"),
            ("Ei", "egg"),
            ("Eier", "egg"),
            ("Petersilie", "parsley"),
            ("Peterli", "parsley"),
            ("Pelati", "tomato-canned"),
            ("Tomatenpüree", "tomato-paste"),
            ("Bouillon", "stock-chicken"),
            ("Weisswein", "white-wine"),
            ("Lachsfilet", "salmon-fillet"),
            ("Crevetten", "shrimp"),
            # French names
            ("Beurre", "butter"),
            ("Oignon", "onion"),
            ("Crème entière", "cream"),
            # English names
            ("Chicken breast", "chicken-breast"),
            ("Butter", "butter"),
        ],
    )
    def test_known_ingredients(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected

    def test_unknown_returns_none(self) -> None:
        assert normalise_ingredient("Xylophon") is None

    def test_empty_returns_none(self) -> None:
        assert normalise_ingredient("") is None

    def test_whitespace_returns_none(self) -> None:
        assert normalise_ingredient("   ") is None


# ---------------------------------------------------------------------------
# Tests: get_ingredient
# ---------------------------------------------------------------------------


class TestGetIngredient:
    def test_existing_key(self) -> None:
        result = get_ingredient("chicken-breast")
        assert result is not None
        assert result.display_de == "Pouletbrust"
        assert result.category == "meat"

    def test_missing_key(self) -> None:
        assert get_ingredient("nonexistent") is None


# ---------------------------------------------------------------------------
# Tests: get_ingredient_id
# ---------------------------------------------------------------------------


class TestGetIngredientId:
    def test_known(self) -> None:
        result = get_ingredient_id("Pouletbrust")
        assert result == 1

    def test_alias(self) -> None:
        result = get_ingredient_id("Karotten")
        assert result == 42

    def test_unknown(self) -> None:
        assert get_ingredient_id("unknown") is None


# ---------------------------------------------------------------------------
# Tests: catalogue_to_rows
# ---------------------------------------------------------------------------


class TestCatalogueToRows:
    def test_row_count_matches_catalogue(self) -> None:
        rows = catalogue_to_rows()
        assert len(rows) == len(SEED_CATALOGUE)

    def test_row_has_all_schema_fields(self) -> None:
        rows = catalogue_to_rows()
        expected_keys = {
            "id",
            "key",
            "display_de",
            "display_fr",
            "display_it",
            "display_en",
            "category",
            "sub_category",
            "default_unit",
            "density_g_per_ml",
            "pairing_tags",
            "aliases",
        }
        for row in rows:
            assert set(row.keys()) == expected_keys

    def test_first_row_values(self) -> None:
        rows = catalogue_to_rows()
        chicken = next(r for r in rows if r["key"] == "chicken-breast")
        assert chicken["id"] == 1
        assert chicken["display_de"] == "Pouletbrust"
        assert chicken["category"] == "meat"
        assert isinstance(chicken["aliases"], list)


# ---------------------------------------------------------------------------
# Tests: all_keys
# ---------------------------------------------------------------------------


class TestAllKeys:
    def test_returns_list(self) -> None:
        keys = all_keys()
        assert isinstance(keys, list)
        assert len(keys) == len(SEED_CATALOGUE)

    def test_contains_known_keys(self) -> None:
        keys = all_keys()
        assert "chicken-breast" in keys
        assert "onion" in keys
        assert "salt" in keys


# ---------------------------------------------------------------------------
# Tests: seed catalogue integrity
# ---------------------------------------------------------------------------


class TestSeedCatalogue:
    def test_unique_ids(self) -> None:
        ids = [item.id for item in SEED_CATALOGUE]
        assert len(ids) == len(set(ids)), "Duplicate IDs in catalogue"

    def test_unique_keys(self) -> None:
        keys = [item.key for item in SEED_CATALOGUE]
        assert len(keys) == len(set(keys)), "Duplicate keys in catalogue"

    def test_all_have_display_de(self) -> None:
        for item in SEED_CATALOGUE:
            assert item.display_de, f"Missing display_de for {item.key}"

    def test_all_items_are_canonical(self) -> None:
        for item in SEED_CATALOGUE:
            assert isinstance(item, CanonicalIngredient)


class TestShimImport:
    def test_import_from_flat_module(self):
        from recipebrain.normalise_ingredients import normalise_ingredient as fn

        assert callable(fn)
        assert fn("Pouletbrust") == "chicken-breast"
