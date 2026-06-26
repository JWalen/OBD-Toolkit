"""Tests for brand profiles and brand-aware diagnosis."""

from __future__ import annotations

from vcds_core import parse, profiles
from vcds_core.diagnose import diagnose


def test_profiles_registry():
    expected = {"generic", "vag", "ford", "gm", "toyota", "honda", "nissan",
                "mazda", "subaru", "hyundai", "mopar", "bmw", "mercedes"}
    assert set(profiles.PROFILES) == expected
    assert profiles.get_profile("ford").id == "ford"
    assert profiles.get_profile("nonsense").id == profiles.DEFAULT_PROFILE
    # every profile has a non-empty persona, label and id
    for pid, prof in profiles.PROFILES.items():
        assert prof.id == pid and prof.label and prof.ai_persona
    assert "VAG" in profiles.get_profile("vag").ai_persona
    assert "Toyota" in profiles.get_profile("toyota").ai_persona


def test_brand_code_packs():
    from vcds_core import knowledge

    cases = {"gm": "P1336", "toyota": "P1349", "honda": "P1259", "nissan": "P17F0",
             "mazda": "P2096", "subaru": "P0011", "hyundai": "P1326", "mopar": "P0521"}
    for brand, code in cases.items():
        k = knowledge.lookup(code, brand=brand)
        assert k.known and k.description and k.causes, f"{brand}:{code}"
    # the Hyundai KSDS rod-bearing code is flagged high severity
    assert knowledge.lookup("P1326", brand="hyundai").severity == "high"


def test_vag_notes_only_for_vag_profile(samples_dir):
    scan = parse.parse_autoscan(samples_dir["autoscan"])
    vag = diagnose(scan=scan, profile="vag")
    generic = diagnose(scan=scan, profile="generic")
    # same number of findings, but the VAG-flavored per-code notes are dropped
    vag_text = " ".join(f.detail for f in vag.findings)
    gen_text = " ".join(f.detail for f in generic.findings)
    # The misfire code (P0301) carries a VAG-flavored note shown only for VAG.
    assert "Swap the coil" in vag_text
    assert "Swap the coil" not in gen_text
    assert len(vag.findings) == len(generic.findings)  # same findings, fewer notes


def test_ford_brand_code_pack():
    from vcds_core import knowledge

    # generic lookup doesn't know a Ford-specific P1xxx code
    assert not knowledge.lookup("P1131").known
    # but the Ford brand pack does
    k = knowledge.lookup("P1131", brand="ford")
    assert k.known and "Lean" in k.description
    assert k.causes


def test_data_known_issue_is_brand_specific(tmp_path):
    # a lean trim triggers a PCV note for VAG/Ford but not generic
    path = tmp_path / "lean.csv"
    path.write_text(
        "TIME,Long Fuel Trim 1\ns,%\n0,5\n1,18\n2,22\n3,20\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    vag = diagnose(log=log, profile="vag")
    ford = diagnose(log=log, profile="ford")
    generic = diagnose(log=log, profile="generic")
    lean_v = next(f for f in vag.findings if f.title == "Lean fuel trims")
    lean_f = next(f for f in ford.findings if f.title == "Lean fuel trims")
    lean_g = next(f for f in generic.findings if f.title == "Lean fuel trims")
    assert "PCV" in lean_v.detail
    assert "PCV" in lean_f.detail
    assert "PCV" not in lean_g.detail  # generic gets no brand note
