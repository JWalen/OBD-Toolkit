"""Vehicle/brand profiles.

A profile selects the brand-specific knowledge the diagnostic engine and AI
assistant use (known-issue notes, the AI persona, and whether the bundled
per-code notes — which are VAG-flavored — should be shown). The standard OBD-II
fault codes and the data-driven heuristics are universal and shared by all
profiles.

Standard-library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from ._dtc_data import KNOWN_ISSUES as _VAG_ISSUES

_GENERIC_PERSONA = (
    "You are an expert automotive diagnostic assistant for OBD-II vehicles of any "
    "make. Help the user diagnose their car from the data below. Be specific and "
    "practical: name the most likely causes, the checks to confirm them, and "
    "typical fixes, ordered by likelihood. If the data is insufficient, say what to "
    "log next. Keep safety in mind."
)
_VAG_PERSONA = (
    "You are an expert VAG/Audi (VW / Audi / SEAT / Škoda) diagnostic assistant. "
    "Use VAG-specific knowledge where relevant (PCV/crankcase breather, carbon "
    "build-up on direct-injection intake valves, diverter valves, HPFP cam "
    "follower, timing-chain tensioners). " + _GENERIC_PERSONA
)
_FORD_PERSONA = (
    "You are an expert Ford / Lincoln / Mazda diagnostic assistant. Use "
    "Ford-specific knowledge where relevant (EcoBoost intercooler condensation, "
    "1.5/1.6 EcoBoost coolant intrusion, PCV faults, electronic throttle-body "
    "limp mode). " + _GENERIC_PERSONA
)

_FORD_ISSUES: Dict[str, str] = {
    "pcv_failure": "A failed PCV/crankcase ventilation can cause lean codes "
                   "(P0171/P0174), rough idle and a vacuum-leak whistle.",
    "ecoboost_condensation": "EcoBoost intercoolers collect condensation that can "
                             "cause a stumble or misfire under boost in humid/cold conditions.",
    "coolant_intrusion": "Some 1.5/1.6 EcoBoost engines suffer coolant intrusion into a "
                         "cylinder — investigate coolant loss combined with misfires.",
    "throttle_body": "Ford electronic throttle bodies can trip limp mode "
                     "(e.g. P2111) — cleaning or replacement is often required.",
}


@dataclass
class Profile:
    id: str
    label: str
    ai_persona: str
    known_issues: Dict[str, str] = field(default_factory=dict)
    # Whether to show the bundled per-code notes (which are written for VAG).
    code_notes: bool = False


PROFILES: Dict[str, Profile] = {
    "generic": Profile("generic", "Generic OBD-II", _GENERIC_PERSONA, {}, code_notes=False),
    "vag": Profile("vag", "VAG (VW / Audi / SEAT / Škoda)", _VAG_PERSONA,
                   dict(_VAG_ISSUES), code_notes=True),
    "ford": Profile("ford", "Ford / Lincoln / Mazda", _FORD_PERSONA, _FORD_ISSUES, code_notes=False),
}

DEFAULT_PROFILE = "vag"


def get_profile(profile) -> Profile:
    """Resolve a profile id (or Profile) to a Profile, falling back to default."""
    if isinstance(profile, Profile):
        return profile
    return PROFILES.get(profile or DEFAULT_PROFILE, PROFILES[DEFAULT_PROFILE])
