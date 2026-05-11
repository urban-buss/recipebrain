"""Recommend rotation recipes — high-rated dishes not cooked recently.

Surfaces recipes the user has rated highly but hasn't made in a while,
encouraging variety in the meal rotation.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from recipebrain.query import execute_query


def suggest_rotation(
    output_dir: Path,
    *,
    min_rating: int = 4,
    not_cooked_in_days: int = 90,
    limit: int = 5,
) -> list[dict]:
    """Return high-rated recipes that haven't been cooked recently.

    Ranks by a composite score favouring higher ratings and longer gaps
    since last cook.

    Args:
        output_dir: Path to Parquet datasets.
        min_rating: Minimum owner_rating to consider (1-5).
        not_cooked_in_days: Prefer recipes not cooked within this many days.
        limit: Maximum number of results.

    Returns:
        List of recipe dicts with keys: id, title, owner_rating,
        times_cooked, last_cooked_at, days_since_cooked, score.

    Examples:
        >>> results = suggest_rotation(Path("output"), min_rating=4, limit=3)
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=not_cooked_in_days)
    cutoff_iso = cutoff.isoformat()

    sql = (
        "SELECT id, title, owner_rating, times_cooked, last_cooked_at, "
        "       total_minutes, difficulty "
        "FROM recipes "
        f"WHERE owner_rating >= {int(min_rating)} "
        "  AND status = 'active' "
        "ORDER BY owner_rating DESC, last_cooked_at ASC NULLS FIRST "
        f"LIMIT {int(limit) * 5}"
    )

    rows = execute_query(sql, output_dir)
    today = datetime.date.today()

    scored: list[dict] = []
    for row in rows:
        rating = row.get("owner_rating") or min_rating
        last_cooked = row.get("last_cooked_at")

        # Days since last cook
        if last_cooked is None:
            days_since = None
            freshness_score = 1.0  # never cooked → maximum freshness bonus
        else:
            if isinstance(last_cooked, datetime.datetime):
                last_date = last_cooked.date()
            elif isinstance(last_cooked, datetime.date):
                last_date = last_cooked
            else:
                last_date = datetime.date.fromisoformat(str(last_cooked)[:10])
            days_since = (today - last_date).days
            if str(last_cooked)[:10] <= cutoff_iso:
                freshness_score = min(1.0, days_since / (not_cooked_in_days * 2))
            else:
                freshness_score = 0.0  # recently cooked

        # Rating score normalised to 0..1
        rating_score = (rating - 1) / 4.0

        score = round(rating_score * 0.6 + freshness_score * 0.4, 3)

        scored.append(
            {
                "id": row["id"],
                "title": row["title"],
                "owner_rating": rating,
                "times_cooked": row.get("times_cooked", 0),
                "last_cooked_at": last_cooked,
                "days_since_cooked": days_since,
                "score": score,
            }
        )

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]
