"""Tests for the Schweizer Fleisch source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.schweizerfleisch import (
    SchweizerfleischAdapter,
    _detect_language,
    _extract_gallery_images,
    _extract_images,
    _is_recipe_url,
    _parse_recipe_html,
    _parse_sitemap_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"

_TEST_SETTINGS = Settings(scraping=ScrapingConfig(rate_limit_seconds=0))


def _adapter_with_mock_client() -> tuple[SchweizerfleischAdapter, MagicMock]:
    """Create an adapter with a mocked HTTP client."""
    adapter = SchweizerfleischAdapter(settings=_TEST_SETTINGS)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


class TestSchweizerfleischDiscover:
    def test_discover_via_sitemap(self):
        sitemap_xml = FIXTURES.joinpath("schweizerfleisch_sitemap.xml").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        urls = list(adapter.discover())

        # 3 recipe URLs in fixture (not /impressum or /rezepte bare)
        assert len(urls) == 3
        assert all("/rezepte/" in url for url in urls)
        assert "https://schweizerfleisch.ch/impressum" not in urls
        assert "https://schweizerfleisch.ch/rezepte" not in urls

    def test_discover_falls_back_to_listing(self):
        listing_html = FIXTURES.joinpath("schweizerfleisch_listing.html").read_text(
            encoding="utf-8"
        )

        adapter, mock_client = _adapter_with_mock_client()

        # First call (sitemap) raises error, second call (listing) returns HTML
        sitemap_response = MagicMock()
        sitemap_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        listing_response = MagicMock()
        listing_response.text = listing_html
        listing_response.raise_for_status = MagicMock()

        mock_client.get.side_effect = [sitemap_response, listing_response]

        urls = list(adapter.discover())

        # 3 recipe URLs from listing (not /impressum or /datenschutz)
        assert len(urls) == 3
        assert "https://schweizerfleisch.ch/rezepte/chicken-tikka-masala" in urls
        assert "https://schweizerfleisch.ch/rezepte/massaman-curry" in urls


class TestSchweizerfleischFetch:
    def test_fetch_parses_recipe(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://schweizerfleisch.ch/rezepte/chicken-tikka-masala"
        recipe = adapter.fetch(url)

        assert recipe.title == "Chicken Tikka Masala"
        assert recipe.language == "de"
        assert recipe.source_url == url
        assert len(recipe.ingredients_raw) == 17
        assert len(recipe.steps_raw) == 5
        assert "4 Knoblauchzehen" in recipe.ingredients_raw
        assert recipe.yield_amount == "4 Portionen"

    def test_fetch_extracts_description(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert "indische Küche" in recipe.description

    def test_fetch_extracts_keywords(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert "Schmoren" in recipe.keywords
        assert "Herbst" in recipe.keywords

    def test_fetch_extracts_difficulty(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert recipe.difficulty == "Einfach"

    def test_fetch_extracts_images(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert len(recipe.image_urls) >= 1
        assert any("Chicken_Tikka_Masala" in img for img in recipe.image_urls)

    def test_fetch_extracts_time(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert "45 min" in recipe.prep_time
        assert "1 h" in recipe.cook_time

    def test_fetch_raises_on_no_title(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>No recipe</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No recipe title found"):
            adapter.fetch("https://schweizerfleisch.ch/rezepte/bad-page")

    def test_fetch_detects_french_language(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://viandesuisse.ch/recettes/chicken-tikka-masala")
        assert recipe.language == "fr"

    def test_fetch_extracts_cuisine_from_tags(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        assert recipe.cuisine == "Indisch"


class TestHelpers:
    def test_is_recipe_url_valid(self):
        assert _is_recipe_url("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")

    def test_is_recipe_url_fr(self):
        assert _is_recipe_url("https://viandesuisse.ch/recettes/poulet-tikka-masala")

    def test_is_not_recipe_url_bare_listing(self):
        assert not _is_recipe_url("https://schweizerfleisch.ch/rezepte")

    def test_is_not_recipe_url_other_page(self):
        assert not _is_recipe_url("https://schweizerfleisch.ch/impressum")

    def test_detect_language_de(self):
        assert _detect_language("https://schweizerfleisch.ch/rezepte/test") == "de"

    def test_detect_language_fr(self):
        assert _detect_language("https://viandesuisse.ch/recettes/test") == "fr"

    def test_parse_sitemap_urls(self):
        xml = FIXTURES.joinpath("schweizerfleisch_sitemap.xml").read_text(encoding="utf-8")
        urls = _parse_sitemap_urls(xml)
        assert len(urls) == 5

    def test_parse_recipe_html_minimal(self):
        html = "<html><body><h1>Test Recipe</h1></body></html>"
        recipe = _parse_recipe_html(
            html, source_url="https://schweizerfleisch.ch/rezepte/test", language="de"
        )
        assert recipe.title == "Test Recipe"
        assert recipe.ingredients_raw == []
        assert recipe.steps_raw == []

    def test_context_manager(self):
        adapter = SchweizerfleischAdapter()
        with adapter:
            pass
        assert adapter._client is None


class TestSchweizerfleischGalleryImages:
    def test_extract_gallery_images_from_fixture(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)

        assert len(images) == 2
        assert "Chicken_Tikka_Masala_step1.jpg" in images[0]
        assert "Chicken_Tikka_Masala_step2.jpg" in images[1]

    def test_extract_gallery_images_deduplicates(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="recipe-gallery">
            <img src="/sites/schweizerfleisch/files/img1.jpg">
            <img src="/sites/schweizerfleisch/files/img1.jpg">
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1

    def test_extract_gallery_images_ignores_icons(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="recipe-gallery">
            <img src="/sites/schweizerfleisch/files/icon-timer.png">
            <img src="/sites/schweizerfleisch/files/gallery/real.jpg">
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1
        assert "real.jpg" in images[0]

    def test_extract_gallery_images_uses_data_src(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="recipe-gallery">
            <img data-src="/sites/schweizerfleisch/files/lazy.jpg" src="placeholder.gif">
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1
        assert "lazy.jpg" in images[0]

    def test_fetch_extracts_gallery_images(self):
        html = FIXTURES.joinpath("schweizerfleisch_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")

        # 1 OG image + 2 gallery images = 3 total
        assert len(recipe.image_urls) == 3
        assert "Chicken_Tikka_Masala.jpg" in recipe.image_urls[0]
        assert "Chicken_Tikka_Masala_step1.jpg" in recipe.image_urls[1]
        assert "Chicken_Tikka_Masala_step2.jpg" in recipe.image_urls[2]

    def test_extract_images_no_gallery(self):
        from selectolax.parser import HTMLParser

        html = """
        <html><head>
            <meta property="og:image" content="https://schweizerfleisch.ch/sites/schweizerfleisch/files/main.jpg">
        </head><body></body></html>
        """
        images = _extract_images(HTMLParser(html))
        assert len(images) == 1
        assert "main.jpg" in images[0]
