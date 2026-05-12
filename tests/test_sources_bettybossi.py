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
    _extract_breadcrumb_categories,
    _extract_gallery_images,
    _extract_keywords,
    _first_srcset_url,
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

    def test_fetch_extracts_keywords_from_jsonld(self):
        """When JSON-LD has keywords, they should be used directly."""
        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
        )

        assert recipe.keywords == ["Vegetarisch", "Glutenfrei", "Gratin", "Kartoffeln"]

    def test_fetch_supplements_keywords_from_html_meta_when_jsonld_lacks_them(self):
        """When JSON-LD has no keywords, fall back to HTML <meta name='keywords'>."""
        html = FIXTURES.joinpath("bettybossi_recipe_no_jsonld_keywords.html").read_text(
            encoding="utf-8"
        )

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch("https://www.bettybossi.ch/de/rezepte/rezept/pilzrisotto-10003000/")

        assert "Risotto" in recipe.keywords
        assert "Pilze" in recipe.keywords
        assert "Vegetarisch" in recipe.keywords
        assert "Herbst" in recipe.keywords
        # Also includes breadcrumb categories
        assert "Hauptgerichte" in recipe.keywords
        assert "Risotto" in recipe.keywords

    def test_fetch_supplements_keywords_from_breadcrumbs_when_no_meta(self):
        """When both JSON-LD and meta keywords are missing, use breadcrumbs."""
        html = FIXTURES.joinpath("bettybossi_recipe_breadcrumb_only.html").read_text(
            encoding="utf-8"
        )

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/geschnetzeltes-10004000/"
        )

        assert "Fleisch" in recipe.keywords
        assert "Kalb" in recipe.keywords
        # Home and Rezepte should be filtered out
        assert "Home" not in recipe.keywords
        assert "Rezepte" not in recipe.keywords


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


class TestKeywordExtraction:
    def test_extract_keywords_from_meta_tag(self):
        from selectolax.parser import HTMLParser

        html = '<html><head><meta name="keywords" content="Pasta, Vegan, Schnell"></head></html>'
        tree = HTMLParser(html)
        assert _extract_keywords(tree) == ["Pasta", "Vegan", "Schnell"]

    def test_extract_keywords_empty_when_no_meta(self):
        from selectolax.parser import HTMLParser

        html = "<html><head></head></html>"
        tree = HTMLParser(html)
        assert _extract_keywords(tree) == []

    def test_extract_keywords_empty_content(self):
        from selectolax.parser import HTMLParser

        html = '<html><head><meta name="keywords" content=""></head></html>'
        tree = HTMLParser(html)
        assert _extract_keywords(tree) == []

    def test_extract_breadcrumb_categories(self):
        from selectolax.parser import HTMLParser

        html = """<nav class="breadcrumb">
            <a href="/">Home</a>
            <a href="/de/rezepte/">Rezepte</a>
            <a href="/de/rezepte/kategorie/desserts/">Desserts</a>
            <a href="/de/rezepte/kategorie/schokolade/">Schokolade</a>
        </nav>"""
        tree = HTMLParser(html)
        result = _extract_breadcrumb_categories(tree)
        assert result == ["Desserts", "Schokolade"]

    def test_extract_breadcrumb_categories_french(self):
        from selectolax.parser import HTMLParser

        html = """<nav class="breadcrumb">
            <a href="/">Accueil</a>
            <a href="/fr/recettes/">Recettes</a>
            <a href="/fr/recettes/categorie/poisson/">Poisson</a>
        </nav>"""
        tree = HTMLParser(html)
        result = _extract_breadcrumb_categories(tree)
        assert result == ["Poisson"]

    def test_extract_breadcrumb_categories_no_nav(self):
        from selectolax.parser import HTMLParser

        html = "<html><body><p>No breadcrumbs</p></body></html>"
        tree = HTMLParser(html)
        assert _extract_breadcrumb_categories(tree) == []


class TestIngredientGroups:
    def test_extract_groups_from_html_with_headings(self):
        from selectolax.parser import HTMLParser

        from recipebrain.sources.bettybossi import _extract_ingredient_groups

        html = FIXTURES.joinpath("bettybossi_recipe_grouped_ingredients.html").read_text(
            encoding="utf-8"
        )
        tree = HTMLParser(html)
        groups = _extract_ingredient_groups(tree)

        assert len(groups) == 3
        assert groups[0].label == "Für den Teig"
        assert groups[0].items == ["200 g Mehl", "3 dl Milch", "3 Eier", "1 Prise Salz"]
        assert groups[1].label == "Für die Schokoladenfüllung"
        assert groups[1].items == ["200 g Zartbitterschokolade", "1 dl Rahm"]
        assert groups[2].label == "Für die Fruchtfüllung"
        assert groups[2].items == ["300 g gemischte Beeren", "2 EL Zucker", "1 EL Zitronensaft"]

    def test_extract_groups_fallback_flat_when_no_headings(self):
        from selectolax.parser import HTMLParser

        from recipebrain.sources.bettybossi import _extract_ingredient_groups

        html = """<html><body>
        <section class="ingredients">
            <h2>Zutaten</h2>
            <ul>
                <li>200 g Mehl</li>
                <li>3 Eier</li>
            </ul>
        </section>
        </body></html>"""
        tree = HTMLParser(html)
        groups = _extract_ingredient_groups(tree)

        assert len(groups) == 1
        assert groups[0].label is None
        assert groups[0].items == ["200 g Mehl", "3 Eier"]

    def test_extract_groups_empty_when_no_ingredients(self):
        from selectolax.parser import HTMLParser

        from recipebrain.sources.bettybossi import _extract_ingredient_groups

        html = "<html><body><p>No ingredients here</p></body></html>"
        tree = HTMLParser(html)
        groups = _extract_ingredient_groups(tree)

        assert groups == []

    def test_fetch_populates_ingredient_groups_from_jsonld_recipe(self):
        """JSON-LD recipe with HTML groups should have ingredient_groups set."""
        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
        )

        # The fixture has a single ungrouped section
        assert len(recipe.ingredient_groups) >= 1
        # All ingredient items should be present across groups
        all_items = [item for g in recipe.ingredient_groups for item in g.items]
        assert len(all_items) >= 1

    def test_fetch_grouped_html_fallback(self):
        """HTML fallback should extract ingredient groups."""
        html = FIXTURES.joinpath("bettybossi_recipe_grouped_ingredients.html").read_text(
            encoding="utf-8"
        )

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/crepes-mit-fuellungen-99999/"
        )

        assert len(recipe.ingredient_groups) == 3
        assert recipe.ingredient_groups[0].label == "Für den Teig"
        assert recipe.ingredient_groups[2].label == "Für die Fruchtfüllung"
        # ingredients_raw should also be populated (flat list)
        assert len(recipe.ingredients_raw) == 9


class TestGalleryImageExtraction:
    def test_extract_gallery_images_from_fixture(self):
        from selectolax.parser import HTMLParser

        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")
        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)

        assert len(images) == 3
        assert all("media.bettybossi.ch" in url for url in images)

    def test_extract_gallery_images_empty_when_no_gallery(self):
        from selectolax.parser import HTMLParser

        html = "<html><body><p>No gallery</p></body></html>"
        tree = HTMLParser(html)
        assert _extract_gallery_images(tree) == []

    def test_extract_gallery_images_deduplicates(self):
        from selectolax.parser import HTMLParser

        html = """<div class="recipe-gallery">
            <img data-src="https://media.bettybossi.ch/img/a.jpg">
            <img data-src="https://media.bettybossi.ch/img/a.jpg">
        </div>"""
        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)
        assert len(images) == 1

    def test_extract_gallery_images_ignores_non_bettybossi(self):
        from selectolax.parser import HTMLParser

        html = """<div class="recipe-gallery">
            <img data-src="https://media.bettybossi.ch/img/a.jpg">
            <img data-src="https://other-cdn.com/img/b.jpg">
        </div>"""
        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)
        assert len(images) == 1
        assert "media.bettybossi.ch" in images[0]

    def test_extract_gallery_images_uses_srcset(self):
        from selectolax.parser import HTMLParser

        html = """<div class="recipe-gallery">
            <img srcset="https://media.bettybossi.ch/img/a.jpg 1x, https://media.bettybossi.ch/img/b.jpg 2x">
        </div>"""
        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)
        assert len(images) == 1
        assert images[0] == "https://media.bettybossi.ch/img/a.jpg"

    def test_extract_gallery_images_uses_src_fallback(self):
        from selectolax.parser import HTMLParser

        html = """<div class="recipe-gallery">
            <img src="https://media.bettybossi.ch/img/a.jpg">
        </div>"""
        tree = HTMLParser(html)
        images = _extract_gallery_images(tree)
        assert len(images) == 1

    def test_fetch_supplements_gallery_images(self):
        """JSON-LD recipe fetch should include gallery images from HTML."""
        html = FIXTURES.joinpath("bettybossi_recipe.html").read_text(encoding="utf-8")

        adapter, mock_client = _adapter_with_mock_client()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        recipe = adapter.fetch(
            "https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/"
        )

        # Should have primary image + 3 gallery images = 4
        assert len(recipe.image_urls) == 4
        assert recipe.image_urls[0] == (
            "https://media.bettybossi.ch/image/992382728798/"
            "image_4vvdg674vt67lefbcknq3skk26/-FWEBP-Ro:5,w:1125,h:844,n:default"
        )

    def test_first_srcset_url_normal(self):
        assert (
            _first_srcset_url("https://example.com/a.jpg 1x, https://example.com/b.jpg 2x")
            == "https://example.com/a.jpg"
        )

    def test_first_srcset_url_empty(self):
        assert _first_srcset_url("") == ""
