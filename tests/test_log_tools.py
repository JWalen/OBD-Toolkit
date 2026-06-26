"""Tests for the AI log-browsing tools (confined to the logs folder)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from vcds_gui import log_tools  # noqa: E402


def test_list_read_and_diagnose(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])

    listing = ex("list_logs", {})
    names = {f["filename"] for f in listing["files"]}
    assert "advanced_uds.CSV" in names and "autoscan.TXT" in names

    log = ex("read_log", {"filename": "advanced_uds.CSV"})
    assert any(c["name"] == "Engine Speed" for c in log["channels"])

    scan = ex("read_autoscan", {"filename": "autoscan.TXT"})
    assert scan["vin"] == "WAUZZZ8K9BA123456"

    diag = ex("diagnose_log", {"autoscan": "autoscan.TXT", "filename": "advanced_uds.CSV"})
    assert diag["findings"]


def test_list_logs_includes_subfolders(samples_dir, tmp_path):
    import os
    import shutil

    base = tmp_path / "logs"
    (base / "2011_Audi_123456").mkdir(parents=True)
    shutil.copy(os.path.join(samples_dir["dir"], "advanced_uds.CSV"),
                base / "2011_Audi_123456" / "drive.CSV")
    ex = log_tools.make_executor(str(base))
    listing = ex("list_logs", {})
    rels = [f["filename"] for f in listing["files"]]
    assert any("2011_Audi_123456" in r and r.endswith("drive.CSV") for r in rels)
    # reading via the relative subpath works
    out = ex("read_log", {"filename": rels[0]})
    assert "channels" in out


def test_path_traversal_rejected(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])
    out = ex("read_log", {"filename": "../../secrets.csv"})
    assert "error" in out


def test_unknown_tool(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])
    assert "error" in ex("nope", {})


def test_lookup_events_and_performance(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])
    assert ex("lookup_dtc", {"code": "P0299"})["severity"] == "high"
    ev = ex("find_events", {"filename": "advanced_uds.CSV"})
    assert ev["count"] > 0
    perf = ex("performance", {"filename": "advanced_uds.CSV"})
    assert "acceleration" in perf  # no speed channel -> empty list, but no crash


class _FakeConn:
    def get_dtcs(self):
        return [("P0299", "Underboost")]

    def supported(self):
        return {"RPM", "SPEED"}

    def status(self):
        return "Car Connected"

    def protocol(self):
        return "ISO 15765-4"


def test_live_tools_with_connection(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"], conn_getter=lambda: _FakeConn())
    dtcs = ex("read_live_dtcs", {})
    assert dtcs["dtcs"][0]["code"] == "P0299" and dtcs["dtcs"][0]["severity"] == "high"
    status = ex("obd_status", {})
    assert "RPM" in status["supported_pids"]


def test_live_tool_without_connection(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"], conn_getter=lambda: None)
    out = ex("read_live_dtcs", {})
    assert "error" in out and "connect" in out["error"].lower()
