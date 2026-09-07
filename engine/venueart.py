"""Are the venue renders one set of pictures, or several?

Ethan, 2026-08-13, after a cache-bust that fixed a real problem but not
his: "the stadium issue is not fixed."

He was right. `variants/` held TWO GENERATIONS of art — three sharp
1536x1024 neutral singles and fifteen softer tiles cut out of colour
sheets — and `venueVariant` picks a slot from the home team's kit, so a
neutral-kitted club got the sharp render and a colour-kitted club got a
sheet tile, deterministically, forever. Put two cards side by side and
they do not look like the same website.

The fix at the time was to serve only the generation we had all of
(`VENUE_MATCHED = {"steel"}`), which cost the tinting and was the right
trade. This module is the other half: the thing that would have CAUGHT
it, and the thing that says when the colours can come back.

WHAT IT MEASURES, and why these three:

    aspect      the tiles are nearly square (1.03) and the reference is
                3:2 (1.50). A card crops to cover, so a square source is
                a different crop of a different composition — the single
                loudest mismatch and the cheapest to check.
    pixels      how much picture there actually is, against the family's
                own reference.
    detail      bytes per pixel. The ingest writes every file at the same
                JPEG quality, so within a family — same subject, same
                encoder setting — bytes per pixel tracks how much fine
                structure survived. A PROXY, reported as one: it cannot
                tell a soft render from a foggy night, and it is not a
                verdict on its own.

THE REFERENCE IS PER FAMILY, not global. `basketball-steel` carries 0.18
bytes/pixel and `football-blue` carries 0.21, and comparing those two
would call the soft tile the better file — an empty wooden arena simply
holds less fine structure than a stadium bowl. Each family is judged
against its own steel render.

Standard library only, deliberately. `tools/venues_ingest.py` needs
Pillow and is a hand-run laptop tool; this has to run anywhere the site
runs, including in the test suite, so the JPEG header is parsed by hand.
"""

from __future__ import annotations

import struct
from pathlib import Path

VENUE_DIR = Path(__file__).parent.parent / "web" / "img" / "venues"

#: The three families the colour rule serves, and the slot every one of
#: them must fill before `VENUE_MATCHED` can widen.
FAMILIES = ("football", "baseball", "basketball")
COLOURS = ("steel", "red", "gold", "green", "blue", "violet")
#: The UFC banners, hash-picked rather than colour-picked, so they have no
#: colour slots and no reference to match.
OCTAGON = tuple(f"octagon-{i}" for i in range(1, 7))

#: The slot every family's other renders are measured against.
REFERENCE = "steel"

#: How far a render may drift from its family reference before it stops
#: looking like the same shoot. Tuned to the observed split, not guessed:
#: the good files sit within 0.3% of 3:2 and the sheet tiles land at 1.03
#: — roughly a third out. Nothing real falls in between.
ASPECT_TOLERANCE = 0.05
#: Fraction of the reference's pixel count a render must carry.
MIN_PIXEL_RATIO = 0.90
#: Fraction of the reference's bytes-per-pixel. The 2026-08-11 tiles run
#: 49-90% of their family reference, so this catches most of them and is
#: honest about the ones it does not.
MIN_DETAIL_RATIO = 0.80


#: Words that declare a file in ``incoming/`` to hold MULTIPLE renders.
#: Mirrors `tools/venues_ingest.py`'s own rule (``sheet = any(k in stem
#: for k in ("colors", "sheet", "grid"))``). The two must agree, because
#: this module tells a reader what running that tool would do.
SHEET_WORDS = ("colors", "sheet", "grid")


def classify_incoming(names) -> dict:
    """Split ``incoming/`` into ``{"sheets": [...], "singles": [...]}``.

    THE DISTINCTION IS THE POINT, and the probe got it wrong on its first
    real run. Ethan, 2026-08-14, ran `--venues` on his laptop and was told
    "Run `python3 tools/venues_ingest.py` to cut and install them" about
    seven files that were the ORIGINAL 2026-08-11 sources — the very
    sheets whose tiles the same output had just rejected fifteen times,
    three inches higher up the screen.

    Following that advice would have been harmless: the ingest replaces a
    file only when the new source carries MORE pixels, and re-cutting a
    sheet yields the same tile sizes, so nothing would be overwritten. But
    harmless is not the bar. It was an instruction that could not work,
    printed directly beneath the evidence that it could not work, and a
    probe that says that is worse than a probe that says nothing.
    """
    sheets, singles = [], []
    for name in (names or []):
        stem = str(name).rsplit(".", 1)[0].lower()
        (sheets if any(k in stem for k in SHEET_WORDS) else singles).append(name)
    return {"sheets": sheets, "singles": singles}


def incoming_targets(names, data) -> dict:
    """What running the ingest on ``incoming/`` would actually change.

    ``{"useful": [...], "noop": [...], "sheets": [...]}``.

    The second version of the probe still got this wrong. Having learned
    to say "4 of those are SHEETS", it then told Ethan "3 single render(s)
    ready — the ingest installs them" about `baseball-neutral.png` and its
    two siblings, which are the STEEL REFERENCES ALREADY INSTALLED. Right
    classification, same useless instruction.

    So this stops classifying and starts checking: a single is worth
    ingesting only when the slot it lands in does not already hold art
    that passes. `-neutral` in a name pins the render to steel, which is
    the ingest's own rule and the reason those three resolve to a
    finished slot.
    """
    kinds = classify_incoming(names)
    useful, noop = [], []
    for name in kinds["singles"]:
        stem = str(name).rsplit(".", 1)[0].lower()
        family = next((f for f in FAMILIES if stem.startswith(f)), None)
        if family is None:
            useful.append(name)          # unknown family — let the tool judge
            continue
        colour = REFERENCE if "neutral" in stem else next(
            (c for c in COLOURS if c in stem), None)
        slot = (data.get("families", {}).get(family, {})
                .get("slots") or {}).get(colour) if colour else None
        # Missing slot, or one still flagged, is a slot worth filling.
        if slot is None or (colour != REFERENCE and not slot.get("matches")):
            useful.append(name)
        else:
            noop.append(name)
    return {"useful": useful, "noop": noop, "sheets": kinds["sheets"]}


def jpeg_size(path) -> tuple[int, int] | None:
    """``(width, height)`` from a JPEG's SOF marker, or None.

    Hand-rolled because this module is stdlib-only. Walks the marker
    chain rather than seeking a fixed offset — EXIF and colour profiles
    push the frame header around, and a fixed offset reads a thumbnail's
    dimensions on some encoders and garbage on others.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None                       # not a JPEG
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF0-SOF15, minus the four that are not frame headers.
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return (w, h) if w and h else None
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        try:
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        except struct.error:
            return None
    return None


def describe(path) -> dict | None:
    """One render's measurements, or None when it is missing/unreadable."""
    p = Path(path)
    if not p.exists():
        return None
    size = jpeg_size(p)
    if not size:
        return None
    w, h = size
    by = p.stat().st_size
    return {"name": p.name, "width": w, "height": h, "bytes": by,
            "pixels": w * h, "aspect": round(w / h, 3),
            "detail": round(by / (w * h), 4)}


def survey(root=None) -> dict:
    """Every variant slot, measured, with each family judged against its
    own reference.

    ``{families: {family: {reference, slots: {colour: {...}}}}, octagon,
    incoming, present, expected}``. A missing file is a slot with
    ``None`` rather than an absent key — "we do not have this" is the
    answer the caller most needs and it should not require a lookup miss
    to discover.
    """
    root = Path(root or VENUE_DIR)
    var = root / "variants"
    out = {"families": {}, "octagon": {}, "incoming": [],
           "present": 0, "expected": len(FAMILIES) * len(COLOURS) + len(OCTAGON)}

    for family in FAMILIES:
        ref = describe(var / f"{family}-{REFERENCE}.jpg")
        slots: dict[str, dict | None] = {}
        for colour in COLOURS:
            d = describe(var / f"{family}-{colour}.jpg")
            if d is not None:
                out["present"] += 1
                d["issues"] = [] if colour == REFERENCE else _issues(d, ref)
                d["matches"] = not d["issues"]
            slots[colour] = d
        out["families"][family] = {"reference": ref, "slots": slots}

    for name in OCTAGON:
        d = describe(var / f"{name}.jpg")
        if d is not None:
            out["present"] += 1
        out["octagon"][name] = d

    inc = root / "incoming"
    if inc.is_dir():
        out["incoming"] = sorted(
            p.name for p in inc.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    return out


def _issues(d: dict, ref: dict | None) -> list[str]:
    """Why this render does not belong with its family's reference.

    An absent reference yields no issues rather than blanket failure: we
    cannot say a file is off-generation when there is no generation to be
    off. That is a different problem and `survey` reports it separately.
    """
    if not ref or not d:
        return []
    out = []
    if ref["aspect"]:
        drift = abs(d["aspect"] - ref["aspect"]) / ref["aspect"]
        if drift > ASPECT_TOLERANCE:
            out.append(f"aspect {d['aspect']:.2f} vs {ref['aspect']:.2f} "
                       f"({drift:.0%} off — a different crop)")
    if ref["pixels"]:
        ratio = d["pixels"] / ref["pixels"]
        if ratio < MIN_PIXEL_RATIO:
            out.append(f"{ratio:.0%} of the reference's pixels")
    if ref["detail"]:
        ratio = d["detail"] / ref["detail"]
        if ratio < MIN_DETAIL_RATIO:
            out.append(f"detail {ratio:.0%} of reference (softer)")
    return out


def matched_colours(data: dict) -> list[str]:
    """Colours whose art matches the reference in EVERY family.

    This is the answer `VENUE_MATCHED` should hold. A colour is served
    site-wide, so one family's soft tile is enough to disqualify it —
    otherwise a baseball card and a football card on the same screen come
    from different shoots again, which is the original complaint.
    """
    ok = []
    for colour in COLOURS:
        good = True
        for family in FAMILIES:
            slot = (data["families"].get(family, {}).get("slots") or {}).get(colour)
            if slot is None or not slot.get("matches", False):
                good = False
                break
        if good:
            ok.append(colour)
    return ok


def served_by_site(app_js=None) -> list[str]:
    """The colours `VENUE_MATCHED` actually holds, read from the source.

    The measurement and the site can legitimately disagree. On 2026-08-14
    Ethan looked at a board of white-lit stadiums and asked for the colour
    back knowing the tiles are off-generation, which is his call to make —
    so this reads what is SERVED rather than assuming it equals what the
    measurement endorses.
    """
    from pathlib import Path as _P
    path = _P(app_js) if app_js else (
        _P(__file__).parent.parent / "web" / "js" / "app.js")
    try:
        src = path.read_text(encoding="utf-8")
        i = src.index("const VENUE_MATCHED = new Set(")
        block = src[i:src.index(")", i)]
    except (OSError, ValueError):
        return []
    return [c for c in COLOURS if f'"{c}"' in block]


def missing(data: dict) -> list[str]:
    """Filenames the kit still wants, in the order they should be made."""
    out = []
    for family in FAMILIES:
        slots = data["families"].get(family, {}).get("slots") or {}
        for colour in COLOURS:
            d = slots.get(colour)
            if d is None:
                out.append(f"variants/{family}-{colour}.jpg  (missing)")
            elif d.get("issues"):
                out.append(f"variants/{family}-{colour}.jpg  ({d['issues'][0]})")
    for name, d in (data.get("octagon") or {}).items():
        if d is None:
            out.append(f"variants/{name}.jpg  (missing)")
    return out
