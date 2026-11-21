#!/usr/bin/env python3
"""Rasterise the Qellys Book "Q" mark. NO LONGER WHAT SHIPS.

READ THIS BEFORE RUNNING IT. Since 2026-08-22 the home-screen icon is
Ethan's own render — "Use the actual image, don't make your own" — and
the source artwork is committed at `brand/appicon-1254.png`. Running this
and letting it write `web/apple-touch-icon.png` replaces that artwork
with the flat drawn mark. `tests/test_brand.py` fails if it ever does.

What it is still good for: it documents the 48-unit geometry that
web/favicon.svg and the <svg class="qmark"> in index.html share, and it
regenerates a matching PNG at any size if the drawn mark is ever wanted
somewhere. Write it to a scratch path, not over the icons.

iOS ignores SVG for "Add to Home Screen", so the phone needs a real PNG.
This draws it from the same 48-unit geometry as web/favicon.svg —
supersampled and written as a bare PNG with nothing but the standard
library, like the rest of the app.

    python3 make_icon.py /tmp/mark.png 512     # any path, any size

To rebuild the SHIPPED icons from Ethan's artwork instead, see
`tools/appicons.sh`.

Change the geometry here and you must change web/favicon.svg and the
<svg class="qmark"> in web/index.html to match, or the tab, the home
screen and the header stop looking like the same brand.
"""

from __future__ import annotations

import re
import math
import struct
import sys
import zlib
from pathlib import Path

# --- the mark, in the SVG's 48x48 user units -----------------------------
U = 48.0
CX, CY = 24.0, 24.0              # bowl centre
RX, RY = 17.0, 11.5              # bowl radii — the venue mark's proportions
HALF = 1.7                       # half of the 3.4-unit stroke
# The bowl sits dead centre (24, 24) and needs no offset: the tail that the
# old ring-plus-handle mark had to leave room for is gone, and so is the
# 2-unit drop that compensated for it. web/favicon.svg carries no <g
# transform> either — the two are aligned by both being centred, not by a
# shared nudge.
NUDGE = (0.0, 0.0)
CORNER = 0.0                     # square: radius 0 everywhere, spec §3.3

def _oklch_to_rgb(L: float, C: float, H: float) -> tuple:
    """OKLCH to 8-bit sRGB. Needed because the neutral ramp is written in
    oklch() — see the block comment on --bg in styles.css — and an icon
    generator that only understands hex would silently keep whatever the
    palette used to be."""
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_, m_, s_ = (L + 0.3963377774 * a + 0.2158037573 * b,
                  L - 0.1055613458 * a - 0.0638541728 * b,
                  L - 0.0894841775 * a - 1.2914855480 * b)
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    out = []
    for c in lin:
        c = max(0.0, min(1.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(max(0, min(255, round(c * 255))))
    return tuple(out)


#: How many `var(--x)` hops to follow. One alias is a design
#: decision — `--warn` IS `--brand`, written as a reference so
#: editing one cannot silently split them. A longer chain is not a
#: palette, it is a puzzle, and capping it also makes a cycle
#: terminate instead of hanging.
_MAX_ALIAS_HOPS = 4


def token(name: str, css: str | None = None, _hops: int = 0) -> tuple:
    """Resolve a custom property from the stylesheet's FIRST :root block.

    First, because that is the dark theme — the light one is a later
    override and matching it here would paint the icon for the wrong
    ground. Reads hex, oklch(), or `var(--other)` — the last so an
    alias stays readable to the tools. Without it, aliasing --warn
    to --brand dropped warn out of contrast.audit() silently,
    because audit swallows ValueError to skip tokens a theme does
    not define. A measurement quietly measuring one thing fewer is
    the worst way for this to fail.

    This is derived rather than copied on purpose. The favicon carried a
    hardcoded #101115 through a palette change and went off-brand without
    anything noticing until the test that compares them ran.
    """
    if css is None:
        css = (Path(__file__).resolve().parent / "web" / "css"
               / "styles.css").read_text(encoding="utf-8")
    # EVERY bare `:root {` block, cascade order — the NEW LOOK layer
    # (2026-08-11) re-declares the dark tokens at the END of the sheet,
    # so "the first block" stopped being the truth the browser paints.
    # `[data-theme="light"]`-scoped blocks are still excluded: the icon
    # is drawn for the dark ground. The LAST declaration wins, exactly
    # like the cascade it mirrors.
    root = ""
    for m0 in re.finditer(r"(?<![\]\w\-\"]):root\s*\{", css):
        block = css[m0.end():css.index("}", m0.end())]
        root += block + "\n"
    hits = re.findall(rf"--{re.escape(name)}:\s*([^;]+);", root)
    if not hits:
        raise KeyError(name)
    m = re.search(r"(.+)", hits[-1])
    val = m.group(1).strip()
    if val.startswith("#"):
        return tuple(int(val[i:i + 2], 16) for i in (1, 3, 5))
    ok = re.match(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)", val)
    if ok:
        return _oklch_to_rgb(*(float(x) for x in ok.groups()))
    alias = re.match(r"var\(\s*--([A-Za-z0-9_-]+)\s*\)$", val)
    if alias:
        if _hops >= _MAX_ALIAS_HOPS:
            raise ValueError(f"--{name}: alias chain too deep at {val!r}")
        return token(alias.group(1), css, _hops + 1)
    raise ValueError(f"--{name}: cannot read {val!r}")


# Flat, not a gradient: these are the site's own --panel-2 and --brand, so
# the home-screen tile looks like the chrome it opens into. Read from the
# stylesheet rather than transcribed, so the tile cannot drift off the
# palette the way it already did once.
TOP = BOT = token("panel-2")
INK = token("gold")

SS = 4                           # supersampling factor per axis


def _in_mark(x: float, y: float) -> bool:
    """Is this point (in user units) painted?

    The mark is the venue bowl ellipse (redesign spec §6.1) — the smallest
    scale of the venue system, so the logo and the product are the same
    idea. It replaced a geometric Q whose tail read as a magnifying glass
    at tab size.

    An ellipse has no closed-form distance-to-outline, so this measures the
    implicit-function residual and scales it by the local gradient. That
    gives a true perpendicular distance to first order, which is what a
    constant-width stroke needs — the naive |f(x,y)-1| test paints a band
    that is visibly fat at the ends of the major axis and thin at the top.
    """
    x, y = x - NUDGE[0], y - NUDGE[1]
    dx, dy = x - CX, y - CY
    f = (dx * dx) / (RX * RX) + (dy * dy) / (RY * RY) - 1.0
    gx, gy = 2 * dx / (RX * RX), 2 * dy / (RY * RY)
    g = math.hypot(gx, gy)
    if g == 0:
        return False
    return abs(f) / g <= HALF


def _in_tile(x: float, y: float, size: int, corner: float) -> bool:
    """Rounded-square coverage, in pixels."""
    cx = min(max(x, corner), size - corner)
    cy = min(max(y, corner), size - corner)
    return math.hypot(x - cx, y - cy) <= corner


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def render(size: int) -> bytes:
    """An 8-bit RGB PNG of the icon at `size` x `size`."""
    corner = size * CORNER / U
    scale = U / size
    rows = []
    for py in range(size):
        row = bytearray(b"\x00")                       # filter type: none
        # Vertical gradient, sampled once per row.
        f = (py + 0.5) / size
        bg = [TOP[i] + (BOT[i] - TOP[i]) * f for i in range(3)]
        for px in range(size):
            ink = tile = 0
            for sy in range(SS):
                for sx in range(SS):
                    fx, fy = px + (sx + .5) / SS, py + (sy + .5) / SS
                    if _in_tile(fx, fy, size, corner):
                        tile += 1
                        if _in_mark(fx * scale, fy * scale):
                            ink += 1
            n = SS * SS
            a_ink, a_tile = ink / n, tile / n
            for i in range(3):
                c = bg[i] * (1 - a_ink) + INK[i] * a_ink   # Q over gradient
                c = c * a_tile + 255 * (1 - a_tile)        # tile over white
                row.append(int(round(max(0.0, min(255.0, c)))))
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + _chunk(b"IEND", b""))


def main() -> None:
    args = sys.argv[1:]
    out = Path(args[0]) if args else Path(__file__).parent / "web" / "apple-touch-icon.png"
    size = int(args[1]) if len(args) > 1 else 180
    png = render(size)
    out.write_bytes(png)
    print(f"wrote {out} ({size}x{size}, {len(png):,} bytes)")


if __name__ == "__main__":
    main()
