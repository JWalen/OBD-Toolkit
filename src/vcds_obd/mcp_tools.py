"""Live OBD-II MCP tools, registered onto the FastMCP server by vcds_mcp.server.

These are request/response only — NO streaming. They require an ELM327 plugged
into the machine running the server and degrade gracefully with a clear message
when no adapter is connected.

The thin tool wrappers (registered with ``@mcp.tool()``) delegate to the
plain functions below, which take ``logs_dir`` explicitly so they can be unit
tested without the MCP machinery or any hardware.
"""

from __future__ import annotations

import os
from typing import List, Optional

from vcds_core import knowledge, vin

from . import live


def _close(conn) -> None:
    closer = getattr(conn, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:  # noqa: BLE001
            pass


def list_serial_ports_impl() -> dict:
    return {"ports": live.scan_ports()}


def obd_status_impl(logs_dir: str, port: Optional[str] = None, baud: Optional[int] = None) -> dict:
    try:
        conn = live.connect(port=port, baud=baud)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}"}
    try:
        supported = sorted(conn.supported())
        channels = [c.name for c in live.build_channels(conn.supported())]
        return {
            "connected": True,
            "status": conn.status(),
            "protocol": conn.protocol(),
            "supported_commands": supported,
            "log_channels": channels,
        }
    finally:
        _close(conn)


def read_live_dtcs_impl(logs_dir: str, port: Optional[str] = None) -> dict:
    try:
        conn = live.connect(port=port)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}", "dtcs": []}
    try:
        dtcs = live.read_dtcs(conn)
        out = []
        for code, desc in dtcs:
            k = knowledge.lookup(code)
            out.append({
                "code": code,
                "description": desc or k.description,
                "severity": k.severity,
                "system": k.system,
                "likely_causes": k.causes,
                "notes": k.notes,
            })
        return {"connected": True, "count": len(out), "dtcs": out}
    finally:
        _close(conn)


def snapshot_pids_impl(
    logs_dir: str, pids: Optional[List[str]] = None, port: Optional[str] = None
) -> dict:
    try:
        conn = live.connect(port=port)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}"}
    try:
        channels = live.build_channels(conn.supported(), pids, include_all=pids is not None)
        snap = live.snapshot(conn, channels)
        by_name = {c.name: c for c in channels}
        return {
            "connected": True,
            "values": {
                name: {"value": val, "unit": by_name[name].unit}
                for name, val in snap.items()
            },
        }
    finally:
        _close(conn)


def vehicle_info_impl(logs_dir: str, port: Optional[str] = None) -> dict:
    try:
        conn = live.connect(port=port)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}"}
    try:
        vin_str = conn.read_vin() if hasattr(conn, "read_vin") else None
        cals = conn.read_calibration_ids() if hasattr(conn, "read_calibration_ids") else []
        info = vin.decode_vin(vin_str) if vin_str else None
        return {
            "connected": True,
            "vin": vin_str,
            "make": info.make if info else None,
            "model_year": info.year if info else None,
            "brand_profile": info.brand_profile if info else None,
            "calibration_ids": cals,
        }
    finally:
        _close(conn)


def readiness_impl(logs_dir: str, port: Optional[str] = None) -> dict:
    try:
        conn = live.connect(port=port)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}"}
    try:
        r = conn.read_readiness() if hasattr(conn, "read_readiness") else None
        perm = conn.read_permanent_dtcs() if hasattr(conn, "read_permanent_dtcs") else []
        if r is None:
            return {"connected": True, "error": "Readiness status unavailable."}
        not_ready = [m for m, s in r["monitors"].items() if s["available"] and not s["complete"]]
        return {
            "connected": True,
            "mil_on": r["mil"],
            "dtc_count": r["dtc_count"],
            "monitors": r["monitors"],
            "incomplete_monitors": not_ready,
            "ready_for_emissions": (not r["mil"]) and len(not_ready) == 0,
            "permanent_dtcs": [{"code": c, "description": d} for c, d in perm],
        }
    finally:
        _close(conn)


def run_obd_session_impl(
    logs_dir: str,
    duration_s: float,
    pids: Optional[List[str]] = None,
    port: Optional[str] = None,
    trigger: Optional[dict] = None,
) -> dict:
    duration_s = min(float(duration_s), float(live.MAX_SESSION_SECONDS))
    try:
        conn = live.connect(port=port)
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": f"No ELM327 adapter: {exc}"}
    try:
        channels = live.build_channels(conn.supported(), pids, include_all=pids is not None)
        if not channels:
            return {"connected": True, "error": "No supported OBD-II PIDs reported by the ECU."}
        logger = live.LiveLogger(conn, channels, logs_dir)
        result = logger.run(duration_s, trigger=live.Trigger.from_obj(trigger))
        return {
            "connected": True,
            "filename": os.path.basename(result.session_file),
            "sample_count": result.sample_count,
            "duration_s": result.duration_s,
            "channels": result.channels,
            "dtcs": [{"code": c, "description": d} for c, d in result.dtcs],
            "captures": [
                {
                    "filename": os.path.basename(cap.file),
                    "trigger_kind": cap.trigger_kind,
                    "trigger_time": cap.trigger_time,
                    "reason": cap.reason,
                }
                for cap in result.captures
            ],
        }
    finally:
        _close(conn)


def register_obd_tools(mcp, logs_dir_fn) -> None:
    """Register the live OBD-II tools onto a FastMCP instance.

    Args:
        mcp: The FastMCP server.
        logs_dir_fn: Callable returning the current logs directory.
    """

    @mcp.tool()
    def list_serial_ports() -> dict:
        """List candidate serial ports for an ELM327 adapter on this machine.

        Returns:
            A dict with a "ports" list of device names (e.g. ["COM5"]).
        """
        return list_serial_ports_impl()

    @mcp.tool()
    def obd_status(port: Optional[str] = None, baud: Optional[int] = None) -> dict:
        """Connect to the ELM327 and report protocol and supported PIDs.

        Args:
            port: Serial port to use (e.g. "COM5"). Auto-scans when omitted.
            baud: Baud-rate override for clones (38400 / 9600 / 115200).

        Returns:
            Connection status, protocol name, supported command names and the
            channels that would be logged. Degrades to {"connected": false, ...}
            when no adapter is present.
        """
        return obd_status_impl(logs_dir_fn(), port=port, baud=baud)

    @mcp.tool()
    def vehicle_info(port: Optional[str] = None) -> dict:
        """Read the VIN and ECU calibration IDs, and decode make / model year.

        Args:
            port: Serial port to use. Auto-scans when omitted.

        Returns:
            VIN, decoded make/model-year/brand-profile, and calibration IDs.
        """
        return vehicle_info_impl(logs_dir_fn(), port=port)

    @mcp.tool()
    def readiness_monitors(port: Optional[str] = None) -> dict:
        """Read I/M emissions-readiness monitors, MIL state and permanent DTCs.

        Args:
            port: Serial port to use. Auto-scans when omitted.

        Returns:
            MIL state, DTC count, each monitor's availability/completeness, which
            monitors are incomplete, an overall emissions-ready flag, and any
            permanent (mode 0A) DTCs.
        """
        return readiness_impl(logs_dir_fn(), port=port)

    @mcp.tool()
    def read_live_dtcs(port: Optional[str] = None) -> dict:
        """Read current stored Diagnostic Trouble Codes from the ECU.

        Args:
            port: Serial port to use. Auto-scans when omitted.

        Returns:
            A list of {code, description} DTCs, or a clear error if no adapter.
        """
        return read_live_dtcs_impl(logs_dir_fn(), port=port)

    @mcp.tool()
    def snapshot_pids(pids: Optional[List[str]] = None, port: Optional[str] = None) -> dict:
        """One-shot read of current values for the supported PIDs.

        Args:
            pids: Optional subset of channel names / command names to read.
                Defaults to all supported channels (incl. "Boost (derived)").
            port: Serial port to use. Auto-scans when omitted.

        Returns:
            A {channel: {value, unit}} map of the current readings.
        """
        return snapshot_pids_impl(logs_dir_fn(), pids=pids, port=port)

    @mcp.tool()
    def run_obd_session(
        duration_s: float,
        pids: Optional[List[str]] = None,
        port: Optional[str] = None,
        trigger: Optional[dict] = None,
    ) -> dict:
        """Log live OBD-II data to a VCDS-compatible CSV for a capped duration.

        The session is HARD-capped at 300 seconds and written into the logs
        folder so read_measuring_log / find_log_events can analyze it next.

        Args:
            duration_s: Seconds to record (capped at 300).
            pids: Optional subset of channel names / command names to log.
            port: Serial port to use. Auto-scans when omitted.
            trigger: Optional event-capture trigger, e.g.
                {"thresholds": [{"channel": "Boost", "op": ">", "value": 120}],
                 "on_new_dtc": true}. On a trigger a clipped capture CSV that
                includes pre-trigger context is written alongside the session.

        Returns:
            The session filename, sample count, channels, current DTCs and any
            event-capture files produced.
        """
        return run_obd_session_impl(
            logs_dir_fn(), duration_s, pids=pids, port=port, trigger=trigger
        )
