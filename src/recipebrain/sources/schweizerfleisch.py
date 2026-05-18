"""Schweizer Fleisch recipe source adapter.

Schweizer Fleisch (Proviande) is a Swiss meat-focused recipe site.
Recipes use structured HTML rather than JSON-LD, so this adapter uses
site-specific HTML parsing.

Site: https://schweizerfleisch.ch (DE), https://viandesuisse.ch (FR)
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
import time
from collections.abc import Iterable
from typing import ClassVar
from xml.etree import ElementTree

import httpx
from selectolax.parser import HTMLParser

from recipebrain.settings import Settings
from recipebrain.sources.base import RawIngredientGroup, RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_URL = "https://schweizerfleisch.ch/sitemap.xml"
_RECIPE_URL_PATTERN = re.compile(r"https://schweizerfleisch\.ch/rezepte/[\w-]+$")
_RECIPE_URL_PATTERN_FR = re.compile(r"https://viandesuisse\.ch/recettes/[\w-]+$")

_BASE_URLS = {
    "de": "https://schweizerfleisch.ch",
    "fr": "https://viandesuisse.ch",
}


class SchweizerfleischAdapter(SourceAdapter):
    """Source adapter for schweizerfleisch.ch recipes."""

    key: ClassVar[str] = "schweizerfleisch"
    display_name: ClassVar[str] = "Schweizer Fleisch"
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
        """Yield recipe URLs from the sitemap.

        Falls back to parsing the listing page if the sitemap has no recipe URLs.
        """
        try:
            response = self._http.get(_SITEMAP_URL)
            response.raise_for_status()
            urls = _parse_sitemap_urls(response.text)
            recipe_urls = [u for u in urls if _is_recipe_url(u)]
            if recipe_urls:
                yield from recipe_urls
                return
        except httpx.HTTPError:
            logger.warning("Failed to fetch sitemap: %s", _SITEMAP_URL)

        # Fallback: scrape listing page
        yield from self._discover_from_listing()

    def _discover_from_listing(self) -> Iterable[str]:
        """Discover recipe URLs by parsing the recipe listing page."""
        self._rate_limit()
        try:
            response = self._http.get(f"{_BASE_URLS['de']}/rezepte")
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Failed to fetch recipe listing page")
            return

        tree = HTMLParser(response.text)
        for node in tree.css("a[href]"):
            href = node.attributes.get("href", "")
            if href:
                url = href if href.startswith("http") else f"{_BASE_URLS['de']}{href}"
                if _is_recipe_url(url):
                    yield url

    def fetch(self, url: str) -> RawRecipe:
        """Fetch a recipe page and extract data from structured HTML.

        Raises ValueError if the page cannot be parsed as a recipe.
        """
        self._rate_limit()

        response = self._http.get(url)
        response.raise_for_status()

        language = _detect_language(url)
        return _parse_recipe_html(response.text, source_url=url, language=language)

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
    """Check if a URL looks like a Schweizer Fleisch recipe page.

    Examples:
        >>> _is_recipe_url("https://schweizerfleisch.ch/rezepte/chicken-tikka-masala")
        True
        >>> _is_recipe_url("https://schweizerfleisch.ch/rezepte")
        False
        >>> _is_recipe_url("https://schweizerfleisch.ch/impressum")
        False
    """
    return bool(_RECIPE_URL_PATTERN.match(url) or _RECIPE_URL_PATTERN_FR.match(url))


def _detect_language(url: str) -> str:
    """Detect language from URL domain.

    Examples:
        >>> _detect_language("https://schweizerfleisch.ch/rezepte/test")
        'de'
        >>> _detect_language("https://viandesuisse.ch/recettes/test")
        'fr'
    """
    if "viandesuisse.ch" in url:
        return "fr"
    return "de"


def _parse_recipe_html(html_text: str, source_url: str, language: str) -> RawRecipe:
    """Parse recipe data from Schweizer Fleisch structured HTML.

    The site uses a consistent layout:
    - Title in <h1>
    - Description in meta description
    - Ingredients in .ingredient or .field--name-field-recipe-ingredient elements
    - Steps in .step or .field--name-field-recipe-step elements

    Raises ValueError if no title can be extracted.
    """
    tree = HTMLParser(html_text)

    # Title from <h1>
    h1 = tree.css_first("h1")
    title = h1.text(strip=True) if h1 else ""
    if not title:
        raise ValueError(f"No recipe title found at {source_url}")

    # Description from meta tag
    description = ""
    meta = tree.css_first('meta[name="description"]')
    if meta:
        description = (meta.attributes.get("content") or "").strip()

    # Ingredients
    ingredients = _extract_ingredients(tree)
    ingredient_groups = _extract_ingredient_groups(tree)

    # Steps
    steps = _extract_steps(tree)

    # Time info
    prep_time = _extract_time(tree, "Aktivzeit")
    total_time = _extract_time(tree, "Gesamtzeit")

    # Images
    image_urls = _extract_images(tree)

    # Keywords
    keywords = _extract_keywords(tree)

    # Category, difficulty, and cuisine from recipe-meta
    category = _extract_category(tree)
    difficulty = _extract_difficulty(tree)
    cuisine = _extract_cuisine(tree)

    # Yield
    yield_amount = _extract_yield(tree)

    return RawRecipe(
        title=title,
        description=description,
        ingredients_raw=ingredients,
        ingredient_groups=ingredient_groups,
        steps_raw=steps,
        yield_amount=yield_amount,
        prep_time=prep_time,
        cook_time=total_time,
        image_urls=image_urls,
        image_captions=[title] * len(image_urls),
        keywords=keywords,
        source_url=source_url,
        language=language,
        category=category,
        difficulty=difficulty,
        cuisine=cuisine,
    )


def _extract_ingredients(tree: HTMLParser) -> list[str]:
    """Extract ingredients from data-react-props JSON or fallback to CSS classes.

    Schweizer Fleisch embeds ingredient data as JSON in a data-react-props attribute
    on a React component element. The JSON structure contains ingredientsLists with
    entities having amount, quantity, and title fields.
    """
    ingredients: list[str] = []

    # Primary: extract from data-react-props JSON
    for node in tree.css("[data-react-props]"):
        props_raw = node.attributes.get("data-react-props") or ""
        props_decoded = html_mod.unescape(props_raw)
        try:
            data = json.loads(props_decoded)
        except (json.JSONDecodeError, TypeError):
            continue

        if "ingredientsLists" not in data:
            continue

        for ing_list in data["ingredientsLists"]:
            entity = ing_list.get("entity", {})
            for ing in entity.get("ingredients", []):
                ie = ing.get("entity", {})
                amount = ie.get("amount", "")
                quantity = ie.get("quantity")
                qty_name = ""
                if isinstance(quantity, dict):
                    qty_entity = quantity.get("entity", {})
                    if isinstance(qty_entity, dict):
                        qty_name = qty_entity.get("shortForm") or qty_entity.get("name") or ""
                title = ie.get("title", "")
                parts = [p for p in (amount, qty_name, title) if p]
                line = " ".join(parts)
                if line:
                    ingredients.append(line)

        if ingredients:
            return ingredients

    # Fallback: try CSS classes
    rows = tree.css(".ingredient")
    for row in rows:
        text = row.text(strip=True)
        text = re.sub(r"\s+", " ", text)
        if text:
            ingredients.append(text)

    return ingredients


def _extract_ingredient_groups(tree: HTMLParser) -> list[RawIngredientGroup]:
    """Extract ingredients preserving group structure from Schweizer Fleisch HTML.

    The site embeds ingredient data in data-react-props JSON with an
    ingredientsLists array. Each list entry may have a title (group label)
    and a list of ingredients.
    """
    groups: list[RawIngredientGroup] = []

    for node in tree.css("[data-react-props]"):
        props_raw = node.attributes.get("data-react-props") or ""
        props_decoded = html_mod.unescape(props_raw)
        try:
            data = json.loads(props_decoded)
        except (json.JSONDecodeError, TypeError):
            continue

        if "ingredientsLists" not in data:
            continue

        for ing_list in data["ingredientsLists"]:
            entity = ing_list.get("entity", {})
            label = (entity.get("title") or entity.get("name") or "").strip() or None
            items: list[str] = []
            for ing in entity.get("ingredients", []):
                ie = ing.get("entity", {})
                amount = ie.get("amount", "")
                quantity = ie.get("quantity")
                qty_name = ""
                if isinstance(quantity, dict):
                    qty_entity = quantity.get("entity", {})
                    if isinstance(qty_entity, dict):
                        qty_name = qty_entity.get("shortForm") or qty_entity.get("name") or ""
                title = ie.get("title", "")
                parts = [p for p in (amount, qty_name, title) if p]
                line = " ".join(parts)
                if line:
                    items.append(line)
            if items:
                groups.append(RawIngredientGroup(label=label, items=items))

        if groups:
            return groups

    # Fallback: wrap flat extraction in a single group
    flat = _extract_ingredients(tree)
    if flat:
        return [RawIngredientGroup(label=None, items=flat)]
    return []


def _extract_steps(tree: HTMLParser) -> list[str]:
    """Extract preparation steps from .preparation__step elements."""
    steps: list[str] = []
    seen: set[str] = set()

    rows = tree.css(".preparation__step")
    if not rows:
        # Fallback to generic step class
        rows = tree.css(".step")

    for row in rows:
        text = row.text(strip=True)
        # Remove leading step numbers like "1 " or "1\n"
        text = re.sub(r"^\d+\s*", "", text)
        text = re.sub(r"\s+", " ", text)
        if text and text not in seen:
            steps.append(text)
            seen.add(text)

    return steps


def _extract_time(tree: HTMLParser, label: str) -> str:
    """Extract time value associated with a label."""
    for node in tree.css("span, div, p"):
        text = node.text(strip=True)
        if label in text:
            match = re.search(r"(\d+\s*(?:h|min|Std)[\s\d]*(?:min)?)", text)
            if match:
                return match.group(1).strip()
    return ""


def _extract_images(tree: HTMLParser) -> list[str]:
    """Extract recipe images from OG meta, data-src, src, and gallery elements.

    Collects the primary image and supplements with gallery/carousel images.
    """
    images: list[str] = []
    seen: set[str] = set()

    # Primary: og:image meta tag (full URL, high quality)
    og = tree.css_first("meta[property='og:image']")
    if og:
        src = (og.attributes.get("content") or "").strip()
        if src:
            images.append(src)
            seen.add(src)

    # Fallback primary: img[data-src] (lazy-loaded images)
    if not images:
        for img in tree.css("img[data-src]"):
            src = img.attributes.get("data-src") or ""
            if src and "/sites/" in src and "/icon" not in src:
                full_url = f"https://schweizerfleisch.ch{src}" if src.startswith("/") else src
                if full_url not in seen:
                    images.append(full_url)
                    seen.add(full_url)
                    break

    # Last resort primary: img[src]
    if not images:
        for img in tree.css("img[src]"):
            src = img.attributes.get("src") or ""
            if src and ("/sites/" in src or "/media/" in src) and src not in seen:
                if "/sprites/" not in src and "/icon" not in src:
                    images.append(src)
                    seen.add(src)
                    break

    # Gallery/carousel images
    for img_url in _extract_gallery_images(tree):
        if img_url not in seen:
            images.append(img_url)
            seen.add(img_url)

    return images


def _extract_gallery_images(tree: HTMLParser) -> list[str]:
    """Extract additional recipe images from Schweizer Fleisch gallery elements.

    Scans for gallery, slider, and step-level image elements beyond the
    primary hero image. Returns deduplicated image URLs from the site.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<div class="recipe-gallery">'
        ...        '<img src="/sites/schweizerfleisch/files/gallery1.jpg"></div>')
        >>> _extract_gallery_images(HTMLParser(html))
        ['https://schweizerfleisch.ch/sites/schweizerfleisch/files/gallery1.jpg']
    """
    images: list[str] = []
    seen: set[str] = set()
    selectors = (
        ".recipe-gallery img, .recipe-slider img, .recipe-carousel img, "
        ".recipe-images img, .field--name-field-recipe-gallery img, "
        ".preparation__step img"
    )
    for node in tree.css(selectors):
        src = (node.attributes.get("data-src") or node.attributes.get("src") or "").strip()
        if not src or "/icon" in src or "/sprites/" in src:
            continue
        full_url = f"https://schweizerfleisch.ch{src}" if src.startswith("/") else src
        if full_url not in seen:
            images.append(full_url)
            seen.add(full_url)
    return images


def _extract_keywords(tree: HTMLParser) -> list[str]:
    """Extract keywords/tags from recipe tag links."""
    keywords: list[str] = []
    for link in tree.css('a[href*="/schlagwort/"]'):
        text = link.text(strip=True)
        if text and text not in keywords:
            keywords.append(text)
    return keywords


def _extract_category(tree: HTMLParser) -> str:
    """Extract recipe category from breadcrumb or tag links.

    Looks for links containing category-like paths or specific keywords
    in the recipe tags that indicate the course type.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<a href="/kategorie/hauptgerichte">Hauptgerichte</a>'
        >>> _extract_category(HTMLParser(html))
        'Hauptgerichte'
    """
    # Try breadcrumb links with category patterns
    for node in tree.css('a[href*="/kategorie/"], a[href*="/catégorie/"]'):
        text = (node.text() or "").strip()
        if text:
            return text

    # Fallback: look for category in recipe-meta section
    for node in tree.css(".recipe-meta span, .recipe-category"):
        text = (node.text() or "").strip()
        lower = text.lower()
        if lower in (
            "hauptgericht",
            "vorspeise",
            "dessert",
            "beilage",
            "plat principal",
            "entrée",
            "accompagnement",
        ):
            return text
    return ""


def _extract_difficulty(tree: HTMLParser) -> str:
    """Extract recipe difficulty from the recipe meta section.

    Schweizer Fleisch shows difficulty as plain text in the recipe-meta div.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-meta"><span>Einfach</span></div>'
        >>> _extract_difficulty(HTMLParser(html))
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
    }
    for node in tree.css(".recipe-meta span, .recipe-meta div, .recipe-difficulty"):
        text = (node.text() or "").strip()
        if text.lower() in difficulty_values:
            return text
    return ""


def _extract_cuisine(tree: HTMLParser) -> str:
    """Extract cuisine from recipe tags or meta description.

    Scans tag links for known cuisine identifiers.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<a href="/schlagwort/asiatisch">Asiatisch</a>'
        >>> _extract_cuisine(HTMLParser(html))
        'Asiatisch'
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
        "chinesisch",
        "chinese",
        "koreanisch",
        "korean",
        "vietnamesisch",
    }
    for link in tree.css('a[href*="/schlagwort/"]'):
        text = (link.text() or "").strip()
        if text.lower() in cuisine_keywords:
            return text
    return ""


def _extract_yield(tree: HTMLParser) -> str:
    """Extract serving/yield information from data-react-props or HTML."""
    # Try data-react-props first
    for node in tree.css("[data-react-props]"):
        props_raw = node.attributes.get("data-react-props") or ""
        props_decoded = html_mod.unescape(props_raw)
        try:
            data = json.loads(props_decoded)
        except (json.JSONDecodeError, TypeError):
            continue
        persons = data.get("numberOfPersons")
        if persons:
            return f"{persons} Portionen"

    # Fallback: look for "Personen" or "Portionen" in text
    for node in tree.css("span, div, p"):
        text = node.text(strip=True)
        match = re.search(r"(\d+)\s*(?:Personen|Portionen)", text)
        if match:
            return f"{match.group(1)} Portionen"
    return ""
