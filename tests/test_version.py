"""The build-time _version.py must be authoritative over dist-info scanning.

This guards the bug where a frozen install accumulated several
``vcds_toolkit-*.dist-info`` folders and the app reported the oldest one.
"""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VF = os.path.join(_ROOT, "src", "vcds_core", "_version.py")


def test_version_py_is_authoritative():
    backup = open(_VF, encoding="utf-8").read() if os.path.exists(_VF) else None
    try:
        with open(_VF, "w", encoding="utf-8") as fh:
            fh.write('__version__ = "9.9.9-test"\n')
        out = subprocess.run(
            [sys.executable, "-c", "import vcds_core; print(vcds_core.__version__)"],
            cwd=_ROOT, capture_output=True, text=True, check=True)
        assert "9.9.9-test" in out.stdout
    finally:
        if backup is not None:
            with open(_VF, "w", encoding="utf-8") as fh:
                fh.write(backup)
        elif os.path.exists(_VF):
            os.remove(_VF)
