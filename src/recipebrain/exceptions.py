"""Shared exception types for recipebrain."""

from __future__ import annotations


class QueryError(Exception):
    """Raised when a SQL query is invalid or fails to execute."""


class DataStaleError(Exception):
    """Raised when required Parquet datasets are missing."""


class RecipeNotFoundError(Exception):
    """Raised when a recipe cannot be found by ID or URL."""


class ProtectedSectionError(Exception):
    """Raised when attempting to modify a protected dossier section."""
