"""Entry point for ``python -m vcds_mcp`` and the bundled ``vcds-mcp.exe``."""

import sys

from vcds_mcp.server import main

if __name__ == "__main__":
    sys.exit(main() or 0)
