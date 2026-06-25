"""Tests for VIN decoding."""

from __future__ import annotations

from vcds_core import vin


def test_decode_vag():
    info = vin.decode_vin("WAUZZZ8K9BA123456")
    assert info.make == "Audi"
    assert info.brand_profile == "vag"
    assert info.year == 2011  # 10th char 'B'


def test_decode_ford():
    info = vin.decode_vin("1FTFW1ET5DFC12345")
    assert info.make == "Ford"
    assert info.brand_profile == "ford"
    assert info.year == 2013  # 'D'


def test_decode_unknown_is_generic():
    info = vin.decode_vin("ZZZ12345678901234")
    assert info.brand_profile == "generic"
    assert info.make is None


def test_model_year_codes():
    assert vin.model_year("A") == 2010
    assert vin.model_year("B") == 2011
    assert vin.model_year("1") == 2031
    assert vin.model_year("O") is None  # not a valid year code
