"""Lightweight VIN decoding (make, model year, brand profile).

Enough to identify the manufacturer and year and pick a vehicle profile — not a
full VIN database. Standard-library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# 30-year cycle of model-year codes (I, O, Q, U, Z and 0 are not used).
_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"

# World Manufacturer Identifier (first 3 chars) -> make.
_WMI_MAKE = {
    "WAU": "Audi", "WA1": "Audi", "WUA": "Audi", "TRU": "Audi", "93U": "Audi",
    "WVW": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen",
    "1VW": "Volkswagen", "3VW": "Volkswagen", "9BW": "Volkswagen", "AAV": "Volkswagen",
    "VSS": "SEAT", "TMB": "Škoda",
    "1FA": "Ford", "1FB": "Ford", "1FC": "Ford", "1FD": "Ford", "1FM": "Ford",
    "1FT": "Ford", "2FM": "Ford", "2FT": "Ford", "3FA": "Ford", "WF0": "Ford",
    "MAJ": "Ford", "1FU": "Ford", "1FV": "Ford",
    "1LN": "Lincoln", "5LM": "Lincoln",
    "JM1": "Mazda", "JM3": "Mazda", "1YV": "Mazda", "4F2": "Mazda", "4F4": "Mazda",
}

_VAG_MAKES = {"Audi", "Volkswagen", "SEAT", "Škoda"}
_FORD_MAKES = {"Ford", "Lincoln", "Mazda"}


@dataclass
class VinInfo:
    vin: str
    wmi: str
    make: Optional[str]
    year: Optional[int]
    brand_profile: str


def model_year(code: str) -> Optional[int]:
    """Decode the 10th-character model-year code (assumes 2010–2039 cycle)."""
    code = (code or "").upper()
    if code not in _YEAR_CODES:
        return None
    return 2010 + _YEAR_CODES.index(code)


def brand_profile(make: Optional[str]) -> str:
    if make in _VAG_MAKES:
        return "vag"
    if make in _FORD_MAKES:
        return "ford"
    return "generic"


def decode_vin(vin: str) -> VinInfo:
    """Decode a VIN into make / model-year / brand profile (best effort)."""
    v = (vin or "").strip().upper()
    wmi = v[:3]
    make = _WMI_MAKE.get(wmi) or _WMI_MAKE.get(v[:2] + v[2:3])
    year = model_year(v[9]) if len(v) >= 10 else None
    return VinInfo(vin=v, wmi=wmi, make=make, year=year, brand_profile=brand_profile(make))
