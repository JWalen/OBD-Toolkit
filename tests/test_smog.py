"""Tests for the emissions-readiness (smog) report + drive-cycle tips."""

from __future__ import annotations

from vcds_core import report, vin


def _readiness(mil=False, **monitors):
    return {"mil": mil, "dtc_count": 0, "monitors": monitors}


def test_smog_ready_verdict():
    r = _readiness(misfire_monitoring={"available": True, "complete": True},
                   catalyst_monitoring={"available": True, "complete": True})
    html = report.build_smog_html("WAUZZZ8K9BA123456", vin.decode_vin("WAUZZZ8K9BA123456"), r, [])
    assert "READY to test" in html
    assert "Audi" in html


def test_smog_not_ready_lists_tips():
    r = _readiness(catalyst_monitoring={"available": True, "complete": False},
                   misfire_monitoring={"available": True, "complete": True})
    html = report.build_smog_html("V", None, r, [])
    assert "NOT ready" in html
    # the incomplete catalyst monitor gets its drive-cycle tip
    assert "cruise" in html.lower()


def test_smog_mil_blocks_ready():
    r = _readiness(mil=True, misfire_monitoring={"available": True, "complete": True})
    html = report.build_smog_html("V", None, r, [])
    assert "NOT ready" in html


def test_drive_cycle_tip_fallback():
    assert "cruise" in report.drive_cycle_tip("catalyst_monitoring").lower()
    assert report.drive_cycle_tip("unknown_monitor")  # non-empty fallback
