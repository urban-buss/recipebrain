"""Tests for ingredient normalisation."""

from __future__ import annotations

import pytest

from recipebrain.normalise.ingredients import (
    CATALOGUE,
    SEED_CATALOGUE,
    CanonicalIngredient,
    _depluralize,
    _depluralize_french,
    _strip_adjectives,
    _strip_french_adjectives,
    _strip_french_context,
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

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("200g Butter", "butter"),
            ("200 g Butter", "butter"),
            ("1.5 kg Kartoffeln", "potato"),
            ("2 EL Olivenöl", "olive-oil"),
            ("1 TL Salz", "salt"),
            ("3 dl Rahm", "cream"),
            ("100ml Kokosmilch", "coconut-milk"),
            ("½ Bund Petersilie", "parsley"),
            ("1 Prise Muskatnuss", "nutmeg"),
        ],
    )
    def test_quantity_unit_prefix_stripped(self, raw: str, expected: str) -> None:
        """Regression test for issue #016: inputs with quantity+unit prefixes."""
        assert normalise_ingredient(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Issue #052: vague quantity modifiers should not prevent matching.
            ("wenig Pfeffer", "pepper-black"),
            ("etwas Salz", "salt"),
            ("reichlich Butter", "butter"),
            ("viel Wasser", "water"),
            ("etwas Petersilie", "parsley"),
            ("ein wenig Pfeffer", "pepper-black"),
            ("sehr wenig Salz", "salt"),
            ("genügend Mehl", "flour"),
        ],
    )
    def test_vague_quantity_modifier_stripped(self, raw: str, expected: str) -> None:
        """Regression test for issue #052: vague quantity modifiers like 'wenig'."""
        assert normalise_ingredient(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Issue #045: Swiss meat-cut aliases that previously failed to match.
            ("Pouletfleisch", "chicken-breast"),
            ("Pouletbrust-Charbonnade", "chicken-breast"),
            ("Pouletschenkel-Steaks", "chicken-thigh"),
            ("Pouletschenkel-Steak", "chicken-thigh"),
            ("Schweinskoteletts", "pork-chop"),
            ("Schweinsplätzli", "pork-chop"),
            ("Lammnierstück", "lamb"),
            ("Lammnierstücke", "lamb"),
            ("T-Bone-Steak", "beef-steak"),
            ("T-Bone-Steaks", "beef-steak"),
            ("Rindshohrücken", "beef-steak"),
            ("Fleischtomate", "tomato"),
            ("Fleischtomaten", "tomato"),
            ("1 Fleischtomate", "tomato"),
            ("Oreganoblättchen", "oregano"),
            ("Sardellenfilet", "anchovy"),
            ("Sardellenfilets", "anchovy"),
        ],
    )
    def test_swiss_meat_cut_aliases(self, raw: str, expected: str) -> None:
        """Regression test for issue #045: Swiss meat-cut and produce aliases."""
        assert normalise_ingredient(raw) == expected


class TestSwissMeatCutRawText:
    """Regression tests for issue #045: full raw text with quantities/qualifiers."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Bare count stripping (no unit between number and ingredient)
            ("4 Schweinshals-Steaks (je ca. 200 g)", "pork-chop"),
            ("8 Rindsplätzli (z.B. Eckstück, je ca. 80 g)", "beef-steak"),
            ("16 Pouletflügeli", "chicken-wing"),
            ("4 Bauernbratwürste (z.B. Pro Montagna)", "sausage-bratwurst"),
            ("2 Schweinskoteletts (je ca. 200 g)", "pork-chop"),
            ("4 Schweinsbratwürste", "sausage-bratwurst"),
            # Tranchen as quantity unit
            ("8 Tranchen Bratspeck", "bacon"),
            ("4 Tranchen Hinterschinken", "ham"),
            # "in Tranchen" / "am Stück" trailing qualifier stripping
            ("130 g Bratspeck in Tranchen", "bacon"),
            ("200 g Schinken in Tranchen", "ham"),
            ("800 g Entrecôte am Stück (z. B. knochengereift)", "beef-steak"),
            ("275 g Bauernspeck am Stück", "bacon"),
            # "ohne Haut" stripping with broader parenthetical removal
            ("600 g Lachsfilet ohne Haut (Bio)", "salmon-fillet"),
            ("4 Lachsfilets ohne Haut (je ca. 160 g), graue Fettschicht entfernt", "salmon-fillet"),
            ("800 g Pouletschenkel-Steaks ohne Haut", "chicken-thigh"),
            # "oder" alternative stripping
            ("100 g Pancetta oder Speck", "pancetta"),
            # Trailing comma stripping (prep instructions)
            ("12 Schweinsplätzli (z. B. Hals, je ca. 100 g), flach geklopft", "pork-chop"),
            ("250 g Lachsfilet ohne Haut , in ca. 2 cm grossen Würfeln", "salmon-fillet"),
            # Adjective stripping ("geschnetzeltes", "rohe")
            ("250 g geschnetzeltes Pouletfleisch", "chicken-breast"),
            ("12 geschälte rohe Crevettenschwänze", "shrimp"),
            # New catalogue entries
            ("800 g Schweinshals", "pork-neck"),
            ("1.2 kg Kalbsbraten (z. B. Schulter)", "veal-roast"),
            ("4 Spareribs (Schweinsbrustspitz-Rippchen)", "spareribs"),
            ("1.5 kg Spareribs am Stück (Schweinsbrustspitz-Rippchen)", "spareribs"),
            ("100 g Bündnerfleisch", "bundnerfleisch"),
            ("8 Felchenfilets (je ca. 60 g)", "char-fillet"),
            ("1 Dose Sardellenfilets (ca. 25 g), kalt abgespült", "anchovy"),
            # New aliases
            ("4 Lachstranchen mit Haut (MSC, je ca. 150 g)", "salmon-fillet"),
            ("160 g Speckwürfeli", "bacon"),
            ("150 g Schinkenwürfeli", "ham"),
            ("80 g Schinkenspeck in Tranchen (Bacon)", "ham"),
            ("4 Pouletbrust-Charbonnade (je ca. 70 g)", "chicken-breast"),
            ("50 g Rohschinken in Tranchen", "prosciutto"),
            ("600 g Lammnierstücke", "lamb"),
            ("1.2 kg Rindshohrücken", "beef-steak"),
        ],
    )
    def test_raw_text_resolves(self, raw: str, expected: str) -> None:
        """Full raw ingredient text with quantities/qualifiers resolves correctly."""
        assert normalise_ingredient(raw) == expected


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
        """Catalogue should have at least 280 entries per v0.0.6 spec."""
        assert len(SEED_CATALOGUE) >= 280

    def test_catalogue_alias(self) -> None:
        """CATALOGUE should be an alias for SEED_CATALOGUE."""
        assert CATALOGUE is SEED_CATALOGUE

    def test_required_keys_present(self) -> None:
        """Keys required by the spec must be in the catalogue."""
        keys = {item.key for item in SEED_CATALOGUE}
        assert "harissa" in keys
        assert "stock-beef" in keys
        assert "pomegranate-seeds" in keys


# ---------------------------------------------------------------------------
# Tests: French ingredient resolution (issue #020)
# ---------------------------------------------------------------------------


class TestFrenchContextStripping:
    """Test that French articles, prepositions, and quantity phrases are stripped."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("un peu de poivre", "poivre"),
            ("du beurre", "beurre"),
            ("de la farine", "farine"),
            ("des oignons", "oignons"),
            ("de l'huile", "huile"),
            ("une pincee de sel", "sel"),
            ("un filet de citron", "citron"),
            ("une poignee de persil", "persil"),
        ],
    )
    def test_strip_french_context(self, input_text: str, expected: str) -> None:
        from recipebrain.normalise.ingredients import _normalise

        normalised = _normalise(input_text)
        assert _strip_french_context(normalised) == expected


class TestFrenchAdjectiveStripping:
    """Test that French adjectives are stripped from ingredient text."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("poivre noir", "poivre"),
            ("petit oignon", "oignon"),
            ("sel fin", "sel"),
            ("creme fraiche", "creme"),
        ],
    )
    def test_strip_french_adjectives(self, input_text: str, expected: str) -> None:
        assert _strip_french_adjectives(input_text) == expected


class TestFrenchDepluralize:
    """Test French plural-to-singular conversion."""

    def test_s_suffix(self) -> None:
        candidates = _depluralize_french("oignons")
        assert "oignon" in candidates

    def test_x_suffix(self) -> None:
        candidates = _depluralize_french("choux")
        assert "chou" in candidates

    def test_aux_to_al(self) -> None:
        candidates = _depluralize_french("animaux")
        assert "animal" in candidates

    def test_short_word_not_depluralized(self) -> None:
        # Words of 3 chars or less should not be depluralized
        candidates = _depluralize_french("les")
        assert candidates == []


class TestFrenchIngredientResolution:
    """Integration tests: French ingredient lines should resolve to canonical keys.

    These are the exact patterns from issue #020 that were failing.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Direct French display names (already indexed)
            ("Beurre", "butter"),
            ("Sel", "salt"),
            ("Poivre", "pepper-black"),
            ("Farine", "flour"),
            ("Oignon", "onion"),
            ("Persil", "parsley"),
            ("Ail", "garlic"),
            ("Riz", "rice"),
            ("Lait", "milk"),
            # With articles/prepositions
            ("du beurre", "butter"),
            ("du sel", "salt"),
            ("du poivre", "pepper-black"),
            ("de la farine", "flour"),
            ("de l'ail", "garlic"),
            # With quantity phrases (from issue description)
            ("un peu de poivre", "pepper-black"),
            ("une pincée de sel", "salt"),
            # With French elided forms
            ("d'huile d'olive", "olive-oil"),
            # French plurals
            ("oignons", "onion"),
            ("carottes", "carrot"),
            ("tomates", "tomato"),
            # French display_fr names
            ("Huile d'olive", "olive-oil"),
            ("Crème", "cream"),
            ("Citron", "lemon"),
            ("Pomme de terre", "potato"),
            ("Viande hachée", "beef-minced"),
            ("Bouillon de poulet", "stock-chicken"),
            ("Vin blanc", "white-wine"),
            ("Vin rouge", "red-wine"),
        ],
    )
    def test_french_ingredients_resolve(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # French quantity+unit prefix patterns from issue
            ("0.5 c.c. de sel", "salt"),
            ("1 pincée de sel", "salt"),
            ("2 c.s. de beurre", "butter"),
            ("3 gousses d'ail", "garlic"),
        ],
    )
    def test_french_quantity_unit_prefix(self, raw: str, expected: str) -> None:
        assert normalise_ingredient(raw) == expected
