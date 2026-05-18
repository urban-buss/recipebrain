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
    # Main courses
    "hauptgericht": "main",
    "hauptgerichte": "main",
    "hauptspeise": "main",
    "main course": "main",
    "main dish": "main",
    "main": "main",
    "plat principal": "main",
    # Starters
    "vorspeise": "starter",
    "vorspeisen": "starter",
    "starter": "starter",
    "appetizer": "starter",
    "entrée": "starter",
    "suppe": "starter",
    "suppen": "starter",
    "soupe": "starter",
    "salat": "starter",
    "salate": "starter",
    "salade": "starter",
    "apéro": "starter",
    "apéritif": "starter",
    "fingerfood": "starter",
    # Desserts
    "dessert": "dessert",
    "desserts": "dessert",
    "nachspeise": "dessert",
    "süsses": "dessert",
    # Sides
    "beilage": "side",
    "beilagen": "side",
    "side dish": "side",
    "side": "side",
    "snack": "snack",
    "snacks": "snack",
    "znüni": "snack",
    "zvieri": "snack",
    # Breakfast
    "breakfast": "breakfast",
    "brunch": "breakfast",
    "frühstück": "breakfast",
    "brunch & frühstück": "breakfast",
    "petit-déjeuner": "breakfast",
    # Baking
    "bake": "bake",
    "backen": "bake",
    "gebäck": "bake",
    "kuchen": "bake",
    "torten": "bake",
    "brot": "bake",
    "pâtisserie": "bake",
    # Drinks
    "getränk": "drink",
    "getränke": "drink",
    "drink": "drink",
    "drinks": "drink",
    "beverage": "drink",
    "smoothie": "drink",
    "cocktail": "drink",
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


# Title patterns → course.  Checked in order; first match wins.
_COURSE_TITLE_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    # Starter (salads & soups)
    (
        re.compile(
            r"salat\b|suppe\b|schaumsuppe|bouillon|consommé|velouté",
            re.IGNORECASE,
        ),
        "starter",
    ),
    # Bake (cakes, pastries, bread)
    (
        re.compile(
            r"torte\b|kuchen\b|cake\b|gugelhopf|muffin|cupcake"
            r"|gipfeli|brioche|focaccia|zopf\b|pie\b"
            r"|schnecken\b|wähe\b|tarte\b|strudel\b|biscuit"
            r"|chaussons?",
            re.IGNORECASE,
        ),
        "bake",
    ),
    # Breakfast
    (
        re.compile(
            r"\bpancake[s]?\b|\bporridge\b|\bgranola\b|\bmüesli\b"
            r"|\bmilchreis\b|\bbirchermüesli\b|\bfrühstück",
            re.IGNORECASE,
        ),
        "breakfast",
    ),
    # Main (protein-centred dishes, complete meals) — checked before side
    # so that "Schweinssteak mit Tomaten-Relish" resolves to main.
    (
        re.compile(
            r"steak\b|schnitzel|filet\b|braten\b|geschnetzeltes"
            r"|cordon\s*bleu|entrecôte|côtelette|köfte|kebab"
            r"|burger\b|hotdog|sandwich|wrap\b|quiche"
            r"|curry\b|eintopf|auflauf|gratin\b|bowl\b"
            r"|lachs\b|poulet|hähnchen|schwein|schinken|rind"
            r"|lamm\b|hackfleisch|hackbraten",
            re.IGNORECASE,
        ),
        "main",
    ),
    # Side (sauces, dips, accompaniments) — no \b prefix on terms that
    # commonly form German compound suffixes (Vanillesauce, Whiskymarinade).
    (
        re.compile(
            r"sauce\b|dip\b|marinade\b|dressing\b"
            r"|relish\b|pesto\b|chutney\b|salsa\b",
            re.IGNORECASE,
        ),
        "side",
    ),
]

# Keywords that indicate a course when no explicit category is set.
_COURSE_KEYWORD_SIGNALS: dict[str, str] = {
    "brunch & frühstück": "breakfast",
    "fleisch": "main",
    "geflügel": "main",
    "fisch": "main",
}


def _infer_course(
    raw_category: str,
    title: str,
    keywords: list[str],
) -> str | None:
    """Resolve course from explicit category, keywords, or title patterns.

    Resolution order:
    1. Explicit category via ``_normalise_course``.
    2. Keywords scanned against ``_COURSE_MAP``.
    3. Title scanned against ``_COURSE_TITLE_SIGNALS``.
    4. Keywords scanned against ``_COURSE_KEYWORD_SIGNALS`` (ingredient-based).

    Examples:
        >>> _infer_course("Hauptgericht", "Anything", [])
        'main'
        >>> _infer_course("", "Zitronentorte", [])
        'bake'
        >>> _infer_course("", "Quinoasalat", [])
        'starter'
        >>> _infer_course("", "Avocado-Dip", [])
        'side'
        >>> _infer_course("", "Pancakes ohne Ei", ["Brunch & Frühstück"])
        'breakfast'
        >>> _infer_course("", "Grillierte Zucchini-Spiessli", ["Gemüse", "Salat"])
    """
    # 1. Explicit category
    explicit = _normalise_course(raw_category)
    if explicit:
        return explicit

    # 2. Keyword scan against _COURSE_MAP (e.g. "Dessert" in keywords)
    for kw in keywords:
        mapped = _normalise_course(kw)
        if mapped:
            return mapped

    # 3. Title pattern scan
    for pattern, course in _COURSE_TITLE_SIGNALS:
        if pattern.search(title):
            return course

    # 4. Ingredient-keyword heuristic (lower priority)
    for kw in keywords:
        kw_lower = kw.strip().lower()
        if kw_lower in _COURSE_KEYWORD_SIGNALS:
            return _COURSE_KEYWORD_SIGNALS[kw_lower]

    return None


def _normalise_cuisine(raw: str) -> str | None:
    """Normalise a cuisine string to lowercase, rejecting category tag dumps.

    Returns None for empty strings or values that look like concatenated
    category tags (contain commas) rather than a single cuisine identifier.

    Examples:
        >>> _normalise_cuisine("Swiss")
        'swiss'
        >>> _normalise_cuisine("Italian")
        'italian'
        >>> _normalise_cuisine("")
        >>> _normalise_cuisine("milchprodukte, käse, eier")
    """
    if not raw:
        return None
    stripped = raw.strip().lower()
    # Reject multi-value category dumps (real cuisine is a single term)
    if "," in stripped:
        return None
    return stripped


# Title/keyword patterns → cuisine.  Checked in order; first match wins.
# Each entry: (compiled regex, cuisine value).
_CUISINE_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    # Swiss / Alpine
    (
        re.compile(
            r"r[öo]sti|fondue|raclette|bircher|z[üu]ri|berner|[äa]lpler"
            r"|zopf|älplermagronen|capuns|cholera|pizokel",
            re.IGNORECASE,
        ),
        "swiss",
    ),
    # Italian
    (
        re.compile(
            r"pasta|risotto|pizza|tiramisu|panna\s*cotta|carbonara"
            r"|bolognese|lasagne|gnocchi|tortellini|bruschetta|focaccia"
            r"|minestrone|ossobuco|parmigiana|saltimbocca|vitello\s*tonnato"
            r"|ciabatta|polenta|antipast[io]|arancin[ie]|calzone",
            re.IGNORECASE,
        ),
        "italian",
    ),
    # Thai
    (
        re.compile(
            r"\bthai\b|pad\s*thai|tom\s*kha|tom\s*yum|green\s*curry"
            r"|panang|massaman|som\s*tam",
            re.IGNORECASE,
        ),
        "thai",
    ),
    # Japanese
    (
        re.compile(
            r"\bsushi\b|ramen|tempura|teriyaki|miso(?:\s*suppe)?"
            r"|gyoza|udon|soba|onigiri|okonomiyaki|yakitori",
            re.IGNORECASE,
        ),
        "japanese",
    ),
    # Chinese
    (
        re.compile(
            r"wonton|dim\s*sum|kung\s*pao|sweet\s*(?:and|&)\s*sour"
            r"|chow\s*mein|fried\s*rice|pek?ing|szechuan|mapo\s*tofu",
            re.IGNORECASE,
        ),
        "chinese",
    ),
    # Korean
    (
        re.compile(
            r"kimchi|bibimbap|bulgogi|korean|japchae|tteokbokki",
            re.IGNORECASE,
        ),
        "korean",
    ),
    # Vietnamese
    (
        re.compile(
            r"\bpho\b|b[áa]nh\s*m[ìi]|vietnamese|summer\s*roll[s]?",
            re.IGNORECASE,
        ),
        "vietnamese",
    ),
    # Generic Asian (catch-all after specific Asian cuisines)
    (
        re.compile(
            r"\bwok\b|stir[\s-]*fry|asia(?:tisch)?|nasi\s*goreng"
            r"|satay|sat[ée]\b|curry(?!wurst)",
            re.IGNORECASE,
        ),
        "asian",
    ),
    # Indian
    (
        re.compile(
            r"\bindisch\b|tandoori|naan\b|chapati|dhal|dal\b"
            r"|masala|tikka|samosa|biryani|paneer|vindaloo|korma",
            re.IGNORECASE,
        ),
        "indian",
    ),
    # Mexican
    (
        re.compile(
            r"\btaco[s]?\b|burrito|quesadilla|enchilada|fajita"
            r"|guacamole|mexikan|nacho[s]?\b|chili\s*con\s*carne",
            re.IGNORECASE,
        ),
        "mexican",
    ),
    # French
    (
        re.compile(
            r"quiche|gratin|cr[êe]pe[s]?\b|ratatouille|bouillabaisse"
            r"|cr[oô]quer?|flambée?|béchamel|proven[çc]al"
            r"|coq\s*au\s*vin|blanquette|boeuf\s*bourguignon",
            re.IGNORECASE,
        ),
        "french",
    ),
    # Greek
    (
        re.compile(
            r"tzatziki|gyros|moussaka|souvlaki|griechisch",
            re.IGNORECASE,
        ),
        "greek",
    ),
    # Middle Eastern
    (
        re.compile(
            r"falafel|hummus|taboul[ée]|shawarma|kebab|lahmacun"
            r"|orientalisch|couscous|harissa|baharat|za.atar",
            re.IGNORECASE,
        ),
        "middle-eastern",
    ),
    # Mediterranean (broad, lower priority)
    (
        re.compile(
            r"mediterran",
            re.IGNORECASE,
        ),
        "mediterranean",
    ),
    # American
    (
        re.compile(
            r"burger[s]?\b|bbq|barbecue|mac\s*(?:and|&|n)\s*cheese"
            r"|pancake[s]?\b|cheesecake|brownie[s]?\b|muffin[s]?\b",
            re.IGNORECASE,
        ),
        "american",
    ),
]


def _infer_cuisine(
    raw_cuisine: str,
    title: str,
    keywords: list[str],
) -> str | None:
    """Resolve cuisine from explicit value or infer from title/keywords.

    If raw_cuisine is provided and valid, use it directly.
    Otherwise scan the recipe title and keywords for cuisine signal patterns.

    Examples:
        >>> _infer_cuisine("Swiss", "Anything", [])
        'swiss'
        >>> _infer_cuisine("", "Spaghetti Carbonara", [])
        'italian'
        >>> _infer_cuisine("", "Pad Thai mit Poulet", [])
        'thai'
        >>> _infer_cuisine("", "Gemüseauflauf", [])
    """
    explicit = _normalise_cuisine(raw_cuisine)
    if explicit:
        return explicit

    # Scan title first (strongest signal)
    for pattern, cuisine in _CUISINE_SIGNALS:
        if pattern.search(title):
            return cuisine

    # Scan keywords
    joined_keywords = " ".join(keywords)
    for pattern, cuisine in _CUISINE_SIGNALS:
        if pattern.search(joined_keywords):
            return cuisine

    return None


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


def extract_classification(data: dict | RawRecipe) -> dict:
    """Extract normalised classification fields from raw recipe metadata.

    Accepts a dict with JSON-LD style keys **or** a ``RawRecipe`` instance
    and returns normalised classification values.  Falls back to scanning
    ``keywords`` for course and difficulty when explicit fields are absent.

    Args:
        data: Dict with optional keys (``recipeCategory``, ``recipeCuisine``,
            ``difficulty``, ``keywords``, ``total_minutes``) **or** a
            ``RawRecipe`` dataclass.

    Returns:
        Dict with keys ``course``, ``cuisine``, ``difficulty`` (values may be None).

    Examples:
        >>> extract_classification({'recipeCategory': 'Hauptgericht'})
        {'course': 'main', 'cuisine': None, 'difficulty': None}
        >>> extract_classification({'keywords': ['einfach', 'Schweizer Küche']})
        {'course': None, 'cuisine': None, 'difficulty': 'easy'}
    """
    if isinstance(data, RawRecipe):
        data = {
            "recipeCategory": data.category,
            "recipeCuisine": data.cuisine,
            "difficulty": data.difficulty,
            "keywords": data.keywords,
            "total_minutes": None,
            "title": data.title,
        }
    category = data.get("recipeCategory") or data.get("category", "")
    cuisine_raw = data.get("recipeCuisine") or data.get("cuisine", "")
    difficulty_raw = data.get("difficulty", "")
    keywords = data.get("keywords") or []
    total_minutes = data.get("total_minutes")
    title = data.get("title", "")

    course = _infer_course(category, title, keywords)
    cuisine = _infer_cuisine(cuisine_raw, title, keywords)
    difficulty = _infer_difficulty(difficulty_raw, total_minutes)

    # Fallback: scan keywords for difficulty when not resolved above
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
    raw_total = _parse_iso_duration(raw.total_time)

    # Detect source duplication: when prep == cook == totalTime, the source
    # copied totalTime into both prep and cook fields (common pattern on
    # Betty Bossi and similar sites). Correct by using totalTime as the
    # canonical total and nulling out the duplicated prep/cook.
    total = None
    if (
        prep is not None
        and cook is not None
        and prep == cook
        and raw_total is not None
        and raw_total == prep
    ):
        total = raw_total
        prep = None
        cook = None
    elif prep is not None and cook is not None:
        total = prep + cook
    elif prep is not None:
        total = prep
    elif cook is not None:
        total = cook
    elif raw_total is not None:
        total = raw_total

    now = datetime.now(UTC)

    keywords = raw.keywords or []
    course = _infer_course(raw.category, raw.title, keywords)
    cuisine = _infer_cuisine(raw.cuisine, raw.title, keywords)
    difficulty = _infer_difficulty(raw.difficulty, total)
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

    return {
        "id": recipe_id,
        "source_id": source_id,
        "source_external_id": _extract_external_id(raw.source_url, raw.language),
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
    captions: list[str] | None = None,
) -> list[dict]:
    """Convert image URL list into dicts matching SCHEMAS["recipe_images"].

    Args:
        recipe_id: FK to the recipes table.
        image_urls: Ordered list of image URLs.
        local_paths: Optional parallel list of local file paths (relative to
            output dir). Pass ``None`` when images have not been downloaded.
        captions: Optional parallel list of caption strings. Pass ``None``
            when captions are unavailable.

    Returns:
        List of dicts, one per image.
    """
    paths: list[str | None] = (
        list(local_paths) if local_paths is not None else [None] * len(image_urls)
    )
    caps: list[str | None] = list(captions) if captions is not None else [None] * len(image_urls)
    return [
        {
            "recipe_id": recipe_id,
            "seq": i + 1,
            "url": url,
            "local_path": paths[i] if i < len(paths) else None,
            "caption": caps[i] if i < len(caps) else None,
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
    Hash covers: language, title, ingredients, steps (order-sensitive).
    """
    parts = [
        raw.language or "",
        raw.title,
        "\n".join(raw.ingredients_raw),
        "\n".join(raw.steps_raw),
    ]
    content = "\x1f".join(parts)  # unit separator as delimiter
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_external_id(url: str, language: str | None = None) -> str:
    """Extract a stable external ID from a recipe URL.

    Uses the last meaningful path segment as the ID. When ``language`` is
    provided and the slug does not already end with the language suffix,
    appends ``-{language}`` to ensure uniqueness for multilingual sources.

    Examples:
        >>> _extract_external_id("https://fooby.ch/de/rezepte/pouletbrust-12345", "de")
        'pouletbrust-12345-de'
        >>> _extract_external_id("https://migusto.migros.ch/de/rezepte/pasta-carbonara.html", "de")
        'pasta-carbonara-de'
        >>> _extract_external_id("https://example.com/recipe/BB_ABRE120801-40-fr", "fr")
        'BB_ABRE120801-40-fr'
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

    # Append language suffix if not already present
    if language and not slug.endswith(f"-{language}"):
        slug = f"{slug}-{language}"

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


# ---------------------------------------------------------------------------
# Keyword → tag mapping
# ---------------------------------------------------------------------------

_KEYWORD_FACET_MAP: dict[str, str] = {
    # ingredient facet — food categories from source keywords
    "gemüse": "ingredient",
    "salat": "ingredient",
    "fleisch": "ingredient",
    "geflügel": "ingredient",
    "fisch": "ingredient",
    "früchte": "ingredient",
    "milchprodukte": "ingredient",
    "käse": "ingredient",
    "eier": "ingredient",
    "kartoffeln": "ingredient",
    "getreide": "ingredient",
    "teigwaren": "ingredient",
    "reis": "ingredient",
    "hülsenfrüchte": "ingredient",
    # occasion facet — events and timing
    "für gäste": "occasion",
    "party": "occasion",
    "weihnachten": "occasion",
    "silvester": "occasion",
    "ostern": "occasion",
    "muttertag": "occasion",
    "fussball em & wm": "occasion",
    "brunch & frühstück": "occasion",
    # audience facet — who the recipe is for
    "familien-gerichte": "audience",
    "für unterwegs": "audience",
    "kochen & backen mit kindern": "audience",
}


def _slugify_tag(tag: str) -> str:
    """Normalise a tag string to a lowercase slug (letters, digits, hyphens).

    Examples:
        >>> _slugify_tag("Für Gäste")
        'für-gäste'
        >>> _slugify_tag("Brunch & Frühstück")
        'brunch-frühstück'
    """
    slug = tag.strip().lower()
    slug = re.sub(r"[^a-z0-9äöüéèà-]+", "-", slug)
    return slug.strip("-")


def build_tag_rows_from_keywords(
    keywords_by_recipe: list[tuple[int, list[str]]],
    existing_tags: dict[str, int] | None = None,
    next_tag_id: int = 1,
) -> tuple[list[dict], list[dict]]:
    """Map original_keywords to tags and recipe_tags rows.

    Builds normalised tag entries from source keywords and assigns them to
    recipes via a junction table. Each unique keyword becomes one tag row
    (deduplicated by slug key). Tags are assigned facets based on the
    keyword-to-facet mapping.

    Args:
        keywords_by_recipe: List of (recipe_id, keywords) tuples.
        existing_tags: Dict of tag key → tag id already present (to avoid
            duplicates and resolve IDs for existing tags).
        next_tag_id: Starting ID for new tags.

    Returns:
        Tuple of (tag_rows, recipe_tag_rows).

    Examples:
        >>> tags, rt = build_tag_rows_from_keywords([(1, ["Gemüse", "Party"])])
        >>> len(tags)
        2
        >>> tags[0]["facet"]
        'ingredient'
        >>> tags[1]["facet"]
        'occasion'
    """
    existing = existing_tags or {}
    tag_id = next_tag_id

    # key → tag row (deduplicated across all recipes in this batch)
    tag_map: dict[str, dict] = {}
    recipe_tag_rows: list[dict] = []

    for recipe_id, keywords in keywords_by_recipe:
        if not keywords:
            continue
        for kw in keywords:
            key = _slugify_tag(kw)
            if not key:
                continue

            # Create tag if not already known
            if key not in tag_map and key not in existing:
                facet = _KEYWORD_FACET_MAP.get(kw.strip().lower(), "free")
                tag_map[key] = {
                    "id": tag_id,
                    "key": key,
                    "display": kw.strip(),
                    "facet": facet,
                }
                tag_id += 1

            # Build recipe_tag link
            if key in tag_map:
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": tag_map[key]["id"]})
            elif key in existing:
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": existing[key]})

    tag_rows = list(tag_map.values())
    return tag_rows, recipe_tag_rows
