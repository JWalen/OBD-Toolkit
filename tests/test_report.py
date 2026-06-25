"""Tests for the HTML diagnostic report generator."""

from __future__ import annotations

from vcds_core import parse
from vcds_core.diagnose import diagnose
from vcds_core.report import build_html_report, save_html_report


def test_report_contains_findings_and_meta(samples_dir):
    scan = parse.parse_autoscan(samples_dir["autoscan"])
    log = parse.parse_measuring_log(samples_dir["advanced"])
    report = diagnose(scan=scan, log=log)
    html = build_html_report(report, log=log, scan=scan, generated="2026-06-24", version="0.3.0")

    assert html.startswith("<!DOCTYPE html>")
    assert "WAUZZZ8K9BA123456" in html
    assert "Findings" in html
    # at least one finding title and its severity badge
    assert report.findings[0].title.split(" — ")[0] in html
    assert "HIGH" in html or "MEDIUM" in html
    # channel-statistics table + scan faults section
    assert "Channel statistics" in html
    assert "Scan faults" in html
    assert "0.3.0" in html


def test_report_embeds_plot_png():
    from vcds_core.diagnose import DiagnosticReport

    report = DiagnosticReport(vin=None, mileage=None, findings=[])
    png = b"\x89PNG\r\n\x1a\nFAKE"
    html = build_html_report(report, plot_png=png)
    assert "data:image/png;base64," in html
    assert "No faults or abnormal readings" in html


def test_save_html_report(tmp_path, samples_dir):
    scan = parse.parse_autoscan(samples_dir["autoscan"])
    report = diagnose(scan=scan)
    out = tmp_path / "report.html"
    save_html_report(str(out), report, scan=scan, version="0.3.0")
    assert out.is_file()
    assert "<html>" in out.read_text(encoding="utf-8")
