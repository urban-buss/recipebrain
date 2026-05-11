"""Cooking frequency and churn analysis.

Provides weekly and monthly cooking trend data from the cook_log,
similar to cellarbrain's cellar_churn analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recipebrain.query import execute_query


@dataclass(frozen=True)
class CookingTrend:
    """A single period's cooking statistics."""

    period: str
    cook_count: int
    unique_recipes: int


def weekly_trends(output_dir: Path, *, weeks: int = 12) -> list[CookingTrend]:
    """Return weekly cooking frequency for the last *weeks* weeks.

    Args:
        output_dir: Path to Parquet datasets.
        weeks: Number of weeks to look back (default 12).

    Returns:
        List of CookingTrend ordered chronologically (oldest first).
    """
    sql = (
        "SELECT strftime(cooked_on, '%Y-W%W') AS period, "
        "       COUNT(*) AS cook_count, "
        "       COUNT(DISTINCT recipe_id) AS unique_recipes "
        "FROM cook_log "
        f"WHERE cooked_on >= CURRENT_DATE - INTERVAL '{int(weeks)} weeks' "
        "GROUP BY period ORDER BY period"
    )
    rows = execute_query(sql, output_dir)
    return [
        CookingTrend(
            period=r["period"],
            cook_count=r["cook_count"],
            unique_recipes=r["unique_recipes"],
        )
        for r in rows
    ]


def monthly_trends(output_dir: Path, *, months: int = 6) -> list[CookingTrend]:
    """Return monthly cooking frequency for the last *months* months.

    Args:
        output_dir: Path to Parquet datasets.
        months: Number of months to look back (default 6).

    Returns:
        List of CookingTrend ordered chronologically (oldest first).
    """
    sql = (
        "SELECT strftime(cooked_on, '%Y-%m') AS period, "
        "       COUNT(*) AS cook_count, "
        "       COUNT(DISTINCT recipe_id) AS unique_recipes "
        "FROM cook_log "
        f"WHERE cooked_on >= CURRENT_DATE - INTERVAL '{int(months)} months' "
        "GROUP BY period ORDER BY period"
    )
    rows = execute_query(sql, output_dir)
    return [
        CookingTrend(
            period=r["period"],
            cook_count=r["cook_count"],
            unique_recipes=r["unique_recipes"],
        )
        for r in rows
    ]


def top_recipes(output_dir: Path, *, limit: int = 10) -> list[dict]:
    """Return the most frequently cooked recipes.

    Args:
        output_dir: Path to Parquet datasets.
        limit: Maximum number of results.

    Returns:
        List of dicts with keys: recipe_id, title, cook_count, last_cooked.
    """
    sql = (
        "SELECT cl.recipe_id, r.title, "
        "       COUNT(*) AS cook_count, "
        "       MAX(cl.cooked_on) AS last_cooked "
        "FROM cook_log cl "
        "LEFT JOIN recipes r ON cl.recipe_id = r.id "
        "GROUP BY cl.recipe_id, r.title "
        f"ORDER BY cook_count DESC LIMIT {int(limit)}"
    )
    return execute_query(sql, output_dir)


def format_trends(trends: list[CookingTrend], label: str = "Period") -> str:
    """Format trends as a markdown table.

    Args:
        trends: List of CookingTrend to format.
        label: Column header for the period (e.g. "Week" or "Month").

    Returns:
        Markdown table string.
    """
    if not trends:
        return "No cooking data found."

    lines = [
        f"| {label} | Cooks | Unique recipes |",
        "|---|---|---|",
    ]
    for t in trends:
        lines.append(f"| {t.period} | {t.cook_count} | {t.unique_recipes} |")
    return "\n".join(lines)
