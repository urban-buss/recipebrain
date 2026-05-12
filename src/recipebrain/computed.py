"""Computed recipe properties derived from resolved ingredients and step text.

Each function takes recipe data (ingredients, steps, timing, course) and returns
a classification value. Called by transform.build_recipe_row() at insert/update time.

Examples:
    >>> compute_primary_protein([{"ingredient_id": 1, "quantity": 200}])
    'poultry'
    >>> compute_taste_profile("dessert", [], [])
    'sweet'
    >>> compute_weight_class("starter", None, [], [])
    'light'
"""

from __future__ import annotations

from recipebrain.normalise.ingredients import (
    CanonicalIngredient,
    get_canonical_ingredient_by_id,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUB_TO_PROTEIN: dict[str, str] = {
    "beef": "beef",
    "veal": "veal",
    "pork": "pork",
    "lamb": "lamb",
    "poultry": "poultry",
    "game": "game",
    "sausage": "sausage",
    "cured": "pork",
    "oily-fish": "fish",
    "white-fish": "fish",
    "freshwater": "fish",
    "shellfish": "seafood",
    "cephalopod": "seafood",
    "smoked": "fish",
}

_CHEESE_SUBS: frozenset[str] = frozenset(
    {
        "cheese-hard",
        "cheese-fresh",
        "cheese-soft",
        "cheese-brined",
        "cheese-blue",
    }
)

_SWEET_KEYWORDS: frozenset[str] = frozenset(
    {
        "süss",
        "dessert",
        "kuchen",
        "torte",
        "gebäck",
        "sweet",
        "cake",
        "guetzli",
        "cookies",
        "praline",
        "konfekt",
        "glacé",
        "glace",
    }
)

_HEAVY_KEYWORDS: frozenset[str] = frozenset(
    {
        "deftig",
        "eintopf",
        "braten",
        "gratin",
        "auflauf",
        "schmorbraten",
        "ragout",
        "gulasch",
        "cassoulet",
        "ossobuco",
        "bourguignon",
    }
)

_LIGHT_KEYWORDS: frozenset[str] = frozenset(
    {
        "salat",
        "leicht",
        "frisch",
        "light",
        "salade",
        "carpaccio",
        "ceviche",
    }
)

_METHOD_PATTERNS: dict[str, list[str]] = {
    "grilled": ["grill", "grillier", "bbq", "barbecue"],
    "baked": ["backen", "ofen", "überback", "au four", "gratinieren"],
    "fried": ["braten", "anbrat", "frittier", "pfanne", "poêl", "sautier"],
    "braised": ["schmor", "köchel", "mijoter", "brais"],
    "steamed": ["dämpf", "dampfgar", "steam", "vapeur"],
    "boiled": ["kochen", "sied", "blanch", "bouillir"],
    "roasted": ["röst", "roast", "rôtir"],
    "raw": ["roh", "raw", "tartare", "cru"],
}

_SWEET_INGREDIENT_KEYS: frozenset[str] = frozenset(
    {
        "sugar",
        "chocolate",
        "honey",
        "maple-syrup",
        "powdered-sugar",
        "vanilla-sugar",
        "brown-sugar",
        "cocoa",
    }
)

CELLARBRAIN_FOOD_GROUP_VOCAB: frozenset[str] = frozenset(
    {
        "red_meat",
        "poultry",
        "fish",
        "seafood",
        "pork",
        "game",
        "vegetarian",
        "vegan",
        "cheese",
        "grilled",
        "braised",
        "stewed",
        "fried",
        "roasted",
        "smoked",
        "raw",
        "sautéed",
        "baked",
        "cured",
        "light",
        "medium",
        "heavy",
        "French",
        "Italian",
        "Swiss",
        "Indian",
        "Spanish",
        "Japanese",
        "Chinese",
        "American",
        "Mexican",
        "German",
        "Middle_Eastern",
        "Korean",
        "Thai",
        "Greek",
        "Vietnamese",
        "Austrian",
        "savory",
        "rich",
        "spicy",
        "creamy",
        "smoky",
        "earthy",
        "herbal",
        "tangy",
        "sweet",
        "umami",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_ingredients(
    ingredient_rows: list[dict],
) -> list[tuple[dict, CanonicalIngredient]]:
    """Return (row, catalogue_entry) pairs for resolved ingredients."""
    result: list[tuple[dict, CanonicalIngredient]] = []
    for row in ingredient_rows:
        iid = row.get("ingredient_id")
        if iid is None:
            continue
        entry = get_canonical_ingredient_by_id(iid)
        if entry is not None:
            result.append((row, entry))
    return result


def _has_keyword_match(keywords: list[str], target_set: frozenset[str]) -> bool:
    """Check if any keyword (lowercased) appears in the target set."""
    return any(kw.lower() in target_set for kw in keywords)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_primary_protein(ingredient_rows: list[dict]) -> str | None:
    """Classify the dominant protein in a recipe.

    Returns one of: beef, veal, pork, lamb, poultry, game, fish, seafood,
    cheese, sausage, vegetarian, vegan, mixed, or None (no resolved ingredients).

    Examples:
        >>> compute_primary_protein([{"ingredient_id": 1, "quantity": 200}])
        'poultry'
        >>> compute_primary_protein([{"ingredient_id": None}])
    """
    resolved = _resolve_ingredients(ingredient_rows)
    if not resolved:
        return None

    meats = [(r, e) for r, e in resolved if e.category == "meat"]
    fishes = [(r, e) for r, e in resolved if e.category == "fish"]

    if not meats and not fishes:
        # Check for cheese-dominant recipes
        cheese_items = [
            (r, e) for r, e in resolved if e.category == "dairy" and e.sub_category in _CHEESE_SUBS
        ]
        if cheese_items:
            return "cheese"

        dairy = [(r, e) for r, e in resolved if e.category == "dairy"]
        if not dairy:
            return "vegan"
        return "vegetarian"

    proteins = meats + fishes
    subs: set[str] = set()
    for _row, entry in proteins:
        if entry.sub_category:
            mapped = _SUB_TO_PROTEIN.get(entry.sub_category)
            if mapped:
                subs.add(mapped)

    if not subs:
        return None

    if len(subs) == 1:
        return subs.pop()

    # Multiple protein types — try weight-based ranking
    protein_weights: dict[str, float] = {}
    for row, entry in proteins:
        mapped = _SUB_TO_PROTEIN.get(entry.sub_category or "")
        if not mapped:
            continue
        qty = row.get("quantity") or 0.0
        protein_weights[mapped] = protein_weights.get(mapped, 0.0) + qty

    if protein_weights:
        ranked = sorted(protein_weights.items(), key=lambda x: x[1], reverse=True)
        if len(ranked) >= 2 and ranked[0][1] > 2 * ranked[1][1]:
            return ranked[0][0]

    return "mixed"


def compute_taste_profile(
    course: str | None,
    ingredient_rows: list[dict],
    keywords: list[str],
) -> str:
    """Classify a recipe as sweet, savoury, or sweet-savoury.

    Examples:
        >>> compute_taste_profile("dessert", [], [])
        'sweet'
        >>> compute_taste_profile("main", [], [])
        'savoury'
    """
    if course in ("dessert", "bake"):
        return "sweet"

    if _has_keyword_match(keywords, _SWEET_KEYWORDS):
        resolved = _resolve_ingredients(ingredient_rows)
        has_savoury = any(e.category in ("meat", "fish", "vegetable") for _r, e in resolved)
        if has_savoury:
            return "sweet-savoury"
        return "sweet"

    # Check if sweet ingredients dominate
    resolved = _resolve_ingredients(ingredient_rows)
    if resolved:
        sweet_count = sum(1 for _r, e in resolved if e.key in _SWEET_INGREDIENT_KEYS)
        if sweet_count > 0 and sweet_count >= len(resolved) * 0.3:
            return "sweet"

    return "savoury"


def compute_weight_class(
    course: str | None,
    cook_minutes: int | None,
    ingredient_rows: list[dict],
    keywords: list[str],
    primary_protein: str | None = None,
) -> str:
    """Classify a recipe as light, medium, or heavy.

    Examples:
        >>> compute_weight_class("starter", None, [], [])
        'light'
        >>> compute_weight_class("main", 90, [], [], "beef")
        'heavy'
    """
    if course in ("starter", "side"):
        return "light"

    heavy_signals = 0
    if cook_minutes is not None and cook_minutes > 60:
        heavy_signals += 1
    if primary_protein in ("beef", "lamb", "pork", "game"):
        heavy_signals += 1

    # Check for heavy dairy (cream, cheese)
    resolved = _resolve_ingredients(ingredient_rows)
    heavy_dairy = any(
        e.category == "dairy" and e.sub_category in (_CHEESE_SUBS | {"cream", "butter"})
        for _r, e in resolved
    )
    if heavy_dairy:
        heavy_signals += 1

    if _has_keyword_match(keywords, _HEAVY_KEYWORDS):
        heavy_signals += 1

    if heavy_signals >= 2:
        return "heavy"

    light_signals = 0
    if primary_protein is None or primary_protein in ("vegan", "vegetarian"):
        light_signals += 1
    if cook_minutes is not None and cook_minutes <= 20:
        light_signals += 1
    if _has_keyword_match(keywords, _LIGHT_KEYWORDS):
        light_signals += 1

    if light_signals >= 2:
        return "light"

    return "medium"


def compute_cooking_method(steps: list[str], keywords: list[str]) -> str | None:
    """Derive the primary cooking method from step text and keywords.

    Scans step text for cooking verb patterns (German, French, English).

    Examples:
        >>> compute_cooking_method(["Fleisch grillieren"], [])
        'grilled'
        >>> compute_cooking_method(["Im Ofen 20 Min. backen"], [])
        'baked'
        >>> compute_cooking_method([], [])
    """
    text = " ".join(steps).lower() + " " + " ".join(keywords).lower()
    if not text.strip():
        return None

    matches: dict[str, int] = {}
    for method, patterns in _METHOD_PATTERNS.items():
        count = sum(1 for p in patterns if p in text)
        if count > 0:
            matches[method] = count

    if not matches:
        return None

    return max(matches, key=matches.get)  # type: ignore[arg-type]


def compute_dietary_flags(
    ingredient_rows: list[dict],
    total_minutes: int | None = None,
) -> list[str]:
    """Compute dietary classification flags for a recipe.

    Returns a sorted list of applicable flags.

    Examples:
        >>> compute_dietary_flags([], total_minutes=20)
        ['dairy-free', 'quick', 'vegan', 'vegetarian']
        >>> compute_dietary_flags([{"ingredient_id": 1}])
        []
    """
    resolved = _resolve_ingredients(ingredient_rows)
    categories = {e.category for _r, e in resolved}

    has_meat = "meat" in categories
    has_fish = "fish" in categories
    has_dairy = "dairy" in categories

    flags: list[str] = []

    if not has_meat and not has_fish:
        flags.append("vegetarian")
        if not has_dairy:
            flags.append("vegan")

    if not has_dairy:
        flags.append("dairy-free")

    if total_minutes is not None and total_minutes <= 30:
        flags.append("quick")

    return sorted(flags)


def compute_food_groups(
    ingredient_rows: list[dict],
    cooking_method: str | None,
    weight_class: str | None,
) -> list[str]:
    """Aggregate cellarbrain-compatible food group tags from ingredients.

    Collects pairing_tags from all resolved ingredients, adds cooking method
    and weight class, then filters to the cellarbrain vocabulary.

    Examples:
        >>> compute_food_groups([], "grilled", "light")
        ['grilled', 'light']
    """
    all_tags: set[str] = set()

    resolved = _resolve_ingredients(ingredient_rows)
    for _row, entry in resolved:
        all_tags.update(entry.pairing_tags)

    method_to_group: dict[str, str] = {
        "grilled": "grilled",
        "braised": "braised",
        "fried": "fried",
        "roasted": "roasted",
        "raw": "raw",
        "baked": "baked",
    }
    if cooking_method and cooking_method in method_to_group:
        all_tags.add(method_to_group[cooking_method])

    if weight_class:
        all_tags.add(weight_class)

    return sorted(all_tags & CELLARBRAIN_FOOD_GROUP_VOCAB)


def build_computed_tags(
    primary_protein: str | None,
    taste_profile: str | None,
    weight_class: str | None,
    cooking_method: str | None,
    dietary_flags: list[str],
    course: str | None,
    cuisine: str | None,
    difficulty: str | None,
) -> list[str]:
    """Build the aggregated computed_tags bag from all computed values.

    Merges all non-None scalar values and dietary flags into a single
    sorted, deduplicated list.

    Examples:
        >>> build_computed_tags("poultry", "savoury", "light", "grilled",
        ...                     ["dairy-free", "quick"], "main", "swiss", "easy")
        ['dairy-free', 'easy', 'grilled', 'light', 'main', 'poultry', 'quick', 'savoury', 'swiss']
        >>> build_computed_tags(None, None, None, None, [], None, None, None)
        []
    """
    tags: list[str] = []
    for v in (
        primary_protein,
        taste_profile,
        weight_class,
        cooking_method,
        course,
        cuisine,
        difficulty,
    ):
        if v:
            tags.append(v)
    tags.extend(dietary_flags)
    return sorted(set(tags))
