"""Tests for the Swissmilk source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.swissmilk import (
    SwissmilkAdapter,
    _detect_language,
    _extract_gallery_images,
    _extract_images,
    _is_recipe_url,
    _parse_sitemap_urls,
    _parse_time_text,
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
        assert recipe.prep_time == "PT45M"
        assert recipe.cook_time == ""
        assert len(recipe.image_urls) >= 1
        assert "kartoffelgratin" in recipe.image_urls[0]

    def test_fetch_raises_on_no_jsonld(self):
        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = "<html><body>No recipe here</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="No recipe title found"):
            adapter.fetch("https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM000/bad/")

    def test_fetch_extracts_keywords(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        assert "gratin" in recipe.keywords
        assert "kartoffeln" in recipe.keywords
        assert "beilage" in recipe.keywords

    def test_fetch_extracts_category_from_breadcrumb(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        assert recipe.category == "Beilagen"

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

    def test_fetch_extracts_cuisine_from_tags(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        assert recipe.cuisine == "Schweizer"

    def test_fetch_extracts_difficulty(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        assert recipe.difficulty == "Einfach"


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


class TestParseTimeText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("45 min", "PT45M"),
            ("30 Min.", "PT30M"),
            ("ca. 30 Min.", "PT30M"),
            ("1 Std. 15 Min.", "PT1H15M"),
            ("2 Stunden", "PT2H"),
            ("1 Std.", "PT1H"),
            ("30 Minuten", "PT30M"),
            ("1 h 30 min", "PT1H30M"),
            ("2 heures", "PT2H"),
            ("15 minutes", "PT15M"),
            ("", ""),
            ("   ", ""),
            ("no time here", ""),
        ],
    )
    def test_parse_time_text(self, text: str, expected: str):
        assert _parse_time_text(text) == expected


class TestSwissmilkGalleryImages:
    def test_extract_gallery_images_from_fixture(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)

        assert len(images) == 3
        assert "kartoffelgratin-step1.jpg" in images[0]
        assert "kartoffelgratin-step2.jpg" in images[1]
        assert "kartoffelgratin-final.jpg" in images[2]

    def test_extract_gallery_images_deduplicates(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="recipe-gallery">
            <img data-src="https://res.cloudinary.com/swissmilk/image/fetch/img1.jpg">
            <img data-src="https://res.cloudinary.com/swissmilk/image/fetch/img1.jpg">
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1

    def test_extract_gallery_images_ignores_nuxt_assets(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="recipe-gallery">
            <img src="/_nuxt/img/placeholder.svg">
            <img src="https://res.cloudinary.com/swissmilk/image/fetch/real.jpg">
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1
        assert "real.jpg" in images[0]

    def test_extract_gallery_images_uses_srcset(self):
        from selectolax.parser import HTMLParser

        html = """
        <div class="RecipeDetail">
            <picture>
                <source srcset="https://res.cloudinary.com/swissmilk/image/fetch/w_400/pic.jpg 1x, https://res.cloudinary.com/swissmilk/image/fetch/w_800/pic.jpg 2x">
            </picture>
        </div>
        """
        images = _extract_gallery_images(HTMLParser(html))
        assert len(images) == 1
        assert "w_400/pic.jpg" in images[0]

    def test_fetch_extracts_gallery_images(self):
        html = FIXTURES.joinpath("swissmilk_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        url = "https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/"
        recipe = adapter.fetch(url)

        # 1 OG image + 3 gallery images = 4 total
        assert len(recipe.image_urls) == 4
        assert "kartoffelgratin.jpg" in recipe.image_urls[0]
        assert "kartoffelgratin-step1.jpg" in recipe.image_urls[1]

    def test_extract_images_no_gallery(self):
        from selectolax.parser import HTMLParser

        html = """
        <html><head>
            <meta property="og:image" content="https://res.cloudinary.com/swissmilk/image/fetch/main.jpg">
        </head><body></body></html>
        """
        images = _extract_images(HTMLParser(html))
        assert len(images) == 1
        assert "main.jpg" in images[0]
