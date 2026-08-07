"""Text contrast, measured rather than eyeballed — and pinned where it is.

APCA rather than WCAG because the ground is dark, and WCAG 2.x is known to
misjudge dark pairs. On a dark ground Lc is negative; the sign is polarity,
not badness.

This file is deliberately a RATCHET, not a standard. It records what the
palette measures today and fails if anything gets fainter. It does not
demand that `--text-mute` reach a target, because it cannot: Lc 60 would
need L 0.761 against `--text-dim` at L 0.708, so the quiet tier would end
up brighter than the tier above it. The fault is one token doing two jobs —
decorative furniture and readable secondary content, across 108 call sites
— and splitting that is a hierarchy decision for a person.

What a ratchet buys is that the decision stays open instead of quietly
getting worse while nobody is looking.

Run directly: `python3 tests/test_contrast.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contrast as ct                                           # noqa: E402
import make_icon as mi                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Measured 2026-08-07. A pair may improve freely; dropping more than a
#: point below its recorded value fails. Two decimal places would make this
#: brittle against a one-bit rounding change, so it is whole Lc.
BASELINE = {
    ("text", "bg"): 90, ("text", "panel"): 90,
    ("text", "panel-2"): 90, ("text", "panel-3"): 90,
    ("brand", "bg"): 69, ("brand", "panel"): 68,
    ("brand", "panel-2"): 68, ("brand", "panel-3"): 68,
    ("good", "bg"): 59, ("good", "panel"): 59,
    ("good", "panel-2"): 59, ("good", "panel-3"): 59,
    ("text-dim", "bg"): 51, ("text-dim", "panel"): 51,
    ("text-dim", "panel-2"): 51, ("text-dim", "panel-3"): 50,
    ("bad", "bg"): 36, ("bad", "panel"): 36,
    ("bad", "panel-2"): 36, ("bad", "panel-3"): 35,
    ("text-mute", "bg"): 15, ("text-mute", "panel"): 15,
    ("text-mute", "panel-2"): 15, ("text-mute", "panel-3"): 14,
}
#: How far a pair may slip before it counts as a regression.
SLACK = 1.0


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
    # warn is the same hex as brand, so it doubles up harmlessly
    missing = {k for k in missing if k[0] != "warn"}
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


def test_the_reason_it_does_not_auto_fix_is_written_down():
    """--text-mute cannot reach the secondary target without passing
    --text-dim, so the repair inverts the hierarchy. A future reader who
    only sees 'Lc 15' will otherwise just make it lighter."""
    flat = " ".join(ct.__doc__.split())
    # Assert the CONTENT, not a phrasing. Naming an exact sentence is how
    # four other tests in this repo went red on a reflow that changed
    # nothing.
    assert "0.761" in flat and "0.708" in flat, "the two lightnesses"
    assert "BRIGHTER than the tier above it" in flat
    assert "hierarchy" in flat and "108 call sites" in flat


def test_the_wcag_comparison_is_labelled_as_not_the_verdict():
    """WCAG is shown for context. On this palette both algorithms agree
    --text-mute is too faint — 2.57:1 fails AA for large text too — so it
    is NOT an example of WCAG flattering a dark pair, and the docstring
    says so rather than borrowing the manual's argument."""
    flat = " ".join(ct.__doc__.split())
    assert "not an example of it" in flat
    assert "for the comparison only" in ct.wcag.__doc__


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
