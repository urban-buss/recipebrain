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


class TestShimImport:
    def test_import_from_flat_module(self):
        from recipebrain.parse_ingredient_line import parse_ingredient_line as fn

        assert callable(fn)
        result = fn("200 g Mehl")
        assert result.quantity == 200.0
        assert result.unit == "g"
        assert result.ingredient == "Mehl"
