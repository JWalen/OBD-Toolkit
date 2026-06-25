"""Tests for MCP-server registration helpers (no real Claude config touched)."""

from __future__ import annotations

import json

from vcds_mcp import install


def test_server_launch_source_mode():
    command, args = install.server_launch()
    assert command  # the interpreter / exe
    assert "-m" in args and "vcds_mcp.server" in args  # not frozen in tests


def test_install_claude_desktop_writes_config(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    ok, msg = install.install_claude_desktop(r"C:\Logs", name="vcds", config_path=str(cfg))
    assert ok, msg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    server = data["mcpServers"]["vcds"]
    assert server["env"]["VCDS_LOGS_DIR"] == r"C:\Logs"
    assert server["command"] and isinstance(server["args"], list)


def test_install_preserves_existing_and_backs_up(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}', encoding="utf-8")
    ok, _ = install.install_claude_desktop("L", config_path=str(cfg))
    assert ok
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert "other" in data["mcpServers"] and "vcds" in data["mcpServers"]
    assert (tmp_path / "cfg.json.bak").is_file()


def test_install_rejects_invalid_json(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{ not valid json", encoding="utf-8")
    ok, msg = install.install_claude_desktop("L", config_path=str(cfg))
    assert not ok and "JSON" in msg


def test_claude_code_available_is_bool():
    assert isinstance(install.claude_code_available(), bool)


def test_install_claude_code_command_order(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        if "add" in cmd:
            captured["cmd"] = cmd

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(install.shutil, "which", lambda n: "claude" if n == "claude" else None)
    monkeypatch.setattr(install.subprocess, "run", fake_run)
    ok, _ = install.install_claude_code(r"C:\Logs", name="vcds")
    assert ok
    cmd = captured["cmd"]
    # name must precede --env, and -- must precede the server command (the bug fix)
    i_name, i_env, i_dd = cmd.index("vcds"), cmd.index("--env"), cmd.index("--")
    assert i_name < i_env < i_dd
    assert len(cmd) > i_dd + 1  # a command follows "--"
