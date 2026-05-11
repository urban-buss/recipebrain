"""Tests for the ETL pipeline orchestrator."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar
from unittest.mock import MagicMock

from recipebrain.etl import (
    EtlResult,
    _get_existing_urls,
    _get_source_adapters,
    _next_recipe_id,
    _reconcile_deleted,
    _run_source,
    run_etl,
)
from recipebrain.settings import PathsConfig, Settings
from recipebrain.sources.base import RawRecipe, SourceAdapter
from recipebrain.writer import read_table, write_table


def _settings_for(tmp_path) -> Settings:
    """Create Settings with output_dir and snapshot_dir under tmp_path."""
    return Settings(
        paths=PathsConfig(
            output_dir=str(tmp_path / "output"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    )


class FakeAdapter(SourceAdapter):
    """Fake adapter for testing ETL without HTTP."""

    key: ClassVar[str] = "fake"
    display_name: ClassVar[str] = "Fake"
    languages: ClassVar[tuple[str, ...]] = ("de",)

    def __init__(self, urls: list[str] | None = None, recipes: dict | None = None) -> None:
        self._urls = urls or []
        self._recipes = recipes or {}

    def discover(self) -> Iterable[str]:
        return self._urls

    def fetch(self, url: str) -> RawRecipe:
        if url in self._recipes:
            return self._recipes[url]
        return RawRecipe(
            title=f"Recipe from {url}",
            ingredients_raw=["100 g Mehl", "2 Eier"],
            steps_raw=["Mischen.", "Backen."],
            source_url=url,
            image_urls=["https://img.ch/1.jpg"],
        )


class TestRunSource:
    def test_basic_pipeline(self, tmp_path):
        adapter = FakeAdapter(urls=["https://example.com/r/1", "https://example.com/r/2"])

        result = _run_source(adapter, tmp_path)

        assert result.source == "fake"
        assert result.discovered == 2
        assert result.fetched == 2
        assert result.errors == 0

        # Verify data was written
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 2

        steps = read_table("recipe_steps", tmp_path)
        assert steps.num_rows == 4  # 2 steps per recipe

        ingredients = read_table("recipe_ingredients", tmp_path)
        assert ingredients.num_rows == 4  # 2 ingredients per recipe

        images = read_table("recipe_images", tmp_path)
        assert images.num_rows == 2  # 1 image per recipe

    def test_skips_existing_urls(self, tmp_path):
        # Pre-populate with one recipe
        write_table(
            "recipes",
            [{"id": 1, "source_url": "https://example.com/r/1", "title": "Existing"}],
            tmp_path,
        )

        adapter = FakeAdapter(urls=["https://example.com/r/1", "https://example.com/r/2"])
        result = _run_source(adapter, tmp_path)

        assert result.discovered == 2
        assert result.skipped == 1
        assert result.fetched == 1

    def test_handles_fetch_errors(self, tmp_path):
        adapter = FakeAdapter(urls=["https://example.com/r/bad"])
        adapter.fetch = MagicMock(side_effect=ValueError("page broken"))

        result = _run_source(adapter, tmp_path)

        assert result.discovered == 1
        assert result.fetched == 0
        assert result.errors == 1
        assert "Fetch failed" in result.error_details[0]

    def test_handles_discover_errors(self, tmp_path):
        adapter = FakeAdapter()
        adapter.discover = MagicMock(side_effect=RuntimeError("network down"))

        result = _run_source(adapter, tmp_path)

        assert result.errors == 1
        assert result.discovered == 0
        assert "Discovery failed" in result.error_details[0]

    def test_assigns_sequential_ids(self, tmp_path):
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3"])
        _run_source(adapter, tmp_path)

        recipes = read_table("recipes", tmp_path)
        ids = recipes.column("id").to_pylist()
        assert ids == [1, 2, 3]

    def test_continues_ids_from_existing(self, tmp_path):
        write_table(
            "recipes", [{"id": 5, "source_url": "https://old.ch/x", "title": "Old"}], tmp_path
        )

        adapter = FakeAdapter(urls=["https://new.ch/1"])
        _run_source(adapter, tmp_path)

        recipes = read_table("recipes", tmp_path)
        ids = recipes.column("id").to_pylist()
        assert 6 in ids


class TestNextRecipeId:
    def test_returns_1_when_no_data(self, tmp_path):
        assert _next_recipe_id(tmp_path) == 1

    def test_returns_next_after_existing(self, tmp_path):
        write_table("recipes", [{"id": 10, "title": "X"}], tmp_path)
        assert _next_recipe_id(tmp_path) == 11


class TestGetExistingUrls:
    def test_returns_empty_when_no_data(self, tmp_path):
        assert _get_existing_urls(tmp_path) == set()

    def test_returns_urls_from_existing(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "source_url": "https://a.ch/1"},
                {"id": 2, "source_url": "https://a.ch/2"},
            ],
            tmp_path,
        )
        assert _get_existing_urls(tmp_path) == {"https://a.ch/1", "https://a.ch/2"}


class TestRunEtl:
    def test_returns_empty_for_unknown_source(self, tmp_path):
        settings = _settings_for(tmp_path)
        (tmp_path / "output").mkdir()
        results = run_etl(settings, source_filter="nonexistent")
        assert results == []

    def test_empty_result_has_correct_structure(self):
        r = EtlResult(source="test")
        assert r.discovered == 0
        assert r.fetched == 0
        assert r.skipped == 0
        assert r.errors == 0
        assert r.error_details == []

    def test_limit_passed_to_run_source(self, tmp_path):
        settings = _settings_for(tmp_path)
        (tmp_path / "output").mkdir()
        # With an unknown source, nothing runs — but this validates the param is accepted
        results = run_etl(settings, source_filter="nonexistent", limit=5)
        assert results == []


class TestPreEtlBackup:
    def test_creates_snapshot_before_etl(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        snapshots = tmp_path / "snapshots"
        write_table("recipes", [{"id": 1, "title": "X"}], output)

        settings = _settings_for(tmp_path)
        run_etl(settings, source_filter="nonexistent")

        snap_dirs = list(snapshots.iterdir())
        assert len(snap_dirs) == 1
        assert "pre-etl" in snap_dirs[0].name

    def test_etl_continues_when_no_data_to_snapshot(self, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        settings = _settings_for(tmp_path)
        # No parquet files → snapshot returns None, but ETL should still proceed
        results = run_etl(settings, source_filter="nonexistent")
        assert results == []


class TestRunSourceLimit:
    def test_limit_caps_fetched(self, tmp_path):
        adapter = FakeAdapter(
            urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3", "https://a.ch/4"]
        )
        result = _run_source(adapter, tmp_path, limit=2)

        assert result.discovered == 4
        assert result.fetched == 2

        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 2

    def test_limit_none_fetches_all(self, tmp_path):
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3"])
        result = _run_source(adapter, tmp_path, limit=None)

        assert result.fetched == 3

    def test_limit_with_skips(self, tmp_path):
        """Limit counts only new fetches, not skips."""
        write_table(
            "recipes",
            [{"id": 1, "source_url": "https://a.ch/1", "title": "Existing"}],
            tmp_path,
        )
        adapter = FakeAdapter(
            urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3", "https://a.ch/4"]
        )
        result = _run_source(adapter, tmp_path, limit=2)

        assert result.skipped == 1
        assert result.fetched == 2

    def test_limit_zero_fetches_none(self, tmp_path):
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2"])
        result = _run_source(adapter, tmp_path, limit=0)

        assert result.fetched == 0
        assert result.discovered == 2


class TestGetSourceAdapters:
    def test_all_four_adapters_registered(self):
        settings = Settings.load(None)
        adapters = _get_source_adapters(settings, source_filter=None)
        keys = {a.key for a in adapters}
        assert keys == {"bettybossi", "fooby", "migusto", "swissmilk", "schweizerfleisch"}

    def test_filter_returns_single(self):
        settings = Settings.load(None)
        adapters = _get_source_adapters(settings, source_filter="swissmilk")
        assert len(adapters) == 1
        assert adapters[0].key == "swissmilk"

    def test_filter_unknown_returns_empty(self):
        settings = Settings.load(None)
        adapters = _get_source_adapters(settings, source_filter="nonexistent")
        assert adapters == []


class TestReconcileDeleted:
    def test_soft_deletes_missing_urls(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "source_id": 1, "source_url": "https://a.ch/1", "status": "active"},
                {"id": 2, "source_id": 1, "source_url": "https://a.ch/2", "status": "active"},
                {"id": 3, "source_id": 1, "source_url": "https://a.ch/3", "status": "active"},
            ],
            tmp_path,
        )
        deleted = _reconcile_deleted(1, {"https://a.ch/1", "https://a.ch/3"}, tmp_path)
        assert deleted == 1

        rows = read_table("recipes", tmp_path).to_pylist()
        statuses = {r["source_url"]: r["status"] for r in rows}
        assert statuses["https://a.ch/1"] == "active"
        assert statuses["https://a.ch/2"] == "deleted"
        assert statuses["https://a.ch/3"] == "active"

    def test_ignores_other_sources(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "source_id": 1, "source_url": "https://a.ch/1", "status": "active"},
                {"id": 2, "source_id": 2, "source_url": "https://b.ch/1", "status": "active"},
            ],
            tmp_path,
        )
        # source_id=1 discovers nothing → its recipe should be deleted
        # source_id=2 recipe should be untouched
        deleted = _reconcile_deleted(1, set(), tmp_path)
        assert deleted == 1

        rows = read_table("recipes", tmp_path).to_pylist()
        assert rows[0]["status"] == "deleted"
        assert rows[1]["status"] == "active"

    def test_skips_already_deleted(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "source_id": 1, "source_url": "https://a.ch/1", "status": "deleted"},
            ],
            tmp_path,
        )
        deleted = _reconcile_deleted(1, set(), tmp_path)
        assert deleted == 0

    def test_no_data_returns_zero(self, tmp_path):
        assert _reconcile_deleted(1, set(), tmp_path) == 0

    def test_all_urls_present_returns_zero(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "source_id": 1, "source_url": "https://a.ch/1", "status": "active"},
            ],
            tmp_path,
        )
        deleted = _reconcile_deleted(1, {"https://a.ch/1"}, tmp_path)
        assert deleted == 0


class TestBatchWriting:
    def test_batch_flushes_periodically(self, tmp_path):
        """With batch_size=2, data is written in chunks."""
        adapter = FakeAdapter(urls=[f"https://a.ch/{i}" for i in range(5)])
        result = _run_source(adapter, tmp_path, batch_size=2)

        assert result.fetched == 5
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 5

    def test_batch_with_limit(self, tmp_path):
        """batch_size and limit work together."""
        adapter = FakeAdapter(urls=[f"https://a.ch/{i}" for i in range(10)])
        result = _run_source(adapter, tmp_path, limit=5, batch_size=2)

        assert result.fetched == 5
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 5

    def test_batch_size_none_writes_once(self, tmp_path):
        """batch_size=None collects all and writes at the end (default)."""
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3"])
        result = _run_source(adapter, tmp_path, batch_size=None)

        assert result.fetched == 3
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 3

    def test_batch_preserves_ids(self, tmp_path):
        """IDs remain sequential across batch flushes."""
        adapter = FakeAdapter(urls=[f"https://a.ch/{i}" for i in range(6)])
        _run_source(adapter, tmp_path, batch_size=2)

        recipes = read_table("recipes", tmp_path)
        ids = recipes.column("id").to_pylist()
        assert ids == [1, 2, 3, 4, 5, 6]

    def test_run_etl_passes_batch_size(self, tmp_path):
        settings = _settings_for(tmp_path)
        (tmp_path / "output").mkdir()
        results = run_etl(settings, source_filter="nonexistent", batch_size=10)
        assert results == []
