"""Register the VCDS MCP server with Claude Desktop and/or Claude Code.

Powers the GUI's "Install MCP Server" button. Kept free of heavy imports (no
``mcp``/Qt) so it can run anywhere — it only writes a JSON config file and/or
shells out to the ``claude`` CLI.

When running as a PyInstaller-frozen app, the server is launched as
``<this .exe> --mcp`` (the bundle can serve MCP itself); from a source/dev
install it is ``<python> -m vcds_mcp.server``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

DEFAULT_NAME = "vcds"
DEFAULT_LOGS_DIR = r"C:\Ross-Tech\VCDS\Logs"


def server_launch() -> Tuple[str, List[str]]:
    """Return ``(command, args)`` that start the stdio MCP server.

    In a frozen bundle this is the dedicated console ``vcds-mcp.exe`` shipped
    alongside the GUI (a windowed exe has no stdin/stdout for stdio); from source
    it is ``<python> -m vcds_mcp.server``.
    """
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        exe = "vcds-mcp.exe" if sys.platform.startswith("win") else "vcds-mcp"
        candidate = os.path.join(os.path.dirname(sys.executable), exe)
        if os.path.isfile(candidate):
            return candidate, []
        return sys.executable, ["--mcp"]  # fallback (single-exe build)
    return sys.executable, ["-m", "vcds_mcp.server"]


def claude_desktop_config_path() -> Optional[str]:
    """Locate ``claude_desktop_config.json`` for the current OS."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return os.path.join(base, "Claude", "claude_desktop_config.json") if base else None
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Claude/claude_desktop_config.json"
        )
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def install_claude_desktop(
    logs_dir: str, name: str = DEFAULT_NAME, config_path: Optional[str] = None
) -> Tuple[bool, str]:
    """Add (or update) the ``name`` MCP server in the Claude Desktop config.

    Existing config is preserved and backed up to ``*.bak``. Returns
    ``(ok, message)``.
    """
    path = config_path or claude_desktop_config_path()
    if not path:
        return False, "Could not determine the Claude Desktop config location."
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as exc:
        return False, f"Could not create config directory: {exc}"

    config = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                config = json.load(fh) or {}
        except ValueError as exc:
            return False, (
                "Your existing Claude Desktop config has a JSON syntax error, so it "
                f"can't be safely updated:\n  {exc}\n\nFix that file (it may contain "
                f"your other MCP servers), then retry.\nFile: {path}"
            )
        except OSError as exc:
            return False, f"Could not read config: {exc}\nFile: {path}"
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass

    command, args = server_launch()
    servers = config.setdefault("mcpServers", {})
    servers[name] = {"command": command, "args": args, "env": {"VCDS_LOGS_DIR": logs_dir}}

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2)
    except OSError as exc:
        return False, f"Could not write config: {exc}"
    return True, f"Added '{name}' to {path}.\nRestart Claude Desktop to load it."


def install_claude_code(logs_dir: str, name: str = DEFAULT_NAME) -> Tuple[bool, str]:
    """Register the server with Claude Code via the ``claude`` CLI."""
    claude = shutil.which("claude")
    if not claude:
        return False, "The 'claude' CLI was not found on PATH (install Claude Code first)."
    command, args = server_launch()
    # Make re-installs idempotent: drop any existing registration first.
    try:
        subprocess.run([claude, "mcp", "remove", name], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        pass
    # Name must come first; options follow; `--` ends options so the command +
    # its args are positionals. (`--env` is variadic and would otherwise consume
    # the name/command — the cause of "missing required argument 'commandOrUrl'".)
    cmd = [claude, "mcp", "add", name, "--transport", "stdio",
           "--env", f"VCDS_LOGS_DIR={logs_dir}", "--", command, *args]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed to run claude: {exc}"
    if res.returncode != 0:
        return False, (res.stderr or res.stdout or "claude mcp add failed").strip()
    return True, f"Registered '{name}' with Claude Code."


def claude_code_available() -> bool:
    return shutil.which("claude") is not None
