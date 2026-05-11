"""Betty Bossi recipe source adapter.

Betty Bossi is a major Swiss recipe platform (owned by Coop) with a large
catalogue in DE/FR. Recipes are discovered via sitemap and parsed via JSON-LD
(schema.org Recipe) with HTML fallback.

Site: https://www.bettybossi.ch
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

_SITEMAP_URLS = (
    "https://www.bettybossi.ch/sitemap-recipe-de.xml",
    "https://www.bettybossi.ch/sitemap-recipe-fr.xml",
)
_RECIPE_URL_PATTERN_DE = "/de/rezepte/rezept/"
_RECIPE_URL_PATTERN_FR = "/fr/recettes/recette/"


class BettybossiAdapter(SourceAdapter):
    """Source adapter for bettybossi.ch recipes."""

    key: ClassVar[str] = "bettybossi"
    display_name: ClassVar[str] = "Betty Bossi"
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
        """Yield recipe URLs from Betty Bossi's sitemaps.

        Fetches DE and FR recipe sitemaps and yields all recipe URLs found.
        """
        for sitemap_url in _SITEMAP_URLS:
            try:
                response = self._http.get(sitemap_url)
                response.raise_for_status()
            except httpx.HTTPError:
                logger.warning("Failed to fetch sitemap: %s", sitemap_url)
                continue

            urls = _parse_sitemap_urls(response.text)
            for url in urls:
                if _is_recipe_url(url):
                    yield url

    def fetch(self, url: str) -> RawRecipe:
        """Fetch a Betty Bossi recipe page and extract data via JSON-LD.

        Falls back to HTML parsing if no JSON-LD is found.
        Raises ValueError if the page contains no recognisable recipe content.
        """
        self._rate_limit()

        response = self._http.get(url)
        response.raise_for_status()

        language = _detect_language(url)

        # Try JSON-LD first (preferred strategy per ADR-002)
        recipes = extract_recipes(response.text, base_url=url)
        if recipes:
            return parse_recipe(recipes[0], source_url=url, language=language)

        # HTML fallback
        tree = HTMLParser(response.text)
        title = _extract_title(tree)
        if not title:
            raise ValueError(f"No recipe found at {url}")

        return RawRecipe(
            title=title,
            description=_extract_description(tree),
            ingredients_raw=_extract_ingredients(tree),
            steps_raw=_extract_steps(tree),
            yield_amount=_extract_yield(tree),
            prep_time=_extract_time(tree, "prep"),
            cook_time=_extract_time(tree, "cook"),
            image_urls=_extract_images(tree),
            keywords=_extract_keywords(tree),
            source_url=url,
            language=language,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _extract_title(tree: HTMLParser) -> str:
    """Extract recipe title from the page heading."""
    node = tree.css_first("h1")
    return (node.text() or "").strip() if node else ""


def _extract_description(tree: HTMLParser) -> str:
    """Extract recipe description from meta tag."""
    meta = tree.css_first("meta[name='description']")
    if meta:
        return (meta.attributes.get("content") or "").strip()
    return ""


def _extract_ingredients(tree: HTMLParser) -> list[str]:
    """Extract ingredients from Betty Bossi's structured ingredient lists.

    Ingredients appear as list items with bold text (name) and quantity text.
    """
    ingredients: list[str] = []
    for li in tree.css("li[itemprop='recipeIngredient'], .ingredient-item"):
        text = (li.text() or "").strip()
        text = " ".join(text.split())
        if text:
            ingredients.append(text)

    # Fallback: look for ingredient rows in step blocks
    if not ingredients:
        for li in tree.css("ul li"):
            text = (li.text() or "").strip()
            text = " ".join(text.split())
            if text and any(
                unit in text for unit in ("g ", "kg ", "dl ", "l ", "EL ", "TL ", "Stk", "Prise")
            ):
                ingredients.append(text)

    return ingredients


def _extract_steps(tree: HTMLParser) -> list[str]:
    """Extract preparation steps from the recipe page."""
    steps: list[str] = []
    for node in tree.css("[itemprop='recipeInstructions'] [itemprop='text']"):
        text = (node.text() or "").strip()
        if text:
            steps.append(text)

    # Fallback: ordered list items in the instructions section
    if not steps:
        for node in tree.css(".preparation-step, .recipe-step"):
            text = (node.text() or "").strip()
            if text:
                steps.append(text)

    return steps


def _extract_yield(tree: HTMLParser) -> str:
    """Extract recipe yield (servings)."""
    node = tree.css_first("[itemprop='recipeYield']")
    if node:
        return (node.text() or "").strip()
    return ""


def _extract_time(tree: HTMLParser, kind: str) -> str:
    """Extract recipe time from structured data.

    Args:
        tree: Parsed HTML tree.
        kind: Either 'prep' or 'cook'.
    """
    prop = "prepTime" if kind == "prep" else "cookTime"
    node = tree.css_first(f"[itemprop='{prop}']")
    if node:
        return (node.attributes.get("content") or node.text() or "").strip()
    return ""


def _extract_images(tree: HTMLParser) -> list[str]:
    """Extract recipe image from OG meta or structured data."""
    images: list[str] = []
    og = tree.css_first("meta[property='og:image']")
    if og:
        src = (og.attributes.get("content") or "").strip()
        if src:
            images.append(src)
            return images

    node = tree.css_first("[itemprop='image']")
    if node:
        src = (node.attributes.get("src") or node.attributes.get("content") or "").strip()
        if src:
            images.append(src)

    return images


def _extract_keywords(tree: HTMLParser) -> list[str]:
    """Extract recipe keywords/tags."""
    keywords: list[str] = []
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        keywords = [k.strip() for k in content.split(",") if k.strip()]
    return keywords


def _parse_sitemap_urls(xml_text: str) -> list[str]:
    """Parse URLs from a sitemap XML document.

    Handles both sitemap index files and regular sitemaps.

    Examples:
        >>> xml = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.bettybossi.ch/de/rezepte/rezept/test-123/</loc></url></urlset>'
        >>> _parse_sitemap_urls(xml)
        ['https://www.bettybossi.ch/de/rezepte/rezept/test-123/']
    """
    root = ElementTree.fromstring(xml_text)  # noqa: S314
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls: list[str] = []
    for loc in root.findall(".//sm:url/sm:loc", ns):
        if loc.text:
            urls.append(loc.text.strip())

    # Sitemap index fallback
    if not urls:
        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())

    return urls


def _is_recipe_url(url: str) -> bool:
    """Check if a URL looks like a Betty Bossi recipe page.

    Examples:
        >>> _is_recipe_url("https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/")
        True
        >>> _is_recipe_url("https://www.bettybossi.ch/fr/recettes/recette/gratin-10002010/")
        True
        >>> _is_recipe_url("https://www.bettybossi.ch/de/rezepte/kategorie/neue-rezepte/")
        False
    """
    return _RECIPE_URL_PATTERN_DE in url or _RECIPE_URL_PATTERN_FR in url


def _detect_language(url: str) -> str:
    """Detect language from Betty Bossi URL path.

    Examples:
        >>> _detect_language("https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/")
        'de'
        >>> _detect_language("https://www.bettybossi.ch/fr/recettes/recette/gratin-10002010/")
        'fr'
    """
    if "/fr/" in url:
        return "fr"
    return "de"
