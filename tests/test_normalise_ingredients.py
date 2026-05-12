"""Tests for ingredient normalisation."""

from __future__ import annotations

import pytest

from recipebrain.normalise.ingredients import (
    SEED_CATALOGUE,
    CanonicalIngredient,
    _depluralize,
    _strip_adjectives,
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


# ---------------------------------------------------------------------------
# Tests: expanded catalogue — new entries from issue #007
# ---------------------------------------------------------------------------


class TestExpandedCatalogue:
    """Test that high-frequency missing ingredients from issue #007 now resolve."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Specifically mentioned in issue
            ("Mascarpone", "mascarpone"),
            ("Mango", "mango"),
            ("Süsskartoffeln", "sweet-potato"),
            ("Süsskartoffel", "sweet-potato"),
            ("Ramen-Nudeln", "noodles-asian"),
            ("Cervelats", "cervelat"),
            ("Cervelat", "cervelat"),
            ("Peperoncino", "chilli"),
            ("Blätterteig", "puff-pastry"),
            ("Reisblätter", "rice-paper"),
            ("Hefe", "yeast"),
            ("Kaffeepulver", "coffee"),
            ("Backpulver", "baking-powder"),
            ("Maizena", "cornstarch"),
            ("Rhabarber", "rhubarb"),
            ("Himbeeren", "raspberry"),
            # Additional expanded entries
            ("Avocado", "avocado"),
            ("Ingwer", "ginger"),
            ("Kokosmilch", "coconut-milk"),
            ("Linsen", "lentil"),
            ("Kichererbsen", "chickpea"),
            ("Couscous", "couscous"),
            ("Quinoa", "quinoa"),
            ("Tofu", "tofu"),
            ("Sojasauce", "soy-sauce"),
            ("Honig", "honey"),
            ("Mandeln", "almond"),
            ("Parmesan", "parmesan"),
            ("Feta", "feta"),
            ("Ricotta", "ricotta"),
            ("Puderzucker", "icing-sugar"),
            ("Zimt", "cinnamon"),
            ("Muskatnuss", "nutmeg"),
            ("Vanillezucker", "vanilla"),
            ("Pinienkerne", "pine-nut"),
            ("Kakaopulver", "cocoa-powder"),
            ("Erdbeeren", "strawberry"),
            ("Spargeln", "asparagus"),
            ("Kürbis", "pumpkin"),
            ("Rucola", "rocket"),
            ("Frühlingszwiebeln", "spring-onion"),
            ("Schalotten", "shallot"),
            ("Aceto balsamico", "aceto-balsamico"),
            ("Aceto balsamico bianco", "aceto-balsamico"),
            ("Lasagneblätter", "lasagne-sheets"),
            ("Polenta", "polenta"),
            ("Oliven", "olives"),
            ("Kapern", "capers"),
        ],
    )
    def test_new_catalogue_entries(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected


# ---------------------------------------------------------------------------
# Tests: adjective stripping (Phase 2 matching improvement)
# ---------------------------------------------------------------------------


class TestAdjectiveStripping:
    """Test that common German adjectives are stripped before matching."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("mehlig kochende Kartoffeln", "potato"),
            ("frische Petersilie", "parsley"),
            ("tiefgekühlte Erbsen", "pea"),
            ("getrocknete Tomaten", "dried-tomatoes"),
            ("geriebener Gruyère", "cheese-gruyere"),
            ("gehackter Knoblauch", "garlic"),
            ("frischer Ingwer", "ginger"),
            ("grosse Zwiebel", "onion"),
            ("kleine Kartoffeln", "potato"),
            ("rote Linsen", "lentil"),
            ("grüner Spargel", "asparagus"),
            ("schwarzer Pfeffer", "pepper-black"),
            ("geschälte Tomaten", "tomato"),
            ("reife Avocado", "avocado"),
            ("weisse Schokolade", "chocolate-white"),
        ],
    )
    def test_adjective_stripped_match(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected

    def test_strip_adjectives_function(self) -> None:
        assert _strip_adjectives("mehlig kochende kartoffeln") == "kartoffeln"
        assert _strip_adjectives("frische petersilie") == "petersilie"
        assert _strip_adjectives("pouletbrust") == "pouletbrust"

    def test_multiple_adjectives_stripped(self) -> None:
        # "fein gehackte" should be stripped
        assert _strip_adjectives("fein gehackte petersilie") == "petersilie"


# ---------------------------------------------------------------------------
# Tests: depluralization (Phase 2 matching improvement)
# ---------------------------------------------------------------------------


class TestDepluralization:
    """Test the plural-to-singular fallback matching."""

    def test_depluralize_n_suffix(self) -> None:
        candidates = _depluralize("kartoffeln")
        assert "kartoffel" in candidates

    def test_depluralize_s_suffix(self) -> None:
        candidates = _depluralize("cervelats")
        assert "cervelat" in candidates

    def test_depluralize_en_suffix(self) -> None:
        candidates = _depluralize("tomaten")
        assert "tomat" in candidates

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # These rely on depluralization to match
            ("Cervelats", "cervelat"),
            ("Peperoncini", "chilli"),
        ],
    )
    def test_plural_form_resolves(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected


# ---------------------------------------------------------------------------
# Tests: catalogue size meets target
# ---------------------------------------------------------------------------


class TestCatalogueSize:
    """Verify the catalogue is large enough to meet the >80% resolution target."""

    def test_minimum_catalogue_size(self) -> None:
        """Catalogue should have at least 200 entries (target: ~250)."""
        assert len(SEED_CATALOGUE) >= 200
