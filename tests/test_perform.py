"""Tests for the performance-analysis module."""

from __future__ import annotations

from vcds_core import parse, perform


def _accel_log(tmp_path):
    # Speed 0 -> 100 km/h linearly over 5 s; RPM 1000 -> 4000; boost constant.
    rows = ["TIME,Engine RPM,Vehicle Speed,Boost (derived)", "s,/min,km/h,kPa"]
    n = 51
    for k in range(n):
        t = k * 0.1
        rpm = 1000 + 600 * t
        speed = 20 * t
        rows.append(f"{t:.1f},{rpm:.0f},{speed:.2f},80")
    path = tmp_path / "pull.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return parse.parse_measuring_log(str(path))


def test_acceleration_run_timing(tmp_path):
    log = _accel_log(tmp_path)
    runs = perform.find_acceleration_runs(log, 0, 100)
    assert runs
    assert abs(runs[0].elapsed_s - 5.0) < 0.25
    assert runs[0].unit == "km/h"


def test_standard_runs_metric(tmp_path):
    log = _accel_log(tmp_path)
    runs = perform.standard_accel_runs(log)
    assert any(abs(r.from_speed) < 1e-6 and abs(r.to_speed - 100) < 1e-6 for r in runs)


def test_detect_pulls(tmp_path):
    log = _accel_log(tmp_path)
    pulls = perform.detect_pulls(log, min_rpm_rise=1500, min_duration=1.0)
    assert len(pulls) == 1
    p = pulls[0]
    assert p.rpm_start < 1100 and p.rpm_end > 3900
    assert p.peak_speed is not None and p.peak_speed > 90
    assert p.peak_boost == 80


def test_estimate_power_positive(tmp_path):
    log = _accel_log(tmp_path)
    est = perform.estimate_power(log, mass_kg=1800)
    assert est is not None
    assert est.peak_hp > 50  # a 0-100 in 5s on 1800kg is a lot of power
    assert est.peak_torque_nm is not None and est.peak_torque_nm > 0
    assert est.peak_torque_rpm is not None


def test_no_speed_channel_returns_empty(tmp_path):
    path = tmp_path / "nospeed.csv"
    path.write_text("TIME,Coolant Temp\ns,°C\n0,80\n1,82\n2,84\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    assert perform.find_acceleration_runs(log, 0, 100) == []
    assert perform.estimate_power(log, 1800) is None
