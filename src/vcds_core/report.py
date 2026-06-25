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


# Generic drive-cycle guidance per readiness monitor (to complete incomplete ones).
DRIVE_CYCLE_TIPS = {
    "catalyst_monitoring": "Warm up fully, then steady cruise at 40–60 mph for several minutes.",
    "heated_catalyst_monitoring": "Steady cruise after full warm-up.",
    "evaporative_system_monitoring": "Begin from a cold start (engine off several hours), "
                                     "fuel tank ~½ full; idle then drive gently.",
    "oxygen_sensor_monitoring": "Steady-speed cruise plus a few gentle decelerations.",
    "oxygen_sensor_heater_monitoring": "Completes shortly after a cold start.",
    "egr_vvt_system_monitoring": "Cruise, then a closed-throttle deceleration or two.",
    "secondary_air_system_monitoring": "Completes at idle shortly after a cold start.",
    "fuel_system_monitoring": "Mix of idle, cruise and light acceleration after warm-up.",
    "misfire_monitoring": "Normal driving after warm-up.",
    "comprehensive_components_monitoring": "Normal driving after warm-up.",
}


def drive_cycle_tip(monitor: str) -> str:
    return DRIVE_CYCLE_TIPS.get(monitor, "Complete a normal warm-up drive cycle (cold start, "
                                         "idle, steady cruise, gentle decel).")


def build_smog_html(vin: Optional[str], vin_info, readiness: Optional[dict],
                    permanent_dtcs=None, generated: str = "", version: str = "") -> str:
    """Render a one-page emissions-readiness (smog) report as HTML."""
    e = html.escape
    permanent_dtcs = permanent_dtcs or []
    incomplete = []
    ready = False
    if readiness:
        incomplete = [m for m, s in readiness["monitors"].items()
                      if s["available"] and not s["complete"]]
        ready = (not readiness["mil"]) and not incomplete

    p = ["<!DOCTYPE html><html><head><meta charset='utf-8'><style>", _CSS, "</style></head><body>"]
    p.append("<h1>Emissions Readiness Report</h1>")
    meta = []
    if vin:
        meta.append(f"VIN {e(vin)}")
    if vin_info and getattr(vin_info, "make", None):
        meta.append(f"{e(str(vin_info.make))} {e(str(vin_info.year or ''))}")
    if generated:
        meta.append(f"Generated {e(generated)}")
    if meta:
        p.append(f"<p class='muted'>{'  ·  '.join(meta)}</p>")

    color = "#38A169" if ready else "#E53E3E"
    verdict = "READY to test" if ready else "NOT ready"
    p.append(f"<h2 style='color:{color}'>{verdict}</h2>")
    if readiness:
        p.append(f"<p>Check-engine light (MIL): "
                 f"<b>{'ON' if readiness['mil'] else 'off'}</b> &nbsp;·&nbsp; "
                 f"stored DTCs: <b>{readiness['dtc_count']}</b></p>")
        p.append("<h2>Monitors</h2><table><tr><th>Monitor</th><th>Status</th>"
                 "<th>Drive-cycle tip</th></tr>")
        for name, s in readiness["monitors"].items():
            if not s["available"]:
                status, tip = "n/a", ""
            elif s["complete"]:
                status, tip = "ready", ""
            else:
                status, tip = "NOT ready", drive_cycle_tip(name)
            p.append(f"<tr><td>{e(name.replace('_', ' '))}</td><td>{status}</td>"
                     f"<td class='muted'>{e(tip)}</td></tr>")
        p.append("</table>")
    else:
        p.append("<p class='muted'>Readiness data unavailable.</p>")

    if permanent_dtcs:
        p.append("<h2>Permanent DTCs</h2><ul>")
        for code, _desc in permanent_dtcs:
            p.append(f"<li>{e(code)}</li>")
        p.append("</ul>")
    p.append(f"<hr><p class='muted'>Generated by OBD Toolkit {e(version)}. Readiness reflects "
             "the vehicle at the time of reading.</p></body></html>")
    return "".join(p)
