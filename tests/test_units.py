"""Tests for unit conversion."""

from __future__ import annotations

from vcds_core import units


def test_imperial_conversions():
    assert units.convert(100, "°C", units.IMPERIAL) == (212.0, "°F")
    v, u = units.convert(100, "km/h", units.IMPERIAL)
    assert abs(v - 62.1371) < 1e-3 and u == "mph"
    v, u = units.convert(100, "kPa", units.IMPERIAL)
    assert abs(v - 14.5038) < 1e-3 and u == "psi"
    v, u = units.convert(1000, "mbar", units.IMPERIAL)
    assert u == "psi" and abs(v - 14.5038) < 1e-2


def test_metric_conversions():
    v, u = units.convert(212, "°F", units.METRIC)
    assert abs(v - 100.0) < 1e-6 and u == "°C"
    v, u = units.convert(60, "mph", units.METRIC)
    assert abs(v - 96.56) < 0.1 and u == "km/h"
    v, u = units.convert(14.5038, "psi", units.METRIC)
    assert abs(v - 100.0) < 0.1 and u == "kPa"


def test_as_logged_is_noop():
    assert units.convert(50.0, "kPa", units.AS_LOGGED) == (50.0, "kPa")
    assert units.convert(50.0, "kPa", "") == (50.0, "kPa")


def test_unknown_unit_passthrough():
    assert units.convert(5.0, "g/s", units.IMPERIAL) == (5.0, "g/s")


def test_none_value():
    assert units.convert(None, "°C", units.IMPERIAL) == (None, "°C")


def test_convert_label():
    assert units.convert_label("°C", units.IMPERIAL) == "°F"
    assert units.convert_label("g/s", units.IMPERIAL) == "g/s"
