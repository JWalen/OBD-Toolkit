"""Tests for trip / fuel-economy and battery analysis."""

from __future__ import annotations

from vcds_core import parse, trip


def test_fuel_economy_from_fuel_rate(tmp_path):
    # 100 km/h for 36 s = 1 km; 9 L/h for 36 s = 0.09 L -> 9 L/100km
    rows = ["TIME,Vehicle Speed,Fuel Rate", "s,km/h,L/h"]
    for k in range(37):
        rows.append(f"{k},100,9")
    path = tmp_path / "fr.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    econ = trip.fuel_economy(log)
    assert econ is not None and econ.source == "fuel_rate"
    assert abs(econ.distance_km - 1.0) < 0.05
    assert abs(econ.l_per_100km - 9.0) < 0.3
    assert econ.mpg_us and 24 < econ.mpg_us < 28


def test_fuel_economy_from_maf(tmp_path):
    rows = ["TIME,Vehicle Speed,MAF", "s,km/h,g/s"]
    for k in range(31):
        rows.append(f"{k},80,5")
    path = tmp_path / "maf.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    econ = trip.fuel_economy(log)
    assert econ is not None and econ.source == "maf"
    assert econ.l_per_100km and econ.l_per_100km > 0


def test_no_fuel_source_returns_none(tmp_path):
    path = tmp_path / "nofuel.csv"
    path.write_text("TIME,Vehicle Speed\ns,km/h\n0,50\n1,55\n2,60\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    assert trip.fuel_economy(log) is None


def test_battery_analysis(tmp_path):
    rows = ["TIME,Control Module Voltage", "s,V",
            "0,12.4", "1,9.5", "2,14.1", "3,14.2", "4,14.0"]
    path = tmp_path / "bat.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = parse.parse_measuring_log(str(path))
    bat = trip.battery_analysis(log)
    assert bat is not None
    assert abs(bat.cranking_v - 9.5) < 1e-6
    assert bat.charging_v is not None and bat.charging_v > 13.5
