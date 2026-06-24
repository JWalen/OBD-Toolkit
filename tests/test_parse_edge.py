"""Parser edge cases beyond the two canonical sample layouts."""

from __future__ import annotations

from vcds_core import parse


def _write(tmp_path, name, content, encoding="utf-8"):
    p = tmp_path / name
    p.write_text(content, encoding=encoding)
    return str(p)


def test_tab_delimited(tmp_path):
    path = _write(
        tmp_path,
        "tab.csv",
        "TIME\tEngine RPM\tCoolant Temp\ns\t/min\t°C\n0\t800\t20\n1\t1000\t21\n2\t1200\t22\n",
    )
    log = parse.parse_measuring_log(path)
    assert log.delimiter == "tab"
    assert {c.name for c in log.channels} == {"Engine RPM", "Coolant Temp"}
    assert log.channel("Engine RPM").unit == "/min"


def test_semicolon_comma_decimal_no_groups(tmp_path):
    path = _write(
        tmp_path,
        "semi.csv",
        "TIME;Boost Pressure;Coolant Temp\ns;mbar;°C\n0;1000,5;20,1\n0,2;1200,5;20,2\n0,4;1400,0;20,3\n",
    )
    log = parse.parse_measuring_log(path)
    assert log.delimiter == "semicolon"
    boost = log.channel("Boost Pressure")
    assert abs(boost.first - 1000.5) < 1e-6
    assert abs(boost.max - 1400.0) < 1e-6


def test_single_header_row_no_units(tmp_path):
    path = _write(
        tmp_path,
        "flat.csv",
        "TIME,Engine RPM,Vehicle Speed\n0,800,0\n1,1000,5\n2,1200,10\n",
    )
    log = parse.parse_measuring_log(path)
    assert log.channel("Engine RPM").unit == ""
    assert log.channel("Vehicle Speed").last == 10.0


def test_utf16_like_cp1252_fallback(tmp_path):
    # cp1252-encoded degree sign decodes via the fallback chain.
    path = tmp_path / "cp.csv"
    path.write_bytes("TIME,Coolant Temp\ns,\xb0C\n0,20\n1,21\n2,22\n".encode("cp1252"))
    log = parse.parse_measuring_log(str(path))
    assert log.channel("Coolant Temp") is not None


def test_classify_file(samples_dir):
    assert parse.classify_file(samples_dir["autoscan"]) == "autoscan"
    assert parse.classify_file(samples_dir["advanced"]) == "measuring_log"
    assert parse.classify_file(samples_dir["classic"]) == "measuring_log"


def test_threshold_ops(tmp_path):
    path = _write(tmp_path, "ops.csv", "TIME,V\ns,x\n0,1\n1,5\n2,10\n3,2\n")
    log = parse.parse_measuring_log(path)
    cases = [(">", 4, True), ("<", 2, True), (">=", 10, True), ("<=", 1, True), ("==", 5, True), (">", 999, False)]
    for op, thr, expect in cases:
        events = parse.find_events(log, rules=[{"channel": "V", "op": op, "value": thr}])
        assert bool(events) is expect, f"op={op} thr={thr}"


def test_events_sorted_by_time(tmp_path):
    path = _write(
        tmp_path,
        "ev.csv",
        "TIME,Boost (specified),Boost (actual),Misfire Count\ns,mbar,mbar,count\n"
        "0,1000,1000,0\n1,1200,800,0\n2,1400,1390,1\n3,1500,1495,3\n",
    )
    log = parse.parse_measuring_log(path)
    events = parse.find_events(log)
    times = [e.time for e in events if e.time is not None]
    assert times == sorted(times)
    assert any(e.kind == "divergence" for e in events)
    assert any(e.kind == "rising_counter" for e in events)
