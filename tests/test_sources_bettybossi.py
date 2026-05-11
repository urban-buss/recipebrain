"""Tests for the Betty Bossi source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.bettybossi import (
    BettybossiAdapter,
    _detect_language,
    _is_recipe_url,
    _parse_sitemap_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"

_TEST_SETTINGS = Settings(scraping=ScrapingConfig(rate_limit_seconds=0))


def _adapter_with_mock_client() -> tuple[BettybossiAdapter, MagicMock]:
    """Create an adapter with a mocked HTTP client."""
    adapter = BettybossiAdapter(settings=_TEST_SETTINGS)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


class TestBettybossiDiscover:
    def test_discover_yields_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("bettybossi_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        # Fixture has 3 recipe URLs per sitemap, fetched from 2 sitemaps = 6 total
        assert len(urls) == 6
        assert all("/rezepte/rezept/" in url for url in urls)

    def test_discover_filters_non_recipe_urls(self):
        sitemap_xml = FIXTURES.joinpath("bettybossi_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        non_recipe_urls = [
            "https://www.bettybossi.ch/de/rezepte/kategorie/neue-rezepte/",
            "https://www.bettybossi.ch/de/magazin/artikel/was-koche-ich-heute/",
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

    def test_discover_continues_on_http_error(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock()
        )
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        assert urls == []
        assert mock_client.get.call_count == 2


class TestBettybossiFetch:
    def test_fetch_parses_recipe_via_jsonld(self):
        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
        recipe = adapter.fetch(url)

        assert recipe.title == "Kartoffelgratin"
        assert len(recipe.ingredients_raw) == 8
        assert "1 Knoblauchzehe, längs halbiert" in recipe.ingredients_raw
        assert (
            "800 g mehlig kochende Kartoffeln, in ca. 2 mm dicken Scheiben"
            in recipe.ingredients_raw
        )
        assert len(recipe.steps_raw) == 4
        assert recipe.language == "de"
        assert recipe.source_url == url
        assert recipe.prep_time == "PT25M"
        assert recipe.cook_time == "PT55M"
        assert recipe.yield_amount == "4 Personen"
        assert len(recipe.image_urls) >= 1

    def test_fetch_raises_on_no_recipe_content(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>No recipe here</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No recipe found"):
            adapter.fetch("https://www.bettybossi.ch/de/rezepte/rezept/bad-00000/")

    def test_fetch_detects_french_language(self):
        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/fr/recettes/recette/gratin-de-pommes-de-terre-10002010/"
        )
        assert recipe.language == "fr"

    def test_fetch_html_fallback_when_no_jsonld(self):
        html = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta name="description" content="Ein einfacher Gratin.">
    <meta property="og:image" content="https://media.bettybossi.ch/test.jpg">
</head>
<body>
    <h1>Einfacher Gratin</h1>
    <ul>
        <li itemprop="recipeIngredient">500 g Kartoffeln</li>
        <li itemprop="recipeIngredient">2 dl Rahm</li>
    </ul>
    <div itemprop="recipeInstructions">
        <div itemprop="text">Kartoffeln schälen und in Scheiben schneiden.</div>
        <div itemprop="text">Im Ofen gratinieren.</div>
    </div>
</body>
</html>"""
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/einfacher-gratin-99999/"
        )

        assert recipe.title == "Einfacher Gratin"
        assert len(recipe.ingredients_raw) == 2
        assert "500 g Kartoffeln" in recipe.ingredients_raw
        assert len(recipe.steps_raw) == 2
        assert recipe.description == "Ein einfacher Gratin."
        assert recipe.image_urls == ["https://media.bettybossi.ch/test.jpg"]


class TestHelpers:
    def test_is_recipe_url_de(self):
        assert _is_recipe_url(
            "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
        )

    def test_is_recipe_url_fr(self):
        assert _is_recipe_url(
            "https://www.bettybossi.ch/fr/recettes/recette/gratin-de-pommes-de-terre-10002010/"
        )

    def test_is_recipe_url_id_only(self):
        assert _is_recipe_url("https://www.bettybossi.ch/de/rezepte/rezept/10000742/")

    def test_is_not_recipe_url_category(self):
        assert not _is_recipe_url("https://www.bettybossi.ch/de/rezepte/kategorie/neue-rezepte/")

    def test_is_not_recipe_url_magazine(self):
        assert not _is_recipe_url(
            "https://www.bettybossi.ch/de/magazin/artikel/was-koche-ich-heute/"
        )

    def test_is_not_recipe_url_shop(self):
        assert not _is_recipe_url("https://www.bettybossi.ch/de/shop/produkt/A12216/")

    def test_detect_language_de(self):
        assert (
            _detect_language(
                "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
            )
            == "de"
        )

    def test_detect_language_fr(self):
        assert (
            _detect_language("https://www.bettybossi.ch/fr/recettes/recette/gratin-10002010/")
            == "fr"
        )

    def test_parse_sitemap_urls(self):
        xml = FIXTURES.joinpath("bettybossi_sitemap.xml").read_text(encoding="utf-8")
        urls = _parse_sitemap_urls(xml)

        assert len(urls) == 5
        assert "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/" in urls

    def test_parse_sitemap_urls_empty(self):
        xml = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        urls = _parse_sitemap_urls(xml)
        assert urls == []
