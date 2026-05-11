"""Markdown rendering for recipe dossiers.

Converts recipe data (from Parquet rows / dicts) into structured Markdown
files that conform to the section layout expected by ``dossier_ops``.

Section names align with ``dossier_ops.ALLOWED_SECTIONS`` and
``dossier_ops.PROTECTED_SECTIONS``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def render_metadata(recipe: dict) -> str:
    """Render the ``## Metadata`` section for a recipe.

    Includes source URL, servings, total time, difficulty, course, and cuisine.

    Examples:
        >>> render_metadata({"source_url": "https://fooby.ch/x", "servings": 4})
        '## Metadata\\n\\n- **Source:** https://fooby.ch/x\\n- **Servings:** 4...'
    """
    lines = ["## Metadata", ""]
    fields = [
        ("Source", "source_url"),
        ("Servings", "servings"),
        ("Total time", "total_minutes"),
        ("Difficulty", "difficulty"),
        ("Course", "course"),
        ("Cuisine", "cuisine"),
        ("Language", "language"),
    ]
    for label, key in fields:
        value = recipe.get(key)
        if value is not None and str(value).strip():
            suffix = " min" if key == "total_minutes" else ""
            lines.append(f"- **{label}:** {value}{suffix}")
    return "\n".join(lines)


def render_source(recipe: dict) -> str:
    """Render the ``## Source`` section for a recipe.

    Shows the origin source information.

    Examples:
        >>> render_source({"source_url": "https://fooby.ch/x", "source_external_id": "abc"})
        '## Source\\n\\n- **URL:** https://fooby.ch/x\\n- **External ID:** abc'
    """
    lines = ["## Source", ""]
    url = recipe.get("source_url")
    ext_id = recipe.get("source_external_id")
    source_id = recipe.get("source_id")
    if url:
        lines.append(f"- **URL:** {url}")
    if ext_id:
        lines.append(f"- **External ID:** {ext_id}")
    if source_id is not None:
        lines.append(f"- **Source ID:** {source_id}")
    return "\n".join(lines)


def render_ingredients(ingredients: list[dict]) -> str:
    """Render the ``## Ingredients`` section.

    Each ingredient is a bullet point with quantity, unit, raw text, and
    optional prep note.  Group labels produce sub-headings.

    Examples:
        >>> render_ingredients([{"raw_text": "200 g Mehl", "group_label": None}])
        '## Ingredients\\n\\n- 200 g Mehl'
    """
    lines = ["## Ingredients", ""]
    current_group: str | None = None

    for ing in ingredients:
        group = ing.get("group_label")
        if group and group != current_group:
            if current_group is not None:
                lines.append("")
            lines.append(f"**{group}**")
            lines.append("")
            current_group = group

        raw = ing.get("raw_text", "")
        qty = ing.get("quantity")
        unit = ing.get("unit", "")
        prep = ing.get("prep_note", "")

        if raw:
            text = raw
        else:
            parts = []
            if qty is not None:
                parts.append(str(qty))
            if unit:
                parts.append(unit)
            text = " ".join(parts) if parts else "?"

        if prep and prep not in text:
            text += f", {prep}"

        optional = ing.get("optional", False)
        if optional:
            text += " *(optional)*"

        lines.append(f"- {text}")

    return "\n".join(lines)


def render_steps(steps: list[dict]) -> str:
    """Render the ``## Steps`` section as an ordered list.

    Examples:
        >>> render_steps([{"step_no": 1, "text": "Preheat oven."}])
        '## Steps\\n\\n1. Preheat oven.'
    """
    lines = ["## Steps", ""]
    for step in steps:
        lines.append(f"{step['step_no']}. {step['text']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full dossier
# ---------------------------------------------------------------------------


def render_dossier(
    recipe: dict,
    ingredients: list[dict] | None = None,
    steps: list[dict] | None = None,
) -> str:
    """Render a complete Markdown dossier for a recipe.

    Produces a document with the title as ``# heading`` followed by protected
    sections (Metadata, Source, Ingredients, Steps) and empty editable sections
    (Notes, Cook log).

    Args:
        recipe: Recipe row dict (keys matching ``recipes`` Parquet schema).
        ingredients: Ordered list of ingredient row dicts.
        steps: Ordered list of step row dicts.

    Returns:
        Full Markdown string ready to be written via ``dossier_ops.write_dossier``.

    Examples:
        >>> md = render_dossier({"title": "Pasta", "servings": 2}, [], [])
        >>> md.startswith("# Pasta")
        True
    """
    sections: list[str] = []

    # Title
    title = recipe.get("title", "Untitled Recipe")
    sections.append(f"# {title}")

    # Description
    desc = recipe.get("description")
    if desc and str(desc).strip():
        sections.append(str(desc).strip())

    # Protected sections
    sections.append(render_metadata(recipe))
    sections.append(render_source(recipe))

    if ingredients:
        sections.append(render_ingredients(ingredients))

    if steps:
        sections.append(render_steps(steps))

    # Editable sections (empty stubs so they exist for dossier_ops)
    sections.append("## Notes\n")
    sections.append("## Cook log\n")

    return "\n\n".join(sections) + "\n"
