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

import re
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
    # -- Additional Meat & Poultry --
    _ci(
        110,
        "cervelat",
        "Cervelat",
        "Cervelas",
        "Cervelat",
        "meat",
        "sausage",
        unit="pcs",
        aliases=["Cervelats"],
        tags=["sausage", "swiss"],
    ),
    _ci(
        111,
        "lamb",
        "Lamm",
        "Agneau",
        "Lamb",
        "meat",
        "lamb",
        aliases=["Lammfleisch", "Lammkeule", "Lammrack", "Lammfilet", "Lamm-Rack"],
        tags=["lamb", "red-meat"],
    ),
    _ci(
        112,
        "pork-fillet",
        "Schweinsfilet",
        "Filet de porc",
        "Pork fillet",
        "meat",
        "pork",
        aliases=["Schweinefilet", "Schweinslungenbraten"],
        tags=["pork", "lean"],
    ),
    _ci(
        113,
        "pork-belly",
        "Schweinebauch",
        "Poitrine de porc",
        "Pork belly",
        "meat",
        "pork",
        aliases=["Schweinsbauch"],
        tags=["pork", "fatty"],
    ),
    _ci(
        114,
        "beef-steak",
        "Rindssteak",
        "Steak de bœuf",
        "Beef steak",
        "meat",
        "beef",
        aliases=["Entrecôte", "Rindsfilet", "Rindshuft", "Huft", "Rumpsteak", "Rindsentrecôte"],
        tags=["beef", "red-meat"],
    ),
    _ci(
        115,
        "ham",
        "Schinken",
        "Jambon",
        "Ham",
        "meat",
        "pork",
        aliases=["Rohschinken", "Kochschinken", "Schinkenwürfel", "Vorderschinken"],
        tags=["pork", "cured"],
    ),
    _ci(
        116,
        "chicken-whole",
        "Poulet ganz",
        "Poulet entier",
        "Whole chicken",
        "meat",
        "poultry",
        aliases=["Bratpoulet", "ganzes Poulet"],
        tags=["poultry"],
    ),
    _ci(
        117,
        "duck",
        "Ente",
        "Canard",
        "Duck",
        "meat",
        "poultry",
        aliases=["Entenbrust", "Entenbrüstli"],
        tags=["poultry", "dark-meat"],
    ),
    _ci(
        118,
        "rabbit",
        "Kaninchen",
        "Lapin",
        "Rabbit",
        "meat",
        "game",
        aliases=["Kaninchenrücken"],
        tags=["game", "lean"],
    ),
    _ci(
        119,
        "salami",
        "Salami",
        "Salami",
        "Salami",
        "meat",
        "cured",
        aliases=["Salametti"],
        tags=["cured", "pork"],
    ),
    _ci(
        120,
        "sausage-wiener",
        "Wienerli",
        "Saucisse de Vienne",
        "Wiener sausage",
        "meat",
        "sausage",
        unit="pcs",
        aliases=["Wiener", "Wienerli"],
        tags=["sausage", "pork"],
    ),
    _ci(
        121,
        "beef-roast",
        "Rindsbraten",
        "Rôti de bœuf",
        "Beef roast",
        "meat",
        "beef",
        aliases=["Schmorbraten", "Siedfleisch"],
        tags=["beef", "braising"],
    ),
    # -- Additional Fish & Seafood --
    _ci(
        125,
        "cod",
        "Kabeljau",
        "Cabillaud",
        "Cod",
        "fish",
        "white-fish",
        aliases=["Dorsch"],
        tags=["fish", "white-fish"],
    ),
    _ci(
        126,
        "tuna",
        "Thunfisch",
        "Thon",
        "Tuna",
        "fish",
        "oily-fish",
        aliases=["Thon"],
        tags=["fish", "oily-fish"],
    ),
    _ci(
        127,
        "trout",
        "Forelle",
        "Truite",
        "Trout",
        "fish",
        "freshwater",
        aliases=["Lachsforelle", "Forellenfilet"],
        tags=["fish", "freshwater"],
    ),
    _ci(
        128,
        "mussels",
        "Muscheln",
        "Moules",
        "Mussels",
        "fish",
        "shellfish",
        aliases=["Miesmuscheln"],
        tags=["shellfish", "seafood"],
    ),
    _ci(
        129,
        "calamari",
        "Tintenfisch",
        "Calamar",
        "Calamari",
        "fish",
        "cephalopod",
        aliases=["Calamares", "Calamari"],
        tags=["seafood"],
    ),
    # -- Additional Dairy & Cheese --
    _ci(
        130,
        "mascarpone",
        "Mascarpone",
        "Mascarpone",
        "Mascarpone",
        "dairy",
        "cheese-fresh",
        aliases=[],
        tags=["cheese", "creamy"],
    ),
    _ci(
        131,
        "ricotta",
        "Ricotta",
        "Ricotta",
        "Ricotta",
        "dairy",
        "cheese-fresh",
        aliases=[],
        tags=["cheese", "mild"],
    ),
    _ci(
        132,
        "parmesan",
        "Parmesan",
        "Parmesan",
        "Parmesan",
        "dairy",
        "cheese-hard",
        aliases=["Parmigiano", "Parmigiano Reggiano", "Sbrinz"],
        tags=["cheese", "umami"],
    ),
    _ci(
        133,
        "cream-cheese",
        "Frischkäse",
        "Fromage frais",
        "Cream cheese",
        "dairy",
        "cheese-fresh",
        aliases=["Philadelphia", "Rahmfrischkäse", "Streichkäse"],
        tags=["cheese", "creamy"],
    ),
    _ci(
        134,
        "feta",
        "Feta",
        "Feta",
        "Feta",
        "dairy",
        "cheese-brined",
        aliases=["Schafskäse", "Schafkäse"],
        tags=["cheese", "tangy"],
    ),
    _ci(
        135,
        "cheese-raclette",
        "Raclettekäse",
        "Fromage à raclette",
        "Raclette cheese",
        "dairy",
        "cheese-hard",
        aliases=["Raclette"],
        tags=["cheese", "alpine", "swiss"],
    ),
    _ci(
        136,
        "creme-fraiche",
        "Crème fraîche",
        "Crème fraîche",
        "Crème fraîche",
        "dairy",
        "cream",
        aliases=["Saure Halbrahm", "Crème fraiche"],
        tags=["dairy", "tangy"],
    ),
    _ci(
        137,
        "buttermilk",
        "Buttermilch",
        "Babeurre",
        "Buttermilk",
        "dairy",
        "fermented",
        unit="dl",
        aliases=[],
        tags=["dairy", "tangy"],
    ),
    _ci(
        138,
        "cheese-fondue-mix",
        "Fonduemischung",
        "Mélange à fondue",
        "Fondue cheese mix",
        "dairy",
        "cheese-hard",
        aliases=["Fondue", "Käsemischung"],
        tags=["cheese", "swiss"],
    ),
    _ci(
        139,
        "whipped-cream",
        "Schlagrahm",
        "Crème fouettée",
        "Whipped cream",
        "dairy",
        "cream",
        unit="dl",
        aliases=["geschlagener Rahm"],
        tags=["dairy", "sweet"],
    ),
    # -- Additional Vegetables --
    _ci(
        140,
        "sweet-potato",
        "Süsskartoffel",
        "Patate douce",
        "Sweet potato",
        "vegetable",
        "tuber",
        aliases=["Süsskartoffeln", "Batate", "Bataten"],
        tags=["starchy", "sweet"],
    ),
    _ci(
        141,
        "aubergine",
        "Aubergine",
        "Aubergine",
        "Eggplant",
        "vegetable",
        "fruit-veg",
        aliases=["Auberginen", "Melanzane"],
        tags=["mediterranean"],
    ),
    _ci(
        142,
        "avocado",
        "Avocado",
        "Avocat",
        "Avocado",
        "vegetable",
        "fruit-veg",
        unit="pcs",
        aliases=["Avocados"],
        tags=["creamy", "healthy-fat"],
    ),
    _ci(
        143,
        "cauliflower",
        "Blumenkohl",
        "Chou-fleur",
        "Cauliflower",
        "vegetable",
        "brassica",
        aliases=["Karfiol"],
        tags=["brassica"],
    ),
    _ci(
        144,
        "asparagus",
        "Spargel",
        "Asperge",
        "Asparagus",
        "vegetable",
        "stalk",
        aliases=["Spargeln", "grüner Spargel", "weisser Spargel"],
        tags=["spring", "elegant"],
    ),
    _ci(
        145,
        "beetroot",
        "Randen",
        "Betterave",
        "Beetroot",
        "vegetable",
        "root",
        aliases=["Rande", "Rote Bete", "Rote Beete"],
        tags=["earthy", "root-veg"],
    ),
    _ci(
        146,
        "pumpkin",
        "Kürbis",
        "Courge",
        "Pumpkin",
        "vegetable",
        "squash",
        aliases=["Butternut", "Butternusskürbis", "Hokkaidokürbis", "Hokkaido"],
        tags=["squash", "sweet"],
    ),
    _ci(
        147,
        "radish",
        "Radieschen",
        "Radis",
        "Radish",
        "vegetable",
        "root",
        aliases=["Rettich"],
        tags=["peppery", "root-veg"],
    ),
    _ci(
        148,
        "spring-onion",
        "Frühlingszwiebel",
        "Oignon nouveau",
        "Spring onion",
        "vegetable",
        "allium",
        aliases=["Frühlingszwiebeln", "Lauchzwiebel", "Lauchzwiebeln"],
        tags=["allium", "fresh"],
    ),
    _ci(
        149,
        "shallot",
        "Schalotte",
        "Échalote",
        "Shallot",
        "vegetable",
        "allium",
        unit="pcs",
        aliases=["Schalotten"],
        tags=["allium", "mild"],
    ),
    _ci(
        150,
        "ginger",
        "Ingwer",
        "Gingembre",
        "Ginger",
        "vegetable",
        "rhizome",
        aliases=["frischer Ingwer"],
        tags=["spicy", "aromatic"],
    ),
    _ci(
        151,
        "chilli",
        "Peperoncino",
        "Piment",
        "Chilli",
        "vegetable",
        "fruit-veg",
        aliases=["Peperoncini", "Chilischote", "Chili", "Chilischoten"],
        tags=["spicy", "hot"],
    ),
    _ci(
        152,
        "pak-choi",
        "Pak Choi",
        "Bok Choy",
        "Pak Choi",
        "vegetable",
        "brassica",
        aliases=["Bok Choy", "Pak Choy"],
        tags=["asian", "green"],
    ),
    _ci(
        153,
        "rocket",
        "Rucola",
        "Roquette",
        "Rocket",
        "vegetable",
        "leaf",
        aliases=["Rauke"],
        tags=["peppery", "green"],
    ),
    _ci(
        154,
        "cherry-tomato",
        "Cherrytomaten",
        "Tomates cerises",
        "Cherry tomatoes",
        "vegetable",
        "fruit-veg",
        aliases=["Cherry-Tomaten", "Kirschtomaten", "Datteltomaten"],
        tags=["tomato", "sweet"],
    ),
    _ci(
        155,
        "celeriac",
        "Knollensellerie",
        "Céleri-rave",
        "Celeriac",
        "vegetable",
        "root",
        aliases=["Sellerie Knolle"],
        tags=["aromatic", "root-veg"],
    ),
    _ci(
        156,
        "kohlrabi",
        "Kohlrabi",
        "Chou-rave",
        "Kohlrabi",
        "vegetable",
        "brassica",
        aliases=["Kohlraben"],
        tags=["brassica", "mild"],
    ),
    _ci(
        157,
        "brussels-sprouts",
        "Rosenkohl",
        "Choux de Bruxelles",
        "Brussels sprouts",
        "vegetable",
        "brassica",
        aliases=["Röschen"],
        tags=["brassica"],
    ),
    _ci(
        158,
        "chicory",
        "Chicorée",
        "Endive",
        "Chicory",
        "vegetable",
        "leaf",
        aliases=["Zuckerhut"],
        tags=["bitter", "leaf"],
    ),
    _ci(
        159,
        "chard",
        "Mangold",
        "Bette",
        "Chard",
        "vegetable",
        "leaf",
        aliases=["Krautstiel"],
        tags=["green", "earthy"],
    ),
    _ci(
        160,
        "edamame",
        "Edamame",
        "Edamame",
        "Edamame",
        "vegetable",
        "legume",
        aliases=["Sojabohnen"],
        tags=["legume", "asian"],
    ),
    _ci(
        161,
        "artichoke",
        "Artischocke",
        "Artichaut",
        "Artichoke",
        "vegetable",
        "flower",
        aliases=["Artischocken", "Artischockenherzen"],
        tags=["mediterranean"],
    ),
    # -- Additional Fruit --
    _ci(
        165,
        "lime",
        "Limette",
        "Lime",
        "Lime",
        "fruit",
        "citrus",
        unit="pcs",
        aliases=["Limetten", "Limettensaft"],
        tags=["citrus", "acidic"],
    ),
    _ci(
        166,
        "mango",
        "Mango",
        "Mangue",
        "Mango",
        "fruit",
        "tropical",
        unit="pcs",
        aliases=["Mangos"],
        tags=["tropical", "sweet"],
    ),
    _ci(
        167,
        "banana",
        "Banane",
        "Banane",
        "Banana",
        "fruit",
        "tropical",
        unit="pcs",
        aliases=["Bananen"],
        tags=["tropical", "sweet"],
    ),
    _ci(
        168,
        "raspberry",
        "Himbeere",
        "Framboise",
        "Raspberry",
        "fruit",
        "berry",
        aliases=["Himbeeren"],
        tags=["berry", "sweet-tart"],
    ),
    _ci(
        169,
        "strawberry",
        "Erdbeere",
        "Fraise",
        "Strawberry",
        "fruit",
        "berry",
        aliases=["Erdbeeren"],
        tags=["berry", "sweet"],
    ),
    _ci(
        170,
        "blueberry",
        "Heidelbeere",
        "Myrtille",
        "Blueberry",
        "fruit",
        "berry",
        aliases=["Heidelbeeren", "Blaubeeren"],
        tags=["berry", "sweet"],
    ),
    _ci(
        171,
        "pear",
        "Birne",
        "Poire",
        "Pear",
        "fruit",
        "pome",
        unit="pcs",
        aliases=["Birnen"],
        tags=["fruit", "sweet"],
    ),
    _ci(
        172,
        "rhubarb",
        "Rhabarber",
        "Rhubarbe",
        "Rhubarb",
        "fruit",
        "stalk",
        aliases=["Rhabarberstangen"],
        tags=["tart", "spring"],
    ),
    _ci(
        173,
        "grape",
        "Traube",
        "Raisin",
        "Grape",
        "fruit",
        "berry",
        aliases=["Trauben", "Weintrauben"],
        tags=["fruit", "sweet"],
    ),
    _ci(
        174,
        "peach",
        "Pfirsich",
        "Pêche",
        "Peach",
        "fruit",
        "stone",
        unit="pcs",
        aliases=["Pfirsiche"],
        tags=["stone-fruit", "sweet"],
    ),
    _ci(
        175,
        "apricot",
        "Aprikose",
        "Abricot",
        "Apricot",
        "fruit",
        "stone",
        aliases=["Aprikosen"],
        tags=["stone-fruit", "sweet"],
    ),
    _ci(
        176,
        "cherry",
        "Kirsche",
        "Cerise",
        "Cherry",
        "fruit",
        "stone",
        aliases=["Kirschen"],
        tags=["stone-fruit", "sweet"],
    ),
    _ci(
        177,
        "plum",
        "Zwetschge",
        "Prune",
        "Plum",
        "fruit",
        "stone",
        aliases=["Zwetschgen", "Pflaume", "Pflaumen"],
        tags=["stone-fruit"],
    ),
    _ci(
        178,
        "coconut",
        "Kokosnuss",
        "Noix de coco",
        "Coconut",
        "fruit",
        "tropical",
        aliases=["Kokosraspel", "Kokosflocken"],
        tags=["tropical", "sweet"],
    ),
    _ci(
        179,
        "passion-fruit",
        "Passionsfrucht",
        "Fruit de la passion",
        "Passion fruit",
        "fruit",
        "tropical",
        aliases=["Maracuja"],
        tags=["tropical", "tart"],
    ),
    _ci(
        180,
        "cranberry",
        "Cranberry",
        "Canneberge",
        "Cranberry",
        "fruit",
        "berry",
        aliases=["Cranberries", "getrocknete Cranberries"],
        tags=["berry", "tart"],
    ),
    # -- Additional Herbs & Spices --
    _ci(
        185,
        "mint",
        "Minze",
        "Menthe",
        "Mint",
        "herb",
        "fresh",
        unit="Bund",
        aliases=["Pfefferminze"],
        tags=["herb", "fresh"],
    ),
    _ci(
        186,
        "oregano",
        "Oregano",
        "Origan",
        "Oregano",
        "herb",
        "dried",
        unit="TL",
        tags=["herb", "mediterranean"],
    ),
    _ci(
        187,
        "sage",
        "Salbei",
        "Sauge",
        "Sage",
        "herb",
        "fresh",
        unit="Blatt",
        aliases=["Salbeiblätter"],
        tags=["herb", "aromatic"],
    ),
    _ci(
        188,
        "bay-leaf",
        "Lorbeerblatt",
        "Feuille de laurier",
        "Bay leaf",
        "herb",
        "dried",
        unit="Blatt",
        aliases=["Lorbeerblätter", "Lorbeer"],
        tags=["herb", "aromatic"],
    ),
    _ci(
        189,
        "paprika",
        "Paprikapulver",
        "Paprika",
        "Paprika",
        "spice",
        "dried",
        unit="TL",
        aliases=["Paprika edelsüss", "geräucherter Paprika"],
        tags=["spice", "sweet"],
    ),
    _ci(
        190,
        "cumin",
        "Kreuzkümmel",
        "Cumin",
        "Cumin",
        "spice",
        "dried",
        unit="TL",
        aliases=["Kümmel"],
        tags=["spice", "earthy"],
    ),
    _ci(
        191,
        "cinnamon",
        "Zimt",
        "Cannelle",
        "Cinnamon",
        "spice",
        "dried",
        unit="TL",
        aliases=["Zimtstange", "Zimtstangen"],
        tags=["spice", "sweet"],
    ),
    _ci(
        192,
        "nutmeg",
        "Muskatnuss",
        "Noix de muscade",
        "Nutmeg",
        "spice",
        "dried",
        unit="Prise",
        aliases=["Muskat"],
        tags=["spice", "warm"],
    ),
    _ci(
        193,
        "turmeric",
        "Kurkuma",
        "Curcuma",
        "Turmeric",
        "spice",
        "dried",
        unit="TL",
        aliases=["Gelbwurz"],
        tags=["spice", "earthy"],
    ),
    _ci(
        194,
        "curry-powder",
        "Currypulver",
        "Poudre de curry",
        "Curry powder",
        "spice",
        "blend",
        unit="TL",
        aliases=["Curry"],
        tags=["spice", "blend"],
    ),
    _ci(
        195,
        "vanilla",
        "Vanille",
        "Vanille",
        "Vanilla",
        "spice",
        "dried",
        unit="Stange",
        aliases=["Vanilleschote", "Vanilleextrakt", "Vanillezucker", "Vanillinzucker"],
        tags=["sweet", "aromatic"],
    ),
    _ci(
        196,
        "chilli-flakes",
        "Chiliflocken",
        "Flocons de piment",
        "Chilli flakes",
        "spice",
        "dried",
        unit="TL",
        aliases=["Chili-Flocken"],
        tags=["spicy", "hot"],
    ),
    _ci(
        197,
        "cardamom",
        "Kardamom",
        "Cardamome",
        "Cardamom",
        "spice",
        "dried",
        unit="TL",
        tags=["spice", "aromatic"],
    ),
    _ci(
        198,
        "star-anise",
        "Sternanis",
        "Anis étoilé",
        "Star anise",
        "spice",
        "dried",
        unit="pcs",
        aliases=["Anis"],
        tags=["spice", "aromatic"],
    ),
    # -- Baking Ingredients --
    _ci(
        200,
        "baking-powder",
        "Backpulver",
        "Poudre à lever",
        "Baking powder",
        "pantry",
        "baking",
        unit="TL",
        aliases=["Triebmittel"],
        tags=["baking", "leavening"],
    ),
    _ci(
        201,
        "yeast",
        "Hefe",
        "Levure",
        "Yeast",
        "pantry",
        "baking",
        unit="Würfel",
        aliases=["Frischhefe", "Trockenhefe", "Germ"],
        tags=["baking", "leavening"],
    ),
    _ci(
        202,
        "cornstarch",
        "Maizena",
        "Maïzena",
        "Cornstarch",
        "pantry",
        "baking",
        unit="EL",
        aliases=["Maisstärke", "Stärkemehl", "Kartoffelstärke"],
        tags=["thickener", "baking"],
    ),
    _ci(
        203,
        "cocoa-powder",
        "Kakaopulver",
        "Poudre de cacao",
        "Cocoa powder",
        "pantry",
        "baking",
        unit="EL",
        aliases=["Kakao", "Backkakao"],
        tags=["chocolate", "baking"],
    ),
    _ci(
        204,
        "chocolate-dark",
        "Schokolade dunkel",
        "Chocolat noir",
        "Dark chocolate",
        "pantry",
        "baking",
        aliases=["dunkle Schokolade", "Zartbitterschokolade", "Kochschokolade"],
        tags=["chocolate", "bitter"],
    ),
    _ci(
        205,
        "chocolate-milk",
        "Milchschokolade",
        "Chocolat au lait",
        "Milk chocolate",
        "pantry",
        "baking",
        aliases=[],
        tags=["chocolate", "sweet"],
    ),
    _ci(
        206,
        "chocolate-white",
        "Weisse Schokolade",
        "Chocolat blanc",
        "White chocolate",
        "pantry",
        "baking",
        aliases=[],
        tags=["chocolate", "sweet"],
    ),
    _ci(
        207,
        "icing-sugar",
        "Puderzucker",
        "Sucre glace",
        "Icing sugar",
        "pantry",
        "sweetener",
        aliases=["Staubzucker"],
        tags=["sweet", "baking"],
    ),
    _ci(
        208,
        "brown-sugar",
        "Brauner Zucker",
        "Sucre brun",
        "Brown sugar",
        "pantry",
        "sweetener",
        aliases=["Muscovadozucker"],
        tags=["sweet", "baking"],
    ),
    _ci(
        209,
        "honey",
        "Honig",
        "Miel",
        "Honey",
        "pantry",
        "sweetener",
        unit="EL",
        aliases=["Blütenhonig", "Akazienhonig"],
        tags=["sweet", "natural"],
    ),
    _ci(
        210,
        "maple-syrup",
        "Ahornsirup",
        "Sirop d'érable",
        "Maple syrup",
        "pantry",
        "sweetener",
        unit="EL",
        aliases=[],
        tags=["sweet", "natural"],
    ),
    _ci(
        211,
        "gelatine",
        "Gelatine",
        "Gélatine",
        "Gelatine",
        "pantry",
        "baking",
        unit="Blatt",
        aliases=["Gelatineblätter"],
        tags=["thickener"],
    ),
    _ci(
        212,
        "baking-soda",
        "Natron",
        "Bicarbonate",
        "Baking soda",
        "pantry",
        "baking",
        unit="TL",
        aliases=["Backsoda"],
        tags=["baking", "leavening"],
    ),
    # -- Pantry / Sauces / Condiments --
    _ci(
        215,
        "soy-sauce",
        "Sojasauce",
        "Sauce soja",
        "Soy sauce",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Sojasosse", "Sojasauce hell", "Sojasauce dunkel"],
        tags=["umami", "asian"],
    ),
    _ci(
        216,
        "fish-sauce",
        "Fischsauce",
        "Sauce de poisson",
        "Fish sauce",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Fischsosse"],
        tags=["umami", "asian"],
    ),
    _ci(
        217,
        "sesame-oil",
        "Sesamöl",
        "Huile de sésame",
        "Sesame oil",
        "pantry",
        "oil",
        unit="TL",
        aliases=["geröstetes Sesamöl"],
        tags=["asian", "nutty"],
    ),
    _ci(
        218,
        "peanut-butter",
        "Erdnussbutter",
        "Beurre de cacahuète",
        "Peanut butter",
        "pantry",
        "spread",
        unit="EL",
        aliases=["Erdnussmus"],
        tags=["nutty"],
    ),
    _ci(
        219,
        "tahini",
        "Tahini",
        "Tahini",
        "Tahini",
        "pantry",
        "spread",
        unit="EL",
        aliases=["Tahin", "Sesampaste"],
        tags=["nutty", "middle-eastern"],
    ),
    _ci(
        220,
        "miso",
        "Miso",
        "Miso",
        "Miso",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Misopaste", "Miso-Paste"],
        tags=["umami", "japanese"],
    ),
    _ci(
        221,
        "ketchup",
        "Ketchup",
        "Ketchup",
        "Ketchup",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Tomatenketchup"],
        tags=["sweet", "tomato"],
    ),
    _ci(
        222,
        "mayonnaise",
        "Mayonnaise",
        "Mayonnaise",
        "Mayonnaise",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Mayo"],
        tags=["creamy", "rich"],
    ),
    _ci(
        223,
        "worcestershire",
        "Worcestersauce",
        "Sauce Worcestershire",
        "Worcestershire sauce",
        "pantry",
        "condiment",
        unit="TL",
        aliases=["Worcestershire"],
        tags=["umami", "pungent"],
    ),
    _ci(
        224,
        "tabasco",
        "Tabasco",
        "Tabasco",
        "Tabasco",
        "pantry",
        "condiment",
        unit="Spritzer",
        aliases=["Chilisauce", "Sriracha"],
        tags=["spicy"],
    ),
    _ci(
        225,
        "pesto",
        "Pesto",
        "Pesto",
        "Pesto",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["Basilikumpesto", "Pesto Genovese", "Pesto rosso"],
        tags=["herb", "italian"],
    ),
    _ci(
        226,
        "capers",
        "Kapern",
        "Câpres",
        "Capers",
        "pantry",
        "preserved",
        unit="EL",
        aliases=["Kaper"],
        tags=["briny", "mediterranean"],
    ),
    _ci(
        227,
        "olives",
        "Oliven",
        "Olives",
        "Olives",
        "pantry",
        "preserved",
        aliases=["schwarze Oliven", "Kalamata-Oliven", "grüne Oliven"],
        tags=["briny", "mediterranean"],
    ),
    _ci(
        228,
        "pickles",
        "Essiggurken",
        "Cornichons",
        "Pickles",
        "pantry",
        "preserved",
        aliases=["Cornichons", "Gewürzgurken"],
        tags=["acidic", "crunchy"],
    ),
    _ci(
        229,
        "aceto-balsamico",
        "Aceto balsamico",
        "Vinaigre balsamique",
        "Balsamic vinegar",
        "pantry",
        "acid",
        unit="EL",
        aliases=["Aceto balsamico bianco", "Balsamicoessig", "Balsamico bianco"],
        tags=["acidic", "sweet"],
    ),
    # -- Nuts & Seeds --
    _ci(
        230,
        "almond",
        "Mandel",
        "Amande",
        "Almond",
        "pantry",
        "nut",
        aliases=["Mandeln", "Mandelblättchen", "gemahlene Mandeln", "Mandelstifte"],
        tags=["nut", "sweet"],
    ),
    _ci(
        231,
        "walnut",
        "Baumnuss",
        "Noix",
        "Walnut",
        "pantry",
        "nut",
        aliases=["Baumnüsse", "Walnuss", "Walnüsse", "Nüsse"],
        tags=["nut", "earthy"],
    ),
    _ci(
        232,
        "hazelnut",
        "Haselnuss",
        "Noisette",
        "Hazelnut",
        "pantry",
        "nut",
        aliases=["Haselnüsse", "gemahlene Haselnüsse"],
        tags=["nut", "sweet"],
    ),
    _ci(
        233,
        "pine-nut",
        "Pinienkerne",
        "Pignon",
        "Pine nut",
        "pantry",
        "nut",
        aliases=["Pinienkern"],
        tags=["nut", "buttery"],
    ),
    _ci(
        234,
        "cashew",
        "Cashewnuss",
        "Noix de cajou",
        "Cashew",
        "pantry",
        "nut",
        aliases=["Cashewnüsse", "Cashew-Kerne", "Cashewkerne"],
        tags=["nut", "creamy"],
    ),
    _ci(
        235,
        "sesame-seeds",
        "Sesamkörner",
        "Graines de sésame",
        "Sesame seeds",
        "pantry",
        "seed",
        unit="EL",
        aliases=["Sesam", "Sesamsamen"],
        tags=["seed", "nutty"],
    ),
    _ci(
        236,
        "sunflower-seeds",
        "Sonnenblumenkerne",
        "Graines de tournesol",
        "Sunflower seeds",
        "pantry",
        "seed",
        unit="EL",
        aliases=[],
        tags=["seed"],
    ),
    _ci(
        237,
        "pumpkin-seeds",
        "Kürbiskerne",
        "Graines de courge",
        "Pumpkin seeds",
        "pantry",
        "seed",
        unit="EL",
        aliases=[],
        tags=["seed"],
    ),
    _ci(
        238,
        "flaxseed",
        "Leinsamen",
        "Graines de lin",
        "Flaxseed",
        "pantry",
        "seed",
        unit="EL",
        aliases=["Leinsaat"],
        tags=["seed", "omega-3"],
    ),
    _ci(
        239,
        "chia-seeds",
        "Chiasamen",
        "Graines de chia",
        "Chia seeds",
        "pantry",
        "seed",
        unit="EL",
        aliases=["Chia"],
        tags=["seed", "superfood"],
    ),
    _ci(
        240,
        "pistachio",
        "Pistazie",
        "Pistache",
        "Pistachio",
        "pantry",
        "nut",
        aliases=["Pistazien", "Pistazienkerne"],
        tags=["nut", "sweet"],
    ),
    # -- Grains, Pasta & Noodles --
    _ci(
        245,
        "couscous",
        "Couscous",
        "Couscous",
        "Couscous",
        "pantry",
        "grain",
        aliases=[],
        tags=["grain", "quick"],
    ),
    _ci(
        246,
        "quinoa",
        "Quinoa",
        "Quinoa",
        "Quinoa",
        "pantry",
        "grain",
        aliases=[],
        tags=["grain", "protein"],
    ),
    _ci(
        247,
        "polenta",
        "Polenta",
        "Polenta",
        "Polenta",
        "pantry",
        "grain",
        aliases=["Bramata", "Maisgriess"],
        tags=["grain", "starchy"],
    ),
    _ci(
        248,
        "oats",
        "Haferflocken",
        "Flocons d'avoine",
        "Oats",
        "pantry",
        "grain",
        aliases=["Hafer", "Rollhafer", "zarte Haferflocken"],
        tags=["grain", "fibre"],
    ),
    _ci(
        249,
        "bulgur",
        "Bulgur",
        "Boulgour",
        "Bulgur",
        "pantry",
        "grain",
        aliases=[],
        tags=["grain", "middle-eastern"],
    ),
    _ci(
        250,
        "noodles-asian",
        "Ramen-Nudeln",
        "Nouilles ramen",
        "Ramen noodles",
        "pantry",
        "noodle",
        aliases=[
            "Ramen",
            "Udon",
            "Udon-Nudeln",
            "Glasnudeln",
            "Reisnudeln",
            "Mie-Nudeln",
            "Mie",
            "Soba",
            "Sobanudeln",
        ],
        tags=["noodle", "asian"],
    ),
    _ci(
        251,
        "rice-paper",
        "Reisblätter",
        "Feuilles de riz",
        "Rice paper",
        "pantry",
        "wrapper",
        aliases=["Reispapier"],
        tags=["asian", "wrapper"],
    ),
    _ci(
        252,
        "lasagne-sheets",
        "Lasagneblätter",
        "Feuilles de lasagne",
        "Lasagne sheets",
        "pantry",
        "pasta",
        aliases=["Lasagne"],
        tags=["pasta", "italian"],
    ),
    _ci(
        253,
        "gnocchi",
        "Gnocchi",
        "Gnocchi",
        "Gnocchi",
        "pantry",
        "pasta",
        aliases=[],
        tags=["pasta", "italian"],
    ),
    _ci(
        254,
        "tortellini",
        "Tortellini",
        "Tortellini",
        "Tortellini",
        "pantry",
        "pasta",
        aliases=["Tortelloni"],
        tags=["pasta", "filled"],
    ),
    # -- Doughs & Wrappers --
    _ci(
        258,
        "puff-pastry",
        "Blätterteig",
        "Pâte feuilletée",
        "Puff pastry",
        "pantry",
        "dough",
        aliases=["Butterblätterteig"],
        tags=["baking", "flaky"],
    ),
    _ci(
        259,
        "shortcrust-pastry",
        "Kuchenteig",
        "Pâte brisée",
        "Shortcrust pastry",
        "pantry",
        "dough",
        aliases=["Mürbeteig"],
        tags=["baking"],
    ),
    _ci(
        260,
        "pizza-dough",
        "Pizzateig",
        "Pâte à pizza",
        "Pizza dough",
        "pantry",
        "dough",
        aliases=[],
        tags=["baking", "italian"],
    ),
    _ci(
        261,
        "filo-pastry",
        "Filoteig",
        "Pâte filo",
        "Filo pastry",
        "pantry",
        "dough",
        aliases=["Yufka"],
        tags=["baking", "flaky"],
    ),
    _ci(
        262,
        "tortilla",
        "Tortilla",
        "Tortilla",
        "Tortilla",
        "pantry",
        "wrapper",
        unit="pcs",
        aliases=["Tortillas", "Weizentortillas"],
        tags=["wrapper", "mexican"],
    ),
    # -- Legumes & Pulses --
    _ci(
        265,
        "lentil",
        "Linse",
        "Lentille",
        "Lentil",
        "pantry",
        "legume",
        aliases=["Linsen", "rote Linsen", "grüne Linsen", "Beluga-Linsen", "Belugalinsen"],
        tags=["legume", "protein"],
    ),
    _ci(
        266,
        "chickpea",
        "Kichererbse",
        "Pois chiche",
        "Chickpea",
        "pantry",
        "legume",
        aliases=["Kichererbsen"],
        tags=["legume", "protein"],
    ),
    _ci(
        267,
        "kidney-bean",
        "Kidneybohne",
        "Haricot rouge",
        "Kidney bean",
        "pantry",
        "legume",
        aliases=["Kidneybohnen", "rote Bohnen"],
        tags=["legume", "protein"],
    ),
    _ci(
        268,
        "white-bean",
        "Weisse Bohne",
        "Haricot blanc",
        "White bean",
        "pantry",
        "legume",
        aliases=["Weisse Bohnen", "Cannellini"],
        tags=["legume", "protein"],
    ),
    _ci(
        269,
        "tofu",
        "Tofu",
        "Tofu",
        "Tofu",
        "pantry",
        "protein",
        aliases=["Seidentofu", "Räuchertofu"],
        tags=["vegan", "protein"],
    ),
    # -- Beverages / Liquids --
    _ci(
        272,
        "coffee",
        "Kaffeepulver",
        "Café",
        "Coffee",
        "pantry",
        "beverage",
        unit="TL",
        aliases=["Kaffee", "Espresso", "Instantkaffee"],
        tags=["bitter", "aromatic"],
    ),
    _ci(
        273,
        "beer",
        "Bier",
        "Bière",
        "Beer",
        "alcohol",
        "beer",
        unit="dl",
        aliases=[],
        tags=["alcohol", "bitter"],
    ),
    _ci(
        274,
        "kirsch",
        "Kirsch",
        "Kirsch",
        "Kirsch",
        "alcohol",
        "spirit",
        unit="EL",
        aliases=["Kirschwasser"],
        tags=["alcohol", "swiss"],
    ),
    # -- Dried Fruit / Misc --
    _ci(
        277,
        "raisin",
        "Rosine",
        "Raisin sec",
        "Raisin",
        "pantry",
        "dried-fruit",
        aliases=["Rosinen", "Sultaninen"],
        tags=["sweet", "dried"],
    ),
    _ci(
        278,
        "date",
        "Dattel",
        "Datte",
        "Date",
        "pantry",
        "dried-fruit",
        aliases=["Datteln", "Medjool-Datteln"],
        tags=["sweet", "dried"],
    ),
    _ci(
        279,
        "dried-apricot",
        "Aprikose getrocknet",
        "Abricot sec",
        "Dried apricot",
        "pantry",
        "dried-fruit",
        aliases=["getrocknete Aprikosen"],
        tags=["sweet", "dried"],
    ),
    # -- Miscellaneous --
    _ci(
        282,
        "breadcrumbs",
        "Paniermehl",
        "Chapelure",
        "Breadcrumbs",
        "pantry",
        "baking",
        aliases=["Semmelbrösel", "Brösmeli"],
        tags=["coating", "baking"],
    ),
    _ci(
        283,
        "tortilla-chips",
        "Tortilla-Chips",
        "Chips de tortilla",
        "Tortilla chips",
        "pantry",
        "snack",
        aliases=["Nachos"],
        tags=["snack", "mexican"],
    ),
    _ci(
        284,
        "dried-tomatoes",
        "Getrocknete Tomaten",
        "Tomates séchées",
        "Sun-dried tomatoes",
        "pantry",
        "preserved",
        aliases=["Tomaten getrocknet"],
        tags=["tomato", "concentrated"],
    ),
    _ci(
        285,
        "coconut-cream",
        "Kokoscreme",
        "Crème de coco",
        "Coconut cream",
        "pantry",
        "canned",
        aliases=["Kokosnusscreme"],
        tags=["coconut", "creamy"],
    ),
    _ci(
        286,
        "curry-paste",
        "Currypaste",
        "Pâte de curry",
        "Curry paste",
        "pantry",
        "condiment",
        unit="EL",
        aliases=["rote Currypaste", "grüne Currypaste", "gelbe Currypaste"],
        tags=["spicy", "thai"],
    ),
    _ci(
        287,
        "harissa",
        "Harissa",
        "Harissa",
        "Harissa",
        "pantry",
        "condiment",
        unit="TL",
        aliases=[],
        tags=["spicy", "north-african"],
    ),
    _ci(
        288,
        "stock-beef",
        "Rindsbouillon",
        "Bouillon de bœuf",
        "Beef stock",
        "pantry",
        "stock",
        unit="dl",
        aliases=["Rindsbrühe", "Fleischbouillon"],
        tags=["umami", "beef"],
    ),
    _ci(
        289,
        "cream-cooking",
        "Kochrahm",
        "Crème de cuisine",
        "Cooking cream",
        "dairy",
        "cream",
        unit="dl",
        aliases=["Kochcreme"],
        tags=["dairy", "cooking"],
    ),
    _ci(
        290,
        "condensed-milk",
        "Kondensmilch",
        "Lait concentré",
        "Condensed milk",
        "dairy",
        "preserved",
        unit="dl",
        aliases=["gezuckerte Kondensmilch"],
        tags=["dairy", "sweet"],
    ),
    # -- Additional Fruit (continued) --
    _ci(
        291,
        "pomegranate",
        "Granatapfel",
        "Grenade",
        "Pomegranate",
        "fruit",
        "tropical",
        unit="pcs",
        aliases=["Granatäpfel"],
        tags=["fruit", "tart"],
    ),
    _ci(
        292,
        "pomegranate-seeds",
        "Granatapfelkerne",
        "Graines de grenade",
        "Pomegranate seeds",
        "fruit",
        "tropical",
        unit="EL",
        aliases=["Granatapfelkernen"],
        tags=["fruit", "tart"],
    ),
    _ci(
        293,
        "fig",
        "Feige",
        "Figue",
        "Fig",
        "fruit",
        "other",
        unit="pcs",
        aliases=["Feigen", "frische Feigen"],
        tags=["fruit", "sweet"],
    ),
    _ci(
        294,
        "kiwi",
        "Kiwi",
        "Kiwi",
        "Kiwi",
        "fruit",
        "tropical",
        unit="pcs",
        aliases=["Kiwis"],
        tags=["fruit", "tart"],
    ),
    _ci(
        295,
        "melon",
        "Melone",
        "Melon",
        "Melon",
        "fruit",
        "melon",
        unit="pcs",
        aliases=["Honigmelone", "Wassermelone", "Cantaloup"],
        tags=["fruit", "sweet"],
    ),
    _ci(
        296,
        "dried-fig",
        "Feige getrocknet",
        "Figue sèche",
        "Dried fig",
        "pantry",
        "dried-fruit",
        aliases=["getrocknete Feigen"],
        tags=["sweet", "dried"],
    ),
    # -- Additional Herbs & Spices (continued) --
    _ci(
        300,
        "saffron",
        "Safran",
        "Safran",
        "Saffron",
        "spice",
        "dried",
        unit="Prise",
        aliases=["Safranfäden"],
        tags=["spice", "floral"],
    ),
    _ci(
        301,
        "clove",
        "Nelke",
        "Clou de girofle",
        "Clove",
        "spice",
        "dried",
        unit="pcs",
        aliases=["Nelken", "Gewürznelken"],
        tags=["spice", "warm"],
    ),
    _ci(
        302,
        "tarragon",
        "Estragon",
        "Estragon",
        "Tarragon",
        "herb",
        "fresh",
        unit="Zweig",
        aliases=[],
        tags=["herb", "anise"],
    ),
    _ci(
        303,
        "marjoram",
        "Majoran",
        "Marjolaine",
        "Marjoram",
        "herb",
        "dried",
        unit="TL",
        aliases=[],
        tags=["herb", "aromatic"],
    ),
    _ci(
        304,
        "lovage",
        "Liebstöckel",
        "Livèche",
        "Lovage",
        "herb",
        "fresh",
        unit="Zweig",
        aliases=["Maggikraut"],
        tags=["herb", "aromatic"],
    ),
    _ci(
        305,
        "chervil",
        "Kerbel",
        "Cerfeuil",
        "Chervil",
        "herb",
        "fresh",
        unit="Bund",
        aliases=[],
        tags=["herb", "delicate"],
    ),
    _ci(
        306,
        "lemongrass",
        "Zitronengras",
        "Citronnelle",
        "Lemongrass",
        "herb",
        "fresh",
        unit="Stange",
        aliases=["Citronella"],
        tags=["herb", "citrus", "asian"],
    ),
    _ci(
        307,
        "galangal",
        "Galgant",
        "Galanga",
        "Galangal",
        "spice",
        "fresh",
        aliases=["Thai-Ingwer"],
        tags=["spice", "aromatic", "asian"],
    ),
    _ci(
        308,
        "juniper-berry",
        "Wacholderbeere",
        "Baie de genièvre",
        "Juniper berry",
        "spice",
        "dried",
        unit="pcs",
        aliases=["Wacholderbeeren"],
        tags=["spice", "piney"],
    ),
    _ci(
        309,
        "fenugreek",
        "Bockshornklee",
        "Fenugrec",
        "Fenugreek",
        "spice",
        "dried",
        unit="TL",
        aliases=[],
        tags=["spice", "bitter"],
    ),
    _ci(
        310,
        "sumac",
        "Sumach",
        "Sumac",
        "Sumac",
        "spice",
        "dried",
        unit="TL",
        aliases=["Sumak"],
        tags=["spice", "tart", "middle-eastern"],
    ),
    _ci(
        311,
        "zaatar",
        "Za'atar",
        "Za'atar",
        "Za'atar",
        "spice",
        "blend",
        unit="TL",
        aliases=["Zatar"],
        tags=["spice", "middle-eastern"],
    ),
    # -- Additional Fish & Seafood (continued) --
    _ci(
        315,
        "perch",
        "Egli",
        "Perche",
        "Perch",
        "fish",
        "freshwater",
        aliases=["Eglifilet", "Flussbarsch"],
        tags=["fish", "freshwater", "swiss"],
    ),
    _ci(
        316,
        "pike-perch",
        "Zander",
        "Sandre",
        "Pike-perch",
        "fish",
        "freshwater",
        aliases=["Zanderfilet"],
        tags=["fish", "freshwater"],
    ),
    _ci(
        317,
        "smoked-salmon",
        "Räucherlachs",
        "Saumon fumé",
        "Smoked salmon",
        "fish",
        "smoked",
        aliases=["Graved Lachs"],
        tags=["fish", "smoked"],
    ),
    _ci(
        318,
        "anchovy",
        "Sardelle",
        "Anchois",
        "Anchovy",
        "fish",
        "preserved",
        aliases=["Sardellen", "Anchovis"],
        tags=["fish", "umami"],
    ),
    _ci(
        319,
        "sardine",
        "Sardine",
        "Sardine",
        "Sardine",
        "fish",
        "oily-fish",
        aliases=["Sardinen"],
        tags=["fish", "oily-fish"],
    ),
    # -- Additional Meat (continued) --
    _ci(
        322,
        "prosciutto",
        "Rohschinken",
        "Prosciutto",
        "Prosciutto",
        "meat",
        "cured",
        aliases=["Prosciutto crudo", "Parmaschinken"],
        tags=["cured", "italian"],
    ),
    _ci(
        323,
        "pancetta",
        "Pancetta",
        "Pancetta",
        "Pancetta",
        "meat",
        "cured",
        aliases=["Würfelpancetta"],
        tags=["cured", "italian"],
    ),
    _ci(
        324,
        "chorizo",
        "Chorizo",
        "Chorizo",
        "Chorizo",
        "meat",
        "sausage",
        aliases=[],
        tags=["sausage", "spicy"],
    ),
    _ci(
        325,
        "veal-escalope",
        "Kalbsschnitzel",
        "Escalope de veau",
        "Veal escalope",
        "meat",
        "veal",
        aliases=["Schnitzel vom Kalb"],
        tags=["veal", "white-meat"],
    ),
    _ci(
        326,
        "beef-stew",
        "Rindsgulasch",
        "Bœuf à braiser",
        "Beef stew meat",
        "meat",
        "beef",
        aliases=["Gulaschfleisch", "Schmorfleisch"],
        tags=["beef", "braising"],
    ),
    _ci(
        327,
        "turkey-breast",
        "Truthahnbrust",
        "Blanc de dinde",
        "Turkey breast",
        "meat",
        "poultry",
        aliases=["Trutenbrust", "Poutrustenbrust", "Truthahn"],
        tags=["poultry", "lean"],
    ),
    # -- Additional Dairy (continued) --
    _ci(
        330,
        "goat-cheese",
        "Ziegenkäse",
        "Fromage de chèvre",
        "Goat cheese",
        "dairy",
        "cheese-soft",
        aliases=["Ziegenfrischkäse", "Chèvre"],
        tags=["cheese", "tangy"],
    ),
    _ci(
        331,
        "blue-cheese",
        "Blauschimmelkäse",
        "Fromage bleu",
        "Blue cheese",
        "dairy",
        "cheese-blue",
        aliases=["Gorgonzola", "Roquefort", "Bleu"],
        tags=["cheese", "pungent"],
    ),
    _ci(
        332,
        "brie",
        "Brie",
        "Brie",
        "Brie",
        "dairy",
        "cheese-soft",
        aliases=["Camembert"],
        tags=["cheese", "creamy"],
    ),
    _ci(
        333,
        "halloumi",
        "Halloumi",
        "Halloumi",
        "Halloumi",
        "dairy",
        "cheese-brined",
        aliases=["Grillkäse"],
        tags=["cheese", "grilling"],
    ),
    _ci(
        334,
        "cheese-sbrinz",
        "Sbrinz",
        "Sbrinz",
        "Sbrinz cheese",
        "dairy",
        "cheese-hard",
        aliases=[],
        tags=["cheese", "alpine", "swiss"],
    ),
    _ci(
        335,
        "ghee",
        "Butterschmalz",
        "Ghee",
        "Ghee",
        "dairy",
        "fat",
        unit="EL",
        aliases=["geklärte Butter", "Bratbutter"],
        tags=["fat", "indian"],
    ),
    # -- Additional Pantry (continued) --
    _ci(
        340,
        "coconut-oil",
        "Kokosöl",
        "Huile de coco",
        "Coconut oil",
        "pantry",
        "oil",
        unit="EL",
        density=0.92,
        aliases=["Kokosfett"],
        tags=["fat", "coconut"],
    ),
    _ci(
        341,
        "rice-vinegar",
        "Reisessig",
        "Vinaigre de riz",
        "Rice vinegar",
        "pantry",
        "acid",
        unit="EL",
        aliases=["Reisweinessig"],
        tags=["acidic", "asian"],
    ),
    _ci(
        342,
        "apple-cider-vinegar",
        "Apfelessig",
        "Vinaigre de cidre",
        "Apple cider vinegar",
        "pantry",
        "acid",
        unit="EL",
        aliases=[],
        tags=["acidic", "natural"],
    ),
    _ci(
        343,
        "agave-syrup",
        "Agavendicksaft",
        "Sirop d'agave",
        "Agave syrup",
        "pantry",
        "sweetener",
        unit="EL",
        aliases=["Agavensirup"],
        tags=["sweet", "natural"],
    ),
    _ci(
        344,
        "coconut-sugar",
        "Kokosblütenzucker",
        "Sucre de coco",
        "Coconut sugar",
        "pantry",
        "sweetener",
        aliases=[],
        tags=["sweet", "natural"],
    ),
    _ci(
        345,
        "preserved-lemon",
        "Salzzitronen",
        "Citrons confits",
        "Preserved lemon",
        "pantry",
        "preserved",
        aliases=["eingelegte Zitronen"],
        tags=["acidic", "north-african"],
    ),
    _ci(
        346,
        "rose-water",
        "Rosenwasser",
        "Eau de rose",
        "Rose water",
        "pantry",
        "flavouring",
        unit="TL",
        aliases=[],
        tags=["floral", "middle-eastern"],
    ),
    _ci(
        347,
        "orange-blossom-water",
        "Orangenblütenwasser",
        "Eau de fleur d'oranger",
        "Orange blossom water",
        "pantry",
        "flavouring",
        unit="TL",
        aliases=[],
        tags=["floral", "aromatic"],
    ),
    _ci(
        348,
        "nori",
        "Nori",
        "Nori",
        "Nori",
        "pantry",
        "seaweed",
        unit="Blatt",
        aliases=["Noriblätter", "Seetang"],
        tags=["umami", "japanese"],
    ),
    _ci(
        349,
        "dried-mushroom",
        "Getrocknete Pilze",
        "Champignons séchés",
        "Dried mushrooms",
        "pantry",
        "dried",
        aliases=["getrocknete Steinpilze", "Shiitake getrocknet", "Morcheln"],
        tags=["umami", "earthy"],
    ),
    _ci(
        350,
        "truffle-oil",
        "Trüffelöl",
        "Huile de truffe",
        "Truffle oil",
        "pantry",
        "oil",
        unit="TL",
        aliases=[],
        tags=["umami", "luxury"],
    ),
    _ci(
        351,
        "kimchi",
        "Kimchi",
        "Kimchi",
        "Kimchi",
        "pantry",
        "fermented",
        aliases=[],
        tags=["fermented", "korean"],
    ),
    _ci(
        352,
        "sauerkraut",
        "Sauerkraut",
        "Choucroute",
        "Sauerkraut",
        "pantry",
        "fermented",
        aliases=["Chabis"],
        tags=["fermented", "german"],
    ),
    # -- Plant-based Proteins --
    _ci(
        355,
        "tempeh",
        "Tempeh",
        "Tempeh",
        "Tempeh",
        "pantry",
        "protein",
        aliases=[],
        tags=["vegan", "protein"],
    ),
    _ci(
        356,
        "seitan",
        "Seitan",
        "Seitan",
        "Seitan",
        "pantry",
        "protein",
        aliases=["Weizeneiweiss"],
        tags=["vegan", "protein"],
    ),
    # -- Plant-based Milks --
    _ci(
        358,
        "oat-milk",
        "Hafermilch",
        "Lait d'avoine",
        "Oat milk",
        "pantry",
        "plant-milk",
        unit="dl",
        aliases=["Haferdrink"],
        tags=["vegan", "dairy-alt"],
    ),
    _ci(
        359,
        "almond-milk",
        "Mandelmilch",
        "Lait d'amande",
        "Almond milk",
        "pantry",
        "plant-milk",
        unit="dl",
        aliases=["Mandeldrink"],
        tags=["vegan", "dairy-alt"],
    ),
    # -- Additional Alcoholic --
    _ci(
        362,
        "rum",
        "Rum",
        "Rhum",
        "Rum",
        "alcohol",
        "spirit",
        unit="EL",
        aliases=["brauner Rum"],
        tags=["alcohol", "sweet"],
    ),
    _ci(
        363,
        "amaretto",
        "Amaretto",
        "Amaretto",
        "Amaretto",
        "alcohol",
        "liqueur",
        unit="EL",
        aliases=[],
        tags=["alcohol", "almond"],
    ),
    _ci(
        364,
        "brandy",
        "Weinbrand",
        "Cognac",
        "Brandy",
        "alcohol",
        "spirit",
        unit="EL",
        aliases=["Cognac"],
        tags=["alcohol", "warming"],
    ),
    _ci(
        365,
        "port-wine",
        "Portwein",
        "Porto",
        "Port wine",
        "alcohol",
        "wine",
        unit="dl",
        aliases=["Port"],
        tags=["alcohol", "sweet"],
    ),
    # -- Additional Legumes --
    _ci(
        368,
        "black-bean",
        "Schwarze Bohne",
        "Haricot noir",
        "Black bean",
        "pantry",
        "legume",
        aliases=["schwarze Bohnen", "Black Beans"],
        tags=["legume", "protein"],
    ),
    _ci(
        369,
        "mung-bean",
        "Mungbohne",
        "Haricot mungo",
        "Mung bean",
        "pantry",
        "legume",
        aliases=["Mungobohnen", "Mungbohnen"],
        tags=["legume", "asian"],
    ),
    # -- Additional Breads & Wrappers --
    _ci(
        372,
        "pita",
        "Pitabrot",
        "Pain pita",
        "Pita bread",
        "bakery",
        "baked",
        unit="pcs",
        aliases=["Pita", "Fladenbrot"],
        tags=["bread", "middle-eastern"],
    ),
    _ci(
        373,
        "naan",
        "Naan",
        "Naan",
        "Naan bread",
        "bakery",
        "baked",
        unit="pcs",
        aliases=["Naanbrot"],
        tags=["bread", "indian"],
    ),
    _ci(
        374,
        "ciabatta",
        "Ciabatta",
        "Ciabatta",
        "Ciabatta",
        "bakery",
        "baked",
        unit="pcs",
        aliases=[],
        tags=["bread", "italian"],
    ),
    _ci(
        375,
        "croissant",
        "Gipfeli",
        "Croissant",
        "Croissant",
        "bakery",
        "baked",
        unit="pcs",
        aliases=["Croissant"],
        tags=["baking", "swiss"],
    ),
    # -- Additional Vegetables (continued) --
    _ci(
        378,
        "kale",
        "Federkohl",
        "Chou frisé",
        "Kale",
        "vegetable",
        "brassica",
        aliases=["Grünkohl"],
        tags=["brassica", "green"],
    ),
    _ci(
        379,
        "turnip",
        "Räbe",
        "Navet",
        "Turnip",
        "vegetable",
        "root",
        aliases=["Herbstrübe", "weisse Rübe"],
        tags=["root-veg"],
    ),
    _ci(
        380,
        "parsnip",
        "Pastinake",
        "Panais",
        "Parsnip",
        "vegetable",
        "root",
        aliases=["Pastinaken"],
        tags=["root-veg", "sweet"],
    ),
    _ci(
        381,
        "watercress",
        "Brunnenkresse",
        "Cresson",
        "Watercress",
        "vegetable",
        "leaf",
        aliases=["Kresse"],
        tags=["peppery", "green"],
    ),
    _ci(
        382,
        "endive",
        "Endivie",
        "Endive",
        "Endive",
        "vegetable",
        "leaf",
        aliases=["Frisée"],
        tags=["bitter", "leaf"],
    ),
    _ci(
        383,
        "sorrel",
        "Sauerampfer",
        "Oseille",
        "Sorrel",
        "vegetable",
        "leaf",
        aliases=[],
        tags=["acidic", "leaf"],
    ),
    _ci(
        384,
        "okra",
        "Okra",
        "Gombo",
        "Okra",
        "vegetable",
        "fruit-veg",
        aliases=["Okraschoten"],
        tags=["african", "thickener"],
    ),
    _ci(
        385,
        "bamboo-shoots",
        "Bambussprossen",
        "Pousses de bambou",
        "Bamboo shoots",
        "vegetable",
        "shoot",
        aliases=[],
        tags=["asian", "crunchy"],
    ),
    _ci(
        386,
        "bean-sprouts",
        "Sojasprossen",
        "Germes de soja",
        "Bean sprouts",
        "vegetable",
        "sprout",
        aliases=["Mungbohnensprossen"],
        tags=["asian", "crunchy"],
    ),
]

# Public alias — documented name in the specification
CATALOGUE = SEED_CATALOGUE


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


# ---------------------------------------------------------------------------
# Adjective stripping — German qualifiers commonly preceding ingredient names
# ---------------------------------------------------------------------------

_ADJECTIVES_DE: list[str] = [
    "mehlig kochende",
    "mehligkochende",
    "festkochende",
    "fest kochende",
    "vorwiegend festkochende",
    "tiefgekuhlte",
    "tiefgekühlte",
    "tiefgefrorene",
    "aufgetaute",
    "frische",
    "frischer",
    "frisches",
    "frischem",
    "frischen",
    "getrocknete",
    "getrockneter",
    "getrocknetes",
    "geriebene",
    "geriebener",
    "geriebenes",
    "geriebenem",
    "gehackte",
    "gehackter",
    "gehacktes",
    "fein gehackte",
    "fein gehackter",
    "grob gehackte",
    "grob gehackter",
    "geschnittene",
    "geschnittener",
    "klein geschnittene",
    "fein geschnittene",
    "grobe",
    "grober",
    "grobes",
    "feine",
    "feiner",
    "feines",
    "feinem",
    "kleine",
    "kleiner",
    "kleines",
    "grosse",
    "grosser",
    "grosses",
    "große",
    "großer",
    "großes",
    "weiche",
    "weicher",
    "weiches",
    "harte",
    "harter",
    "hartes",
    "reife",
    "reifer",
    "reifes",
    "reifen",
    "unreife",
    "kalte",
    "kalter",
    "kaltes",
    "warme",
    "warmer",
    "warmes",
    "heisse",
    "heisser",
    "heisses",
    "ungekochte",
    "ungekochter",
    "vorgekochte",
    "vorgekochter",
    "eingeweichte",
    "eingeweichter",
    "abgetropfte",
    "abgetropfter",
    "geröstete",
    "gerösteter",
    "geröstetes",
    "ungesalzene",
    "ungesalzener",
    "gesalzene",
    "gesalzener",
    "eingelegte",
    "eingelegter",
    "marinierte",
    "marinierter",
    "gewürfelte",
    "gewürfelter",
    "geschälte",
    "geschälter",
    "entsteinte",
    "entsteinter",
    "halbierte",
    "halbierter",
    "geviertelte",
    "geviertelter",
    "ganze",
    "ganzer",
    "ganzes",
    "halbe",
    "halber",
    "halbes",
    "Bio-",
    "bio",
    "unbehandelte",
    "unbehandelter",
    "dünne",
    "dünner",
    "dünnes",
    "dicke",
    "dicker",
    "dickes",
    "mittlere",
    "mittlerer",
    "mittleres",
    "mehlige",
    "weisse",
    "weisser",
    "rote",
    "roter",
    "rotes",
    "rotem",
    "gelbe",
    "gelber",
    "gelbes",
    "grüne",
    "grüner",
    "grünes",
    "schwarze",
    "schwarzer",
    "schwarzes",
    "braune",
    "brauner",
    "braunes",
]

# Sort by length descending so longer prefixes match first
_ADJECTIVES_NORMALISED: list[str] = sorted(
    [_normalise(adj) for adj in _ADJECTIVES_DE],
    key=len,
    reverse=True,
)

# German plural suffixes to try stripping (ordered by specificity)
_PLURAL_SUFFIXES: list[str] = ["eln", "ien", "en", "er", "es", "el", "n", "e", "s"]


def _strip_adjectives(normalised_text: str) -> str:
    """Strip common German adjectives/qualifiers from the beginning of an ingredient name.

    Examples:
        >>> _strip_adjectives("mehlig kochende kartoffeln")
        'kartoffeln'
        >>> _strip_adjectives("frische petersilie")
        'petersilie'
        >>> _strip_adjectives("pouletbrust")
        'pouletbrust'
    """
    text = normalised_text
    changed = True
    while changed:
        changed = False
        for adj in _ADJECTIVES_NORMALISED:
            if text.startswith(adj + " "):
                text = text[len(adj) + 1 :].lstrip()
                changed = True
                break
            if text.startswith(adj) and adj.endswith("-"):
                text = text[len(adj) :].lstrip()
                changed = True
                break
    return text


# ---------------------------------------------------------------------------
# French article/preposition stripping
# ---------------------------------------------------------------------------

# French quantity phrases that precede the ingredient name (normalised form)
_FRENCH_QUANTITY_PHRASES: list[str] = sorted(
    [
        _normalise(p)
        for p in [
            "un peu de",
            "un peu d'",
            "une pincée de",
            "une pincée d'",
            "quelques",
            "un brin de",
            "un brin d'",
            "un filet de",
            "un filet d'",
            "une poignée de",
            "une poignée d'",
            "une noisette de",
            "une noisette d'",
            "une noix de",
            "une noix d'",
            "un trait de",
            "un trait d'",
            "un soupçon de",
            "un soupcon de",
            "un morceau de",
            "un morceau d'",
            "une tranche de",
            "une tranche d'",
            "une gousse de",
            "une gousse d'",
            "une feuille de",
            "une feuille d'",
            "une branche de",
            "une branche d'",
            "un bouquet de",
            "un bouquet d'",
        ]
    ],
    key=len,
    reverse=True,
)

# French articles and prepositions (normalised) — sorted longest first
_FRENCH_ARTICLES: list[str] = sorted(
    [
        _normalise(a)
        for a in [
            "de la",
            "de l'",
            "du",
            "des",
            "de",
            "d'",
            "le",
            "la",
            "l'",
            "les",
            "un",
            "une",
        ]
    ],
    key=len,
    reverse=True,
)

# Common French adjectives in recipe ingredient lines
_ADJECTIVES_FR: list[str] = [
    "frais",
    "fraîche",
    "fraîches",
    "frais",
    "haché",
    "hachée",
    "hachés",
    "hachées",
    "finement haché",
    "finement hachée",
    "coupé",
    "coupée",
    "coupés",
    "coupées",
    "émincé",
    "émincée",
    "émincés",
    "émincées",
    "râpé",
    "râpée",
    "râpés",
    "râpées",
    "moulu",
    "moulue",
    "moulus",
    "moulues",
    "séché",
    "séchée",
    "séchés",
    "séchées",
    "surgelé",
    "surgelée",
    "surgelés",
    "surgelées",
    "pelé",
    "pelée",
    "pelés",
    "pelées",
    "cuit",
    "cuite",
    "cuits",
    "cuites",
    "gros",
    "grosse",
    "grosses",
    "petit",
    "petite",
    "petites",
    "petits",
    "grand",
    "grande",
    "grandes",
    "grands",
    "blanc",
    "blanche",
    "blanches",
    "blancs",
    "rouge",
    "rouges",
    "vert",
    "verte",
    "vertes",
    "verts",
    "noir",
    "noire",
    "noires",
    "noirs",
    "doux",
    "douce",
    "douces",
    "long",
    "longue",
    "longues",
    "longs",
    "fin",
    "fine",
    "fines",
    "fins",
    "tiède",
    "tièdes",
    "chaud",
    "chaude",
    "chaudes",
    "chauds",
    "froid",
    "froide",
    "froides",
    "froids",
    "entier",
    "entière",
    "entières",
    "entiers",
    "bio",
]

_ADJECTIVES_FR_NORMALISED: list[str] = sorted(
    [_normalise(adj) for adj in _ADJECTIVES_FR],
    key=len,
    reverse=True,
)


def _strip_french_context(normalised_text: str) -> str:
    """Strip French quantity phrases, articles, and prepositions from ingredient text.

    Handles patterns like:
    - "un peu de poivre" → "poivre"
    - "d'huile d'olive" → "huile d'olive" (preserves internal d')
    - "du beurre" → "beurre"
    - "de la farine" → "farine"

    Examples:
        >>> _strip_french_context("un peu de poivre")
        'poivre'
        >>> _strip_french_context("du beurre")
        'beurre'
        >>> _strip_french_context("de la farine")
        'farine'
    """
    text = normalised_text

    # Step 1: strip full quantity phrases first (longest match)
    for phrase in _FRENCH_QUANTITY_PHRASES:
        if text.startswith(phrase):
            remainder = text[len(phrase) :].lstrip()
            if remainder:
                text = remainder
                break

    # Step 2: strip leading articles/prepositions
    changed = True
    while changed:
        changed = False
        for art in _FRENCH_ARTICLES:
            if text.startswith(art + " "):
                text = text[len(art) + 1 :].lstrip()
                changed = True
                break
            # Handle elided forms (d', l') — no space after
            if art.endswith("'") and text.startswith(art):
                text = text[len(art) :].lstrip()
                changed = True
                break

    return text


def _strip_french_adjectives(normalised_text: str) -> str:
    """Strip common French adjectives from ingredient text.

    Handles both leading and trailing adjectives (French adjectives often follow
    the noun, but in recipes they sometimes precede it).

    Examples:
        >>> _strip_french_adjectives("poivre noir")
        'poivre'
        >>> _strip_french_adjectives("petit oignon")
        'oignon'
    """
    text = normalised_text

    # Strip leading adjectives
    changed = True
    while changed:
        changed = False
        for adj in _ADJECTIVES_FR_NORMALISED:
            if text.startswith(adj + " "):
                text = text[len(adj) + 1 :].lstrip()
                changed = True
                break

    # Strip trailing adjectives (common in French: "poivre noir", "sel fin")
    changed = True
    while changed:
        changed = False
        for adj in _ADJECTIVES_FR_NORMALISED:
            if text.endswith(" " + adj):
                text = text[: -(len(adj) + 1)].rstrip()
                changed = True
                break

    return text


def _depluralize_french(word: str) -> list[str]:
    """Generate singular candidates from a French plural form.

    French plurals are typically formed by adding -s or -x.

    Examples:
        >>> 'oignon' in _depluralize_french('oignons')
        True
        >>> 'chou' in _depluralize_french('choux')
        True
    """
    candidates = []
    if word.endswith("s") and len(word) > 3:
        candidates.append(word[:-1])
    if word.endswith("x") and len(word) > 3:
        candidates.append(word[:-1])
    # -aux → -al (e.g. animaux → animal)
    if word.endswith("aux") and len(word) > 4:
        candidates.append(word[:-3] + "al")
    return candidates


def _depluralize(word: str) -> list[str]:
    """Generate singular candidates from a German plural form.

    Returns a list of possible singular forms (may include the original).

    Examples:
        >>> 'kartoffel' in _depluralize('kartoffeln')
        True
        >>> 'cervelat' in _depluralize('cervelats')
        True
    """
    candidates = []
    for suffix in _PLURAL_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            candidates.append(word[: -len(suffix)])
    return candidates


_INDEX: dict[str, str] = _build_index(SEED_CATALOGUE)
_CATALOGUE_BY_KEY: dict[str, CanonicalIngredient] = {item.key: item for item in SEED_CATALOGUE}
_CATALOGUE_BY_ID: dict[int, CanonicalIngredient] = {item.id: item for item in SEED_CATALOGUE}


def get_canonical_ingredient_by_id(ingredient_id: int) -> CanonicalIngredient | None:
    """Return the canonical ingredient for the given ID, or None."""
    return _CATALOGUE_BY_ID.get(ingredient_id)


# ---------------------------------------------------------------------------
# Quantity / unit stripping
# ---------------------------------------------------------------------------

# Matches leading quantity+unit patterns like "200g", "200 g", "1.5 kg",
# "½ dl", "2½ EL", fractional quantities, and range patterns ("2-3").
# Includes German units (EL, TL, Prise, etc.) and French units (c.s., c.c., pincée, etc.)
_QUANTITY_UNIT_RE = re.compile(
    r"^\s*"
    r"(?:\d+(?:[.,]\d+)?\s*)?"  # optional whole number
    r"(?:[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]\s*)?"  # optional unicode fraction
    r"(?:[-–/]\s*\d+(?:[.,]\d+)?\s*)?"  # optional range end
    r"(?:g|kg|ml|cl|dl|l|el|tl|msp|prise|prisen|bund"
    r"|stück|stk|scheibe|scheiben|blatt|blätter"
    r"|zweig|zweige|zehe|zehen|dose|dosen"
    r"|becher|packung|pkg|tropfen|tasse|tassen"
    # French units
    r"|c\.s\.|c\.c\.|cs|cc|pincee|pincées?|gouttes?"
    r"|tranche|tranches|bouquet|sachet|sachets"
    r"|paquet|paquets|boite|boîte|pot|pots"
    r"|branche|branches|feuille|feuilles"
    r"|gousse|gousses|morceau|morceaux)"
    r"(?:\.)?"  # optional trailing dot
    r"\s+",
    re.IGNORECASE | re.UNICODE,
)


def _strip_quantity_unit(text: str) -> str:
    """Strip a leading quantity+unit prefix from ingredient text.

    Examples:
        >>> _strip_quantity_unit('200g butter')
        'butter'
        >>> _strip_quantity_unit('200 g butter')
        'butter'
        >>> _strip_quantity_unit('butter')
        'butter'
    """
    result = _QUANTITY_UNIT_RE.sub("", text).strip()
    return result if result else text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalise_ingredient(raw_name: str) -> str | None:
    """Look up a raw ingredient name and return its canonical key.

    Matching strategy (applied in order):
    1. Exact match on normalised name (display names + aliases)
    2. Strip adjectives/qualifiers, then exact match
    3. Depluralize (try removing common German plural suffixes)
    4. Strip adjectives + depluralize
    5. Strip leading quantity+unit prefix, then retry strategies 1-4

    Args:
        raw_name: Raw ingredient text, e.g. "Pouletbrust", "Zwiebeln",
            or "200g Butter".

    Returns:
        Canonical key like "chicken-breast", or None if unresolved.

    Examples:
        >>> normalise_ingredient("Pouletbrust")
        'chicken-breast'
        >>> normalise_ingredient("Zwiebeln")
        'onion'
        >>> normalise_ingredient("mehlig kochende Kartoffeln")
        'potato'
        >>> normalise_ingredient("200g Butter")
        'butter'
        >>> normalise_ingredient("Xylophon")
    """
    normalised = _normalise(raw_name)
    if not normalised:
        return None

    result = _match_normalised(normalised)
    if result:
        return result

    # Strategy 5: strip quantity+unit prefix from raw text (before NFKD
    # decomposition mangles unicode fractions), then normalise and retry.
    raw_stripped = _strip_quantity_unit(raw_name.strip().lower())
    if raw_stripped != raw_name.strip().lower():
        stripped_normalised = _normalise(raw_stripped)
        if stripped_normalised and stripped_normalised != normalised:
            result = _match_normalised(stripped_normalised)
            if result:
                return result

    return None


def _match_normalised(normalised: str) -> str | None:
    """Try all matching strategies on already-normalised text."""
    # Strategy 1: exact match
    result = _INDEX.get(normalised)
    if result:
        return result

    # Strategy 2: strip German adjectives then match
    stripped = _strip_adjectives(normalised)
    if stripped != normalised:
        result = _INDEX.get(stripped)
        if result:
            return result

    # Strategy 3: depluralize (German) on original normalised text
    for candidate in _depluralize(normalised):
        result = _INDEX.get(candidate)
        if result:
            return result

    # Strategy 4: strip German adjectives + depluralize
    if stripped != normalised:
        for candidate in _depluralize(stripped):
            result = _INDEX.get(candidate)
            if result:
                return result

    # Strategy 5: French context stripping (articles, prepositions, quantity phrases)
    fr_stripped = _strip_french_context(normalised)
    if fr_stripped != normalised:
        result = _INDEX.get(fr_stripped)
        if result:
            return result

        # Strategy 5a: French context + French adjective stripping
        fr_adj_stripped = _strip_french_adjectives(fr_stripped)
        if fr_adj_stripped != fr_stripped:
            result = _INDEX.get(fr_adj_stripped)
            if result:
                return result

        # Strategy 5b: French context + French depluralize
        for candidate in _depluralize_french(fr_stripped):
            result = _INDEX.get(candidate)
            if result:
                return result

        # Strategy 5c: French context + adjective strip + depluralize
        if fr_adj_stripped != fr_stripped:
            for candidate in _depluralize_french(fr_adj_stripped):
                result = _INDEX.get(candidate)
                if result:
                    return result

    # Strategy 6: French adjective stripping on original (without context strip)
    fr_adj_only = _strip_french_adjectives(normalised)
    if fr_adj_only != normalised and fr_adj_only != fr_stripped:
        result = _INDEX.get(fr_adj_only)
        if result:
            return result

        for candidate in _depluralize_french(fr_adj_only):
            result = _INDEX.get(candidate)
            if result:
                return result

    # Strategy 7: French depluralize on original
    for candidate in _depluralize_french(normalised):
        result = _INDEX.get(candidate)
        if result:
            return result

    return None


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
