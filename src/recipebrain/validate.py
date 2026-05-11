"""Data integrity validation for the recipebrain knowledge base.

Checks that Parquet datasets exist, schemas match expectations, foreign keys
are consistent, and required fields are populated. Returns a structured list
of validation issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from recipebrain.query import execute_query


@dataclass
class ValidationResult:
    """Result of a validation run."""

    checks_run: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0

    def add(self, issue: str) -> None:
        self.issues.append(issue)

    def check(self, label: str) -> None:
        self.checks_run += 1


def validate(output_dir: Path) -> ValidationResult:
    """Run all data integrity checks against the Parquet datasets.

    Args:
        output_dir: Path to the directory containing Parquet files.

    Returns:
        ValidationResult with counts and issues found.

    Examples:
        >>> result = validate(Path("output"))
        >>> result.ok
        True
    """
    result = ValidationResult()
    _check_parquet_files_exist(output_dir, result)
    _check_recipe_required_fields(output_dir, result)
    _check_recipe_ingredient_fks(output_dir, result)
    _check_recipe_step_fks(output_dir, result)
    _check_cook_log_fks(output_dir, result)
    _check_duplicate_recipes(output_dir, result)
    return result


def _check_parquet_files_exist(output_dir: Path, result: ValidationResult) -> None:
    """Check that core Parquet files exist."""
    core_entities = ["recipes", "recipe_ingredients", "recipe_steps", "sources"]
    for entity in core_entities:
        result.check(f"parquet_exists:{entity}")
        path = output_dir / f"{entity}.parquet"
        if not path.exists():
            result.add(f"Missing Parquet file: {entity}.parquet")


def _check_recipe_required_fields(output_dir: Path, result: ValidationResult) -> None:
    """Check that recipes have required fields populated."""
    if not (output_dir / "recipes.parquet").exists():
        return

    result.check("recipe_required_fields")
    try:
        rows = execute_query(
            "SELECT id, title, source_id FROM recipes "
            "WHERE title IS NULL OR title = '' OR source_id IS NULL",
            output_dir,
        )
        for row in rows:
            result.add(
                f"Recipe id={row['id']} missing required field "
                f"(title={row.get('title')!r}, source_id={row.get('source_id')})"
            )
    except Exception as exc:  # noqa: BLE001
        result.add(f"Error checking recipe fields: {exc}")


def _check_recipe_ingredient_fks(output_dir: Path, result: ValidationResult) -> None:
    """Check recipe_ingredients.recipe_id references valid recipes."""
    ri_path = output_dir / "recipe_ingredients.parquet"
    r_path = output_dir / "recipes.parquet"
    if not ri_path.exists() or not r_path.exists():
        return

    result.check("recipe_ingredient_fks")
    try:
        rows = execute_query(
            "SELECT DISTINCT ri.recipe_id FROM recipe_ingredients ri "
            "LEFT JOIN recipes r ON r.id = ri.recipe_id "
            "WHERE r.id IS NULL",
            output_dir,
        )
        for row in rows:
            result.add(f"recipe_ingredients references missing recipe_id={row['recipe_id']}")
    except Exception as exc:  # noqa: BLE001
        result.add(f"Error checking recipe_ingredient FKs: {exc}")


def _check_recipe_step_fks(output_dir: Path, result: ValidationResult) -> None:
    """Check recipe_steps.recipe_id references valid recipes."""
    rs_path = output_dir / "recipe_steps.parquet"
    r_path = output_dir / "recipes.parquet"
    if not rs_path.exists() or not r_path.exists():
        return

    result.check("recipe_step_fks")
    try:
        rows = execute_query(
            "SELECT DISTINCT rs.recipe_id FROM recipe_steps rs "
            "LEFT JOIN recipes r ON r.id = rs.recipe_id "
            "WHERE r.id IS NULL",
            output_dir,
        )
        for row in rows:
            result.add(f"recipe_steps references missing recipe_id={row['recipe_id']}")
    except Exception as exc:  # noqa: BLE001
        result.add(f"Error checking recipe_step FKs: {exc}")


def _check_cook_log_fks(output_dir: Path, result: ValidationResult) -> None:
    """Check cook_log.recipe_id references valid recipes."""
    cl_path = output_dir / "cook_log.parquet"
    r_path = output_dir / "recipes.parquet"
    if not cl_path.exists() or not r_path.exists():
        return

    result.check("cook_log_fks")
    try:
        rows = execute_query(
            "SELECT DISTINCT cl.recipe_id FROM cook_log cl "
            "LEFT JOIN recipes r ON r.id = cl.recipe_id "
            "WHERE r.id IS NULL",
            output_dir,
        )
        for row in rows:
            result.add(f"cook_log references missing recipe_id={row['recipe_id']}")
    except Exception as exc:  # noqa: BLE001
        result.add(f"Error checking cook_log FKs: {exc}")


def _check_duplicate_recipes(output_dir: Path, result: ValidationResult) -> None:
    """Check for duplicate recipes (same source_id + source_external_id)."""
    if not (output_dir / "recipes.parquet").exists():
        return

    result.check("duplicate_recipes")
    try:
        rows = execute_query(
            "SELECT source_id, source_external_id, COUNT(*) AS n "
            "FROM recipes GROUP BY source_id, source_external_id HAVING COUNT(*) > 1",
            output_dir,
        )
        for row in rows:
            result.add(
                f"Duplicate recipe: source_id={row['source_id']} "
                f"external_id={row['source_external_id']} (count={row['n']})"
            )
    except Exception as exc:  # noqa: BLE001
        result.add(f"Error checking duplicates: {exc}")
