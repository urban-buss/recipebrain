"""Ingredient normalisation: raw ingredient names → canonical keys.

Maps raw ingredient strings (parsed from recipe text) to canonical
ingredient keys using a seed dictionary and fuzzy alias matching.
The canonical catalogue defines the ``ingredients`` Parquet table
schema — new ingredients are resolved or flagged as unresolved.

Examples:
    >>> normalise_ingredient("Pouletbrust")
    'chicken-breast'
    >>> normalise_ingredient("Zwiebeln")
    'onion'
    >>> normalise_ingredient("unknown-xyz")  # unresolved
    None
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


@dataclass
class CanonicalIngredient:
    """A single entry in the canonical ingredient catalogue."""

    id: int
    key: str
    display_de: str
    display_fr: str | None = None
    display_it: str | None = None
    display_en: str | None = None
    category: str = "other"
    sub_category: str | None = None
    default_unit: str = "g"
    density_g_per_ml: float | None = None
    pairing_tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Seed catalogue — canonical ingredients for Swiss recipes (v1 starter set)
# ---------------------------------------------------------------------------


def _ci(
    id: int,
    key: str,
    de: str,
    fr: str | None = None,
    en: str | None = None,
    cat: str = "other",
    sub: str | None = None,
    unit: str = "g",
    density: float | None = None,
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
) -> CanonicalIngredient:
    """Shorthand factory for catalogue entries."""
    return CanonicalIngredient(
        id=id,
        key=key,
        display_de=de,
        display_fr=fr,
        display_en=en,
        category=cat,
        sub_category=sub,
        default_unit=unit,
        density_g_per_ml=density,
        pairing_tags=tags or [],
        aliases=aliases or [],
    )


SEED_CATALOGUE: list[CanonicalIngredient] = [
    # -- Meat & Poultry --
    _ci(
        1,
        "chicken-breast",
        "Pouletbrust",
        "Blanc de poulet",
        "Chicken breast",
        "meat",
        "poultry",
        aliases=[
            "Hühnerbrust",
            "Poulet",
            "Pouletbrüstli",
            "Hähnchenbrustfilet",
            "Hähnchenfilet",
            "Hähnchenbrust",
            "Pouletbrustfilet",
        ],
        tags=["poultry", "white-meat"],
    ),
    _ci(
        2,
        "chicken-thigh",
        "Pouletschenkel",
        "Cuisse de poulet",
        "Chicken thigh",
        "meat",
        "poultry",
        aliases=["Hähnchenschenkel", "Pouletoberschenkel"],
        tags=["poultry", "dark-meat"],
    ),
    _ci(
        3,
        "beef-minced",
        "Hackfleisch",
        "Viande hachée",
        "Minced beef",
        "meat",
        "beef",
        aliases=["Rindshackfleisch", "Gehacktes", "Faschiertes"],
        tags=["beef", "red-meat"],
    ),
    _ci(
        4,
        "veal-sliced",
        "Kalbsgeschnetzeltes",
        "Émincé de veau",
        "Sliced veal",
        "meat",
        "veal",
        aliases=["Kalbfleisch geschnetzelt", "Geschnetzeltes vom Kalb"],
        tags=["veal", "white-meat"],
    ),
    _ci(
        5,
        "pork-chop",
        "Schweinekotelett",
        "Côtelette de porc",
        "Pork chop",
        "meat",
        "pork",
        aliases=["Schweinskotelette", "Koteletten"],
        tags=["pork", "red-meat"],
    ),
    _ci(
        6,
        "bacon",
        "Speck",
        "Lard",
        "Bacon",
        "meat",
        "pork",
        aliases=["Bauchspeck", "Frühstücksspeck", "Räucherspeck"],
        tags=["pork", "smoky"],
    ),
    _ci(
        7,
        "sausage-bratwurst",
        "Bratwurst",
        "Saucisse à rôtir",
        "Bratwurst",
        "meat",
        "sausage",
        unit="pcs",
        aliases=["Kalbsbratwurst", "St. Galler Bratwurst"],
        tags=["pork", "sausage"],
    ),
    # -- Fish & Seafood --
    _ci(
        10,
        "salmon-fillet",
        "Lachsfilet",
        "Filet de saumon",
        "Salmon fillet",
        "fish",
        "oily-fish",
        aliases=["Lachs"],
        tags=["fish", "oily-fish"],
    ),
    _ci(
        11,
        "shrimp",
        "Crevetten",
        "Crevettes",
        "Shrimp",
        "fish",
        "shellfish",
        aliases=["Garnelen", "Shrimps", "Riesencrevetten"],
        tags=["shellfish", "seafood"],
    ),
    # -- Dairy --
    _ci(
        20,
        "butter",
        "Butter",
        "Beurre",
        "Butter",
        "dairy",
        "fat",
        density=0.911,
        aliases=["Bratbutter"],
        tags=["dairy", "fat"],
    ),
    _ci(
        21,
        "cream",
        "Rahm",
        "Crème",
        "Cream",
        "dairy",
        "cream",
        unit="dl",
        density=1.005,
        aliases=["Vollrahm", "Sahne", "Halbrahm", "Schlagrahm", "Crème entière"],
        tags=["dairy", "cream"],
    ),
    _ci(
        22,
        "cream-sour",
        "Sauerrahm",
        "Crème acidulée",
        "Sour cream",
        "dairy",
        "cream",
        unit="dl",
        density=1.005,
        aliases=["Saure Sahne", "Schmand"],
        tags=["dairy", "tangy"],
    ),
    _ci(
        23,
        "cheese-gruyere",
        "Gruyère",
        "Gruyère",
        "Gruyère cheese",
        "dairy",
        "cheese-hard",
        aliases=["Greyerzer", "Le Gruyère"],
        tags=["cheese", "alpine"],
    ),
    _ci(
        24,
        "cheese-emmental",
        "Emmentaler",
        "Emmental",
        "Emmental cheese",
        "dairy",
        "cheese-hard",
        aliases=["Emmenthaler"],
        tags=["cheese", "alpine"],
    ),
    _ci(
        25,
        "cheese-appenzeller",
        "Appenzeller",
        "Appenzeller",
        "Appenzeller cheese",
        "dairy",
        "cheese-hard",
        tags=["cheese", "alpine"],
    ),
    _ci(
        26,
        "milk",
        "Milch",
        "Lait",
        "Milk",
        "dairy",
        "liquid",
        unit="dl",
        density=1.03,
        aliases=["Vollmilch", "Magermilch"],
        tags=["dairy"],
    ),
    _ci(
        27,
        "yogurt",
        "Joghurt",
        "Yogourt",
        "Yogurt",
        "dairy",
        "fermented",
        density=1.03,
        aliases=["Jogurt", "Naturjoghurt"],
        tags=["dairy", "tangy"],
    ),
    _ci(
        28,
        "cheese-mozzarella",
        "Mozzarella",
        "Mozzarella",
        "Mozzarella",
        "dairy",
        "cheese-fresh",
        aliases=["Büffelmozzarella"],
        tags=["cheese", "mild"],
    ),
    _ci(
        29,
        "quark",
        "Quark",
        "Séré",
        "Quark",
        "dairy",
        "fresh",
        aliases=["Magerquark", "Halbfettquark"],
        tags=["dairy", "tangy"],
    ),
    # -- Eggs --
    _ci(
        30,
        "egg",
        "Ei",
        "Œuf",
        "Egg",
        "dairy",
        "egg",
        unit="pcs",
        aliases=["Eier", "Hühnerei"],
        tags=["egg"],
    ),
    # -- Vegetables --
    _ci(
        40,
        "onion",
        "Zwiebel",
        "Oignon",
        "Onion",
        "vegetable",
        "allium",
        unit="pcs",
        aliases=["Zwiebeln", "Gemüsezwiebel", "Gemüsezwiebeln"],
        tags=["allium", "aromatic"],
    ),
    _ci(
        41,
        "garlic",
        "Knoblauch",
        "Ail",
        "Garlic",
        "vegetable",
        "allium",
        unit="Zehe",
        aliases=["Knoblauchzehe", "Knoblauchzehen"],
        tags=["allium", "aromatic"],
    ),
    _ci(
        42,
        "carrot",
        "Rüebli",
        "Carotte",
        "Carrot",
        "vegetable",
        "root",
        aliases=["Karotte", "Karotten", "Möhre", "Möhren", "Rüebli"],
        tags=["root-veg", "sweet"],
    ),
    _ci(
        43,
        "potato",
        "Kartoffel",
        "Pomme de terre",
        "Potato",
        "vegetable",
        "tuber",
        aliases=["Kartoffeln", "Erdapfel", "Erdäpfel"],
        tags=["starchy", "root-veg"],
    ),
    _ci(
        44,
        "tomato",
        "Tomate",
        "Tomate",
        "Tomato",
        "vegetable",
        "fruit-veg",
        aliases=["Tomaten", "Cherrytomaten", "Cherry-Tomaten", "Rispentomaten"],
        tags=["tomato", "acidic"],
    ),
    _ci(
        45,
        "bell-pepper",
        "Peperoni",
        "Poivron",
        "Bell pepper",
        "vegetable",
        "fruit-veg",
        unit="pcs",
        aliases=["Paprika", "Peperoni rot", "Peperoni gelb"],
        tags=["pepper", "sweet"],
    ),
    _ci(
        46,
        "zucchini",
        "Zucchetti",
        "Courgette",
        "Zucchini",
        "vegetable",
        "squash",
        aliases=["Zucchini"],
        tags=["squash", "mild"],
    ),
    _ci(
        47,
        "leek",
        "Lauch",
        "Poireau",
        "Leek",
        "vegetable",
        "allium",
        aliases=["Lauchstange", "Porree"],
        tags=["allium", "mild"],
    ),
    _ci(
        48,
        "mushroom",
        "Champignon",
        "Champignon",
        "Mushroom",
        "vegetable",
        "fungus",
        aliases=["Champignons", "Pilze", "Pilz"],
        tags=["earthy", "umami"],
    ),
    _ci(
        49,
        "spinach",
        "Spinat",
        "Épinard",
        "Spinach",
        "vegetable",
        "leaf",
        aliases=["Blattspinat"],
        tags=["green", "iron-rich"],
    ),
    _ci(
        50,
        "broccoli",
        "Broccoli",
        "Brocoli",
        "Broccoli",
        "vegetable",
        "brassica",
        aliases=["Brokkoli"],
        tags=["brassica", "green"],
    ),
    _ci(
        51,
        "lettuce",
        "Salat",
        "Salade",
        "Lettuce",
        "vegetable",
        "leaf",
        unit="pcs",
        aliases=["Kopfsalat", "Eisbergsalat", "Nüsslisalat"],
        tags=["green", "fresh"],
    ),
    _ci(
        52,
        "cucumber",
        "Gurke",
        "Concombre",
        "Cucumber",
        "vegetable",
        "fruit-veg",
        unit="pcs",
        aliases=["Salatgurke"],
        tags=["fresh", "mild"],
    ),
    _ci(
        53,
        "cabbage",
        "Kohl",
        "Chou",
        "Cabbage",
        "vegetable",
        "brassica",
        aliases=["Weisskohl", "Rotkohl", "Blaukraut", "Kabis"],
        tags=["brassica"],
    ),
    _ci(
        54,
        "celery",
        "Sellerie",
        "Céleri",
        "Celery",
        "vegetable",
        "stalk",
        aliases=["Stangensellerie", "Knollensellerie"],
        tags=["aromatic", "green"],
    ),
    _ci(
        55,
        "fennel",
        "Fenchel",
        "Fenouil",
        "Fennel",
        "vegetable",
        "bulb",
        tags=["anise", "aromatic"],
    ),
    _ci(
        56,
        "corn",
        "Mais",
        "Maïs",
        "Corn",
        "vegetable",
        "grain-veg",
        aliases=["Maiskörner"],
        tags=["sweet", "starchy"],
    ),
    _ci(
        57,
        "pea",
        "Erbse",
        "Petit pois",
        "Pea",
        "vegetable",
        "legume",
        aliases=["Erbsen", "Tiefkühlerbsen"],
        tags=["legume", "sweet"],
    ),
    _ci(
        58,
        "green-bean",
        "Bohne",
        "Haricot vert",
        "Green bean",
        "vegetable",
        "legume",
        aliases=["Bohnen", "grüne Bohnen"],
        tags=["legume", "green"],
    ),
    # -- Fruit --
    _ci(
        60,
        "lemon",
        "Zitrone",
        "Citron",
        "Lemon",
        "fruit",
        "citrus",
        unit="pcs",
        aliases=["Zitronen", "Zitronensaft"],
        tags=["citrus", "acidic"],
    ),
    _ci(
        61,
        "apple",
        "Apfel",
        "Pomme",
        "Apple",
        "fruit",
        "pome",
        unit="pcs",
        aliases=["Äpfel"],
        tags=["fruit", "sweet"],
    ),
    _ci(
        62,
        "orange",
        "Orange",
        "Orange",
        "Orange",
        "fruit",
        "citrus",
        unit="pcs",
        aliases=["Orangen"],
        tags=["citrus", "sweet"],
    ),
    # -- Herbs & Spices --
    _ci(
        70,
        "parsley",
        "Petersilie",
        "Persil",
        "Parsley",
        "herb",
        "fresh",
        unit="Bund",
        aliases=["Peterli", "glatte Petersilie"],
        tags=["herb", "fresh"],
    ),
    _ci(
        71,
        "basil",
        "Basilikum",
        "Basilic",
        "Basil",
        "herb",
        "fresh",
        unit="Bund",
        tags=["herb", "aromatic"],
    ),
    _ci(
        72,
        "thyme",
        "Thymian",
        "Thym",
        "Thyme",
        "herb",
        "fresh",
        unit="Zweig",
        tags=["herb", "aromatic"],
    ),
    _ci(
        73,
        "rosemary",
        "Rosmarin",
        "Romarin",
        "Rosemary",
        "herb",
        "fresh",
        unit="Zweig",
        tags=["herb", "aromatic"],
    ),
    _ci(
        74,
        "chive",
        "Schnittlauch",
        "Ciboulette",
        "Chive",
        "herb",
        "fresh",
        unit="Bund",
        tags=["herb", "allium"],
    ),
    _ci(75, "dill", "Dill", "Aneth", "Dill", "herb", "fresh", unit="Bund", tags=["herb", "fresh"]),
    _ci(
        76,
        "coriander",
        "Koriander",
        "Coriandre",
        "Coriander",
        "herb",
        "fresh",
        unit="Bund",
        aliases=["Cilantro"],
        tags=["herb", "aromatic"],
    ),
    # -- Pantry staples --
    _ci(
        80,
        "salt",
        "Salz",
        "Sel",
        "Salt",
        "spice",
        "mineral",
        unit="Prise",
        aliases=["Meersalz", "Fleur de Sel"],
        tags=["seasoning"],
    ),
    _ci(
        81,
        "pepper-black",
        "Pfeffer",
        "Poivre",
        "Black pepper",
        "spice",
        "dried",
        unit="Prise",
        aliases=["schwarzer Pfeffer", "Pfeffer aus der Mühle"],
        tags=["seasoning", "spicy"],
    ),
    _ci(
        82,
        "sugar",
        "Zucker",
        "Sucre",
        "Sugar",
        "pantry",
        "sweetener",
        aliases=["Kristallzucker", "Rohrzucker"],
        tags=["sweet"],
    ),
    _ci(
        83,
        "flour",
        "Mehl",
        "Farine",
        "Flour",
        "pantry",
        "grain",
        aliases=["Weissmehl", "Weizenmehl", "Halbweissmehl"],
        tags=["starchy", "baking"],
    ),
    _ci(
        84,
        "olive-oil",
        "Olivenöl",
        "Huile d'olive",
        "Olive oil",
        "pantry",
        "oil",
        unit="EL",
        density=0.92,
        aliases=["Öl"],
        tags=["fat", "mediterranean"],
    ),
    _ci(
        85,
        "sunflower-oil",
        "Sonnenblumenöl",
        "Huile de tournesol",
        "Sunflower oil",
        "pantry",
        "oil",
        unit="EL",
        density=0.92,
        aliases=["Bratöl", "Rapsöl"],
        tags=["fat", "neutral"],
    ),
    _ci(
        86,
        "vinegar",
        "Essig",
        "Vinaigre",
        "Vinegar",
        "pantry",
        "acid",
        unit="EL",
        density=1.01,
        aliases=["Weissweinessig", "Balsamico", "Balsamicoessig", "Apfelessig"],
        tags=["acidic"],
    ),
    _ci(
        87,
        "mustard",
        "Senf",
        "Moutarde",
        "Mustard",
        "pantry",
        "condiment",
        unit="TL",
        aliases=["Dijonsenf"],
        tags=["pungent", "condiment"],
    ),
    # -- Grains & Pasta --
    _ci(
        90,
        "rice",
        "Reis",
        "Riz",
        "Rice",
        "pantry",
        "grain",
        aliases=["Langkornreis", "Basmati", "Basmatireis", "Risottoreis", "Jasminreis"],
        tags=["starchy", "grain"],
    ),
    _ci(
        91,
        "pasta",
        "Teigwaren",
        "Pâtes",
        "Pasta",
        "pantry",
        "grain",
        aliases=["Nudeln", "Spaghetti", "Penne", "Fusilli", "Tagliatelle"],
        tags=["starchy", "grain"],
    ),
    _ci(
        92,
        "bread",
        "Brot",
        "Pain",
        "Bread",
        "bakery",
        "baked",
        aliases=["Weissbrot", "Vollkornbrot", "Toastbrot"],
        tags=["starchy", "baking"],
    ),
    # -- Canned / Preserved --
    _ci(
        95,
        "tomato-canned",
        "Pelati",
        "Tomates pelées",
        "Canned tomatoes",
        "pantry",
        "canned",
        unit="Dose",
        aliases=["Dosentomaten", "gehackte Tomaten", "Tomatenkonserve"],
        tags=["tomato"],
    ),
    _ci(
        96,
        "tomato-paste",
        "Tomatenpüree",
        "Concentré de tomates",
        "Tomato paste",
        "pantry",
        "preserved",
        unit="EL",
        aliases=["Tomatenmark"],
        tags=["tomato", "concentrated"],
    ),
    _ci(
        97,
        "coconut-milk",
        "Kokosmilch",
        "Lait de coco",
        "Coconut milk",
        "pantry",
        "canned",
        unit="Dose",
        aliases=["Kokosnussmilch"],
        tags=["coconut", "creamy"],
    ),
    # -- Stock / Broth --
    _ci(
        100,
        "stock-chicken",
        "Hühnerbrühe",
        "Bouillon de poulet",
        "Chicken stock",
        "pantry",
        "stock",
        unit="dl",
        aliases=["Hühnerbouillon", "Pouletbouillon", "Bouillon"],
        tags=["umami", "poultry"],
    ),
    _ci(
        101,
        "stock-vegetable",
        "Gemüsebouillon",
        "Bouillon de légumes",
        "Vegetable stock",
        "pantry",
        "stock",
        unit="dl",
        aliases=["Gemüsebrühe"],
        tags=["umami", "vegetable"],
    ),
    # -- Wine / Alcohol --
    _ci(
        105,
        "white-wine",
        "Weisswein",
        "Vin blanc",
        "White wine",
        "alcohol",
        "wine",
        unit="dl",
        aliases=["trockener Weisswein"],
        tags=["wine", "acidic"],
    ),
    _ci(
        106,
        "red-wine",
        "Rotwein",
        "Vin rouge",
        "Red wine",
        "alcohol",
        "wine",
        unit="dl",
        aliases=["trockener Rotwein"],
        tags=["wine", "tannic"],
    ),
]


# ---------------------------------------------------------------------------
# Lookup index (built once at import time)
# ---------------------------------------------------------------------------


def _build_index(catalogue: list[CanonicalIngredient]) -> dict[str, str]:
    """Build a normalised-name → canonical-key index from the catalogue.

    Indexes: display_de, display_fr, display_en, display_it, and all aliases.
    All keys are lowercased, accent-stripped, and whitespace-collapsed.
    """
    index: dict[str, str] = {}
    for item in catalogue:
        names = [item.display_de]
        if item.display_fr:
            names.append(item.display_fr)
        if item.display_it:
            names.append(item.display_it)
        if item.display_en:
            names.append(item.display_en)
        names.extend(item.aliases)
        names.append(item.key)

        for name in names:
            normalised = _normalise(name)
            if normalised:
                index[normalised] = item.key
    return index


def _normalise(text: str) -> str:
    """Normalise text for matching: lowercase, strip accents, collapse whitespace.

    Examples:
        >>> _normalise("Pouletbrust")
        'pouletbrust'
        >>> _normalise("Crème entière")
        'creme entiere'
    """
    text = text.strip().lower()
    # Strip accents
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Collapse whitespace
    text = " ".join(text.split())
    return text


_INDEX: dict[str, str] = _build_index(SEED_CATALOGUE)
_CATALOGUE_BY_KEY: dict[str, CanonicalIngredient] = {item.key: item for item in SEED_CATALOGUE}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalise_ingredient(raw_name: str) -> str | None:
    """Look up a raw ingredient name and return its canonical key.

    Matches against display names (DE, FR, EN, IT) and aliases.
    Returns None if no match is found.

    Args:
        raw_name: Raw ingredient text, e.g. "Pouletbrust" or "Zwiebeln".

    Returns:
        Canonical key like "chicken-breast", or None if unresolved.

    Examples:
        >>> normalise_ingredient("Pouletbrust")
        'chicken-breast'
        >>> normalise_ingredient("Zwiebeln")
        'onion'
        >>> normalise_ingredient("Xylophon")
    """
    normalised = _normalise(raw_name)
    if not normalised:
        return None
    return _INDEX.get(normalised)


def get_ingredient(key: str) -> CanonicalIngredient | None:
    """Look up a CanonicalIngredient by its key.

    Args:
        key: Canonical ingredient key, e.g. "chicken-breast".

    Returns:
        CanonicalIngredient or None if not in catalogue.
    """
    return _CATALOGUE_BY_KEY.get(key)


def get_ingredient_id(raw_name: str) -> int | None:
    """Resolve a raw ingredient name to its catalogue ID.

    Convenience wrapper combining normalise_ingredient + get_ingredient.

    Args:
        raw_name: Raw ingredient text.

    Returns:
        Integer ID or None if unresolved.
    """
    key = normalise_ingredient(raw_name)
    if key is None:
        return None
    item = _CATALOGUE_BY_KEY.get(key)
    return item.id if item else None


def catalogue_to_rows() -> list[dict]:
    """Convert the seed catalogue to row dicts matching SCHEMAS["ingredients"].

    Suitable for writing to the ingredients Parquet table via writer.write_table.
    """
    return [
        {
            "id": item.id,
            "key": item.key,
            "display_de": item.display_de,
            "display_fr": item.display_fr,
            "display_it": item.display_it,
            "display_en": item.display_en,
            "category": item.category,
            "sub_category": item.sub_category,
            "default_unit": item.default_unit,
            "density_g_per_ml": item.density_g_per_ml,
            "pairing_tags": item.pairing_tags,
            "aliases": item.aliases,
        }
        for item in SEED_CATALOGUE
    ]


def all_keys() -> list[str]:
    """Return all canonical ingredient keys in the catalogue."""
    return [item.key for item in SEED_CATALOGUE]
