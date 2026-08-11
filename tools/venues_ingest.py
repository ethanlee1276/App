#!/usr/bin/env python3
"""Venue render intake — drop files in, get the site's variants out.

    web/img/venues/incoming/football-colors.png      (a 5/6-tile sheet)
    web/img/venues/incoming/baseball-neutral.png     (a single render)
    python3 tools/venues_ingest.py

Built 2026-08-11, the night Ethan started sending full-resolution
renders one family at a time ("make sure they are good and not super
blurry then throw them on the site"). The chat pipeline recompresses
and lags; files do neither. Drop any mix of sheets and singles into
``incoming/`` with the family as the filename's first word —
``football`` / ``baseball`` / ``basketball`` / ``octagon`` — and this
does the rest:

  * A GRID (multiple tiles) is sliced by brightness bands, the same
    detector that cut the original contact sheet.
  * Each tile's LIGHTING colour is read from its upper region (the
    rig, not the grass/wood, which polluted naive sampling) and mapped
    to the site's names: red / gold / green / blue / violet, with a
    low-saturation tile landing on steel.
  * Singles work the same way — a neutral white-lit render is steel.
  * Output goes to ``variants/{family}-{name}.jpg`` (octagon uses the
    1-6 rotation slots), downscaled to at most 1600px wide, gently
    sharpened, JPG q87. Existing files are only replaced when the new
    source carries MORE pixels — a re-run can upgrade, never downgrade.

Per-team overrides ({sport}/{ABBR}.jpg) are untouched — this feeds the
colour-variant layer only. The ingest prints everything it did and
everything it refused, and an empty incoming/ is a no-op, not an error.
"""

from __future__ import annotations

import colorsys
import math
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "web" / "img" / "venues" / "incoming"
VARIANTS = ROOT / "web" / "img" / "venues" / "variants"

FAMILIES = ("football", "baseball", "basketball", "octagon")
HUE_ANCHORS = {"red": 358, "gold": 40, "green": 140, "blue": 225, "violet": 285}
#: Below this lighting saturation a render reads as neutral -> steel.
NEUTRAL_SAT = 0.16
#: The octagon rotation slots, by lighting colour.
OCTAGON_SLOTS = {"violet": 1, "blue": 2, "red": 3, "gold": 4,
                 "green": 5, "steel": 6}
MAX_W = 1600


def _bands(gray, axis: str, lo: int, hi: int, other_lo: int, other_hi: int,
           min_len: int) -> list[tuple[int, int]]:
    """Bright runs along one axis, measured by per-line max — vignetted
    dark tiles survive a max where they vanish under a mean."""
    px = gray.load()
    runs, in_run, start = [], False, 0
    for a in range(lo, hi):
        m = 0
        for b in range(other_lo, other_hi, 4):
            v = px[a, b] if axis == "x" else px[b, a]
            if v > m:
                m = v
        bright = m > 12
        if bright and not in_run:
            start, in_run = a, True
        elif not bright and in_run:
            if a - start >= min_len:
                runs.append((start, a))
            in_run = False
    if in_run and hi - start >= min_len:
        runs.append((start, hi))
    return runs


def slice_tiles(im: Image.Image) -> list[Image.Image]:
    """Tiles out of a sheet; a single un-gridded render comes back whole."""
    gray = im.convert("L")
    W, H = im.size
    rows = _bands(gray, "y", 0, H, 0, W, min_len=max(120, H // 8))
    tiles = []
    for (y0, y1) in rows:
        cols = _bands(gray, "x", 0, W, y0, y1, min_len=max(120, W // 10))
        for (x0, x1) in cols:
            tiles.append(im.crop((x0 + 4, y0 + 4, x1 - 4, y1 - 4)))
    # One row x one column that spans nearly everything = not a grid.
    if len(tiles) <= 1:
        return [im]
    return tiles


def light_hue(tile: Image.Image) -> tuple[float, float]:
    """(hue°, saturation) of the LIGHTING: the tile's upper region only,
    so grass, dirt and wood floors never vote."""
    band = tile.crop((0, 0, tile.width, max(1, int(tile.height * 0.40))))
    tp = band.convert("RGB").load()
    sx = sy = wsum = 0.0
    sat_acc = wn = 0.0
    step = max(1, band.width // 300)
    for y in range(0, band.height, step):
        for x in range(0, band.width, step):
            r, g, b = tp[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if v < 0.25:
                continue
            sat_acc += s * v
            wn += v
            w = s * v
            if w > 0.04:
                a = h * 2 * math.pi
                sx += math.cos(a) * w
                sy += math.sin(a) * w
                wsum += w
    hue = (math.degrees(math.atan2(sy, sx)) % 360) if wsum else 0.0
    return hue, (sat_acc / wn if wn else 0.0)


def classify(tile: Image.Image) -> str:
    hue, sat = light_hue(tile)
    if sat < NEUTRAL_SAT:
        return "steel"
    best, bd = "steel", 361.0
    for name, anchor in HUE_ANCHORS.items():
        raw = abs(hue - anchor) % 360
        d = min(raw, 360 - raw)
        if d < bd:
            best, bd = name, d
    return best


def finish(tile: Image.Image) -> Image.Image:
    """Size + gentle sharpen. Big sources only come DOWN in size — the
    blur this pipeline exists to kill came from upscaling tiny tiles."""
    t = tile.convert("RGB")
    if t.width > MAX_W:
        t = t.resize((MAX_W, round(t.height * MAX_W / t.width)), Image.LANCZOS)
    elif t.width < 900:
        t = t.resize((t.width * 2, t.height * 2), Image.LANCZOS)
    return t.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=2))


def target_name(family: str, cls: str) -> str:
    if family == "octagon":
        return f"octagon-{OCTAGON_SLOTS[cls]}.jpg"
    return f"{family}-{cls}.jpg"


def ingest(incoming: Path = INCOMING, variants: Path = VARIANTS,
           families: tuple = FAMILIES) -> list[str]:
    """Process every file; returns the printed report lines (tested on
    synthetic sheets — see tests/test_venue_ingest.py)."""
    report = []
    variants.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in incoming.glob("*")
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not files:
        report.append(f"nothing to ingest — drop renders in {incoming}")
        return report
    for f in files:
        fam = f.stem.split("-")[0].split("_")[0].lower()
        if fam not in families:
            report.append(f"SKIP {f.name}: name must start with one of "
                          f"{'/'.join(families)}")
            continue
        try:
            im = Image.open(f)
        except Exception as exc:                    # noqa: BLE001
            report.append(f"SKIP {f.name}: unreadable ({exc})")
            continue
        for tile in slice_tiles(im):
            cls = classify(tile)
            out = variants / target_name(fam, cls)
            done = finish(tile)
            if out.exists():
                old_w = Image.open(out).width
                if done.width < old_w:
                    report.append(f"KEEP {out.name}: existing {old_w}px "
                                  f"outranks new {done.width}px")
                    continue
            done.save(out, quality=87, optimize=True, progressive=True)
            report.append(f"WROTE {out.name} <- {f.name} "
                          f"({done.width}x{done.height}, lighting={cls})")
    return report


if __name__ == "__main__":
    for line in ingest():
        print(" ", line)
    sys.exit(0)
