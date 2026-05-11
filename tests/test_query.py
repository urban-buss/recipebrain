"""Tests for the DuckDB query layer."""

from __future__ import annotations

import pytest

from recipebrain.query import (
    DataStaleError,
    QueryError,
    create_connection,
    execute_query,
    invalidate_connection,
    search_recipes,
    validate_sql,
)
from recipebrain.writer import write_table


class TestValidateSql:
    def test_accepts_select(self):
        assert validate_sql("SELECT * FROM recipes") == "SELECT * FROM recipes"

    def test_accepts_with_clause(self):
        sql = "WITH cte AS (SELECT 1) SELECT * FROM cte"
        assert validate_sql(sql) == sql

    def test_strips_whitespace(self):
        assert validate_sql("  SELECT 1  ") == "SELECT 1"

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO recipes VALUES (1)",
            "UPDATE recipes SET title = 'x'",
            "DELETE FROM recipes",
            "DROP TABLE recipes",
            "CREATE TABLE evil (id int)",
            "ALTER TABLE recipes ADD col int",
            "TRUNCATE TABLE recipes",
            "GRANT ALL ON recipes TO public",
        ],
    )
    def test_rejects_dml_ddl(self, sql):
        with pytest.raises(QueryError, match="Forbidden SQL keyword"):
            validate_sql(sql)

    def test_rejects_empty(self):
        with pytest.raises(QueryError, match="Empty SQL"):
            validate_sql("")

    def test_rejects_keyword_in_subquery(self):
        with pytest.raises(QueryError):
            validate_sql("SELECT * FROM (DELETE FROM recipes)")

    def test_ignores_keywords_in_comments(self):
        # Keywords in comments should still be caught (security-first)
        # Our implementation strips comments before checking
        sql = "SELECT * FROM recipes -- safe query"
        assert validate_sql(sql) == sql

    def test_case_insensitive_rejection(self):
        with pytest.raises(QueryError):
            validate_sql("insert into recipes values (1)")

    @pytest.mark.parametrize(
        "sql",
        [
            "COPY recipes TO 'out.csv'",
            "ATTACH DATABASE 'file.db' AS ext",
            "PRAGMA table_info('recipes')",
            "LOAD 'httpfs'",
            "INSTALL 'httpfs'",
        ],
    )
    def test_rejects_additional_keywords(self, sql):
        with pytest.raises(QueryError, match="Forbidden SQL keyword"):
            validate_sql(sql)

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM read_parquet('evil.parquet')",
            "SELECT * FROM read_csv('evil.csv')",
            "SELECT * FROM read_csv_auto('evil.csv')",
            "SELECT * FROM read_json('evil.json')",
            "SELECT * FROM read_json_auto('evil.json')",
            "SELECT * FROM parquet_scan('evil.parquet')",
            "SELECT * FROM parquet_metadata('evil.parquet')",
            "SELECT * FROM parquet_schema('evil.parquet')",
        ],
    )
    def test_rejects_file_access_functions(self, sql):
        with pytest.raises(QueryError, match="Forbidden SQL function"):
            validate_sql(sql)


class TestCreateConnection:
    def test_creates_connection_with_views(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        write_table("recipes", [{"id": 1, "title": "Test"}], tmp_path)

        conn = create_connection(tmp_path)
        result = conn.execute("SELECT key FROM sources").fetchall()
        assert result == [("fooby",)]

    def test_raises_on_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        with pytest.raises(DataStaleError, match="does not exist"):
            create_connection(missing)

    def test_skips_missing_parquet_files(self, tmp_path):
        # Only write sources, not recipes
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)

        conn = create_connection(tmp_path)
        # sources should work
        result = conn.execute("SELECT count(*) FROM sources").fetchone()
        assert result[0] == 1

    def test_raises_on_schema_version_mismatch(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        # Write a fake stale schema hash
        import json

        (tmp_path / ".schema_version.json").write_text(
            json.dumps({"schema_hash": "stale_hash_value", "entity_count": 14}),
            encoding="utf-8",
        )
        with pytest.raises(DataStaleError, match="Schema version mismatch"):
            create_connection(tmp_path)

    def test_ignores_missing_sidecar(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        # No sidecar file — should still work
        conn = create_connection(tmp_path)
        assert conn is not None

    def test_returns_cached_connection(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        conn1 = create_connection(tmp_path)
        conn2 = create_connection(tmp_path)
        assert conn1 is conn2

    def test_invalidate_forces_new_connection(self, tmp_path):
        write_table("sources", [{"id": 1, "key": "fooby"}], tmp_path)
        conn1 = create_connection(tmp_path)
        invalidate_connection(tmp_path)
        conn2 = create_connection(tmp_path)
        assert conn1 is not conn2


class TestExecuteQuery:
    def test_executes_select(self, tmp_path):
        write_table(
            "recipes",
            [
                {"id": 1, "title": "Pasta", "language": "de"},
                {"id": 2, "title": "Risotto", "language": "de"},
            ],
            tmp_path,
        )

        results = execute_query("SELECT id, title FROM recipes ORDER BY id", tmp_path)
        assert len(results) == 2
        assert results[0] == {"id": 1, "title": "Pasta"}
        assert results[1] == {"id": 2, "title": "Risotto"}

    def test_applies_limit(self, tmp_path):
        write_table(
            "recipes",
            [{"id": i, "title": f"Recipe {i}"} for i in range(10)],
            tmp_path,
        )

        results = execute_query("SELECT * FROM recipes", tmp_path, limit=3)
        assert len(results) == 3

    def test_rejects_dangerous_sql(self, tmp_path):
        write_table("recipes", [{"id": 1}], tmp_path)
        with pytest.raises(QueryError, match="Forbidden"):
            execute_query("DROP TABLE recipes", tmp_path)

    def test_raises_on_bad_sql(self, tmp_path):
        write_table("recipes", [{"id": 1}], tmp_path)
        with pytest.raises(QueryError, match="execution failed"):
            execute_query("SELECT * FROM nonexistent_table", tmp_path)


class TestSearchRecipes:
    def _seed_recipes(self, tmp_path):
        write_table(
            "recipes",
            [
                {
                    "id": 1,
                    "title": "Pasta Carbonara",
                    "title_normalised": "pasta carbonara",
                    "language": "de",
                },
                {
                    "id": 2,
                    "title": "Risotto Milanese",
                    "title_normalised": "risotto milanese",
                    "language": "de",
                },
                {
                    "id": 3,
                    "title": "Poulet Rôti",
                    "title_normalised": "poulet roti",
                    "language": "fr",
                },
            ],
            tmp_path,
        )

    def test_search_by_text(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path, query="pasta")
        assert len(results) == 1
        assert results[0]["title"] == "Pasta Carbonara"

    def test_search_by_language(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path, language="fr")
        assert len(results) == 1
        assert results[0]["title"] == "Poulet Rôti"

    def test_search_combined(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path, query="risotto", language="de")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path, query="sushi")
        assert results == []

    def test_search_all(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path)
        assert len(results) == 3

    def test_search_respects_limit(self, tmp_path):
        self._seed_recipes(tmp_path)
        results = search_recipes(tmp_path, limit=2)
        assert len(results) == 2
