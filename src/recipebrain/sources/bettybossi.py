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
from recipebrain.sources.base import RawIngredientGroup, RawRecipe, SourceAdapter

logger = logging.getLogger(__name__)

_SITEMAP_BY_LANGUAGE: dict[str, str] = {
    "de": "https://www.bettybossi.ch/sitemap-recipe-de.xml",
    "fr": "https://www.bettybossi.ch/sitemap-recipe-fr.xml",
}
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
            raw = parse_recipe(recipes[0], source_url=url, language=language)
            # Supplement with HTML ingredient groups only when JSON-LD lacks ingredients
            tree = HTMLParser(response.text)
            if not raw.ingredients_raw:
                raw.ingredient_groups = _extract_ingredient_groups(tree)
            # Betty Bossi misuses recipeCuisine for category tags — harvest as keywords
            if raw.cuisine and "," in raw.cuisine:
                cuisine_tags = [k.strip() for k in raw.cuisine.split(",") if k.strip()]
                if not raw.keywords:
                    raw.keywords = cuisine_tags
                else:
                    raw.keywords.extend(cuisine_tags)
            if not raw.keywords:
                raw.keywords = _extract_keywords(tree)
                if not raw.keywords:
                    raw.keywords = _extract_breadcrumb_categories(tree)
                else:
                    raw.keywords.extend(_extract_breadcrumb_categories(tree))
            # Supplement classification from HTML when JSON-LD is incomplete
            if not raw.category:
                raw.category = _extract_category_from_breadcrumb(tree)
            # Betty Bossi misuses recipeCuisine for category tags — always derive from HTML
            raw.cuisine = _extract_cuisine_from_tags(tree)
            # Supplement with gallery images from HTML
            for img in _extract_gallery_images(tree):
                if img not in raw.image_urls:
                    raw.image_urls.append(img)
            return raw

        # HTML fallback
        tree = HTMLParser(response.text)
        title = _extract_title(tree)
        if not title:
            raise ValueError(f"No recipe found at {url}")

        groups = _extract_ingredient_groups(tree)
        ingredients_flat = [item for g in groups for item in g.items]

        return RawRecipe(
            title=title,
            description=_extract_description(tree),
            ingredients_raw=ingredients_flat,
            ingredient_groups=groups,
            steps_raw=_extract_steps(tree),
            yield_amount=_extract_yield(tree),
            prep_time=_extract_time(tree, "prep"),
            cook_time=_extract_time(tree, "cook"),
            image_urls=_extract_images(tree),
            keywords=_extract_keywords(tree),
            source_url=url,
            language=language,
            category=_extract_category_from_breadcrumb(tree),
            cuisine=_extract_cuisine_from_tags(tree),
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


_NAV_KEYWORDS: frozenset[str] = frozenset(
    {
        "hauptmenü",
        "menu schliessen",
        "jetzt entdecken",
        "jetzt weiterstöbern",
        "werbung buchen",
        "shop",
    }
)

_MAX_INGREDIENT_LENGTH = 200


def _is_valid_ingredient_text(text: str) -> bool:
    """Check whether text looks like a genuine ingredient line.

    Rejects navigation/menu text that is too long or contains known
    navigation keywords.

    Examples:
        >>> _is_valid_ingredient_text("200 g Mehl")
        True
        >>> _is_valid_ingredient_text("ShopHauptmenüMenu SchliessenShopJetzt entdecken")
        False
        >>> _is_valid_ingredient_text("")
        False
        >>> _is_valid_ingredient_text("x" * 250)
        False
    """
    if not text:
        return False
    if len(text) > _MAX_INGREDIENT_LENGTH:
        return False
    lower = text.lower()
    return not any(kw in lower for kw in _NAV_KEYWORDS)


def _extract_ingredients(tree: HTMLParser) -> list[str]:
    """Extract ingredients from Betty Bossi's structured ingredient lists.

    Ingredients appear as list items with bold text (name) and quantity text.
    """
    ingredients: list[str] = []
    for li in tree.css("li[itemprop='recipeIngredient'], .ingredient-item"):
        text = (li.text() or "").strip()
        text = " ".join(text.split())
        if text and _is_valid_ingredient_text(text):
            ingredients.append(text)

    # Fallback: look for ingredient rows in step blocks
    if not ingredients:
        for li in tree.css("ul li"):
            text = (li.text() or "").strip()
            text = " ".join(text.split())
            if (
                text
                and _is_valid_ingredient_text(text)
                and any(
                    unit in text
                    for unit in ("g ", "kg ", "dl ", "l ", "EL ", "TL ", "Stk", "Prise")
                )
            ):
                ingredients.append(text)

    return ingredients


def _extract_ingredient_groups(tree: HTMLParser) -> list[RawIngredientGroup]:
    """Extract ingredients preserving group structure from Betty Bossi HTML.

    Betty Bossi structures ingredients in sections. Group headings appear as
    h3/h4 elements or dedicated heading elements within ingredient sections.
    Ingredients within each group are list items.

    Examples:
        Input HTML with groups:
            <section class="ingredients">
                <h3>Für den Teig</h3>
                <ul><li>200 g Mehl</li><li>100 ml Milch</li></ul>
                <h3>Für die Sauce</h3>
                <ul><li>2 dl Rahm</li></ul>
            </section>
        Output:
            [RawIngredientGroup("Für den Teig", [...]),
             RawIngredientGroup("Für die Sauce", [...])]
    """
    groups: list[RawIngredientGroup] = []

    # Strategy 1: Look for grouped ingredient sections with headings
    ingredient_sections = tree.css(
        ".ingredients, .ingredient-section, [class*='ingredient-group'], [class*='ingredientGroup']"
    )

    for section in ingredient_sections:
        current_label: str | None = None
        current_items: list[str] = []

        # Use css('*') for document-order traversal of all descendants
        for child in section.css("*"):
            if child.tag in ("h3", "h4", "h5"):
                text = (child.text() or "").strip()
                # Skip the main "Zutaten" / "Ingrédients" heading
                if text.lower() in ("zutaten", "ingrédients", "ingredients", "ingredienti"):
                    continue
                if text:
                    # Save previous group if it has items
                    if current_items:
                        groups.append(RawIngredientGroup(label=current_label, items=current_items))
                    current_label = text
                    current_items = []
            elif child.tag == "li":
                item_text = (child.text() or "").strip()
                item_text = " ".join(item_text.split())
                if item_text and _is_valid_ingredient_text(item_text):
                    current_items.append(item_text)

        # Save the last group
        if current_items:
            groups.append(RawIngredientGroup(label=current_label, items=current_items))

    if groups:
        return groups

    # Strategy 2: Fall back to flat extraction wrapped in a single group
    flat = _extract_ingredients(tree)
    if flat:
        return [RawIngredientGroup(label=None, items=flat)]
    return []


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


def _extract_gallery_images(tree: HTMLParser) -> list[str]:
    """Extract additional recipe images from Betty Bossi's page gallery.

    Scans HTML for gallery/carousel/slider image elements that are not
    captured by JSON-LD. Returns deduplicated URLs from media.bettybossi.ch.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<div class="recipe-gallery"><img data-src="https://media.bettybossi.ch/img1.jpg"></div>'
        >>> _extract_gallery_images(HTMLParser(html))
        ['https://media.bettybossi.ch/img1.jpg']
    """
    images: list[str] = []
    seen: set[str] = set()
    selectors = ".recipe-gallery img, .recipe-slider img, .recipe-carousel img, picture source"
    for node in tree.css(selectors):
        src = (
            node.attributes.get("data-src")
            or _first_srcset_url(node.attributes.get("srcset") or "")
            or node.attributes.get("src")
            or ""
        ).strip()
        if src and "media.bettybossi.ch" in src and src not in seen:
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
    """Extract recipe keywords/tags."""
    keywords: list[str] = []
    meta = tree.css_first("meta[name='keywords']")
    if meta:
        content = meta.attributes.get("content") or ""
        keywords = [k.strip() for k in content.split(",") if k.strip()]
    return keywords


def _extract_breadcrumb_categories(tree: HTMLParser) -> list[str]:
    """Extract category keywords from breadcrumb navigation.

    Betty Bossi uses breadcrumb navigation that contains recipe categories
    useful as supplementary keyword data.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = (
        ...     '<nav class="breadcrumb">'
        ...     '<a href="/">Home</a>'
        ...     '<a href="/r">Rezepte</a>'
        ...     '<a href="/r/g">Gratin</a></nav>'
        ... )
        >>> _extract_breadcrumb_categories(HTMLParser(html))
        ['Gratin']
    """
    keywords: list[str] = []
    skip = {"Home", "Rezepte", "Recettes", "Accueil"}
    seen: set[str] = set()
    for node in tree.css("nav.breadcrumb a, .breadcrumb-item a"):
        text = (node.text() or "").strip()
        if text and text not in skip and text not in seen:
            keywords.append(text)
            seen.add(text)
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


def _get_configured_languages(settings: Settings, key: str) -> list[str]:
    """Return the configured languages for a source, defaulting to [\"de\"]."""
    source_cfg = settings.sources.get(key)
    if source_cfg is None:
        return ["de"]
    return source_cfg.languages


def _extract_category_from_breadcrumb(tree: HTMLParser) -> str:
    """Extract recipe category from breadcrumb navigation.

    Returns the first non-generic breadcrumb text as the category.

    Examples:
        >>> from selectolax.parser import HTMLParser
        >>> html = '<nav class="breadcrumb"><a>Home</a><a>Rezepte</a><a>Hauptgerichte</a></nav>'
        >>> _extract_category_from_breadcrumb(HTMLParser(html))
        'Hauptgerichte'
    """
    skip = {"Home", "Rezepte", "Recettes", "Accueil"}
    for node in tree.css("nav.breadcrumb a, .breadcrumb-item a, .breadcrumb a"):
        text = (node.text() or "").strip()
        if text and text not in skip:
            return text
    return ""


def _extract_cuisine_from_tags(tree: HTMLParser) -> str:
    """Extract cuisine from recipe tag links or meta keywords.

    Scans tag links and meta keywords for known cuisine identifiers.

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
        "chinesisch",
        "chinese",
        "koreanisch",
        "korean",
        "vietnamesisch",
    }
    for node in tree.css(".recipe-tags a, .tag a, [class*='tag'] a"):
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
