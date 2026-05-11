"""Base class for recipe source adapters.

Each source (Fooby, Migusto, etc.) implements this ABC to provide
recipe discovery and fetching.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class RawRecipe:
    """Raw recipe data as extracted from a source (typically via JSON-LD)."""

    title: str
    description: str = ""
    ingredients_raw: list[str] = field(default_factory=list)
    steps_raw: list[str] = field(default_factory=list)
    yield_amount: str = ""
    prep_time: str = ""
    cook_time: str = ""
    image_urls: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source_url: str = ""
    language: str = "de"


class SourceAdapter(ABC):
    """Abstract base class for recipe source adapters."""

    key: ClassVar[str]  # 'fooby', 'migusto', ...
    display_name: ClassVar[str]
    languages: ClassVar[tuple[str, ...]]

    @abstractmethod
    def discover(self) -> Iterable[str]:
        """Yield recipe URLs to scrape."""

    @abstractmethod
    def fetch(self, url: str) -> RawRecipe:
        """Fetch and parse one recipe page."""
