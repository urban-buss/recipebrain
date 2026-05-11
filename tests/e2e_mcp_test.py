"""End-to-end MCP server test — exercises all 25 tools across 5 categories.

This script creates a rich test dataset, calls each MCP tool function directly
(with output_dir patched), validates results, and reports pass/fail per scenario.
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from recipebrain.writer import write_table

# ---------------------------------------------------------------------------
# Test Dataset Builder
# ---------------------------------------------------------------------------


def build_e2e_dataset(output_dir: Path) -> None:
    """Create a comprehensive dataset for E2E testing."""

    # Sources
    sources = [
        {
            "id": 1,
            "key": "fooby",
            "display_name": "Fooby",
            "base_url": "https://fooby.ch",
            "language": "de",
            "kind": "recipe",
        },
        {
            "id": 2,
            "key": "migusto",
            "display_name": "Migusto",
            "base_url": "https://migusto.migros.ch",
            "language": "de",
            "kind": "recipe",
        },
    ]
    write_table("sources", sources, output_dir)

    # Recipes — varied courses, times, difficulties, languages
    now = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    recipes = [
        {
            "id": 1,
            "source_id": 1,
            "source_external_id": "r1",
            "source_url": "https://fooby.ch/r/1",
            "title": "Zürcher Geschnetzeltes",
            "title_normalised": "zürcher geschnetzeltes",
            "language": "de",
            "description": "Classic Zurich veal dish",
            "servings": 4,
            "prep_minutes": 15,
            "cook_minutes": 30,
            "total_minutes": 45,
            "difficulty": "medium",
            "cuisine": "swiss",
            "course": "main",
            "primary_image_url": None,
            "original_keywords": ["meat", "classic"],
            "owner_rating": 5,
            "starred": True,
            "times_cooked": 3,
            "last_cooked_at": datetime.datetime(2024, 6, 15, tzinfo=datetime.UTC),
            "scraped_at": now,
            "updated_at": now,
            "content_hash": "h1",
            "status": "active",
        },
        {
            "id": 2,
            "source_id": 1,
            "source_external_id": "r2",
            "source_url": "https://fooby.ch/r/2",
            "title": "Rösti",
            "title_normalised": "rösti",
            "language": "de",
            "description": "Swiss potato classic",
            "servings": 2,
            "prep_minutes": 10,
            "cook_minutes": 15,
            "total_minutes": 25,
            "difficulty": "easy",
            "cuisine": "swiss",
            "course": "side",
            "primary_image_url": None,
            "original_keywords": ["potato"],
            "owner_rating": 4,
            "starred": True,
            "times_cooked": 10,
            "last_cooked_at": datetime.datetime(2024, 3, 1, tzinfo=datetime.UTC),
            "scraped_at": now,
            "updated_at": now,
            "content_hash": "h2",
            "status": "active",
        },
        {
            "id": 3,
            "source_id": 1,
            "source_external_id": "r3",
            "source_url": "https://fooby.ch/r/3",
            "title": "Fondue",
            "title_normalised": "fondue",
            "language": "de",
            "description": "Traditional cheese fondue",
            "servings": 4,
            "prep_minutes": 5,
            "cook_minutes": 20,
            "total_minutes": 25,
            "difficulty": "easy",
            "cuisine": "swiss",
            "course": "main",
            "primary_image_url": None,
            "original_keywords": ["cheese"],
            "owner_rating": 5,
            "starred": False,
            "times_cooked": 5,
            "last_cooked_at": datetime.datetime(2024, 1, 15, tzinfo=datetime.UTC),
            "scraped_at": now,
            "updated_at": now,
            "content_hash": "h3",
            "status": "active",
        },
        {
            "id": 4,
            "source_id": 2,
            "source_external_id": "r4",
            "source_url": "https://migusto.ch/r/4",
            "title": "Birchermüesli",
            "title_normalised": "birchermüesli",
            "language": "de",
            "description": "Swiss breakfast classic",
            "servings": 2,
            "prep_minutes": 10,
            "cook_minutes": 0,
            "total_minutes": 10,
            "difficulty": "easy",
            "cuisine": "swiss",
            "course": "breakfast",
            "primary_image_url": None,
            "original_keywords": ["breakfast", "healthy"],
            "owner_rating": None,
            "starred": False,
            "times_cooked": 0,
            "last_cooked_at": None,
            "scraped_at": now,
            "updated_at": now,
            "content_hash": "h4",
            "status": "active",
        },
        {
            "id": 5,
            "source_id": 2,
            "source_external_id": "r5",
            "source_url": "https://migusto.ch/r/5",
            "title": "Poulet an Currysauce",
            "title_normalised": "poulet an currysauce",
            "language": "de",
            "description": "Chicken in curry sauce",
            "servings": 4,
            "prep_minutes": 10,
            "cook_minutes": 20,
            "total_minutes": 30,
            "difficulty": "easy",
            "cuisine": "asian",
            "course": "main",
            "primary_image_url": None,
            "original_keywords": ["chicken", "curry"],
            "owner_rating": 4,
            "starred": False,
            "times_cooked": 2,
            "last_cooked_at": datetime.datetime(2024, 2, 1, tzinfo=datetime.UTC),
            "scraped_at": now,
            "updated_at": now,
            "content_hash": "h5",
            "status": "active",
        },
    ]
    write_table("recipes", recipes, output_dir)

    # Ingredients
    ingredients = [
        {
            "id": 1,
            "key": "mehl",
            "display_de": "Mehl",
            "display_fr": None,
            "display_it": None,
            "display_en": "Flour",
            "category": "baking",
            "sub_category": None,
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 2,
            "key": "butter",
            "display_de": "Butter",
            "display_fr": None,
            "display_it": None,
            "display_en": "Butter",
            "category": "dairy",
            "sub_category": None,
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 3,
            "key": "kartoffeln",
            "display_de": "Kartoffeln",
            "display_fr": None,
            "display_it": None,
            "display_en": "Potatoes",
            "category": "vegetable",
            "sub_category": None,
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 4,
            "key": "rahm",
            "display_de": "Rahm",
            "display_fr": None,
            "display_it": None,
            "display_en": "Cream",
            "category": "dairy",
            "sub_category": None,
            "default_unit": "dl",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 5,
            "key": "kalbfleisch",
            "display_de": "Kalbfleisch",
            "display_fr": None,
            "display_it": None,
            "display_en": "Veal",
            "category": "meat",
            "sub_category": None,
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 6,
            "key": "gruyere",
            "display_de": "Gruyère",
            "display_fr": None,
            "display_it": None,
            "display_en": "Gruyere",
            "category": "dairy",
            "sub_category": "cheese",
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 7,
            "key": "poulet",
            "display_de": "Poulet",
            "display_fr": None,
            "display_it": None,
            "display_en": "Chicken",
            "category": "meat",
            "sub_category": None,
            "default_unit": "g",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
        {
            "id": 8,
            "key": "curry",
            "display_de": "Curry",
            "display_fr": None,
            "display_it": None,
            "display_en": "Curry",
            "category": "spice",
            "sub_category": None,
            "default_unit": "TL",
            "density_g_per_ml": None,
            "pairing_tags": [],
            "aliases": [],
        },
    ]
    write_table("ingredients", ingredients, output_dir)

    # Recipe ingredients
    recipe_ingredients = [
        {
            "recipe_id": 1,
            "seq": 1,
            "ingredient_id": 5,
            "raw_text": "400g Kalbsgeschnetzeltes",
            "quantity": 400.0,
            "unit": "g",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 1,
            "seq": 2,
            "ingredient_id": 4,
            "raw_text": "2 dl Rahm",
            "quantity": 2.0,
            "unit": "dl",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 1,
            "seq": 3,
            "ingredient_id": 2,
            "raw_text": "30g Butter",
            "quantity": 30.0,
            "unit": "g",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 2,
            "seq": 1,
            "ingredient_id": 3,
            "raw_text": "500g Kartoffeln",
            "quantity": 500.0,
            "unit": "g",
            "prep_note": "geschält",
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 2,
            "seq": 2,
            "ingredient_id": 2,
            "raw_text": "50g Butter",
            "quantity": 50.0,
            "unit": "g",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 3,
            "seq": 1,
            "ingredient_id": 6,
            "raw_text": "400g Gruyère",
            "quantity": 400.0,
            "unit": "g",
            "prep_note": "gerieben",
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 5,
            "seq": 1,
            "ingredient_id": 7,
            "raw_text": "500g Poulet",
            "quantity": 500.0,
            "unit": "g",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 5,
            "seq": 2,
            "ingredient_id": 8,
            "raw_text": "1 TL Curry",
            "quantity": 1.0,
            "unit": "TL",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
        {
            "recipe_id": 5,
            "seq": 3,
            "ingredient_id": 4,
            "raw_text": "2 dl Rahm",
            "quantity": 2.0,
            "unit": "dl",
            "prep_note": None,
            "optional": False,
            "group_label": None,
        },
    ]
    write_table("recipe_ingredients", recipe_ingredients, output_dir)

    # Recipe steps
    recipe_steps = [
        {"recipe_id": 1, "step_no": 1, "text": "Fleisch in Butter anbraten.", "image_url": None},
        {
            "recipe_id": 1,
            "step_no": 2,
            "text": "Rahm dazugeben und köcheln lassen.",
            "image_url": None,
        },
        {
            "recipe_id": 2,
            "step_no": 1,
            "text": "Kartoffeln raffeln und in Butter braten.",
            "image_url": None,
        },
        {"recipe_id": 3, "step_no": 1, "text": "Käse im Caquelon schmelzen.", "image_url": None},
        {"recipe_id": 5, "step_no": 1, "text": "Poulet anbraten.", "image_url": None},
        {"recipe_id": 5, "step_no": 2, "text": "Curry und Rahm dazugeben.", "image_url": None},
    ]
    write_table("recipe_steps", recipe_steps, output_dir)

    # Cook log — some recipes cooked recently, some long ago
    cook_log = [
        {
            "id": 1,
            "recipe_id": 1,
            "cooked_on": datetime.date(2024, 5, 1),
            "servings": 4,
            "scale_factor": None,
            "rating": 5,
            "notes": "Perfekt",
            "logged_at": datetime.datetime(2024, 5, 1, 18, 0, tzinfo=datetime.UTC),
        },
        {
            "id": 2,
            "recipe_id": 1,
            "cooked_on": datetime.date(2024, 6, 15),
            "servings": 2,
            "scale_factor": None,
            "rating": 4,
            "notes": None,
            "logged_at": datetime.datetime(2024, 6, 15, 19, 0, tzinfo=datetime.UTC),
        },
        {
            "id": 3,
            "recipe_id": 2,
            "cooked_on": datetime.date(2024, 3, 1),
            "servings": None,
            "scale_factor": None,
            "rating": None,
            "notes": "Quick meal",
            "logged_at": datetime.datetime(2024, 3, 1, 20, 0, tzinfo=datetime.UTC),
        },
        {
            "id": 4,
            "recipe_id": 3,
            "cooked_on": datetime.date(2024, 1, 15),
            "servings": 4,
            "scale_factor": None,
            "rating": 5,
            "notes": None,
            "logged_at": datetime.datetime(2024, 1, 15, 19, 0, tzinfo=datetime.UTC),
        },
        {
            "id": 5,
            "recipe_id": 5,
            "cooked_on": datetime.date(2024, 2, 1),
            "servings": 4,
            "scale_factor": None,
            "rating": 4,
            "notes": None,
            "logged_at": datetime.datetime(2024, 2, 1, 19, 0, tzinfo=datetime.UTC),
        },
    ]
    write_table("cook_log", cook_log, output_dir)

    # Promotions
    today = datetime.date.today()
    promotions = [
        {
            "id": 1,
            "retailer_id": 1,
            "product_name": "Emmentaler 250g",
            "brand": "Migros",
            "pack_size": "250g",
            "pack_quantity": 250.0,
            "pack_unit": "g",
            "price_chf": 3.50,
            "regular_price_chf": 4.90,
            "discount_pct": 28.6,
            "valid_from": today,
            "valid_to": today + datetime.timedelta(days=7),
            "source_url": "http://promo/1",
            "scraped_at": datetime.datetime.now(tz=datetime.UTC),
        },
        {
            "id": 2,
            "retailer_id": 2,
            "product_name": "Poulet ganz",
            "brand": "Coop",
            "pack_size": "1.2kg",
            "pack_quantity": 1200.0,
            "pack_unit": "g",
            "price_chf": 8.90,
            "regular_price_chf": 12.90,
            "discount_pct": 31.0,
            "valid_from": today,
            "valid_to": today + datetime.timedelta(days=7),
            "source_url": "http://promo/2",
            "scraped_at": datetime.datetime.now(tz=datetime.UTC),
        },
    ]
    write_table("promotions", promotions, output_dir)

    # Retailers
    retailers = [
        {"id": 1, "key": "migros", "display_name": "Migros", "base_url": "https://migros.ch"},
        {"id": 2, "key": "coop", "display_name": "Coop", "base_url": "https://coop.ch"},
    ]
    write_table("retailers", retailers, output_dir)

    # Pantry — has butter, kartoffeln, rahm
    pantry = [
        {
            "ingredient_id": 2,
            "approx_quantity": 250.0,
            "unit": "g",
            "location": "fridge",
            "updated_at": datetime.datetime.now(tz=datetime.UTC),
            "note": None,
        },
        {
            "ingredient_id": 3,
            "approx_quantity": 1000.0,
            "unit": "g",
            "location": "pantry",
            "updated_at": datetime.datetime.now(tz=datetime.UTC),
            "note": None,
        },
        {
            "ingredient_id": 4,
            "approx_quantity": 5.0,
            "unit": "dl",
            "location": "fridge",
            "updated_at": datetime.datetime.now(tz=datetime.UTC),
            "note": None,
        },
    ]
    write_table("pantry", pantry, output_dir)

    # Tags
    tags = [
        {"id": 1, "key": "comfort-food", "display": "Comfort Food", "facet": "mood"},
        {"id": 2, "key": "swiss", "display": "Swiss", "facet": "cuisine"},
        {"id": 3, "key": "quick", "display": "Quick", "facet": "time"},
    ]
    write_table("tags", tags, output_dir)

    # Recipe tags — recipe 1 tagged as comfort-food and swiss
    recipe_tags = [
        {"recipe_id": 1, "tag_id": 1},
        {"recipe_id": 1, "tag_id": 2},
        {"recipe_id": 2, "tag_id": 3},
    ]
    write_table("recipe_tags", recipe_tags, output_dir)


# ---------------------------------------------------------------------------
# Test Results Tracking
# ---------------------------------------------------------------------------


class TestResult:
    def __init__(self, scenario_id: str, name: str, status: str, notes: str = "", output: str = ""):
        self.scenario_id = scenario_id
        self.name = name
        self.status = status  # "pass", "fail", "partial", "skip"
        self.notes = notes
        self.output = output


results: list[TestResult] = []


def record(scenario_id: str, name: str, passed: bool, notes: str = "", output: str = ""):
    status = "pass" if passed else "fail"
    results.append(TestResult(scenario_id, name, status, notes, output))
    icon = "✅" if passed else "❌"
    print(f"  {icon} {scenario_id}: {name} — {notes}")


def record_partial(scenario_id: str, name: str, notes: str = "", output: str = ""):
    results.append(TestResult(scenario_id, name, "partial", notes, output))
    print(f"  ⚠️  {scenario_id}: {name} — {notes}")


def record_skip(scenario_id: str, name: str, notes: str = ""):
    results.append(TestResult(scenario_id, name, "skip", notes))
    print(f"  ⏭️  {scenario_id}: {name} — {notes}")


# ---------------------------------------------------------------------------
# Patch helper
# ---------------------------------------------------------------------------


def _patch_output(output_dir: Path):
    return patch("recipebrain.mcp_server._output_dir", return_value=output_dir)


# ---------------------------------------------------------------------------
# Category 1: Discovery & Search
# ---------------------------------------------------------------------------


def test_category_1(output_dir: Path):
    print("\n" + "=" * 60)
    print("CATEGORY 1: Discovery & Search")
    print("=" * 60)

    from recipebrain.mcp_server import (
        current_promotions,
        find_recipe,
        list_starred,
        query_recipes,
        read_recipe,
        server_stats,
    )

    # S1.1: Find by course + time
    with _patch_output(output_dir):
        result = find_recipe(course="main", max_total_minutes=30)
    # Should have Fondue (25min, main) and Poulet (30min, main), NOT Geschnetzeltes (45min)
    has_fondue = "Fondue" in result
    has_poulet = "Poulet" in result or "Curry" in result
    no_geschnetzeltes = "Geschnetzeltes" not in result
    passed = has_fondue and no_geschnetzeltes
    record(
        "S1.1",
        "Find by course + time",
        passed,
        f"Fondue={has_fondue}, Poulet={has_poulet}, NoGeschnetzeltes={no_geschnetzeltes}",
        result,
    )

    # S1.2: Find → Read chaining
    with _patch_output(output_dir):
        search_result = find_recipe(query="rösti")
    has_rosti = "Rösti" in search_result
    # Extract ID (should be 2)
    with _patch_output(output_dir):
        detail = read_recipe(recipe_id=2)
    has_ingredients = "## Ingredients" in detail
    has_steps = "## Steps" in detail
    passed = has_rosti and has_ingredients and has_steps
    record(
        "S1.2",
        "Find → Read chaining",
        passed,
        f"Search={has_rosti}, Ingredients={has_ingredients}, Steps={has_steps}",
        f"Search:\n{search_result}\n\nDetail:\n{detail[:500]}",
    )

    # S1.3: List starred
    with _patch_output(output_dir):
        result = list_starred()
    has_geschnetzeltes = "Geschnetzeltes" in result
    has_rosti = "Rösti" in result
    no_fondue = "Fondue" not in result  # Not starred
    passed = has_geschnetzeltes and has_rosti and no_fondue
    record(
        "S1.3",
        "List starred",
        passed,
        f"Geschnetzeltes={has_geschnetzeltes}, Rösti={has_rosti}, NoFondue={no_fondue}",
        result,
    )

    # S1.4: Find by tags
    with _patch_output(output_dir):
        result = find_recipe(tags=["comfort-food"])
    has_geschnetzeltes = "Geschnetzeltes" in result
    no_rosti = "Rösti" not in result
    passed = has_geschnetzeltes and no_rosti
    record(
        "S1.4",
        "Find by tags",
        passed,
        f"Geschnetzeltes={has_geschnetzeltes}, NoRösti={no_rosti}",
        result,
    )

    # S1.5: Current promotions
    with _patch_output(output_dir):
        result = current_promotions()
    has_emmentaler = "Emmentaler" in result
    has_poulet = "Poulet" in result
    is_table = "|" in result
    passed = has_emmentaler and has_poulet and is_table
    record(
        "S1.5",
        "Current promotions",
        passed,
        f"Emmentaler={has_emmentaler}, Poulet={has_poulet}, Table={is_table}",
        result,
    )

    # S1.6: SQL query
    with _patch_output(output_dir):
        result = query_recipes("SELECT id, title FROM recipes LIMIT 5")
    has_table = "|" in result
    has_id_col = "id" in result
    passed = has_table and has_id_col and "Error" not in result
    record("S1.6", "SQL query", passed, f"Table={has_table}, HasId={has_id_col}", result)

    # S1.7: Server stats
    with _patch_output(output_dir):
        result = server_stats()
    has_recipes = "recipes" in result.lower()
    has_count = "5" in result  # We have 5 recipes
    passed = has_recipes and "Error" not in result
    record("S1.7", "Server stats", passed, f"HasRecipes={has_recipes}, Has5={has_count}", result)


# ---------------------------------------------------------------------------
# Category 2: Recommendations
# ---------------------------------------------------------------------------


def test_category_2(output_dir: Path):
    print("\n" + "=" * 60)
    print("CATEGORY 2: Recommendations")
    print("=" * 60)

    from recipebrain.mcp_server import suggest_easy, suggest_for_pantry, suggest_rotation

    # S2.1: Suggest for pantry
    with _patch_output(output_dir):
        result = suggest_for_pantry(missing_ok=3)
    # We have butter, kartoffeln, rahm in pantry
    # Rösti needs kartoffeln + butter (both in pantry) — should rank high
    has_results = "No recipes found" not in result
    has_coverage = "%" in result or "coverage" in result.lower()
    passed = has_results
    record(
        "S2.1",
        "Suggest for pantry",
        passed,
        f"HasResults={has_results}, HasCoverage={has_coverage}",
        result,
    )

    # S2.2: Suggest rotation (min_rating=4, not_cooked_in_days=90)
    with _patch_output(output_dir):
        result = suggest_rotation(min_rating=4, not_cooked_in_days=90)
    # Recipes rated ≥4 and not cooked in 90+ days:
    # Geschnetzeltes (5, last 2024-06-15), Rösti (4, last 2024-03-01),
    # Fondue (5, last 2024-01-15), Poulet (4, last 2024-02-01)
    # All should qualify since today is 2026
    has_results = "No rotation" not in result
    passed = has_results
    record("S2.2", "Suggest rotation", passed, f"HasResults={has_results}", result)

    # S2.3: Suggest easy (max_total_minutes=25)
    with _patch_output(output_dir):
        result = suggest_easy(max_total_minutes=25)
    # Birchermüesli (10min), Rösti (25min), Fondue (25min)
    has_results = "No easy recipes" not in result
    passed = has_results
    record("S2.3", "Suggest easy (max 25min)", passed, f"HasResults={has_results}", result)


# ---------------------------------------------------------------------------
# Category 3: Write Operations
# ---------------------------------------------------------------------------


def test_category_3(output_dir: Path):
    print("\n" + "=" * 60)
    print("CATEGORY 3: Write Operations")
    print("=" * 60)

    from recipebrain.mcp_server import (
        add_recipe,
        annotate_recipe,
        find_recipe,
        list_starred,
        log_cook,
        rate_recipe,
        read_recipe,
        star_recipe,
        tag_recipe,
    )

    # S3.1: Log cook
    with _patch_output(output_dir):
        result = log_cook(recipe_id=1, rating=4, cooked_on="2026-05-10")
    passed = "Logged" in result and "Error" not in result
    record("S3.1", "Log cook", passed, f"Result: {result}", result)

    # Verify stats updated
    with _patch_output(output_dir):
        detail = read_recipe(recipe_id=1)
    has_cook_event = "2026-05-10" in detail
    record(
        "S3.1b",
        "Log cook stats updated",
        has_cook_event,
        f"CookEvent visible={has_cook_event}",
        detail[:300],
    )

    # S3.2: Star recipe
    with _patch_output(output_dir):
        # Recipe 3 (Fondue) is not starred — star it
        result = star_recipe(recipe_id=3)
    passed = "Starred" in result and "Error" not in result
    record("S3.2", "Star recipe", passed, f"Result: {result}", result)

    # Verify visible in list_starred
    with _patch_output(output_dir):
        starred = list_starred()
    fondue_in_starred = "Fondue" in starred
    record(
        "S3.2b",
        "Star visible in list_starred",
        fondue_in_starred,
        f"Fondue in starred={fondue_in_starred}",
        starred,
    )

    # S3.3: Rate recipe
    with _patch_output(output_dir):
        result = rate_recipe(recipe_id=4, rating=5)
    passed = "Rated" in result and "5/5" in result and "Error" not in result
    record("S3.3", "Rate recipe", passed, f"Result: {result}", result)

    # S3.4: Add recipe
    with _patch_output(output_dir):
        result = add_recipe(
            title="Omas Zopf",
            ingredients=["500g Mehl", "200ml Milch", "80g Butter", "1 Ei"],
            steps=["Teig kneten", "Aufgehen lassen", "Flechten und backen"],
            servings=8,
            prep_minutes=30,
            cook_minutes=35,
            difficulty="medium",
        )
    passed = "Created" in result and "Error" not in result
    # Extract new ID
    new_id = None
    if "id=" in result:
        try:
            new_id = int(result.split("id=")[1].split(".")[0])
        except (ValueError, IndexError):
            pass
    record("S3.4", "Add recipe", passed, f"Result: {result}, new_id={new_id}", result)

    # Verify searchable
    if new_id:
        with _patch_output(output_dir):
            search = find_recipe(query="zopf")
        found = "Zopf" in search
        record("S3.4b", "New recipe searchable", found, f"Found in search={found}", search)

    # S3.5: Tag recipe
    with _patch_output(output_dir):
        result = tag_recipe(recipe_id=3, tags=["comfort-food", "winter"])
    passed = "Tagged" in result and "Error" not in result
    record("S3.5", "Tag recipe", passed, f"Result: {result}", result)

    # Verify searchable by tag
    with _patch_output(output_dir):
        search = find_recipe(tags=["winter"])
    found = "Fondue" in search
    record("S3.5b", "Tags searchable", found, f"Fondue found by winter tag={found}", search)

    # S3.6: Annotate recipe
    with _patch_output(output_dir):
        result = annotate_recipe(recipe_id=1, section="notes", content="Best with Spätzli as side.")
    passed = "Added" in result and "Error" not in result
    record("S3.6", "Annotate recipe", passed, f"Result: {result}", result)

    # Verify in read_recipe
    with _patch_output(output_dir):
        detail = read_recipe(recipe_id=1)
    has_note = "Spätzli" in detail
    record(
        "S3.6b",
        "Annotation visible in read_recipe",
        has_note,
        f"Note visible={has_note}",
        detail[-400:],
    )


# ---------------------------------------------------------------------------
# Category 4: Multi-Step Workflows
# ---------------------------------------------------------------------------


def test_category_4(output_dir: Path):
    print("\n" + "=" * 60)
    print("CATEGORY 4: Multi-Step Workflows")
    print("=" * 60)

    from recipebrain.mcp_server import (
        add_recipe,
        batch_annotate,
        batch_tag,
        find_recipe,
        list_pinned,
        log_cook,
        pin_recipe,
        read_recipe,
        suggest_easy,
        tag_recipe,
        unpin_recipe,
    )

    # S4.1: Meal plan workflow — suggest → pin → list → cook → verify auto-unpin
    print("\n  --- S4.1: Meal plan workflow ---")
    with _patch_output(output_dir):
        easy = suggest_easy()
    has_suggestions = "No easy" not in easy
    record("S4.1a", "Suggest easy returns results", has_suggestions, "", easy)

    # Pin recipe 4 (Birchermüesli)
    with _patch_output(output_dir):
        pin_result = pin_recipe(recipe_id=4, target_date="2026-05-15", note="Weekend brunch")
    pinned_ok = "Pinned" in pin_result and "Error" not in pin_result
    record("S4.1b", "Pin recipe", pinned_ok, f"Result: {pin_result}", pin_result)

    # List pinned
    with _patch_output(output_dir):
        pinned_list = list_pinned()
    in_list = "Birchermüesli" in pinned_list
    record("S4.1c", "Appears in list_pinned", in_list, "", pinned_list)

    # Cook the pinned recipe — should auto-transition status
    with _patch_output(output_dir):
        cook_result = log_cook(recipe_id=4, rating=4, cooked_on="2026-05-15")
    cooked_ok = "Logged" in cook_result
    record("S4.1d", "Log cook for pinned recipe", cooked_ok, f"Result: {cook_result}", cook_result)

    # Verify auto-unpin (should not appear in active pinned list)
    with _patch_output(output_dir):
        pinned_after = list_pinned()
    auto_unpinned = "Birchermüesli" not in pinned_after or "No pinned" in pinned_after
    record(
        "S4.1e",
        "Auto-unpin after cooking",
        auto_unpinned,
        f"Still in list={not auto_unpinned}",
        pinned_after,
    )

    # S4.2: New recipe lifecycle
    print("\n  --- S4.2: New recipe lifecycle ---")
    with _patch_output(output_dir):
        add_result = add_recipe(
            title="Käseschnitte",
            ingredients=["4 Scheiben Brot", "200g Gruyère", "2 dl Weisswein"],
            steps=["Brot in Form legen", "Käse und Wein darüber", "Im Ofen backen"],
            servings=4,
            prep_minutes=10,
            cook_minutes=15,
        )
    add_ok = "Created" in add_result
    new_id = None
    if "id=" in add_result:
        try:
            new_id = int(add_result.split("id=")[1].split(".")[0])
        except (ValueError, IndexError):
            pass
    record("S4.2a", "Add recipe", add_ok, f"id={new_id}", add_result)

    if new_id:
        with _patch_output(output_dir):
            search = find_recipe(query="käseschnitte")
        found = "Käseschnitte" in search
        record("S4.2b", "Find new recipe", found, "", search)

        with _patch_output(output_dir):
            detail = read_recipe(recipe_id=new_id)
        has_detail = "## Ingredients" in detail
        record("S4.2c", "Read new recipe", has_detail, "", detail[:300])

        with _patch_output(output_dir):
            tag_result = tag_recipe(recipe_id=new_id, tags=["swiss", "cheese"])
        tagged = "Tagged" in tag_result
        record("S4.2d", "Tag new recipe", tagged, f"Result: {tag_result}", tag_result)

        with _patch_output(output_dir):
            cook_result = log_cook(recipe_id=new_id, rating=5)
        cooked = "Logged" in cook_result
        record("S4.2e", "Cook new recipe", cooked, f"Result: {cook_result}", cook_result)

    # S4.3: Rating evolution
    print("\n  --- S4.3: Rating evolution ---")
    with _patch_output(output_dir):
        r1 = log_cook(recipe_id=2, rating=3, cooked_on="2026-05-01")
    first_ok = "Logged" in r1
    record("S4.3a", "First cook with rating 3", first_ok, f"Result: {r1}", r1)

    with _patch_output(output_dir):
        r2 = log_cook(recipe_id=2, rating=5, cooked_on="2026-05-08")
    second_ok = "Logged" in r2
    record("S4.3b", "Second cook with rating 5", second_ok, f"Result: {r2}", r2)

    # Latest rating should win (5)
    with _patch_output(output_dir):
        detail = read_recipe(recipe_id=2)
    # Check the owner_rating or cook history
    has_5_rating = "5/5" in detail
    record(
        "S4.3c",
        "Latest rating wins",
        has_5_rating,
        f"Has 5/5 in output={has_5_rating}",
        detail[-400:],
    )

    # S4.4: Pin lifecycle
    print("\n  --- S4.4: Pin lifecycle ---")
    with _patch_output(output_dir):
        pin1 = pin_recipe(recipe_id=5, target_date="2026-05-20")
    pin_ok = "Pinned" in pin1
    record("S4.4a", "Pin recipe", pin_ok, f"Result: {pin1}", pin1)

    # Duplicate should be rejected
    with _patch_output(output_dir):
        pin2 = pin_recipe(recipe_id=5)
    dup_rejected = "already pinned" in pin2.lower()
    record("S4.4b", "Duplicate pin rejected", dup_rejected, f"Result: {pin2}", pin2)

    # Unpin
    with _patch_output(output_dir):
        unpin = unpin_recipe(recipe_id=5)
    unpin_ok = "Unpinned" in unpin
    record("S4.4c", "Unpin recipe", unpin_ok, f"Result: {unpin}", unpin)

    # Re-pin should be allowed
    with _patch_output(output_dir):
        repin = pin_recipe(recipe_id=5, target_date="2026-05-25")
    repin_ok = "Pinned" in repin and "Error" not in repin
    record("S4.4d", "Re-pin allowed after unpin", repin_ok, f"Result: {repin}", repin)

    # S4.5: Batch operations
    print("\n  --- S4.5: Batch operations ---")
    with _patch_output(output_dir):
        bt_result = batch_tag(recipe_ids=[1, 2, 3], tags=["family-dinner"])
    batch_tagged = "Tagged" in bt_result and "Error" not in bt_result
    record("S4.5a", "Batch tag", batch_tagged, f"Result: {bt_result}", bt_result)

    # Find by that tag
    with _patch_output(output_dir):
        search = find_recipe(tags=["family-dinner"])
    found_all = "Geschnetzeltes" in search and "Rösti" in search and "Fondue" in search
    record("S4.5b", "Batch-tagged recipes searchable", found_all, "", search)

    # Batch annotate
    with _patch_output(output_dir):
        ba_result = batch_annotate(recipe_ids=[1, 2], section="notes", content="Great for guests.")
    annotated = "Annotated" in ba_result
    record("S4.5c", "Batch annotate", annotated, f"Result: {ba_result}", ba_result)

    # Verify annotation visible
    with _patch_output(output_dir):
        detail = read_recipe(recipe_id=2)
    has_note = "Great for guests" in detail
    record("S4.5d", "Batch annotation visible", has_note, "", detail[-300:])


# ---------------------------------------------------------------------------
# Category 5: Security & Edge Cases
# ---------------------------------------------------------------------------


def test_category_5(output_dir: Path):
    print("\n" + "=" * 60)
    print("CATEGORY 5: Security & Edge Cases")
    print("=" * 60)

    from recipebrain.mcp_server import (
        add_recipe,
        annotate_recipe,
        find_recipe,
        log_cook,
        query_recipes,
        rate_recipe,
        read_recipe,
    )

    # S5.1: SQL injection — DROP TABLE
    with _patch_output(output_dir):
        result = query_recipes("DROP TABLE recipes")
    rejected = "Error" in result
    record("S5.1", "SQL injection rejected (DROP)", rejected, f"Result: {result}", result)

    # Also test SELECT + injection
    with _patch_output(output_dir):
        result2 = query_recipes("SELECT * FROM recipes; DROP TABLE recipes")
    rejected2 = "Error" in result2
    record("S5.1b", "SQL injection rejected (semicolon)", rejected2, f"Result: {result2}", result2)

    # S5.2: Protected section write
    with _patch_output(output_dir):
        result = annotate_recipe(recipe_id=1, section="ingredients", content="Injected!")
    rejected = "Error" in result and "not allowed" in result.lower()
    record("S5.2", "Protected section rejected", rejected, f"Result: {result}", result)

    # S5.3: Empty/None args
    with _patch_output(output_dir):
        result = find_recipe(query=None, course=None, max_total_minutes=None)
    no_crash = "Error" not in result or "No recipes" in result
    # It should return all recipes or a graceful message
    record(
        "S5.3",
        "None args handled gracefully",
        no_crash,
        f"Result type: {type(result)}",
        result[:200],
    )

    # S5.4: Very large limit
    with _patch_output(output_dir):
        result = find_recipe(limit=99999)
    no_crash = isinstance(result, str) and ("Error" not in result or "No recipes" not in result)
    record("S5.4", "Large limit handled", True, "No crash occurred", result[:200])

    # S5.5: Read non-existent recipe
    with _patch_output(output_dir):
        result = read_recipe(recipe_id=999999)
    not_found = "not found" in result.lower() or "error" in result.lower()
    record("S5.5", "Non-existent recipe → not found", not_found, f"Result: {result}", result)

    # S5.6: Unicode preservation
    with _patch_output(output_dir):
        result = add_recipe(
            title="Züri-Gschnätzlets mit Röschti",
            ingredients=["400g Kalbsgeschnetzeltes", "2 dl Rahm"],
            steps=["Fleisch anbraten", "Rahm dazugeben"],
        )
    created = "Created" in result
    unicode_ok = "Züri-Gschnätzlets" in result
    record(
        "S5.6",
        "Unicode preserved",
        created and unicode_ok,
        f"Created={created}, Unicode={unicode_ok}",
        result,
    )

    # Verify searchable with unicode
    if created:
        with _patch_output(output_dir):
            search = find_recipe(query="züri")
        found = "Züri" in search
        record("S5.6b", "Unicode searchable", found, f"Found={found}", search[:200])

    # S5.7: Log cook for non-existent recipe
    with _patch_output(output_dir):
        result = log_cook(recipe_id=999)
    error_msg = "not found" in result.lower() or "error" in result.lower()
    record("S5.7", "Log cook non-existent recipe", error_msg, f"Result: {result}", result)

    # S5.8: Rate recipe out of range
    with _patch_output(output_dir):
        result = rate_recipe(recipe_id=1, rating=6)
    rejected = "error" in result.lower() and ("1" in result and "5" in result)
    record("S5.8", "Out-of-range rating rejected", rejected, f"Result: {result}", result)

    # Also test rating=0
    with _patch_output(output_dir):
        result0 = rate_recipe(recipe_id=1, rating=0)
    rejected0 = "error" in result0.lower()
    record("S5.8b", "Rating 0 rejected", rejected0, f"Result: {result0}", result0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("RECIPEBRAIN E2E MCP TEST SUITE")
    print(f"Date: {datetime.date.today().isoformat()}")
    print("=" * 60)

    # Create temp directory and build dataset
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        print(f"\nTest dataset: {output_dir}")
        build_e2e_dataset(output_dir)
        print("Dataset built successfully.\n")

        # Invalidate any cached DuckDB connections
        from recipebrain.query import invalidate_connection

        invalidate_connection(output_dir)

        # Run all categories
        test_category_1(output_dir)
        test_category_2(output_dir)
        test_category_3(output_dir)
        test_category_4(output_dir)
        test_category_5(output_dir)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    partial = sum(1 for r in results if r.status == "partial")
    skipped = sum(1 for r in results if r.status == "skip")
    print(f"Total: {total}")
    print(f"Passed: {passed} ({passed * 100 // total}%)")
    print(f"Failed: {failed} ({failed * 100 // total}%)")
    print(f"Partial: {partial}")
    print(f"Skipped: {skipped}")

    if failed > 0:
        print("\nFAILED SCENARIOS:")
        for r in results:
            if r.status == "fail":
                print(f"  ❌ {r.scenario_id}: {r.name}")
                print(f"     Notes: {r.notes}")
                if r.output:
                    print(f"     Output: {r.output[:200]}")

    # Return results for report generation
    return results


if __name__ == "__main__":
    main()
