"""Tests for the Fooby source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recipebrain.settings import ScrapingConfig, Settings, SourceConfig
from recipebrain.sources.fooby import (
    FoobyAdapter,
    _detect_language,
    _extract_cuisine_from_tags,
    _is_recipe_url,
    _parse_sitemap_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"

_TEST_SETTINGS = Settings(scraping=ScrapingConfig(rate_limit_seconds=0))


def _adapter_with_mock_client() -> tuple[FoobyAdapter, MagicMock]:
    """Create an adapter with a mocked HTTP client."""
    adapter = FoobyAdapter(settings=_TEST_SETTINGS)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


class TestFoobyDiscover:
    def test_discover_yields_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("fooby_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        # Default config is DE-only: fixture has 2 DE recipe URLs
        assert len(urls) == 2
        assert all("/de/rezepte/" in url for url in urls)

    def test_discover_yields_all_languages_when_configured(self):
        settings = Settings(
            scraping=ScrapingConfig(rate_limit_seconds=0),
            sources={"fooby": SourceConfig(languages=["de", "fr"])},
        )
        adapter = FoobyAdapter(settings=settings)
        mock_client = MagicMock()
        adapter._client = mock_client

        sitemap_xml = FIXTURES.joinpath("fooby_sitemap.xml").read_text(encoding="utf-8")
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        # DE+FR configured: 2 DE + 1 FR recipe URLs
        assert len(urls) == 3
        assert any("/fr/recettes/" in url for url in urls)

    def test_discover_filters_non_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("fooby_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        assert "https://fooby.ch/de/ueber-uns" not in urls
        assert "https://fooby.ch/de/tipps-tricks/messer-schaerfen" not in urls


class TestFoobyFetch:
    def test_fetch_parses_recipe(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/de/rezepte/pouletbrust-12345")

        assert recipe.title == "Pouletbrust mit Lauch und Reis"
        assert len(recipe.ingredients_raw) == 6
        assert len(recipe.steps_raw) == 6
        assert recipe.language == "de"
        assert recipe.source_url == "https://fooby.ch/de/rezepte/pouletbrust-12345"

    def test_fetch_raises_on_no_jsonld(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body>No recipe</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No Recipe JSON-LD found"):
            adapter.fetch("https://fooby.ch/de/rezepte/bad-page")

    def test_fetch_detects_french_language(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/fr/recettes/poulet-12345")

        assert recipe.language == "fr"

    def test_fetch_extracts_classification_from_jsonld(self):
        html = FIXTURES.joinpath("fooby_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/de/rezepte/pouletbrust-12345")

        assert recipe.category == "Hauptgericht"
        assert recipe.cuisine == "Swiss"
        assert "poulet" in recipe.keywords
        assert "einfach" in recipe.keywords

    def test_fetch_supplements_keywords_from_html_when_jsonld_empty(self):
        # JSON-LD without keywords, but with meta keywords in HTML
        html = """<!DOCTYPE html><html><head>
        <meta name="keywords" content="schnell, einfach, alltagsküche">
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Recipe","name":"Test",
         "recipeIngredient":["100g Mehl"],"recipeInstructions":[{"@type":"HowToStep","text":"Mix."}]}
        </script></head><body></body></html>"""

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/de/rezepte/test-123")

        assert recipe.keywords == ["schnell", "einfach", "alltagsküche"]

    def test_fetch_supplements_cuisine_from_html_when_jsonld_empty(self):
        # JSON-LD without recipeCuisine, but with cuisine tag in HTML
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Recipe","name":"Pad Thai",
         "recipeIngredient":["200g Reisnudeln"],"recipeInstructions":[{"@type":"HowToStep","text":"Fry."}]}
        </script></head><body>
        <div class="recipe-tags"><a href="/tag/thai">Thai</a><a href="/tag/schnell">Schnell</a></div>
        </body></html>"""

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/de/rezepte/pad-thai-456")

        assert recipe.cuisine == "thai"

    def test_fetch_does_not_override_jsonld_cuisine(self):
        # JSON-LD provides recipeCuisine, HTML also has cuisine tag — JSON-LD wins
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Recipe","name":"Pasta",
         "recipeCuisine":"Italian",
         "recipeIngredient":["200g Spaghetti"],"recipeInstructions":[{"@type":"HowToStep","text":"Boil."}]}
        </script></head><body>
        <div class="recipe-tags"><a href="/tag/mediterran">Mediterran</a></div>
        </body></html>"""

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://fooby.ch/de/rezepte/pasta-789")

        assert recipe.cuisine == "Italian"


class TestHelpers:
    def test_parse_sitemap_urls(self):
        xml = FIXTURES.joinpath("fooby_sitemap.xml").read_text(encoding="utf-8")
        urls = _parse_sitemap_urls(xml)
        assert len(urls) == 5

    def test_is_recipe_url_true(self):
        assert _is_recipe_url("https://fooby.ch/de/rezepte/test-123")

    def test_is_recipe_url_true_french(self):
        assert _is_recipe_url("https://fooby.ch/fr/recettes/poulet-12345")

    def test_is_recipe_url_true_italian(self):
        assert _is_recipe_url("https://fooby.ch/it/ricette/pollo-12345")

    def test_is_recipe_url_false(self):
        assert not _is_recipe_url("https://fooby.ch/de/ueber-uns")

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://fooby.ch/de/rezepte/test", "de"),
            ("https://fooby.ch/fr/recettes/test", "fr"),
            ("https://fooby.ch/it/ricette/test", "it"),
            ("https://fooby.ch/rezepte/test", "de"),
        ],
    )
    def test_detect_language(self, url, expected):
        assert _detect_language(url) == expected


class TestExtractCuisineFromTags:
    """Tests for _extract_cuisine_from_tags with the _FOOBY_CUISINE_MAP."""

    def test_german_single_word_maps_to_english(self):
        from selectolax.parser import HTMLParser

        html = '<div class="recipe-tags"><a>Asiatisch</a></div>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == "asian"

    def test_german_multi_word_maps_to_english(self):
        from selectolax.parser import HTMLParser

        html = '<meta name="keywords" content="Schweizer Küche,Hauptgericht"/>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == "swiss"

    def test_non_cuisine_keyword_blocked(self):
        from selectolax.parser import HTMLParser

        html = '<meta name="keywords" content="Schnelle Küche,Hauptgericht"/>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == ""

    def test_raclette_not_returned_as_cuisine(self):
        from selectolax.parser import HTMLParser

        html = '<meta name="keywords" content="Raclette,Hauptgericht"/>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == ""

    def test_italian_via_meta_keywords(self):
        from selectolax.parser import HTMLParser

        html = '<meta name="keywords" content="Pasta,Italienische Küche"/>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == "italian"

    def test_english_value_passes_through(self):
        from selectolax.parser import HTMLParser

        html = '<div class="recipe-tags"><a>Mediterranean</a></div>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == "mediterranean"

    def test_no_cuisine_keywords_returns_empty(self):
        from selectolax.parser import HTMLParser

        html = '<meta name="keywords" content="Dessert,Vegetarisch"/>'
        assert _extract_cuisine_from_tags(HTMLParser(html)) == ""


# ---------------------------------------------------------------------------
# Tests: brand prefix stripping (issue #068)
# ---------------------------------------------------------------------------


class TestStripBrandPrefix:
    """_strip_brand_prefix removes Coop retail brand prefixes."""

    def test_fine_food_prefix(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        assert _strip_brand_prefix("Fine Food Manchego Gran Reserva") == "Manchego Gran Reserva"

    def test_fine_food_sherry(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        assert _strip_brand_prefix("Fine Food Sherry-Weinessig") == "Sherry-Weinessig"

    def test_naturaplan_prefix(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        assert _strip_brand_prefix("Naturaplan Joghurt natur") == "Joghurt natur"

    def test_betty_bossi_prefix(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        assert _strip_brand_prefix("Betty Bossi Pasta") == "Pasta"

    def test_no_prefix_unchanged(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        assert _strip_brand_prefix("Butter") == "Butter"
        assert _strip_brand_prefix("200 g Mehl") == "200 g Mehl"

    def test_prefix_case_sensitive(self):
        from recipebrain.sources.fooby import _strip_brand_prefix

        # Only strips when case matches exactly
        assert _strip_brand_prefix("fine food Manchego") == "fine food Manchego"


# ---------------------------------------------------------------------------
# Tests: equipment filtering (issue #070)
# ---------------------------------------------------------------------------


class TestIsEquipment:
    """_is_equipment detects cooking equipment in ingredient text."""

    def test_holzspiesschen(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("Holzspiesschen") is True
        assert _is_equipment("4 Holzspiesschen") is True

    def test_alu_grillschalen(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("Alu-Grillschalen") is True

    def test_grillholzbrettchen(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("1 Zedern Grillholzbrettchen") is True

    def test_kuechenschnur(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("Küchenschnur") is True

    def test_backpapier(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("Backpapier") is True

    def test_food_not_filtered(self):
        from recipebrain.sources.fooby import _is_equipment

        assert _is_equipment("200 g Mehl") is False
        assert _is_equipment("Butter") is False
        assert _is_equipment("Spinat") is False

    def test_holundersaft_not_filtered(self):
        from recipebrain.sources.fooby import _is_equipment

        # "Holunder" must not match "grillholz" — substring match is targeted
        assert _is_equipment("Holundersaft") is False
