"""Headless smoke test for the GUI (offscreen Qt platform).

Skipped automatically when PySide6 / pyqtgraph are not installed. Verifies the
window constructs and that Tab 1 can load a measuring CSV and an Auto-Scan,
populate channels, run event detection and export a clipped CSV — all without a
display or any hardware.
"""

from __future__ import annotations

import os

import pytest

# Force the non-interactive Qt backend before importing anything Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtWidgets  # noqa: E402

from vcds_core import parse  # noqa: E402
from vcds_gui import app as gui_app  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_window_constructs(qapp):
    win = gui_app.MainWindow()
    assert win.tabs.count() == 2
    win.close()


def test_analyzer_loads_csv_and_runs_events(qapp, samples_dir):
    win = gui_app.MainWindow()
    tab = win.analyzer
    tab.load_csv(samples_dir["advanced"])
    assert tab.chan_list.count() >= 5
    assert "Boost (derived)" not in {  # sanity: advanced sample has no derived chan
        tab.chan_list.item(i).data(0x0100) for i in range(tab.chan_list.count())
    }
    # plot received the channels
    assert "Engine Speed" in tab.plot.channels

    # heuristic event detection populates the list
    tab.run_events(use_rules=False)
    assert tab.event_list.count() > 0

    # cursor readout works at an arbitrary time
    tab.plot.set_cursor(2.0)
    assert "t = 2.000" in tab.plot.readout.text()
    win.close()


def test_help_dialog_builds(qapp):
    win = gui_app.MainWindow()
    dlg = gui_app.HelpDialog(win._version, win)
    assert "User Guide" in dlg.windowTitle()
    win.close()


def test_quick_tour_navigation(qapp, tmp_path):
    from PySide6 import QtCore

    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat)
    dlg = gui_app.QuickTourDialog(settings, show_startup_default=True)
    assert dlg.stack.count() == len(gui_app.TOUR_PAGES) == 4
    assert dlg.btn_next.text() == "Next"
    assert not dlg.btn_back.isEnabled()  # first page

    # advance to the final page
    for _ in range(dlg.stack.count() - 1):
        dlg._next()
    assert dlg.btn_next.text() == "Finish"
    assert dlg.btn_back.isEnabled()

    # unticking "show at startup" must persist
    dlg.chk.setChecked(False)
    dlg._persist()
    assert settings.value("ui/show_tour", True, type=bool) is False


def test_update_banner_shows_on_found(qapp):
    from vcds_gui.updater import UpdateInfo

    win = gui_app.MainWindow()
    assert win.update_banner.isHidden()  # nothing yet
    info = UpdateInfo(
        version="9.9.9", tag="v9.9.9", name="v9.9.9", notes="notes",
        html_url="https://github.com/JWalen/VAGScanner/releases/tag/v9.9.9",
        installer_url="https://example.test/setup.exe", installer_name="setup.exe",
        installer_size=10, sha256=None,
    )
    win._on_update_found(info)
    assert not win.update_banner.isHidden()
    assert "9.9.9" in win.update_banner.label.text()
    # a "no update" result with a background (non-manual) check is silent
    win._update_manual = False
    win._on_update_none()
    win.close()


def test_analyzer_adds_computed_channels(qapp, tmp_path):
    path = tmp_path / "trims.csv"
    path.write_text(
        "TIME,Engine RPM,Short Fuel Trim 1,Long Fuel Trim 1\n"
        "s,/min,%,%\n0,800,2,12\n1,820,3,14\n2,810,2,16\n",
        encoding="utf-8",
    )
    win = gui_app.MainWindow()
    win.analyzer.load_csv(str(path))
    assert "Fuel Trim Total" in win.analyzer.plot.channels
    assert "AFR (estimated)" in win.analyzer.plot.channels
    win.close()


def test_diagnosis_dialog_builds(qapp, samples_dir):
    from vcds_core.diagnose import diagnose as run_diagnose

    win = gui_app.MainWindow()
    win.analyzer.load_scan(samples_dir["autoscan"])
    assert win.analyzer.scan is not None
    report = run_diagnose(scan=win.analyzer.scan)
    dlg = gui_app.DiagnosisDialog(report, win)
    tree = dlg.findChild(QtWidgets.QTreeWidget)
    assert tree is not None and tree.topLevelItemCount() == len(report.findings)
    win.close()


def test_analyzer_loads_autoscan(qapp, samples_dir):
    win = gui_app.MainWindow()
    tab = win.analyzer
    tab.load_scan(samples_dir["autoscan"])
    assert tab.scan_tree.topLevelItemCount() == 3
    assert "WAUZZZ8K9BA123456" in tab.scan_info.text()
    win.close()


def test_export_clip_roundtrips(qapp, samples_dir, tmp_path):
    mlog = parse.parse_measuring_log(samples_dir["advanced"])
    out = str(tmp_path / "clip.CSV")
    n = gui_app._export_clip(mlog, out, 2.0, 6.0)
    assert n > 0
    # the exported clip parses straight back through the core
    reparsed = parse.parse_measuring_log(out)
    assert reparsed.channel("Engine Speed") is not None
    assert reparsed.duration_s is not None and reparsed.duration_s <= 4.5
