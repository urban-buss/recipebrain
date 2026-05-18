"""Swissmilk recipe source adapter.

Swissmilk is a Swiss recipe platform focused on dairy-based cooking with a
very broad catalogue in DE/FR. Recipes are discovered via sitemap and parsed
via JSON-LD (schema.org Recipe).

Site: https://www.swissmilk.ch
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable
from typing import ClassVar
from xml.etree import ElementTree

import httpx
from selectolax.parser import HTMLParser

from recipebrain.settings import Settings
from recipebrain.sources.base import RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_BY_LANGUAGE: dict[str, str] = {
    "de": "https://www.swissmilk.ch/de/sitemap.xml",
    "fr": "https://www.swissmilk.ch/fr/sitemap.xml",
}
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

        Only fetches sitemaps for languages configured in the source settings.
        Defaults to German-only when no config is present.
        """
        configured_languages = _get_configured_languages(self._settings, self.key)
        for lang in configured_languages:
            sitemap_url = _SITEMAP_BY_LANGUAGE.get(lang)
            if not sitemap_url:
                continue
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

        image_urls = _extract_images(tree)

        return RawRecipe(
            title=title,
            description=_extract_description(tree),
            ingredients_raw=_extract_ingredients(tree),
            steps_raw=_extract_steps(tree),
            yield_amount=_extract_yield(tree),
            prep_time=_extract_prep_time(tree),
            cook_time=_extract_cook_time(tree),
            image_urls=image_urls,
            image_captions=[title] * len(image_urls),
            keywords=_extract_keywords(tree),
            source_url=url,
            language=language,
            category=_extract_category(tree),
            cuisine=_extract_cuisine(tree),
            difficulty=_extract_difficulty(tree),
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


_TIME_TEXT_RE = re.compile(
    r"(?:ca\.?\s*)?"
    r"(?:(\d+)\s*(?:Std\.?|Stunden?|h(?:eures?)?))\s*"
    r"(?:(\d+)\s*(?:Min\.?|Minuten?|min(?:utes?)?))?|"  # hours then optional minutes
    r"(?:ca\.?\s*)?"
    r"(\d+)\s*(?:Min\.?|Minuten?|min(?:utes?)?)",  # minutes only
    re.IGNORECASE,
)


def _parse_time_text(text: str) -> str:
    """Convert Swiss-German/French plain-text duration to ISO 8601.

    Examples:
        >>> _parse_time_text("45 min")
        'PT45M'
        >>> _parse_time_text("ca. 30 Min.")
        'PT30M'
        >>> _parse_time_text("1 Std. 15 Min.")
        'PT1H15M'
        >>> _parse_time_text("2 Stunden")
        'PT2H'
        >>> _parse_time_text("")
        ''
    """
    if not text or not text.strip():
        return ""
    match = _TIME_TEXT_RE.search(text.strip())
    if not match:
        return ""
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    minutes_only = int(match.group(3) or 0)
    if minutes_only:
        minutes = minutes_only
    if hours == 0 and minutes == 0:
        return ""
    parts = ["PT"]
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    return "".join(parts)


def _extract_prep_time(tree: HTMLParser) -> str:
    """Extract recipe prep time as ISO 8601 duration.

    Tries itemprop="prepTime" first, then falls back to parsing
    the .RecipeFacts text.
    """
    node = tree.css_first("[itemprop='prepTime']")
    if node:
        content = (node.attributes.get("content") or "").strip()
        if content:
            return content
    node = tree.css_first(".RecipeFacts")
    if node:
        return _parse_time_text(node.text() or "")
    return ""


def _extract_cook_time(tree: HTMLParser) -> str:
    """Extract recipe cook time as ISO 8601 duration.

    Looks for itemprop="cookTime"; returns empty string if not found.
    """
    node = tree.css_first("[itemprop='cookTime']")
    if node:
        content = (node.attributes.get("content") or "").strip()
        if content:
            return content
    return ""


def _extract_images(tree: HTMLParser) -> list[str]:
    """Extract recipe images from OG meta, header image, and gallery elements.

    Collects the primary image from OG meta or header, then supplements
    with additional gallery/carousel images found on the page.
    """
    images: list[str] = []
    seen: set[str] = set()

    # Primary: og:image meta tag
    og = tree.css_first("meta[property='og:image']")
    if og:
        src = (og.attributes.get("content") or "").strip()
        if src:
            images.append(src)
            seen.add(src)

    # Header image fallback (if no OG)
    if not images:
        for img in tree.css(".RecipeHeader img"):
            src = (img.attributes.get("src") or "").strip()
            if src and not src.startswith("data:") and "/_nuxt/" not in src and src not in seen:
                images.append(src)
                seen.add(src)

    # Gallery/carousel images
    for img_url in _extract_gallery_images(tree):
        if img_url not in seen:
            images.append(img_url)
            seen.add(img_url)

    return images


def _extract_gallery_images(tree: HTMLParser) -> list[str]:
    """Extract additional recipe images from Swissmilk gallery/carousel elements.

    Scans for gallery, slider, and carousel image elements beyond the
    primary hero image. Returns deduplicated image URLs.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-gallery"><img src="https://res.cloudinary.com/swissmilk/image/fetch/gallery1.jpg"></div>'
        >>> _extract_gallery_images(HTMLParser(html))
        ['https://res.cloudinary.com/swissmilk/image/fetch/gallery1.jpg']
    """
    images: list[str] = []
    seen: set[str] = set()
    selectors = (
        ".recipe-gallery img, .recipe-slider img, .recipe-carousel img, "
        ".RecipeGallery img, .RecipeSlider img, "
        ".recipe-images img, .RecipeDetail picture source"
    )
    for node in tree.css(selectors):
        src = (
            node.attributes.get("data-src")
            or _first_srcset_url(node.attributes.get("srcset") or "")
            or node.attributes.get("src")
            or ""
        ).strip()
        if src and not src.startswith("data:") and "/_nuxt/" not in src and src not in seen:
            images.append(src)
            seen.add(src)
    return images


def _first_srcset_url(srcset: str) -> str:
    """Extract the first URL from a srcset attribute value.

    Examples:
        >>> _first_srcset_url("https://example.com/img.jpg 1x, https://example.com/img2.jpg 2x")
        'https://example.com/img.jpg'
        >>> _first_srcset_url("")
        ''
    """
    if not srcset:
        return ""
    return srcset.split(",")[0].split(" ")[0].strip()


def _extract_keywords(tree: HTMLParser) -> list[str]:
    """Extract keywords from meta tag or recipe tag links.

    Swissmilk may include keywords in a meta tag or as tag links on the page.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = ('<html><head><meta name="keywords"'
        ...        ' content="gratin, kartoffel, käse"></head></html>')
        >>> _extract_keywords(HTMLParser(html))
        ['gratin', 'kartoffel', 'käse']
    """
    # Try meta keywords first
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        meta_keywords = [kw.strip() for kw in content.split(",") if kw.strip()]
        if meta_keywords:
            return meta_keywords

    # Try tag links
    keywords: list[str] = []
    for node in tree.css(".RecipeTags a, .recipe-tags a, [class*='tag'] a"):
        text = (node.text() or "").strip()
        if text and text not in keywords:
            keywords.append(text)
    return keywords


def _extract_category(tree: HTMLParser) -> str:
    """Extract recipe category from breadcrumb navigation.

    Swissmilk uses breadcrumb navigation that contains the recipe category.
    Skips generic entries like 'Home', 'Rezepte' and returns the first
    specific category.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<nav class="breadcrumb"><a>Home</a><a>Rezepte</a><a>Hauptgerichte</a></nav>'
        >>> _extract_category(HTMLParser(html))
        'Hauptgerichte'
    """
    skip = {"Home", "Rezepte", "Recettes", "Rezepte & Kochideen", "Recettes & idées cuisine"}
    for node in tree.css("nav.breadcrumb a, .breadcrumb a, .Breadcrumb a"):
        text = (node.text() or "").strip()
        if text and text not in skip:
            return text
    return ""


def _extract_cuisine(tree: HTMLParser) -> str:
    """Extract cuisine from recipe tags or keywords.

    Scans tag links and meta keywords for known cuisine identifiers.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="RecipeTags"><a href="/tag/italienisch">Italienisch</a></div>'
        >>> _extract_cuisine(HTMLParser(html))
        'Italienisch'
        >>> html = '<html><head><meta name="keywords" content="Thai, schnell"></head></html>'
        >>> _extract_cuisine(HTMLParser(html))
        'Thai'
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
        "vietnamien",
        "italien",
        "mexicain",
        "indien",
        "thaïlandais",
        "japonais",
        "grec",
        "chinois",
    }
    # Try tag links
    for node in tree.css(".RecipeTags a, .recipe-tags a, [class*='tag'] a"):
        text = (node.text() or "").strip()
        if text.lower() in cuisine_keywords:
            return text

    # Fallback: scan meta keywords
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        for kw in content.split(","):
            kw = kw.strip()
            if kw.lower() in cuisine_keywords:
                return kw
    return ""


def _extract_difficulty(tree: HTMLParser) -> str:
    """Extract recipe difficulty from recipe facts or meta section.

    Swissmilk shows difficulty as text in the RecipeFacts section
    or as metadata in the page.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="RecipeFacts"><span>Einfach</span></div>'
        >>> _extract_difficulty(HTMLParser(html))
        'Einfach'
        >>> html = '<div class="recipe-meta"><span>leicht</span></div>'
        >>> _extract_difficulty(HTMLParser(html))
        'leicht'
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
    selector = ".RecipeFacts span, .RecipeFacts div, .recipe-meta span, .recipe-difficulty"
    for node in tree.css(selector):
        text = (node.text() or "").strip()
        if text.lower() in difficulty_values:
            return text
    return ""


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


def _get_configured_languages(settings: Settings, key: str) -> list[str]:
    """Return the configured languages for a source, defaulting to [\"de\"]."""
    source_cfg = settings.sources.get(key)
    if source_cfg is None:
        return ["de"]
    return source_cfg.languages
