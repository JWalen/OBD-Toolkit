"""Build a self-contained HTML diagnostic report.

Dependency-free: produces an HTML string with inline styles (so it renders the
same whether opened in a browser, emailed, or printed to PDF by the GUI). The
GUI converts this to PDF via Qt; nothing here needs a GUI or third-party deps.
"""

from __future__ import annotations

import base64
import html
from typing import Optional

from .diagnose import DiagnosticReport
from .parse import AutoScan, MeasuringLog

_SEV_COLOR = {
    "critical": "#E53E3E", "high": "#DD6B20", "medium": "#D69E2E",
    "low": "#3182CE", "info": "#718096",
}

_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1A202C; margin: 24px; }
h1 { color: #0066CC; margin-bottom: 2px; }
h2 { border-bottom: 2px solid #E2E8F0; padding-bottom: 4px; margin-top: 22px; }
table { border-collapse: collapse; width: 100%; margin-top: 6px; }
th, td { border: 1px solid #E2E8F0; padding: 5px 8px; text-align: left; font-size: 12px; }
th { background: #F7F8FA; }
.muted { color: #718096; }
.finding { margin: 10px 0; padding: 10px 12px; border-left: 4px solid #ccc; background: #F7F8FA; }
.badge { color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
ul { margin: 6px 0; }
"""


def _badge(severity: str) -> str:
    color = _SEV_COLOR.get(severity, "#718096")
    return f'<span class="badge" style="background:{color}">{html.escape(severity.upper())}</span>'


def _fmt(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def build_html_report(
    report: DiagnosticReport,
    log: Optional[MeasuringLog] = None,
    scan: Optional[AutoScan] = None,
    plot_png: Optional[bytes] = None,
    title: str = "VCDS Diagnostic Report",
    generated: str = "",
    version: str = "",
) -> str:
    """Render a diagnostic report as a standalone HTML document.

    Args:
        report: The :class:`DiagnosticReport` to render.
        log: Optional measuring log (adds a channel-statistics table).
        scan: Optional Auto-Scan (adds a raw fault list).
        plot_png: Optional PNG bytes of the plot to embed.
        title, generated, version: Header/footer text.
    """
    e = html.escape
    p: list = ["<!DOCTYPE html><html><head><meta charset='utf-8'><style>", _CSS,
               "</style></head><body>"]
    p.append(f"<h1>{e(title)}</h1>")

    meta = []
    if report.vin:
        meta.append(f"VIN {e(report.vin)}")
    if report.mileage:
        meta.append(e(report.mileage))
    if generated:
        meta.append(f"Generated {e(generated)}")
    if meta:
        p.append(f"<p class='muted'>{'  ·  '.join(meta)}</p>")

    p.append(f"<p><b>{e(report.headline)}</b></p>")
    summary = report.summary
    chips = " &nbsp; ".join(
        f"{_badge(k)} {summary[k]}"
        for k in ("critical", "high", "medium", "low", "info") if summary.get(k)
    )
    if chips:
        p.append(f"<p>{chips}</p>")

    # --- findings ---------------------------------------------------------- #
    p.append("<h2>Findings</h2>")
    if not report.findings:
        p.append("<p>No faults or abnormal readings detected.</p>")
    for f in report.findings:
        p.append(f"<div class='finding' style='border-left-color:{_SEV_COLOR.get(f.severity, '#ccc')}'>")
        p.append(f"<div>{_badge(f.severity)} &nbsp;<b>{e(f.title)}</b></div>")
        p.append(f"<div>{e(f.detail)}</div>")
        if f.causes:
            p.append("<div class='muted'>Likely causes (most likely first):</div><ul>")
            p.extend(f"<li>{e(c)}</li>" for c in f.causes)
            p.append("</ul>")
        p.append("</div>")

    # --- embedded plot ----------------------------------------------------- #
    if plot_png:
        b64 = base64.b64encode(plot_png).decode("ascii")
        p.append("<h2>Plot</h2>")
        p.append(f"<img src='data:image/png;base64,{b64}' style='max-width:100%;border:1px solid #E2E8F0'/>")

    # --- channel stats ----------------------------------------------------- #
    if log and log.channels:
        p.append("<h2>Channel statistics</h2><table>")
        p.append("<tr><th>Channel</th><th>Unit</th><th>Min</th><th>Max</th><th>Mean</th></tr>")
        for c in log.channels:
            p.append(f"<tr><td>{e(c.name)}</td><td>{e(c.unit)}</td>"
                     f"<td>{_fmt(c.min)}</td><td>{_fmt(c.max)}</td><td>{_fmt(c.mean)}</td></tr>")
        p.append("</table>")

    # --- raw scan faults --------------------------------------------------- #
    if scan and any(m.faults for m in scan.modules):
        p.append("<h2>Scan faults</h2>")
        for m in scan.modules:
            if not m.faults:
                continue
            p.append(f"<p><b>Address {e(m.address)} — {e(m.name)}</b></p><ul>")
            for fault in m.faults:
                detail = (f" <span class='muted'>({e(fault.status_detail)})</span>"
                          if fault.status_detail else "")
                p.append(f"<li>{e(fault.code)} — {e(fault.description)}{detail}</li>")
            p.append("</ul>")

    p.append(f"<hr><p class='muted'>Generated by VCDS Toolkit {e(version)}. "
             "Findings are heuristic guidance — verify before performing repairs.</p>")
    p.append("</body></html>")
    return "".join(p)


def save_html_report(path: str, *args, **kwargs) -> str:
    """Build and write an HTML report to ``path``; returns the path."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_html_report(*args, **kwargs))
    return path
