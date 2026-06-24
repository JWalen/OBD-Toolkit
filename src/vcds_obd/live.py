"""Live data capture from a generic ELM327 OBD-II adapter.

Design notes
------------
* A generic ELM327 exposes ONLY the standard OBD-II PIDs and is blind to the
  VAG-specific channels VCDS reads. We are honest about that limit.
* The OBD library is hidden behind a tiny :class:`Connection` protocol so the
  capture engine has no hard dependency on ``obd``/``pyserial`` and can be
  driven by a fake in tests (no hardware in CI).
* Sessions are written in the SAME flat CSV layout that :mod:`vcds_core` parses
  (a Marker column, a TIME column in seconds-from-start, then one column per
  channel, with a channel-name header row and a unit header row). A captured
  session therefore feeds straight back into every existing analysis tool.

The console entry point ``vcds-obd-log`` records a capped session to disk.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

# Hard safety cap shared with the MCP run_obd_session tool.
MAX_SESSION_SECONDS = 300


# --------------------------------------------------------------------------- #
# Channel model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LiveChannel:
    """One logged channel.

    ``command_name`` is the python-OBD command attribute (e.g. ``"RPM"``) for a
    real PID, or ``None`` for a derived channel computed from others.
    """

    name: str
    unit: str
    command_name: Optional[str] = None
    derived_from: Optional[Tuple[str, str]] = None  # (minuend, subtrahend) channel names


# Default PID set. The DERIVED boost channel = INTAKE_PRESSURE - BAROMETRIC.
DEFAULT_CHANNELS: List[LiveChannel] = [
    LiveChannel("Engine RPM", "rpm", "RPM"),
    LiveChannel("Vehicle Speed", "km/h", "SPEED"),
    LiveChannel("Engine Load", "%", "ENGINE_LOAD"),
    LiveChannel("Coolant Temp", "°C", "COOLANT_TEMP"),
    LiveChannel("Intake Air Temp", "°C", "INTAKE_TEMP"),
    LiveChannel("MAF", "g/s", "MAF"),
    LiveChannel("Intake MAP", "kPa", "INTAKE_PRESSURE"),
    LiveChannel("Barometric Pressure", "kPa", "BAROMETRIC_PRESSURE"),
    LiveChannel("Short Fuel Trim 1", "%", "SHORT_FUEL_TRIM_1"),
    LiveChannel("Long Fuel Trim 1", "%", "LONG_FUEL_TRIM_1"),
    LiveChannel("Throttle Position", "%", "THROTTLE_POS"),
    LiveChannel("Timing Advance", "°", "TIMING_ADVANCE"),
    # Derived: usable boost figure for the supercharged 3.0T = MAP - ambient.
    LiveChannel(
        "Boost (derived)",
        "kPa",
        command_name=None,
        derived_from=("Intake MAP", "Barometric Pressure"),
    ),
]

DEFAULT_CHANNELS_BY_NAME = {c.name: c for c in DEFAULT_CHANNELS}
DEFAULT_CHANNELS_BY_CMD = {c.command_name: c for c in DEFAULT_CHANNELS if c.command_name}


# --------------------------------------------------------------------------- #
# Connection protocol — the only seam between us and the OBD hardware/library.
# --------------------------------------------------------------------------- #


class Connection(Protocol):
    def supported(self) -> "set[str]":
        """Set of supported python-OBD command names."""

    def query_value(self, command_name: str) -> Optional[float]:
        """Latest value for a command, stripped to a plain float (or None)."""

    def get_dtcs(self) -> List[Tuple[str, str]]:
        """Current stored DTCs as (code, description) tuples."""

    def status(self) -> str: ...

    def protocol(self) -> str: ...


def build_channels(
    supported_names: "set[str]",
    selected: Optional[Sequence[str]] = None,
) -> List[LiveChannel]:
    """Resolve the channels to log, restricted to PIDs the ECU supports.

    Args:
        supported_names: command names the connection reports as supported.
        selected: optional subset of channel names or command names to keep.

    Returns:
        Ordered channels. A derived channel is only included when both of its
        source channels are supported.
    """
    chosen: List[LiveChannel] = []
    sel_lower = {s.lower() for s in selected} if selected else None

    for ch in DEFAULT_CHANNELS:
        if sel_lower is not None and not (
            ch.name.lower() in sel_lower
            or (ch.command_name and ch.command_name.lower() in sel_lower)
        ):
            continue
        if ch.command_name is not None:
            if ch.command_name in supported_names:
                chosen.append(ch)
        else:
            # derived: require both sources
            a, b = ch.derived_from  # type: ignore[misc]
            ca = DEFAULT_CHANNELS_BY_NAME.get(a)
            cb = DEFAULT_CHANNELS_BY_NAME.get(b)
            if ca and cb and ca.command_name in supported_names and cb.command_name in supported_names:
                chosen.append(ch)
    return chosen


def read_row(conn: Connection, channels: Sequence[LiveChannel]) -> Dict[str, Optional[float]]:
    """Read one sample for every channel, computing derived channels last."""
    values: Dict[str, Optional[float]] = {}
    for ch in channels:
        if ch.command_name is not None:
            values[ch.name] = conn.query_value(ch.command_name)
    for ch in channels:
        if ch.derived_from is not None:
            a, b = ch.derived_from
            va, vb = values.get(a), values.get(b)
            values[ch.name] = (va - vb) if (va is not None and vb is not None) else None
    return values


# --------------------------------------------------------------------------- #
# Trigger configuration
# --------------------------------------------------------------------------- #


@dataclass
class Trigger:
    """Event-capture trigger: thresholds and/or "any new DTC"."""

    thresholds: List[dict] = field(default_factory=list)  # {channel, op, value}
    on_new_dtc: bool = False

    @classmethod
    def from_obj(cls, obj: Optional[dict]) -> Optional["Trigger"]:
        if not obj:
            return None
        return cls(
            thresholds=list(obj.get("thresholds", [])),
            on_new_dtc=bool(obj.get("on_new_dtc", False)),
        )


_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def _threshold_hit(trigger: Trigger, values: Dict[str, Optional[float]]) -> Optional[str]:
    for rule in trigger.thresholds:
        chan_q = str(rule.get("channel", "")).lower()
        op = rule.get("op", ">")
        thr = float(rule.get("value"))
        fn = _OPS.get(op)
        if fn is None:
            continue
        for name, v in values.items():
            if v is None:
                continue
            if chan_q and chan_q not in name.lower():
                continue
            if fn(v, thr):
                return f"{name} {op} {thr} (={v:g})"
    return None


# --------------------------------------------------------------------------- #
# CSV writing — flat layout identical to what vcds_core.parse expects.
# --------------------------------------------------------------------------- #


def _fmt(v: Optional[float]) -> str:
    return "" if v is None else f"{v:g}"


def write_measuring_csv(
    path: str,
    channels: Sequence[LiveChannel],
    rows: Sequence[Tuple[str, float, Dict[str, Optional[float]]]],
) -> None:
    """Write rows in the flat measuring-log layout vcds_core parses.

    Args:
        path: Output CSV path.
        channels: Ordered channels (defines the column order).
        rows: Each row is ``(marker, time_seconds, {channel_name: value})``.
    """
    names = ["Marker", "TIME"] + [c.name for c in channels]
    units = ["", "s"] + [c.unit for c in channels]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(names)
        w.writerow(units)
        for marker, t, values in rows:
            w.writerow([marker, f"{t:.3f}"] + [_fmt(values.get(c.name)) for c in channels])


# --------------------------------------------------------------------------- #
# Capture results
# --------------------------------------------------------------------------- #


@dataclass
class CaptureResult:
    file: str
    trigger_kind: str  # "dtc" or "threshold"
    trigger_time: float
    reason: str


@dataclass
class SessionResult:
    session_file: str
    sample_count: int
    duration_s: float
    channels: List[str]
    dtcs: List[Tuple[str, str]]
    captures: List[CaptureResult] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# The capture engine
# --------------------------------------------------------------------------- #


class LiveLogger:
    """Continuously samples a :class:`Connection` and writes a flat-layout CSV.

    Maintains a rolling ring buffer of the last ``buffer_before_s`` seconds so a
    triggered event capture includes context from BEFORE the trigger fired.
    """

    def __init__(
        self,
        conn: Connection,
        channels: Sequence[LiveChannel],
        logs_dir: str,
        sample_rate_hz: float = 5.0,
        buffer_before_s: float = 10.0,
        buffer_after_s: float = 10.0,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        dtc_poll_s: float = 1.0,
    ) -> None:
        self.conn = conn
        self.channels = list(channels)
        self.logs_dir = logs_dir
        self.sample_rate_hz = max(0.1, sample_rate_hz)
        self.period = 1.0 / self.sample_rate_hz
        self.buffer_before_s = buffer_before_s
        self.buffer_after_s = buffer_after_s
        # Resolve against the module's ``time`` at call-time so tests can patch it.
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.dtc_poll_s = dtc_poll_s
        self._stop = threading.Event()

    def stop(self) -> None:
        """Request the running capture loop to finish early (thread-safe)."""
        self._stop.set()

    def run(
        self,
        duration_s: float,
        trigger: Optional[Trigger] = None,
        session_name: Optional[str] = None,
        on_sample: Optional[Callable[[float, Dict[str, Optional[float]], str], None]] = None,
    ) -> SessionResult:
        """Record for a capped duration, writing a session CSV (+ any captures).

        Args:
            duration_s: How long to record (hard-capped at MAX_SESSION_SECONDS).
            trigger: Optional event-capture trigger.
            session_name: Base file name (without extension); a timestamped
                default is generated when omitted.

        Returns:
            A :class:`SessionResult` describing the session file and captures.
        """
        os.makedirs(self.logs_dir, exist_ok=True)
        duration_s = min(float(duration_s), float(MAX_SESSION_SECONDS))

        # For an Async connection, watch the selected commands up front so the
        # background poller has values ready; a no-op for blocking/raw adapters.
        watcher = getattr(self.conn, "watch", None)
        if callable(watcher):
            try:
                watcher([c.command_name for c in self.channels if c.command_name])
            except Exception:  # noqa: BLE001
                pass

        if session_name is None:
            session_name = "OBD_" + time.strftime("%Y%m%d_%H%M%S")
        session_path = os.path.join(self.logs_dir, session_name + ".CSV")

        ring_len = max(1, int(self.buffer_before_s * self.sample_rate_hz) + 1)
        ring: deque = deque(maxlen=ring_len)
        all_rows: List[Tuple[str, float, Dict[str, Optional[float]]]] = []

        known_dtcs = set(self._safe_dtcs())
        captures: List[CaptureResult] = []

        # Active event capture (if any) collecting post-trigger rows.
        cap_rows: Optional[List[Tuple[str, float, Dict[str, Optional[float]]]]] = None
        cap_end = 0.0
        cap_info: Optional[CaptureResult] = None
        last_dtc_poll = -1e9

        start = self.clock()
        n = 0
        while True:
            now = self.clock()
            t = now - start
            if t > duration_s or self._stop.is_set():
                break

            values = read_row(self.conn, self.channels)
            marker = ""
            fired_reason: Optional[str] = None
            fired_kind = ""

            # --- threshold trigger ---
            if trigger is not None and cap_rows is None and trigger.thresholds:
                hit = _threshold_hit(trigger, values)
                if hit:
                    fired_reason, fired_kind = hit, "threshold"

            # --- new-DTC trigger (polled, not every tick) ---
            if (
                trigger is not None
                and cap_rows is None
                and trigger.on_new_dtc
                and (t - last_dtc_poll) >= self.dtc_poll_s
            ):
                last_dtc_poll = t
                current = set(self._safe_dtcs())
                new = current - known_dtcs
                known_dtcs |= current
                if new:
                    code, desc = sorted(new)[0]
                    fired_reason, fired_kind = f"New DTC {code} ({desc})", "dtc"

            if fired_reason is not None:
                marker = "TRIGGER"
                cap_rows = list(ring)  # buffer_before context
                cap_end = t + self.buffer_after_s
                cap_name = f"{session_name}_EVENT{len(captures) + 1}_{fired_kind}.CSV"
                cap_info = CaptureResult(
                    file=os.path.join(self.logs_dir, cap_name),
                    trigger_kind=fired_kind,
                    trigger_time=t,
                    reason=fired_reason,
                )

            row = (marker, t, values)
            ring.append(row)
            all_rows.append(row)
            if on_sample is not None:
                on_sample(t, values, marker)
            if cap_rows is not None:
                cap_rows.append(row)
                if t >= cap_end:
                    write_measuring_csv(cap_info.file, self.channels, cap_rows)  # type: ignore[arg-type]
                    captures.append(cap_info)  # type: ignore[arg-type]
                    cap_rows = None
                    cap_info = None

            n += 1
            self.sleep(self.period)

        # finalize an in-progress capture (session ended before buffer_after elapsed)
        if cap_rows is not None and cap_info is not None:
            write_measuring_csv(cap_info.file, self.channels, cap_rows)
            captures.append(cap_info)

        write_measuring_csv(session_path, self.channels, all_rows)
        final_dtcs = self._safe_dtcs()
        duration = all_rows[-1][1] if all_rows else 0.0
        return SessionResult(
            session_file=session_path,
            sample_count=len(all_rows),
            duration_s=duration,
            channels=[c.name for c in self.channels],
            dtcs=final_dtcs,
            captures=captures,
        )

    def _safe_dtcs(self) -> List[Tuple[str, str]]:
        try:
            return list(self.conn.get_dtcs())
        except Exception:  # noqa: BLE001 - DTC reads can fail mid-session
            return []


def read_dtcs(conn: Connection) -> List[Tuple[str, str]]:
    """Return current stored DTCs as (code, description) tuples."""
    return list(conn.get_dtcs())


def snapshot(conn: Connection, channels: Optional[Sequence[LiveChannel]] = None) -> Dict[str, Optional[float]]:
    """One-shot read of the current values for the given (or supported) channels."""
    if channels is None:
        channels = build_channels(conn.supported())
    return read_row(conn, channels)


# --------------------------------------------------------------------------- #
# Real ELM327 connection adapters (library first, raw AT as last resort).
# --------------------------------------------------------------------------- #


def _strip(value) -> Optional[float]:
    """Strip a python-OBD Pint quantity (or anything) to a plain float."""
    if value is None:
        return None
    mag = getattr(value, "magnitude", None)
    try:
        return float(mag if mag is not None else value)
    except (TypeError, ValueError):
        return None


class PyOBDConnection:
    """Adapter around python-OBD (``obd.Async`` preferred, ``obd.OBD`` fallback)."""

    def __init__(self, port: Optional[str] = None, baud: Optional[int] = None, prefer_async: bool = True):
        import obd  # lazy: keeps the dependency out of import-time/CI

        self._obd = obd
        self._is_async = False
        conn = None
        kwargs = {}
        if port:
            kwargs["portstr"] = port
        if baud:
            kwargs["baudrate"] = int(baud)

        if prefer_async:
            try:
                conn = obd.Async(**kwargs)
                self._is_async = True
            except Exception:  # noqa: BLE001 - fall back to blocking
                conn = None
        if conn is None:
            conn = obd.OBD(**kwargs)
            self._is_async = False
        self._conn = conn

    def watch(self, command_names: Sequence[str]) -> None:
        if not self._is_async:
            return
        for name in command_names:
            cmd = getattr(self._obd.commands, name, None)
            if cmd is not None:
                try:
                    self._conn.watch(cmd)
                except Exception:  # noqa: BLE001
                    pass
        try:
            self._conn.start()
        except Exception:  # noqa: BLE001
            pass

    def supported(self) -> "set[str]":
        try:
            return {c.name for c in self._conn.supported_commands}
        except Exception:  # noqa: BLE001
            return set()

    def query_value(self, command_name: str) -> Optional[float]:
        cmd = getattr(self._obd.commands, command_name, None)
        if cmd is None:
            return None
        try:
            resp = self._conn.query(cmd)
        except Exception:  # noqa: BLE001
            return None
        if resp is None or resp.is_null():
            return None
        return _strip(resp.value)

    def get_dtcs(self) -> List[Tuple[str, str]]:
        cmd = getattr(self._obd.commands, "GET_DTC", None)
        if cmd is None:
            return []
        resp = self._conn.query(cmd)
        if resp is None or resp.is_null() or not resp.value:
            return []
        return [(str(code), str(desc)) for code, desc in resp.value]

    def clear_dtcs(self) -> bool:
        """Clear stored DTCs. EXPLICIT user action only — never call automatically."""
        cmd = getattr(self._obd.commands, "CLEAR_DTC", None)
        if cmd is None:
            return False
        resp = self._conn.query(cmd, force=True)
        return resp is not None and not resp.is_null()

    def status(self) -> str:
        try:
            return str(self._conn.status())
        except Exception:  # noqa: BLE001
            return "unknown"

    def protocol(self) -> str:
        try:
            return str(self._conn.protocol_name())
        except Exception:  # noqa: BLE001
            return "unknown"

    def is_connected(self) -> bool:
        try:
            return bool(self._conn.is_connected())
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


class RawELM327Connection:
    """Last-resort raw ELM327 driver over pyserial (AT init + mode-01 PIDs).

    Use only when python-OBD cannot initialise the adapter. This speaks ELM327
    AT commands directly and decodes the standard OBD-II PIDs in our default set.
    VAG-specific channels remain unavailable — a generic ELM327 cannot read them.

    The serial object is injectable (``serial_obj``) so the protocol decoding can
    be unit-tested without hardware.
    """

    # name -> (mode-01 PID hex, data byte count, decoder)
    _PIDS = {
        "ENGINE_LOAD": ("04", 1, lambda b: b[0] * 100.0 / 255.0),
        "COOLANT_TEMP": ("05", 1, lambda b: b[0] - 40.0),
        "SHORT_FUEL_TRIM_1": ("06", 1, lambda b: (b[0] - 128) * 100.0 / 128.0),
        "LONG_FUEL_TRIM_1": ("07", 1, lambda b: (b[0] - 128) * 100.0 / 128.0),
        "INTAKE_PRESSURE": ("0B", 1, lambda b: float(b[0])),
        "RPM": ("0C", 2, lambda b: (b[0] * 256 + b[1]) / 4.0),
        "SPEED": ("0D", 1, lambda b: float(b[0])),
        "TIMING_ADVANCE": ("0E", 1, lambda b: b[0] / 2.0 - 64.0),
        "INTAKE_TEMP": ("0F", 1, lambda b: b[0] - 40.0),
        "MAF": ("10", 2, lambda b: (b[0] * 256 + b[1]) / 100.0),
        "THROTTLE_POS": ("11", 1, lambda b: b[0] * 100.0 / 255.0),
        "BAROMETRIC_PRESSURE": ("33", 1, lambda b: float(b[0])),
    }

    def __init__(self, port: Optional[str] = None, baud: Optional[int] = None,
                 timeout: float = 1.0, serial_obj=None):
        if serial_obj is not None:
            self._ser = serial_obj
        else:
            import serial  # lazy: pyserial only needed for the raw path

            self._ser = serial.Serial(port, baudrate=int(baud or 38400), timeout=timeout)
        self._init_elm()

    # -- low-level transport ------------------------------------------------ #
    def _transact(self, cmd: str) -> str:
        try:
            self._ser.reset_input_buffer()
        except Exception:  # noqa: BLE001
            pass
        self._ser.write((cmd + "\r").encode("ascii"))
        raw = self._ser.read_until(b">")
        return raw.decode("ascii", errors="ignore")

    def _init_elm(self) -> None:
        for cmd in ("ATZ", "ATE0", "ATL0", "ATS0", "ATSP0"):
            try:
                self._transact(cmd)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _hex_bytes(text: str) -> List[int]:
        import re

        return [int(tok, 16) for tok in re.findall(r"\b[0-9A-Fa-f]{2}\b", text)]

    def _extract(self, text: str, resp_mode: int, pid: int, nbytes: int) -> Optional[List[int]]:
        toks = self._hex_bytes(text)
        for i in range(len(toks) - 1):
            if toks[i] == resp_mode and toks[i + 1] == pid:
                data = toks[i + 2 : i + 2 + nbytes]
                if len(data) == nbytes:
                    return data
        return None

    # -- Connection protocol ------------------------------------------------ #
    def supported(self) -> "set[str]":
        supported_pids: "set[int]" = set()
        for base in (0x00, 0x20, 0x40):
            data = self._extract(self._transact("01" + format(base, "02X")), 0x41, base, 4)
            if not data:
                continue
            bits = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
            for i in range(32):
                if bits & (1 << (31 - i)):
                    supported_pids.add(base + i + 1)
        names = {name for name, (ph, _n, _f) in self._PIDS.items() if int(ph, 16) in supported_pids}
        # If the probe yielded nothing (some clones refuse it), fall back to the
        # full known set; unsupported PIDs simply read as None at query time.
        return names or set(self._PIDS.keys())

    def query_value(self, command_name: str) -> Optional[float]:
        spec = self._PIDS.get(command_name)
        if spec is None:
            return None
        pidhex, nbytes, decode = spec
        data = self._extract(self._transact("01" + pidhex), 0x41, int(pidhex, 16), nbytes)
        if data is None:
            return None
        try:
            return float(decode(data))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _decode_dtc(b1: int, b2: int) -> str:
        letter = "PCBU"[(b1 & 0xC0) >> 6]
        return (
            f"{letter}{(b1 & 0x30) >> 4}{format(b1 & 0x0F, 'X')}"
            f"{format((b2 & 0xF0) >> 4, 'X')}{format(b2 & 0x0F, 'X')}"
        )

    def get_dtcs(self) -> List[Tuple[str, str]]:
        toks = self._hex_bytes(self._transact("03"))
        out: List[Tuple[str, str]] = []
        if 0x43 in toks:
            i = toks.index(0x43) + 1
            pairs = toks[i:]
            for j in range(0, len(pairs) - 1, 2):
                b1, b2 = pairs[j], pairs[j + 1]
                if b1 == 0 and b2 == 0:
                    continue
                out.append((self._decode_dtc(b1, b2), ""))
        return out

    def clear_dtcs(self) -> bool:
        """Clear stored DTCs. EXPLICIT user action only — never call automatically."""
        resp = self._transact("04")
        return "44" in resp or "OK" in resp.upper()

    def status(self) -> str:
        return "Raw ELM327 (pyserial)"

    def protocol(self) -> str:
        return self._transact("ATDPN").strip() or "unknown"

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:  # noqa: BLE001
            pass


def scan_ports() -> List[str]:
    """Discover candidate serial ports for an ELM327 adapter."""
    try:
        import obd

        return list(obd.scan_serial())
    except Exception:  # noqa: BLE001
        pass
    # pyserial fallback
    try:
        from serial.tools import list_ports

        return [p.device for p in list_ports.comports()]
    except Exception:  # noqa: BLE001
        return []


def connect(
    port: Optional[str] = None,
    baud: Optional[int] = None,
    prefer_async: bool = True,
    prefer: str = "library",
):
    """Connect to an ELM327, trying python-OBD first and raw AT as last resort.

    Args:
        port: Serial port (e.g. ``COM5``). Auto-scanned by the library if None.
        baud: Baud override for clones (38400 / 9600 / 115200).
        prefer_async: Use ``obd.Async`` when possible (falls back to blocking).
        prefer: ``"library"`` (default) tries python-OBD then falls back to the
            raw pyserial driver; ``"raw"`` forces the raw driver (needs a port).

    Returns:
        A connection implementing the :class:`Connection` protocol.
    """
    if prefer == "raw":
        return RawELM327Connection(port=port, baud=baud)
    try:
        return PyOBDConnection(port=port, baud=baud, prefer_async=prefer_async)
    except Exception:  # noqa: BLE001 - last-resort raw AT path
        if not port:
            raise
        return RawELM327Connection(port=port, baud=baud)


# --------------------------------------------------------------------------- #
# Console entry point
# --------------------------------------------------------------------------- #


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Log live ELM327 OBD-II data to a VCDS-compatible CSV.")
    p.add_argument("--port", help="Serial port (e.g. COM5). Default: auto-scan.")
    p.add_argument("--baud", type=int, help="Baud rate override (38400 / 9600 / 115200).")
    p.add_argument("--duration", type=float, default=30.0, help="Seconds to record (cap 300).")
    p.add_argument("--rate", type=float, default=5.0, help="Sample rate in Hz (default 5).")
    p.add_argument("--logs-dir", default=os.environ.get("VCDS_LOGS_DIR", r"C:\Ross-Tech\VCDS\Logs"))
    p.add_argument("--list-ports", action="store_true", help="List candidate ports and exit.")
    p.add_argument("--raw", action="store_true", help="Force the raw pyserial ELM327 driver.")
    args = p.parse_args(argv)

    if args.list_ports:
        ports = scan_ports()
        print("Candidate ports:" if ports else "No serial ports found.", file=sys.stderr)
        for port in ports:
            print(f"  {port}", file=sys.stderr)
        return 0

    try:
        conn = connect(port=args.port, baud=args.baud, prefer="raw" if args.raw else "library")
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to an ELM327 adapter: {exc}", file=sys.stderr)
        return 2

    channels = build_channels(conn.supported())
    if not channels:
        print("No supported OBD-II PIDs reported by the ECU.", file=sys.stderr)
        return 3

    logger = LiveLogger(conn, channels, args.logs_dir, sample_rate_hz=args.rate)
    print(f"Recording {args.duration:g}s at {args.rate:g} Hz -> {args.logs_dir}", file=sys.stderr)
    result = logger.run(args.duration)
    conn.close()
    print(f"Wrote {result.session_file} ({result.sample_count} samples).", file=sys.stderr)
    if result.dtcs:
        print(f"Stored DTCs: {result.dtcs}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
