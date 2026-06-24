"""Unit tests for the raw pyserial ELM327 driver (no hardware).

A fake serial object returns canned ELM327 responses so the AT/PID/DTC decoding
is verified deterministically.
"""

from __future__ import annotations

from vcds_core import parse
from vcds_obd import live


class FakeSerial:
    """Minimal pyserial stand-in: maps an uppercased command to a response."""

    def __init__(self, responses: dict):
        self.responses = responses
        self._last = ""

    def reset_input_buffer(self):
        pass

    def write(self, data: bytes):
        self._last = data.decode("ascii").strip().upper()

    def read_until(self, expected=b">"):
        resp = self.responses.get(self._last, "NO DATA")
        return (resp + " \r\r>").encode("ascii")

    def close(self):
        pass


def _fake_conn():
    responses = {
        "ATZ": "ELM327 v1.5",
        "ATE0": "OK",
        "ATL0": "OK",
        "ATS0": "OK",
        "ATSP0": "OK",
        "ATDPN": "A6",
        "010C": "41 0C 1A F8",  # RPM = (0x1AF8)/4 = 1726
        "0105": "41 05 5A",     # Coolant = 0x5A - 40 = 50
        "010B": "41 0B 96",     # MAP = 0x96 = 150 kPa
        "0133": "41 33 64",     # Baro = 0x64 = 100 kPa
        "010D": "41 0D 28",     # Speed = 40
        "03": "43 01 33 00 00", # one DTC: P0133
        "04": "44",
    }
    return live.RawELM327Connection(serial_obj=FakeSerial(responses))


def test_raw_pid_decoding():
    conn = _fake_conn()
    assert conn.query_value("RPM") == 1726.0
    assert conn.query_value("COOLANT_TEMP") == 50.0
    assert conn.query_value("INTAKE_PRESSURE") == 150.0
    assert conn.query_value("BAROMETRIC_PRESSURE") == 100.0
    assert conn.query_value("VEHICLE_SPEED" if False else "SPEED") == 40.0


def test_raw_supported_fallback_and_channels():
    conn = _fake_conn()
    # The probe (0100…) isn't answered, so it falls back to the full known set.
    supported = conn.supported()
    assert "RPM" in supported and "INTAKE_PRESSURE" in supported
    channels = live.build_channels(supported)
    names = {c.name for c in channels}
    assert "Boost (derived)" in names


def test_raw_derived_boost_snapshot():
    conn = _fake_conn()
    snap = live.snapshot(conn)
    # Boost (derived) = MAP(150) - Baro(100) = 50 kPa
    assert snap["Boost (derived)"] == 50.0


def test_raw_dtc_decode():
    conn = _fake_conn()
    assert conn.get_dtcs() == [("P0133", "")]
    assert conn.clear_dtcs() is True


def test_raw_session_roundtrips(tmp_path):
    conn = _fake_conn()
    channels = live.build_channels(conn.supported())

    class Clock:
        def __init__(self, dt):
            self.dt = dt
            self.t = -dt

        def __call__(self):
            self.t += self.dt
            return self.t

    logger = live.LiveLogger(
        conn, channels, str(tmp_path), sample_rate_hz=5.0, clock=Clock(0.2), sleep=lambda _s: None
    )
    result = logger.run(duration_s=4.0, session_name="raw")
    mlog = parse.parse_measuring_log(result.session_file)
    boost = mlog.channel("Boost (derived)")
    assert boost is not None and boost.first == 50.0
