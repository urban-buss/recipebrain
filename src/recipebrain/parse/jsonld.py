"""Generic JSON-LD recipe parser using extruct.

Extracts schema.org Recipe objects from HTML pages and converts them
to RawRecipe dataclass instances. This is the primary parsing strategy —
per-site HTML overrides are only added when JSON-LD is missing.

Examples:
    >>> html = '<script type="application/ld+json">{"@type":"Recipe","name":"Test"}</script>'
    >>> recipes = extract_recipes(html)
    >>> recipes[0]["name"]
    'Test'
"""

from __future__ import annotations

import extruct

from recipebrain.sources.base import RawRecipe


def extract_recipes(html: str, base_url: str = "") -> list[dict]:
    """Extract schema.org Recipe objects from HTML via JSON-LD.

    Returns a list of dicts, each representing a Recipe JSON-LD object.
    Returns an empty list if no Recipe JSON-LD is found.
    """
    try:
        data = extruct.extract(html, base_url=base_url, syntaxes=["json-ld"])
    except Exception:
        return []

    recipes: list[dict] = []
    for item in data.get("json-ld", []):
        if isinstance(item, dict):
            if item.get("@type") == "Recipe":
                recipes.append(item)
            # Handle @graph wrapper (some sites nest recipes inside a graph)
            elif "@graph" in item:
                for node in item["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "Recipe":
                        recipes.append(node)

    return recipes


def parse_recipe(data: dict, source_url: str = "", language: str = "de") -> RawRecipe:
    """Convert a schema.org Recipe JSON-LD dict to a RawRecipe.

    Raises ValueError if the required 'name' field is missing.
    """
    title = data.get("name", "").strip()
    if not title:
        raise ValueError("Recipe JSON-LD missing required 'name' field")

    return RawRecipe(
        title=title,
        description=data.get("description", "").strip(),
        ingredients_raw=_extract_ingredients(data.get("recipeIngredient")),
        steps_raw=_extract_instructions(data.get("recipeInstructions")),
        yield_amount=_extract_yield(data.get("recipeYield")),
        prep_time=data.get("prepTime", "") or "",
        cook_time=data.get("cookTime", "") or "",
        image_urls=_extract_images(data.get("image")),
        keywords=_extract_keywords(data.get("keywords")),
        source_url=source_url,
        language=language,
        category=_extract_first_string(data.get("recipeCategory")),
        cuisine=_extract_first_string(data.get("recipeCuisine")),
    )


def _extract_ingredients(raw: list | str | None) -> list[str]:
    """Extract ingredient list from recipeIngredient field.

    Examples:
        >>> _extract_ingredients(["200 g flour", "3 eggs"])
        ['200 g flour', '3 eggs']
        >>> _extract_ingredients(None)
        []
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.split("\n") if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _extract_instructions(raw: list | str | None) -> list[str]:
    """Extract step text from recipeInstructions.

    Handles both plain string lists and HowToStep/HowToSection objects.

    Examples:
        >>> _extract_instructions([{"@type": "HowToStep", "text": "Preheat oven."}])
        ['Preheat oven.']
        >>> _extract_instructions(["Step 1", "Step 2"])
        ['Step 1', 'Step 2']
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.split("\n") if line.strip()]
    if not isinstance(raw, list):
        return []

    steps: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                steps.append(text)
        elif isinstance(item, dict):
            item_type = item.get("@type", "")
            if item_type == "HowToStep":
                text = item.get("text", "").strip()
                if text:
                    steps.append(text)
            elif item_type == "HowToSection":
                # Recurse into section items
                section_steps = _extract_instructions(item.get("itemListElement"))
                steps.extend(section_steps)
    return steps


def _extract_yield(raw: str | list | int | None) -> str:
    """Extract yield/servings as a string.

    Examples:
        >>> _extract_yield("4 Portionen")
        '4 Portionen'
        >>> _extract_yield(["4 servings"])
        '4 servings'
        >>> _extract_yield(4)
        '4'
    """
    if raw is None:
        return ""
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, list):
        return str(raw[0]).strip() if raw else ""
    return str(raw).strip()


def _extract_images(raw: str | list | dict | None) -> list[str]:
    """Extract image URLs from the image field.

    Examples:
        >>> _extract_images("https://example.com/img.jpg")
        ['https://example.com/img.jpg']
        >>> _extract_images({"url": "https://example.com/img.jpg"})
        ['https://example.com/img.jpg']
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, dict):
        url = raw.get("url", "")
        return [url] if url else []
    if isinstance(raw, list):
        urls: list[str] = []
        for item in raw:
            if isinstance(item, str) and item:
                urls.append(item)
            elif isinstance(item, dict):
                url = item.get("url", "")
                if url:
                    urls.append(url)
        return urls
    return []


def _extract_keywords(raw: str | list | None) -> list[str]:
    """Extract keywords as a list of strings.

    Examples:
        >>> _extract_keywords("quick, easy, pasta")
        ['quick', 'easy', 'pasta']
        >>> _extract_keywords(["quick", "easy"])
        ['quick', 'easy']
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [kw.strip() for kw in raw.split(",") if kw.strip()]
    if isinstance(raw, list):
        return [str(kw).strip() for kw in raw if str(kw).strip()]
    return []


def _extract_first_string(raw: str | list | None) -> str:
    """Extract a single string value from a field that may be a string or list.

    Some sites encode recipeCategory/recipeCuisine as arrays.

    Examples:
        >>> _extract_first_string("Hauptgericht")
        'Hauptgericht'
        >>> _extract_first_string(["Hauptgericht", "Mittagessen"])
        'Hauptgericht'
        >>> _extract_first_string(None)
        ''
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list) and raw:
        return str(raw[0]).strip()
    return ""
