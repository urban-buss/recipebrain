"""Query layer: SQL validation and execution against DuckDB/Parquet.

Provides safe, read-only SQL access to the Parquet datasets via DuckDB.
Validates queries to reject DML/DDL, registers Parquet files as views,
and returns results as lists of dicts.

Security: validate_sql rejects INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import duckdb

from recipebrain.exceptions import DataStaleError, QueryError
from recipebrain.writer import SCHEMAS, compute_schema_hash, read_schema_version

__all__ = [
    "DataStaleError",
    "QueryEngine",
    "QueryError",
    "create_connection",
    "execute_query",
    "invalidate_connection",
    "validate_sql",
]


_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE"
    r"|COPY|ATTACH|DETACH|PRAGMA|LOAD|INSTALL)\b",
    re.IGNORECASE,
)

# Block direct file-access functions that bypass view-only exposure
_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(read_parquet|read_csv|read_csv_auto|read_json|read_json_auto"
    r"|parquet_scan|parquet_metadata|parquet_schema)\s*\(",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Connection cache — one connection per output_dir, thread-safe
# ---------------------------------------------------------------------------

_conn_cache: dict[Path, duckdb.DuckDBPyConnection] = {}
_conn_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Virtual computed_tags column — aggregates classification scalars + list
# fields into a single searchable bag, computed at query time rather than
# persisted on disk (resolves issue #043).
# ---------------------------------------------------------------------------

_COMPUTED_TAGS_EXPR = """\
list_sort(list_distinct(list_filter(
  list_concat(
    list_concat(
      [primary_protein, taste_profile, weight_class, cooking_method, course, cuisine, difficulty],
      coalesce(dietary_flags, []::VARCHAR[])
    ),
    coalesce(food_groups, []::VARCHAR[])
  ),
  x -> x IS NOT NULL AND x != ''
))) AS computed_tags"""


def invalidate_connection(output_dir: Path | None = None) -> None:
    """Invalidate the cached connection for *output_dir*, or all if None."""
    with _conn_lock:
        if output_dir is None:
            for conn in _conn_cache.values():
                try:
                    conn.close()
                except Exception:
                    pass
            _conn_cache.clear()
        else:
            resolved = output_dir.resolve()
            removed = _conn_cache.pop(resolved, None)
            if removed is not None:
                try:
                    removed.close()
                except Exception:
                    pass


def validate_sql(sql: str) -> str:
    """Validate that a SQL string is read-only. Returns the SQL if valid.

    Rejects any statement containing DML/DDL keywords.

    Args:
        sql: The SQL query to validate.

    Returns:
        The validated SQL string (stripped).

    Raises:
        QueryError: If the SQL contains forbidden keywords.
    """
    stripped = sql.strip()
    if not stripped:
        raise QueryError("Empty SQL query")

    # Remove comments before checking
    no_comments = re.sub(r"--[^\n]*", "", stripped)
    no_comments = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)

    match = _FORBIDDEN_KEYWORDS.search(no_comments)
    if match:
        raise QueryError(f"Forbidden SQL keyword: {match.group(1).upper()}")

    func_match = _FORBIDDEN_FUNCTIONS.search(no_comments)
    if func_match:
        raise QueryError(f"Forbidden SQL function: {func_match.group(1)}")

    return stripped


def create_connection(output_dir: Path) -> duckdb.DuckDBPyConnection:
    """Return a (possibly cached) DuckDB connection with Parquet views.

    Registers each known entity's parquet file as a view if the file exists.
    Connections are cached per resolved *output_dir* and reused on subsequent
    calls. Call ``invalidate_connection()`` after writes to force re-creation.

    Args:
        output_dir: Path to the directory containing parquet files.

    Returns:
        A DuckDB connection with views registered.

    Raises:
        DataStaleError: If the output directory does not exist.
    """
    if not output_dir.exists():
        raise DataStaleError(f"Output directory does not exist: {output_dir}")

    resolved = output_dir.resolve()

    with _conn_lock:
        cached = _conn_cache.get(resolved)
        if cached is not None:
            return cached

    # Check schema version sidecar if present
    stored_hash = read_schema_version(output_dir)
    if stored_hash is not None and stored_hash != compute_schema_hash():
        raise DataStaleError(
            "Schema version mismatch — data was written with a different schema. "
            "Run 'recipebrain etl' to rebuild or 'recipebrain snapshot restore' to revert."
        )

    conn = duckdb.connect(":memory:")

    for entity in SCHEMAS:
        parquet_path = output_dir / f"{entity}.parquet"
        if parquet_path.exists():
            # Use forward slashes for DuckDB path compatibility
            path_str = str(parquet_path).replace("\\", "/")
            if entity == "recipes":
                # Add virtual computed_tags column (issue #043)
                conn.execute(
                    f"CREATE VIEW {entity} AS SELECT *, {_COMPUTED_TAGS_EXPR} "
                    f"FROM read_parquet('{path_str}')"
                )
            else:
                conn.execute(f"CREATE VIEW {entity} AS SELECT * FROM read_parquet('{path_str}')")

    with _conn_lock:
        # Another thread may have populated the cache; close ours if so
        if resolved in _conn_cache:
            conn.close()
            return _conn_cache[resolved]
        _conn_cache[resolved] = conn

    return conn


def execute_query(
    sql: str,
    output_dir: Path,
    *,
    limit: int | None = None,
    params: list | None = None,
) -> list[dict]:
    """Validate and execute a read-only SQL query against the Parquet data.

    Args:
        sql: SQL query (must pass validate_sql).
        output_dir: Path to parquet datasets.
        limit: Optional row limit appended to query.
        params: Optional list of bind parameters for ``?`` placeholders.

    Returns:
        List of dicts, one per result row.

    Raises:
        QueryError: If SQL is invalid or execution fails.
        DataStaleError: If output directory is missing.
    """
    validated = validate_sql(sql)

    if limit is not None and "LIMIT" not in validated.upper():
        validated = f"{validated.rstrip(';')} LIMIT {limit}"

    conn = create_connection(output_dir)
    try:
        result = conn.execute(validated, params or [])
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]
    except duckdb.Error as exc:
        raise QueryError(f"Query execution failed: {exc}") from exc


def search_recipes(
    output_dir: Path,
    *,
    query: str | None = None,
    language: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search recipes by text and/or language.

    Args:
        output_dir: Path to parquet datasets.
        query: Optional search text (matched against title_normalised).
        language: Optional language filter.
        limit: Max results (default 20).

    Returns:
        List of recipe dicts.
    """
    conditions: list[str] = []
    params: list[object] = []
    if query:
        conditions.append("title_normalised LIKE ?")
        params.append(f"%{query.lower()}%")
    if language:
        conditions.append("language = ?")
        params.append(language)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM recipes{where} ORDER BY title LIMIT {limit}"

    conn = create_connection(output_dir)
    try:
        result = conn.execute(sql, params)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]
    except duckdb.Error as exc:
        raise QueryError(f"Search failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Class-based API
# ---------------------------------------------------------------------------


class QueryEngine:
    """Convenience wrapper around the functional query API.

    Binds an *output_dir* once so callers don't have to pass it repeatedly.

    Examples:
        >>> engine = QueryEngine(Path("output"))
        >>> engine.execute("SELECT * FROM recipes LIMIT 5")
        [{'id': 1, ...}, ...]
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = Path(output_dir)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def execute(
        self,
        sql: str,
        *,
        limit: int | None = None,
        params: list | None = None,
    ) -> list[dict]:
        """Validate and execute a read-only SQL query.

        Delegates to :func:`execute_query`.
        """
        return execute_query(sql, self._output_dir, limit=limit, params=params)

    def search(
        self,
        *,
        query: str | None = None,
        language: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search recipes by text and/or language.

        Delegates to :func:`search_recipes`.
        """
        return search_recipes(self._output_dir, query=query, language=language, limit=limit)

    def invalidate(self) -> None:
        """Invalidate the cached connection for this output directory."""
        invalidate_connection(self._output_dir)
