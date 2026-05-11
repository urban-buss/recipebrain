"""Base class for promotion source adapters.

Each promotion source (Profital, per-retailer, etc.) implements this ABC
to provide current promotion data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import ClassVar


@dataclass
class RawPromotion:
    """Raw promotion data as extracted from a source."""

    retailer: str
    product_name: str
    original_price: float | None = None
    discounted_price: float | None = None
    discount_pct: float | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    category: str = ""
    source_url: str = ""
    image_url: str = ""


class PromotionAdapter(ABC):
    """Abstract base class for promotion source adapters."""

    key: ClassVar[str]  # 'profital', 'migros', ...
    display_name: ClassVar[str]

    @abstractmethod
    def fetch_current(self) -> Iterable[RawPromotion]:
        """Fetch current promotions from this source."""
