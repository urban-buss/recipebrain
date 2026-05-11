"""Tests for the test dataset factory itself."""

from __future__ import annotations

from recipebrain.writer import read_table
from tests.dataset_factory import (
    make_cook_log,
    make_ingredient,
    make_promotion,
    make_recipe,
    make_recipe_ingredient,
    make_recipe_step,
    make_source,
    make_tag,
    write_dataset,
)


class TestMakeFactories:
    def test_make_recipe_defaults(self):
        r = make_recipe()
        assert r["id"] == 1
        assert r["title"] == "Test Recipe"

    def test_make_recipe_override(self):
        r = make_recipe(id=42, title="Custom")
        assert r["id"] == 42
        assert r["title"] == "Custom"

    def test_make_source_defaults(self):
        s = make_source()
        assert s["key"] == "fooby"

    def test_make_ingredient_defaults(self):
        i = make_ingredient()
        assert i["key"] == "mehl"

    def test_make_recipe_ingredient_defaults(self):
        ri = make_recipe_ingredient()
        assert ri["raw_text"] == "200 g Mehl"

    def test_make_recipe_step_defaults(self):
        s = make_recipe_step()
        assert "Mix" in s["text"]

    def test_make_cook_log_defaults(self):
        cl = make_cook_log()
        assert cl["recipe_id"] == 1

    def test_make_tag_defaults(self):
        t = make_tag()
        assert t["key"] == "quick"

    def test_make_promotion_defaults(self):
        p = make_promotion()
        assert p["product_name"] == "Butter"


class TestWriteDataset:
    def test_writes_multiple_entities(self, tmp_path):
        write_dataset(
            tmp_path,
            sources=[make_source()],
            recipes=[make_recipe()],
            recipe_steps=[make_recipe_step()],
        )
        assert read_table("sources", tmp_path).num_rows == 1
        assert read_table("recipes", tmp_path).num_rows == 1
        assert read_table("recipe_steps", tmp_path).num_rows == 1

    def test_skips_none_entities(self, tmp_path):
        write_dataset(tmp_path, sources=[make_source()])
        assert (tmp_path / "sources.parquet").exists()
        assert not (tmp_path / "recipes.parquet").exists()


class TestPopulatedOutputFixture:
    def test_fixture_has_data(self, populated_output):
        recipes = read_table("recipes", populated_output)
        assert recipes.num_rows == 2
        sources = read_table("sources", populated_output)
        assert sources.num_rows == 1
