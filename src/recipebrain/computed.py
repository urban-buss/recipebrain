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

# Keywords indicating meat/fish presence in raw ingredient text.
# Used as a fallback when the catalogue cannot resolve an ingredient.
_MEAT_RAW_KEYWORDS: frozenset[str] = frozenset(
    {
        # German meat terms
        "fleisch",
        "rindfleisch",
        "schweinefleisch",
        "kalbfleisch",
        "lammfleisch",
        "wildfleisch",
        "hackfleisch",
        "gehacktes",
        "schnitzel",
        "steak",
        "filet",
        "geschnetzeltes",
        "poulet",
        "pouletbrust",
        "pouletschenkel",
        "pouletflügel",
        "hähnchen",
        "huhn",
        "hühnchen",
        "truthahn",
        "ente",
        "entenbrust",
        "gans",
        "rind",
        "rinds",
        "kalb",
        "lamm",
        "schwein",
        "schweins",
        "speck",
        "schinken",
        "salami",
        "wurst",
        "bratwurst",
        "cervelat",
        "landjäger",
        "hirsch",
        "reh",
        "wildschwein",
        "kaninchen",
        "hase",
        # Swiss-German / regional meat terms
        "siedfleisch",
        "trockenfleisch",
        "bündnerfleisch",
        "fleischkäse",
        "salsiz",
        "mostbröckli",
        "fleischvogel",
        "schweinshaxe",
        "kutteln",
        # Italian/charcuterie meat terms
        "lardo",
        "pancetta",
        "bresaola",
        "mortadella",
        "coppa",
        "guanciale",
        # French meat terms
        "viande",
        "boeuf",
        "veau",
        "porc",
        "agneau",
        "volaille",
        "canard",
        "dinde",
        "gibier",
        "chevreuil",
        "lapin",
        "jambon",
        "saucisse",
        "lardons",
        # English meat terms
        "chicken",
        "beef",
        "pork",
        "lamb",
        "veal",
        "duck",
        "turkey",
        "venison",
        "rabbit",
        "ham",
        "sausage",
        "bacon",
        "prosciutto",
    }
)

_FISH_RAW_KEYWORDS: frozenset[str] = frozenset(
    {
        # German fish/seafood terms
        "fisch",
        "lachs",
        "lachsfilet",
        "forelle",
        "dorsch",
        "kabeljau",
        "thunfisch",
        "zander",
        "egli",
        "eglifilet",
        "saibling",
        "felchen",
        "hecht",
        "seezunge",
        "scholle",
        "pangasius",
        "wolfsbarsch",
        "dorade",
        "sardine",
        "sardelle",
        "anchovis",
        "hering",
        "makrele",
        "crevetten",
        "crevette",
        "garnelen",
        "shrimps",
        "scampi",
        "langustine",
        "jakobsmuschel",
        "muscheln",
        "tintenfisch",
        "calamari",
        "pulpo",
        "oktopus",
        "meeresfrüchte",
        # French fish/seafood terms
        "poisson",
        "saumon",
        "truite",
        "cabillaud",
        "thon",
        "loup",
        "daurade",
        "crevettes",
        "moules",
        "calamars",
        "poulpe",
        "homard",
        "langoustine",
        "fruits de mer",
        # English fish/seafood terms
        "salmon",
        "trout",
        "cod",
        "tuna",
        "seabass",
        "shrimp",
        "prawn",
        "lobster",
        "mussel",
        "squid",
        "octopus",
        "seafood",
        "anchovy",
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
        # True food groups only — protein family, cheese, diet category.
        # Cooking method, weight class, cuisine, and taste descriptors belong in
        # their dedicated scalar columns (and are re-aggregated in computed_tags
        # for central querying). Putting them here would pollute food_groups
        # and conflate independent dimensions.
        "red_meat",
        "poultry",
        "fish",
        "seafood",
        "pork",
        "game",
        "vegetarian",
        "vegan",
        "cheese",
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


def _token_matches_keywords(token: str, keyword_set: frozenset[str]) -> bool:
    """Check if a cleaned token matches any keyword via exact or prefix match.

    German compound words (e.g. 'Pouletschenkel') start with the base noun
    ('Poulet'), so we also check if the token starts with a keyword of 4+
    characters to avoid false positives from short prefixes.
    """
    cleaned = token.rstrip(",.;:()")
    if cleaned in keyword_set:
        return True
    # Check hyphenated sub-parts
    if "-" in cleaned:
        for part in cleaned.split("-"):
            if part in keyword_set:
                return True
            # Prefix match for compound sub-parts
            for kw in keyword_set:
                if len(kw) >= 4 and part.startswith(kw):
                    return True
    else:
        # Prefix match for German compound words (e.g. "pouletschenkel" starts with "poulet")
        for kw in keyword_set:
            if len(kw) >= 4 and cleaned.startswith(kw):
                return True
    return False


def _raw_text_has_meat(ingredient_rows: list[dict]) -> bool:
    """Check unresolved ingredient raw_text for meat keywords.

    Scans only rows where ingredient_id is None (unresolved), checking each
    word (and hyphenated sub-parts) against the meat keyword set.
    """
    for row in ingredient_rows:
        if row.get("ingredient_id") is not None:
            continue
        raw = row.get("raw_text", "")
        tokens = raw.lower().split()
        for token in tokens:
            if _token_matches_keywords(token, _MEAT_RAW_KEYWORDS):
                return True
    return False


def _raw_text_has_fish(ingredient_rows: list[dict]) -> bool:
    """Check unresolved ingredient raw_text for fish/seafood keywords.

    Scans only rows where ingredient_id is None (unresolved), checking each
    word (and hyphenated sub-parts) against the fish keyword set.
    """
    for row in ingredient_rows:
        if row.get("ingredient_id") is not None:
            continue
        raw = row.get("raw_text", "")
        tokens = raw.lower().split()
        for token in tokens:
            if _token_matches_keywords(token, _FISH_RAW_KEYWORDS):
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_primary_protein(ingredient_rows: list[dict]) -> str | None:
    """Classify the dominant protein in a recipe.

    Returns one of: beef, veal, pork, lamb, poultry, game, fish, seafood,
    sausage, mixed, meat, or None (no animal protein present).

    Dietary classifications (vegan, vegetarian, cheese) are NOT returned here;
    they belong in ``compute_dietary_flags`` and ``compute_food_groups``.

    Examples:
        >>> compute_primary_protein([{"ingredient_id": 1, "quantity": 200}])
        'poultry'
        >>> compute_primary_protein([{"ingredient_id": None}])
    """
    resolved = _resolve_ingredients(ingredient_rows)
    if not resolved:
        # Nothing resolved — try raw text fallback
        raw_meat = _raw_text_has_meat(ingredient_rows)
        raw_fish = _raw_text_has_fish(ingredient_rows)
        if raw_meat and raw_fish:
            return "mixed"
        if raw_meat:
            return "meat"
        if raw_fish:
            return "fish"
        return None

    meats = [(r, e) for r, e in resolved if e.category == "meat"]
    fishes = [(r, e) for r, e in resolved if e.category == "fish"]

    if not meats and not fishes:
        # Fallback: scan unresolved ingredient raw text for meat/fish keywords
        raw_meat = _raw_text_has_meat(ingredient_rows)
        raw_fish = _raw_text_has_fish(ingredient_rows)
        if raw_meat or raw_fish:
            if raw_meat and raw_fish:
                return "mixed"
            if raw_meat:
                return "meat"
            return "fish"

        return None

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
    if primary_protein is None:
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

    Returns a sorted list of applicable flags.  When ingredients exist but
    none could be resolved (all ``ingredient_id`` null), returns an empty
    list rather than falsely claiming vegan/vegetarian.

    Falls back to scanning raw ingredient text for meat/fish keywords when
    resolved ingredients alone show no meat/fish.

    Examples:
        >>> compute_dietary_flags([], total_minutes=20)
        ['dairy-free', 'quick', 'vegan', 'vegetarian']
        >>> compute_dietary_flags([{"ingredient_id": 1}])
        []
        >>> compute_dietary_flags([{"ingredient_id": None, "raw_text": "500 g Poulet"}])
        []
    """
    resolved = _resolve_ingredients(ingredient_rows)

    # Guard: ingredients exist but none resolved — check raw text fallback
    if ingredient_rows and not resolved:
        raw_meat = _raw_text_has_meat(ingredient_rows)
        raw_fish = _raw_text_has_fish(ingredient_rows)
        flags: list[str] = []
        if not raw_meat and not raw_fish:
            # Cannot determine — don't falsely claim vegan/vegetarian
            pass
        if total_minutes is not None and total_minutes <= 30:
            flags.append("quick")
        return sorted(flags)

    categories = {e.category for _r, e in resolved}

    has_meat = "meat" in categories
    has_fish = "fish" in categories
    has_dairy = "dairy" in categories

    # Secondary fallback: check resolved ingredients' display names for
    # meat/fish keywords.  Catches miscategorized catalogue entries (e.g. a
    # meat product filed under "pantry").
    if not has_meat and not has_fish:
        for _row, entry in resolved:
            display = entry.display_de.lower()
            for token in display.split():
                if _token_matches_keywords(token, _MEAT_RAW_KEYWORDS):
                    has_meat = True
                    break
                if _token_matches_keywords(token, _FISH_RAW_KEYWORDS):
                    has_fish = True
                    break
            if has_meat or has_fish:
                break

    # Tertiary fallback: scan unresolved ingredient raw text
    if not has_meat and not has_fish:
        has_meat = _raw_text_has_meat(ingredient_rows)
        has_fish = _raw_text_has_fish(ingredient_rows)

    flags = []

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
    cooking_method: str | None = None,
    weight_class: str | None = None,
) -> list[str]:
    """Aggregate cellarbrain-compatible food-group tags from ingredients.

    `food_groups` carries only true food-group classifications (protein family,
    cheese, diet category) so it can be joined cleanly with cellarbrain's wine
    pairing vocabulary. Cooking method, weight class, cuisine, and taste
    descriptors are intentionally NOT included here: they live in their
    dedicated scalar columns and are re-aggregated in `computed_tags` for
    central querying.

    The `cooking_method` and `weight_class` parameters are retained for
    backwards compatibility but are no longer mixed into the result.

    Examples:
        >>> compute_food_groups([], "grilled", "light")
        []
    """
    del cooking_method, weight_class  # intentionally unused (see docstring)

    all_tags: set[str] = set()
    resolved = _resolve_ingredients(ingredient_rows)
    for _row, entry in resolved:
        all_tags.update(entry.pairing_tags)

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
    food_groups: list[str] | None = None,
) -> list[str]:
    """Build the aggregated computed_tags bag from all computed values.

    Merges all non-None scalar values, dietary flags, and food groups into a
    single sorted, deduplicated list. Every classification dimension lives in
    its own dedicated column AND is re-aggregated here so the bag can be used
    for central querying without joining multiple columns (issue #042).

    Examples:
        >>> build_computed_tags("poultry", "savoury", "light", "grilled",
        ...                     ["dairy-free", "quick"], "main", "swiss", "easy",
        ...                     ["poultry", "cheese"])  # doctest: +NORMALIZE_WHITESPACE
        ['cheese', 'dairy-free', 'easy', 'grilled', 'light', 'main',
         'poultry', 'quick', 'savoury', 'swiss']
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
    if food_groups:
        tags.extend(food_groups)
    return sorted(set(tags))
