"""Test data builders for recipebrain Parquet datasets.

Provides ``make_*()`` factory functions with sensible defaults and
``**overrides`` for each entity. Use ``write_dataset()`` to write a
complete minimal dataset to a temporary directory.

Examples:
    >>> recipe = make_recipe(title="Pasta", language="de")
    >>> write_dataset(tmp_path, recipes=[recipe])
"""

from __future__ import annotations

import datetime
from pathlib import Path

from recipebrain.writer import write_table


def make_source(**overrides: object) -> dict:
    """Build a source row with defaults."""
    defaults: dict = {
        "id": 1,
        "key": "fooby",
        "display_name": "Fooby",
        "base_url": "https://fooby.ch",
        "language": "de",
        "kind": "scraped",
    }
    defaults.update(overrides)
    return defaults


def make_recipe(**overrides: object) -> dict:
    """Build a recipe row with defaults."""
    defaults: dict = {
        "id": 1,
        "source_id": 1,
        "source_external_id": "r1",
        "source_url": "https://fooby.ch/r/1",
        "title": "Test Recipe",
        "title_normalised": "test recipe",
        "language": "de",
        "description": "A test recipe",
        "servings": 4,
        "prep_minutes": 10,
        "cook_minutes": 20,
        "total_minutes": 30,
        "difficulty": "easy",
        "cuisine": "swiss",
        "course": "main",
        "primary_image_url": None,
        "original_keywords": [],
        "owner_rating": None,
        "starred": False,
        "times_cooked": 0,
        "last_cooked_at": None,
        "scraped_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        "updated_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        "content_hash": "abc123",
        "status": "active",
    }
    defaults.update(overrides)
    return defaults


def make_ingredient(**overrides: object) -> dict:
    """Build an ingredient row with defaults."""
    defaults: dict = {
        "id": 1,
        "key": "mehl",
        "display_de": "Mehl",
        "display_fr": None,
        "display_it": None,
        "display_en": None,
        "category": "baking",
        "sub_category": None,
        "default_unit": "g",
        "density_g_per_ml": None,
        "pairing_tags": [],
        "aliases": [],
    }
    defaults.update(overrides)
    return defaults


def make_recipe_ingredient(**overrides: object) -> dict:
    """Build a recipe_ingredient row with defaults."""
    defaults: dict = {
        "recipe_id": 1,
        "seq": 1,
        "ingredient_id": None,
        "raw_text": "200 g Mehl",
        "quantity": 200.0,
        "unit": "g",
        "prep_note": None,
        "optional": False,
        "group_label": None,
    }
    defaults.update(overrides)
    return defaults


def make_recipe_step(**overrides: object) -> dict:
    """Build a recipe_step row with defaults."""
    defaults: dict = {
        "recipe_id": 1,
        "step_no": 1,
        "text": "Mix everything.",
        "image_url": None,
    }
    defaults.update(overrides)
    return defaults


def make_cook_log(**overrides: object) -> dict:
    """Build a cook_log row with defaults."""
    defaults: dict = {
        "id": 1,
        "recipe_id": 1,
        "cooked_on": datetime.date(2025, 3, 15),
        "servings": 4,
        "scale_factor": None,
        "rating": 4,
        "notes": None,
        "logged_at": datetime.datetime(2025, 3, 15, 19, 0, tzinfo=datetime.UTC),
    }
    defaults.update(overrides)
    return defaults


def make_tag(**overrides: object) -> dict:
    """Build a tag row with defaults."""
    defaults: dict = {
        "id": 1,
        "key": "quick",
        "display": "Quick",
        "facet": "time",
    }
    defaults.update(overrides)
    return defaults


def make_promotion(**overrides: object) -> dict:
    """Build a promotion row with defaults."""
    defaults: dict = {
        "id": 1,
        "retailer_id": 1,
        "product_name": "Butter",
        "brand": None,
        "pack_size": "250g",
        "pack_quantity": 1.0,
        "pack_unit": "piece",
        "price_chf": 2.50,
        "regular_price_chf": 3.50,
        "discount_pct": 28.6,
        "valid_from": datetime.date(2025, 1, 1),
        "valid_to": datetime.date(2025, 1, 7),
        "source_url": "https://profital.ch/p/1",
        "scraped_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
    }
    defaults.update(overrides)
    return defaults


def write_dataset(
    output_dir: Path,
    *,
    sources: list[dict] | None = None,
    recipes: list[dict] | None = None,
    recipe_steps: list[dict] | None = None,
    recipe_ingredients: list[dict] | None = None,
    ingredients: list[dict] | None = None,
    cook_log: list[dict] | None = None,
    tags: list[dict] | None = None,
    recipe_tags: list[dict] | None = None,
    promotions: list[dict] | None = None,
) -> None:
    """Write multiple entity tables to *output_dir* in one call.

    Only writes entities that are explicitly provided (non-None).
    """
    if sources is not None:
        write_table("sources", sources, output_dir)
    if recipes is not None:
        write_table("recipes", recipes, output_dir)
    if recipe_steps is not None:
        write_table("recipe_steps", recipe_steps, output_dir)
    if recipe_ingredients is not None:
        write_table("recipe_ingredients", recipe_ingredients, output_dir)
    if ingredients is not None:
        write_table("ingredients", ingredients, output_dir)
    if cook_log is not None:
        write_table("cook_log", cook_log, output_dir)
    if tags is not None:
        write_table("tags", tags, output_dir)
    if recipe_tags is not None:
        write_table("recipe_tags", recipe_tags, output_dir)
    if promotions is not None:
        write_table("promotions", promotions, output_dir)
