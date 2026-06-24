"""Shared pytest fixtures.

Generates the synthetic sample files once per session so every test works
against the same VCDS-style inputs without any hardware.
"""

from __future__ import annotations

import atexit
import os
import sys

import pytest

# Make ``src/`` importable without an editable install.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def pytest_sessionfinish(session, exitstatus):
    """Avoid a PySide6/pyqtgraph offscreen crash corrupting the exit code.

    On Windows the Qt "offscreen" platform can segfault inside C++ static
    destructors during interpreter shutdown — AFTER every test has already
    passed — which would otherwise turn a green run into a non-zero exit. If Qt
    was loaded this session, flush output and hard-exit with pytest's real
    status before those destructors run.
    """
    if "PySide6" in sys.modules:
        def _hard_exit():
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(int(exitstatus))

        atexit.register(_hard_exit)


@pytest.fixture(scope="session")
def samples_dir(tmp_path_factory):
    import make_samples

    d = tmp_path_factory.mktemp("samples")
    classic = str(d / "classic_group.CSV")
    advanced = str(d / "advanced_uds.CSV")
    autoscan = str(d / "autoscan.TXT")
    make_samples.make_classic(classic)
    make_samples.make_advanced(advanced)
    make_samples.make_autoscan(autoscan)
    return {
        "dir": str(d),
        "classic": classic,
        "advanced": advanced,
        "autoscan": autoscan,
    }
