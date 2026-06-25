"""Unit conversion for display (metric ⇄ imperial).

Pure functions over (value, unit_label). ``system`` is ``"as_logged"`` (no
change), ``"metric"`` or ``"imperial"``. Unknown units pass through unchanged,
so a value is never corrupted — at worst it stays in its original unit.

Standard-library only.
"""

from __future__ import annotations

from typing import Optional, Tuple

AS_LOGGED = "as_logged"
METRIC = "metric"
IMPERIAL = "imperial"


def _norm(unit: str) -> str:
    return (unit or "").strip().lower().replace("°", "").replace(" ", "")


# Imperial conversions: source-unit -> (factor, offset, label). value*factor+offset.
_TO_IMPERIAL = {
    "c": (9 / 5, 32.0, "°F"), "degc": (9 / 5, 32.0, "°F"),
    "km/h": (0.621371, 0.0, "mph"), "kph": (0.621371, 0.0, "mph"),
    "km": (0.621371, 0.0, "mi"),
    "kpa": (0.145038, 0.0, "psi"),
    "mbar": (0.0145038, 0.0, "psi"), "hpa": (0.0145038, 0.0, "psi"),
    "bar": (14.5038, 0.0, "psi"),
    "l": (0.264172, 0.0, "gal"), "l/h": (0.264172, 0.0, "gal/h"),
    "nm": (0.737562, 0.0, "lb-ft"), "n·m": (0.737562, 0.0, "lb-ft"),
    "m": (3.28084, 0.0, "ft"),
}

# Metric conversions (for imperial-sourced logs).
_TO_METRIC = {
    "f": (5 / 9, -32.0 * 5 / 9, "°C"), "degf": (5 / 9, -32.0 * 5 / 9, "°C"),
    "mph": (1 / 0.621371, 0.0, "km/h"),
    "mi": (1 / 0.621371, 0.0, "km"), "mile": (1 / 0.621371, 0.0, "km"),
    "miles": (1 / 0.621371, 0.0, "km"),
    "psi": (6.89476, 0.0, "kPa"),
    "gal": (3.78541, 0.0, "L"), "gal/h": (3.78541, 0.0, "L/h"),
    "lb-ft": (1 / 0.737562, 0.0, "N·m"), "ftlb": (1 / 0.737562, 0.0, "N·m"),
    "ft": (0.3048, 0.0, "m"),
}


def convert(value: Optional[float], unit: str, system: str) -> Tuple[Optional[float], str]:
    """Convert ``value``/``unit`` to ``system``; unknown units pass through."""
    if value is None or system in (None, "", AS_LOGGED):
        return value, unit
    table = _TO_IMPERIAL if system == IMPERIAL else _TO_METRIC
    spec = table.get(_norm(unit))
    if spec is None:
        return value, unit
    factor, offset, label = spec
    return value * factor + offset, label


def convert_label(unit: str, system: str) -> str:
    """Return the unit label after conversion (without a value)."""
    _, label = convert(0.0, unit, system)
    return label
