"""The projection with no floor under it.

Every look-back window in `compute_form` is an average of the SAME games,
so weighting them differently cannot rescue a short log. A hitter with
three quiet games came out at three quiet games, and there was nothing
underneath: `MLB_WINDOW_WEIGHTS` gives "career" a weight of zero.

That zero was CORRECT for what career_avg used to be. MLB built it as the
mean of the same fifteen logs the blend was about to weight — an anchor
made out of the thing it was supposed to anchor — so giving it weight
would have changed nothing.

The live sim gate is what surfaced it, and not as a sim problem. Across
three runs it kept failing on hitters whose projected per-game hits, over
the plate appearances their batting spot gets, implied batting averages no
hitter can have: Carlos Cortes at .014, Justin Foscue at .030, Tristan
Peters at .060, Nicky Lopez at .053, Donovan Walton at .078. Those are the
numbers the BOARD prices from, so it outlives the reconciliation entirely.

Two fixes, and the first is what made the second possible:

  * `career_avg` now spans the season, not the form window. The gameLog
    response already contained it — parse_game_log was truncating to
    fifteen and the untruncated parse costs no extra request.
  * the blend shrinks toward it by how thin the window is, w = n/(n+k).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.form import (compute_form, MLB_WINDOW_WEIGHTS,      # noqa: E402
                         CAREER_PRIOR_GAMES)
from engine.models import GameLog                               # noqa: E402

#: Plate appearances a mid-order spot gets, for turning a per-game hits
#: projection into the batting average that makes it obviously wrong.
PA = 3.9


def _logs(values):
    return [GameLog(week=i, opponent="X", value=float(v))
            for i, v in enumerate(values)]


def _form(values, prior=None, prior_n=0):
    return compute_form(_logs(values), prior if prior is not None else 0.0,
                        None, weights=MLB_WINDOW_WEIGHTS,
                        prior=prior, prior_n=prior_n,
                        prior_games=CAREER_PRIOR_GAMES)


# --- the defect ------------------------------------------------------------
def test_an_unanchored_short_log_projects_a_batting_average_of_zero():
    """The regression, stated as the thing a bettor would see. With no
    prior supplied there is no floor, and three quiet games from a .250
    hitter price him at .000."""
    bare = compute_form(_logs([0, 0, 0]), 0.95, None,
                        weights=MLB_WINDOW_WEIGHTS)
    assert bare.mean == 0.0
    assert bare.shrunk_to is None


def test_a_season_behind_the_window_puts_a_floor_under_it():
    f = _form([0, 0, 0], prior=0.95, prior_n=60)
    assert f.mean / PA > 0.15, f.mean          # a hitter, not a zero
    assert f.shrunk_to == 0.95


def test_every_hitter_the_live_gate_flagged_comes_back_into_range():
    """The five real shapes, each against a season rate an everyday player
    would carry. None of them should still price under .100."""
    for values, season in (([1, 0, 0, 0], 0.90),          # Cortes
                           ([0, 0, 1, 0, 0, 0], 0.85),    # Foscue
                           ([0, 1, 0, 0, 1, 0, 0], 0.88),  # Peters
                           ([0, 0, 0, 1, 0], 0.80),       # Lopez
                           ([1, 0, 0, 1, 0, 0, 0], 0.92)):  # Walton
        f = _form(values, prior=season, prior_n=90)
        assert f.mean / PA > 0.10, (values, f.mean / PA)


# --- and does not become a different model ---------------------------------
def test_a_regular_on_form_is_barely_moved():
    """The control. The shrink is scoped to a defect, not to replacing the
    recency curve docs/MLB_MODEL.md specifies — and for the hitter it is
    likeliest to harm, a regular whose recent games look like his season,
    the two numbers agree and it changes nothing."""
    window = [1, 1, 0, 1, 2, 0, 1, 1, 0, 1, 2, 1, 0, 1, 1]
    before = compute_form(_logs(window), 1.05, None,
                          weights=MLB_WINDOW_WEIGHTS).mean
    after = _form(window, prior=1.05, prior_n=150).mean
    assert abs(after - before) / before < 0.15, (before, after)


def test_a_full_window_keeps_most_of_its_own_number():
    """k is half a form window on purpose. Fifteen games keep roughly two
    thirds of their own weight; the textbook empirical-Bayes k for batting
    rates is nearer 40, which would leave every hitter at a quarter his own
    form and is a far larger claim than this fix is making."""
    assert CAREER_PRIOR_GAMES == 8.0
    w = 15 / (15 + CAREER_PRIOR_GAMES)
    assert 0.6 < w < 0.7


def test_a_genuinely_cold_fifteen_games_is_still_allowed_to_be_cold():
    """Fifteen hitless games is evidence, not noise. The shrink must not
    launder a real slump back up to league average."""
    f = _form([0] * 15, prior=0.95, prior_n=120)
    assert f.mean / PA < 0.13, f.mean / PA


# --- it declines when the anchor is not one --------------------------------
def test_a_season_no_longer_than_the_window_anchors_nothing():
    """Exactly the state this shipped in: career_avg was the mean of the
    same fifteen logs. An anchor carrying nothing the blend does not
    already have must stand down rather than pretend."""
    for prior_n in (0, 3, 6):
        f = _form([0, 1, 0, 0, 0, 0], prior=0.30, prior_n=prior_n)
        assert f.shrunk_to is None, prior_n


def test_a_missing_or_zero_season_rate_is_not_treated_as_a_measurement():
    assert _form([1, 0, 1], prior=None, prior_n=90).shrunk_to is None
    assert _form([1, 0, 1], prior=0.0, prior_n=90).shrunk_to is None


def test_the_weight_uses_the_windows_own_sample_not_the_priors():
    """A bug this shipped with for one commit: weighting a three-game
    estimate by the SIXTY games belonging to the number it was being
    shrunk toward. It left a hitless three-game log at 0.38 where the
    arithmetic wants 0.88."""
    f = _form([0, 0, 0], prior=0.95, prior_n=60)
    expect = (3 / (3 + CAREER_PRIOR_GAMES)) * 0.0 + \
             (CAREER_PRIOR_GAMES / (3 + CAREER_PRIOR_GAMES)) * 0.95
    assert abs(f.mean - expect) < 1e-9, (f.mean, expect)


# --- the other sports are untouched ----------------------------------------
def test_no_other_sport_is_re_priced_by_this():
    """The shrink is opt-in per caller. NFL, CFB, NBA and WNBA carry the
    same gap and were NOT changed here — that is a separate decision about
    somebody's money, not a free rider on this one."""
    from engine.form import WINDOW_WEIGHTS
    nfl = compute_form(_logs([0, 0, 0]), 60.0, None, weights=WINDOW_WEIGHTS)
    assert nfl.shrunk_to is None


def test_the_mlb_projection_path_asks_for_the_shrink():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "mlb", "projection.py"),
               encoding="utf-8").read()
    i = src.index("form = compute_form(")
    assert "prior_games=CAREER_PRIOR_GAMES" in src[i:i + 500]
    assert "career_games" in src[i:i + 500]


def test_the_season_rate_is_parsed_from_the_same_cached_response():
    """It has to cost nothing. gameLog already returns season-to-date and
    parse_game_log was throwing it away at fifteen; a second parse of the
    response already in hand is free, a second request would not be."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "mlb", "sources", "statslogs.py"),
               encoding="utf-8").read()
    i = src.index("def _add_prop(")
    body = src[i:i + 2500]
    assert body.count("fetch_game_log(") == 1, "one request, two parses"
    assert "limit=None" in body
    assert "career_games=" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
