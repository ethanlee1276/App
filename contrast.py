#!/usr/bin/env python3
"""What the palette's text actually measures. APCA, not WCAG.

    python3 contrast.py
    python3 contrast.py --wcag        # both, side by side

Reads web/css/styles.css. Writes nothing, changes nothing.

WHY APCA AND NOT WCAG
---------------------
WCAG 2.x contrast is a ratio of relative luminances plus a constant, and it
is known to misjudge dark colour pairs — a pair can clear 4.5:1 near black
and still be hard to resolve. APCA (Andrew Somers / Myndex, the candidate
algorithm for WCAG 3) is perceptually uniform: Lc 60 means the same
readability wherever on the scale the pair sits. On a dark ground Lc comes
out negative, and the sign is polarity rather than badness.

The reference targets, from APCA's own guidance:

    |Lc| 90   preferred for body text
    |Lc| 75   minimum for body text
    |Lc| 60   larger or secondary text
    |Lc| 45   large or bold UI
    |Lc| 30   disabled or decorative
    |Lc| 15   the point of invisibility

WHAT IT FOUND, AND WHAT WAS DONE ABOUT IT
------------------------------------------
Measured 2026-08-07, the dark theme read:

    --text        Lc  90 on every ground     exactly the body target
    --brand       Lc  69                     comfortable for secondary
    --good        Lc  59                     secondary, just under
    --text-dim    Lc  51                     under the 60 secondary target
    --bad         Lc  36                     under the 45 large/bold target
    --text-mute   Lc  15                     the point of invisibility

`--text-mute` carried **223 uses** — 108 in the stylesheet, 114 in the
inline styles app.js writes, one in the social card — and not on
decoration: .section-title, .tile .k (the label on every metric),
.matchup .away, .pick .book, .game-sub.starters. Things a reader needs to
resolve.

NOT the WCAG-versus-APCA subtlety, though, and it is worth being exact:
--text-mute measured 2.57:1 in WCAG terms, which fails AA for both normal
(4.5) and large (3.0) text. Both algorithms agreed it was too faint. The
manual's point about WCAG flattering dark pairs is real, but this token
was not an example of it.

It could not be repaired by lightening one token, and that is the whole
reason it stayed open as long as it did: Lc 60 needs L 0.761, and
`--text-dim` was L 0.708, so the quiet tier would have ended up BRIGHTER
than the tier above it. The fault was one token doing two jobs —
decorative furniture, and readable secondary content — so the repair is a
fourth step rather than a brighter third one:

    --text        Lc 90    body text, preferred
    --text-dim    Lc 60    larger or secondary text     (was 51)
    --text-mute   Lc 45    large or bold UI             (was 15)
    --text-faint  Lc 30    disabled or decorative       (new)

APCA's own reference targets, one tier apart, each solved against
`--panel-3` because the lightest panel is where contrast is lowest and
therefore binds.

**The split defaults to readable.** Everything stayed on `--text-mute`
and rose to Lc 45; only five genuinely non-text marks moved down to
`--text-faint` — the card's 4px grade stripe, the parlay miss stripe, two
separator glyphs, and the empty-state icon. Misfiling something that way
leaves it too legible rather than invisible.

The disclosure chevron deliberately stayed on `--text-mute`: it is a
control affordance, and Lc 45 (large or bold UI) is exactly its target.

The light theme was NOT given the same ladder. Measured, its `--text-mute`
is already Lc 52-64 and its `--text-dim` Lc 76-87, both above target, so
copying the dark side's numbers across would have made paper worse. Only
the fourth tier is new there.

Still under target and left alone: `--bad` at Lc 36, below the 45
large/bold bar. That one is a colour with a job — negative EV and errors
read red — and moving it is a palette decision, not a hierarchy one.
"""

from __future__ import annotations

import argparse
import sys

import make_icon as _mi

#: APCA 0.1.9 (W3C draft). Named rather than inlined so a future reader can
#: see which revision these came from — the constants have moved before.
_TRC = 2.4
_R, _G, _B = 0.2126729, 0.7151522, 0.0721750
_NORM_BG, _NORM_TXT, _REV_TXT, _REV_BG = 0.56, 0.57, 0.62, 0.65
_BLK_THRS, _BLK_CLMP, _SCALE = 0.022, 1.414, 1.14
_OFFSET, _LO_CLIP, _DELTA_MIN = 0.027, 0.1, 0.0005

#: The reference targets, biggest first so a lookup returns the strictest
#: level a pair actually clears.
TARGETS = ((90, "body text, preferred"), (75, "body text, minimum"),
           (60, "larger or secondary text"), (45, "large or bold UI"),
           (30, "disabled or decorative"), (15, "point of invisibility"))

#: Which inks are checked against which grounds. Every real pairing on the
#: dark theme; anything not listed is not text on a surface.
GROUNDS = ("bg", "panel", "panel-2", "panel-3")
INKS = ("text", "text-dim", "text-mute", "text-faint",
        "brand", "good", "bad", "warn")


def luminance(rgb) -> float:
    """APCA's Y: a simple 2.4 exponent, NOT the piecewise sRGB curve, then
    a soft clamp so near-blacks do not run away."""
    r, g, b = (c / 255 for c in rgb)
    y = _R * r ** _TRC + _G * g ** _TRC + _B * b ** _TRC
    return y + (_BLK_THRS - y) ** _BLK_CLMP if y < _BLK_THRS else y


def lc(text, bg) -> float:
    """Lightness contrast. Negative means light ink on a dark ground."""
    yt, yb = luminance(text), luminance(bg)
    if abs(yb - yt) < _DELTA_MIN:
        return 0.0
    if yb > yt:                                    # dark ink, light ground
        s = (yb ** _NORM_BG - yt ** _NORM_TXT) * _SCALE
        return 0.0 if s < _LO_CLIP else (s - _OFFSET) * 100
    s = (yb ** _REV_BG - yt ** _REV_TXT) * _SCALE  # light ink, dark ground
    return 0.0 if s > -_LO_CLIP else (s + _OFFSET) * 100


def wcag(text, bg) -> float:
    """WCAG 2.x, for the comparison only. Never the verdict here."""
    def rel(c):
        out = []
        for x in (v / 255 for v in c):
            out.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    a, b = rel(text), rel(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def level(value: float) -> str:
    v = abs(value)
    for bar, name in TARGETS:
        if v >= bar:
            return name
    return "below the point of invisibility"


def audit(css: str | None = None) -> list[dict]:
    """Every ink-on-ground pair, worst first."""
    out = []
    for ink in INKS:
        try:
            ic = _mi.token(ink, css)
        except (KeyError, ValueError):
            continue
        for ground in GROUNDS:
            gc = _mi.token(ground, css)
            out.append({"ink": ink, "ground": ground,
                        "lc": lc(ic, gc), "wcag": wcag(ic, gc)})
    return sorted(out, key=lambda r: abs(r["lc"]))


def report(show_wcag: bool = False) -> int:
    rows = audit()
    print("=" * 74)
    print("TEXT CONTRAST — APCA, dark theme")
    print("=" * 74)
    print("  |Lc| 90 body preferred · 75 body minimum · 60 secondary")
    print("      45 large or bold UI · 30 decorative · 15 invisible")
    print()
    head = f"  {'ink':11}{'ground':10}{'Lc':>7}"
    if show_wcag:
        head += f"{'WCAG':>8}"
    print(head + "   clears")
    print("  " + "-" * (60 if show_wcag else 52))
    for r in rows:
        line = f"  {r['ink']:11}{r['ground']:10}{r['lc']:7.0f}"
        if show_wcag:
            line += f"{r['wcag']:8.2f}"
        print(line + f"   {level(r['lc'])}")
    print()

    # --text-faint is SUPPOSED to sit under the large/bold bar; that is its
    # whole job. Listing it as a problem every run is how a report teaches
    # someone to stop reading it.
    weak = [r for r in rows if abs(r["lc"]) < 45 and r["ink"] != "text-faint"]
    if weak:
        inks = sorted({r["ink"] for r in weak})
        print(f"  Below the large/bold UI bar: {', '.join(inks)}")
        print()
        print("  --bad is the one left, and it is a colour with a job:")
        print("  negative EV and errors read red. Moving it is a palette")
        print("  decision rather than a hierarchy one, so it is not")
        print("  something this tool should quietly pick for you.")
    else:
        print("  Every text pair clears the large/bold UI bar.")
    print()
    faint = [r for r in rows if r["ink"] == "text-faint"]
    if faint:
        lo = min(abs(r["lc"]) for r in faint)
        print(f"  --text-faint sits at Lc {lo:.0f} deliberately — decorative")
        print("  marks only (the grade stripes, two separator glyphs, the")
        print("  empty-state icon). Text on it would be a misfiling.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--wcag", action="store_true",
                   help="show WCAG 2.x beside APCA, for comparison only")
    a = p.parse_args(argv)
    return report(show_wcag=a.wcag)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
