"""Data transformation: raw scraped data → normalised schema-conformant records.

Converts RawRecipe instances (from source adapters) into dicts that conform
to writer.SCHEMAS. This is the bridge between scraping and Parquet storage.

Key transformations:
- ISO 8601 durations → integer minutes
- Title normalisation (lowercase, accent-stripped)
- Content hashing for change detection
- External ID extraction from URLs
- Timestamp generation
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime

from recipebrain.computed import (
    build_computed_tags,
    compute_cooking_method,
    compute_dietary_flags,
    compute_food_groups,
    compute_primary_protein,
    compute_taste_profile,
    compute_weight_class,
)
from recipebrain.normalise.ingredients import get_ingredient_id
from recipebrain.parse.ingredient_line import parse_ingredient_line
from recipebrain.sources.base import RawIngredientGroup, RawRecipe

# ---------------------------------------------------------------------------
# Classification normalisation
# ---------------------------------------------------------------------------

_COURSE_MAP: dict[str, str] = {
    "hauptgericht": "main",
    "main course": "main",
    "main dish": "main",
    "main": "main",
    "vorspeise": "starter",
    "starter": "starter",
    "appetizer": "starter",
    "entrée": "starter",
    "dessert": "dessert",
    "nachspeise": "dessert",
    "süsses": "dessert",
    "beilage": "side",
    "side dish": "side",
    "side": "side",
    "bake": "bake",
    "backen": "bake",
    "gebäck": "bake",
    "getränk": "drink",
    "drink": "drink",
    "beverage": "drink",
    "smoothie": "drink",
}

_DIFFICULTY_MAP: dict[str, str] = {
    "easy": "easy",
    "einfach": "easy",
    "leicht": "easy",
    "facile": "easy",
    "medium": "medium",
    "mittel": "medium",
    "normal": "medium",
    "moyen": "medium",
    "advanced": "advanced",
    "schwer": "advanced",
    "schwierig": "advanced",
    "difficile": "advanced",
}


def _normalise_course(raw: str) -> str | None:
    """Map a raw category string to a normalised course enum value.

    Examples:
        >>> _normalise_course("Hauptgericht")
        'main'
        >>> _normalise_course("Dessert")
        'dessert'
        >>> _normalise_course("")
    """
    if not raw:
        return None
    return _COURSE_MAP.get(raw.strip().lower())


def _normalise_cuisine(raw: str) -> str | None:
    """Normalise a cuisine string to lowercase.

    Examples:
        >>> _normalise_cuisine("Swiss")
        'swiss'
        >>> _normalise_cuisine("Italian")
        'italian'
        >>> _normalise_cuisine("")
    """
    if not raw:
        return None
    return raw.strip().lower()


def _normalise_difficulty(raw: str) -> str | None:
    """Map a raw difficulty string to a normalised difficulty enum value.

    Examples:
        >>> _normalise_difficulty("Einfach")
        'easy'
        >>> _normalise_difficulty("medium")
        'medium'
        >>> _normalise_difficulty("")
    """
    if not raw:
        return None
    return _DIFFICULTY_MAP.get(raw.strip().lower())


def _infer_difficulty(raw_difficulty: str, total_minutes: int | None) -> str | None:
    """Resolve difficulty from explicit value or infer from total cook time.

    If raw_difficulty is provided and maps to a known value, use it.
    Otherwise, infer from total_minutes:
      - ≤ 30 min → easy
      - ≤ 60 min → medium
      - > 60 min → advanced

    Examples:
        >>> _infer_difficulty("Einfach", 90)
        'easy'
        >>> _infer_difficulty("", 25)
        'easy'
        >>> _infer_difficulty("", 45)
        'medium'
        >>> _infer_difficulty("", 90)
        'advanced'
        >>> _infer_difficulty("", None)
    """
    explicit = _normalise_difficulty(raw_difficulty)
    if explicit:
        return explicit
    if total_minutes is None:
        return None
    if total_minutes <= 30:
        return "easy"
    if total_minutes <= 60:
        return "medium"
    return "advanced"


# ---------------------------------------------------------------------------
# Public API — classification extraction
# ---------------------------------------------------------------------------


def extract_classification(data: dict) -> dict:
    """Extract normalised classification fields from raw recipe metadata.

    Accepts a dict with JSON-LD style keys and returns normalised
    classification values. Falls back to scanning ``keywords`` for
    course and difficulty when explicit fields are absent.

    Args:
        data: Dict with optional keys:
            - ``recipeCategory`` / ``category``: raw category string
            - ``recipeCuisine`` / ``cuisine``: raw cuisine string
            - ``difficulty``: raw difficulty string
            - ``keywords``: list of keyword strings
            - ``total_minutes``: integer total cook time (for difficulty inference)

    Returns:
        Dict with keys ``course``, ``cuisine``, ``difficulty`` (values may be None).

    Examples:
        >>> extract_classification({'recipeCategory': 'Hauptgericht'})
        {'course': 'main', 'cuisine': None, 'difficulty': None}
        >>> extract_classification({'keywords': ['einfach', 'Schweizer Küche']})
        {'course': None, 'cuisine': None, 'difficulty': 'easy'}
    """
    category = data.get("recipeCategory") or data.get("category", "")
    cuisine_raw = data.get("recipeCuisine") or data.get("cuisine", "")
    difficulty_raw = data.get("difficulty", "")
    keywords = data.get("keywords") or []
    total_minutes = data.get("total_minutes")

    course = _normalise_course(category)
    cuisine = _normalise_cuisine(cuisine_raw)
    difficulty = _infer_difficulty(difficulty_raw, total_minutes)

    # Fallback: scan keywords for course / difficulty when not resolved above
    if not course:
        for kw in keywords:
            course = _normalise_course(kw)
            if course:
                break

    if not difficulty:
        for kw in keywords:
            difficulty = _normalise_difficulty(kw)
            if difficulty:
                break

    return {
        "course": course,
        "cuisine": cuisine,
        "difficulty": difficulty,
    }


# ---------------------------------------------------------------------------
# Public API — row builders
# ---------------------------------------------------------------------------


def build_recipe_row(
    raw: RawRecipe,
    source_id: int,
    recipe_id: int,
    ingredient_rows: list[dict] | None = None,
) -> dict:
    """Convert a RawRecipe into a dict matching SCHEMAS["recipes"].

    Args:
        raw: The raw recipe data from a source adapter.
        source_id: FK to the sources table.
        recipe_id: Assigned PK for this recipe.
        ingredient_rows: Pre-built ingredient row dicts (from
            ``build_recipe_ingredients_rows``). When provided, computed
            classification tags are derived from the resolved ingredients.

    Returns:
        Dict with all columns for the recipes schema.
    """
    prep = _parse_iso_duration(raw.prep_time)
    cook = _parse_iso_duration(raw.cook_time)
    total = None
    if prep is not None and cook is not None:
        total = prep + cook
    elif prep is not None:
        total = prep
    elif cook is not None:
        total = cook

    now = datetime.now(UTC)

    course = _normalise_course(raw.category)
    cuisine = _normalise_cuisine(raw.cuisine)
    difficulty = _infer_difficulty(raw.difficulty, total)
    keywords = raw.keywords or []
    ing_rows = ingredient_rows or []

    # Computed classification tags
    primary_protein = compute_primary_protein(ing_rows)
    taste_profile = compute_taste_profile(course, ing_rows, keywords)
    weight_class = compute_weight_class(
        course,
        cook,
        ing_rows,
        keywords,
        primary_protein,
    )
    cooking_method = compute_cooking_method(raw.steps_raw, keywords)
    dietary_flags = compute_dietary_flags(ing_rows, total_minutes=total)
    food_groups = compute_food_groups(ing_rows, cooking_method, weight_class)
    computed_tags = build_computed_tags(
        primary_protein,
        taste_profile,
        weight_class,
        cooking_method,
        dietary_flags,
        course,
        cuisine,
        difficulty,
    )

    return {
        "id": recipe_id,
        "source_id": source_id,
        "source_external_id": _extract_external_id(raw.source_url),
        "source_url": raw.source_url,
        "title": raw.title,
        "title_normalised": normalise_title(raw.title),
        "language": raw.language,
        "description": raw.description,
        "servings": _parse_servings(raw.yield_amount),
        "prep_minutes": prep,
        "cook_minutes": cook,
        "total_minutes": total,
        "difficulty": difficulty,
        "cuisine": cuisine,
        "course": course,
        "primary_image_url": raw.image_urls[0] if raw.image_urls else None,
        "original_keywords": keywords,
        "owner_rating": None,
        "starred": False,
        "times_cooked": 0,
        "last_cooked_at": None,
        "scraped_at": now,
        "updated_at": now,
        "content_hash": _compute_content_hash(raw),
        "status": "active",
        "primary_protein": primary_protein,
        "taste_profile": taste_profile,
        "weight_class": weight_class,
        "cooking_method": cooking_method,
        "dietary_flags": dietary_flags,
        "food_groups": food_groups,
        "computed_tags": computed_tags,
    }


def build_recipe_steps_rows(recipe_id: int, steps: list[str]) -> list[dict]:
    """Convert step text list into dicts matching SCHEMAS["recipe_steps"].

    Args:
        recipe_id: FK to the recipes table.
        steps: Ordered list of step text strings.

    Returns:
        List of dicts, one per step.
    """
    return [
        {
            "recipe_id": recipe_id,
            "step_no": i + 1,
            "text": text,
            "image_url": None,
        }
        for i, text in enumerate(steps)
    ]


def build_recipe_images_rows(
    recipe_id: int,
    image_urls: list[str],
    local_paths: list[str | None] | None = None,
) -> list[dict]:
    """Convert image URL list into dicts matching SCHEMAS["recipe_images"].

    Args:
        recipe_id: FK to the recipes table.
        image_urls: Ordered list of image URLs.
        local_paths: Optional parallel list of local file paths (relative to
            output dir). Pass ``None`` when images have not been downloaded.

    Returns:
        List of dicts, one per image.
    """
    paths = local_paths or [None] * len(image_urls)
    return [
        {
            "recipe_id": recipe_id,
            "seq": i + 1,
            "url": url,
            "local_path": paths[i] if i < len(paths) else None,
            "caption": None,
        }
        for i, url in enumerate(image_urls)
    ]


def build_recipe_ingredients_rows(
    recipe_id: int,
    ingredients_raw: list[str] | None = None,
    *,
    ingredient_groups: list[RawIngredientGroup] | None = None,
) -> list[dict]:
    """Convert raw ingredient lines into dicts matching SCHEMAS["recipe_ingredients"].

    Parses each line to extract quantity, unit, and prep_note, then attempts
    to link to the canonical ingredient catalogue via ``get_ingredient_id``.

    Accepts either a flat list via ``ingredients_raw`` (backward compat) or
    structured ``ingredient_groups`` with group labels. When groups are provided,
    ``group_label`` is populated per-row.

    Args:
        recipe_id: FK to the recipes table.
        ingredients_raw: Flat list of raw ingredient text lines (legacy).
        ingredient_groups: Structured groups with optional labels.

    Returns:
        List of dicts, one per ingredient line.
    """
    groups: list[RawIngredientGroup]
    if ingredient_groups:
        groups = ingredient_groups
    elif ingredients_raw:
        groups = [RawIngredientGroup(label=None, items=ingredients_raw)]
    else:
        return []

    rows: list[dict] = []
    seq = 1
    for group in groups:
        for text in group.items:
            parsed = parse_ingredient_line(text)
            ingredient_id = get_ingredient_id(parsed.ingredient) if parsed.ingredient else None
            rows.append(
                {
                    "recipe_id": recipe_id,
                    "seq": seq,
                    "ingredient_id": ingredient_id,
                    "raw_text": text,
                    "quantity": parsed.quantity,
                    "unit": parsed.unit,
                    "prep_note": parsed.prep_note,
                    "optional": parsed.optional,
                    "group_label": group.label,
                }
            )
            seq += 1
    return rows


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_ISO_DURATION_RE = re.compile(
    r"^PT?"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+)S)?$",
    re.IGNORECASE,
)


def _parse_iso_duration(iso: str) -> int | None:
    """Parse an ISO 8601 duration string into total minutes.

    Examples:
        >>> _parse_iso_duration("PT15M")
        15
        >>> _parse_iso_duration("PT1H30M")
        90
        >>> _parse_iso_duration("PT2H")
        120
        >>> _parse_iso_duration("")
        None
    """
    if not iso or not iso.strip():
        return None

    match = _ISO_DURATION_RE.match(iso.strip())
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    total = hours * 60 + minutes + (1 if seconds >= 30 else 0)
    return total if total > 0 else None


def normalise_title(title: str) -> str:
    """Normalise a recipe title for search: lowercase, strip accents, collapse whitespace.

    Examples:
        >>> normalise_title("Crème Brûlée mit Früchten")
        'creme brulee mit fruchten'
        >>> normalise_title("  POULET   Brust  ")
        'poulet brust'
    """
    # Decompose unicode, strip combining marks (accents)
    nfkd = unicodedata.normalize("NFKD", title)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase and collapse whitespace
    return " ".join(stripped.lower().split())


def _compute_content_hash(raw: RawRecipe) -> str:
    """Compute a stable SHA-256 hash of the recipe's core content.

    Used for change detection during incremental ETL.
    Hash covers: title, ingredients, steps (order-sensitive).
    """
    parts = [
        raw.title,
        "\n".join(raw.ingredients_raw),
        "\n".join(raw.steps_raw),
    ]
    content = "\x1f".join(parts)  # unit separator as delimiter
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_external_id(url: str) -> str:
    """Extract a stable external ID from a recipe URL.

    Uses the last meaningful path segment as the ID.

    Examples:
        >>> _extract_external_id("https://fooby.ch/de/rezepte/pouletbrust-12345")
        'pouletbrust-12345'
        >>> _extract_external_id("https://migusto.migros.ch/de/rezepte/pasta-carbonara.html")
        'pasta-carbonara'
    """
    if not url:
        return ""

    # Strip query params and fragment
    path = url.split("?")[0].split("#")[0]
    # Get last non-empty path segment
    segments = [s for s in path.rstrip("/").split("/") if s]
    if not segments:
        return ""

    slug = segments[-1]
    # Strip common extensions
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    return slug


_SERVINGS_RE = re.compile(r"(\d+)")


def _parse_servings(yield_amount: str) -> int | None:
    """Extract an integer servings count from a yield string.

    Examples:
        >>> _parse_servings("4 Portionen")
        4
        >>> _parse_servings("6")
        6
        >>> _parse_servings("")
        None
    """
    if not yield_amount:
        return None
    match = _SERVINGS_RE.search(yield_amount)
    if match:
        return int(match.group(1))
    return None
