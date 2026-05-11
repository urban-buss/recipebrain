"""Swissmilk recipe source adapter.

Swissmilk is a Swiss recipe platform focused on dairy-based cooking with a
very broad catalogue in DE/FR. Recipes are discovered via sitemap and parsed
via JSON-LD (schema.org Recipe).

Site: https://www.swissmilk.ch
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import ClassVar
from xml.etree import ElementTree

import httpx
from selectolax.parser import HTMLParser

from recipebrain.settings import Settings
from recipebrain.sources.base import RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_URLS = (
    "https://www.swissmilk.ch/de/sitemap.xml",
    "https://www.swissmilk.ch/fr/sitemap.xml",
)
_RECIPE_URL_PATTERN = "/rezepte-kochideen/rezepte/"
_RECIPE_URL_PATTERN_FR = "/recettes-idees-cuisine/recettes/"


class SwissmilkAdapter(SourceAdapter):
    """Source adapter for swissmilk.ch recipes."""

    key: ClassVar[str] = "swissmilk"
    display_name: ClassVar[str] = "Swissmilk"
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
        """Yield recipe URLs from Swissmilk's sitemaps.

        Fetches DE and FR sitemaps and filters for URLs containing the
        recipe path pattern.
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
        """Fetch a Swissmilk recipe page and extract data from HTML.

        Swissmilk uses Nuxt SSR with microdata (itemprop) and BEM-style CSS
        classes. Ingredients are in a table with tr.Ingredient rows, steps in
        .PreparationList--step elements.

        Raises ValueError if the page contains no recognisable recipe content.
        """
        self._rate_limit()

        response = self._http.get(url)
        response.raise_for_status()

        tree = HTMLParser(response.text)
        language = _detect_language(url)

        title = _extract_title(tree)
        if not title:
            raise ValueError(f"No recipe title found at {url}")

        return RawRecipe(
            title=title,
            description=_extract_description(tree),
            ingredients_raw=_extract_ingredients(tree),
            steps_raw=_extract_steps(tree),
            yield_amount=_extract_yield(tree),
            prep_time=_extract_time(tree),
            cook_time="",
            image_urls=_extract_images(tree),
            keywords=[],
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
    """Extract recipe title from the page heading.

    Tries specific recipe selectors first to avoid navigation headings.
    """
    for selector in (".RecipeHeader h1", ".RecipeDetail h1"):
        node = tree.css_first(selector)
        if node:
            text = (node.text() or "").strip()
            if text:
                return text
    # Fallback to generic h1
    node = tree.css_first("h1")
    return (node.text() or "").strip() if node else ""


def _extract_description(tree: HTMLParser) -> str:
    """Extract recipe description from meta tag."""
    meta = tree.css_first("meta[name='description']")
    if meta:
        return (meta.attributes.get("content") or "").strip()
    return ""


def _extract_ingredients(tree: HTMLParser) -> list[str]:
    """Extract ingredients from Swissmilk's IngredientsCalculator table.

    Each ingredient row has .Ingredient--amount (quantity+unit) and
    .Ingredient--text (name).
    """
    ingredients: list[str] = []
    for row in tree.css("tr.Ingredient"):
        amount_el = row.css_first(".Ingredient--amount")
        text_el = row.css_first(".Ingredient--text")
        if not text_el:
            continue
        name = (text_el.text() or "").strip()
        amount = ""
        if amount_el:
            amount = (amount_el.text() or "").strip()
            # Clean up whitespace from nested spans
            amount = " ".join(amount.split())
        if amount and name:
            ingredients.append(f"{amount} {name}")
        elif name:
            ingredients.append(name)
    return ingredients


def _extract_steps(tree: HTMLParser) -> list[str]:
    """Extract preparation steps."""
    steps: list[str] = []
    for node in tree.css(".PreparationList--step"):
        text = (node.text() or "").strip()
        if text:
            steps.append(text)
    return steps


def _extract_yield(tree: HTMLParser) -> str:
    """Extract recipe yield (servings)."""
    node = tree.css_first("[itemprop='recipeYield'], .IngredientsCalculator--amount")
    if node:
        return (node.text() or "").strip()
    return ""


def _extract_time(tree: HTMLParser) -> str:
    """Extract recipe time from RecipeFacts element."""
    node = tree.css_first(".RecipeFacts")
    if node:
        return (node.text() or "").strip()
    return ""


def _extract_images(tree: HTMLParser) -> list[str]:
    """Extract recipe image from OG meta or header image."""
    images: list[str] = []
    og = tree.css_first("meta[property='og:image']")
    if og:
        src = (og.attributes.get("content") or "").strip()
        if src:
            images.append(src)
            return images

    for img in tree.css(".RecipeHeader img"):
        src = (img.attributes.get("src") or "").strip()
        if src and not src.startswith("data:") and "/_nuxt/" not in src:
            images.append(src)
    return images


def _parse_sitemap_urls(xml_text: str) -> list[str]:
    """Parse URLs from a sitemap XML document.

    Handles both sitemap index files and regular sitemaps.
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
    """Check if a URL looks like a Swissmilk recipe page.

    Examples:
        >>> _is_recipe_url("https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM200803_37/kartoffelgratin/")
        True
        >>> _is_recipe_url("https://www.swissmilk.ch/de/nachhaltigkeit/")
        False
    """
    return _RECIPE_URL_PATTERN in url or _RECIPE_URL_PATTERN_FR in url


def _detect_language(url: str) -> str:
    """Detect language from Swissmilk URL path.

    Examples:
        >>> _detect_language("https://www.swissmilk.ch/de/rezepte-kochideen/rezepte/LM123/test/")
        'de'
        >>> _detect_language("https://www.swissmilk.ch/fr/recettes-idees-cuisine/recettes/LM123/test/")
        'fr'
    """
    if "/fr/" in url:
        return "fr"
    return "de"
