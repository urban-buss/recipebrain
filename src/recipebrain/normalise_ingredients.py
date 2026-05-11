"""Compatibility shim — re-exports from ``recipebrain.normalise.ingredients``."""

from __future__ import annotations

from recipebrain.normalise.ingredients import *  # noqa: F401,F403
from recipebrain.normalise.ingredients import normalise_ingredient

__all__ = ["normalise_ingredient"]
