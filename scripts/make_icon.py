"""Generate the OBD Toolkit application icon.

A boost-gauge motif in the carbon "motorsport" palette: a graphite rounded-square
tile, an amber gauge arc with tick marks, and a racing-red needle swept up toward
boost. Emits a Windows ``.ico``, a macOS ``.icns`` and a 1024px ``.png``.

Re-run after any tweak:

    python scripts/make_icon.py
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

CARBON = (21, 23, 28, 255)    # #15171C  graphite tile
EDGE = (38, 42, 49, 255)      # #262A31  subtle inner edge
AMBER = (255, 106, 0, 255)    # #FF6A00  gauge arc
RED = (225, 6, 0, 255)        # #E10600  needle
LIGHT = (232, 234, 237, 255)  # #E8EAED  hub highlight
MUTED = (168, 174, 184, 255)  # #A8AEB8  tick marks


def render(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-square background tile with a subtle inner edge.
    m = int(size * 0.045)
    radius = int(size * 0.21)
    d.rounded_rectangle([m, m, size - m, size - m], radius=radius, fill=EDGE)
    g = m + int(size * 0.012)
    d.rounded_rectangle([g, g, size - g, size - g], radius=radius - int(size * 0.01), fill=CARBON)

    cx = cy = size / 2.0
    R = size * 0.34

    # Gauge arc — bottom ~270°, open at the top (PIL angles: 0=right, 90=down).
    bbox = [cx - R, cy - R, cx + R, cy + R]
    d.arc(bbox, start=315, end=585, fill=AMBER, width=int(size * 0.058))

    # A short "redline" sweep at the high end of the arc.
    d.arc(bbox, start=540, end=585, fill=RED, width=int(size * 0.058))

    # Tick marks around the arc.
    for ang in range(315, 586, 30):
        a = math.radians(ang)
        r1, r2 = R - size * 0.018, R - size * 0.08
        d.line(
            [cx + r1 * math.cos(a), cy + r1 * math.sin(a),
             cx + r2 * math.cos(a), cy + r2 * math.sin(a)],
            fill=MUTED, width=max(2, int(size * 0.012)),
        )

    # Needle swept up-and-right (an "active" reading), drawn as a tapered blade.
    na = math.radians(305)
    L = R * 0.95
    nx, ny = cx + L * math.cos(na), cy + L * math.sin(na)
    ta = math.radians(305 + 180)
    tl = R * 0.30
    tx, ty = cx + tl * math.cos(ta), cy + tl * math.sin(ta)
    perp = na + math.pi / 2
    w = size * 0.024
    px, py = math.cos(perp) * w, math.sin(perp) * w
    d.polygon([(nx, ny), (cx + px, cy + py), (tx, ty), (cx - px, cy - py)], fill=RED)

    # Center hub.
    hub = size * 0.05
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=LIGHT)
    d.ellipse([cx - hub / 2, cy - hub / 2, cx + hub / 2, cy + hub / 2], fill=AMBER)

    return img


def main(preview_path: str | None = None) -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(os.path.dirname(here), "installer")
    os.makedirs(out_dir, exist_ok=True)

    big = render(1024)

    ico_path = os.path.join(out_dir, "app.ico")
    big.save(ico_path, sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    print(f"wrote {ico_path}")

    png_path = os.path.join(out_dir, "app.png")
    big.save(png_path)
    print(f"wrote {png_path}")

    # macOS .icns (Pillow's ICNS encoder; falls back gracefully if unavailable).
    icns_path = os.path.join(out_dir, "app.icns")
    try:
        big.save(icns_path, format="ICNS")
        print(f"wrote {icns_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"skipped {icns_path}: {exc} (CI regenerates it from app.png on macOS)")

    if preview_path:
        big.resize((256, 256), Image.LANCZOS).save(preview_path)
        print(f"wrote {preview_path}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else None)
