"""Drive the MCP server as a subprocess via the official mcp client.

Confirms the file tools register and return correct data through a real
initialize -> list_tools -> call_tool handshake over stdio.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

mcp_client = pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")


def _server_params(logs_dir: str) -> StdioServerParameters:
    env = dict(os.environ)
    env["VCDS_LOGS_DIR"] = logs_dir
    # Ensure the child can import the src packages.
    env["PYTHONPATH"] = _SRC + os.pathsep + env.get("PYTHONPATH", "")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "vcds_mcp.server"],
        env=env,
    )


def _content_json(result):
    """Extract a JSON/text payload from a CallToolResult."""
    # structuredContent is the parsed return value when available.
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        # FastMCP wraps non-dict returns under "result"; dict returns pass through.
        return sc.get("result", sc)
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            return json.loads(text)
    raise AssertionError("No content returned from tool call.")


@pytest.mark.asyncio
async def test_mcp_handshake_and_file_tools(samples_dir):
    params = _server_params(samples_dir["dir"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            for expected in (
                "list_logs",
                "read_autoscan",
                "read_measuring_log",
                "channel_stats",
                "find_log_events",
            ):
                assert expected in names, f"missing tool {expected}"

            # list_logs classifies both files
            res = await session.call_tool("list_logs", {"kind": "all", "limit": 50})
            payload = _content_json(res)
            kinds = {f["filename"]: f["kind"] for f in payload["files"]}
            assert kinds.get("autoscan.TXT") == "autoscan"
            assert kinds.get("advanced_uds.CSV") == "measuring_log"

            # read_autoscan returns VIN + correct fault structure
            res = await session.call_tool("read_autoscan", {"filename": "autoscan.TXT"})
            scan = _content_json(res)
            assert scan["vin"] == "WAUZZZ8K9BA123456"
            assert scan["total_faults"] == 3
            engine = next(m for m in scan["modules"] if m["address"] == "01")
            assert len(engine["faults"]) == 2
            assert any("P2196" in (f["status_detail"] or "") for f in engine["faults"])

            # read_measuring_log returns channels + stats
            res = await session.call_tool(
                "read_measuring_log",
                {"filename": "advanced_uds.CSV", "include_series": True, "channels": ["Engine"]},
            )
            mlog = _content_json(res)
            chan_names = {c["name"] for c in mlog["channels"]}
            assert "Boost Pressure (actual)" in chan_names
            assert "Engine Speed" in mlog["series"]

            # channel_stats for a single channel
            res = await session.call_tool(
                "channel_stats", {"filename": "advanced_uds.CSV", "channel": "Coolant"}
            )
            stats = _content_json(res)
            assert stats["name"] == "Coolant Temp"
            assert stats["unit"] == "°C"

            # find_log_events heuristics
            res = await session.call_tool("find_log_events", {"filename": "advanced_uds.CSV"})
            ev = _content_json(res)
            assert ev["count"] > 0
            assert any(e["kind"] == "divergence" for e in ev["events"])


@pytest.mark.asyncio
async def test_mcp_rejects_path_traversal(samples_dir):
    params = _server_params(samples_dir["dir"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(
                "read_autoscan", {"filename": "..\\..\\windows\\system32\\drivers\\etc\\hosts"}
            )
            # The tool raises ValueError -> surfaced as an error result.
            assert res.isError, "path traversal must be rejected"
