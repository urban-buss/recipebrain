"""Tests for the ingredient line parser."""

from __future__ import annotations

import pytest

from recipebrain.parse.ingredient_line import ParsedIngredient, parse_ingredient_line


class TestParseIngredientLine:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "200 g Pouletbrust, in Würfeln",
                ParsedIngredient(200.0, "g", "Pouletbrust", "in Würfeln"),
            ),
            (
                "2 EL Olivenöl",
                ParsedIngredient(2.0, "EL", "Olivenöl", None),
            ),
            (
                "1 TL Salz",
                ParsedIngredient(1.0, "TL", "Salz", None),
            ),
            (
                "500 ml Bouillon",
                ParsedIngredient(500.0, "ml", "Bouillon", None),
            ),
            (
                "1.5 kg Rindsbraten",
                ParsedIngredient(1.5, "kg", "Rindsbraten", None),
            ),
            (
                "2 dl Rahm",
                ParsedIngredient(2.0, "dl", "Rahm", None),
            ),
            (
                "1 Bund Petersilie",
                ParsedIngredient(1.0, "Bund", "Petersilie", None),
            ),
            (
                "3 Zehen Knoblauch, fein gehackt",
                ParsedIngredient(3.0, "Zehe", "Knoblauch", "fein gehackt"),
            ),
            (
                "1 Prise Muskatnuss",
                ParsedIngredient(1.0, "Prise", "Muskatnuss", None),
            ),
        ],
    )
    def test_standard_patterns(self, line, expected):
        assert parse_ingredient_line(line) == expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "½ Zitrone, Saft davon",
                ParsedIngredient(0.5, None, "Zitrone", "Saft davon"),
            ),
            (
                "¼ TL Zimt",
                ParsedIngredient(0.25, "TL", "Zimt", None),
            ),
            (
                "1½ dl Milch",
                ParsedIngredient(1.5, "dl", "Milch", None),
            ),
        ],
    )
    def test_fractions(self, line, expected):
        assert parse_ingredient_line(line) == expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "Salz und Pfeffer",
                ParsedIngredient(None, None, "Salz und Pfeffer", None),
            ),
            (
                "Butter zum Einfetten",
                ParsedIngredient(None, None, "Butter zum Einfetten", None),
            ),
        ],
    )
    def test_no_quantity(self, line, expected):
        assert parse_ingredient_line(line) == expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "2 Eier",
                ParsedIngredient(2.0, None, "Eier", None),
            ),
            (
                "4 Tomaten, halbiert",
                ParsedIngredient(4.0, None, "Tomaten", "halbiert"),
            ),
        ],
    )
    def test_quantity_no_unit(self, line, expected):
        assert parse_ingredient_line(line) == expected

    def test_parenthetical_prep_note(self):
        result = parse_ingredient_line("1 Zitrone (nur Saft)")
        assert result.ingredient == "Zitrone"
        assert result.prep_note == "nur Saft"

    def test_decimal_with_comma(self):
        result = parse_ingredient_line("0,5 dl Essig")
        assert result.quantity == 0.5
        assert result.unit == "dl"
        assert result.ingredient == "Essig"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ingredient_line("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_ingredient_line("   ")

    def test_strips_whitespace(self):
        result = parse_ingredient_line("  200 g Mehl  ")
        assert result.quantity == 200.0
        assert result.unit == "g"
        assert result.ingredient == "Mehl"


class TestEdgeCases:
    def test_unit_with_period(self):
        # Some sources write "EL." with a period
        result = parse_ingredient_line("2 EL. Butter")
        assert result.unit == "EL"
        assert result.ingredient == "Butter"

    def test_stk_unit(self):
        result = parse_ingredient_line("3 Stk Zwiebeln")
        assert result.unit == "Stück"
        assert result.ingredient == "Zwiebeln"

    def test_multiple_commas(self):
        result = parse_ingredient_line("200 g Käse, gerieben, für die Kruste")
        assert result.ingredient == "Käse"
        assert result.prep_note == "gerieben, für die Kruste"

    def test_package_unit(self):
        result = parse_ingredient_line("1 Packung Blätterteig")
        assert result.unit == "Packung"
        assert result.ingredient == "Blätterteig"


class TestOptionalDetection:
    @pytest.mark.parametrize(
        ("line", "expected_ingredient", "expected_optional"),
        [
            ("evt. etwas Petersilie", "Petersilie", True),
            ("2 EL Schnittlauch, optional", "Schnittlauch", True),
            ("Muskatnuss, nach Belieben", "Muskatnuss", True),
            ("evtl. 1 TL Zucker", "Zucker", True),
            ("1 Prise Salz, fakultativ", "Salz", True),
            ("nach Belieben: Schnittlauch", "Schnittlauch", True),
            # Issue #064: expanded German optional markers
            ("Pfeffer nach Bedarf", "Pfeffer", True),
            ("nach Bedarf Salz", "Salz", True),
            ("ev. einige Tropfen Tabasco", "einige Tropfen Tabasco", True),
            ("eventuell 1 TL Senf", "Senf", True),
            ("zum Garnieren frische Kräuter", "frische Kräuter", True),
            ("Minze, zum Dekorieren", "Minze", True),
            ("Puderzucker, zur Dekoration", "Puderzucker", True),
            ("wer mag: Chili", "Chili", True),
            ("wer möchte: 1 EL Crème fraîche", "Crème fraîche", True),
        ],
    )
    def test_detects_optional_markers(self, line, expected_ingredient, expected_optional):
        result = parse_ingredient_line(line)
        assert result.optional is expected_optional
        assert result.ingredient == expected_ingredient

    @pytest.mark.parametrize(
        ("line",),
        [
            ("200 g Pouletbrust",),
            ("Salz und Pfeffer",),
            ("3 Eier",),
            ("1 Bund Petersilie",),
        ],
    )
    def test_non_optional_ingredients(self, line):
        result = parse_ingredient_line(line)
        assert result.optional is False

    def test_optional_with_quantity_and_unit(self):
        result = parse_ingredient_line("evt. 2 dl Rahm")
        assert result.optional is True
        assert result.quantity == 2.0
        assert result.unit == "dl"
        assert result.ingredient == "Rahm"

    def test_optional_marker_stripped_from_ingredient(self):
        result = parse_ingredient_line("Petersilie, optional")
        assert result.optional is True
        assert "optional" not in result.ingredient
        assert result.ingredient == "Petersilie"

    def test_nach_belieben_colon_syntax(self):
        result = parse_ingredient_line("nach Belieben: 1 EL Honig")
        assert result.optional is True
        assert result.ingredient == "Honig"
        assert result.quantity == 1.0
        assert result.unit == "EL"

    def test_ev_dot_marker_stripped(self):
        result = parse_ingredient_line("ev. einige Tropfen Tabasco")
        assert result.optional is True
        assert "ev." not in result.ingredient

    def test_nach_bedarf_nulls_quantity(self):
        result = parse_ingredient_line("Pfeffer nach Bedarf")
        assert result.optional is True
        assert result.quantity is None
        assert result.unit is None

    def test_zum_garnieren_stripped(self):
        result = parse_ingredient_line("zum Garnieren frische Kräuter")
        assert result.optional is True
        assert "Garnieren" not in result.ingredient

    def test_nach_belieben_puderzucker(self):
        result = parse_ingredient_line("nach Belieben Puderzucker")
        assert result.optional is True
        assert result.ingredient == "Puderzucker"
        assert result.quantity is None


class TestFrenchUnits:
    """French unit abbreviation parsing (issue #022)."""

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "3 c.s. de sucre",
                ParsedIngredient(3.0, "EL", "sucre", None),
            ),
            (
                "2 c.c. de sel",
                ParsedIngredient(2.0, "TL", "sel", None),
            ),
            (
                "1 c. à s. de beurre",
                ParsedIngredient(1.0, "EL", "beurre", None),
            ),
            (
                "½ c. à c. de cannelle",
                ParsedIngredient(0.5, "TL", "cannelle", None),
            ),
            (
                "1 pincée de sel",
                ParsedIngredient(1.0, "Prise", "sel", None),
            ),
            (
                "2 branches de thym",
                ParsedIngredient(2.0, "Zweig", "thym", None),
            ),
            (
                "1 brin de romarin",
                ParsedIngredient(1.0, "Zweig", "romarin", None),
            ),
            (
                "4 tranches de jambon",
                ParsedIngredient(4.0, "Scheibe", "jambon", None),
            ),
            (
                "2 gousses d'ail, émincées",
                ParsedIngredient(2.0, "Zehe", "ail", "émincées"),
            ),
            (
                "1 botte de persil",
                ParsedIngredient(1.0, "Bund", "persil", None),
            ),
            (
                "1 bouquet de basilic",
                ParsedIngredient(1.0, "Bund", "basilic", None),
            ),
            (
                "1 sachet de levure",
                ParsedIngredient(1.0, "Packung", "levure", None),
            ),
        ],
    )
    def test_french_units(self, line, expected):
        assert parse_ingredient_line(line) == expected

    def test_french_cs_without_dots(self):
        result = parse_ingredient_line("2 cs de moutarde")
        assert result.unit == "EL"
        assert result.ingredient == "moutarde"

    def test_french_cc_without_dots(self):
        result = parse_ingredient_line("1 cc de vanille")
        assert result.unit == "TL"
        assert result.ingredient == "vanille"

    def test_french_optional_facultatif(self):
        result = parse_ingredient_line("1 pincée de muscade, facultatif")
        assert result.optional is True
        assert result.unit == "Prise"
        assert result.ingredient == "muscade"

    def test_french_optional_selon_gout(self):
        result = parse_ingredient_line("selon goût: sel et poivre")
        assert result.optional is True


class TestVagueQuantityStripping:
    """Regression tests for issue #052: vague quantity modifiers stripped correctly."""

    @pytest.mark.parametrize(
        ("line", "expected_ingredient"),
        [
            ("wenig Pfeffer", "Pfeffer"),
            ("etwas Salz", "Salz"),
            ("reichlich Butter", "Butter"),
            ("viel Wasser", "Wasser"),
            ("genügend Mehl", "Mehl"),
            ("ein wenig Pfeffer", "Pfeffer"),
            ("sehr wenig Salz", "Salz"),
        ],
    )
    def test_vague_quantity_stripped(self, line, expected_ingredient):
        result = parse_ingredient_line(line)
        assert result.ingredient == expected_ingredient
        assert result.quantity is None
        assert result.unit is None

    def test_vague_quantity_with_trailing_descriptor(self):
        result = parse_ingredient_line("wenig Pfeffer aus der Mühle")
        assert result.ingredient == "Pfeffer aus der Mühle"

    def test_french_du_preposition(self):
        result = parse_ingredient_line("3 c.s. du vinaigre")
        assert result.unit == "EL"
        assert result.ingredient == "vinaigre"

    @pytest.mark.parametrize(
        ("line", "qty", "unit", "ing"),
        [
            ("1 cuillère à soupe de beurre", 1, "EL", "beurre"),
            ("2 cuillères à soupe de sucre", 2, "EL", "sucre"),
            ("1 cuillère à café de sel", 1, "TL", "sel"),
            ("3 cuillères à café de cannelle", 3, "TL", "cannelle"),
            ("1 c.à.s. de beurre", 1, "EL", "beurre"),
            ("2 c.à.c. de sel", 2, "TL", "sel"),
            ("1 c.à s. de moutarde", 1, "EL", "moutarde"),
            ("1 c.à c. de vanille", 1, "TL", "vanille"),
            ("2 pincées de sel", 2, "Prise", "sel"),
        ],
    )
    def test_french_multiword_units(self, line, qty, unit, ing):
        """Regression test for issue #027: French multi-word units."""
        r = parse_ingredient_line(line)
        assert (r.quantity, r.unit, r.ingredient) == (qty, unit, ing)


class TestShimImport:
    def test_import_from_flat_module(self):
        from recipebrain.parse_ingredient_line import parse_ingredient_line as fn

        assert callable(fn)
        result = fn("200 g Mehl")
        assert result.quantity == 200.0
        assert result.unit == "g"
        assert result.ingredient == "Mehl"
