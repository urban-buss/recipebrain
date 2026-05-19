"""Fooby (Coop) recipe source adapter.

Fooby is a Swiss recipe platform by Coop with a large catalogue in DE/FR/IT.
Recipes are discovered via sitemap and parsed via JSON-LD (schema.org Recipe).

Site: https://fooby.ch
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

_SITEMAP_URL = "https://fooby.ch/sitemap.xml"
_RECIPE_URL_PATTERNS = ("/rezepte/", "/recettes/", "/ricette/")

# Mapping from lowercased Fooby cuisine keyword/tag text to canonical English
# cuisine value.  Includes both English and German language variants.
# Keys NOT in this map are silently ignored by _extract_cuisine_from_tags().
_FOOBY_CUISINE_MAP: dict[str, str] = {
    "italian": "italian",
    "italienisch": "italian",
    "italienische küche": "italian",
    "swiss": "swiss",
    "schweizer": "swiss",
    "schweizer küche": "swiss",
    "asian": "asian",
    "asiatisch": "asian",
    "asiatische küche": "asian",
    "mexican": "mexican",
    "mexikanisch": "mexican",
    "indian": "indian",
    "indisch": "indian",
    "french": "french",
    "französisch": "french",
    "thai": "thai",
    "japanese": "japanese",
    "japanisch": "japanese",
    "greek": "greek",
    "griechisch": "greek",
    "orientalisch": "middle-eastern",
    "mediterran": "mediterranean",
    "mediterranean": "mediterranean",
    "mediterrane küche": "mediterranean",
    "chinese": "chinese",
    "chinesisch": "chinese",
    "korean": "korean",
    "koreanisch": "korean",
    "vietnamese": "vietnamese",
    "vietnamesisch": "vietnamese",
    "spanish": "spanish",
    "spanisch": "spanish",
}

# Coop retail brand prefixes embedded in JSON-LD recipeIngredient text.
# Stripping these allows the normaliser to match the actual ingredient name.
_COOP_BRAND_PREFIXES: tuple[str, ...] = (
    "Fine Food ",
    "Naturaplan ",
    "Prix Garantie ",
    "Betty Bossi ",
)


def _strip_brand_prefix(text: str) -> str:
    """Remove known Coop retail brand prefixes from ingredient text."""
    for prefix in _COOP_BRAND_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


# Equipment keywords that appear in Fooby's recipeIngredient field but are
# not food ingredients. Substring match (case-insensitive).
_EQUIPMENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "schnur",
        "grillholz",
        "holzbrettchen",
        "alu-grill",
        "grillschalen",
        "spiesschen",
        "spiess",
        "backpapier",
        "alufolie",
        "frischhaltefolie",
        "zahnstocher",
    }
)


def _is_equipment(text: str) -> bool:
    """Return True if the ingredient text looks like cooking equipment."""
    lower = text.lower()
    return any(kw in lower for kw in _EQUIPMENT_KEYWORDS)


class FoobyAdapter(SourceAdapter):
    """Source adapter for fooby.ch recipes."""

    key: ClassVar[str] = "fooby"
    display_name: ClassVar[str] = "Fooby"
    languages: ClassVar[tuple[str, ...]] = ("de", "fr", "it")

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
        """Yield recipe URLs from Fooby's sitemap.

        Only yields URLs whose language matches the configured languages.
        Defaults to German-only when no config is present.
        """
        response = self._http.get(_SITEMAP_URL)
        response.raise_for_status()

        configured_languages = _get_configured_languages(self._settings, self.key)
        urls = _parse_sitemap_urls(response.text)
        for url in urls:
            if _is_recipe_url(url) and _detect_language(url) in configured_languages:
                yield url

    def fetch(self, url: str) -> RawRecipe:
        """Fetch a Fooby recipe page and extract data via JSON-LD.

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

        # Use the first Recipe found on the page
        language = _detect_language(url)
        raw = parse_recipe(recipes[0], source_url=url, language=language)

        # Strip Coop retail brand prefixes from ingredient text
        raw.ingredients_raw = [_strip_brand_prefix(ing) for ing in raw.ingredients_raw]

        # Remove cooking equipment / non-food items from ingredient list
        raw.ingredients_raw = [ing for ing in raw.ingredients_raw if not _is_equipment(ing)]

        # Supplement with HTML extraction for classification when JSON-LD is incomplete
        tree = HTMLParser(response.text)
        if not raw.keywords:
            raw.keywords = _extract_meta_keywords(tree)
        if not raw.category:
            raw.category = _extract_category_from_breadcrumb(tree)
        if not raw.cuisine:
            raw.cuisine = _extract_cuisine_from_tags(tree)

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
    """Parse URLs from a sitemap XML document.

    Handles both sitemap index files and regular sitemaps.
    """
    # Strip namespace for simpler parsing
    root = ElementTree.fromstring(xml_text)  # noqa: S314
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls: list[str] = []
    # Regular sitemap: <url><loc>...</loc></url>
    for loc in root.findall(".//sm:url/sm:loc", ns):
        if loc.text:
            urls.append(loc.text.strip())

    # Sitemap index: <sitemap><loc>...</loc></sitemap>
    if not urls:
        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())

    return urls


def _is_recipe_url(url: str) -> bool:
    """Check if a URL looks like a Fooby recipe page."""
    return any(pattern in url for pattern in _RECIPE_URL_PATTERNS)


def _detect_language(url: str) -> str:
    """Detect language from Fooby URL path.

    Examples:
        >>> _detect_language("https://fooby.ch/de/rezepte/123")
        'de'
        >>> _detect_language("https://fooby.ch/fr/recettes/123")
        'fr'
    """
    if "/de/" in url:
        return "de"
    if "/fr/" in url:
        return "fr"
    if "/it/" in url:
        return "it"
    return "de"


def _get_configured_languages(settings: Settings, key: str) -> list[str]:
    """Return the configured languages for a source, defaulting to [\"de\"]."""
    source_cfg = settings.sources.get(key)
    if source_cfg is None:
        return ["de"]
    return source_cfg.languages


def _extract_meta_keywords(tree: HTMLParser) -> list[str]:
    """Extract keywords from HTML meta tag.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<html><head><meta name="keywords"'
        ...        ' content="poulet, reis, einfach"></head></html>')
        >>> _extract_meta_keywords(HTMLParser(html))
        ['poulet', 'reis', 'einfach']
    """
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        return [kw.strip() for kw in content.split(",") if kw.strip()]
    return []


def _extract_category_from_breadcrumb(tree: HTMLParser) -> str:
    """Extract recipe category from breadcrumb navigation.

    Fooby uses breadcrumb links that may contain the recipe category.
    Returns the first non-generic breadcrumb text as the category.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<nav class="breadcrumb"><a href="/">Home</a>'
        ...        '<a href="/rezepte">Rezepte</a>'
        ...        '<a href="/hauptgerichte">Hauptgerichte</a></nav>')
        >>> _extract_category_from_breadcrumb(HTMLParser(html))
        'Hauptgerichte'
    """
    skip = {"Home", "Fooby", "Rezepte", "Recettes", "Ricette"}
    for node in tree.css("nav.breadcrumb a, .breadcrumb a, .breadcrumbs a"):
        text = (node.text() or "").strip()
        if text and text not in skip:
            return text
    return ""


def _extract_cuisine_from_tags(tree: HTMLParser) -> str:
    """Extract cuisine from recipe tag links or meta keywords.

    Scans tag links and meta keywords against ``_FOOBY_CUISINE_MAP`` and
    returns the canonical English cuisine value.  Keywords not in the map
    are silently ignored, preventing non-cuisine terms (e.g. "Schnelle
    Küche", "Familienküche") from polluting the cuisine field.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-tags"><a href="/tag/asiatisch">Asiatisch</a></div>'
        >>> _extract_cuisine_from_tags(HTMLParser(html))
        'asian'
        >>> html_blocked = '<meta name="keywords" content="Schnelle Küche,Hauptgericht"/>'
        >>> _extract_cuisine_from_tags(HTMLParser(html_blocked))
        ''
    """
    for node in tree.css(".recipe-tags a, .tag a, [class*='tag'] a"):
        text = (node.text() or "").strip()
        canonical = _FOOBY_CUISINE_MAP.get(text.lower())
        if canonical:
            return canonical

    # Fallback: scan meta keywords
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        for kw in content.split(","):
            kw = kw.strip()
            canonical = _FOOBY_CUISINE_MAP.get(kw.lower())
            if canonical:
                return canonical
    return ""
