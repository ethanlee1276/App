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

WHAT IT FOUND, AND WHAT IT DID NOT
----------------------------------
Run against the dark theme:

    --text        Lc  90 on every ground     exactly the body target
    --brand       Lc  69                     comfortable for secondary
    --good        Lc  59                     secondary, just under
    --text-dim    Lc  51                     under the 60 secondary target
    --bad         Lc  36                     under the 45 large/bold target
    --text-mute   Lc  15                     the point of invisibility

`--text-mute` is used 108 times, and not on decoration: .section-title,
.tile .k (the label on every metric), .matchup .away, .pick .book,
.game-sub.starters. Those are things a reader needs to resolve.

NOT the WCAG-versus-APCA subtlety, though, and it is worth being exact:
--text-mute measures 2.57:1 in WCAG terms, which fails AA for both normal
(4.5) and large (3.0) text. Both algorithms agree it is too faint. The
manual's point about WCAG flattering dark pairs is real, but this token is
not an example of it.

WHY THIS TOOL DOES NOT ALSO FIX IT
-----------------------------------
Reaching Lc 60 would need `--text-mute` at L 0.761. `--text-dim` sits at
L 0.708. The quiet tier would end up BRIGHTER than the tier above it and
the hierarchy would invert.

So the fault is not the colour, it is that one token is doing two jobs:
genuinely decorative furniture, and readable secondary content. Splitting
those is a design decision about hierarchy, with 108 call sites behind it,
and it belongs to a person rather than to a script that can only see
numbers.

What this ships instead is the measurement, so the numbers are visible and
a test can keep them from drifting further down.
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
INKS = ("text", "text-dim", "text-mute", "brand", "good", "bad", "warn")


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

    weak = [r for r in rows if abs(r["lc"]) < 45]
    if weak:
        inks = sorted({r["ink"] for r in weak})
        print(f"  Below the large/bold UI bar: {', '.join(inks)}")
        print()
        print("  See this module's docstring before changing any of them —")
        print("  --text-mute cannot reach the secondary-text target without")
        print("  becoming brighter than --text-dim, so the repair is a")
        print("  hierarchy decision rather than a colour one.")
    else:
        print("  Every pair clears the large/bold UI bar.")
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
