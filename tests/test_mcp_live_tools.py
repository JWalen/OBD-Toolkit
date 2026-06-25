"""Tests for the live OBD-II MCP tool implementations (mocked, no hardware)."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import pytest

from vcds_core import parse
from vcds_obd import live, mcp_tools


class FakeClock:
    def __init__(self, dt: float) -> None:
        self.dt = dt
        self.t = -dt

    def __call__(self) -> float:
        self.t += self.dt
        return self.t


class FakeOBD:
    def __init__(self) -> None:
        self.i = -1
        self.closed = False

    def supported(self):
        return set(live.DEFAULT_CHANNELS_BY_CMD.keys())

    def query_value(self, command_name: str) -> Optional[float]:
        if command_name == "RPM":
            self.i += 1
        i = max(0, self.i)
        if command_name == "BAROMETRIC_PRESSURE":
            return 100.0
        if command_name == "INTAKE_PRESSURE":
            return min(180.0, 100.0 + 2.0 * i)
        if command_name == "RPM":
            return 800.0 + 10.0 * i
        return 0.0

    def get_dtcs(self) -> List[Tuple[str, str]]:
        return [("P2196", "Boost Pressure Regulation")]

    def status(self) -> str:
        return "Car Connected"

    def protocol(self) -> str:
        return "ISO 15765-4 (CAN 11/500)"

    def close(self) -> None:
        self.closed = True


def test_graceful_degradation_no_adapter(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("no device on COM5")

    monkeypatch.setattr(live, "connect", boom)
    out = mcp_tools.obd_status_impl(str(tmp_path))
    assert out["connected"] is False
    assert "no device" in out["error"].lower() or "elm327" in out["error"].lower()

    dtcs = mcp_tools.read_live_dtcs_impl(str(tmp_path))
    assert dtcs["connected"] is False
    assert dtcs["dtcs"] == []


def test_list_serial_ports(monkeypatch):
    monkeypatch.setattr(live, "scan_ports", lambda: ["COM3", "COM5"])
    assert mcp_tools.list_serial_ports_impl() == {"ports": ["COM3", "COM5"]}


def test_obd_status_and_dtcs(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "connect", lambda **k: FakeOBD())
    status = mcp_tools.obd_status_impl(str(tmp_path))
    assert status["connected"] is True
    assert "Boost (derived)" in status["log_channels"]
    assert "RPM" in status["supported_commands"]

    dtcs = mcp_tools.read_live_dtcs_impl(str(tmp_path))
    assert dtcs["connected"] is True
    assert dtcs["dtcs"][0]["code"] == "P2196"


def test_snapshot_pids(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "connect", lambda **k: FakeOBD())
    snap = mcp_tools.snapshot_pids_impl(str(tmp_path))
    assert snap["connected"] is True
    assert snap["values"]["Barometric Pressure"]["value"] == 100.0
    assert snap["values"]["Boost (derived)"]["unit"] == "kPa"


def test_vehicle_info_impl(monkeypatch, tmp_path):
    class Conn(FakeOBD):
        def read_vin(self):
            return "WAUZZZ8K9BA123456"

        def read_calibration_ids(self):
            return ["8K0907115P", "CVN1234"]

    monkeypatch.setattr(live, "connect", lambda **k: Conn())
    out = mcp_tools.vehicle_info_impl(str(tmp_path))
    assert out["connected"] and out["vin"] == "WAUZZZ8K9BA123456"
    assert out["make"] == "Audi" and out["brand_profile"] == "vag"
    assert "8K0907115P" in out["calibration_ids"]


def test_readiness_impl(monkeypatch, tmp_path):
    class Conn(FakeOBD):
        def read_readiness(self):
            return {"mil": False, "dtc_count": 0, "monitors": {
                "misfire_monitoring": {"available": True, "complete": True},
                "catalyst_monitoring": {"available": True, "complete": False}}}

        def read_permanent_dtcs(self):
            return []

    monkeypatch.setattr(live, "connect", lambda **k: Conn())
    out = mcp_tools.readiness_impl(str(tmp_path))
    assert out["mil_on"] is False
    assert "catalyst_monitoring" in out["incomplete_monitors"]
    assert out["ready_for_emissions"] is False  # an incomplete monitor


def test_onboard_tests_impl(monkeypatch, tmp_path):
    class Conn(FakeOBD):
        def read_monitor_tests(self):
            return [{"command": "MONITOR_O2_B1S1", "name": "Rich-to-lean", "value": 0.7,
                     "min": 0.5, "max": 1.0, "passed": True}]

    monkeypatch.setattr(live, "connect", lambda **k: Conn())
    out = mcp_tools.onboard_tests_impl(str(tmp_path))
    assert out["connected"] and out["count"] == 1
    assert out["tests"][0]["passed"] is True


def test_run_obd_session_roundtrips(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "connect", lambda **k: FakeOBD())
    # Make the session instant and deterministic.
    monkeypatch.setattr(live.time, "sleep", lambda _s: None)
    monkeypatch.setattr(live.time, "monotonic", FakeClock(0.2))

    out = mcp_tools.run_obd_session_impl(
        str(tmp_path),
        duration_s=12.0,
        trigger={"thresholds": [{"channel": "Boost (derived)", "op": ">", "value": 50}]},
    )
    assert out["connected"] is True
    assert "Boost (derived)" in out["channels"]
    assert out["sample_count"] > 20
    assert out["captures"], "threshold should have produced a capture"

    # The returned session file lives in the logs dir and round-trips.
    session_path = os.path.join(str(tmp_path), out["filename"])
    assert os.path.isfile(session_path)
    mlog = parse.parse_measuring_log(session_path)
    assert mlog.channel("Boost (derived)") is not None
    events = parse.find_events(mlog)
    assert events  # analysis tools work on the live capture unchanged
