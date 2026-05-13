"""Ingredient line parser for Swiss recipe text.

Parses lines like "200 g Pouletbrust, in Würfeln" into structured
components: quantity, unit, ingredient name, and preparation note.

Handles Swiss-German conventions: fractional quantities (½, ¼),
common units (g, kg, ml, dl, l, EL, TL, Prise, Bund, Stück),
and comma-separated prep notes.

Examples:
    >>> parse_ingredient_line("200 g Pouletbrust, in Würfeln")
    ParsedIngredient(quantity=200.0, unit='g', ingredient='Pouletbrust', prep_note='in Würfeln')

    >>> parse_ingredient_line("Salz und Pfeffer")
    ParsedIngredient(quantity=None, unit=None, ingredient='Salz und Pfeffer', prep_note=None)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedIngredient:
    """Structured representation of a parsed ingredient line."""

    quantity: float | None
    unit: str | None
    ingredient: str
    prep_note: str | None
    optional: bool = False


# Optional ingredient markers common in Swiss-German and French recipe text
_OPTIONAL_MARKERS = re.compile(
    r"(?:^|\b)"
    r"(?:optional|nach Belieben|evt(?:l)?\.?|evtl\.?|fakultativ|facultatif|selon go[uû]t)"
    r"(?:\b|(?=[\s:,;.])|$)",
    re.IGNORECASE,
)

# Unicode fraction map
_FRACTIONS: dict[str, float] = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}

# Known units (case-insensitive matching, stored normalised)
_UNITS: dict[str, str] = {
    # Metric
    "g": "g",
    "kg": "kg",
    "ml": "ml",
    "cl": "cl",
    "dl": "dl",
    "l": "l",
    # German
    "el": "EL",
    "tl": "TL",
    "msp": "Msp",
    "prise": "Prise",
    "prisen": "Prise",
    "bund": "Bund",
    "stück": "Stück",
    "stk": "Stück",
    "scheibe": "Scheibe",
    "scheiben": "Scheibe",
    "blatt": "Blatt",
    "blätter": "Blatt",
    "zweig": "Zweig",
    "zweige": "Zweig",
    "zehe": "Zehe",
    "zehen": "Zehe",
    "dose": "Dose",
    "dosen": "Dose",
    "becher": "Becher",
    "packung": "Packung",
    "pkg": "Packung",
    "tropfen": "Tropfen",
    "tasse": "Tasse",
    "tassen": "Tasse",
    # French
    "pincée": "Prise",
    "pincee": "Prise",
    "branche": "Zweig",
    "branches": "Zweig",
    "brin": "Zweig",
    "brins": "Zweig",
    "tranche": "Scheibe",
    "tranches": "Scheibe",
    "gousse": "Zehe",
    "gousses": "Zehe",
    "botte": "Bund",
    "bottes": "Bund",
    "bouquet": "Bund",
    "sachet": "Packung",
    "sachets": "Packung",
    "paquet": "Packung",
    "paquets": "Packung",
}

# Pattern: optional quantity (number or fraction), optional unit, rest is ingredient
_QUANTITY_RE = re.compile(
    r"^"
    r"(?P<whole>\d+(?:[.,]\d+)?)?"  # whole number or decimal
    r"(?:\s*(?P<frac>[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]))?"  # unicode fraction
    r"(?:\s*[-–/]\s*(?P<range_end>\d+(?:[.,]\d+)?))?"  # optional range (e.g. 2-3)
    r"\s*"
    r"(?P<rest>.+)"
    r"$",
    re.UNICODE,
)

# Multi-token French unit abbreviations (tried before single-word lookup)
_MULTI_TOKEN_UNITS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"c\.\s*à\s*s\.?", re.IGNORECASE), "EL"),
    (re.compile(r"c\.\s*à\s*c\.?", re.IGNORECASE), "TL"),
    (re.compile(r"c\.s\.?", re.IGNORECASE), "EL"),
    (re.compile(r"c\.c\.?", re.IGNORECASE), "TL"),
    (re.compile(r"cs\.?", re.IGNORECASE), "EL"),
    (re.compile(r"cc\.?", re.IGNORECASE), "TL"),
]

# French preposition between unit and ingredient (e.g. "de", "d'", "du")
_FRENCH_PREP_RE = re.compile(r"^(?:de\s+|d['']\s*|du\s+)", re.IGNORECASE)


def parse_ingredient_line(line: str) -> ParsedIngredient:
    """Parse a raw ingredient line into structured components.

    Args:
        line: Raw ingredient text, e.g. "200 g Pouletbrust, in Würfeln".

    Returns:
        ParsedIngredient with extracted quantity, unit, ingredient, prep_note.

    Raises:
        ValueError: If line is empty or whitespace-only.
    """
    line = line.strip()
    if not line:
        raise ValueError("Ingredient line is empty")

    # Detect and strip optional markers before parsing
    optional = bool(_OPTIONAL_MARKERS.search(line))
    if optional:
        line = _OPTIONAL_MARKERS.sub("", line).strip()
        # Clean up leftover colon/comma after marker removal
        line = re.sub(r"^[:,]\s*", "", line)
        line = re.sub(r"\s*[:,]\s*$", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip()

    if not line:
        raise ValueError("Ingredient line is empty")

    match = _QUANTITY_RE.match(line)
    if not match:
        return ParsedIngredient(
            quantity=None,
            unit=None,
            ingredient=line,
            prep_note=None,
            optional=optional,
        )

    whole = match.group("whole")
    frac = match.group("frac")
    rest = match.group("rest").strip()

    # Parse quantity
    quantity = _parse_quantity(whole, frac)

    # Try to extract unit from rest
    unit, remainder = _extract_unit(rest)

    # Split ingredient from prep note
    ingredient, prep_note = _split_prep_note(remainder)

    return ParsedIngredient(
        quantity=quantity,
        unit=unit,
        ingredient=ingredient.strip(),
        prep_note=prep_note.strip() if prep_note else None,
        optional=optional,
    )


def _parse_quantity(whole: str | None, frac: str | None) -> float | None:
    """Combine whole number and fraction into a float."""
    if whole is None and frac is None:
        return None

    value = 0.0
    if whole:
        value = float(whole.replace(",", "."))
    if frac:
        value += _FRACTIONS.get(frac, 0.0)

    return value if value > 0 else None


def _extract_unit(text: str) -> tuple[str | None, str]:
    """Try to extract a known unit from the beginning of text.

    Handles single-word units, dot-separated French abbreviations (c.s., c.c.),
    and multi-word French abbreviations (c. à s., c. à c.).

    Returns:
        (normalised_unit, remaining_text) or (None, original_text).
    """
    # Try multi-token patterns first (French dot-separated abbreviations)
    for pattern, canonical in _MULTI_TOKEN_UNITS:
        m = pattern.match(text)
        if m:
            remainder = text[m.end() :].strip()
            remainder = _FRENCH_PREP_RE.sub("", remainder).strip()
            return canonical, remainder

    # Try first word as unit
    parts = text.split(None, 1)
    if not parts:
        return None, text

    candidate = parts[0].rstrip(".")  # handle "EL." abbreviation
    normalised = _UNITS.get(candidate.lower())

    if normalised:
        remainder = parts[1] if len(parts) > 1 else ""
        remainder = _FRENCH_PREP_RE.sub("", remainder).strip()
        return normalised, remainder

    return None, text


def _split_prep_note(text: str) -> tuple[str, str | None]:
    """Split ingredient name from preparation note.

    Prep notes are typically after a comma or in parentheses.

    Examples:
        "Pouletbrust, in Würfeln" → ("Pouletbrust", "in Würfeln")
        "Zitrone (Saft davon)" → ("Zitrone", "Saft davon")
        "Mehl" → ("Mehl", None)
    """
    # Check for parenthetical note
    paren_match = re.match(r"^(.+?)\s*\((.+)\)\s*$", text)
    if paren_match:
        return paren_match.group(1).strip(), paren_match.group(2).strip()

    # Check for comma-separated note
    if "," in text:
        parts = text.split(",", 1)
        return parts[0].strip(), parts[1].strip()

    return text, None
