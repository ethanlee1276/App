#!/usr/bin/env python3
"""Put a token back on its contrast target without changing its colour.

    python3 palettefit.py                 # what it WOULD do. Writes nothing.
    python3 palettefit.py --apply         # edit web/css/styles.css in place
    python3 palettefit.py --target        # aim at the APCA tier, not the floor

WHAT THIS IS FOR
----------------
`contrast.py` measures and `tests/test_contrast.py` ratchets, so a pass that
darkens a token fails the suite with a list like

    contrast regressed: [(('good','bg'), 59, 55), (('bad','bg'), 36, 33)]

and then somebody has to work out new hex values by hand. That is arithmetic
nobody should do twice, and doing it by eye is how the ratchet got installed
in the first place.

HOW IT KEEPS THE DESIGN INTENT
------------------------------
APCA contrast is very nearly a function of LIGHTNESS alone. So the repair
converts the token to OKLCH, **holds H and C exactly**, and moves only L
until the pair clears its bar. A hue chosen in a design pass survives
untouched; a chroma chosen in a design pass survives untouched. Only the
one dimension that contrast actually depends on moves.

That is the whole reason this is safe to run on someone else's colour
choices — including choices this file has never seen.

WHICH BAR
---------
Default is the RATCHET floor: the value `tests/test_contrast.py` recorded,
which is the bar the suite is actually failing against. Restoring that is
the minimal repair and makes no design decision.

`--target` instead aims at the token's APCA tier. That is a bigger and more
visible change — `--bad` at Lc 45 rather than 36 is a noticeably lighter
red — so it is opt-in rather than something a fixer quietly does on the way
past.

Solved against `--panel-3`, the lightest dark ground, because the lightest
panel is where contrast is lowest and therefore binds. Plus a little
headroom so rounding never prints a token as sitting below its own bar.

Dark theme only: `make_icon.token` reads the FIRST `:root`, so that is what
`contrast.py` audits and what the ratchet holds. The light theme is not
measured and is not touched.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import re
import sys

import contrast as ct
import make_icon as mi

CSS_PATH = "web/css/styles.css"

#: Ground the solve runs against. The lightest dark panel gives the lowest
#: contrast, so clearing it clears every other ground too.
BINDING_GROUND = "panel-3"

#: A token that lands exactly on its bar rounds below it half the time.
HEADROOM = 0.8

#: APCA tier per token, used by --target. Same table as contrast.py's.
TARGETS = {"text": 90, "text-dim": 60, "text-mute": 45, "text-faint": 30,
           "good": 60, "bad": 45, "brand": 60, "warn": 60}


def srgb_to_oklch(rgb) -> tuple[float, float, float]:
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def oklch_to_srgb(L: float, C: float, H: float) -> tuple[int, int, int]:
    a = C * math.cos(math.radians(H))
    b = C * math.sin(math.radians(H))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(c):
        c = max(0.0, min(1.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return int(round(c * 255))
    return enc(r), enc(g), enc(bb)


def solve(target: float, chroma: float, hue: float, ground) -> tuple:
    """Lowest L whose |Lc| against ``ground`` clears ``target``.

    Bisection rather than a formula: APCA's soft clamp near black makes it
    non-analytic, and 60 iterations is instant.
    """
    lo, hi = 0.05, 0.99
    for _ in range(60):
        mid = (lo + hi) / 2
        if abs(ct.lc(oklch_to_srgb(mid, chroma, hue), ground)) < target:
            lo = mid
        else:
            hi = mid
    L = (lo + hi) / 2
    return L, oklch_to_srgb(L, chroma, hue)


def _ratchet():
    """The recorded baseline and the slip the test actually tolerates."""
    try:
        from tests.test_contrast import BASELINE, SLACK
    except Exception:                                    # noqa: BLE001
        return {}, 1.0
    return BASELINE, SLACK


def plan(use_target: bool = False, css: str | None = None) -> list[dict]:
    """One row per token that is short of its bar.

    **Per (ink, ground) PAIR, which is how the ratchet reads.** The first
    cut took the max baseline across grounds and compared it against the
    min current Lc, so any token whose baseline differs by a point between
    grounds — `text` is 90 on `bg` and 89 on `panel-2` — looked short by
    construction. It proposed rewriting four tokens that were passing.

    A fixer that edits colours nobody asked it to touch is worse than no
    fixer, because the diff stops being reviewable.
    """
    baseline, slack = _ratchet()
    ground = mi.token(BINDING_GROUND, css)
    out = []
    for ink in ct.INKS:
        try:
            rgb = mi.token(ink, css)
        except (KeyError, ValueError):
            continue

        if use_target:
            bar = TARGETS.get(ink)
            if not bar:
                continue
            short = any(abs(ct.lc(rgb, mi.token(g, css))) < bar
                        for g in ct.GROUNDS)
        else:
            # Exactly the test's own condition, pair by pair.
            short = any(
                abs(ct.lc(rgb, mi.token(g, css))) < baseline[(ink, g)] - slack
                for g in ct.GROUNDS if (ink, g) in baseline)
            bar = baseline.get((ink, BINDING_GROUND))
        if not short or not bar:
            continue

        now = min(abs(ct.lc(rgb, mi.token(g, css))) for g in ct.GROUNDS)
        L, C, H = srgb_to_oklch(rgb)
        newL, new_rgb = solve(bar + HEADROOM, C, H, ground)
        after = min(abs(ct.lc(new_rgb, mi.token(g, css))) for g in ct.GROUNDS)
        out.append({"ink": ink, "bar": bar, "now": now, "after": after,
                    "was": "#%02X%02X%02X" % rgb,
                    "new": "#%02X%02X%02X" % new_rgb,
                    "L": L, "newL": newL, "C": C, "H": H})
    return out


def rewrite(css: str, rows: list[dict]) -> str:
    """Replace each token's value in the FIRST :root only.

    The light theme is a separate block with its own values and its own
    (unmeasured) contrast; rewriting it from a dark-ground solve would be
    changing a colour nobody measured to fix a number nobody read.
    """
    end = css.index("}", css.index(":root"))
    head, tail = css[:end], css[end:]
    for r in rows:
        pat = re.compile(r"(--%s:\s*)(#[0-9A-Fa-f]{6})" % re.escape(r["ink"]))
        head, n = pat.subn(lambda m: m.group(1) + r["new"], head, count=1)
        if not n:
            raise SystemExit(
                f"could not find --{r['ink']} as a hex value in the first "
                f":root; it may be written as oklch() — fix that one by hand")
    return head + tail


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--apply", action="store_true",
                   help="write the new values into " + CSS_PATH)
    p.add_argument("--target", action="store_true",
                   help="aim at the APCA tier rather than the ratchet floor "
                        "(a bigger, visible change — opt in on purpose)")
    a = p.parse_args(argv)

    rows = plan(use_target=a.target)
    bar_name = "APCA tier" if a.target else "ratchet floor"
    print("=" * 70)
    print(f"PALETTE FIT — lightness only, against the {bar_name}")
    print("=" * 70)
    if not rows:
        print("  Every token already clears its bar. Nothing to do.")
        return 0
    print(f"  {'token':11}{'bar':>5}{'now':>6}{'after':>7}   was -> new")
    print("  " + "-" * 52)
    for r in rows:
        print(f"  {r['ink']:11}{r['bar']:5.0f}{r['now']:6.0f}{r['after']:7.0f}"
              f"   {r['was']} -> {r['new']}")
    print()
    print("  Hue and chroma are held exactly; only lightness moves, because")
    print("  that is the dimension APCA contrast actually depends on. The")
    print("  colour a design pass chose survives.")
    print()
    for r in rows:
        print(f"  --{r['ink']:11} L {r['L']:.3f} -> {r['newL']:.3f}   "
              f"(C {r['C']:.4f}, H {r['H']:.1f} unchanged)")
    print()
    if not a.apply:
        print("  DRY RUN — nothing written. Re-run with --apply.")
        return 0
    css = open(CSS_PATH, encoding="utf-8").read()
    open(CSS_PATH, "w", encoding="utf-8").write(rewrite(css, rows))
    print(f"  wrote {CSS_PATH}")
    print("  now run: python3 tests/test_contrast.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
