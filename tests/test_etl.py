"""Tests for the ETL pipeline orchestrator."""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import MagicMock

from recipebrain.etl import (
    _DEFAULT_BATCH_SIZE,
    EtlResult,
    _get_existing_urls,
    _get_source_adapters,
    _get_source_id,
    _next_recipe_id,
    _next_run_id,
    _reconcile_deleted,
    _run_source,
    _seed_lookup_tables,
    _validate_recipe_content,
    _warn_on_suspicious_ingredients,
    run_etl,
)
from recipebrain.settings import PathsConfig, Settings, SourceConfig
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

    def test_writes_tags_from_keywords(self, tmp_path):
        """ETL populates tags and recipe_tags from original_keywords."""
        recipes = {
            "https://example.com/r/1": RawRecipe(
                title="Gemüsepfanne",
                ingredients_raw=["200 g Gemüse"],
                steps_raw=["Braten."],
                source_url="https://example.com/r/1",
                keywords=["Gemüse", "Familien-Gerichte"],
            ),
            "https://example.com/r/2": RawRecipe(
                title="Party-Salat",
                ingredients_raw=["100 g Salat"],
                steps_raw=["Mischen."],
                source_url="https://example.com/r/2",
                keywords=["Salat", "Party", "Gemüse"],
            ),
        }
        adapter = FakeAdapter(urls=list(recipes.keys()), recipes=recipes)

        result = _run_source(adapter, tmp_path)

        assert result.fetched == 2

        # Verify tags were created
        tags = read_table("tags", tmp_path)
        assert tags.num_rows > 0

        tag_keys = set(tags.column("key").to_pylist())
        assert "gemüse" in tag_keys
        assert "party" in tag_keys
        assert "familien-gerichte" in tag_keys
        assert "salat" in tag_keys

        # Verify facets
        key_to_facet = dict(
            zip(tags.column("key").to_pylist(), tags.column("facet").to_pylist(), strict=False)
        )
        assert key_to_facet["gemüse"] == "ingredient"
        assert key_to_facet["party"] == "occasion"
        assert key_to_facet["familien-gerichte"] == "audience"

        # Verify recipe_tags links
        recipe_tags = read_table("recipe_tags", tmp_path)
        assert recipe_tags.num_rows > 0

        # Recipe 1 should have 2 tags, recipe 2 should have 3
        rt_rows = recipe_tags.to_pylist()
        recipe_1_id = read_table("recipes", tmp_path).column("id").to_pylist()[0]
        recipe_2_id = read_table("recipes", tmp_path).column("id").to_pylist()[1]
        r1_links = [r for r in rt_rows if r["recipe_id"] == recipe_1_id]
        r2_links = [r for r in rt_rows if r["recipe_id"] == recipe_2_id]
        assert len(r1_links) == 2
        assert len(r2_links) == 3

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

    def test_language_safety_net_skips_wrong_language(self, tmp_path):
        """ETL skips recipes whose language is not in allowed_languages."""
        recipes = {
            "https://example.com/de/r1": RawRecipe(
                title="German",
                ingredients_raw=["100 g Mehl"],
                steps_raw=["Mischen."],
                source_url="https://example.com/de/r1",
                language="de",
            ),
            "https://example.com/fr/r2": RawRecipe(
                title="French",
                ingredients_raw=["100 g farine"],
                steps_raw=["Mélanger."],
                source_url="https://example.com/fr/r2",
                language="fr",
            ),
        }
        adapter = FakeAdapter(
            urls=list(recipes.keys()),
            recipes=recipes,
        )

        result = _run_source(adapter, tmp_path, allowed_languages=["de"])

        assert result.fetched == 1
        assert result.skipped == 1

        table = read_table("recipes", tmp_path)
        assert table.num_rows == 1
        assert table.column("title").to_pylist() == ["German"]

    def test_language_safety_net_allows_all_when_none(self, tmp_path):
        """When allowed_languages is None, all recipes are ingested."""
        recipes = {
            "https://example.com/fr/r1": RawRecipe(
                title="French",
                ingredients_raw=["100 g farine"],
                steps_raw=["Mélanger."],
                source_url="https://example.com/fr/r1",
                language="fr",
            ),
        }
        adapter = FakeAdapter(urls=list(recipes.keys()), recipes=recipes)

        result = _run_source(adapter, tmp_path, allowed_languages=None)

        assert result.fetched == 1


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
    def _all_enabled_settings(self) -> Settings:
        """Return settings with all sources explicitly enabled."""
        all_sources = {
            k: SourceConfig(enabled=True)
            for k in ("bettybossi", "fooby", "migusto", "swissmilk", "schweizerfleisch")
        }
        return Settings(sources=all_sources)

    def test_all_four_adapters_registered(self):
        settings = self._all_enabled_settings()
        adapters = _get_source_adapters(settings, source_filter=None)
        keys = {a.key for a in adapters}
        assert keys == {"bettybossi", "fooby", "migusto", "swissmilk", "schweizerfleisch"}

    def test_filter_returns_single(self):
        settings = self._all_enabled_settings()
        adapters = _get_source_adapters(settings, source_filter="swissmilk")
        assert len(adapters) == 1
        assert adapters[0].key == "swissmilk"

    def test_filter_unknown_returns_empty(self):
        settings = self._all_enabled_settings()
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


class TestInterruptSafety:
    def test_flush_on_keyboard_interrupt(self, tmp_path):
        """Data accumulated before Ctrl+C is flushed to disk."""
        call_count = 0

        class InterruptAfterTwo(FakeAdapter):
            def fetch(self, url: str) -> RawRecipe:
                nonlocal call_count
                call_count += 1
                if call_count > 2:
                    raise KeyboardInterrupt
                return super().fetch(url)

        adapter = InterruptAfterTwo(urls=[f"https://a.ch/{i}" for i in range(5)])
        result = _run_source(adapter, tmp_path)

        assert result.fetched == 2
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 2

    def test_flush_on_interrupt_with_batch(self, tmp_path):
        """Interrupt mid-batch still flushes the partial batch."""
        call_count = 0

        class InterruptAfterThree(FakeAdapter):
            def fetch(self, url: str) -> RawRecipe:
                nonlocal call_count
                call_count += 1
                if call_count > 3:
                    raise KeyboardInterrupt
                return super().fetch(url)

        adapter = InterruptAfterThree(urls=[f"https://a.ch/{i}" for i in range(10)])
        result = _run_source(adapter, tmp_path, batch_size=5)

        assert result.fetched == 3
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 3


class TestDefaultBatchSize:
    def test_default_batch_size_is_set(self):
        assert _DEFAULT_BATCH_SIZE > 0

    def test_default_batch_used_when_none(self, tmp_path):
        """When batch_size is not specified, the default is used for periodic flushing."""
        adapter = FakeAdapter(urls=[f"https://a.ch/{i}" for i in range(_DEFAULT_BATCH_SIZE + 5)])
        result = _run_source(adapter, tmp_path)

        assert result.fetched == _DEFAULT_BATCH_SIZE + 5
        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == _DEFAULT_BATCH_SIZE + 5


class TestGetSourceId:
    def test_bettybossi_has_source_id(self):
        adapter = FakeAdapter()
        adapter.key = "bettybossi"  # type: ignore[misc]
        assert _get_source_id(adapter) == 1

    def test_all_sources_have_unique_ids(self):
        ids = set()
        for key in ("bettybossi", "fooby", "migusto", "swissmilk", "schweizerfleisch"):
            adapter = FakeAdapter()
            adapter.key = key  # type: ignore[misc]
            sid = _get_source_id(adapter)
            assert sid != 99, f"{key} should not fall back to 99"
            ids.add(sid)
        assert len(ids) == 5, "All source IDs should be unique"


class TestEtlRunLog:
    def test_run_source_writes_etl_run(self, tmp_path):
        """A successful _run_source writes one row to etl_runs."""
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2"])
        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert len(runs) == 1
        row = runs[0]
        assert row["source"] == "fake"
        assert row["discovered"] == 2
        assert row["fetched"] == 2
        assert row["skipped"] == 0
        assert row["errors"] == 0
        assert row["status"] == "success"
        assert row["duration_seconds"] >= 0
        assert row["started_at"] is not None
        assert row["finished_at"] is not None

    def test_run_source_logs_errors_as_partial(self, tmp_path):
        """A run with some errors and some successes is logged as partial."""
        call_count = 0

        class PartialFailAdapter(FakeAdapter):
            def fetch(self, url: str) -> RawRecipe:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise ValueError("bad page")
                return super().fetch(url)

        adapter = PartialFailAdapter(urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3"])
        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert len(runs) == 1
        assert runs[0]["status"] == "partial"
        assert runs[0]["errors"] == 1
        assert runs[0]["fetched"] == 2
        assert "bad page" in runs[0]["error_summary"]

    def test_run_source_logs_discovery_failure(self, tmp_path):
        """A discovery failure still logs a run with status=failed."""
        adapter = FakeAdapter()
        adapter.discover = MagicMock(side_effect=RuntimeError("network down"))

        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert len(runs) == 1
        assert runs[0]["status"] == "failed"
        assert runs[0]["discovered"] == 0
        assert "Discovery failed" in runs[0]["error_summary"]

    def test_run_source_logs_all_failures_as_failed(self, tmp_path):
        """When all fetches fail, status is failed."""
        adapter = FakeAdapter(urls=["https://a.ch/1", "https://a.ch/2"])
        adapter.fetch = MagicMock(side_effect=ValueError("broken"))

        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["status"] == "failed"
        assert runs[0]["fetched"] == 0
        assert runs[0]["errors"] == 2

    def test_run_source_logs_batch_size_and_limit(self, tmp_path):
        """batch_size and limit are captured in the log."""
        adapter = FakeAdapter(urls=["https://a.ch/1"])
        _run_source(adapter, tmp_path, batch_size=5, limit=10)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["batch_size"] == 5
        assert runs[0]["limit"] == 10

    def test_run_source_logs_default_batch_size(self, tmp_path):
        """When batch_size is None, the default is recorded."""
        adapter = FakeAdapter(urls=["https://a.ch/1"])
        _run_source(adapter, tmp_path, batch_size=None)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["batch_size"] == _DEFAULT_BATCH_SIZE

    def test_run_source_logs_null_limit(self, tmp_path):
        """When limit is None, it is stored as null."""
        adapter = FakeAdapter(urls=["https://a.ch/1"])
        _run_source(adapter, tmp_path, limit=None)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["limit"] is None

    def test_run_source_logs_soft_deleted(self, tmp_path):
        """soft_deleted count is captured in the log."""
        from recipebrain.writer import write_table as wt

        wt(
            "recipes",
            [
                {"id": 1, "source_id": 99, "source_url": "https://a.ch/gone", "status": "active"},
            ],
            tmp_path,
        )
        # FakeAdapter discovers nothing for source_id=99 → the existing recipe gets soft-deleted
        adapter = FakeAdapter(urls=[])
        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["soft_deleted"] == 1

    def test_multiple_runs_get_sequential_ids(self, tmp_path):
        """Each run gets an incrementing ID."""
        for i in range(3):
            adapter = FakeAdapter(urls=[f"https://a.ch/{i}"])
            _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        ids = [r["id"] for r in runs]
        assert ids == [1, 2, 3]

    def test_interrupt_logged_as_interrupted(self, tmp_path):
        """A KeyboardInterrupt results in status=interrupted."""
        call_count = 0

        class InterruptAdapter(FakeAdapter):
            def fetch(self, url: str) -> RawRecipe:
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise KeyboardInterrupt
                return super().fetch(url)

        adapter = InterruptAdapter(urls=["https://a.ch/1", "https://a.ch/2", "https://a.ch/3"])
        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["status"] == "interrupted"


class TestNextRunId:
    def test_returns_1_when_no_data(self, tmp_path):
        assert _next_run_id(tmp_path) == 1

    def test_returns_next_after_existing(self, tmp_path):
        from recipebrain.writer import write_table as wt

        wt("etl_runs", [{"id": 5, "source": "test"}], tmp_path)
        assert _next_run_id(tmp_path) == 6

    def test_logs_warning_on_unexpected_error(self, tmp_path, caplog):
        """Non-FileNotFoundError exceptions log a warning and return 1."""
        import logging

        # Write a corrupted file so read_table raises something unexpected
        etl_runs_path = tmp_path / "etl_runs.parquet"
        etl_runs_path.write_text("not valid parquet data")

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            result = _next_run_id(tmp_path)

        assert result == 1
        assert "failed to read etl_runs for next ID" in caplog.text

    def test_no_warning_on_missing_file(self, tmp_path, caplog):
        """FileNotFoundError does not log a warning (normal first-run case)."""
        import logging

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            result = _next_run_id(tmp_path)

        assert result == 1
        assert "failed to read etl_runs" not in caplog.text


class TestEtlRunLogWarning:
    def test_log_etl_run_warns_on_write_failure(self, tmp_path, caplog, monkeypatch):
        """_log_etl_run logs a warning with exc_info when append_table fails."""
        import logging

        from recipebrain.etl import _log_etl_run

        monkeypatch.setattr(
            "recipebrain.etl.append_table",
            MagicMock(side_effect=OSError("disk full")),
        )

        result = EtlResult(source="fake", discovered=1, fetched=1)
        started_at = datetime.now(UTC)
        t0 = time.monotonic()

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _log_etl_run(
                result,
                started_at,
                t0,
                batch_size=20,
                limit=None,
                status="success",
                output_dir=tmp_path,
            )

        assert "failed to write etl_runs log for fake" in caplog.text
        # exc_info=True means the traceback is included
        assert "disk full" in caplog.text


class _FoobyAdapter(SourceAdapter):
    """Adapter with a key that exists in _SOURCE_METADATA."""

    key: ClassVar[str] = "fooby"
    display_name: ClassVar[str] = "Fooby"
    languages: ClassVar[tuple[str, ...]] = ("de",)

    def discover(self) -> Iterable[str]:
        return []

    def fetch(self, url: str) -> RawRecipe:
        raise NotImplementedError


class TestSeedLookupTables:
    """Tests for _seed_lookup_tables."""

    def test_seeds_sources_when_missing(self, tmp_path):
        """sources.parquet is created with adapter metadata."""
        adapter = _FoobyAdapter()
        _seed_lookup_tables(tmp_path, [adapter])

        sources = read_table("sources", tmp_path).to_pylist()
        assert len(sources) == 1
        row = sources[0]
        assert row["id"] == 2
        assert row["key"] == "fooby"
        assert row["display_name"] == "Fooby"
        assert row["base_url"] == "https://fooby.ch"
        assert row["language"] == "de"
        assert row["kind"] == "scraped"

    def test_seeds_ingredients_when_missing(self, tmp_path):
        """ingredients.parquet is created with the seed catalogue."""
        _seed_lookup_tables(tmp_path, [])

        ingredients = read_table("ingredients", tmp_path).to_pylist()
        assert len(ingredients) > 0
        # Verify structure matches schema
        assert "id" in ingredients[0]
        assert "key" in ingredients[0]
        assert "display_de" in ingredients[0]

    def test_idempotent_does_not_overwrite_sources(self, tmp_path):
        """If sources already has data, seeding does not replace it."""
        write_table(
            "sources",
            [
                {
                    "id": 99,
                    "key": "custom",
                    "display_name": "Custom",
                    "base_url": "https://x.ch",
                    "language": "fr",
                    "kind": "manual",
                }
            ],
            tmp_path,
        )
        adapter = _FoobyAdapter()
        _seed_lookup_tables(tmp_path, [adapter])

        sources = read_table("sources", tmp_path).to_pylist()
        assert len(sources) == 1
        assert sources[0]["id"] == 99  # original data preserved

    def test_idempotent_does_not_overwrite_ingredients(self, tmp_path):
        """If ingredients already has data, seeding does not replace it."""
        write_table(
            "ingredients",
            [{"id": 999, "key": "test_ing", "display_de": "TestZutat", "category": "other"}],
            tmp_path,
        )
        _seed_lookup_tables(tmp_path, [])

        ingredients = read_table("ingredients", tmp_path).to_pylist()
        assert len(ingredients) == 1
        assert ingredients[0]["id"] == 999  # original data preserved

    def test_unknown_adapter_key_skipped(self, tmp_path):
        """Adapters not in _SOURCE_METADATA are silently skipped."""
        adapter = FakeAdapter()  # key="fake", not in metadata
        _seed_lookup_tables(tmp_path, [adapter])

        # No sources written (no valid metadata), but ingredients still seeded
        import pytest

        from recipebrain.writer import DataStaleError

        with pytest.raises(DataStaleError):
            read_table("sources", tmp_path)

    def test_multiple_adapters_seeded(self, tmp_path):
        """Multiple known adapters are all written to sources."""

        class _BettyAdapter(SourceAdapter):
            key: ClassVar[str] = "bettybossi"
            display_name: ClassVar[str] = "Betty Bossi"
            languages: ClassVar[tuple[str, ...]] = ("de",)

            def discover(self) -> Iterable[str]:
                return []

            def fetch(self, url: str) -> RawRecipe:
                raise NotImplementedError

        _seed_lookup_tables(tmp_path, [_FoobyAdapter(), _BettyAdapter()])

        sources = read_table("sources", tmp_path).to_pylist()
        assert len(sources) == 2
        ids = {s["id"] for s in sources}
        assert ids == {1, 2}  # bettybossi=1, fooby=2


class TestValidateRecipeContent:
    """Tests for _validate_recipe_content — rejects empty recipes."""

    def test_rejects_empty_ingredients_and_steps(self):
        raw = RawRecipe(title="Empty Page", ingredients_raw=[], steps_raw=[])
        assert _validate_recipe_content(raw, "https://a.ch/empty") is False

    def test_accepts_recipe_with_ingredients_only(self):
        raw = RawRecipe(title="Salad", ingredients_raw=["100 g Tomaten"], steps_raw=[])
        assert _validate_recipe_content(raw, "https://a.ch/salad") is True

    def test_accepts_recipe_with_steps_only(self):
        raw = RawRecipe(title="Quick Tip", ingredients_raw=[], steps_raw=["Mix well."])
        assert _validate_recipe_content(raw, "https://a.ch/tip") is True

    def test_accepts_recipe_with_both(self):
        raw = RawRecipe(
            title="Full Recipe",
            ingredients_raw=["200 g Mehl"],
            steps_raw=["Mischen."],
            description="A good recipe",
        )
        assert _validate_recipe_content(raw, "https://a.ch/full") is True

    def test_warns_on_empty_description(self, caplog):
        import logging

        raw = RawRecipe(
            title="No Desc",
            ingredients_raw=["100 g Butter"],
            steps_raw=["Schmelzen."],
            description="",
        )
        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            result = _validate_recipe_content(raw, "https://a.ch/nodesc")

        assert result is True
        assert "empty description" in caplog.text

    def test_no_warning_when_description_present(self, caplog):
        import logging

        raw = RawRecipe(
            title="Good",
            ingredients_raw=["1 Ei"],
            steps_raw=["Kochen."],
            description="A nice dish.",
        )
        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _validate_recipe_content(raw, "https://a.ch/good")

        assert "empty description" not in caplog.text

    def test_warns_on_suspicious_nav_ingredients(self, caplog):
        import logging

        raw = RawRecipe(
            title="Bad",
            ingredients_raw=["ShopHauptmenüJetzt entdecken", "Werbung buchen"],
            steps_raw=["Some step."],
        )
        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            result = _validate_recipe_content(raw, "https://a.ch/nav")

        assert result is True  # warns but doesn't reject
        assert "suspicious ingredients" in caplog.text

    def test_warns_on_long_average_ingredients(self, caplog):
        import logging

        raw = RawRecipe(
            title="Long",
            ingredients_raw=["x" * 200, "y" * 200],
            steps_raw=["Cook."],
        )
        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _validate_recipe_content(raw, "https://a.ch/long")

        assert "avg length" in caplog.text

    def test_no_warning_on_good_ingredients(self, caplog):
        import logging

        raw = RawRecipe(
            title="Good",
            ingredients_raw=["200 g Mehl", "3 Eier", "1 dl Milch"],
            steps_raw=["Mischen."],
            description="Nice.",
        )
        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _validate_recipe_content(raw, "https://a.ch/good")

        assert "suspicious" not in caplog.text


class TestWarnOnSuspiciousIngredients:
    """Tests for the _warn_on_suspicious_ingredients helper."""

    def test_no_warning_for_normal_ingredients(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _warn_on_suspicious_ingredients(["200 g Mehl", "3 Eier", "1 Prise Salz"], "http://test")
        assert caplog.text == ""

    def test_warns_on_nav_keywords(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _warn_on_suspicious_ingredients(
                ["ShopHauptmenüMenu Schliessen", "Jetzt entdecken"], "http://test"
            )
        assert "navigation keywords" in caplog.text

    def test_warns_on_excessive_length(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _warn_on_suspicious_ingredients(["a" * 200, "b" * 180], "http://test")
        assert "avg length" in caplog.text

    def test_warns_on_no_numbers(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="recipebrain.etl"):
            _warn_on_suspicious_ingredients(["Butter", "Mehl", "Salz", "Pfeffer"], "http://test")
        assert "contain numbers" in caplog.text


class TestValidationSkippedInPipeline:
    """Integration tests: _run_source skips invalid recipes."""

    def test_skips_recipe_without_content(self, tmp_path):
        empty_recipe = RawRecipe(
            title="Category Page",
            ingredients_raw=[],
            steps_raw=[],
            source_url="https://a.ch/category",
        )
        adapter = FakeAdapter(
            urls=["https://a.ch/category", "https://a.ch/real"],
            recipes={"https://a.ch/category": empty_recipe},
        )

        result = _run_source(adapter, tmp_path)

        assert result.discovered == 2
        assert result.fetched == 1
        assert result.validation_skipped == 1

        recipes = read_table("recipes", tmp_path)
        assert recipes.num_rows == 1

    def test_all_invalid_skipped(self, tmp_path):
        empty1 = RawRecipe(
            title="Empty1", ingredients_raw=[], steps_raw=[], source_url="https://a.ch/1"
        )
        empty2 = RawRecipe(
            title="Empty2", ingredients_raw=[], steps_raw=[], source_url="https://a.ch/2"
        )
        adapter = FakeAdapter(
            urls=["https://a.ch/1", "https://a.ch/2"],
            recipes={"https://a.ch/1": empty1, "https://a.ch/2": empty2},
        )

        result = _run_source(adapter, tmp_path)

        assert result.fetched == 0
        assert result.validation_skipped == 2

    def test_validation_skipped_logged_in_etl_run(self, tmp_path):
        empty_recipe = RawRecipe(
            title="Bad Page",
            ingredients_raw=[],
            steps_raw=[],
            source_url="https://a.ch/bad",
        )
        adapter = FakeAdapter(
            urls=["https://a.ch/bad", "https://a.ch/good"],
            recipes={"https://a.ch/bad": empty_recipe},
        )

        _run_source(adapter, tmp_path)

        runs = read_table("etl_runs", tmp_path).to_pylist()
        assert runs[0]["validation_skipped"] == 1
