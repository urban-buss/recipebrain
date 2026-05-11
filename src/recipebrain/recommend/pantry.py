"""Recommend recipes based on pantry coverage.

Ranks recipes by the fraction of their ingredients currently available in
the user's pantry, optionally supplemented with ad-hoc extra ingredients.
Pantry staples (salt, pepper, oil, etc.) are assumed always present and
excluded from the coverage denominator.
"""

from __future__ import annotations

from pathlib import Path

from recipebrain.query import execute_query

# Ingredients assumed always available — excluded from coverage calculation
PANTRY_STAPLES: frozenset[str] = frozenset(
    {
        "salt",
        "pepper",
        "black-pepper",
        "olive-oil",
        "sunflower-oil",
        "rapeseed-oil",
        "water",
        "sugar",
        "flour",
        "butter",
    }
)


def suggest_for_pantry(
    output_dir: Path,
    *,
    extra_ingredients: list[str] | None = None,
    missing_ok: int = 2,
    max_total_minutes: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return recipes ranked by pantry ingredient coverage.

    Coverage = (ingredients in pantry ∪ extras ∪ staples) / total ingredients.
    Recipes with more missing ingredients than ``missing_ok`` are excluded.

    Args:
        output_dir: Path to Parquet datasets.
        extra_ingredients: Ad-hoc ingredient keys the user has on hand.
        missing_ok: Maximum number of non-staple missing ingredients tolerated.
        max_total_minutes: Optional time filter.
        limit: Maximum results.

    Returns:
        List of recipe dicts with keys: id, title, total_minutes,
        ingredient_count, covered, missing, coverage_score, score.

    Examples:
        >>> results = suggest_for_pantry(
        ...     Path("output"), extra_ingredients=["chicken-breast"], limit=3
        ... )
    """
    extras = set(extra_ingredients or [])

    # Load pantry ingredient keys
    pantry_keys = _load_pantry_keys(output_dir)
    available = pantry_keys | extras | PANTRY_STAPLES

    # Load recipes with their ingredient keys
    time_filter = ""
    if max_total_minutes is not None:
        time_filter = f" AND r.total_minutes <= {int(max_total_minutes)}"

    sql = (
        "SELECT r.id, r.title, r.total_minutes, r.difficulty "
        "FROM recipes r "
        f"WHERE r.status = 'active'{time_filter} "
        f"LIMIT {int(limit) * 20}"
    )
    recipes = execute_query(sql, output_dir)

    if not recipes:
        return []

    recipe_ids = [r["id"] for r in recipes]
    recipe_map = {r["id"]: r for r in recipes}

    # Fetch ingredient links for candidate recipes
    ingredients_by_recipe = _load_recipe_ingredients(output_dir, recipe_ids)

    scored: list[dict] = []
    for rid, ings in ingredients_by_recipe.items():
        if rid not in recipe_map:
            continue

        recipe = recipe_map[rid]
        total = len(ings)
        if total == 0:
            continue

        covered = 0
        missing_list: list[str] = []
        for ing_key in ings:
            if ing_key in available:
                covered += 1
            else:
                missing_list.append(ing_key)

        missing = len(missing_list)
        if missing > missing_ok:
            continue

        coverage_score = round(covered / total, 3) if total > 0 else 0.0

        # Bonus for fewer missing ingredients
        missing_penalty = missing * 0.1
        score = round(coverage_score - missing_penalty, 3)

        scored.append(
            {
                "id": rid,
                "title": recipe["title"],
                "total_minutes": recipe.get("total_minutes"),
                "ingredient_count": total,
                "covered": covered,
                "missing": missing,
                "missing_ingredients": missing_list,
                "coverage_score": coverage_score,
                "score": score,
            }
        )

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def _load_pantry_keys(output_dir: Path) -> set[str]:
    """Load ingredient keys currently in the pantry."""
    pantry_path = output_dir / "pantry.parquet"
    if not pantry_path.exists():
        return set()

    sql = "SELECT i.key FROM pantry p JOIN ingredients i ON i.id = p.ingredient_id"
    try:
        rows = execute_query(sql, output_dir)
        return {r["key"] for r in rows if r.get("key")}
    except Exception:  # noqa: BLE001
        return set()


def _load_recipe_ingredients(output_dir: Path, recipe_ids: list[int]) -> dict[int, list[str]]:
    """Load ingredient keys per recipe for a set of recipe IDs."""
    if not recipe_ids:
        return {}

    id_list = ", ".join(str(int(rid)) for rid in recipe_ids)
    sql = (
        "SELECT ri.recipe_id, "
        "       COALESCE(i.key, LOWER(ri.raw_text)) AS ing_key "
        "FROM recipe_ingredients ri "
        "LEFT JOIN ingredients i ON i.id = ri.ingredient_id "
        f"WHERE ri.recipe_id IN ({id_list}) "
        "ORDER BY ri.recipe_id, ri.seq"
    )
    rows = execute_query(sql, output_dir)

    result: dict[int, list[str]] = {}
    for row in rows:
        rid = row["recipe_id"]
        key = row.get("ing_key", "")
        if key:
            result.setdefault(rid, []).append(key)
    return result
