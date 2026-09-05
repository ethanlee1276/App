"""A prior over zero teams drew a green tick for three weeks.

REPORTED FROM THE LIVE CFB BOARD, 2026-08-30, with the card circled:

    ✓ Preseason talent prior — 0 team(s)
      recruiting —   blue-chip 229   returning 106   portal 256
      ... Not loaded: talent.

A green check, a green left border, and the words "0 team(s)" and "Not
loaded" on the same card. Ethan: "why has this been saying zero teams
for like 3 weeks and have we been using any of its data."

TWO FAULTS, AND THEY ARE DIFFERENT SHAPES.

THE TICK. `available` was set to True unconditionally once the fetch did
not raise. CFBD answered `/talent` with HTTP 200 and an empty array,
which is not an exception, so the flag said the prior was available and
the page drew a success over a prior covering nobody. An empty
successful response and a full one are the same shape at every layer
between the API and the card; the only place the difference exists is
the row count, so that is what decides now.

THE UNUSED DATA. The other three layers arrived — 229 teams of
blue-chip ratio from `/recruiting/players?classification=HighSchool`,
which is exactly the high-school recruiting data. `talent_prior` loops
over the COMPOSITE's z-scores, so with the composite empty the loop
never ran and all 229 teams were computed and discarded.

Its docstring is right that blue-chip must not ADD to the composite —
the same star ratings counted twice. It says nothing about the composite
being ABSENT, and there the ratio is not a second view of a fact we
have, it is the only view. So it is now a fallback, FITTED ON ITS OWN
SCALE: 2.451 points per SD was measured against composite z-scores, and
reusing it for a different variable would be a slope fitted on one
population applied to another. If the blue-chip slope will not fit, the
prior stays off rather than borrowing one.

Run directly: `python3 tests/test_talent_empty.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.cfb import talent as T


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- the premise ----------------------------------------------------------
def test_an_empty_composite_produces_an_empty_prior():
    """The loop is over the composite's z-scores, so with none there is
    nothing to iterate — whatever else arrived."""
    blue = {f"T{i}": {"ratio": 0.4 + i * 0.001} for i in range(229)}
    assert T.talent_prior({}, T.PRIOR_FIT, blue) == {}


def test_blue_chip_alone_can_carry_a_prior_when_asked_to():
    """The same function, given the ratios as its first argument. No new
    machinery was needed — only the decision to fall back."""
    ratios = {f"T{i}": 0.4 + i * 0.001 for i in range(120)}
    assert len(T.talent_prior(ratios, T.PRIOR_FIT)) == 120


def test_blue_chip_still_never_adds_to_a_present_composite():
    """The docstring's rule, unchanged: with a composite present the
    ratio only shades it, because they are the same fact."""
    src = T.talent_prior.__doc__
    assert "does NOT add points" in src
    both = T.talent_prior({"A": 900.0, "B": 500.0}, T.PRIOR_FIT,
                          {"A": {"ratio": 0.9}, "B": {"ratio": 0.1}})
    assert set(both) == {"A", "B"}


# --- the tick -------------------------------------------------------------
def test_available_means_a_prior_is_in_force_not_that_the_fetch_survived():
    src = _src("cfb_build.py")
    assert 'in_force = bool(blend_report["teams"])' in src
    assert "available=in_force" in src
    assert "available=True" not in src


def test_a_prior_over_nobody_leaves_the_ratings_alone():
    """It used to publish `blended` regardless — a blend of results with
    an empty prior, which is the results, but named as though a prior had
    been applied."""
    assert "ratings=blended if in_force else ratings" in _src("cfb_build.py")


def test_the_card_does_not_draw_a_success_on_the_empty_branch():
    src = _src("web", "js", "app.js")
    at = src.index("function renderTalent()")
    body = src[at:src.index("if (!t.available)", at)
               + src[at:].index("return;\n  }")]
    empty = body[body.index("if (!t.available)"):]
    assert 'iconMark("warn")' in empty
    assert 'iconMark("check")' not in empty
    assert "--warn" in empty and "--good" not in empty


def test_the_card_says_which_feeds_answered_with_nothing():
    """A layer at zero fetched cleanly and had no rows, which is a
    different fault from one that failed and needs a different fix."""
    src = _src("web", "js", "app.js")
    assert "t.empty_layers" in src
    assert "not the same" in src


def test_the_build_publishes_the_empty_layers():
    assert "empty_layers=[" in _src("cfb_build.py")


# --- the fallback, and its guard ------------------------------------------
def test_the_fallback_only_runs_when_the_composite_is_empty():
    """Running it alongside a composite is the double count the
    docstring forbids."""
    src = _src("cfb_build.py")
    assert "if not prior and blue:" in src


def test_the_fallback_fits_its_own_slope():
    """THE LOAD-BEARING ONE. 2.451 pts/SD was fitted on composite
    z-scores; blue-chip ratio is a different variable."""
    src = _src("cfb_build.py")
    assert "bc_fit = (T.fit_points_per_sd(" in src
    assert "cfbd.blue_chip_ratio(y)" in src


def test_an_unfitted_slope_is_refused_rather_than_borrowed():
    src = _src("cfb_build.py")
    assert "if bc_fit is not None and bc_fit.fitted:" in src


def test_the_fit_helper_is_generic_over_whatever_table_it_is_given():
    """No new function was needed — `team_seasons_from_db` z-scores its
    input, so blue-chip ratios in the same shape fit the same way."""
    import inspect
    src = inspect.getsource(T.team_seasons_from_db)
    assert "_z_scores(table)" in src


def test_the_report_names_which_source_carried_the_prior():
    """The two are not the same claim and the weaker one must say so."""
    src = _src("cfb_build.py")
    assert "prior_source=source" in src
    assert 'source = "composite"' in src
    assert 'fit, source = bc_fit, "blue_chip"' in src


def test_the_note_says_when_the_coarser_source_was_used():
    assert "Built from the BLUE-CHIP RATIO" in _src("cfb_build.py")


def test_the_note_no_longer_claims_the_data_is_used_for_nothing():
    """It was, before the fallback. Leaving that sentence in would be
    the page describing a version of itself that no longer exists."""
    assert "is currently used for nothing" not in _src("cfb_build.py")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
