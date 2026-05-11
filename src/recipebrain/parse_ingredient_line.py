"""Compatibility shim — re-exports from ``recipebrain.parse.ingredient_line``."""

from __future__ import annotations

from recipebrain.parse.ingredient_line import *  # noqa: F401,F403
from recipebrain.parse.ingredient_line import parse_ingredient_line

__all__ = ["parse_ingredient_line"]
