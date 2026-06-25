"""Entry point for ``python -m vcds_gui`` and the PyInstaller bundle.

``--mcp`` makes the same executable serve the stdio MCP server instead of the
GUI, so the bundled app can be registered with Claude Desktop / Code without a
separate Python. The dispatch happens before importing the GUI so MCP mode
never loads Qt.
"""

import sys


def run() -> int:
    if "--mcp" in sys.argv[1:]:
        from vcds_mcp.server import main as mcp_main

        return mcp_main() or 0
    from vcds_gui.app import main

    return main()


if __name__ == "__main__":
    sys.exit(run())
