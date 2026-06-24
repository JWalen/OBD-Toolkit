"""Unit tests for the MCP server's path confinement (no subprocess)."""

from __future__ import annotations

import pytest

from vcds_mcp import server


def test_safe_path_allows_files_inside(tmp_path, monkeypatch):
    monkeypatch.setenv("VCDS_LOGS_DIR", str(tmp_path))
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    resolved = server._safe_path("a.csv")
    assert resolved.endswith("a.csv")


@pytest.mark.parametrize(
    "bad",
    [
        "../a.csv",
        "..\\a.csv",
        "sub/../../x.csv",
        r"C:\Windows\system32\drivers\etc\hosts",
        "/etc/passwd",
        "",
    ],
)
def test_safe_path_rejects_traversal_and_absolute(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("VCDS_LOGS_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        server._safe_path(bad)


def test_safe_path_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("VCDS_LOGS_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        server._safe_path("does_not_exist.csv")


def test_list_logs_classifies(samples_dir, monkeypatch):
    monkeypatch.setenv("VCDS_LOGS_DIR", samples_dir["dir"])
    out = server.list_logs(kind="all", limit=50)
    kinds = {f["filename"]: f["kind"] for f in out["files"]}
    assert kinds["autoscan.TXT"] == "autoscan"
    assert kinds["advanced_uds.CSV"] == "measuring_log"


def test_read_measuring_log_tool(samples_dir, monkeypatch):
    monkeypatch.setenv("VCDS_LOGS_DIR", samples_dir["dir"])
    out = server.read_measuring_log("advanced_uds.CSV", include_series=True, channels=["Coolant"])
    names = {c["name"] for c in out["channels"]}
    assert "Coolant Temp" in names
    assert "Coolant Temp" in out["series"]  # filtered series included
