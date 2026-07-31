#!/usr/bin/env python3
"""Rasterise the Qellys Book "Q" mark into the home-screen icon.

iOS ignores SVG for "Add to Home Screen", so the phone needs a real PNG.
Rather than commit a binary nobody can regenerate, this draws it from the
same 48-unit geometry as web/favicon.svg — supersampled and written as a
bare PNG with nothing but the standard library, like the rest of the app.

    python3 make_icon.py                       # web/apple-touch-icon.png
    python3 make_icon.py /tmp/big.png 512      # any path, any size

Change the geometry here and you must change web/favicon.svg and the
<svg class="qmark"> in web/index.html to match, or the tab, the home
screen and the header stop looking like the same brand.
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

# --- the mark, in the SVG's 48x48 user units -----------------------------
U = 48.0
CX, CY, R = 24.0, 22.0, 14.0     # ring centre and radius
HALF = 1.75                      # half of the 3.5-unit stroke
TAIL_A = (30.36, 28.36)          # tail crosses the ring: from r = 9 inside…
TAIL_B = (36.73, 34.73)          # …to r = 18, just outside. A LONG tail here
                                 # turns the mark into a magnifying glass.
# The ring is centred at y=22 to leave room for a tail that no longer needs
# it, so the whole mark drops 2 units. Matches the <g transform> in the SVG.
NUDGE = (0.0, 2.0)
CORNER = 11.0                    # tile corner radius, matching the favicon

# Flat, not a gradient: these are the site's own --panel-2 and --brand, so
# the home-screen tile looks like the chrome it opens into.
TOP = (0x16, 0x17, 0x1D)
BOT = (0x16, 0x17, 0x1D)
INK = (0x7A, 0xA2, 0xF7)

SS = 4                           # supersampling factor per axis


def _in_mark(x: float, y: float) -> bool:
    """Is this point (in user units) painted white?"""
    x, y = x - NUDGE[0], y - NUDGE[1]
    if abs(math.hypot(x - CX, y - CY) - R) <= HALF:
        return True
    # The tail, with a flat cap at both ends — a round cap would bulge into
    # the counter and read as a magnifying glass rather than a Q.
    ax, ay = TAIL_A
    dx, dy = TAIL_B[0] - ax, TAIL_B[1] - ay
    t = ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)
    if not 0.0 <= t <= 1.0:
        return False
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy)) <= HALF


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
