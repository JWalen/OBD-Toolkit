# Windows installer

Builds a self-contained Windows installer for the **VCDS Toolkit desktop GUI**
(`vcds-gui`). End users do **not** need Python installed — the bundle ships its
own interpreter and all of PySide6 / pyqtgraph.

> The installer covers the **GUI** only. The **MCP server** (`vcds-mcp`) is a
> developer integration for Claude Desktop / Code and is installed via
> `pip install -e ".[mcp]"` (see the top-level README), not this installer.

## What you get

- `dist\VCDS Toolkit\` — a portable, self-contained app folder (PyInstaller
  one-folder build). `VCDS Toolkit.exe` runs the GUI directly.
- `installer\Output\VCDS-Toolkit-Setup-<version>.exe` — a proper installer with
  Start-Menu (and optional desktop) shortcuts and an Add/Remove Programs entry.
  Installs per-user by default, so **no admin rights are required**.

## Prerequisites

- Python 3.10+ (your project venv is fine).
- [Inno Setup 6](https://jrsoftware.org/isdl.php) for the `Setup.exe` step.
  Without it you still get the portable folder.

## Build

From the repository root, with the venv active:

```powershell
.\.venv\Scripts\Activate.ps1
.\installer\build_installer.ps1
```

The script reads the version from `pyproject.toml`, runs PyInstaller, then
compiles the Inno Setup installer if `iscc.exe` is found.

### Manual steps (equivalent)

```powershell
pip install pyinstaller
pip install -e ".[gui]"
pyinstaller installer\vcds_gui.spec --clean --noconfirm
iscc installer\vcds-toolkit.iss /DMyAppVersion=0.1.0
```

## Notes

- **One-folder, not one-file** — chosen on purpose: faster startup and far less
  antivirus friction than the one-file temp-extraction approach on locked-down
  corporate machines.
- **Branding** — drop an `app.ico` next to the spec and set `icon=...` in
  `vcds_gui.spec` plus `SetupIconFile` in `vcds-toolkit.iss`.
- **Releases** — the GitHub Actions release workflow builds this installer and
  attaches `VCDS-Toolkit-Setup-<version>.exe` to each tagged release
  automatically (requires Inno Setup on the runner, installed via Chocolatey).
- **Code signing** — unsigned installers trigger a SmartScreen warning. To sign,
  add a `signtool` step after the `iscc` compile with your code-signing cert.
