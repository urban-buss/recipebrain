"""Tests for the Migusto source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.migusto import (
    MigustoAdapter,
    _detect_language,
    _is_recipe_url,
    _parse_sitemap_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"

_TEST_SETTINGS = Settings(scraping=ScrapingConfig(rate_limit_seconds=0))


def _adapter_with_mock_client() -> tuple[MigustoAdapter, MagicMock]:
    """Create an adapter with a mocked HTTP client."""
    adapter = MigustoAdapter(settings=_TEST_SETTINGS)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


class TestMigustoDiscover:
    def test_discover_yields_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("migusto_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        assert len(urls) == 3
        assert all("/rezepte/" in url or "/recettes/" in url for url in urls)

    def test_discover_filters_non_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("migusto_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        assert "https://migusto.migros.ch/de/magazin/kochtipps" not in urls
        assert "https://migusto.migros.ch/de/ueber-uns" not in urls


class TestMigustoFetch:
    def test_fetch_parses_recipe(self):
        html = FIXTURES.joinpath("migusto_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/de/rezepte/pasta-carbonara")

        assert recipe.title == "Pasta Carbonara"
        assert len(recipe.ingredients_raw) == 5
        assert len(recipe.steps_raw) == 4
        assert recipe.language == "de"
        assert recipe.source_url == "https://migusto.migros.ch/de/rezepte/pasta-carbonara"

    def test_fetch_raises_on_no_jsonld(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body>No recipe</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No Recipe JSON-LD found"):
            adapter.fetch("https://migusto.migros.ch/de/rezepte/bad")

    def test_fetch_detects_french(self):
        html = FIXTURES.joinpath("migusto_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/fr/recettes/pates-carbonara")
        assert recipe.language == "fr"

    def test_fetch_extracts_keywords_from_jsonld(self):
        html = FIXTURES.joinpath("migusto_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/de/rezepte/pasta-carbonara")

        assert "pasta" in recipe.keywords
        assert "italienisch" in recipe.keywords

    def test_fetch_supplements_category_from_html(self):
        # JSON-LD without recipeCategory, HTML has article:section
        html = FIXTURES.joinpath("migusto_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/de/rezepte/pasta-carbonara")

        # JSON-LD has no recipeCategory, so HTML fallback should fill it
        assert recipe.category == "Hauptgerichte"

    def test_fetch_supplements_cuisine_from_tags(self):
        # JSON-LD without recipeCuisine, HTML has recipe-tags
        html = FIXTURES.joinpath("migusto_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/de/rezepte/pasta-carbonara")

        # JSON-LD has no recipeCuisine, so HTML fallback should fill it
        assert recipe.cuisine == "Italienisch"

    def test_fetch_supplements_difficulty_from_tags(self):
        # JSON-LD without difficulty, HTML has difficulty tag
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Recipe","name":"Pasta",
         "recipeIngredient":["200g Spaghetti"],"recipeInstructions":[{"@type":"HowToStep","text":"Boil."}],
         "keywords":"pasta, schnell"}
        </script></head><body>
        <div class="recipe-tags"><a href="/tag/einfach">Einfach</a><a href="/tag/schnell">Schnell</a></div>
        </body></html>"""

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://migusto.migros.ch/de/rezepte/pasta-easy")

        assert recipe.difficulty == "Einfach"


class TestHelpers:
    def test_parse_sitemap_urls(self):
        xml = FIXTURES.joinpath("migusto_sitemap.xml").read_text(encoding="utf-8")
        urls = _parse_sitemap_urls(xml)
        assert len(urls) == 5

    def test_is_recipe_url_de(self):
        assert _is_recipe_url("https://migusto.migros.ch/de/rezepte/pasta")

    def test_is_recipe_url_fr(self):
        assert _is_recipe_url("https://migusto.migros.ch/fr/recettes/pates")

    def test_is_recipe_url_false(self):
        assert not _is_recipe_url("https://migusto.migros.ch/de/magazin/tipps")

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://migusto.migros.ch/de/rezepte/test", "de"),
            ("https://migusto.migros.ch/fr/recettes/test", "fr"),
            ("https://migusto.migros.ch/rezepte/test", "de"),
        ],
    )
    def test_detect_language(self, url, expected):
        assert _detect_language(url) == expected
