# PyInstaller spec for the macOS .app bundle.
#
# Build (from repo root, on macOS):
#     pyinstaller installer/vcds_gui_mac.spec --clean --noconfirm
#
# Output: dist/OBD Toolkit.app   (then packaged into a .dmg by CI)

import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

SPEC_DIR = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(SPEC_DIR)
SRC = os.path.join(ROOT, "src")
ENTRY = os.path.join(SRC, "vcds_gui", "__main__.py")
ICON = os.path.join(SPEC_DIR, "app.icns")
ICON = ICON if os.path.isfile(ICON) else None

pg_datas, pg_binaries, pg_hidden = collect_all("pyqtgraph")
try:
    mcp_datas, mcp_binaries, mcp_hidden = collect_all("mcp")
except Exception:
    mcp_datas, mcp_binaries, mcp_hidden = [], [], []
try:
    meta_datas = copy_metadata("vcds-toolkit")
except Exception:
    meta_datas = []

example_datas = []
examples_dir = os.path.join(ROOT, "examples")
if os.path.isdir(examples_dir):
    for name in os.listdir(examples_dir):
        full = os.path.join(examples_dir, name)
        if os.path.isfile(full):
            example_datas.append((full, "examples"))

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=pg_binaries + mcp_binaries,
    datas=pg_datas + example_datas + meta_datas + mcp_datas,
    hiddenimports=pg_hidden
    + mcp_hidden
    + [
        "vcds_core", "vcds_core.parse", "vcds_core._version",
        "vcds_obd", "vcds_obd.live", "vcds_obd.mcp_tools", "vcds_obd.enhanced",
        "vcds_gui.ai", "vcds_gui.log_tools",
        "vcds_mcp", "vcds_mcp.server", "vcds_mcp.install",
        "certifi",
    ],
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
        "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
        "PyQt5", "PyQt6", "tkinter", "matplotlib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="OBD Toolkit",
    debug=False, strip=False, upx=False, console=False, icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="OBD Toolkit")
app = BUNDLE(
    coll,
    name="OBD Toolkit.app",
    icon=ICON,
    bundle_identifier="com.deltamodtech.obdtoolkit",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": os.environ.get("OBD_VERSION", "1.0.0"),
        "CFBundleVersion": os.environ.get("OBD_VERSION", "1.0.0"),
    },
)
