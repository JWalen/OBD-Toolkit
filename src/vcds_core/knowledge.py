"""Fault-code knowledge: descriptions, severity and likely causes.

Wraps the curated :mod:`vcds_core._dtc_data` table with a structural decoder so
that *any* code — even one not in the table — gets a sensible category and
subsystem. Used to enrich VCDS Auto-Scans and to give raw ELM327 DTCs (which
arrive as bare codes) human-readable meaning.

Standard-library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ._dtc_data import (
    BRAND_CODE_DB,
    CODE_CATEGORY,
    CODE_DB,
    KNOWN_ISSUES,
    P_SUBSYSTEM,
    SEVERITY_ORDER,
)

_CODE_RE = re.compile(r"^([PUBC])([0-9A-F]{4,5})$", re.IGNORECASE)


@dataclass
class CodeKnowledge:
    code: str
    description: str
    severity: str
    system: str
    causes: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    known: bool = False  # True if the code was found in the curated table

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 0)


def normalize_code(code: str) -> str:
    """Upper-case and strip the leading apostrophe / whitespace VCDS may add."""
    return (code or "").strip().lstrip("'").strip().upper()


def _structural(code: str) -> CodeKnowledge:
    """Best-effort meaning from the code's structure when it isn't in the table."""
    m = _CODE_RE.match(code)
    if not m:
        return CodeKnowledge(code=code, description="Unrecognized code format",
                             severity="info", system="Unknown")
    letter, digits = m.group(1).upper(), m.group(2)
    category = CODE_CATEGORY.get(letter, "Unknown")
    system = category
    if letter == "P" and len(digits) >= 2:
        system = P_SUBSYSTEM.get(digits[1], category)
    # Generic codes (P0/P2/U0…) are standardized; manufacturer codes (P1, P3xxx,
    # VAG 5-digit) are vendor-specific.
    generic = letter == "P" and digits[0] in ("0", "2")
    desc = f"{category}"
    if letter == "P":
        desc = f"{system}"
    return CodeKnowledge(
        code=code,
        description=desc + (" (generic)" if generic else " (manufacturer-specific)"),
        severity="medium" if letter in ("P", "U") else "low",
        system=system,
        causes=[],
        notes=None,
        known=False,
    )


def lookup(code: str, brand: Optional[str] = None) -> CodeKnowledge:
    """Return knowledge for a DTC, falling back to structural decoding.

    Args:
        code: A DTC such as ``"P0299"`` (apostrophes/whitespace tolerated).
        brand: Optional vehicle profile id (e.g. ``"ford"``) to consult its
            manufacturer-specific (P1xxx) code pack for codes not in the shared
            generic table.
    """
    norm = normalize_code(code)
    entry = CODE_DB.get(norm)
    if entry is None and brand:
        entry = BRAND_CODE_DB.get(brand, {}).get(norm)
    if entry is None:
        return _structural(norm)
    return CodeKnowledge(
        code=norm,
        description=entry["description"],
        severity=entry.get("severity", "medium"),
        system=entry.get("system", "Unknown"),
        causes=list(entry.get("causes", [])),
        notes=entry.get("notes"),
        known=True,
    )


def known_issue(topic: str) -> Optional[str]:
    """Return a VAG known-issue note by topic key, if present."""
    return KNOWN_ISSUES.get(topic)


def describe(code: str) -> str:
    """One-line ``CODE — description`` for quick display."""
    k = lookup(code)
    return f"{k.code} — {k.description}"
