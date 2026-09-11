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

  * A file whose name contains ``colors``/``sheet``/``grid`` holds
    MULTIPLE renders and is cut apart on its colour seams — a straight
    line whose two sides disagree in colour along its entire length.
    Any other name is ONE render and is never cut (a stadium's own rim
    wall looks exactly like a seam, so singles must say they're singles).
  * Each tile's LIGHTING colour is read from its upper region (the
    rig, not the grass/wood, which polluted naive sampling) and mapped
    to the site's names: red / gold / green / blue / violet, with a
    low-saturation tile landing on steel.
  * Singles work the same way — a neutral white-lit render is steel,
    and a filename containing ``neutral`` forces steel outright (white
    rigs over navy bowls can carry enough cool cast to read as blue).
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

from PIL import Image, ImageEnhance, ImageFilter

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


def _bright_bbox(region) -> tuple | None:
    """Bounding box of everything brighter than the padding floor — the
    trim step. Only trims: splitting on dark gaps shreds night renders,
    whose skies carry genuinely pitch-black full-width bands."""
    mask = region.convert("L").point(lambda v: 255 if v > 12 else 0)
    return mask.getbbox()


#: A candidate seam must jump at least this much in the cheap scan...
SEAM_CANDIDATE = 40.0
#: ...and score at least this on the consistency check to cut.
SEAM_CONFIRM = 26.0
#: No cut may leave a piece thinner than this.
MIN_PIECE = 200


def _line_means(rgb, axis: str):
    """Per-line mean RGB along an axis ('x' = one entry per column)."""
    W, H = rgb.size
    px = rgb.load()
    out = []
    other = range(0, H if axis == "x" else W, 4)
    n = float(len(other))
    for a in range(W if axis == "x" else H):
        r = g = b = 0
        for o in other:
            p = px[a, o] if axis == "x" else px[o, a]
            r += p[0]; g += p[1]; b += p[2]
        out.append((r / n, g / n, b / n))
    return out


def _seam_consistency(rgb, axis: str, pos: int, w: int = 6, K: int = 8) -> float:
    """Second-smallest per-segment colour jump across a candidate line.

    A butted-grid seam changes colour along its WHOLE length — every
    segment of the line has differently-lit pixels on its two sides. A
    field or court edge inside one render jumps hugely in the middle and
    not at all in the outer segments, so its weak tail gives it away.
    Dark-on-dark seam segments (night sky against night sky) carry little
    absolute RGB distance but still disagree in chroma direction, so each
    segment scores max(rgb distance, scaled direction distance)."""
    W, H = rgb.size
    px = rgb.load()
    L = H if axis == "x" else W
    scores = []
    for k in range(K):
        lo, hi = k * L // K, (k + 1) * L // K
        acc = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        n = 0
        for o in range(lo, hi, 2):
            for side, rng in enumerate((range(pos - w, pos),
                                        range(pos, pos + w))):
                for p in rng:
                    v = px[p, o] if axis == "x" else px[o, p]
                    acc[side][0] += v[0]; acc[side][1] += v[1]
                    acc[side][2] += v[2]
            n += 1
        n = float(max(1, n) * w)
        left = [c / n for c in acc[0]]
        right = [c / n for c in acc[1]]
        d_rgb = math.dist(left, right)
        sl, sr = sum(left) + 1, sum(right) + 1
        d_dir = math.dist([c / sl for c in left], [c / sr for c in right])
        scores.append(max(d_rgb, 400 * d_dir))
    return sorted(scores)[1]


def _best_seam(region):
    """The strongest confirmed grid seam in a region, or None.

    Cheap pass: windowed jump of per-line mean colour, both axes. Every
    local peak above SEAM_CANDIDATE then faces the consistency check;
    the best confirmed position wins. MIN_PIECE keeps any cut from
    shaving fragments off a real render."""
    rgb = region.convert("RGB")
    w = 6
    best = None
    for axis in ("y", "x"):
        means = _line_means(rgb, axis)
        span = len(means)
        if span < 2 * MIN_PIECE:
            continue
        jumps = []
        for i in range(MIN_PIECE, span - MIN_PIECE):
            l = [sum(c[k] for c in means[i - w:i]) / w for k in range(3)]
            r = [sum(c[k] for c in means[i:i + w]) / w for k in range(3)]
            jumps.append((math.dist(l, r), i))
        jumps.sort(reverse=True)
        taken = []
        for d, i in jumps:
            if d < SEAM_CANDIDATE or len(taken) >= 6:
                break
            if any(abs(i - t) < 50 for t in taken):
                continue
            taken.append(i)
            score = _seam_consistency(rgb, axis, i)
            if score >= SEAM_CONFIRM and (best is None or score > best[0]):
                best = (score, axis, i)
    return best


def _cut_region(im, box, out, depth: int = 0):
    """Recursive slicer: trim the dark border, hunt for a grid seam,
    recurse on the halves; emit the box when no seam is confirmed."""
    region = im.crop(box)
    bb = _bright_bbox(region)
    if bb is None:                       # pure-black scrap between tiles
        return
    x0, y0 = box[0] + bb[0], box[1] + bb[1]
    x1, y1 = box[0] + bb[2], box[1] + bb[3]
    region = im.crop((x0, y0, x1, y1))
    if depth < 5:
        seam = _best_seam(region)
        if seam:
            _, axis, p = seam
            if axis == "y":
                _cut_region(im, (x0, y0, x1, y0 + p - 2), out, depth + 1)
                _cut_region(im, (x0, y0 + p + 2, x1, y1), out, depth + 1)
            else:
                _cut_region(im, (x0, y0, x0 + p - 2, y1), out, depth + 1)
                _cut_region(im, (x0 + p + 2, y0, x1, y1), out, depth + 1)
            return
    out.append((x0 + 4, y0 + 4, x1 - 4, y1 - 4))


def slice_tiles(im: Image.Image) -> list[Image.Image]:
    """Tiles out of a sheet; a single un-gridded render comes back whole.

    The cutter is a colour-seam hunt, not a gap hunt: a straight line
    whose two sides disagree in colour along the line's ENTIRE length is
    a grid seam — true whether the tiles butt pixel-to-pixel (tonight's
    full-res sheets) or sit apart with padding (a padded sheet's tile
    edge). A field or court edge inside one render never manages it,
    because real scene boundaries die out toward the image corners.
    Dark padding and margins are trimmed, never split on: night renders
    carry genuinely pitch-black full-width sky bands."""
    boxes = []
    _cut_region(im, (0, 0, im.width, im.height), boxes)
    if len(boxes) <= 1:
        return [im]
    return [im.crop(b) for b in boxes]


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
        # The filename declares the geometry and the intent — that's the
        # contract. "...-colors"/"-sheet"/"-grid" means MULTIPLE renders
        # to cut apart; anything else is ONE render, never cut. (The
        # cutter can't be trusted on singles: a stadium's upper-rim wall
        # is a straight full-width colour edge that scores exactly like
        # a grid seam.) "...-neutral" additionally IS the steel render —
        # a white-lit arena over a navy bowl can carry enough cool cast
        # to tip the hue vote toward blue.
        stem = f.stem.lower()
        sheet = any(k in stem for k in ("colors", "sheet", "grid"))
        neutral = "neutral" in stem
        try:
            im = Image.open(f)
        except Exception as exc:                    # noqa: BLE001
            report.append(f"SKIP {f.name}: unreadable ({exc})")
            continue
        for tile in (slice_tiles(im) if sheet else [im]):
            cls = "steel" if neutral else classify(tile)
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
    # No neutral octagon render exists, so the steel rotation slot is the
    # blue one desaturated to house-neutral — until a real one lands.
    six, two = variants / "octagon-6.jpg", variants / "octagon-2.jpg"
    if two.exists() and (not six.exists()
                         or Image.open(six).width < Image.open(two).width):
        muted = ImageEnhance.Color(Image.open(two).convert("RGB")).enhance(0.18)
        muted.save(six, quality=87, optimize=True, progressive=True)
        report.append(f"WROTE {six.name} <- {two.name} desaturated "
                      f"({muted.width}x{muted.height}, steel slot)")
    return report


if __name__ == "__main__":
    for line in ingest():
        print(" ", line)
    sys.exit(0)
