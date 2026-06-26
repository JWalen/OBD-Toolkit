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
    "3MZ": "Mazda", "3MV": "Mazda", "JMZ": "Mazda",
    # GM
    "1G1": "Chevrolet", "1GC": "Chevrolet", "1GB": "Chevrolet", "2G1": "Chevrolet",
    "3G1": "Chevrolet", "KL1": "Chevrolet", "1GN": "Chevrolet", "1GT": "GMC", "1GK": "GMC",
    "1GD": "GMC", "1G4": "Buick", "1G6": "Cadillac", "1GY": "Cadillac", "1G2": "Pontiac",
    "1G8": "Saturn",
    # Toyota / Lexus / Scion
    "JTD": "Toyota", "JTE": "Toyota", "JTM": "Toyota", "JTN": "Toyota", "4T1": "Toyota",
    "4T3": "Toyota", "5TD": "Toyota", "5TF": "Toyota", "5TB": "Toyota", "2T1": "Toyota",
    "JTH": "Lexus", "58A": "Lexus", "JTK": "Scion",
    # Honda / Acura
    "JHM": "Honda", "1HG": "Honda", "2HG": "Honda", "19X": "Honda", "5FN": "Honda",
    "5J6": "Honda", "2HK": "Honda", "5KB": "Honda", "JH4": "Acura", "19U": "Acura", "5J8": "Acura",
    # Nissan / Infiniti
    "JN1": "Nissan", "JN6": "Nissan", "JN8": "Nissan", "1N4": "Nissan", "1N6": "Nissan",
    "3N1": "Nissan", "5N1": "Nissan", "JNK": "Infiniti", "JNR": "Infiniti", "5N3": "Infiniti",
    # Subaru
    "JF1": "Subaru", "JF2": "Subaru", "4S3": "Subaru", "4S4": "Subaru",
    # Hyundai / Kia / Genesis
    "KMH": "Hyundai", "KM8": "Hyundai", "5NP": "Hyundai", "5NM": "Hyundai", "3KP": "Hyundai",
    "KNA": "Kia", "KND": "Kia", "5XY": "Kia", "KNM": "Kia",
    # Chrysler / Dodge / Jeep / Ram (Mopar)
    "1C3": "Chrysler", "2C3": "Chrysler", "3C3": "Chrysler", "1C4": "Jeep", "1C6": "Ram",
    "3C6": "Ram", "1B3": "Dodge", "2B3": "Dodge", "1D7": "Dodge", "1J4": "Jeep", "1J8": "Jeep",
    # BMW / Mini
    "WBA": "BMW", "WBS": "BMW", "WBY": "BMW", "5UX": "BMW", "4US": "BMW", "WMW": "Mini",
    # Mercedes-Benz
    "WDB": "Mercedes-Benz", "WDD": "Mercedes-Benz", "WDC": "Mercedes-Benz", "WDF": "Mercedes-Benz",
    "4JG": "Mercedes-Benz", "55S": "Mercedes-Benz",
}

# make -> brand profile id
_MAKE_PROFILE = {
    "Audi": "vag", "Volkswagen": "vag", "SEAT": "vag", "Škoda": "vag",
    "Ford": "ford", "Lincoln": "ford",
    "Mazda": "mazda",
    "Chevrolet": "gm", "GMC": "gm", "Buick": "gm", "Cadillac": "gm", "Pontiac": "gm",
    "Saturn": "gm", "Oldsmobile": "gm", "Hummer": "gm",
    "Toyota": "toyota", "Lexus": "toyota", "Scion": "toyota",
    "Honda": "honda", "Acura": "honda",
    "Nissan": "nissan", "Infiniti": "nissan",
    "Subaru": "subaru",
    "Hyundai": "hyundai", "Kia": "hyundai", "Genesis": "hyundai",
    "Chrysler": "mopar", "Dodge": "mopar", "Jeep": "mopar", "Ram": "mopar", "Plymouth": "mopar",
    "BMW": "bmw", "Mini": "bmw",
    "Mercedes-Benz": "mercedes",
}


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
    return _MAKE_PROFILE.get(make, "generic")


def decode_vin(vin: str) -> VinInfo:
    """Decode a VIN into make / model-year / brand profile (best effort)."""
    v = (vin or "").strip().upper()
    wmi = v[:3]
    make = _WMI_MAKE.get(wmi) or _WMI_MAKE.get(v[:2] + v[2:3])
    year = model_year(v[9]) if len(v) >= 10 else None
    return VinInfo(vin=v, wmi=wmi, make=make, year=year, brand_profile=brand_profile(make))
