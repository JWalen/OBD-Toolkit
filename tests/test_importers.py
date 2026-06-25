"""Tests for generic-app CSV importers (Torque / OBD Fusion / FORScan style)."""

from __future__ import annotations

from vcds_core import importers, parse


def test_torque_timestamp_import(tmp_path):
    content = (
        "Device Time,Longitude,Latitude,Engine RPM(rpm),Speed (OBD)(km/h),Coolant Temp(°C)\n"
        "2026-06-25 14:30:00,-93.1,44.9,800,0,80\n"
        "2026-06-25 14:30:01,-93.1,44.9,1200,10,82\n"
        "2026-06-25 14:30:02,-93.1,44.9,2000,30,84\n"
        "2026-06-25 14:30:03,-93.1,44.9,2500,45,86\n"
    )
    path = tmp_path / "torque.csv"
    path.write_text(content, encoding="utf-8")
    log = importers.import_generic_csv(str(path))

    names = {c.name for c in log.channels}
    assert "Engine RPM" in names
    assert "Speed (OBD)" in names   # name kept, unit parsed out
    assert "Coolant Temp" in names
    assert log.channel("Engine RPM").unit == "rpm"
    assert log.channel("Coolant Temp").unit == "°C"
    # time derived from the timestamp column -> ~3 s span
    assert log.duration_s is not None and abs(log.duration_s - 3.0) < 0.01
    assert log.format_guess == "generic_csv"
    # speed must NOT have been mistaken for the time axis
    assert log.channel("Speed (OBD)").max == 45


def test_obd_fusion_seconds_import(tmp_path):
    content = (
        "Time (sec),Engine RPM (rpm),Boost (psi)\n"
        "0.0,820,0.1\n0.5,1500,2.0\n1.0,3000,8.5\n1.5,4200,14.0\n"
    )
    path = tmp_path / "fusion.csv"
    path.write_text(content, encoding="utf-8")
    log = importers.import_generic_csv(str(path))
    assert log.channel("Engine RPM").unit == "rpm"
    assert log.channel("Boost").unit == "psi"
    assert abs(log.duration_s - 1.5) < 1e-6


def test_open_measuring_file_prefers_vcds(samples_dir):
    # a real VCDS log should still go through the VCDS parser
    log = importers.open_measuring_file(samples_dir["advanced"])
    assert log.format_guess == "advanced_uds"


def test_open_measuring_file_falls_back_to_generic(tmp_path):
    content = "Time (sec),MAF (g/s)\n0,2.1\n1,4.5\n2,9.0\n"
    path = tmp_path / "g.csv"
    path.write_text(content, encoding="utf-8")
    log = importers.open_measuring_file(str(path))
    assert log.channel("MAF") is not None
