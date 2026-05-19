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
import logging
import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlparse

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

logger = logging.getLogger(__name__)

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


# German-language cuisine synonyms mapped to canonical English values.
# Used as a shared fallback in _normalise_cuisine so any source returning
# raw German text gets normalised consistently.
_GERMAN_CUISINE_SYNONYMS: dict[str, str] = {
    "schweizer küche": "swiss",
    "schweizer": "swiss",
    "asiatische küche": "asian",
    "asiatisch": "asian",
    "mediterrane küche": "mediterranean",
    "mediterran": "mediterranean",
    "italienische küche": "italian",
    "italienisch": "italian",
    "indisch": "indian",
    "spanisch": "spanish",
    "französisch": "french",
    "japanisch": "japanese",
    "chinesisch": "chinese",
    "griechisch": "greek",
    "koreanisch": "korean",
    "vietnamesisch": "vietnamese",
    "mexikanisch": "mexican",
    "orientalisch": "middle-eastern",
    "russisch": "russian",
    "ungarisch": "hungarian",
    "lateinamerikanisch": "latin",
    "südamerikanisch": "latin",
}

# Non-cuisine keywords that sources may incorrectly return as cuisine values.
_CUISINE_BLOCKLIST: frozenset[str] = frozenset(
    {
        "root",
        "schnelle küche",
        "familienküche",
        "raclette",
        "zmittag",
        "znacht",
        "zmorge",
        "backen",
        "grillieren",
        "apéro",
        "dessert",
        "vorspeise",
        "hauptgericht",
    }
)


def _normalise_cuisine(raw: str) -> str | None:
    """Normalise a cuisine string to lowercase, rejecting category tag dumps.

    Returns None for empty strings, values that look like concatenated
    category tags (contain commas), or values in the blocklist (non-cuisine
    keywords). Maps known German synonyms to canonical English values.

    Examples:
        >>> _normalise_cuisine("Swiss")
        'swiss'
        >>> _normalise_cuisine("Italian")
        'italian'
        >>> _normalise_cuisine("schweizer küche")
        'swiss'
        >>> _normalise_cuisine("asiatische küche")
        'asian'
        >>> _normalise_cuisine("Schnelle Küche")
        >>> _normalise_cuisine("")
        >>> _normalise_cuisine("milchprodukte, käse, eier")
    """
    if not raw:
        return None
    stripped = raw.strip().lower()
    # Reject multi-value category dumps (real cuisine is a single term)
    if "," in stripped:
        return None
    # Reject non-cuisine keywords
    if stripped in _CUISINE_BLOCKLIST:
        return None
    # Map German synonyms to canonical English
    mapped = _GERMAN_CUISINE_SYNONYMS.get(stripped)
    if mapped:
        return mapped
    return stripped


# Title/keyword patterns → cuisine.  Checked in order; first match wins.
# Each entry: (compiled regex, cuisine value).
_CUISINE_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    # Swiss / Alpine
    (
        re.compile(
            r"r[öo]sti|fondue|raclette|bircher|z[üu]ri|berner|[äa]lpler"
            r"|zopf|älplermagronen|capuns|cholera|pizokel"
            r"|bündner|appenzeller|emmentaler|gruyère|vacherin"
            r"|geschnetzeltes|züpfe|weggen|basler|luzerner",
            re.IGNORECASE,
        ),
        "swiss",
    ),
    # Italian
    (
        re.compile(
            r"pasta|spaghetti|risotto|pizza|tiramisu|panna\s*cotta|carbonara"
            r"|bolognese|lasagne|gnocchi|tortellini|bruschetta|focaccia"
            r"|minestrone|ossobuco|parmigiana|saltimbocca|vitello\s*tonnato"
            r"|ciabatta|polenta|antipast[io]|arancin[ie]|calzone"
            r"|pesto|mascarpone|amaretti|panettone|prosciutto|pancetta"
            r"|tagliatelle|penne|rigatoni|ravioli|agnolotti|cannelloni"
            r"|arrabiata|arrabbiata|aglio\s*e?\s*olio|cacio\s*e\s*pepe"
            r"|tagliata|carpaccio|bresaola|caprese|tramezzini",
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
            r"|gyoza|udon|soba|onigiri|okonomiyaki|yakitori"
            r"|edamame|wasabi|ponzu|dashi",
            re.IGNORECASE,
        ),
        "japanese",
    ),
    # Chinese
    (
        re.compile(
            r"wonton|dim\s*sum|kung\s*pao|sweet\s*(?:and|&)\s*sour"
            r"|chow\s*mein|fried\s*rice|pek?ing|szechuan|mapo\s*tofu"
            r"|chinesisch|wan\s*tan",
            re.IGNORECASE,
        ),
        "chinese",
    ),
    # Korean
    (
        re.compile(
            r"kimchi|bibimbap|bulgogi|korean|japchae|tteokbokki"
            r"|koreanisch|gochujang",
            re.IGNORECASE,
        ),
        "korean",
    ),
    # Vietnamese
    (
        re.compile(
            r"\bpho\b|b[áa]nh\s*m[ìi]|vietnamese|summer\s*roll[s]?"
            r"|vietnamesisch",
            re.IGNORECASE,
        ),
        "vietnamese",
    ),
    # Generic Asian (catch-all after specific Asian cuisines)
    (
        re.compile(
            r"\bwok\b|stir[\s-]*fry|asia(?:tisch)?|nasi\s*goreng"
            r"|satay|sat[ée]\b|curry(?!wurst)"
            r"|glasnudeln|reisnudeln|fr[üu]hlingsroll",
            re.IGNORECASE,
        ),
        "asian",
    ),
    # Indian
    (
        re.compile(
            r"\bindisch\b|tandoori|naan\b|chapati|dhal|dal\b"
            r"|masala|tikka|samosa|biryani|paneer|vindaloo|korma"
            r"|pakora|chutney|raita|lassi",
            re.IGNORECASE,
        ),
        "indian",
    ),
    # Mexican
    (
        re.compile(
            r"\btaco[s]?\b|burrito|quesadilla|enchilada|fajita"
            r"|guacamole|mexikan|nacho[s]?\b|chili\s*con\s*carne"
            r"|tortilla(?!\s*chip)|jalape[ñn]o",
            re.IGNORECASE,
        ),
        "mexican",
    ),
    # French
    (
        re.compile(
            r"quiche|cr[êe]pe[s]?\b|ratatouille|bouillabaisse"
            r"|cr[oô]quer?|flambée?|béchamel|proven[çc]al"
            r"|coq\s*au\s*vin|blanquette|boeuf\s*bourguignon"
            r"|tarte\s*tatin|clafoutis|madeleines|brioche|croissant"
            r"|gratin\s*dauphinois|confit|cassoulet|ni[çc]oise",
            re.IGNORECASE,
        ),
        "french",
    ),
    # Greek
    (
        re.compile(
            r"tzatziki|gyros|moussaka|souvlaki|griechisch"
            r"|halloumi|feta(?:\s*salat|\s*k[äa]se)",
            re.IGNORECASE,
        ),
        "greek",
    ),
    # Middle Eastern
    (
        re.compile(
            r"falafel|hummus|taboul[ée]|shawarma|kebab|lahmacun"
            r"|orientalisch|couscous|harissa|baharat|za.atar"
            r"|fattoush|meze|börek|kibbeh",
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
    # Russian / Eastern European
    (
        re.compile(
            r"stroganoff|borschtsch|blini|pelmeni|pirog",
            re.IGNORECASE,
        ),
        "russian",
    ),
    # Hungarian
    (
        re.compile(
            r"gulasch|goulash|gul[áa]s|langos|lángos",
            re.IGNORECASE,
        ),
        "hungarian",
    ),
    # Latin American / South American
    (
        re.compile(
            r"s[üu]damerika|lateinamerika|ceviche|empanada|chimichurri",
            re.IGNORECASE,
        ),
        "latin",
    ),
]


# ---------------------------------------------------------------------------
# URL-based cuisine signals — match slug segments in source URLs.
# Checked only when title/keyword scan yields no result.
# ---------------------------------------------------------------------------

_CUISINE_URL_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"schweiz|swiss|suisse", re.IGNORECASE), "swiss"),
    (re.compile(r"italien|italian|pasta|risotto|pizza", re.IGNORECASE), "italian"),
    (re.compile(r"\bthai\b", re.IGNORECASE), "thai"),
    (re.compile(r"japan|nippon|sushi|ramen", re.IGNORECASE), "japanese"),
    (re.compile(r"chines|china", re.IGNORECASE), "chinese"),
    (re.compile(r"korea", re.IGNORECASE), "korean"),
    (re.compile(r"vietnam", re.IGNORECASE), "vietnamese"),
    (re.compile(r"asia", re.IGNORECASE), "asian"),
    (re.compile(r"indisch|indian|indien", re.IGNORECASE), "indian"),
    (re.compile(r"mexik|mexican|mexic", re.IGNORECASE), "mexican"),
    (re.compile(r"franz[öo]s|french|fran[çc]ais", re.IGNORECASE), "french"),
    (re.compile(r"griech|greek|grec", re.IGNORECASE), "greek"),
    (re.compile(r"orient|nahostlich|middle.east", re.IGNORECASE), "middle-eastern"),
    (re.compile(r"mediterran", re.IGNORECASE), "mediterranean"),
    (re.compile(r"amerikan|american", re.IGNORECASE), "american"),
]


# ---------------------------------------------------------------------------
# Ingredient-combination cuisine signals.
# Each entry: (set of keywords to match in raw_text, minimum required matches, cuisine)
# These are checked against the collection of ingredient raw_text lines.
# ---------------------------------------------------------------------------

_CUISINE_INGREDIENT_COMBOS: list[tuple[list[str], int, str]] = [
    # Asian (need at least 2 of these)
    (
        [
            "sojasauce",
            "sojasosse",
            "soja-sauce",
            "soja sauce",
            "ingwer",
            "sesam",
            "sesamöl",
            "reisessig",
            "reiswein",
            "kokosmilch",
            "kokoscreme",
            "fischsauce",
            "fischsosse",
            "zitronengras",
            "koriander frisch",
            "limetten",
            "sriracha",
            "sambal",
            "mirin",
            "sake",
        ],
        2,
        "asian",
    ),
    # Italian (need at least 2 of these)
    (
        [
            "mozzarella",
            "parmesan",
            "parmigiano",
            "pecorino",
            "ricotta",
            "basilikum",
            "oregano",
            "mascarpone",
            "pancetta",
            "prosciutto",
            "passata",
            "pelati",
            "san marzano",
        ],
        2,
        "italian",
    ),
    # Indian (need at least 2 of these)
    (
        [
            "kurkuma",
            "kreuzkümmel",
            "garam masala",
            "koriander gemahlen",
            "currypulver",
            "curry-pulver",
            "kardamom",
            "ghee",
            "joghurt nature",
            "kokosmilch",
            "linsen",
        ],
        2,
        "indian",
    ),
    # Middle Eastern (need at least 2 of these)
    (
        [
            "kichererbsen",
            "tahini",
            "tahina",
            "granatapfel",
            "sumach",
            "za'atar",
            "zaatar",
            "minze",
            "bulgur",
            "couscous",
            "harissa",
            "kreuzkümmel",
        ],
        2,
        "middle-eastern",
    ),
    # Mexican (need at least 2 of these)
    (
        [
            "kidneybohnen",
            "schwarze bohnen",
            "jalapeño",
            "jalapeno",
            "mais",
            "avocado",
            "limetten",
            "koriander frisch",
            "tortilla",
            "salsa",
            "chipotle",
        ],
        2,
        "mexican",
    ),
]


def _infer_cuisine_from_url(source_url: str) -> str | None:
    """Extract cuisine hint from URL path slug.

    Many Swiss recipe sites embed cuisine keywords in the URL slug
    (e.g. /rezepte/rezept/thai-curry-99998/).

    Examples:
        >>> _infer_cuisine_from_url("https://www.bettybossi.ch/de/rezepte/rezept/thai-curry-99998/")
        'thai'
        >>> _infer_cuisine_from_url("https://fooby.ch/de/rezepte/asiatische-gemuesepfanne-123")
        'asian'
        >>> _infer_cuisine_from_url("https://www.bettybossi.ch/de/rezepte/rezept/kartoffelgratin-10002010/")
    """
    if not source_url:
        return None
    # Extract the last meaningful path segment (the slug)
    path = urlparse(source_url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if "/" in path else path
    # Replace hyphens with spaces for better matching
    slug_text = slug.replace("-", " ")

    for pattern, cuisine in _CUISINE_URL_SIGNALS:
        if pattern.search(slug_text):
            return cuisine
    return None


def _infer_cuisine_from_ingredients(ingredient_rows: list[dict]) -> str | None:
    """Infer cuisine from ingredient combination patterns.

    Checks ingredient raw_text lines against known cuisine-specific ingredient
    combinations. Requires multiple matching ingredients to reduce false positives.

    Examples:
        >>> _infer_cuisine_from_ingredients([
        ...     {"raw_text": "2 EL Sojasauce"},
        ...     {"raw_text": "1 Stück Ingwer"},
        ...     {"raw_text": "1 EL Sesamöl"},
        ... ])
        'asian'
        >>> _infer_cuisine_from_ingredients([{"raw_text": "200 g Butter"}])
    """
    if not ingredient_rows:
        return None

    # Build a single lowercased text from all ingredient raw_text
    all_text = " ".join(row.get("raw_text", "").lower() for row in ingredient_rows)

    for keywords, min_matches, cuisine in _CUISINE_INGREDIENT_COMBOS:
        matches = sum(1 for kw in keywords if kw in all_text)
        if matches >= min_matches:
            return cuisine

    return None


def _infer_cuisine(
    raw_cuisine: str,
    title: str,
    keywords: list[str],
    *,
    source_url: str = "",
    ingredient_rows: list[dict] | None = None,
) -> str | None:
    """Resolve cuisine from explicit value or infer via layered heuristics.

    Inference priority:
    1. Explicit raw_cuisine value (if valid)
    2. Title text pattern matching
    3. Keywords pattern matching
    4. Source URL slug pattern matching
    5. Ingredient combination matching

    Examples:
        >>> _infer_cuisine("Swiss", "Anything", [])
        'swiss'
        >>> _infer_cuisine("", "Spaghetti Carbonara", [])
        'italian'
        >>> _infer_cuisine("", "Pad Thai mit Poulet", [])
        'thai'
        >>> _infer_cuisine("", "Gemüseauflauf", [])
        >>> _infer_cuisine("", "Gemüsepfanne", [], source_url="https://example.ch/rezepte/asiatisch-gemuese-123/")
        'asian'
    """
    explicit = _normalise_cuisine(raw_cuisine)
    if explicit:
        return explicit

    # Layer 1: Scan title (strongest signal)
    for pattern, cuisine in _CUISINE_SIGNALS:
        if pattern.search(title):
            return cuisine

    # Layer 1: Scan keywords
    joined_keywords = " ".join(keywords)
    for pattern, cuisine in _CUISINE_SIGNALS:
        if pattern.search(joined_keywords):
            return cuisine

    # Layer 3: URL slug mining
    url_cuisine = _infer_cuisine_from_url(source_url)
    if url_cuisine:
        return url_cuisine

    # Layer 2: Ingredient-based inference
    if ingredient_rows:
        ing_cuisine = _infer_cuisine_from_ingredients(ingredient_rows)
        if ing_cuisine:
            return ing_cuisine

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
            "source_url": data.source_url,
        }
    category = data.get("recipeCategory") or data.get("category", "")
    cuisine_raw = data.get("recipeCuisine") or data.get("cuisine", "")
    difficulty_raw = data.get("difficulty", "")
    keywords = data.get("keywords") or []
    total_minutes = data.get("total_minutes")
    title = data.get("title", "")
    source_url = data.get("source_url", "")

    course = _infer_course(category, title, keywords)
    cuisine = _infer_cuisine(cuisine_raw, title, keywords, source_url=source_url)
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

    # Detect source duplication: when prep == cook, the source duplicated a
    # single duration into both fields (common pattern on Betty Bossi and
    # similar sites). The duplicated value represents active/prep time.
    # When totalTime is available and exceeds prep, derive passive cook time.
    total = None
    if prep is not None and cook is not None and prep == cook:
        if raw_total is not None and raw_total > prep:
            # Derive passive cook time from total minus active prep.
            cook = raw_total - prep
            total = raw_total
        elif raw_total is not None:
            # Total <= active time — no meaningful passive cook time.
            cook = None
            total = raw_total
        else:
            # No total available; use duplicated value as total.
            cook = None
            total = prep
    elif prep is not None and cook is not None:
        total = prep + cook
    elif prep is not None:
        # Only prep available — use totalTime if present (e.g. Fooby provides
        # prepTime=Aktiv and totalTime=Gesamt but omits cookTime).
        if raw_total is not None and raw_total > prep:
            cook = raw_total - prep
            total = raw_total
        elif raw_total is not None:
            # totalTime present but not larger than prep — no passive cook time.
            total = raw_total
        else:
            total = prep
    elif cook is not None:
        total = cook
    elif raw_total is not None:
        total = raw_total

    # Belt-and-suspenders: clamp any value exceeding int16 max to None.
    prep = _clamp_int16(prep)
    cook = _clamp_int16(cook)
    total = _clamp_int16(total)

    now = datetime.now(UTC)

    keywords = raw.keywords or []
    course = _infer_course(raw.category, raw.title, keywords)
    cuisine = _infer_cuisine(
        raw.cuisine,
        raw.title,
        keywords,
        source_url=raw.source_url,
        ingredient_rows=ingredient_rows,
    )
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

_TIME_TEXT_HOURS_RE = re.compile(
    r"(\d+)\s*(?:h|Std|Stunden?)\.?",
    re.IGNORECASE,
)
_TIME_TEXT_MINUTES_RE = re.compile(
    r"(\d+)\s*(?:min|Min|Minuten?)\.?",
    re.IGNORECASE,
)

_MAX_RECIPE_MINUTES = 10_080  # 7 days — generous upper bound

_INT16_MAX = 32_767


def _clamp_int16(value: int | None) -> int | None:
    """Return None if value exceeds int16 max, otherwise pass through."""
    if value is not None and value > _INT16_MAX:
        return None
    return value


def _parse_iso_duration(iso: str) -> int | None:
    """Parse an ISO 8601 duration string into total minutes.

    Falls back to German plain-text time formats (e.g. "45 min", "1 h 30 min")
    when the ISO regex does not match.

    Examples:
        >>> _parse_iso_duration("PT15M")
        15
        >>> _parse_iso_duration("PT1H30M")
        90
        >>> _parse_iso_duration("PT2H")
        120
        >>> _parse_iso_duration("45 min")
        45
        >>> _parse_iso_duration("1 h 35 min")
        95
        >>> _parse_iso_duration("2 Std 10 min")
        130
        >>> _parse_iso_duration("")
    """
    if not iso or not iso.strip():
        return None

    match = _ISO_DURATION_RE.match(iso.strip())
    if not match:
        return _parse_time_text(iso)

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    total = hours * 60 + minutes + (1 if seconds >= 30 else 0)
    if total > _MAX_RECIPE_MINUTES:
        logger.warning("Duration %s exceeds cap (%d min), treating as invalid", iso, total)
        return None
    return total if total > 0 else None


def _parse_time_text(text: str) -> int | None:
    """Parse German plain-text time into minutes.

    Handles formats produced by HTML-based adapters (Schweizer Fleisch,
    Swissmilk) that return human-readable strings instead of ISO 8601.

    Examples:
        >>> _parse_time_text("45 min")
        45
        >>> _parse_time_text("1 h 35 min")
        95
        >>> _parse_time_text("2 Std 10 min")
        130
        >>> _parse_time_text("2 h")
        120
        >>> _parse_time_text("ca. 30 Min.")
        30
        >>> _parse_time_text("")
    """
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    h_match = _TIME_TEXT_HOURS_RE.search(cleaned)
    m_match = _TIME_TEXT_MINUTES_RE.search(cleaned)
    if not h_match and not m_match:
        return None
    hours = int(h_match.group(1)) if h_match else 0
    minutes = int(m_match.group(1)) if m_match else 0
    total = hours * 60 + minutes
    if total <= 0 or total > _MAX_RECIPE_MINUTES:
        return None
    return total


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
    "suppen": "ingredient",
    "saucen & dips": "ingredient",
    "pilze": "ingredient",
    "nüsse": "ingredient",
    # occasion facet — events and timing
    "für gäste": "occasion",
    "party": "occasion",
    "weihnachten": "occasion",
    "silvester": "occasion",
    "ostern": "occasion",
    "muttertag": "occasion",
    "fussball em & wm": "occasion",
    "brunch & frühstück": "occasion",
    "apéro": "occasion",
    "valentinstag": "occasion",
    # audience facet — who the recipe is for
    "familien-gerichte": "audience",
    "für unterwegs": "audience",
    "kochen & backen mit kindern": "audience",
    # dietary facet — dietary properties
    "vegetarisch": "dietary",
    "vegan": "dietary",
    "glutenfrei": "dietary",
    "laktosefrei": "dietary",
    # method facet — cooking methods
    "grillieren": "method",
    "backen": "method",
    "dämpfen": "method",
    "schmoren": "method",
    # difficulty facet — effort level
    "schnell & einfach": "difficulty",
    # course facet — meal type
    "dessert": "course",
    "vorspeise": "course",
    "hauptgericht": "course",
    "beilage": "course",
    "getränke": "course",
}

# Maps German keyword slugs to their canonical English tag key so that
# keywords like "Hauptgericht" merge with the classification-derived "main"
# tag rather than creating a parallel German entry.
_KEYWORD_TO_CANONICAL_TAG: dict[str, str] = {
    # course
    "hauptgericht": "main",
    "vorspeise": "starter",
    "beilage": "side",
    "dessert": "dessert",
    "getränke": "drink",
    "frühstück": "breakfast",
    # dietary
    "vegetarisch": "vegetarian",
    "vegan": "vegan",
    "glutenfrei": "gluten-free",
    "laktosefrei": "dairy-free",
    # method
    "grillieren": "grilled",
    "backen": "baked",
    "dämpfen": "steamed",
    "schmoren": "braised",
}

# Keywords that produce noise tags with no useful canonical equivalent.
# These are suppressed entirely rather than stored as free-form tags.
_TAG_KEYWORD_BLOCKLIST: frozenset[str] = frozenset(
    {
        "sommer",
        "winter",
        "frühling",
        "herbst",
        "zmittag",
        "znacht",
        "zmorge",
        "schnelle-küche",
        "familienküche",
        "guetzli-weihnachten",
        "backen-süss",
    }
)


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

    German keywords that have a canonical English equivalent (e.g.
    ``"Hauptgericht"`` → ``"main"``) are merged into the canonical tag
    rather than creating a parallel entry.  Keywords in the blocklist are
    suppressed entirely.

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

            # Block noise keywords
            if key in _TAG_KEYWORD_BLOCKLIST:
                continue

            # Resolve to canonical English key if available
            canonical_key = _KEYWORD_TO_CANONICAL_TAG.get(key)
            resolved_key = canonical_key if canonical_key else key

            # Create tag if not already known
            if resolved_key not in tag_map and resolved_key not in existing:
                facet = _KEYWORD_FACET_MAP.get(kw.strip().lower(), "free")
                tag_map[resolved_key] = {
                    "id": tag_id,
                    "key": resolved_key,
                    "display": canonical_key if canonical_key else kw.strip(),
                    "facet": facet,
                }
                tag_id += 1

            # Build recipe_tag link
            if resolved_key in tag_map:
                link_id = tag_map[resolved_key]["id"]
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": link_id})
            elif resolved_key in existing:
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": existing[resolved_key]})

    tag_rows = list(tag_map.values())
    return tag_rows, recipe_tag_rows


def build_tag_rows_from_classification(
    recipe_rows: list[dict],
    existing_tags: dict[str, int] | None = None,
    next_tag_id: int = 1,
) -> tuple[list[dict], list[dict]]:
    """Derive tag rows from computed classification fields on recipe rows.

    Guarantees every recipe gets at least one tag by creating tags from
    the already-computed fields: dietary_flags, course, difficulty, and
    cooking_method. This eliminates untagged recipes whose
    original_keywords happen to be empty.

    Args:
        recipe_rows: List of recipe row dicts (output of build_recipe_row).
        existing_tags: Dict of tag key → tag id already present.
        next_tag_id: Starting ID for new tags.

    Returns:
        Tuple of (tag_rows, recipe_tag_rows).

    Examples:
        >>> rows = [{"id": 1, "dietary_flags": ["vegetarian", "quick"],
        ...          "course": "main", "difficulty": "easy",
        ...          "cooking_method": "braten"}]
        >>> tags, rt = build_tag_rows_from_classification(rows)
        >>> len(tags) >= 4
        True
    """
    existing = existing_tags or {}
    tag_id = next_tag_id

    tag_map: dict[str, dict] = {}
    recipe_tag_rows: list[dict] = []

    for row in recipe_rows:
        recipe_id = row["id"]
        derived: list[tuple[str, str]] = []  # (display, facet)

        # Dietary flags → dietary facet
        for flag in row.get("dietary_flags") or []:
            derived.append((flag, "dietary"))

        # Course → course facet
        course = row.get("course")
        if course:
            derived.append((course, "course"))

        # Difficulty → difficulty facet
        difficulty = row.get("difficulty")
        if difficulty:
            derived.append((difficulty, "difficulty"))

        # Cooking method → method facet
        method = row.get("cooking_method")
        if method:
            derived.append((method, "method"))

        for display, facet in derived:
            key = _slugify_tag(display)
            if not key:
                continue

            if key not in tag_map and key not in existing:
                tag_map[key] = {
                    "id": tag_id,
                    "key": key,
                    "display": display,
                    "facet": facet,
                }
                tag_id += 1

            if key in tag_map:
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": tag_map[key]["id"]})
            elif key in existing:
                recipe_tag_rows.append({"recipe_id": recipe_id, "tag_id": existing[key]})

    tag_rows = list(tag_map.values())
    return tag_rows, recipe_tag_rows
