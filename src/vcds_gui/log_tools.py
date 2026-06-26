"""Function-calling tools that let the AI assistant browse the stored logs.

The executor is confined to the logs folder (path-traversal rejected), mirrors
the MCP file tools, and returns plain JSON-able dicts. Standard-library + core.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from vcds_core import compute, parse
from vcds_core.diagnose import diagnose

TOOL_SPECS = [
    {
        "name": "list_logs",
        "description": "List the VCDS/OBD log files in the user's logs folder "
                       "(measuring-value CSVs and Auto-Scan TXTs), newest first.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_log",
        "description": "Read a measuring-value CSV log: detected format, channels and "
                       "per-channel min/max/mean stats.",
        "parameters": {
            "type": "object",
            "properties": {"filename": {"type": "string",
                                        "description": "file name within the logs folder"}},
            "required": ["filename"],
        },
    },
    {
        "name": "read_autoscan",
        "description": "Read a VCDS Auto-Scan TXT: VIN, mileage, modules and faults.",
        "parameters": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
    },
    {
        "name": "diagnose_log",
        "description": "Diagnose a measuring log and/or an Auto-Scan into prioritized "
                       "findings with likely causes.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "measuring CSV (optional)"},
                "autoscan": {"type": "string", "description": "Auto-Scan TXT (optional)"},
            },
            "required": [],
        },
    },
]


def make_executor(logs_dir: str, profile: str = "generic"):
    """Return ``execute(name, args) -> dict`` confined to ``logs_dir``."""

    def _safe(filename: str) -> str:
        if (not filename or os.path.isabs(filename)
                or ".." in filename.replace("\\", "/").split("/")):
            raise ValueError(f"Illegal filename: {filename!r}")
        base = os.path.abspath(logs_dir)
        full = os.path.abspath(os.path.join(base, filename))
        if os.path.commonpath([os.path.normcase(full), os.path.normcase(base)]) != os.path.normcase(base):
            raise ValueError("Path escapes the logs folder.")
        if not os.path.isfile(full):
            raise ValueError(f"File not found: {filename!r}")
        return full

    def _list() -> dict:
        base = os.path.abspath(logs_dir)
        rows = []
        if os.path.isdir(base):
            for name in os.listdir(base):
                full = os.path.join(base, name)
                if os.path.isfile(full) and name.lower().endswith((".csv", ".txt")):
                    st = os.stat(full)
                    rows.append({"filename": name, "kind": parse.classify_file(full),
                                 "size": st.st_size, "mtime": st.st_mtime})
        rows.sort(key=lambda r: r["mtime"], reverse=True)
        return {"logs_dir": base, "count": len(rows), "files": rows}

    def _read_log(fn: str) -> dict:
        log = parse.parse_measuring_log(_safe(fn))
        return {
            "file": os.path.basename(log.file), "format": log.format_guess,
            "delimiter": log.delimiter, "duration_s": log.duration_s,
            "sample_count": log.sample_count,
            "channels": [{"name": c.name, "unit": c.unit, "min": c.min, "max": c.max,
                          "mean": c.mean} for c in log.channels],
        }

    def _read_scan(fn: str) -> dict:
        scan = parse.parse_autoscan(_safe(fn))
        return {
            "vin": scan.vin, "mileage": scan.mileage, "total_faults": scan.total_faults,
            "modules": [{"address": m.address, "name": m.name,
                         "faults": [{"code": f.code, "description": f.description,
                                     "status_detail": f.status_detail} for f in m.faults]}
                        for m in scan.modules],
        }

    def _diagnose(fn: Optional[str], autoscan: Optional[str]) -> dict:
        log = scan = None
        if autoscan:
            scan = parse.parse_autoscan(_safe(autoscan))
        if fn:
            log = parse.parse_measuring_log(_safe(fn))
            compute.add_computed_channels(log)
        if log is None and scan is None:
            return {"error": "Provide a measuring filename and/or an autoscan filename."}
        report = diagnose(scan=scan, log=log, profile=profile)
        return {
            "headline": report.headline, "summary": report.summary,
            "findings": [{"severity": f.severity, "title": f.title, "detail": f.detail,
                          "causes": f.causes} for f in report.findings],
        }

    def execute(name: str, args: dict) -> dict:
        try:
            args = args or {}
            if name == "list_logs":
                return _list()
            if name == "read_log":
                return _read_log(args["filename"])
            if name == "read_autoscan":
                return _read_scan(args["filename"])
            if name == "diagnose_log":
                return _diagnose(args.get("filename"), args.get("autoscan"))
            return {"error": f"unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    return execute
