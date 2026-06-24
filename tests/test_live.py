"""Mocked live-capture tests — NO hardware.

A fake Connection supplies canned supported_commands, a scripted PID stream and
a DTC list. We assert that:
  * a logged session CSV round-trips through vcds_core.parse and yields the
    expected channels, including the derived boost channel;
  * a threshold trigger fires and writes a clipped capture;
  * a new-DTC trigger fires;
  * read_dtcs surfaces the mocked codes.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from vcds_core import parse
from vcds_obd import live


class FakeClock:
    """Deterministic monotonic clock advancing by ``dt`` on every call."""

    def __init__(self, dt: float) -> None:
        self.dt = dt
        self.t = -dt

    def __call__(self) -> float:
        self.t += self.dt
        return self.t


class FakeOBD:
    """Scripted ELM327 stand-in implementing the live.Connection protocol."""

    def __init__(self, dtc_at: Optional[int] = None) -> None:
        self.i = -1  # advances once per sampled row (on the first channel read)
        self.dtc_at = dtc_at

    def supported(self):
        return set(live.DEFAULT_CHANNELS_BY_CMD.keys())

    def query_value(self, command_name: str) -> Optional[float]:
        if command_name == "RPM":
            self.i += 1
        i = max(0, self.i)
        if command_name == "BAROMETRIC_PRESSURE":
            return 100.0
        if command_name == "INTAKE_PRESSURE":  # MAP ramps 100 -> 180 kPa
            return min(180.0, 100.0 + 2.0 * i)
        if command_name == "RPM":
            return 800.0 + 10.0 * i
        if command_name == "COOLANT_TEMP":
            return 60.0 + 0.5 * i
        if command_name == "SPEED":
            return float(i)
        if command_name == "ENGINE_LOAD":
            return 30.0 + (i % 5)
        return 0.0

    def get_dtcs(self) -> List[Tuple[str, str]]:
        if self.dtc_at is not None and self.i >= self.dtc_at:
            return [("P0301", "Cylinder 1 Misfire Detected")]
        return []

    def status(self) -> str:
        return "Car Connected"

    def protocol(self) -> str:
        return "ISO 15765-4 (CAN 11/500)"


def _logger(conn, tmp_path, **kw):
    return live.LiveLogger(
        conn,
        live.build_channels(conn.supported()),
        str(tmp_path),
        sample_rate_hz=5.0,
        clock=FakeClock(0.2),
        sleep=lambda _s: None,
        **kw,
    )


def test_session_roundtrips_through_core(tmp_path):
    conn = FakeOBD()
    channels = live.build_channels(conn.supported())
    names = {c.name for c in channels}
    assert "Boost (derived)" in names  # derived channel offered

    logger = _logger(conn, tmp_path)
    result = logger.run(duration_s=8.0, session_name="sess")
    assert result.sample_count > 20

    # The session file must parse back through the dependency-free core.
    mlog = parse.parse_measuring_log(result.session_file)
    parsed_names = {c.name for c in mlog.channels}
    assert "Engine RPM" in parsed_names
    assert "Boost (derived)" in parsed_names
    assert "Marker" not in parsed_names  # marker column is not a channel

    boost = mlog.channel("Boost (derived)")
    assert boost.unit == "kPa"
    # Boost = MAP(100..180) - Baro(100) -> climbs from 0 to ~80.
    assert boost.max is not None and boost.max > 50
    assert boost.min is not None and boost.min <= 1.0


def test_threshold_trigger_writes_capture(tmp_path):
    conn = FakeOBD()
    logger = _logger(conn, tmp_path, buffer_before_s=2.0, buffer_after_s=2.0)
    trigger = live.Trigger(thresholds=[{"channel": "Boost (derived)", "op": ">", "value": 50}])
    result = logger.run(duration_s=12.0, trigger=trigger, session_name="sess")

    assert result.captures, "threshold should have produced a capture"
    cap = result.captures[0]
    assert cap.trigger_kind == "threshold"

    import os

    assert os.path.isfile(cap.file)
    assert "EVENT" in os.path.basename(cap.file)

    # The capture round-trips and includes pre-trigger context (buffer_before).
    cmlog = parse.parse_measuring_log(cap.file)
    boost = cmlog.channel("Boost (derived)")
    assert boost is not None
    t0 = cmlog.raw_series["Boost (derived)"]["time"][0]
    assert t0 < cap.trigger_time  # context from BEFORE the trigger is present


def test_new_dtc_trigger_fires(tmp_path):
    conn = FakeOBD(dtc_at=10)
    logger = _logger(conn, tmp_path, buffer_before_s=1.0, buffer_after_s=1.0, dtc_poll_s=1.0)
    trigger = live.Trigger(on_new_dtc=True)
    result = logger.run(duration_s=12.0, trigger=trigger, session_name="sess")

    assert any(c.trigger_kind == "dtc" for c in result.captures)
    assert ("P0301", "Cylinder 1 Misfire Detected") in result.dtcs


def test_read_dtcs_surfaces_codes(tmp_path):
    conn = FakeOBD(dtc_at=-1)  # report immediately
    dtcs = live.read_dtcs(conn)
    assert dtcs == [("P0301", "Cylinder 1 Misfire Detected")]


def test_snapshot_returns_supported_values(tmp_path):
    conn = FakeOBD()
    snap = live.snapshot(conn)
    assert "Engine RPM" in snap
    assert "Boost (derived)" in snap
    assert snap["Barometric Pressure"] == 100.0
