"""Tests for the Fooby source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recipebrain.settings import ScrapingConfig, Settings
from recipebrain.sources.fooby import (
    FoobyAdapter,
    _detect_language,
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

        # Should include recipe URLs only (3 in fixture), not /ueber-uns or /tipps-tricks
        assert len(urls) == 3
        assert all("/rezepte/" in url or "/recettes/" in url for url in urls)

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
