"""Tests for MCP server tools."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from recipebrain.writer import SCHEMAS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Create a temp output dir with minimal recipe data."""
    # recipes
    recipes_data = {
        "id": [1, 2, 3],
        "source_id": [1, 1, 1],
        "source_external_id": ["r1", "r2", "r3"],
        "source_url": ["http://x/1", "http://x/2", "http://x/3"],
        "title": ["Zürcher Geschnetzeltes", "Rösti", "Fondue"],
        "title_normalised": ["zürcher geschnetzeltes", "rösti", "fondue"],
        "language": ["de", "de", "de"],
        "description": ["Classic dish", "Potato dish", "Cheese dish"],
        "servings": [4, 2, 4],
        "prep_minutes": [15, 10, 5],
        "cook_minutes": [30, 20, 30],
        "total_minutes": [45, 30, 35],
        "difficulty": ["medium", "easy", "easy"],
        "cuisine": ["swiss", "swiss", "swiss"],
        "course": ["main", "side", "main"],
        "primary_image_url": [None, None, None],
        "original_keywords": [["meat", "classic"], ["potato"], ["cheese"]],
        "owner_rating": [5, 4, 5],
        "starred": [False, False, False],
        "times_cooked": [3, 10, 5],
        "last_cooked_at": [None, None, None],
        "scraped_at": [datetime.datetime(2024, 1, 1)] * 3,
        "updated_at": [datetime.datetime(2024, 1, 1)] * 3,
        "content_hash": ["h1", "h2", "h3"],
        "status": ["active", "active", "active"],
    }
    table = pa.table(recipes_data, schema=SCHEMAS["recipes"])
    pq.write_table(table, tmp_path / "recipes.parquet")

    # recipe_ingredients
    ri_data = {
        "recipe_id": [1, 1, 2],
        "seq": [1, 2, 1],
        "ingredient_id": [10, 11, 12],
        "raw_text": ["400g Kalbsgeschnetzeltes", "2 dl Rahm", "500g Kartoffeln"],
        "quantity": [400.0, 2.0, 500.0],
        "unit": ["g", "dl", "g"],
        "prep_note": [None, None, "geschält"],
        "optional": [False, False, False],
        "group_label": [None, None, None],
    }
    table = pa.table(ri_data, schema=SCHEMAS["recipe_ingredients"])
    pq.write_table(table, tmp_path / "recipe_ingredients.parquet")

    # recipe_steps
    steps_data = {
        "recipe_id": [1, 1],
        "step_no": [1, 2],
        "text": ["Fleisch anbraten", "Rahm dazugeben und köcheln lassen"],
        "image_url": [None, None],
    }
    table = pa.table(steps_data, schema=SCHEMAS["recipe_steps"])
    pq.write_table(table, tmp_path / "recipe_steps.parquet")

    # promotions
    promo_data = {
        "id": [1, 2],
        "retailer_id": [1, 2],
        "product_name": ["Emmentaler 250g", "Poulet ganz"],
        "brand": ["Migros", "Coop"],
        "pack_size": ["250g", "1.2kg"],
        "pack_quantity": [250.0, 1200.0],
        "pack_unit": ["g", "g"],
        "price_chf": [3.50, 8.90],
        "regular_price_chf": [4.90, 12.90],
        "discount_pct": [28.6, 31.0],
        "valid_from": [datetime.date(2024, 6, 1), datetime.date(2024, 6, 1)],
        "valid_to": [datetime.date(2024, 6, 7), datetime.date(2024, 6, 7)],
        "source_url": ["http://promo/1", "http://promo/2"],
        "scraped_at": [datetime.datetime(2024, 6, 1)] * 2,
    }
    table = pa.table(promo_data, schema=SCHEMAS["promotions"])
    pq.write_table(table, tmp_path / "promotions.parquet")

    # retailers
    ret_data = {
        "id": [1, 2],
        "key": ["migros", "coop"],
        "display_name": ["Migros", "Coop"],
        "base_url": ["https://migros.ch", "https://coop.ch"],
    }
    table = pa.table(ret_data, schema=SCHEMAS["retailers"])
    pq.write_table(table, tmp_path / "retailers.parquet")

    # sources
    src_data = {
        "id": [1],
        "key": ["fooby"],
        "display_name": ["Fooby"],
        "base_url": ["https://fooby.ch"],
        "language": ["de"],
        "kind": ["recipe"],
    }
    table = pa.table(src_data, schema=SCHEMAS["sources"])
    pq.write_table(table, tmp_path / "sources.parquet")

    # cook_log
    cook_data = {
        "id": [1, 2, 3],
        "recipe_id": [1, 1, 2],
        "cooked_on": [
            datetime.date(2024, 5, 1),
            datetime.date(2024, 6, 15),
            datetime.date(2024, 6, 10),
        ],
        "servings": [4, 2, None],
        "scale_factor": [None, 2.0, None],
        "rating": [5, 4, None],
        "notes": ["Great result", None, "Quick weeknight meal"],
        "logged_at": [
            datetime.datetime(2024, 5, 1, 18, 0),
            datetime.datetime(2024, 6, 15, 19, 0),
            datetime.datetime(2024, 6, 10, 20, 0),
        ],
    }
    table = pa.table(cook_data, schema=SCHEMAS["cook_log"])
    pq.write_table(table, tmp_path / "cook_log.parquet")

    return tmp_path


def _patch_output(output_dir: Path):
    """Patch mcp_server._output_dir to return our temp dir."""
    return patch("recipebrain.mcp_server._output_dir", return_value=output_dir)


# ---------------------------------------------------------------------------
# Tests: find_recipe
# ---------------------------------------------------------------------------


class TestFindRecipe:
    def test_find_all(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe()
        assert "Rösti" in result
        assert "Fondue" in result
        assert "Zürcher Geschnetzeltes" in result

    def test_find_by_query(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(query="rösti")
        assert "Rösti" in result
        assert "Fondue" not in result

    def test_find_by_difficulty(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(difficulty="easy")
        assert "Rösti" in result
        assert "Fondue" in result
        assert "Geschnetzeltes" not in result

    def test_find_by_max_time(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(max_total_minutes=30)
        assert "Rösti" in result
        assert "Geschnetzeltes" not in result

    def test_find_no_results(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(query="nonexistent")
        assert "No recipes found" in result

    def test_find_missing_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(tmp_path):
            result = find_recipe()
        # Should return error (no parquet files, output dir exists but no data)
        assert "No recipes found" in result or "Error" in result


# ---------------------------------------------------------------------------
# Tests: read_recipe
# ---------------------------------------------------------------------------


class TestReadRecipe:
    def test_read_existing(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "Zürcher Geschnetzeltes" in result
        assert "## Ingredients" in result
        assert "400g Kalbsgeschnetzeltes" in result
        assert "## Steps" in result
        assert "Fleisch anbraten" in result

    def test_read_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=999)
        assert "not found" in result.lower()

    def test_read_recipe_without_steps(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=2)
        assert "Rösti" in result
        assert "500g Kartoffeln" in result
        # Recipe 2 has no steps
        assert "## Steps" not in result

    def test_read_includes_cook_history(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "## Cook History" in result
        # Recipe 1 has 2 cook events
        assert "2024-06-15" in result
        assert "2024-05-01" in result
        assert "Great result" in result

    def test_read_no_cook_history(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=3)
        # Recipe 3 (Fondue) has no cook events
        assert "## Cook History" not in result

    def test_read_cook_history_shows_rating(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "5/5" in result
        assert "4/5" in result

    def test_read_includes_dossier_notes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        dossier_dir = output_dir / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / "1.md").write_text(
            "# Zürcher Geschnetzeltes\n\n## notes\n\nBest with fresh cream\n",
            encoding="utf-8",
        )

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "## Notes" in result
        assert "Best with fresh cream" in result

    def test_read_includes_dossier_variations(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        dossier_dir = output_dir / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / "2.md").write_text(
            "# Rösti\n\n## variations\n\nUse sweet potato instead\n",
            encoding="utf-8",
        )

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=2)
        assert "## Variations" in result
        assert "Use sweet potato instead" in result

    def test_read_includes_multiple_dossier_sections(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        dossier_dir = output_dir / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / "1.md").write_text(
            "# Zürcher Geschnetzeltes\n\n"
            "## notes\n\nPersonal note\n\n"
            "## pairings\n\nGoes with Riesling\n\n"
            "## tags\n\nweeknight, comfort-food\n",
            encoding="utf-8",
        )

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "## Notes" in result
        assert "Personal note" in result
        assert "## Pairings" in result
        assert "Goes with Riesling" in result
        assert "## Tags" in result
        assert "weeknight" in result

    def test_read_no_dossier_still_works(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        # No dossier directory at all
        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        assert "Zürcher Geschnetzeltes" in result
        assert "## Notes" not in result

    def test_read_dossier_empty_section_skipped(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import read_recipe

        dossier_dir = output_dir / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / "1.md").write_text(
            "# Zürcher Geschnetzeltes\n\n## notes\n\n\n\n## variations\n\nReal content\n",
            encoding="utf-8",
        )

        with _patch_output(output_dir):
            result = read_recipe(recipe_id=1)
        # Empty notes section should be skipped
        assert "## Notes" not in result
        assert "## Variations" in result
        assert "Real content" in result


# ---------------------------------------------------------------------------
# Tests: log_cook
# ---------------------------------------------------------------------------


class TestLogCook:
    def test_log_basic(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook

        with _patch_output(output_dir):
            result = log_cook(recipe_id=1, cooked_on="2024-06-15", rating=5)
        assert "Logged" in result
        assert "Zürcher Geschnetzeltes" in result
        assert "Rating: 5/5" in result

        # Verify parquet was written
        assert (output_dir / "cook_log.parquet").exists()

    def test_log_invalid_recipe(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook

        with _patch_output(output_dir):
            result = log_cook(recipe_id=999)
        assert "not found" in result.lower()

    def test_log_invalid_rating(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook

        with _patch_output(output_dir):
            result = log_cook(recipe_id=1, rating=6)
        assert "Error" in result

    def test_log_defaults_to_today(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook

        with _patch_output(output_dir):
            result = log_cook(recipe_id=2)
        today = datetime.date.today().isoformat()
        assert today in result

    def test_log_updates_times_cooked(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            log_cook(recipe_id=3, cooked_on="2024-07-01")

        rows = execute_query(
            "SELECT times_cooked, last_cooked_at FROM recipes WHERE id = 3", output_dir
        )
        # Recipe 3 had 0 cook events in fixture; now 1
        assert rows[0]["times_cooked"] == 1
        assert rows[0]["last_cooked_at"].date() == datetime.date(2024, 7, 1)

    def test_log_updates_last_cooked_at(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            # Recipe 1 already has 2 cook events (May 1 + Jun 15)
            log_cook(recipe_id=1, cooked_on="2024-08-01")

        rows = execute_query(
            "SELECT times_cooked, last_cooked_at FROM recipes WHERE id = 1", output_dir
        )
        assert rows[0]["times_cooked"] == 3  # 2 existing + 1 new
        assert rows[0]["last_cooked_at"].date() == datetime.date(2024, 8, 1)

    def test_log_updates_owner_rating_from_latest(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            log_cook(recipe_id=3, cooked_on="2024-07-01", rating=3)

        rows = execute_query("SELECT owner_rating FROM recipes WHERE id = 3", output_dir)
        assert rows[0]["owner_rating"] == 3

    def test_log_no_rating_preserves_latest(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            # Recipe 1 has existing ratings 5 (May) and 4 (Jun 15); log without rating
            log_cook(recipe_id=1, cooked_on="2024-08-01")

        rows = execute_query("SELECT owner_rating FROM recipes WHERE id = 1", output_dir)
        # Latest non-null rating is 4 from Jun 15
        assert rows[0]["owner_rating"] == 4

    def test_log_with_scale_factor(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            log_cook(recipe_id=1, cooked_on="2024-07-01", scale_factor=2.0, servings=8)

        rows = execute_query(
            "SELECT scale_factor, servings FROM cook_log WHERE recipe_id = 1 "
            "ORDER BY cooked_on DESC LIMIT 1",
            output_dir,
        )
        assert rows[0]["scale_factor"] == 2.0
        assert rows[0]["servings"] == 8

    def test_log_transitions_pin_to_cooked(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook, pin_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            log_cook(recipe_id=1, cooked_on="2024-07-01")

        rows = execute_query(
            "SELECT status FROM pinned_recipes WHERE recipe_id = 1",
            output_dir,
        )
        assert rows[0]["status"] == "cooked"

    def test_log_no_pin_no_error(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook

        with _patch_output(output_dir):
            # No pin exists — should not error
            result = log_cook(recipe_id=1, cooked_on="2024-07-01")
        assert "Logged" in result

    def test_log_dismissed_pin_unchanged(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import log_cook, pin_recipe, unpin_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            unpin_recipe(recipe_id=1)
            log_cook(recipe_id=1, cooked_on="2024-07-01")

        rows = execute_query(
            "SELECT status FROM pinned_recipes WHERE recipe_id = 1",
            output_dir,
        )
        # Was dismissed, should stay dismissed (not transition to cooked)
        assert rows[0]["status"] == "dismissed"


# ---------------------------------------------------------------------------
# Tests: current_promotions
# ---------------------------------------------------------------------------


class TestCurrentPromotions:
    def test_all_promotions(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import current_promotions

        with _patch_output(output_dir):
            result = current_promotions()
        assert "Emmentaler" in result
        assert "Poulet" in result

    def test_filter_by_discount(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import current_promotions

        with _patch_output(output_dir):
            result = current_promotions(min_discount_pct=30.0)
        assert "Poulet" in result
        # 28.6% discount should be excluded
        assert "Emmentaler" not in result

    def test_no_promotions(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import current_promotions

        with _patch_output(tmp_path):
            result = current_promotions()
        assert "No promotions found" in result or "Error" in result

    def test_filter_by_ingredient(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import current_promotions

        with _patch_output(output_dir):
            result = current_promotions(ingredient="Emmentaler")
        assert "Emmentaler" in result
        assert "Poulet" not in result

    def test_filter_by_ingredient_no_match(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import current_promotions

        with _patch_output(output_dir):
            result = current_promotions(ingredient="nonexistent")
        assert "No promotions found" in result


# ---------------------------------------------------------------------------
# Tests: query_recipes
# ---------------------------------------------------------------------------


class TestQueryRecipes:
    def test_valid_select(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import query_recipes

        with _patch_output(output_dir):
            result = query_recipes(sql="SELECT id, title FROM recipes")
        assert "Rösti" in result
        assert "id" in result

    def test_forbidden_sql(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import query_recipes

        with _patch_output(output_dir):
            result = query_recipes(sql="DROP TABLE recipes")
        assert "Error" in result
        assert "Forbidden" in result or "DROP" in result

    def test_limit_applied(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import query_recipes

        with _patch_output(output_dir):
            result = query_recipes(sql="SELECT id FROM recipes", limit=1)
        # Should have header + separator + 1 data row = 3 lines
        lines = [ln for ln in result.strip().split("\n") if ln.strip()]
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# Tests: server_stats
# ---------------------------------------------------------------------------


class TestServerStats:
    def test_stats_with_data(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import server_stats

        with _patch_output(output_dir):
            result = server_stats()
        assert "recipes" in result.lower()
        assert "3" in result  # 3 recipes
        assert "promotions" in result.lower()

    def test_stats_empty(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import server_stats

        with _patch_output(tmp_path):
            result = server_stats()
        assert "no data" in result.lower()


# ---------------------------------------------------------------------------
# Tests: suggest_easy
# ---------------------------------------------------------------------------


class TestSuggestEasyMcp:
    def test_returns_table(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import suggest_easy

        with _patch_output(output_dir):
            result = suggest_easy(max_total_minutes=60)
        assert "| ID |" in result

    def test_no_results(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import suggest_easy

        with _patch_output(output_dir):
            result = suggest_easy(max_total_minutes=1)
        assert "No easy recipes" in result

    def test_missing_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import suggest_easy

        with _patch_output(tmp_path):
            result = suggest_easy()
        assert "No easy recipes" in result or "Error" in result


# ---------------------------------------------------------------------------
# Tests: suggest_rotation
# ---------------------------------------------------------------------------


class TestSuggestRotationMcp:
    def test_returns_table(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import suggest_rotation

        with _patch_output(output_dir):
            result = suggest_rotation(min_rating=4)
        assert "| ID |" in result or "No rotation" in result

    def test_high_rating_filter(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import suggest_rotation

        with _patch_output(output_dir):
            result = suggest_rotation(min_rating=5)
        # Recipes 1 and 3 have rating 5
        if "| ID |" in result:
            assert "Zürcher Geschnetzeltes" in result or "Fondue" in result

    def test_missing_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import suggest_rotation

        with _patch_output(tmp_path):
            result = suggest_rotation()
        assert "No rotation" in result or "Error" in result


# ---------------------------------------------------------------------------
# Tests: suggest_for_pantry
# ---------------------------------------------------------------------------


class TestSuggestForPantryMcp:
    def test_no_pantry_data(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import suggest_for_pantry

        with _patch_output(output_dir):
            result = suggest_for_pantry(missing_ok=10)
        # No pantry.parquet or ingredients.parquet → may still return results
        assert isinstance(result, str)

    def test_missing_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import suggest_for_pantry

        with _patch_output(tmp_path):
            result = suggest_for_pantry()
        assert "No recipes" in result or "Error" in result


# ---------------------------------------------------------------------------
# Tests: update_pantry
# ---------------------------------------------------------------------------


class TestUpdatePantryMcp:
    def test_no_changes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import update_pantry

        with _patch_output(output_dir):
            result = update_pantry()
        assert "No changes" in result

    def test_unknown_ingredient(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import update_pantry

        # No ingredients.parquet in fixture → returns error
        with _patch_output(output_dir):
            result = update_pantry(additions=[{"ingredient": "nonexistent-thing"}])
        assert "Unknown" in result or "Error" in result


# ---------------------------------------------------------------------------
# Tests: refresh_source
# ---------------------------------------------------------------------------


class TestRefreshSource:
    def test_unknown_source_returns_error(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import refresh_source

        with _patch_output(output_dir):
            result = refresh_source(source="nonexistent")
        assert "Error" in result or "No source adapter" in result

    def test_refresh_with_fake_etl(self, output_dir: Path) -> None:
        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import refresh_source

        fake_result = EtlResult(source="migusto", discovered=100, fetched=10, skipped=90, errors=0)

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=[fake_result]) as mock_etl,
        ):
            result = refresh_source(source="migusto", limit=10)

        assert "10 new" in result
        assert "90 skipped" in result
        assert "migusto" in result

        # Verify run_etl was called with correct args
        _, kwargs = mock_etl.call_args
        assert kwargs["source_filter"] == "migusto"
        assert kwargs["limit"] == 10

    def test_default_limit_applied(self, output_dir: Path) -> None:
        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import _DEFAULT_REFRESH_LIMIT, refresh_source

        fake_result = EtlResult(source="migusto", discovered=50, fetched=5)

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=[fake_result]) as mock_etl,
        ):
            refresh_source(source="migusto")

        _, kwargs = mock_etl.call_args
        assert kwargs["limit"] == _DEFAULT_REFRESH_LIMIT

    def test_limit_capped_at_max(self, output_dir: Path) -> None:
        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import _MAX_REFRESH_LIMIT, refresh_source

        fake_result = EtlResult(source="migusto", discovered=50, fetched=5)

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=[fake_result]) as mock_etl,
        ):
            refresh_source(source="migusto", limit=999)

        _, kwargs = mock_etl.call_args
        assert kwargs["limit"] == _MAX_REFRESH_LIMIT

    def test_all_sources(self, output_dir: Path) -> None:
        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import refresh_source

        fake_results = [
            EtlResult(source="migusto", discovered=50, fetched=5),
            EtlResult(source="swissmilk", discovered=30, fetched=3),
        ]

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=fake_results) as mock_etl,
        ):
            result = refresh_source(source="all")

        _, kwargs = mock_etl.call_args
        assert kwargs["source_filter"] is None
        assert "migusto" in result
        assert "swissmilk" in result

    def test_error_details_included(self, output_dir: Path) -> None:
        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import refresh_source

        fake_result = EtlResult(
            source="migusto",
            discovered=10,
            fetched=8,
            errors=2,
            error_details=["Fetch failed (http://x): timeout"],
        )

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=[fake_result]),
        ):
            result = refresh_source(source="migusto")

        assert "2 errors" in result
        assert "Fetch failed" in result

    def test_limit_zero_starts_async(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import refresh_source

        with (
            _patch_output(output_dir),
            patch("recipebrain.mcp_server._start_async_refresh", return_value="abc123") as mock,
        ):
            result = refresh_source(source="migusto", limit=0)

        mock.assert_called_once_with("migusto")
        assert "abc123" in result
        assert "refresh_status" in result


# ---------------------------------------------------------------------------
# Tests: async refresh jobs
# ---------------------------------------------------------------------------


class TestAsyncRefresh:
    def test_start_and_complete(self, output_dir: Path) -> None:
        import time

        from recipebrain.etl import EtlResult
        from recipebrain.mcp_server import _jobs, refresh_status

        fake_result = EtlResult(source="migusto", discovered=100, fetched=50, skipped=50)

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", return_value=[fake_result]),
        ):
            from recipebrain.mcp_server import _start_async_refresh

            job_id = _start_async_refresh("migusto")

            # Wait for background thread to finish
            for _ in range(50):
                if _jobs[job_id].status != "running":
                    break
                time.sleep(0.05)

        assert _jobs[job_id].status == "completed"
        assert _jobs[job_id].results[0].fetched == 50

        status = refresh_status(job_id=job_id)
        assert "completed" in status
        assert "50 new" in status

        # Clean up
        del _jobs[job_id]

    def test_failed_job(self, output_dir: Path) -> None:
        import time

        from recipebrain.mcp_server import _jobs, refresh_status

        with (
            _patch_output(output_dir),
            patch("recipebrain.etl.run_etl", side_effect=RuntimeError("boom")),
        ):
            from recipebrain.mcp_server import _start_async_refresh

            job_id = _start_async_refresh("migusto")

            for _ in range(50):
                if _jobs[job_id].status != "running":
                    break
                time.sleep(0.05)

        assert _jobs[job_id].status == "failed"
        assert "boom" in _jobs[job_id].error

        status = refresh_status(job_id=job_id)
        assert "failed" in status
        assert "boom" in status

        del _jobs[job_id]


# ---------------------------------------------------------------------------
# Tests: refresh_status
# ---------------------------------------------------------------------------


class TestRefreshStatus:
    def test_no_jobs(self) -> None:
        from recipebrain.mcp_server import _jobs, refresh_status

        # Ensure clean state
        original = dict(_jobs)
        _jobs.clear()
        try:
            result = refresh_status()
            assert "No refresh jobs" in result
        finally:
            _jobs.update(original)

    def test_unknown_job_id(self) -> None:
        from recipebrain.mcp_server import refresh_status

        result = refresh_status(job_id="nonexistent")
        assert "Error" in result
        assert "nonexistent" in result


# ---------------------------------------------------------------------------
# Tests: star_recipe
# ---------------------------------------------------------------------------


class TestStarRecipe:
    def test_star(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import star_recipe

        with _patch_output(output_dir):
            result = star_recipe(recipe_id=1, starred=True)
        assert "Starred" in result
        assert "Zürcher Geschnetzeltes" in result

        # Verify persisted
        from recipebrain.query import execute_query

        rows = execute_query("SELECT starred FROM recipes WHERE id = 1", output_dir)
        assert rows[0]["starred"] is True

    def test_unstar(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import star_recipe

        with _patch_output(output_dir):
            star_recipe(recipe_id=2, starred=True)
            result = star_recipe(recipe_id=2, starred=False)
        assert "Unstarred" in result

        from recipebrain.query import execute_query

        rows = execute_query("SELECT starred FROM recipes WHERE id = 2", output_dir)
        assert rows[0]["starred"] is False

    def test_star_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import star_recipe

        with _patch_output(output_dir):
            result = star_recipe(recipe_id=999)
        assert "not found" in result.lower()

    def test_star_default_true(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import star_recipe

        with _patch_output(output_dir):
            result = star_recipe(recipe_id=3)
        assert "Starred" in result


# ---------------------------------------------------------------------------
# Tests: rate_recipe
# ---------------------------------------------------------------------------


class TestRateRecipe:
    def test_rate(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            result = rate_recipe(recipe_id=2, rating=5)
        assert "Rated" in result
        assert "5/5" in result

        from recipebrain.query import execute_query

        rows = execute_query("SELECT owner_rating FROM recipes WHERE id = 2", output_dir)
        assert rows[0]["owner_rating"] == 5

    def test_clear_rating(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            result = rate_recipe(recipe_id=1, rating=None)
        assert "Cleared" in result

        from recipebrain.query import execute_query

        rows = execute_query("SELECT owner_rating FROM recipes WHERE id = 1", output_dir)
        assert rows[0]["owner_rating"] is None

    def test_rate_invalid(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            result = rate_recipe(recipe_id=1, rating=6)
        assert "Error" in result

    def test_rate_zero_invalid(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            result = rate_recipe(recipe_id=1, rating=0)
        assert "Error" in result

    def test_rate_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            result = rate_recipe(recipe_id=999, rating=3)
        assert "not found" in result.lower()

    def test_rate_preserves_other_fields(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import rate_recipe

        with _patch_output(output_dir):
            rate_recipe(recipe_id=1, rating=3)

        from recipebrain.query import execute_query

        rows = execute_query(
            "SELECT title, owner_rating, times_cooked FROM recipes WHERE id = 1",
            output_dir,
        )
        assert rows[0]["title"] == "Zürcher Geschnetzeltes"
        assert rows[0]["owner_rating"] == 3
        assert rows[0]["times_cooked"] == 3


# ---------------------------------------------------------------------------
# Tests: cook_history
# ---------------------------------------------------------------------------


class TestCookHistory:
    def test_history_for_recipe(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history(recipe_id=1)
        assert "Cook History" in result
        assert "Zürcher Geschnetzeltes" in result
        # Should show both cook events for recipe 1
        assert "2024-06-15" in result
        assert "2024-05-01" in result
        assert "Great result" in result

    def test_history_global(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history()
        assert "Recent Cook History" in result
        # All 3 events across recipes
        assert "Zürcher Geschnetzeltes" in result
        assert "Rösti" in result

    def test_history_with_limit(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history(limit=1)
        # Only 1 event (most recent)
        lines = [line for line in result.splitlines() if line.startswith("- ")]
        assert len(lines) == 1

    def test_history_recipe_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history(recipe_id=999)
        assert "not found" in result.lower()

    def test_history_no_events(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            # Recipe 3 (Fondue) has no cook events
            result = cook_history(recipe_id=3)
        assert "No cook history" in result

    def test_history_shows_rating(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history(recipe_id=1)
        assert "5/5" in result
        assert "4/5" in result

    def test_history_shows_servings(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import cook_history

        with _patch_output(output_dir):
            result = cook_history(recipe_id=1)
        assert "4 servings" in result
        assert "2 servings" in result


# ---------------------------------------------------------------------------
# Tests: pin_recipe
# ---------------------------------------------------------------------------


class TestPinRecipe:
    def test_pin(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe

        with _patch_output(output_dir):
            result = pin_recipe(recipe_id=1)
        assert "Pinned" in result
        assert "Zürcher Geschnetzeltes" in result

    def test_pin_with_date_and_note(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe

        with _patch_output(output_dir):
            result = pin_recipe(recipe_id=2, target_date="2024-07-01", note="Saturday dinner")
        assert "Pinned" in result
        assert "2024-07-01" in result

    def test_pin_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe

        with _patch_output(output_dir):
            result = pin_recipe(recipe_id=999)
        assert "not found" in result.lower()

    def test_pin_already_pinned(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            result = pin_recipe(recipe_id=1)
        assert "already pinned" in result.lower()

    def test_pin_after_unpin_allowed(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe, unpin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            unpin_recipe(recipe_id=1)
            result = pin_recipe(recipe_id=1)
        assert "Pinned" in result


# ---------------------------------------------------------------------------
# Tests: list_pinned
# ---------------------------------------------------------------------------


class TestListPinned:
    def test_no_pins(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_pinned

        with _patch_output(output_dir):
            result = list_pinned()
        assert "No pinned" in result

    def test_list_active_pins(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_pinned, pin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            pin_recipe(recipe_id=2, target_date="2024-07-01")
            result = list_pinned()
        assert "Pinboard" in result
        assert "Zürcher Geschnetzeltes" in result
        assert "Rösti" in result

    def test_list_excludes_dismissed(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_pinned, pin_recipe, unpin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            pin_recipe(recipe_id=2)
            unpin_recipe(recipe_id=1)
            result = list_pinned()
        assert "Zürcher Geschnetzeltes" not in result
        assert "Rösti" in result

    def test_list_include_done(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_pinned, pin_recipe, unpin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            unpin_recipe(recipe_id=1)
            result = list_pinned(include_done=True)
        assert "Zürcher Geschnetzeltes" in result
        assert "dismissed" in result

    def test_list_shows_note(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_pinned, pin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1, note="for guests")
            result = list_pinned()
        assert "for guests" in result


# ---------------------------------------------------------------------------
# Tests: unpin_recipe
# ---------------------------------------------------------------------------


class TestUnpinRecipe:
    def test_unpin(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import pin_recipe, unpin_recipe

        with _patch_output(output_dir):
            pin_recipe(recipe_id=1)
            result = unpin_recipe(recipe_id=1)
        assert "Unpinned" in result

    def test_unpin_not_pinned(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import unpin_recipe

        with _patch_output(output_dir):
            result = unpin_recipe(recipe_id=1)
        assert "not currently pinned" in result.lower()

    def test_unpin_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import unpin_recipe

        with _patch_output(output_dir):
            result = unpin_recipe(recipe_id=999)
        assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# Tests: add_recipe
# ---------------------------------------------------------------------------


class TestAddRecipe:
    def test_add_basic(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe

        with _patch_output(output_dir):
            result = add_recipe(
                title="Pasta Aglio e Olio",
                ingredients=["400 g Spaghetti", "4 Zehen Knoblauch", "Olivenöl"],
                steps=["Spaghetti kochen", "Knoblauch anbraten", "Mischen"],
            )
        assert "Created" in result
        assert "Pasta Aglio e Olio" in result
        assert "id=" in result

    def test_add_returns_id(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            result = add_recipe(
                title="Test Recipe",
                ingredients=["1 EL Butter"],
                steps=["Melt butter"],
            )

        # Extract id from result
        recipe_id = int(result.split("id=")[1].rstrip("."))
        rows = execute_query(
            f"SELECT title, status, source_id FROM recipes WHERE id = {recipe_id}",
            output_dir,
        )
        assert rows[0]["title"] == "Test Recipe"
        assert rows[0]["status"] == "active"

    def test_add_creates_own_source(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            add_recipe(
                title="Test",
                ingredients=["1 Ei"],
                steps=["Cook"],
            )

        rows = execute_query("SELECT key, kind FROM sources WHERE key = 'own'", output_dir)
        assert len(rows) == 1
        assert rows[0]["kind"] == "own"

    def test_add_parses_ingredients(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            result = add_recipe(
                title="Parsed Test",
                ingredients=["200 g Pouletbrust, in Würfeln"],
                steps=["Kochen"],
            )

        recipe_id = int(result.split("id=")[1].rstrip("."))
        rows = execute_query(
            f"SELECT raw_text, quantity, unit, prep_note FROM recipe_ingredients "
            f"WHERE recipe_id = {recipe_id}",
            output_dir,
        )
        assert rows[0]["raw_text"] == "200 g Pouletbrust, in Würfeln"
        assert rows[0]["quantity"] == 200.0
        assert rows[0]["unit"] == "g"
        assert rows[0]["prep_note"] == "in Würfeln"


class TestBatchAnnotate:
    def test_annotates_multiple(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_annotate

        with _patch_output(output_dir):
            result = batch_annotate(
                recipe_ids=[1, 2],
                section="notes",
                content="Batch note",
            )
        assert "Annotated 2" in result
        # Verify dossiers were created
        d1 = output_dir / "dossiers" / "recipes" / "1.md"
        d2 = output_dir / "dossiers" / "recipes" / "2.md"
        assert d1.exists()
        assert d2.exists()
        assert "Batch note" in d1.read_text(encoding="utf-8")
        assert "Batch note" in d2.read_text(encoding="utf-8")

    def test_reports_missing_recipes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_annotate

        with _patch_output(output_dir):
            result = batch_annotate(
                recipe_ids=[1, 999],
                section="notes",
                content="Test",
            )
        assert "Annotated 1" in result
        assert "#999: not found" in result

    def test_rejects_empty_content(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_annotate

        with _patch_output(output_dir):
            result = batch_annotate(recipe_ids=[1], section="notes", content="")
        assert "Error" in result

    def test_rejects_protected_section(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_annotate

        with _patch_output(output_dir):
            result = batch_annotate(
                recipe_ids=[1],
                section="ingredients",
                content="test",
            )
        assert "not allowed" in result

    def test_rejects_empty_ids(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_annotate

        with _patch_output(output_dir):
            result = batch_annotate(recipe_ids=[], section="notes", content="test")
        assert "Error" in result


class TestBatchTag:
    def test_tags_multiple_recipes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_tag

        with _patch_output(output_dir):
            result = batch_tag(recipe_ids=[1, 2], tags=["quick", "swiss"])
        assert "Tagged 2" in result

    def test_reports_missing_recipes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_tag

        with _patch_output(output_dir):
            result = batch_tag(recipe_ids=[1, 999], tags=["test"])
        assert "Tagged 1" in result
        assert "Errors" in result

    def test_rejects_empty_ids(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_tag

        with _patch_output(output_dir):
            result = batch_tag(recipe_ids=[], tags=["test"])
        assert "Error" in result

    def test_rejects_empty_tags(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import batch_tag

        with _patch_output(output_dir):
            result = batch_tag(recipe_ids=[1], tags=[])
        assert "Error" in result


class TestResources:
    def test_recipe_list(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_recipe_list

        with _patch_output(output_dir):
            result = resource_recipe_list()
        data = json.loads(result)
        assert len(data) == 3
        assert data[0]["title"] is not None

    def test_recipe_stats(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_recipe_stats

        with _patch_output(output_dir):
            result = resource_recipe_stats()
        data = json.loads(result)
        assert data["total"] == 3
        assert data["active"] == 3

    def test_starred_resource(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_starred

        with _patch_output(output_dir):
            result = resource_starred()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_cook_log_resource(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_cook_log

        with _patch_output(output_dir):
            result = resource_cook_log()
        data = json.loads(result)
        assert len(data) == 3

    def test_sources_resource(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_sources

        with _patch_output(output_dir):
            result = resource_sources()
        data = json.loads(result)
        assert len(data) >= 1
        assert data[0]["key"] == "fooby"

    def test_tags_resource_empty(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_tags

        with _patch_output(output_dir):
            result = resource_tags()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_pantry_resource_empty(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_pantry

        with _patch_output(output_dir):
            result = resource_pantry()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_promotions_resource(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_promotions

        with _patch_output(output_dir):
            result = resource_promotions()
        # May or may not have current promotions depending on test data dates
        data = json.loads(result)
        assert isinstance(data, list)

    def test_ingredients_resource_empty(self, output_dir: Path) -> None:
        import json

        from recipebrain.mcp_server import resource_ingredients

        with _patch_output(output_dir):
            result = resource_ingredients()
        data = json.loads(result)
        assert isinstance(data, list)


class TestPrompts:
    def test_recipe_qa_prompt(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import prompt_recipe_qa

        with _patch_output(output_dir):
            result = prompt_recipe_qa()
        assert "recipe assistant" in result
        assert "Total recipes: 3" in result
        assert "Cook log entries: 3" in result

    def test_recipe_qa_prompt_no_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import prompt_recipe_qa

        with _patch_output(tmp_path):
            result = prompt_recipe_qa()
        assert "unavailable" in result

    def test_meal_plan_prompt(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import prompt_meal_plan

        with _patch_output(output_dir):
            result = prompt_meal_plan()
        assert "meal planning" in result
        assert "pantry" in result.lower()
        assert "Guidelines" in result

    def test_meal_plan_prompt_no_data(self, tmp_path: Path) -> None:
        from recipebrain.mcp_server import prompt_meal_plan

        with _patch_output(tmp_path):
            result = prompt_meal_plan()
        # Empty dir still produces a valid prompt with empty indicators
        assert "meal planning" in result
        assert "(empty or unknown)" in result
        assert "(none)" in result

    def test_add_stores_steps(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            result = add_recipe(
                title="Step Test",
                ingredients=["Butter"],
                steps=["Step one", "Step two", "Step three"],
            )

        recipe_id = int(result.split("id=")[1].rstrip("."))
        rows = execute_query(
            f"SELECT step_no, text FROM recipe_steps "
            f"WHERE recipe_id = {recipe_id} ORDER BY step_no",
            output_dir,
        )
        assert len(rows) == 3
        assert rows[0]["text"] == "Step one"
        assert rows[2]["step_no"] == 3

    def test_add_with_optional_fields(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            result = add_recipe(
                title="Full Recipe",
                ingredients=["100 ml Milch"],
                steps=["Pour milk"],
                servings=4,
                prep_minutes=10,
                cook_minutes=20,
                difficulty="easy",
            )

        recipe_id = int(result.split("id=")[1].rstrip("."))
        rows = execute_query(
            f"SELECT servings, prep_minutes, cook_minutes, total_minutes, difficulty "
            f"FROM recipes WHERE id = {recipe_id}",
            output_dir,
        )
        assert rows[0]["servings"] == 4
        assert rows[0]["prep_minutes"] == 10
        assert rows[0]["cook_minutes"] == 20
        assert rows[0]["total_minutes"] == 30
        assert rows[0]["difficulty"] == "easy"

    def test_add_empty_title_error(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe

        with _patch_output(output_dir):
            result = add_recipe(title="", ingredients=["egg"], steps=["cook"])
        assert "Error" in result

    def test_add_no_ingredients_error(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe

        with _patch_output(output_dir):
            result = add_recipe(title="Test", ingredients=[], steps=["cook"])
        assert "Error" in result

    def test_add_no_steps_error(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe

        with _patch_output(output_dir):
            result = add_recipe(title="Test", ingredients=["egg"], steps=[])
        assert "Error" in result

    def test_add_can_read_back(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe, read_recipe

        with _patch_output(output_dir):
            result = add_recipe(
                title="Readable Recipe",
                ingredients=["2 dl Rahm", "1 EL Mehl"],
                steps=["Mix together", "Heat gently"],
            )
            recipe_id = int(result.split("id=")[1].rstrip("."))
            read_result = read_recipe(recipe_id=recipe_id)

        assert "Readable Recipe" in read_result
        assert "2 dl Rahm" in read_result
        assert "Mix together" in read_result

    def test_add_strips_accents_in_title_normalised(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import add_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            result = add_recipe(
                title="Crème Brûlée mit Früchten",
                ingredients=["3 Eigelb"],
                steps=["Backen"],
            )

        recipe_id = int(result.split("id=")[1].rstrip("."))
        rows = execute_query(
            f"SELECT title_normalised FROM recipes WHERE id = {recipe_id}",
            output_dir,
        )
        assert rows[0]["title_normalised"] == "creme brulee mit fruchten"


# ---------------------------------------------------------------------------
# Tests: annotate_recipe
# ---------------------------------------------------------------------------


class TestAnnotateRecipe:
    def test_annotate_creates_dossier_and_section(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=1, section="notes", content="Tastes great")
        assert "Added" in result
        assert "notes" in result

        dossier = (output_dir / "dossiers" / "recipes" / "1.md").read_text(encoding="utf-8")
        assert "## notes" in dossier
        assert "Tastes great" in dossier

    def test_annotate_appends_to_existing_section(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            annotate_recipe(recipe_id=1, section="notes", content="First note")
            result = annotate_recipe(recipe_id=1, section="notes", content="Second note")
        assert "Added" in result

        dossier = (output_dir / "dossiers" / "recipes" / "1.md").read_text(encoding="utf-8")
        assert "First note" in dossier
        assert "Second note" in dossier

    def test_annotate_variations_section(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(
                recipe_id=2,
                section="variations",
                content="Use mascarpone instead of cream cheese",
            )
        assert "Added" in result
        assert "variations" in result

        dossier = (output_dir / "dossiers" / "recipes" / "2.md").read_text(encoding="utf-8")
        assert "mascarpone" in dossier

    def test_annotate_multiple_sections(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            annotate_recipe(recipe_id=1, section="notes", content="My note")
            annotate_recipe(recipe_id=1, section="pairings", content="Goes with Riesling")

        dossier = (output_dir / "dossiers" / "recipes" / "1.md").read_text(encoding="utf-8")
        assert "## notes" in dossier
        assert "My note" in dossier
        assert "## pairings" in dossier
        assert "Goes with Riesling" in dossier

    def test_annotate_invalid_section(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=1, section="ingredients", content="hack")
        assert "Error" in result
        assert "not allowed" in result

    def test_annotate_recipe_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=999, section="notes", content="anything")
        assert "not found" in result.lower()

    def test_annotate_empty_content(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=1, section="notes", content="")
        assert "Error" in result

    def test_annotate_whitespace_content(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=1, section="notes", content="   ")
        assert "Error" in result

    def test_annotate_preserves_title_header(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import annotate_recipe

        with _patch_output(output_dir):
            annotate_recipe(recipe_id=1, section="notes", content="A note")

        dossier = (output_dir / "dossiers" / "recipes" / "1.md").read_text(encoding="utf-8")
        assert dossier.startswith("# Zürcher Geschnetzeltes")

    def test_annotate_existing_dossier(self, output_dir: Path) -> None:
        """Annotating a recipe that already has a dossier (e.g. from add_recipe)."""
        from recipebrain.mcp_server import annotate_recipe

        # Pre-create dossier
        dossier_dir = output_dir / "dossiers" / "recipes"
        dossier_dir.mkdir(parents=True, exist_ok=True)
        (dossier_dir / "1.md").write_text(
            "# Zürcher Geschnetzeltes\n\n## notes\n\nExisting note\n", encoding="utf-8"
        )

        with _patch_output(output_dir):
            result = annotate_recipe(recipe_id=1, section="notes", content="New note")
        assert "Added" in result

        dossier = (dossier_dir / "1.md").read_text(encoding="utf-8")
        assert "Existing note" in dossier
        assert "New note" in dossier


# ---------------------------------------------------------------------------
# Tests: tag_recipe
# ---------------------------------------------------------------------------


class TestTagRecipe:
    def test_tag_basic(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe

        with _patch_output(output_dir):
            result = tag_recipe(recipe_id=1, tags=["weeknight", "comfort-food"])
        assert "Tagged" in result
        assert "weeknight" in result
        assert "comfort-food" in result

    def test_tag_creates_tags_table(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["quick"])

        rows = execute_query("SELECT key, display, facet FROM tags", output_dir)
        keys = [r["key"] for r in rows]
        assert "quick" in keys
        # Verify facet is "user"
        quick = [r for r in rows if r["key"] == "quick"][0]
        assert quick["facet"] == "user"

    def test_tag_normalises_to_slug(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe

        with _patch_output(output_dir):
            result = tag_recipe(recipe_id=1, tags=["Meal Prep", "COMFORT FOOD"])
        assert "meal-prep" in result
        assert "comfort-food" in result

    def test_tag_reuses_existing_tag(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["weeknight"])
            tag_recipe(recipe_id=2, tags=["weeknight"])

        rows = execute_query("SELECT key FROM tags WHERE key = 'weeknight'", output_dir)
        assert len(rows) == 1  # tag created only once

    def test_tag_duplicate_assignment_ignored(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["weeknight"])
            tag_recipe(recipe_id=1, tags=["weeknight"])

        rows = execute_query("SELECT * FROM recipe_tags WHERE recipe_id = 1", output_dir)
        weeknight_count = len(rows)
        assert weeknight_count == 1

    def test_tag_recipe_not_found(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe

        with _patch_output(output_dir):
            result = tag_recipe(recipe_id=999, tags=["quick"])
        assert "not found" in result.lower()

    def test_tag_empty_list(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe

        with _patch_output(output_dir):
            result = tag_recipe(recipe_id=1, tags=[])
        assert "Error" in result

    def test_tag_display_from_slug(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import tag_recipe
        from recipebrain.query import execute_query

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["meal-prep"])

        rows = execute_query("SELECT display FROM tags WHERE key = 'meal-prep'", output_dir)
        assert rows[0]["display"] == "meal prep"


# ---------------------------------------------------------------------------
# Tests: find_recipe with tags and starred_only
# ---------------------------------------------------------------------------


class TestFindRecipeFilters:
    def test_find_starred_only(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe, star_recipe

        with _patch_output(output_dir):
            star_recipe(recipe_id=1, starred=True)
            result = find_recipe(starred_only=True)
        assert "Zürcher Geschnetzeltes" in result
        assert "Rösti" not in result

    def test_find_starred_only_none_starred(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(starred_only=True)
        assert "No recipes found" in result

    def test_find_by_tag(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe, tag_recipe

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["weeknight"])
            tag_recipe(recipe_id=2, tags=["weeknight", "quick"])
            result = find_recipe(tags=["weeknight"])
        assert "Zürcher Geschnetzeltes" in result
        assert "Rösti" in result

    def test_find_by_multiple_tags_intersect(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe, tag_recipe

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["weeknight"])
            tag_recipe(recipe_id=2, tags=["weeknight", "quick"])
            result = find_recipe(tags=["weeknight", "quick"])
        # Only recipe 2 has both tags
        assert "Rösti" in result
        assert "Zürcher Geschnetzeltes" not in result

    def test_find_by_tag_no_match(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe

        with _patch_output(output_dir):
            result = find_recipe(tags=["nonexistent"])
        assert "No recipes found" in result

    def test_find_combined_tag_and_query(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import find_recipe, tag_recipe

        with _patch_output(output_dir):
            tag_recipe(recipe_id=1, tags=["swiss"])
            tag_recipe(recipe_id=2, tags=["swiss"])
            result = find_recipe(query="rösti", tags=["swiss"])
        assert "Rösti" in result
        assert "Zürcher Geschnetzeltes" not in result


# ---------------------------------------------------------------------------
# Tests: list_starred
# ---------------------------------------------------------------------------


class TestListStarred:
    def test_no_starred(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_starred

        with _patch_output(output_dir):
            result = list_starred()
        assert "No starred" in result

    def test_list_starred_recipes(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_starred, star_recipe

        with _patch_output(output_dir):
            star_recipe(recipe_id=1, starred=True)
            star_recipe(recipe_id=3, starred=True)
            result = list_starred()
        assert "Starred Recipes" in result
        assert "Zürcher Geschnetzeltes" in result
        assert "Fondue" in result
        assert "Rösti" not in result

    def test_list_starred_shows_rating(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_starred, star_recipe

        with _patch_output(output_dir):
            star_recipe(recipe_id=1, starred=True)
            result = list_starred()
        assert "5/5" in result

    def test_list_starred_with_limit(self, output_dir: Path) -> None:
        from recipebrain.mcp_server import list_starred, star_recipe

        with _patch_output(output_dir):
            star_recipe(recipe_id=1, starred=True)
            star_recipe(recipe_id=2, starred=True)
            star_recipe(recipe_id=3, starred=True)
            result = list_starred(limit=2)
        # Table header + separator + 2 data rows
        table_rows = [line for line in result.splitlines() if line.startswith("|")]
        assert len(table_rows) == 4  # header + sep + 2 data
