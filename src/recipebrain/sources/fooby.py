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

from recipebrain.parse.jsonld import extract_recipes, parse_recipe
from recipebrain.settings import Settings
from recipebrain.sources.base import RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_URL = "https://fooby.ch/sitemap.xml"
_RECIPE_URL_PATTERNS = ("/rezepte/", "/recettes/", "/ricette/")


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

        Fetches the sitemap XML and filters for URLs containing the
        recipe path pattern. Respects rate limiting between requests.
        """
        response = self._http.get(_SITEMAP_URL)
        response.raise_for_status()

        urls = _parse_sitemap_urls(response.text)
        for url in urls:
            if _is_recipe_url(url):
                yield url

    def fetch(self, url: str) -> RawRecipe:
        """Fetch a Fooby recipe page and extract data via JSON-LD.

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
        return parse_recipe(recipes[0], source_url=url, language=language)

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
