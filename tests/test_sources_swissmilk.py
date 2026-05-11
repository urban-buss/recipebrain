"""Tests for the Swissmilk source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.swissmilk import (
    SwissmilkAdapter,
    _detect_language,
    _is_recipe_url,
    _parse_sitemap_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"

_TEST_SETTINGS = Settings(scraping=ScrapingConfig(rate_limit_seconds=0))


def _adapter_with_mock_client() -> tuple[SwissmilkAdapter, MagicMock]:
    """Create an adapter with a mocked HTTP client."""
    adapter = SwissmilkAdapter(settings=_TEST_SETTINGS)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


class TestSwissmilkDiscover:
    def test_discover_yields_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("swissmilk_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        # Fixture has 3 recipe URLs, fetched from 2 sitemaps = 6 total
        assert len(urls) == 6
        assert all("/rezepte-kochideen/rezepte/" in url for url in urls)

    def test_discover_filters_non_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("swissmilk_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        non_recipe_urls = [
            "https://www.swissmilk.ch/de/nachhaltigkeit/engagement/",
            "https://www.swissmilk.ch/de/milch-produzenten/betriebe/",
        ]
        for non_recipe in non_recipe_urls:
            assert non_recipe not in urls

    def test_discover_fetches_both_sitemaps(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        list(adapter.discover())

        # Should fetch both DE and FR sitemaps
        assert mock_client.get.call_count == 2


class TestSwissmilkFetch:
    def test_fetch_parses_recipe(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        assert recipe.title == "Kartoffelgratin"
        assert len(recipe.ingredients_raw) == 7
        assert len(recipe.steps_raw) == 5
        assert recipe.language == "de"
        assert recipe.source_url == url
        assert recipe.prep_time == "45 min"
        assert recipe.cook_time == ""
        assert len(recipe.image_urls) == 1
        assert "kartoffelgratin" in recipe.image_urls[0]

    def test_fetch_raises_on_no_jsonld(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body>No recipe here</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No recipe title found"):
            adapter.fetch("https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM000/bad/")

    def test_fetch_detects_french_language(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.swissmilk.ch/fr/recettes-idees-cuisine/recettes/LM200803_37/gratin/"
        )
        assert recipe.language == "fr"


class TestHelpers:
    def test_is_recipe_url_de(self):
        assert _is_recipe_url(
            "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        )

    def test_is_recipe_url_fr(self):
        assert _is_recipe_url(
            "https://www.swissmilk.ch/fr/recettes-idees-cuisine/recettes/LM200803_37/gratin/"
        )

    def test_is_not_recipe_url(self):
        assert not _is_recipe_url("https://www.swissmilk.ch/de/nachhaltigkeit/engagement/")

    def test_detect_language_de(self):
        assert (
            _detect_language("https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM123/x/")
            == "de"
        )

    def test_detect_language_fr(self):
        assert (
            _detect_language("https://www.swissmilk.ch/fr/recettes-idees-cuisine/recettes/LM123/x/")
            == "fr"
        )

    def test_parse_sitemap_urls(self):
        xml = FIXTURES.joinpath("swissmilk_sitemap.xml").read_text(encoding="utf-8")
        urls = _parse_sitemap_urls(xml)
        assert len(urls) == 5

    def test_context_manager(self):
        adapter = SwissmilkAdapter()
        with adapter:
            pass
        assert adapter._client is None
