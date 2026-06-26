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


def test_path_traversal_rejected(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])
    out = ex("read_log", {"filename": "../../secrets.csv"})
    assert "error" in out


def test_unknown_tool(samples_dir):
    ex = log_tools.make_executor(samples_dir["dir"])
    assert "error" in ex("nope", {})
