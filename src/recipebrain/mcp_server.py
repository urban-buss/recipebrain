"""MCP server for recipebrain — exposes recipe knowledge base tools.

Tools are thin wrappers over the query layer and writer. All tools handle
exceptions and return error strings — never raise across the MCP boundary.
"""

from __future__ import annotations

import datetime
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from recipebrain.exceptions import DataStaleError, QueryError
from recipebrain.observability import collector
from recipebrain.parse.ingredient_line import parse_ingredient_line
from recipebrain.query import execute_query, invalidate_connection
from recipebrain.recommend.easy import suggest_easy as _suggest_easy
from recipebrain.recommend.pantry import suggest_for_pantry as _suggest_for_pantry
from recipebrain.recommend.rotation import suggest_rotation as _suggest_rotation
from recipebrain.settings import Settings
from recipebrain.transform import normalise_title
from recipebrain.writer import SCHEMAS, append_table, read_table, write_table

mcp = FastMCP("recipebrain")

_settings: Settings | None = None

_MAX_REFRESH_LIMIT = 200
_DEFAULT_REFRESH_LIMIT = 50
_ASYNC_BATCH_SIZE = 50


# ---------------------------------------------------------------------------
# Async refresh job tracking
# ---------------------------------------------------------------------------


@dataclass
class _RefreshJob:
    """Tracks a background ETL refresh job."""

    job_id: str
    source: str
    started_at: datetime.datetime
    status: str = "running"  # "running" | "completed" | "failed"
    results: list = field(default_factory=list)
    error: str | None = None


_jobs: dict[str, _RefreshJob] = {}
_jobs_lock = threading.Lock()


def _start_async_refresh(source: str) -> str:
    """Spawn a background thread to run ETL without a limit."""
    job_id = uuid.uuid4().hex[:8]
    job = _RefreshJob(
        job_id=job_id,
        source=source,
        started_at=datetime.datetime.now(tz=datetime.UTC),
    )
    with _jobs_lock:
        _jobs[job_id] = job
    thread = threading.Thread(target=_run_refresh_job, args=(job,), daemon=True)
    thread.start()
    return job_id


def _run_refresh_job(job: _RefreshJob) -> None:
    """Background thread target: run ETL and update job status."""
    try:
        from recipebrain.etl import run_etl

        settings = _get_settings()
        source_filter = None if job.source == "all" else job.source
        results = run_etl(
            settings,
            source_filter=source_filter,
            limit=None,
            batch_size=_ASYNC_BATCH_SIZE,
        )
        with _jobs_lock:
            job.results = results
            job.status = "completed"
    except Exception as exc:
        with _jobs_lock:
            job.error = str(exc)
            job.status = "failed"


def _format_job_status(job: _RefreshJob) -> str:
    """Format a single job's status for display."""
    elapsed = datetime.datetime.now(tz=datetime.UTC) - job.started_at
    minutes = int(elapsed.total_seconds() // 60)
    seconds = int(elapsed.total_seconds() % 60)

    lines = [f"**Job {job.job_id}** ({job.source}): {job.status} ({minutes}m {seconds}s)"]

    if job.status == "completed" and job.results:
        for r in job.results:
            lines.append(f"  {r.source}: {r.fetched} new, {r.skipped} skipped, {r.errors} errors")
    elif job.status == "failed":
        lines.append(f"  Error: {job.error}")

    return "\n".join(lines)


def _get_settings() -> Settings:
    global _settings  # noqa: PLW0603
    if _settings is None:
        import os

        config_path = os.environ.get("RECIPEBRAIN_CONFIG")
        _settings = Settings.load(config_path)
    return _settings


def _output_dir() -> Path:
    import os

    # Prefer the environment variable set by the CLI (guaranteed absolute).
    env_dir = os.environ.get("RECIPEBRAIN_OUTPUT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(_get_settings().paths.output_dir)


# ---------------------------------------------------------------------------
# Tool 1: find_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def find_recipe(
    query: str | None = None,
    language: str | None = None,
    max_total_minutes: int | None = None,
    difficulty: str | None = None,
    course: str | None = None,
    starred_only: bool = False,
    tags: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Search recipes by text, language, time, difficulty, course, starred, or tags.

    Returns a markdown table of matching recipes.
    """
    try:
        output = _output_dir()
        conditions: list[str] = []
        params: list[object] = []
        if query:
            conditions.append("title_normalised LIKE ?")
            params.append(f"%{query.lower()}%")
        if language:
            conditions.append("language = ?")
            params.append(language)
        if max_total_minutes is not None:
            conditions.append(f"total_minutes <= {int(max_total_minutes)}")
        if difficulty:
            conditions.append("difficulty = ?")
            params.append(difficulty)
        if course:
            conditions.append("course = ?")
            params.append(course)
        if starred_only:
            conditions.append("starred = true")

        # Tag filter: find recipe_ids that have ALL requested tags
        tag_filter_ids: list[int] | None = None
        if tags:
            slugs = [_slugify_tag(t) for t in tags if _slugify_tag(t)]
            if slugs:
                tags_path = output / "tags.parquet"
                rt_path = output / "recipe_tags.parquet"
                if tags_path.exists() and rt_path.exists():
                    placeholders = ", ".join("?" for _ in slugs)
                    tag_sql = (
                        f"SELECT rt.recipe_id FROM recipe_tags rt "
                        f"JOIN tags t ON rt.tag_id = t.id "
                        f"WHERE t.key IN ({placeholders}) "
                        f"GROUP BY rt.recipe_id "
                        f"HAVING COUNT(DISTINCT t.key) = {len(slugs)}"
                    )
                    tag_rows = execute_query(tag_sql, output, params=list(slugs))
                    tag_filter_ids = [r["recipe_id"] for r in tag_rows]
                else:
                    tag_filter_ids = []

        if tag_filter_ids is not None:
            if not tag_filter_ids:
                return "No recipes found matching your criteria."
            id_list = ", ".join(str(int(i)) for i in tag_filter_ids)
            conditions.append(f"id IN ({id_list})")

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            f"SELECT id, title, total_minutes, difficulty, course, language "
            f"FROM recipes{where} ORDER BY title LIMIT {int(limit)}"
        )

        rows = execute_query(sql, output, params=params)
        if not rows:
            return "No recipes found matching your criteria."

        lines = ["| ID | Title | Time (min) | Difficulty | Course | Language |"]
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['id']} | {r['title']} | {r.get('total_minutes', '')} "
                f"| {r.get('difficulty', '')} | {r.get('course', '')} "
                f"| {r.get('language', '')} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 2: read_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def read_recipe(recipe_id: int) -> str:
    """Return full details for a recipe by ID, including ingredients and steps."""
    try:
        output = _output_dir()

        # Fetch recipe
        recipes = execute_query(f"SELECT * FROM recipes WHERE id = {int(recipe_id)}", output)
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."
        recipe = recipes[0]

        # Fetch ingredients
        ingredients = execute_query(
            f"SELECT * FROM recipe_ingredients WHERE recipe_id = {int(recipe_id)} ORDER BY seq",
            output,
        )

        # Fetch steps
        steps = execute_query(
            f"SELECT * FROM recipe_steps WHERE recipe_id = {int(recipe_id)} ORDER BY step_no",
            output,
        )

        # Build markdown dossier
        lines = [f"# {recipe['title']}", ""]
        if recipe.get("description"):
            lines.extend([recipe["description"], ""])

        lines.append("## Details")
        lines.append(f"- **Source:** {recipe.get('source_url', 'N/A')}")
        lines.append(f"- **Servings:** {recipe.get('servings', 'N/A')}")
        lines.append(f"- **Total time:** {recipe.get('total_minutes', 'N/A')} min")
        lines.append(f"- **Difficulty:** {recipe.get('difficulty', 'N/A')}")
        lines.append(f"- **Course:** {recipe.get('course', 'N/A')}")
        lines.append(f"- **Cuisine:** {recipe.get('cuisine', 'N/A')}")
        lines.append("")

        if ingredients:
            lines.append("## Ingredients")
            for ing in ingredients:
                qty = ing.get("quantity", "")
                unit = ing.get("unit", "")
                raw = ing.get("raw_text", "")
                prep = ing.get("prep_note", "")
                text = raw or f"{qty} {unit}".strip()
                if prep:
                    text += f", {prep}"
                lines.append(f"- {text}")
            lines.append("")

        if steps:
            lines.append("## Steps")
            for step in steps:
                lines.append(f"{step['step_no']}. {step['text']}")
            lines.append("")

        # Cook history (FR-8.2.1)
        try:
            cook_events = execute_query(
                "SELECT cooked_on, servings, rating, notes FROM cook_log "
                f"WHERE recipe_id = {int(recipe_id)} "
                "ORDER BY cooked_on DESC, logged_at DESC LIMIT 5",
                output,
            )
        except (QueryError, DataStaleError):
            cook_events = []

        if cook_events:
            lines.append("## Cook History")
            for ev in cook_events:
                parts = [str(ev["cooked_on"])]
                if ev["servings"] is not None:
                    parts.append(f"{ev['servings']} servings")
                if ev["rating"] is not None:
                    parts.append(f"{ev['rating']}/5")
                entry = " | ".join(parts)
                if ev["notes"]:
                    entry += f" — {ev['notes']}"
                lines.append(f"- {entry}")
            lines.append("")

        # Merge dossier sections (FR-11.3.2 / FR-11.3.3)
        try:
            from recipebrain.dossier_ops import read_dossier, read_section

            dossier_dir = output / "dossiers" / "recipes"
            dossier_content = read_dossier(str(recipe_id), dossier_dir)
            if dossier_content:
                for sec in ("notes", "variations", "pairings", "tags"):
                    body = read_section(str(recipe_id), sec, dossier_dir)
                    if body and body.strip():
                        lines.append(f"## {sec.title()}")
                        lines.append(body.strip())
                        lines.append("")
        except Exception:
            pass  # Dossier is optional; missing file is fine

        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Helper: update recipe fields (read-modify-write on a single recipe)
# ---------------------------------------------------------------------------


def _update_recipe_fields(recipe_id: int, output_dir: Path, **updates: object) -> None:
    """Update specific fields on a single recipe row.

    Reads the full recipes table, modifies the target row, and writes back.
    """
    table = read_table("recipes", output_dir)
    ids = table.column("id").to_pylist()
    idx = ids.index(int(recipe_id))

    rows = table.to_pylist()
    for key, value in updates.items():
        rows[idx][key] = value

    write_table("recipes", rows, output_dir)
    invalidate_connection(output_dir)


# ---------------------------------------------------------------------------
# Tool 18: star_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def star_recipe(recipe_id: int, starred: bool = True) -> str:
    """Star or unstar a recipe as a favourite.

    Args:
        recipe_id: The recipe to star/unstar.
        starred: True to star, False to unstar.
    """
    try:
        output = _output_dir()

        recipes = execute_query(
            f"SELECT id, title FROM recipes WHERE id = {int(recipe_id)}", output
        )
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        _update_recipe_fields(recipe_id, output, starred=starred)

        action = "Starred" if starred else "Unstarred"
        return f"{action} '{recipes[0]['title']}'."
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 19: rate_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def rate_recipe(recipe_id: int, rating: int | None = None) -> str:
    """Set or clear the owner rating on a recipe.

    This is the user's considered opinion, distinct from the per-cook
    rating in log_cook.

    Args:
        recipe_id: The recipe to rate.
        rating: Rating 1-5, or None to clear.
    """
    try:
        output = _output_dir()

        recipes = execute_query(
            f"SELECT id, title FROM recipes WHERE id = {int(recipe_id)}", output
        )
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        if rating is not None and not (1 <= rating <= 5):
            return "Error: Rating must be between 1 and 5."

        _update_recipe_fields(recipe_id, output, owner_rating=rating)

        if rating is None:
            return f"Cleared rating for '{recipes[0]['title']}'."
        return f"Rated '{recipes[0]['title']}' {rating}/5."
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 20: cook_history
# ---------------------------------------------------------------------------


@mcp.tool()
def cook_history(recipe_id: int | None = None, limit: int = 10) -> str:
    """Show recent cook events from the cook log.

    Without recipe_id, shows global recent history across all recipes.
    With recipe_id, shows history for that specific recipe.

    Args:
        recipe_id: Optional recipe to filter by.
        limit: Max events to return (default 10).
    """
    try:
        output = _output_dir()

        if recipe_id is not None:
            # Validate recipe exists
            recipes = execute_query(
                f"SELECT id, title FROM recipes WHERE id = {int(recipe_id)}", output
            )
            if not recipes:
                return f"Error: Recipe with id={recipe_id} not found."

        if recipe_id is not None:
            sql = (
                "SELECT cl.cooked_on, cl.servings, cl.rating, cl.notes, r.title "
                "FROM cook_log cl JOIN recipes r ON cl.recipe_id = r.id "
                f"WHERE cl.recipe_id = {int(recipe_id)} "
                f"ORDER BY cl.cooked_on DESC, cl.logged_at DESC LIMIT {int(limit)}"
            )
        else:
            sql = (
                "SELECT cl.cooked_on, cl.servings, cl.rating, cl.notes, r.title "
                "FROM cook_log cl JOIN recipes r ON cl.recipe_id = r.id "
                f"ORDER BY cl.cooked_on DESC, cl.logged_at DESC LIMIT {int(limit)}"
            )

        rows = execute_query(sql, output)
        if not rows:
            if recipe_id is not None:
                return f"No cook history for recipe {recipe_id}."
            return "No cook history yet."

        lines: list[str] = []
        if recipe_id is not None:
            lines.append(f"## Cook History — {recipes[0]['title']}")
        else:
            lines.append("## Recent Cook History")
        lines.append("")

        for row in rows:
            date_str = str(row["cooked_on"])
            parts = [date_str]
            if recipe_id is None:
                parts.append(row["title"])
            if row["servings"] is not None:
                parts.append(f"{row['servings']} servings")
            if row["rating"] is not None:
                parts.append(f"{row['rating']}/5")
            line = " | ".join(parts)
            if row["notes"]:
                line += f" — {row['notes']}"
            lines.append(f"- {line}")

        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 9: log_cook
# ---------------------------------------------------------------------------


@mcp.tool()
def log_cook(
    recipe_id: int,
    cooked_on: str | None = None,
    servings: int | None = None,
    scale_factor: float | None = None,
    rating: int | None = None,
    notes: str | None = None,
) -> str:
    """Record a cook event for a recipe. Append-only.

    After logging, updates denormalised fields on the recipe:
    times_cooked, last_cooked_at, and owner_rating (latest non-null
    cook rating wins).

    Args:
        recipe_id: The recipe that was cooked.
        cooked_on: ISO date string (defaults to today).
        servings: Number of servings made.
        scale_factor: Multiplier applied to the recipe (e.g. 2.0 for doubled).
        rating: Rating 1-5.
        notes: Free-form notes.
    """
    try:
        output = _output_dir()

        # Validate recipe exists
        recipes = execute_query(
            f"SELECT id, title, times_cooked FROM recipes WHERE id = {int(recipe_id)}", output
        )
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        if rating is not None and not (1 <= rating <= 5):
            return "Error: Rating must be between 1 and 5."

        cook_date = cooked_on or datetime.date.today().isoformat()

        # Determine next ID
        try:
            existing = execute_query("SELECT MAX(id) AS max_id FROM cook_log", output)
            next_id = (existing[0]["max_id"] or 0) + 1
        except (QueryError, DataStaleError):
            next_id = 1

        row = {
            "id": next_id,
            "recipe_id": int(recipe_id),
            "cooked_on": datetime.date.fromisoformat(cook_date),
            "servings": servings,
            "scale_factor": scale_factor,
            "rating": rating,
            "notes": notes,
            "logged_at": datetime.datetime.now(tz=datetime.UTC),
        }

        append_table("cook_log", [row], output)
        invalidate_connection(output)

        # Denormalise stats onto the recipe (FR-8.1.2)
        rid = int(recipe_id)
        stats = execute_query(
            "SELECT COUNT(*) AS cnt, MAX(cooked_on) AS last_on FROM cook_log "
            f"WHERE recipe_id = {rid}",
            output,
        )
        latest_rating_rows = execute_query(
            "SELECT rating FROM cook_log "
            f"WHERE recipe_id = {rid} AND rating IS NOT NULL "
            "ORDER BY cooked_on DESC, logged_at DESC LIMIT 1",
            output,
        )
        denorm: dict[str, object] = {
            "times_cooked": stats[0]["cnt"],
        }
        last_on = stats[0]["last_on"]
        if last_on is not None:
            if isinstance(last_on, datetime.date) and not isinstance(last_on, datetime.datetime):
                last_on = datetime.datetime(
                    last_on.year, last_on.month, last_on.day, tzinfo=datetime.UTC
                )
            denorm["last_cooked_at"] = last_on
        else:
            denorm["last_cooked_at"] = None
        if latest_rating_rows:
            denorm["owner_rating"] = latest_rating_rows[0]["rating"]
        _update_recipe_fields(rid, output, **denorm)

        # Auto-transition pinned → cooked (FR-10.2.4)
        if (output / "pinned_recipes.parquet").exists():
            try:
                active_pins = execute_query(
                    f"SELECT id FROM pinned_recipes WHERE recipe_id = {rid} AND status = 'pinned'",
                    output,
                )
                if active_pins:
                    table = read_table("pinned_recipes", output)
                    pin_rows = table.to_pylist()
                    for pr in pin_rows:
                        if pr["recipe_id"] == rid and pr["status"] == "pinned":
                            pr["status"] = "cooked"
                    write_table("pinned_recipes", pin_rows, output)
                    invalidate_connection(output)
            except (QueryError, DataStaleError):
                pass

        return (
            f"Logged: cooked '{recipes[0]['title']}' on {cook_date}."
            f"{f' Rating: {rating}/5.' if rating else ''}"
        )
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 12: current_promotions
# ---------------------------------------------------------------------------


@mcp.tool()
def current_promotions(
    retailer: str | None = None,
    ingredient: str | None = None,
    min_discount_pct: float = 0.0,
    limit: int = 50,
) -> str:
    """Browse current promotions, optionally filtered by retailer or ingredient."""
    try:
        output = _output_dir()
        conditions: list[str] = []
        params: list[object] = []

        if min_discount_pct > 0:
            conditions.append(f"discount_pct >= {float(min_discount_pct)}")
        if retailer:
            conditions.append("retailer_id IN (SELECT id FROM retailers WHERE key = ?)")
            params.append(retailer)
        if ingredient:
            conditions.append("product_name ILIKE ?")
            params.append(f"%{ingredient}%")

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            f"SELECT product_name, brand, price_chf, regular_price_chf, discount_pct, "
            f"valid_from, valid_to FROM promotions{where} "
            f"ORDER BY discount_pct DESC LIMIT {int(limit)}"
        )

        rows = execute_query(sql, output, params=params)
        if not rows:
            return "No promotions found matching your criteria."

        lines = ["| Product | Brand | Price | Regular | Discount % | Valid |"]
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['product_name']} | {r.get('brand', '')} "
                f"| {r.get('price_chf', '')} | {r.get('regular_price_chf', '')} "
                f"| {r.get('discount_pct', '')}% "
                f"| {r.get('valid_from', '')} → {r.get('valid_to', '')} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 14: query_recipes
# ---------------------------------------------------------------------------


@mcp.tool()
def query_recipes(sql: str, limit: int = 100) -> str:
    """Execute a validated read-only SQL query against the recipe database.

    Only SELECT queries are allowed. DML/DDL is rejected.
    """
    try:
        rows = execute_query(sql, _output_dir(), limit=limit)
        if not rows:
            return "Query returned no results."

        # Format as markdown table
        columns = list(rows[0].keys())
        lines = ["| " + " | ".join(columns) + " |"]
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 3: suggest_for_pantry
# ---------------------------------------------------------------------------


@mcp.tool()
def suggest_for_pantry(
    extra_ingredients: list[str] | None = None,
    missing_ok: int = 2,
    max_total_minutes: int | None = None,
    limit: int = 5,
) -> str:
    """Suggest recipes matching current pantry contents.

    Ranks by coverage: fraction of recipe ingredients available in the pantry
    (plus extras and staples). Recipes with more missing items than missing_ok
    are excluded.
    """
    try:
        results = _suggest_for_pantry(
            _output_dir(),
            extra_ingredients=extra_ingredients,
            missing_ok=missing_ok,
            max_total_minutes=max_total_minutes,
            limit=limit,
        )
        if not results:
            return "No recipes found matching your pantry contents."

        lines = ["| ID | Title | Time | Coverage | Missing |"]
        lines.append("|---|---|---|---|---|")
        for r in results:
            missing_list = ", ".join(r.get("missing_ingredients", []))
            lines.append(
                f"| {r['id']} | {r['title']} "
                f"| {r.get('total_minutes', '')} min "
                f"| {r['coverage_score']:.0%} "
                f"| {missing_list or 'none'} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 4: suggest_rotation
# ---------------------------------------------------------------------------


@mcp.tool()
def suggest_rotation(
    min_rating: int = 4,
    not_cooked_in_days: int = 90,
    limit: int = 5,
) -> str:
    """Suggest high-rated recipes not cooked recently.

    Great for rediscovering favourites you haven't made in a while.
    """
    try:
        results = _suggest_rotation(
            _output_dir(),
            min_rating=min_rating,
            not_cooked_in_days=not_cooked_in_days,
            limit=limit,
        )
        if not results:
            return "No rotation suggestions found."

        lines = ["| ID | Title | Rating | Times Cooked | Last Cooked |"]
        lines.append("|---|---|---|---|---|")
        for r in results:
            last = r.get("last_cooked_at") or "never"
            lines.append(
                f"| {r['id']} | {r['title']} "
                f"| {r['owner_rating']}/5 "
                f"| {r.get('times_cooked', 0)} "
                f"| {last} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 7: suggest_easy
# ---------------------------------------------------------------------------


@mcp.tool()
def suggest_easy(
    max_total_minutes: int = 30,
    max_ingredients: int = 8,
    avoid_recent_days: int = 14,
    limit: int = 5,
) -> str:
    """Suggest quick, simple weeknight recipes.

    Filters by time and ingredient count, then ranks by speed and simplicity.
    """
    try:
        results = _suggest_easy(
            _output_dir(),
            max_total_minutes=max_total_minutes,
            max_ingredients=max_ingredients,
            avoid_recent_days=avoid_recent_days,
            limit=limit,
        )
        if not results:
            return "No easy recipes found matching your criteria."

        lines = ["| ID | Title | Time | Ingredients | Difficulty |"]
        lines.append("|---|---|---|---|---|")
        for r in results:
            lines.append(
                f"| {r['id']} | {r['title']} "
                f"| {r.get('total_minutes', '')} min "
                f"| {r.get('ingredient_count', '')} "
                f"| {r.get('difficulty', '')} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 10: update_pantry
# ---------------------------------------------------------------------------


@mcp.tool()
def update_pantry(
    additions: list[dict] | None = None,
    removals: list[str] | None = None,
    location: str = "fridge",
    note: str | None = None,
) -> str:
    """Update pantry contents. Add or remove ingredients.

    Args:
        additions: List of dicts with keys: ingredient (key), quantity, unit.
        removals: List of ingredient keys to remove from pantry.
        location: Storage location (fridge, freezer, pantry, garden).
        note: Optional note for additions.
    """
    try:
        output = _output_dir()
        now = datetime.datetime.now(tz=datetime.UTC)
        changes: list[str] = []

        if additions:
            # Resolve ingredient keys to IDs
            for item in additions:
                ing_key = item.get("ingredient", "")
                rows = execute_query(
                    "SELECT id, key FROM ingredients WHERE key = ?",
                    output,
                    params=[ing_key],
                )
                if not rows:
                    changes.append(f"⚠ Unknown ingredient: {ing_key}")
                    continue

                ing_id = rows[0]["id"]
                row = {
                    "ingredient_id": ing_id,
                    "approx_quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "location": location,
                    "updated_at": now,
                    "note": note,
                }
                write_table("pantry", [row], output)
                invalidate_connection(output)
                qty_str = ""
                if item.get("quantity"):
                    qty_str = f" ({item['quantity']} {item.get('unit', '')})"
                changes.append(f"+ {ing_key}{qty_str} → {location}")

        if removals:
            # Remove by rewriting pantry without the removed keys
            try:
                existing = execute_query("SELECT * FROM pantry", output)
            except (QueryError, DataStaleError):
                existing = []

            removal_ids: set[int] = set()
            for key in removals:
                rows = execute_query(
                    "SELECT id FROM ingredients WHERE key = ?",
                    output,
                    params=[key],
                )
                if rows:
                    removal_ids.add(rows[0]["id"])
                    changes.append(f"- {key}")
                else:
                    changes.append(f"⚠ Unknown ingredient: {key}")

            if removal_ids and existing:
                kept = [r for r in existing if r["ingredient_id"] not in removal_ids]
                write_table("pantry", kept, output)
                invalidate_connection(output)

        if not changes:
            return "No changes made. Provide additions or removals."

        return "Pantry updated:\n" + "\n".join(changes)
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 16: refresh_source
# ---------------------------------------------------------------------------


@mcp.tool()
def refresh_source(
    source: str = "all",
    limit: int | None = None,
) -> str:
    """Refresh recipes from a source by running the ETL pipeline.

    Discovers new recipe URLs, skips already-scraped ones, and fetches new
    recipes. Append-only — existing data is never deleted.

    Args:
        source: Source key ('migusto', 'swissmilk', 'schweizerfleisch', 'fooby',
                or 'all' for every enabled source).
        limit: Max new recipes to fetch per source. Defaults to 50, capped at
            200. Set to 0 for unlimited — runs asynchronously in the background
            and returns a job ID to check with refresh_status().
    """
    try:
        if limit == 0:
            # Unlimited async mode — run in a background thread with batch writing
            job_id = _start_async_refresh(source)
            return (
                f"Started full refresh for '{source}' (job: {job_id}).\n"
                f"Recipes are saved in batches of {_ASYNC_BATCH_SIZE} so partial "
                f"progress is preserved.\n"
                f"Use refresh_status(job_id='{job_id}') to check progress."
            )

        from recipebrain.etl import run_etl

        effective_limit = (
            min(limit, _MAX_REFRESH_LIMIT) if limit is not None else _DEFAULT_REFRESH_LIMIT
        )

        settings = _get_settings()
        source_filter = None if source == "all" else source

        results = run_etl(settings, source_filter=source_filter, limit=effective_limit)

        if not results:
            return f"Error: No source adapter found for '{source}'."

        lines: list[str] = []
        for r in results:
            lines.append(
                f"**{r.source}**: {r.fetched} new, {r.skipped} skipped, {r.errors} errors"
                f" ({r.discovered} discovered)"
            )
            for detail in r.error_details[:5]:
                lines.append(f"  - {detail}")
        return "Refresh complete:\n" + "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 17: refresh_status
# ---------------------------------------------------------------------------


@mcp.tool()
def refresh_status(job_id: str | None = None) -> str:
    """Check the status of a background recipe refresh job.

    Args:
        job_id: The job ID returned by refresh_source with limit=0.
            If omitted, shows all recent jobs.
    """
    with _jobs_lock:
        if job_id:
            job = _jobs.get(job_id)
            if not job:
                return f"Error: No job found with id '{job_id}'."
            return _format_job_status(job)

        if not _jobs:
            return "No refresh jobs found."

        lines = [_format_job_status(job) for job in _jobs.values()]
        return "\n---\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 21: pin_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def pin_recipe(
    recipe_id: int,
    target_date: str | None = None,
    note: str | None = None,
) -> str:
    """Pin a recipe to the cook-next board.

    Args:
        recipe_id: The recipe to pin.
        target_date: Optional ISO date for when you plan to cook it.
        note: Optional note (e.g. "for Saturday dinner with guests").
    """
    try:
        output = _output_dir()

        recipes = execute_query(
            f"SELECT id, title FROM recipes WHERE id = {int(recipe_id)}", output
        )
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        # Check if already pinned
        try:
            existing = execute_query(
                "SELECT id FROM pinned_recipes "
                f"WHERE recipe_id = {int(recipe_id)} AND status = 'pinned'",
                output,
            )
            if existing:
                return f"Recipe '{recipes[0]['title']}' is already pinned."
        except (QueryError, DataStaleError):
            pass

        # Determine next ID
        try:
            max_rows = execute_query("SELECT MAX(id) AS max_id FROM pinned_recipes", output)
            next_id = (max_rows[0]["max_id"] or 0) + 1
        except (QueryError, DataStaleError):
            next_id = 1

        row = {
            "id": next_id,
            "recipe_id": int(recipe_id),
            "pinned_at": datetime.datetime.now(tz=datetime.UTC),
            "target_date": (datetime.date.fromisoformat(target_date) if target_date else None),
            "note": note,
            "status": "pinned",
        }

        append_table("pinned_recipes", [row], output)
        invalidate_connection(output)

        parts = [f"Pinned '{recipes[0]['title']}'."]
        if target_date:
            parts.append(f"Target date: {target_date}.")
        return " ".join(parts)
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 22: list_pinned
# ---------------------------------------------------------------------------


@mcp.tool()
def list_pinned(include_done: bool = False) -> str:
    """Show currently pinned recipes, ordered by target date then pin date.

    Args:
        include_done: If True, also show cooked/dismissed pins.
    """
    try:
        output = _output_dir()

        if not (output / "pinned_recipes.parquet").exists():
            return "No pinned recipes."

        status_filter = "" if include_done else "WHERE p.status = 'pinned' "
        sql = (
            "SELECT p.id, p.recipe_id, r.title, p.pinned_at, "
            "p.target_date, p.note, p.status "
            "FROM pinned_recipes p JOIN recipes r ON p.recipe_id = r.id "
            f"{status_filter}"
            "ORDER BY p.target_date ASC NULLS LAST, p.pinned_at ASC"
        )

        rows = execute_query(sql, output)
        if not rows:
            return "No pinned recipes."

        lines = ["## Pinboard", ""]
        for row in rows:
            parts = [row["title"]]
            if row["target_date"] is not None:
                parts.append(f"📅 {row['target_date']}")
            if row["status"] != "pinned":
                parts.append(f"[{row['status']}]")
            entry = " | ".join(parts)
            if row["note"]:
                entry += f" — {row['note']}"
            lines.append(f"- {entry}")

        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 23: unpin_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def unpin_recipe(recipe_id: int) -> str:
    """Dismiss a pinned recipe from the cook-next board.

    Args:
        recipe_id: The recipe to unpin.
    """
    try:
        output = _output_dir()

        recipes = execute_query(
            f"SELECT id, title FROM recipes WHERE id = {int(recipe_id)}", output
        )
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        try:
            pinned = execute_query(
                "SELECT id FROM pinned_recipes "
                f"WHERE recipe_id = {int(recipe_id)} AND status = 'pinned'",
                output,
            )
        except (QueryError, DataStaleError):
            pinned = []

        if not pinned:
            return f"Recipe '{recipes[0]['title']}' is not currently pinned."

        # Read-modify-write on pinned_recipes
        table = read_table("pinned_recipes", output)
        rows = table.to_pylist()
        for row in rows:
            if row["recipe_id"] == int(recipe_id) and row["status"] == "pinned":
                row["status"] = "dismissed"
        write_table("pinned_recipes", rows, output)
        invalidate_connection(output)

        return f"Unpinned '{recipes[0]['title']}'."
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Helper: ensure the 'own' source exists
# ---------------------------------------------------------------------------

_OWN_SOURCE_KEY = "own"


def _ensure_own_source(output: Path) -> int:
    """Return the source_id for the 'own' source, creating it if needed."""
    try:
        rows = execute_query(
            "SELECT id FROM sources WHERE key = ?", output, params=[_OWN_SOURCE_KEY]
        )
        if rows:
            return rows[0]["id"]
    except (QueryError, DataStaleError):
        pass

    # Determine next ID
    try:
        max_rows = execute_query("SELECT MAX(id) AS max_id FROM sources", output)
        next_id = (max_rows[0]["max_id"] or 0) + 1
    except (QueryError, DataStaleError):
        next_id = 1

    row = {
        "id": next_id,
        "key": _OWN_SOURCE_KEY,
        "display_name": "Own Recipes",
        "base_url": None,
        "language": None,
        "kind": "own",
    }
    append_table("sources", [row], output)
    invalidate_connection(output)
    return next_id


# ---------------------------------------------------------------------------
# Tool 24: add_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def add_recipe(
    title: str,
    ingredients: list[str],
    steps: list[str],
    servings: int | None = None,
    prep_minutes: int | None = None,
    cook_minutes: int | None = None,
    difficulty: str | None = None,
    notes: str | None = None,
) -> str:
    """Add a user-created recipe to the knowledge base.

    Ingredients are free-text strings (e.g. "200 g Pouletbrust, in Würfeln")
    that are parsed into quantity/unit/ingredient/prep_note.

    Args:
        title: Recipe title.
        ingredients: List of ingredient lines.
        steps: List of step descriptions.
        servings: Number of servings.
        prep_minutes: Preparation time in minutes.
        cook_minutes: Cooking time in minutes.
        difficulty: Difficulty level (e.g. "easy", "medium", "hard").
        notes: Optional notes to store in the recipe dossier.
    """
    try:
        output = _output_dir()

        if not title or not title.strip():
            return "Error: Title is required."
        if not ingredients:
            return "Error: At least one ingredient is required."
        if not steps:
            return "Error: At least one step is required."

        source_id = _ensure_own_source(output)
        now = datetime.datetime.now(tz=datetime.UTC)

        # Determine next recipe ID
        try:
            max_rows = execute_query("SELECT MAX(id) AS max_id FROM recipes", output)
            next_id = (max_rows[0]["max_id"] or 0) + 1
        except (QueryError, DataStaleError):
            next_id = 1

        total = None
        if prep_minutes is not None and cook_minutes is not None:
            total = prep_minutes + cook_minutes
        elif prep_minutes is not None:
            total = prep_minutes
        elif cook_minutes is not None:
            total = cook_minutes

        recipe_row = {
            "id": next_id,
            "source_id": source_id,
            "source_external_id": f"own-{next_id}",
            "source_url": None,
            "title": title.strip(),
            "title_normalised": normalise_title(title),
            "language": None,
            "description": None,
            "servings": servings,
            "prep_minutes": prep_minutes,
            "cook_minutes": cook_minutes,
            "total_minutes": total,
            "difficulty": difficulty,
            "cuisine": None,
            "course": None,
            "primary_image_url": None,
            "original_keywords": [],
            "owner_rating": None,
            "starred": False,
            "times_cooked": 0,
            "last_cooked_at": None,
            "scraped_at": now,
            "updated_at": now,
            "content_hash": None,
            "status": "active",
        }
        append_table("recipes", [recipe_row], output)
        invalidate_connection(output)

        # Parse and store ingredients
        ingredient_rows = []
        for seq, raw_text in enumerate(ingredients, start=1):
            parsed = parse_ingredient_line(raw_text)
            ingredient_rows.append(
                {
                    "recipe_id": next_id,
                    "seq": seq,
                    "ingredient_id": None,
                    "raw_text": raw_text,
                    "quantity": parsed.quantity,
                    "unit": parsed.unit,
                    "prep_note": parsed.prep_note,
                    "optional": False,
                    "group_label": None,
                }
            )
        append_table("recipe_ingredients", ingredient_rows, output)
        invalidate_connection(output)

        # Store steps
        step_rows = [
            {
                "recipe_id": next_id,
                "step_no": i,
                "text": text,
                "image_url": None,
            }
            for i, text in enumerate(steps, start=1)
        ]
        append_table("recipe_steps", step_rows, output)
        invalidate_connection(output)

        # Store notes in dossier if provided
        if notes:
            try:
                from recipebrain.dossier_ops import resolve_dossier_path

                dossier_dir = output / "dossiers" / "recipes"
                dossier_dir.mkdir(parents=True, exist_ok=True)
                dossier_path = resolve_dossier_path(str(next_id), dossier_dir)
                dossier_path.write_text(
                    f"# {title.strip()}\n\n## notes\n\n{notes}\n", encoding="utf-8"
                )
            except Exception:
                pass  # Notes are best-effort; recipe is still created

        return f"Created recipe '{title.strip()}' with id={next_id}."
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 25: annotate_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def annotate_recipe(recipe_id: int, section: str, content: str) -> str:
    """Add a personal annotation to a recipe's dossier file.

    Appends *content* to the given *section* in the recipe's Markdown dossier.
    If the dossier or section doesn't exist yet, it is created automatically.

    Allowed sections: notes, cook_log, tags, pairings, variations.
    """
    try:
        from recipebrain.dossier_ops import (
            ALLOWED_SECTIONS,
            append_to_section,
            resolve_dossier_path,
            write_dossier,
        )
        from recipebrain.exceptions import ProtectedSectionError, RecipeNotFoundError

        output = _output_dir()

        normalised = section.strip().lower()
        if normalised not in ALLOWED_SECTIONS:
            return (
                f"Error: Section '{section}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_SECTIONS))}."
            )

        if not content or not content.strip():
            return "Error: Content must not be empty."

        # Verify recipe exists
        recipes = execute_query(f"SELECT title FROM recipes WHERE id = {int(recipe_id)}", output)
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        title = recipes[0]["title"]
        dossier_dir = output / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        dossier_path = resolve_dossier_path(str(recipe_id), dossier_dir)

        # Create dossier if it doesn't exist yet
        if not dossier_path.exists():
            write_dossier(str(recipe_id), f"# {title}\n", dossier_dir)

        append_to_section(str(recipe_id), normalised, content.strip(), dossier_dir)

        return f"Added to '{normalised}' section for recipe {recipe_id} ({title})."
    except (ProtectedSectionError, RecipeNotFoundError) as exc:
        return f"Error: {exc}"
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Helper: slugify tag
# ---------------------------------------------------------------------------


def _slugify_tag(tag: str) -> str:
    """Normalise a tag string to a lowercase slug (letters, digits, hyphens)."""
    import re

    slug = tag.strip().lower()
    slug = re.sub(r"[^a-z0-9äöüéèà-]+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Tool 26: tag_recipe
# ---------------------------------------------------------------------------


@mcp.tool()
def tag_recipe(recipe_id: int, tags: list[str]) -> str:
    """Add user tags to a recipe. Tags are normalised to lowercase slugs.

    New tags are auto-created in the tags table on first use.
    Duplicate tag assignments are silently ignored.
    """
    try:
        output = _output_dir()

        if not tags:
            return "Error: At least one tag is required."

        # Verify recipe exists
        recipes = execute_query(f"SELECT id FROM recipes WHERE id = {int(recipe_id)}", output)
        if not recipes:
            return f"Error: Recipe with id={recipe_id} not found."

        # Normalise tags
        slugs = [_slugify_tag(t) for t in tags]
        slugs = [s for s in slugs if s]  # drop empty after slugify
        if not slugs:
            return "Error: No valid tags after normalisation."

        # Load or create tags table
        tags_path = output / "tags.parquet"
        if tags_path.exists():
            tag_table = read_table("tags", output)
            existing_keys = tag_table.column("key").to_pylist()
            existing_ids = tag_table.column("id").to_pylist()
            next_tag_id = max(existing_ids) + 1 if existing_ids else 1
        else:
            existing_keys = []
            next_tag_id = 1

        # Auto-create missing tags
        new_tag_rows = []
        for slug in slugs:
            if slug not in existing_keys:
                new_tag_rows.append(
                    {
                        "id": next_tag_id,
                        "key": slug,
                        "display": slug.replace("-", " "),
                        "facet": "user",
                    }
                )
                existing_keys.append(slug)
                next_tag_id += 1

        if new_tag_rows:
            append_table("tags", new_tag_rows, output)
            invalidate_connection(output)

        # Reload tags to get id mapping
        tag_table = read_table("tags", output)
        key_to_id = dict(
            zip(
                tag_table.column("key").to_pylist(),
                tag_table.column("id").to_pylist(),
                strict=False,
            )
        )

        # Load existing recipe_tags
        rt_path = output / "recipe_tags.parquet"
        if rt_path.exists():
            rt_table = read_table("recipe_tags", output)
            existing_pairs = set(
                zip(
                    rt_table.column("recipe_id").to_pylist(),
                    rt_table.column("tag_id").to_pylist(),
                    strict=False,
                )
            )
        else:
            existing_pairs = set()

        # Add new associations (skip duplicates)
        new_rt_rows = []
        for slug in slugs:
            tag_id = key_to_id[slug]
            if (int(recipe_id), tag_id) not in existing_pairs:
                new_rt_rows.append({"recipe_id": int(recipe_id), "tag_id": tag_id})

        if new_rt_rows:
            append_table("recipe_tags", new_rt_rows, output)
            invalidate_connection(output)

        return f"Tagged recipe {recipe_id} with: {', '.join(slugs)}."
    except (QueryError, DataStaleError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 27: list_starred
# ---------------------------------------------------------------------------


@mcp.tool()
def list_starred(limit: int = 50) -> str:
    """List all starred (favourite) recipes.

    Returns a markdown table of starred recipes, ordered by title.
    """
    try:
        output = _output_dir()
        sql = (
            "SELECT id, title, total_minutes, difficulty, course, owner_rating "
            f"FROM recipes WHERE starred = true ORDER BY title LIMIT {int(limit)}"
        )
        rows = execute_query(sql, output)
        if not rows:
            return "No starred recipes."

        lines = ["# Starred Recipes", ""]
        lines.append("| ID | Title | Time (min) | Difficulty | Course | Rating |")
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            rating = f"{r['owner_rating']}/5" if r.get("owner_rating") is not None else ""
            lines.append(
                f"| {r['id']} | {r['title']} | {r.get('total_minutes', '')} "
                f"| {r.get('difficulty', '')} | {r.get('course', '')} "
                f"| {rating} |"
            )
        return "\n".join(lines)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 29: batch_annotate
# ---------------------------------------------------------------------------


@mcp.tool()
def batch_annotate(recipe_ids: list[int], section: str, content: str) -> str:
    """Add the same annotation to multiple recipes at once.

    Appends *content* to the given *section* in each recipe's dossier.
    Allowed sections: notes, cook_log, tags, pairings, variations.

    Args:
        recipe_ids: List of recipe IDs to annotate.
        section: Dossier section name.
        content: Text to append.
    """
    from recipebrain.dossier_ops import (
        ALLOWED_SECTIONS,
        append_to_section,
        resolve_dossier_path,
        write_dossier,
    )
    from recipebrain.exceptions import ProtectedSectionError, RecipeNotFoundError

    normalised = section.strip().lower()
    if normalised not in ALLOWED_SECTIONS:
        return (
            f"Error: Section '{section}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_SECTIONS))}."
        )

    if not content or not content.strip():
        return "Error: Content must not be empty."

    if not recipe_ids:
        return "Error: No recipe IDs provided."

    try:
        output = _output_dir()
        dossier_dir = output / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)

        ok: list[str] = []
        errors: list[str] = []

        for rid in recipe_ids:
            try:
                recipes = execute_query(f"SELECT title FROM recipes WHERE id = {int(rid)}", output)
                if not recipes:
                    errors.append(f"#{rid}: not found")
                    continue

                title = recipes[0]["title"]
                dossier_path = resolve_dossier_path(str(rid), dossier_dir)
                if not dossier_path.exists():
                    write_dossier(str(rid), f"# {title}\n", dossier_dir)

                append_to_section(str(rid), normalised, content.strip(), dossier_dir)
                ok.append(f"#{rid} ({title})")
            except (ProtectedSectionError, RecipeNotFoundError, ValueError) as exc:
                errors.append(f"#{rid}: {exc}")

        parts = []
        if ok:
            parts.append(f"Annotated {len(ok)} recipe(s): {', '.join(ok)}.")
        if errors:
            parts.append(f"Errors ({len(errors)}): {'; '.join(errors)}.")
        return " ".join(parts) or "No changes made."
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 30: batch_tag
# ---------------------------------------------------------------------------


@mcp.tool()
def batch_tag(recipe_ids: list[int], tags: list[str]) -> str:
    """Add the same tags to multiple recipes at once.

    Tags are normalised to lowercase slugs and auto-created if new.

    Args:
        recipe_ids: List of recipe IDs to tag.
        tags: List of tag strings to apply.
    """
    if not recipe_ids:
        return "Error: No recipe IDs provided."
    if not tags:
        return "Error: No tags provided."

    ok: list[str] = []
    errors: list[str] = []

    for rid in recipe_ids:
        result = tag_recipe(recipe_id=rid, tags=tags)
        if result.startswith("Error"):
            errors.append(f"#{rid}: {result}")
        else:
            ok.append(f"#{rid}")

    parts = []
    if ok:
        parts.append(f"Tagged {len(ok)} recipe(s): {', '.join(ok)}.")
    if errors:
        parts.append(f"Errors ({len(errors)}): {'; '.join(errors)}.")
    return " ".join(parts) or "No changes made."


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("recipe://list", description="All active recipes with basic metadata")
def resource_recipe_list() -> str:
    """List all active recipes as JSON."""
    output = _output_dir()
    rows = execute_query(
        "SELECT id, title, language, total_minutes, difficulty, course "
        "FROM recipes WHERE status = 'active' ORDER BY title",
        output,
    )
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://stats", description="Recipe collection statistics")
def resource_recipe_stats() -> str:
    """Summary statistics about the recipe collection."""
    output = _output_dir()
    rows = execute_query(
        "SELECT COUNT(*) AS total, "
        "COUNT(CASE WHEN status='active' THEN 1 END) AS active, "
        "COUNT(CASE WHEN status='deleted' THEN 1 END) AS deleted, "
        "COUNT(CASE WHEN starred THEN 1 END) AS starred, "
        "AVG(total_minutes) AS avg_minutes, "
        "COUNT(DISTINCT language) AS languages, "
        "COUNT(DISTINCT course) AS courses "
        "FROM recipes",
        output,
    )
    import json

    return json.dumps(rows[0] if rows else {}, default=str)


@mcp.resource("recipe://starred", description="All starred/favourite recipes")
def resource_starred() -> str:
    """Starred recipes as JSON."""
    output = _output_dir()
    rows = execute_query(
        "SELECT id, title, owner_rating, times_cooked "
        "FROM recipes WHERE starred = true ORDER BY title",
        output,
    )
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://pinned", description="Currently pinned recipes for meal planning")
def resource_pinned() -> str:
    """Pinned recipes as JSON."""
    output = _output_dir()
    try:
        rows = execute_query(
            "SELECT pr.recipe_id, r.title, pr.target_date, pr.note, pr.status "
            "FROM pinned_recipes pr LEFT JOIN recipes r ON pr.recipe_id = r.id "
            "WHERE pr.status = 'pinned' ORDER BY pr.target_date",
            output,
        )
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://cook-log", description="Recent cooking history")
def resource_cook_log() -> str:
    """Recent cook log entries as JSON."""
    output = _output_dir()
    rows = execute_query(
        "SELECT cl.recipe_id, r.title, cl.cooked_on, cl.rating, cl.notes "
        "FROM cook_log cl LEFT JOIN recipes r ON cl.recipe_id = r.id "
        "ORDER BY cl.cooked_on DESC LIMIT 50",
        output,
    )
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://pantry", description="Current pantry contents")
def resource_pantry() -> str:
    """Pantry items as JSON."""
    output = _output_dir()
    try:
        rows = execute_query(
            "SELECT p.ingredient_id, i.key, i.display_de, p.approx_quantity, "
            "p.unit, p.location "
            "FROM pantry p LEFT JOIN ingredients i ON p.ingredient_id = i.id "
            "ORDER BY i.key",
            output,
        )
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://tags", description="All recipe tags")
def resource_tags() -> str:
    """All tags as JSON."""
    output = _output_dir()
    try:
        rows = execute_query("SELECT id, key, display, facet FROM tags ORDER BY key", output)
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://sources", description="Configured recipe sources")
def resource_sources() -> str:
    """Source adapters as JSON."""
    output = _output_dir()
    try:
        rows = execute_query(
            "SELECT id, key, display_name, base_url, language, kind FROM sources ORDER BY key",
            output,
        )
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


@mcp.resource("recipe://promotions", description="Current active promotions")
def resource_promotions() -> str:
    """Current promotions as JSON."""
    output = _output_dir()
    try:
        rows = execute_query(
            "SELECT id, product_name, brand, price_chf, regular_price_chf, "
            "discount_pct, valid_from, valid_to "
            "FROM promotions WHERE valid_to >= CURRENT_DATE "
            "ORDER BY discount_pct DESC LIMIT 50",
            output,
        )
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


@mcp.resource(
    "recipe://ingredients",
    description="Canonical ingredient catalogue",
)
def resource_ingredients() -> str:
    """Ingredient catalogue as JSON."""
    output = _output_dir()
    try:
        rows = execute_query(
            "SELECT id, key, display_de, display_fr, display_en, category, "
            "sub_category, default_unit FROM ingredients ORDER BY key",
            output,
        )
    except (QueryError, DataStaleError):
        rows = []
    import json

    return json.dumps(rows, default=str)


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@mcp.prompt(
    name="recipe_qa",
    description="System prompt for recipe Q&A with embedded collection stats",
)
def prompt_recipe_qa() -> str:
    """Generate a context-rich system prompt for recipe question answering."""
    try:
        output = _output_dir()
        stats_rows = execute_query(
            "SELECT COUNT(*) AS total, "
            "COUNT(CASE WHEN status='active' THEN 1 END) AS active, "
            "COUNT(CASE WHEN starred THEN 1 END) AS starred, "
            "ROUND(AVG(total_minutes), 0) AS avg_minutes, "
            "COUNT(DISTINCT language) AS languages "
            "FROM recipes",
            output,
        )
        stats = stats_rows[0] if stats_rows else {}

        cook_rows = execute_query("SELECT COUNT(*) AS n FROM cook_log", output)
        cook_count = cook_rows[0]["n"] if cook_rows else 0

        return (
            "You are a helpful recipe assistant with access to a personal Swiss recipe "
            "knowledge base.\n\n"
            f"## Collection stats\n"
            f"- Total recipes: {stats.get('total', 0)} "
            f"(active: {stats.get('active', 0)}, starred: {stats.get('starred', 0)})\n"
            f"- Languages: {stats.get('languages', 0)}\n"
            f"- Avg cooking time: {stats.get('avg_minutes', '?')} minutes\n"
            f"- Cook log entries: {cook_count}\n\n"
            "## Guidelines\n"
            "- Suggest recipes from the collection when possible\n"
            "- Consider cooking time, difficulty, and available ingredients\n"
            "- Mention starred favourites when relevant\n"
            "- Reference the user's cooking history for personalisation\n"
            "- Use the pantry contents to suggest what can be cooked now\n"
            "- For Swiss recipes, provide German ingredient names\n"
        )
    except (QueryError, DataStaleError):
        return (
            "You are a helpful recipe assistant. The recipe database is currently "
            "unavailable. Answer general cooking questions."
        )


@mcp.prompt(
    name="meal_plan",
    description="System prompt for weekly meal planning",
)
def prompt_meal_plan() -> str:
    """Generate a system prompt for meal planning with pantry context."""
    try:
        output = _output_dir()
        pantry_rows: list[dict] = []
        try:
            pantry_rows = execute_query(
                "SELECT i.display_de, p.approx_quantity, p.unit "
                "FROM pantry p LEFT JOIN ingredients i ON p.ingredient_id = i.id "
                "ORDER BY i.display_de",
                output,
            )
        except (QueryError, DataStaleError):
            pass

        pinned_rows: list[dict] = []
        try:
            pinned_rows = execute_query(
                "SELECT r.title, pr.target_date "
                "FROM pinned_recipes pr LEFT JOIN recipes r ON pr.recipe_id = r.id "
                "WHERE pr.status = 'pinned' ORDER BY pr.target_date",
                output,
            )
        except (QueryError, DataStaleError):
            pass

        parts = [
            "You are a meal planning assistant for a Swiss household.",
            "",
            "## Current pantry",
        ]
        if pantry_rows:
            for p in pantry_rows[:20]:
                qty = f"{p['approx_quantity']} {p['unit']}" if p.get("approx_quantity") else ""
                parts.append(f"- {p.get('display_de', '?')} {qty}".strip())
        else:
            parts.append("- (empty or unknown)")

        parts.append("")
        parts.append("## Already planned")
        if pinned_rows:
            for pin in pinned_rows[:10]:
                date_str = str(pin.get("target_date") or "no date")[:10]
                parts.append(f"- {pin.get('title', '?')} ({date_str})")
        else:
            parts.append("- (none)")

        parts.extend(
            [
                "",
                "## Guidelines",
                "- Plan 5-7 dinners for the week",
                "- Use pantry ingredients where possible to reduce waste",
                "- Balance quick meals (≤30 min) with longer weekend recipes",
                "- Avoid repeating recent cooks (check cook_log)",
                "- Consider promotions for cost savings",
            ]
        )
        return "\n".join(parts)
    except (QueryError, DataStaleError):
        return "You are a meal planning assistant. Database unavailable."


# ---------------------------------------------------------------------------
# Tool 15: server_stats
# ---------------------------------------------------------------------------


@mcp.tool()
def server_stats() -> str:
    """Return server statistics: dataset counts, last refresh, and tool metrics."""
    try:
        output = _output_dir()
        lines = ["# recipebrain stats", ""]

        for entity in sorted(SCHEMAS.keys()):
            parquet_path = output / f"{entity}.parquet"
            if parquet_path.exists():
                try:
                    count_rows = execute_query(f"SELECT COUNT(*) AS n FROM {entity}", output)
                    count = count_rows[0]["n"] if count_rows else 0
                except QueryError:
                    count = "error"
                lines.append(f"- **{entity}:** {count} rows")
            else:
                lines.append(f"- **{entity}:** no data")

        # Observability metrics
        obs = collector.stats()
        if obs.get("total", 0) > 0:
            lines.append("")
            lines.append("## Tool metrics")
            lines.append(f"- Calls: {obs['total']} ({obs['success']} ok, {obs['error']} err)")
            lines.append(f"- Avg latency: {obs['avg_ms']}ms, max: {obs['max_ms']}ms")

        return "\n".join(lines)
    except (DataStaleError, QueryError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool 28: cooking_frequency
# ---------------------------------------------------------------------------


@mcp.tool()
def cooking_frequency(
    granularity: str = "weekly",
    periods: int | None = None,
) -> str:
    """Show cooking frequency trends (weekly or monthly) and top recipes.

    Args:
        granularity: 'weekly' or 'monthly'.
        periods: Number of periods to look back (default 12 for weekly, 6 for monthly).
    """
    from recipebrain.recommend.frequency import (
        format_trends,
        monthly_trends,
        top_recipes,
        weekly_trends,
    )

    try:
        output = _output_dir()

        if granularity == "monthly":
            n = periods or 6
            trends = monthly_trends(output, months=n)
            table = format_trends(trends, label="Month")
        else:
            n = periods or 12
            trends = weekly_trends(output, weeks=n)
            table = format_trends(trends, label="Week")

        # Top recipes section
        top = top_recipes(output, limit=5)
        parts = [table]
        if top:
            parts.append("")
            parts.append("## Most cooked recipes")
            parts.append("| Recipe | Times | Last cooked |")
            parts.append("|---|---|---|")
            for r in top:
                title = r.get("title") or f"#{r['recipe_id']}"
                last = str(r.get("last_cooked") or "—")[:10]
                parts.append(f"| {title} | {r['cook_count']} | {last} |")

        return "\n".join(parts)
    except (QueryError, DataStaleError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------


def run() -> int:
    """Start the MCP server (stdio transport)."""
    mcp.run(transport="stdio")
    return 0
