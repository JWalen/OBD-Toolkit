"""Tests for the knowledge base, computed channels and diagnostic engine."""

from __future__ import annotations

from vcds_core import compute, diagnose, knowledge, parse


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #


def test_known_code_lookup():
    k = knowledge.lookup("P0299")
    assert k.known
    assert "Underboost" in k.description
    assert k.severity == "high"
    assert any("leak" in c.lower() or "valve" in c.lower() for c in k.causes)


def test_apostrophe_and_case_tolerant():
    assert knowledge.lookup("'p0299").code == "P0299"


def test_unknown_code_structural_decode():
    k = knowledge.lookup("P0420")  # known, but check structural for an unknown one
    assert knowledge.lookup("P3XYZ") is not None
    u = knowledge.lookup("U0155")  # not in table -> structural
    assert not u.known
    assert "Network" in u.system or "communication" in u.system.lower()


def test_misfire_codes_generated():
    for c in range(1, 7):
        k = knowledge.lookup(f"P030{c}")
        assert k.known and f"Cylinder {c}" in k.description


# --------------------------------------------------------------------------- #
# Computed channels
# --------------------------------------------------------------------------- #


def _trim_log(tmp_path):
    path = tmp_path / "trims.csv"
    path.write_text(
        "TIME,Engine RPM,Short Fuel Trim 1,Long Fuel Trim 1\n"
        "s,/min,%,%\n"
        "0,800,2,12\n1,820,3,14\n2,810,2,16\n3,800,1,15\n",
        encoding="utf-8",
    )
    return parse.parse_measuring_log(str(path))


def test_add_computed_fuel_trim_total_and_afr(tmp_path):
    log = _trim_log(tmp_path)
    added = compute.add_computed_channels(log)
    assert "Fuel Trim Total" in added
    assert "AFR (estimated)" in added
    total = log.channel("Fuel Trim Total")
    # first sample: 2 + 12 = 14
    assert abs(total.first - 14) < 1e-6
    afr = log.channel("AFR (estimated)")
    # 14.7 / (1 + 14/100) ~= 12.9
    assert 12.0 < afr.first < 13.5


def test_safe_expression_rejects_code():
    import pytest

    with pytest.raises(ValueError):
        compute.evaluate_expression("__import__('os').system('x')", {})
    assert compute.evaluate_expression("a*2 + 1", {"a": 3}) == 7


# --------------------------------------------------------------------------- #
# Diagnostic engine
# --------------------------------------------------------------------------- #


def test_diagnose_from_scan(samples_dir):
    scan = parse.parse_autoscan(samples_dir["autoscan"])
    report = diagnose(scan=scan)
    assert report.vin == "WAUZZZ8K9BA123456"
    assert report.findings
    # known fault codes become findings with causes
    assert any(f.category == "fault" and f.causes for f in report.findings)
    # sorted most-severe first
    ranks = [f.severity_rank for f in report.findings]
    assert ranks == sorted(ranks, reverse=True)


def test_diagnose_data_symptoms(tmp_path):
    # a log with a lean trim and a boost shortfall + overheat
    path = tmp_path / "sick.csv"
    path.write_text(
        "TIME,Long Fuel Trim 1,Coolant Temp,Boost (specified),Boost (actual)\n"
        "s,%,°C,mbar,mbar\n"
        "0,5,90,1500,1480\n"
        "1,18,108,1600,1000\n"
        "2,24,118,1700,1100\n"
        "3,22,116,1700,1120\n",
        encoding="utf-8",
    )
    log = parse.parse_measuring_log(str(path))
    report = diagnose(log=log)
    titles = " | ".join(f.title for f in report.findings)
    assert "Lean fuel trims" in titles
    assert "High coolant temperature" in titles
    assert "falls short of target" in titles
    # overheat at 118C is flagged critical
    assert any(f.severity == "critical" for f in report.findings)


def test_diagnose_combined_and_summary(samples_dir):
    scan = parse.parse_autoscan(samples_dir["autoscan"])
    log = parse.parse_measuring_log(samples_dir["advanced"])
    report = diagnose(scan=scan, log=log)
    assert report.summary["high"] >= 1
    assert report.headline.startswith(str(len(report.findings)))


def test_diagnose_empty():
    report = diagnose()
    assert report.findings == []
    assert report.notes
