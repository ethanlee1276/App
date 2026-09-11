"""Text contrast, measured rather than eyeballed — and pinned where it is.

APCA rather than WCAG because the ground is dark, and WCAG 2.x is known to
misjudge dark pairs. On a dark ground Lc is negative; the sign is polarity,
not badness.

This file was a RATCHET holding a fault open: `--text-mute` measured Lc 15,
the point of invisibility, across 223 uses, and could not be repaired by
lightening it — Lc 60 needs L 0.761 against `--text-dim` at L 0.708, so the
quiet tier would have ended up brighter than the tier above it.

It has since been split, so the file now pins a LADDER as well as a floor:

    --text        Lc 90    body text, preferred
    --text-dim    Lc 60    larger or secondary text
    --text-mute   Lc 45    large or bold UI
    --text-faint  Lc 30    disabled or decorative

The ratchet stays, because a ladder that is only correct on the day it was
built is not worth having. What is new is that the ORDER is pinned too: the
original fault was a hierarchy that could invert, and a test that only
checks floors would let that happen again with every tier still passing.

Run directly: `python3 tests/test_contrast.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contrast as ct                                           # noqa: E402
import make_icon as mi                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Re-measured 2026-08-07 after the split. A pair may improve freely;
#: dropping more than a point below its recorded value fails. Two decimal
#: places would make this brittle against a one-bit rounding change, so it
#: is whole Lc.
BASELINE = {
    # Re-measured 2026-08-11, the NEW LOOK re-baseline (Ethan's render:
    # violet-cast near-blacks, violet accent). Every TEXT tier measured
    # equal or better than the 08-07 numbers. --brand fell from 68 to 32
    # BY DESIGN: the old brand was amber and painted text; the violet
    # brand is an ACCENT (borders, fills, glows) and its text duty moved
    # to --brand-2 (Lc ~50, checked in the audit's floor below) — every
    # `color: var(--brand)` in the sheet was switched to --brand-2 in
    # the same commit as this table.
    ("text", "bg"): 99, ("text", "panel"): 98,
    ("text", "panel-2"): 98, ("text", "panel-3"): 97,
    ("brand", "bg"): 32, ("brand", "panel"): 32,
    ("brand", "panel-2"): 31, ("brand", "panel-3"): 30,
    # RECORDED 2026-08-23 rather than excused. It used to be skipped
    # below on the grounds that it was "the same hex as brand" — true of
    # the amber era and false since. A pair nobody measures is a pair
    # that can rot, and this one is now the site's only near-collision
    # (see --warn's note in the stylesheet), which is exactly the pair
    # worth watching.
    ("warn", "bg"): 60, ("warn", "panel"): 60,
    ("warn", "panel-2"): 59, ("warn", "panel-3"): 59,
    ("text-dim", "bg"): 67, ("text-dim", "panel"): 66,
    ("text-dim", "panel-2"): 66, ("text-dim", "panel-3"): 65,
    ("good", "bg"): 57, ("good", "panel"): 57,
    ("good", "panel-2"): 56, ("good", "panel-3"): 55,
    ("text-mute", "bg"): 48, ("text-mute", "panel"): 47,
    ("text-mute", "panel-2"): 47, ("text-mute", "panel-3"): 46,
    ("bad", "bg"): 37, ("bad", "panel"): 37,
    ("bad", "panel-2"): 36, ("bad", "panel-3"): 35,
    ("text-faint", "bg"): 33, ("text-faint", "panel"): 32,
    ("text-faint", "panel-2"): 32, ("text-faint", "panel-3"): 31,
}
#: How far a pair may slip before it counts as a regression.
SLACK = 1.0

#: The ladder, quiet to loud, with the APCA target each tier is solved to.
#: Pinned as an ORDER and not only as four floors: the original fault was a
#: hierarchy that could invert, and four independent floor checks would let
#: that happen again with every one of them still green.
#:
#: `--text` is 89 rather than 90 because it was NOT re-solved in this pass.
#: It measures 89.9 on --panel-2 — a rounding hair under APCA's *preferred*
#: body bar, where the actual minimum for body text is 75. Moving the colour
#: every line of prose is set in is a bigger change than a hierarchy repair,
#: so it keeps the value it has had and the tolerance the old body-text test
#: already used.
LADDER = (("text-faint", 30), ("text-mute", 45),
          ("text-dim", 60), ("text", 89))


# --- the algorithm ------------------------------------------------------------
def test_apca_matches_known_reference_pairs():
    """Black on white and white on black are the two values every APCA
    implementation agrees on. If these drift the constants are wrong and
    every number below is decoration."""
    black, white = (0, 0, 0), (255, 255, 255)
    assert 105 < ct.lc(black, white) < 108, ct.lc(black, white)
    assert -108 < ct.lc(white, black) < -105, ct.lc(white, black)


def test_the_sign_is_polarity_not_badness():
    """Light ink on a dark ground is negative by construction. A reader who
    takes the minus for a failure will 'fix' the whole dark theme."""
    assert ct.lc((255, 255, 255), (0, 0, 0)) < 0
    assert ct.lc((0, 0, 0), (255, 255, 255)) > 0
    assert ct.level(-90) == ct.level(90)


def test_identical_colours_score_zero_rather_than_dividing():
    assert ct.lc((30, 30, 30), (30, 30, 30)) == 0.0


def test_the_near_black_clamp_is_applied():
    """Without the soft clamp, luminance near zero runs away and every
    dark-on-dark pair scores as though it were readable."""
    assert ct.luminance((0, 0, 0)) > 0
    assert ct.luminance((0, 0, 0)) < 0.01


# --- the ratchet --------------------------------------------------------------
def test_no_pair_has_got_fainter():
    """The point of the file. Any pair may improve; none may slip."""
    now = {(r["ink"], r["ground"]): abs(r["lc"]) for r in ct.audit()}
    worse = []
    for key, was in BASELINE.items():
        assert key in now, f"{key} vanished from the audit"
        if now[key] < was - SLACK:
            worse.append((key, was, round(now[key])))
    assert not worse, f"contrast regressed: {worse}"


def test_the_baseline_covers_every_pair_the_audit_reports():
    """A new ink or ground must be recorded, not silently unmeasured."""
    now = {(r["ink"], r["ground"]) for r in ct.audit()}
    missing = now - set(BASELINE)
    assert not missing, f"unrecorded pairs: {sorted(missing)}"


def test_body_text_still_clears_the_body_target():
    """--text is the one that carries real prose, and it sits exactly on
    the preferred bar with no margin. If anything is going to be defended
    it is this."""
    for ground in ct.GROUNDS:
        v = abs(ct.lc(mi.token("text"), mi.token(ground)))
        assert v >= 89, f"--text on --{ground} fell to Lc {v:.0f}"


# --- what it refuses to do ----------------------------------------------------
def test_it_reports_and_changes_nothing():
    src = open(os.path.join(ROOT, "contrast.py"), encoding="utf-8").read()
    for forbidden in ("write_text", "open(", "UPDATE ", "INSERT "):
        assert forbidden not in src.split('"""')[2], forbidden


def test_every_tier_clears_the_target_it_was_solved_to():
    """Each value carries ~0.8 Lc of headroom for exactly this: solved to
    45.0 on the nose, --text-mute measured 44.7 on --panel-3 and the audit
    filed it as decorative."""
    for ink, target in LADDER:
        for ground in ct.GROUNDS:
            v = abs(ct.lc(mi.token(ink), mi.token(ground)))
            assert v >= target, f"--{ink} on --{ground} is Lc {v:.1f} < {target}"


def test_the_ladder_cannot_invert():
    """The fault that started this was a hierarchy that could not be
    repaired without turning over. Four floor checks would all stay green
    through an inversion; the ORDER is the thing to pin."""
    for ground in ct.GROUNDS:
        got = [abs(ct.lc(mi.token(ink), mi.token(ground)))
               for ink, _t in LADDER]
        assert got == sorted(got), f"the ladder inverted on --{ground}: {got}"


def test_the_tiers_are_far_enough_apart_to_read_as_different():
    """Adjacent tiers 3 Lc apart are one tier with two names, which is how
    a hierarchy quietly becomes decoration again."""
    for ground in ct.GROUNDS:
        got = [abs(ct.lc(mi.token(ink), mi.token(ground)))
               for ink, _t in LADDER]
        gaps = [b - a for a, b in zip(got, got[1:])]
        assert min(gaps) >= 10, f"--{ground} tiers too close: {gaps}"


def test_the_split_defaulted_to_readable():
    """The safety property worth keeping: everything stayed on the
    readable tier and only genuinely non-text marks were demoted. If a
    later pass starts moving text down, this is the number that moves."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    faint = css.count("var(--text-faint)")
    mute = css.count("var(--text-mute)")
    assert faint <= 8, f"{faint} uses of --text-faint — text is being demoted"
    assert mute > 90, f"only {mute} uses left on --text-mute"


def test_the_disclosure_chevron_stayed_readable():
    """It is a control affordance, not decoration, and Lc 45 is its
    target. Demoting it would make the thing that says a section opens
    fainter than the section."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".pz-runner > summary::after")
    block = css[i:css.index("}", i)]
    assert "var(--text-mute)" in block
    assert "var(--text-faint)" not in block


def test_the_light_theme_was_not_given_the_dark_ladder():
    """Paper never had the fault — measured, its --text-mute is already
    Lc 52-64 — so copying the dark numbers across would have made it
    worse. Only the fourth tier is new there."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    light = css[css.index(':root[data-theme="light"]'):]
    light = light[:light.index("}")]
    assert "--text-faint:" in light
    assert "--text-dim: #3E3A31;" in light, "the light dim tier moved"


def test_the_wcag_comparison_is_labelled_as_not_the_verdict():
    """WCAG is shown for context. On the palette as it was, both
    algorithms agreed --text-mute was too faint — 2.57:1 fails AA for
    large text too — so it was NOT an example of WCAG flattering a dark
    pair, and the docstring says so rather than borrowing the manual's
    argument."""
    flat = " ".join(ct.__doc__.split())
    assert "not an example of it" in flat
    assert "for the comparison only" in ct.wcag.__doc__


def test_the_history_of_the_repair_is_written_down():
    """A reader seeing a tidy four-tier ladder will not know it was ever
    a trap, and 'why is there a fourth one' is exactly the question that
    gets answered by deleting it."""
    flat = " ".join(ct.__doc__.split())
    assert "0.761" in flat and "0.708" in flat, "the two lightnesses"
    assert "223" in flat, "how many call sites were affected"
    assert "hierarchy" in flat


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
