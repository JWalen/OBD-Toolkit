"""Allow ``python -m vcds_gui`` and serve as the PyInstaller entry point."""

import sys

from vcds_gui.app import main

if __name__ == "__main__":
    sys.exit(main())
