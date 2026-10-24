#!/usr/bin/env python3
"""Lift the crown-and-QB mark off its app-icon background.

    python3 tools/qbmark.py

Ethan, 2026-08-23, with the header logo circled on his phone: "can we
remove the shiny lights on the left and right side of the crown so the
logo can look more natural sitting there and not like a picture placed
there if that makes sense."

It makes sense, and the lights are not a rendering artefact — they are
painted into the artwork. brand/appicon-1254.png is a full app icon: two
stadium floodlight banks in the upper corners, gold dust across a black
ground, the mark in the middle, the wordmark below. As a home-screen tile
that is exactly right, and the home-screen icons still ship it whole. In
the site header it was a photograph of an app icon pasted into a bar,
which is what he could see and could not name.

So the mark gets cut out and everything behind it thrown away: no lights,
no dust, no black ground, no rounded tile. It then sits on whatever the
page's background is, in either theme, which is what "natural" means here.

--------------------------------------------------------------------------
HOW THE CUT IS MADE, and why not by colour
--------------------------------------------------------------------------
The obvious approach fails: the floodlights are the same gold as the
crown. Measured, a ray reads hue 34, saturation 1.00, value 0.45 and the
Q reads hue 40, saturation 0.98, value 0.65 — no threshold on colour
separates them, and one tuned until it did would be tuned to this file
rather than to what the file contains.

What DOES separate them is that the mark is one connected object and the
lights are not part of it. So the cut is a flood fill from nine seeds
inside the crown, the Q and the B, over everything brighter than
VALUE_FLOOR, and the lights are simply never reached.

Three details, each of which was wrong first:

  * VALUE_FLOOR is 25, not 60. At 60 the flood stops at the mark's own
    black outline, which orphans all four balls on the crown's points —
    each is joined to its spike only through that outline. At 15 the
    flood escapes along the background gradient into the left light bank.
    25 is inside the window and not on either edge of it.
  * enclosed gaps up to HOLE_MAX are filled, which closes the pinholes
    the outline leaves. The Q's counter is far larger than that and stays
    open, so the mark is a ring on a light background rather than a disc.
  * the boundary is smoothed before it is used. A hard threshold through
    a soft gradient leaves a dotted fringe of half-caught pixels; blurring
    the mask, re-thresholding, then blurring once more for anti-aliasing
    removes it without rounding off the crown's points.

The output keeps the SOURCE'S OWN GEOMETRY — same crop box, same position
inside it — so the mark lands at the size it already had and this is a
change of background only, not a resize somebody has to re-approve.

Pillow only, no numpy: this is a hand-run tool, and the box the test
suite runs on has no image libraries at all.
"""

from __future__ import annotations

import base64
import io
import os
import sys
from collections import deque

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "brand", "appicon-1254.png")

#: Brightness above which a pixel can carry the flood. See the docstring:
#: 60 orphans the crown's balls, 15 escapes into the floodlights.
VALUE_FLOOR = 25
#: An enclosed gap this size or smaller is a pinhole in the mark's outline
#: and gets closed. The Q's counter is ~30x this and stays open.
HOLE_MAX = 2500
#: Blur radii: the first closes the threshold's speckle, the second is the
#: anti-aliased edge.
CLOSE_R, EDGE_R = 2.5, 1.2

#: Points known to be inside the mark, in SOURCE coordinates (x, y) — the
#: crown band, the Q and the B. Nine rather than one because the three
#: parts are separate objects at this threshold.
SEEDS = [(627, 330), (560, 300), (700, 300),
         (430, 760), (380, 700), (470, 820),
         (800, 700), (830, 800), (760, 760)]

#: The four balls on the crown's points, located by scanning the artwork
#: for gold rather than by eye. They are the reason VALUE_FLOOR is not
#: higher — each joins its spike only through the mark's black outline —
#: and they are what _sanity checks, because losing them is the failure
#: this tool actually made: a crown with one ball left, which renders as a
#: picture and raises nothing. An area check cannot see it; four balls are
#: a rounding error in a 200,000-pixel mark.
BALLS = [(356, 202), (504, 181), (752, 189), (903, 193)]


def _flood(bright: bytearray, w: int, h: int, seeds) -> bytearray:
    """4-connected flood over `bright`, from every seed. Iterative: the
    mark is ~200k pixels and Python's recursion limit is 1000."""
    out = bytearray(w * h)
    for sx, sy in seeds:
        i = sy * w + sx
        if not bright[i] or out[i]:
            continue
        out[i] = 1
        q = deque([i])
        while q:
            j = q.popleft()
            y, x = divmod(j, w)
            for nj, ok in ((j - w, y > 0), (j + w, y < h - 1),
                           (j - 1, x > 0), (j + 1, x < w - 1)):
                if ok and bright[nj] and not out[nj]:
                    out[nj] = 1
                    q.append(nj)
    return out


def _fill_small_holes(region: bytearray, w: int, h: int) -> int:
    """Close enclosed gaps up to HOLE_MAX. Returns how many pixels moved.

    "Enclosed" means not reachable from the border, which is why this runs
    on the CROP rather than the whole artwork: inside the crop the
    leftover slivers of floodlight still touch an edge and stay out.
    """
    gap = bytearray(1 - v for v in region)
    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] \
        + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    outside = _flood(gap, w, h, border)
    todo = [i for i in range(w * h) if gap[i] and not outside[i]]
    seen = bytearray(w * h)
    moved = 0
    for start in todo:
        if seen[start]:
            continue
        comp, q = [start], deque([start])
        seen[start] = 1
        while q:
            j = q.popleft()
            y, x = divmod(j, w)
            for nj, ok in ((j - w, y > 0), (j + w, y < h - 1),
                           (j - 1, x > 0), (j + 1, x < w - 1)):
                if ok and gap[nj] and not outside[nj] and not seen[nj]:
                    seen[nj] = 1
                    comp.append(nj)
                    q.append(nj)
        if len(comp) <= HOLE_MAX:
            for j in comp:
                region[j] = 1
            moved += len(comp)
    return moved


def cut(box) -> Image.Image:
    """The mark, on transparency, inside the given crop box."""
    im = Image.open(SRC).convert("RGB").crop(box)
    w, h = im.size
    px = im.load()
    bright = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            if r > VALUE_FLOOR or g > VALUE_FLOOR or b > VALUE_FLOOR:
                bright[row + x] = 1
    seeds = [(sx - box[0], sy - box[1]) for sx, sy in SEEDS]
    off = [(sx, sy) for sx, sy in seeds
           if not (0 <= sx < w and 0 <= sy < h)]
    if off:
        raise SystemExit(f"seeds fall outside the crop box: {off}")
    region = _flood(bright, w, h, seeds)
    if not sum(region):
        raise SystemExit("the flood found nothing — check VALUE_FLOOR")
    _fill_small_holes(region, w, h)

    mask = Image.frombytes("L", (w, h), bytes(v * 255 for v in region))
    mask = mask.filter(ImageFilter.GaussianBlur(CLOSE_R)).point(
        lambda v: 255 if v > 127 else 0)
    mask = mask.filter(ImageFilter.GaussianBlur(EDGE_R))
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def _sanity(im: Image.Image, box) -> None:
    """Refuse a cut that kept the lights or lost the mark.

    Both failures render as a picture, so neither raises on its own —
    which is how the first version shipped a crown missing three of its
    four balls and nothing said a word.
    """
    w, h = im.size
    alpha = im.getchannel("A")
    kept = sum(alpha.histogram()[9:])
    frac = kept / (w * h)
    if not 0.20 < frac < 0.45:
        raise SystemExit(
            f"the cut kept {frac:.0%} of the crop. Under ~20% it has lost "
            "part of the mark; over ~45% it has taken the floodlights too.")
    # The lights live in the top corners. Nothing there may survive.
    for name, (x0, x1) in (("left", (0, int(w * .06))),
                           ("right", (int(w * .94), w))):
        band = alpha.crop((x0, 0, x1, int(h * .35)))
        if band.getextrema()[1] > 40:
            raise SystemExit(
                f"the {name} floodlight is still in the cut — the flood "
                "escaped along the background")
    # And every ball is still on the crown.
    lost = [b for b in BALLS
            if alpha.getpixel((b[0] - box[0], b[1] - box[1])) < 200]
    if lost:
        raise SystemExit(
            f"{len(lost)} of {len(BALLS)} balls fell off the crown at "
            f"{lost} — VALUE_FLOOR is too high and has orphaned them "
            "behind the mark's own outline.")


if __name__ == "__main__":
    box = tuple(int(v) for v in
                (sys.argv[1] if len(sys.argv) > 1 else "214,0,1039,825")
                .split(","))
    mark = cut(box)
    _sanity(mark, box)

    logo = mark.resize((152, 152), Image.LANCZOS)
    logo.save(os.path.join(ROOT, "web", "logo-qb.png"))
    print(f"  152x152  web/logo-qb.png  (cut out, no background)")

    # The tab icon is the same picture at 64px, embedded, because an SVG
    # favicon cannot reference an external file. It keeps the name
    # favicon.svg: sw.js precaches "/favicon.svg", and removing it would
    # fail the service-worker install and take the installed app down.
    small = mark.resize((64, 64), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "PNG", optimize=True)
    path = os.path.join(ROOT, "web", "favicon.svg")
    head = open(path, encoding="utf-8").read().split('"data:image/png;base64,')[0]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(head + '"data:image/png;base64,'
                 + base64.b64encode(buf.getvalue()).decode()
                 + '"\n         x="0" y="0" width="48" height="48"/>\n</svg>\n')
    print("  48x48    web/favicon.svg  (same cut, embedded)")
