#!/usr/bin/env python3
"""Fit Ethan's app icon to the home-screen tile, and write every size.

    python3 tools/appiconfit.py

Ethan, 2026-10-28, with the new artwork attached: "here is the new app icon
too use. Make it fit right."

The artwork (brand/appicon-2026-10-28.png, committed as he sent it) is a
picture OF an app icon: a dark rounded tile with a thin gold rim, the crown
and the QB on it, floating on a darker backdrop with a margin all round.
Scaled whole, a phone would draw that tile inside its own: a small rounded
square in a black square, the rim nowhere near the edge.

WHAT FITTING IT MEANS
  * The tile fills the square. TILE is the tile's outer edge, measured on
    the rim (the brightest line one to three pixels inside each side), and
    the crop is a square around it (976 wide; the tile is 958 tall, so 9px
    of backdrop above and below, painted over below), so nothing is
    stretched.
  * The phone draws the corners. iOS cuts every icon to its own continuous
    corner (the UIBezierPath roundedRect shape, radius RADIUS of the side),
    and so do Android's launchers, each to its own. The artwork's rim was
    drawn ON its tile's edge, which is exactly where that cut lands, so on
    a phone it would come and go round the corners. It is drawn again
    instead, on iOS's own corner, RIM_INSET inside the edge and RIM_WIDTH
    wide, in the artwork's own colours (dilated off the old rim, so the
    bright top and the bronze sides are his): whatever a launcher cuts, it
    cuts the dark band outside the rim, never the rim.
  * RIM_WIDTH is 6px of 1024, wider than the artwork's 4 of 976. At 180px,
    the iPhone's size, his would be three quarters of a pixel and gone in
    the edge's anti-aliasing; this is one pixel and reads as the gold frame
    it is in the picture.
  * Android's maskable icon keeps only a circle 80% across (or the
    launcher's own squircle), so it is the tile without the rim (a circle
    would cut the rim into four arcs), its edge faded into a ground of the
    field's own colours (FIELD_INSET in, so the old rim's bevel never shows,
    and no seam where the tile ends), shrunk to MASKABLE_SCALE so the crown
    and the QB sit inside the circle.

The header logo is NOT made here: it is still cut from the earlier artwork,
brand/appicon-1254.png, by tools/qbmark.py (tools/appicons.sh runs both).

Pillow only, no numpy, like tools/qbmark.py. It refuses to write what it
cannot vouch for (raise SystemExit), because every way this can go wrong
still produces a picture.
"""

from __future__ import annotations

import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "brand", "appicon-2026-10-28.png")
MASTER = os.path.join(ROOT, "brand", "appicon-1024.png")

#: The tile's outer edge in the 1254px artwork: left, top, right, bottom
#: (right and bottom exclusive). Checked against the rim on every run.
TILE = (138, 134, 1114, 1092)
#: iOS's icon corner, as a share of the side (22.37%).
RADIUS = 0.2237
#: The redrawn rim, in px of the 1024 master: its outer edge's inset, its width.
RIM_INSET = 10
RIM_WIDTH = 6
#: Android's maskable safe zone is a circle 80% across; the tile is shrunk
#: to this inside it.
MASKABLE_SCALE = 0.90
#: Where the field is the artwork's own for the maskable icon: inside the
#: old rim's inner bevel (a lighter line 14-17px in on the square crop).
FIELD_INSET = 24
#: How far, in px of the 1024 tile, its edge fades into the ground there.
FEATHER = 16
#: The dark the band outside the rim, and the maskable's margin, are painted.
GROUND = (15, 15, 14)
S = 1024
SS = 4                      # supersampling for the masks' edges

#: One continuous corner (iOS 7's roundedRect, the published reverse-
#: engineered constants), from its first edge to its second, in radii:
#: (along the first edge from the corner, along the second).
_SEGMENTS = [("L", (1.52866483, 0.0)),
             ("C", (1.08849323, 0.0), (0.86840689, 0.0), (0.66993427, 0.06549600)),
             ("L", (0.63149399, 0.07491100)),
             ("C", (0.37282392, 0.16905899), (0.16905899, 0.37282392), (0.07491100, 0.63149399)),
             ("L", (0.06549600, 0.66993427)),
             ("C", (0.0, 0.86840689), (0.0, 1.08849323), (0.0, 1.52866483))]


def _bezier(p0, p1, p2, p3, n=32):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d
                         for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def _corner():
    pts, cur = [], None
    for seg in _SEGMENTS:
        if seg[0] == "L":
            cur = seg[1]
            pts.append(cur)
        else:
            pts += _bezier(cur, seg[1], seg[2], seg[3])
            cur = seg[3]
    return pts


def outline(size: float, inset: float, radius: float) -> list:
    """The icon's outline, clockwise, ``inset`` in from a ``size`` square."""
    lo, hi = inset, size - inset
    r = min(radius, (hi - lo) / 2 / 1.52866483)
    c = _corner()
    return ([(hi - a * r, lo + b * r) for a, b in c]          # top-right: top edge, then the right
            + [(hi - b * r, hi - a * r) for a, b in c]        # bottom-right
            + [(lo + a * r, hi - b * r) for a, b in c]        # bottom-left
            + [(lo + b * r, lo + a * r) for a, b in c])       # top-left


def shape(size: int, inset: float, radius: float) -> Image.Image:
    """The outline filled, as an anti-aliased mask."""
    big = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(big).polygon([(x * SS, y * SS) for x, y in outline(size, inset, radius)], fill=255)
    return big.resize((size, size), Image.LANCZOS)


def _lum(p) -> float:
    return sum(p[:3]) / 3


def _check_tile(src: Image.Image) -> None:
    """The crop box is on the rim: on each side's middle line, the brightest
    pixel within 12px of the box's edge is the rim, one to four pixels in."""
    px = src.load()
    x0, y0, x1, y1 = TILE
    mx, my = (x0 + x1) // 2, (y0 + y1) // 2
    sides = {"left": [(x, my) for x in range(x0 - 8, x0 + 12)],
             "right": [(x, my) for x in range(x1 + 7, x1 - 13, -1)],
             "top": [(mx, y) for y in range(y0 - 8, y0 + 12)],
             "bottom": [(mx, y) for y in range(y1 + 7, y1 - 13, -1)]}
    for name, line in sides.items():
        at = max(range(len(line)), key=lambda i: _lum(px[line[i]]))
        inside = at - 8
        if not 0 <= inside <= 4:
            raise SystemExit(f"the tile's {name} edge is not on the rim: the rim is {inside}px in")


def square(src: Image.Image) -> Image.Image:
    """The tile, cropped square round TILE (its height made up from the
    backdrop above and below, which fit() paints over) and scaled to S."""
    x0, y0, x1, y1 = TILE
    side = x1 - x0
    top = y0 - (side - (y1 - y0)) // 2
    return src.crop((x0, top, x1, top + side)).resize((S, S), Image.LANCZOS)


def fit(src: Image.Image) -> Image.Image:
    """The 1024 master: the square tile, its old rim and the backdrop under a
    dark band, and the gold drawn again on iOS's corner."""
    tile = square(src)
    r = RADIUS * S
    outer = shape(S, RIM_INSET, r - RIM_INSET)
    inner = shape(S, RIM_INSET + RIM_WIDTH, r - RIM_INSET - RIM_WIDTH)
    # The old rim's colours, spread inward over where the new one goes: the
    # band within 18px of the edge, dilated a pixel a step (a max filter
    # keeps the brightest, which is the rim and never the dark around it).
    band = ImageChops.invert(shape(S, 18, r - 18)).point(lambda v: 255 if v > 128 else 0)
    colour = Image.composite(tile, Image.new("RGB", (S, S), 0), band)
    for _ in range(12):
        colour = colour.filter(ImageFilter.MaxFilter(5))
    out = Image.composite(tile, Image.new("RGB", (S, S), GROUND), outer)
    return Image.composite(colour, out, ImageChops.subtract(outer, inner))


def _check_master(img: Image.Image) -> None:
    px = img.load()
    m = S // 2
    for name, (x, y) in {"top": (m, RIM_INSET + RIM_WIDTH // 2), "bottom": (m, S - RIM_INSET - RIM_WIDTH // 2 - 1),
                         "left": (RIM_INSET + RIM_WIDTH // 2, m), "right": (S - RIM_INSET - RIM_WIDTH // 2 - 1, m)}.items():
        r, g, b = px[x, y]
        if not (r > g > b and r > 80):
            raise SystemExit(f"the rim is not gold on the {name} side: {px[x, y]}")
    for x, y in ((2, m), (m, 2), (S - 3, m), (m, S - 3)):
        if _lum(px[x, y]) > 30:
            raise SystemExit(f"the band outside the rim is not dark at {(x, y)}: {px[x, y]}")


def _row(img: Image.Image, y: int) -> tuple:
    """The field's colour along one row, across its middle half: the median,
    so a gold stripe crossing the row does not tint the ground."""
    px = img.load()
    pts = [px[x, y] for x in range(img.size[0] // 4, img.size[0] * 3 // 4, 4)]
    return tuple(sorted(p[i] for p in pts)[len(pts) // 2] for i in range(3))


def padded(tile: Image.Image, grow: int) -> Image.Image:
    """``tile`` on a canvas ``grow`` px bigger all round, its edge faded
    (FEATHER) into a ground that runs from the field's own top colour to its
    bottom one, so the tile ends without a seam: the old rim and its bevel
    are outside FIELD_INSET and never shown."""
    n = S + 2 * grow
    top, bottom = _row(tile, FIELD_INSET + 4), _row(tile, S - FIELD_INSET - 5)
    ground = Image.new("RGB", (n, n))
    draw = ImageDraw.Draw(ground)
    for y in range(n):
        t = min(1.0, max(0.0, (y - grow) / S))
        draw.line([(0, y), (n, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    keep = Image.new("L", (n, n), 0)
    keep.paste(shape(S, FIELD_INSET + FEATHER, RADIUS * S - FIELD_INSET - FEATHER), (grow, grow))
    keep = keep.filter(ImageFilter.GaussianBlur(FEATHER / 2))
    canvas = ground.copy()
    canvas.paste(tile, (grow, grow))
    return Image.composite(canvas, ground, keep)


def maskable(src: Image.Image) -> Image.Image:
    """Android's adaptive icon: the field to every edge, no rim, the mark
    inside the safe circle."""
    n = 512
    tile = square(src)
    grow = round(S * (1 / MASKABLE_SCALE - 1) / 2)
    full = padded(tile, grow)
    out = full.resize((n, n), Image.LANCZOS)
    # The crown and the QB inside Android's circle (40% of the side out).
    px = out.load()
    far = max((math.hypot(x - n / 2, y - n / 2) for y in range(0, n, 2) for x in range(0, n, 2)
               if _lum(px[x, y]) > 110), default=0)
    if far > 0.4 * n:
        raise SystemExit(f"the mark reaches {far:.0f}px out, past the maskable circle ({0.4 * n:.0f})")
    return out


def main() -> int:
    src = Image.open(SRC).convert("RGB")
    if src.size != (1254, 1254):
        raise SystemExit(f"{SRC} is {src.size}, not the 1254px artwork TILE was measured on")
    _check_tile(src)
    master = fit(src)
    _check_master(master)
    master.save(MASTER, optimize=True)
    print(f"  1024x1024  {os.path.relpath(MASTER, ROOT)}  (the fitted master; the iOS build's App Store icon)")
    for n, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        out = os.path.join(ROOT, "web", name)
        master.resize((n, n), Image.LANCZOS).save(out, optimize=True)
        print(f"  {n}x{n}  web/{name}")
    out = os.path.join(ROOT, "web", "icon-maskable-512.png")
    maskable(src).save(out, optimize=True)
    print("  512x512  web/icon-maskable-512.png  (no rim, inside Android's circle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
