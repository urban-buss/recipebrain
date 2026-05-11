"""Recommend easy / quick recipes for weeknight cooking.

Filters the recipe catalogue by time, ingredient count, and difficulty,
then sorts by a composite score favouring speed, simplicity, and freshness
(not recently cooked).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from recipebrain.query import execute_query


def suggest_easy(
    output_dir: Path,
    *,
    max_total_minutes: int = 30,
    max_ingredients: int = 8,
    avoid_recent_days: int = 14,
    limit: int = 5,
) -> list[dict]:
    """Return easy recipe suggestions ranked by simplicity and freshness.

    Applies three hard filters then scores remaining candidates:
    1. ``total_minutes <= max_total_minutes``
    2. ingredient count ``<= max_ingredients``
    3. not cooked within ``avoid_recent_days`` (soft: still included at lower rank)

    Score = speed_score + simplicity_score + freshness_bonus

    Args:
        output_dir: Path to Parquet datasets.
        max_total_minutes: Maximum total cooking time in minutes.
        max_ingredients: Maximum number of ingredients.
        avoid_recent_days: Days since last cook to get a freshness bonus.
        limit: Maximum number of results.

    Returns:
        List of recipe dicts with keys: id, title, total_minutes,
        difficulty, ingredient_count, last_cooked_at, score.

    Examples:
        >>> results = suggest_easy(Path("output"), max_total_minutes=20, limit=3)
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=avoid_recent_days)
    cutoff_iso = cutoff.isoformat()

    sql = (
        "SELECT r.id, r.title, r.total_minutes, r.difficulty, "
        "       r.last_cooked_at, r.owner_rating, "
        "       COUNT(ri.recipe_id) AS ingredient_count "
        "FROM recipes r "
        "LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id "
        f"WHERE r.total_minutes <= {int(max_total_minutes)} "
        "  AND r.status = 'active' "
        "GROUP BY r.id, r.title, r.total_minutes, r.difficulty, "
        "         r.last_cooked_at, r.owner_rating "
        f"HAVING COUNT(ri.recipe_id) <= {int(max_ingredients)} "
        f"LIMIT {int(limit) * 5}"
    )

    rows = execute_query(sql, output_dir)

    scored: list[dict] = []
    for row in rows:
        total = row.get("total_minutes") or max_total_minutes
        ing_count = row.get("ingredient_count", 0)

        # Speed score: faster is better (0..1)
        speed_score = max(0.0, 1.0 - total / max_total_minutes) if max_total_minutes else 0.0

        # Simplicity score: fewer ingredients is better (0..1)
        simplicity_score = max(0.0, 1.0 - ing_count / max_ingredients) if max_ingredients else 0.0

        # Freshness bonus: not recently cooked gets a bonus
        freshness_bonus = 0.0
        last_cooked = row.get("last_cooked_at")
        if last_cooked is None:
            freshness_bonus = 0.5
        elif str(last_cooked) < cutoff_iso:
            freshness_bonus = 0.3

        # Difficulty bonus
        diff_bonus = {"easy": 0.2, "medium": 0.0, "advanced": -0.2}.get(
            row.get("difficulty", ""), 0.0
        )

        score = round(speed_score + simplicity_score + freshness_bonus + diff_bonus, 3)

        scored.append(
            {
                "id": row["id"],
                "title": row["title"],
                "total_minutes": row.get("total_minutes"),
                "difficulty": row.get("difficulty"),
                "ingredient_count": ing_count,
                "last_cooked_at": row.get("last_cooked_at"),
                "score": score,
            }
        )

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]
