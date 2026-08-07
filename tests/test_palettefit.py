"""The fixer must repair contrast without redesigning anything.

Written 2026-08-07 after a design pass darkened `--good` (Lc 59 -> 55) and
`--bad` (36 -> 33) and the ratchet caught it. Working new hex values out by
hand is arithmetic nobody should do twice, and doing it by eye is how the
ratchet came to exist.

Two properties matter and they pull against each other:

  * it has to actually clear the bar, on every ground, not just the one it
    solved against;
  * it must not touch anything else. Hue and chroma are design decisions.
    A fixer that edits colours nobody asked about produces a diff nobody
    reviews, which is the same failure as no fixer at all.

Run directly: `python3 tests/test_palettefit.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contrast as ct                                          # noqa: E402
import make_icon as mi                                         # noqa: E402
import palettefit as pf                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def _darken(css: str, ink: str, target: float) -> str:
    """Push one token down to a chosen Lc, holding hue and chroma — a
    stand-in for whatever a design pass did."""
    L, C, H = pf.srgb_to_oklch(mi.token(ink, css))
    _newL, rgb = pf.solve(target, C, H, mi.token(pf.BINDING_GROUND, css))
    hexv = "#%02X%02X%02X" % rgb
    out, n = re.subn(r"(--%s:\s*)(#[0-9A-Fa-f]{6})" % ink,
                     lambda m: m.group(1) + hexv, css, count=1)
    assert n == 1, ink
    return out


# --- the round trip ----------------------------------------------------------
def test_oklch_survives_a_round_trip():
    """Everything else rests on this. A conversion that drifts would move
    the hue while claiming to hold it."""
    for ink in ("good", "bad", "text", "brand"):
        rgb = mi.token(ink)
        L, C, H = pf.srgb_to_oklch(rgb)
        back = pf.oklch_to_srgb(L, C, H)
        assert max(abs(a - b) for a, b in zip(rgb, back)) <= 1, (ink, rgb, back)


def test_the_solver_hits_the_lc_it_was_asked_for():
    ground = mi.token(pf.BINDING_GROUND)
    for target in (30, 45, 60, 75):
        _L, rgb = pf.solve(target, 0.02, 84.0, ground)
        assert abs(abs(ct.lc(rgb, ground)) - target) < 0.5, target


# --- it repairs what the ratchet actually complains about --------------------
def test_a_darkened_token_is_brought_back_over_its_baseline():
    """The real case: --good at Lc 55 against a recorded 59."""
    css = _darken(CSS, "good", 55)
    rows = pf.plan(css=css)
    assert [r["ink"] for r in rows] == ["good"], rows
    fixed = pf.rewrite(css, rows)
    from tests.test_contrast import BASELINE, SLACK
    for g in ct.GROUNDS:
        got = abs(ct.lc(mi.token("good", fixed), mi.token(g, fixed)))
        assert got >= BASELINE[("good", g)] - SLACK, (g, got)


def test_it_clears_every_ground_not_only_the_one_it_solved_against():
    """It solves against --panel-3 alone. That is only valid because the
    lightest panel is the binding one; if it were not, three grounds would
    stay broken while the report claimed success."""
    css = _darken(_darken(CSS, "good", 50), "bad", 28)
    fixed = pf.rewrite(css, pf.plan(css=css))
    for ink in ("good", "bad"):
        vals = [abs(ct.lc(mi.token(ink, fixed), mi.token(g, fixed)))
                for g in ct.GROUNDS]
        assert min(vals) >= min(
            abs(ct.lc(mi.token(ink, CSS), mi.token(g, CSS)))
            for g in ct.GROUNDS) - 1.0, (ink, vals)


# --- and changes nothing else ------------------------------------------------
def test_hue_and_chroma_are_held_exactly():
    """The design decision survives; only the dimension contrast depends
    on moves."""
    css = _darken(CSS, "bad", 30)
    rows = pf.plan(css=css)
    fixed = pf.rewrite(css, rows)
    _L0, C0, H0 = pf.srgb_to_oklch(mi.token("bad", css))
    _L1, C1, H1 = pf.srgb_to_oklch(mi.token("bad", fixed))
    assert abs(C1 - C0) < 0.004, (C0, C1)
    assert abs(H1 - H0) < 1.0, (H0, H1)


def test_a_passing_token_is_left_alone():
    """The bug the first cut had: it compared the MAX baseline across
    grounds against the MIN current Lc, so `text` — 90 on bg, 89 on
    panel-2 — read as short and four passing tokens were proposed for
    rewriting."""
    assert pf.plan(css=CSS) == [], pf.plan(css=CSS)
    css = _darken(CSS, "good", 55)
    assert [r["ink"] for r in pf.plan(css=css)] == ["good"]


def test_only_the_named_token_changes_in_the_file():
    css = _darken(CSS, "good", 55)
    fixed = pf.rewrite(css, pf.plan(css=css))
    a = [l for l in css.split("\n")]
    b = [l for l in fixed.split("\n")]
    assert len(a) == len(b)
    differing = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert len(differing) == 1, [a[i] for i in differing]
    assert "--good" in a[differing[0]]


def test_the_light_theme_is_never_rewritten():
    """It has its own values and its own unmeasured contrast. Rewriting it
    from a dark-ground solve changes a colour nobody measured."""
    css = _darken(CSS, "good", 55)
    fixed = pf.rewrite(css, pf.plan(css=css))
    light = fixed[fixed.index(':root[data-theme="light"]'):]
    was = css[css.index(':root[data-theme="light"]'):]
    assert light == was


# --- what it refuses to do ---------------------------------------------------
def test_it_writes_nothing_without_apply():
    src = open(os.path.join(ROOT, "palettefit.py"), encoding="utf-8").read()
    main = src[src.index("def main("):]
    assert 'if not a.apply:' in main
    assert main.index("DRY RUN") < main.index('open(CSS_PATH, "w"')


def test_the_target_mode_is_opt_in():
    """--bad at Lc 45 rather than 36 is a visibly lighter red. A fixer must
    not make that call on the way past."""
    css = _darken(CSS, "bad", 30)
    floor_rows = pf.plan(css=css)
    target_rows = pf.plan(use_target=True, css=css)
    assert floor_rows[0]["bar"] < target_rows[0]["bar"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
