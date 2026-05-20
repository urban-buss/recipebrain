"""Migusto (Migros) recipe source adapter.

Migusto is a Swiss recipe platform by Migros with recipes in DE/FR.
Recipes are discovered via sitemap and parsed via JSON-LD (schema.org Recipe).

Site: https://migusto.migros.ch
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import ClassVar
from xml.etree import ElementTree

import httpx
from selectolax.parser import HTMLParser

from recipebrain.parse.jsonld import extract_recipes, parse_recipe
from recipebrain.settings import Settings
from recipebrain.sources.base import RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_URL = "https://migusto.migros.ch/.rest/sitemap/migusto/de.xml"
_RECIPE_URL_PATTERNS = ("/rezepte/", "/recettes/", "/ricette/")


class MigustoAdapter(SourceAdapter):
    """Source adapter for migusto.migros.ch recipes."""

    key: ClassVar[str] = "migusto"
    display_name: ClassVar[str] = "Migusto"
    languages: ClassVar[tuple[str, ...]] = ("de", "fr")

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.load(None)
        self._client: httpx.Client | None = None

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            scraping = self._settings.scraping
            self._client = httpx.Client(
                headers={"User-Agent": scraping.user_agent},
                timeout=scraping.timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    def _rate_limit(self) -> None:
        time.sleep(self._settings.scraping.rate_limit_seconds)

    def discover(self) -> Iterable[str]:
        """Yield recipe URLs from Migusto's sitemap.

        Fetches the sitemap XML and filters for URLs containing the
        recipe path pattern.
        """
        discovery_timeout = self._settings.scraping.discovery_timeout_seconds
        response = self._http.get(_SITEMAP_URL, timeout=discovery_timeout)
        response.raise_for_status()

        urls = _parse_sitemap_urls(response.text)
        for url in urls:
            if _is_recipe_url(url):
                yield url

    def fetch(self, url: str) -> RawRecipe:
        """Fetch a Migusto recipe page and extract data via JSON-LD.

        Supplements JSON-LD with HTML extraction for classification metadata
        when JSON-LD lacks category, cuisine, or keywords.

        Raises ValueError if the page contains no valid Recipe JSON-LD.
        """
        self._rate_limit()

        response = self._http.get(url)
        response.raise_for_status()

        recipes = extract_recipes(response.text, base_url=url)
        if not recipes:
            raise ValueError(f"No Recipe JSON-LD found at {url}")

        language = _detect_language(url)
        raw = parse_recipe(recipes[0], source_url=url, language=language)

        # Supplement with HTML extraction for classification when JSON-LD is incomplete
        tree = HTMLParser(response.text)
        if not raw.keywords:
            raw.keywords = _extract_meta_keywords(tree)
        if not raw.category:
            raw.category = _extract_category_from_meta(tree)
        if not raw.cuisine:
            raw.cuisine = _extract_cuisine_from_tags(tree)
        if not raw.difficulty:
            raw.difficulty = _extract_difficulty_from_tags(tree)

        # Ensure image captions are populated; use title as fallback
        while len(raw.image_captions) < len(raw.image_urls):
            raw.image_captions.append(raw.title)
        for i, cap in enumerate(raw.image_captions):
            if not cap:
                raw.image_captions[i] = raw.title

        return raw

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _parse_sitemap_urls(xml_text: str) -> list[str]:
    """Parse URLs from a sitemap XML document."""
    root = ElementTree.fromstring(xml_text)  # noqa: S314
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls: list[str] = []
    for loc in root.findall(".//sm:url/sm:loc", ns):
        if loc.text:
            urls.append(loc.text.strip())

    if not urls:
        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())

    return urls


def _is_recipe_url(url: str) -> bool:
    """Check if a URL looks like a Migusto recipe page."""
    return any(pattern in url for pattern in _RECIPE_URL_PATTERNS)


def _detect_language(url: str) -> str:
    """Detect language from Migusto URL path.

    Examples:
        >>> _detect_language("https://migusto.migros.ch/de/rezepte/pasta")
        'de'
        >>> _detect_language("https://migusto.migros.ch/fr/recettes/pates")
        'fr'
    """
    if "/fr/" in url:
        return "fr"
    if "/it/" in url:
        return "it"
    return "de"


def _extract_meta_keywords(tree: HTMLParser) -> list[str]:
    """Extract keywords from HTML meta tag.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<html><head><meta name="keywords"'
        ...        ' content="pasta, italienisch, schnell"></head></html>')
        >>> _extract_meta_keywords(HTMLParser(html))
        ['pasta', 'italienisch', 'schnell']
    """
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        return [kw.strip() for kw in content.split(",") if kw.strip()]
    return []


def _extract_category_from_meta(tree: HTMLParser) -> str:
    """Extract recipe category from page metadata or breadcrumb.

    Migusto uses breadcrumb navigation and article:section meta tags.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<html><head><meta property="article:section"'
        ...        ' content="Hauptgerichte"></head></html>')
        >>> _extract_category_from_meta(HTMLParser(html))
        'Hauptgerichte'
    """
    # Try article:section meta tag
    meta = tree.css_first("meta[property='article:section']")
    if meta:
        content = (meta.attributes.get("content") or "").strip()
        if content:
            return content

    # Try breadcrumb navigation
    skip = {"Home", "Migusto", "Rezepte", "Recettes"}
    for node in tree.css("nav.breadcrumb a, .breadcrumb a, .breadcrumbs a"):
        text = (node.text() or "").strip()
        if text and text not in skip:
            return text
    return ""


def _extract_cuisine_from_tags(tree: HTMLParser) -> str:
    """Extract cuisine from recipe tag links.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-tags"><a href="/tag/italienisch">Italienisch</a></div>'
        >>> _extract_cuisine_from_tags(HTMLParser(html))
        'Italienisch'
    """
    cuisine_keywords = {
        "italienisch",
        "italian",
        "swiss",
        "schweizer",
        "asiatisch",
        "asian",
        "mexikanisch",
        "mexican",
        "indisch",
        "indian",
        "französisch",
        "french",
        "thai",
        "japanisch",
        "japanese",
        "griechisch",
        "greek",
        "orientalisch",
        "mediterran",
        "mediterranean",
    }
    for node in tree.css(".recipe-tags a, .tag a, [class*='tag'] a"):
        text = (node.text() or "").strip()
        if text.lower() in cuisine_keywords:
            return text
    return ""


def _extract_difficulty_from_tags(tree: HTMLParser) -> str:
    """Extract difficulty from recipe tag links or recipe meta.

    Migusto may show difficulty as a tag or in a recipe info section.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-tags"><a href="/tag/einfach">Einfach</a></div>'
        >>> _extract_difficulty_from_tags(HTMLParser(html))
        'Einfach'
    """
    difficulty_values = {
        "einfach",
        "easy",
        "leicht",
        "simpel",
        "mittel",
        "medium",
        "modéré",
        "schwer",
        "advanced",
        "difficile",
        "anspruchsvoll",
        "facile",
        "moyen",
    }
    for node in tree.css(".recipe-tags a, .tag a, [class*='tag'] a"):
        text = (node.text() or "").strip()
        if text.lower() in difficulty_values:
            return text

    # Fallback: recipe info/meta section
    for node in tree.css(".recipe-info span, .recipe-meta span, .recipe-difficulty"):
        text = (node.text() or "").strip()
        if text.lower() in difficulty_values:
            return text
    return ""
