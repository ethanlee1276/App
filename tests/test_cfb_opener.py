"""The college board prices on the opening Saturday.

Dress-rehearsed 2026-08-19, ten days before the opener, the same way the
NFL Week-1 gap was found — and it found the same shape of bug in a
different sport.

CFB rates on THIS SEASON ONLY, deliberately: college rosters turn over
about a quarter a year, so blending six ingested seasons would rate a
team on players who have graduated. The recruiting prior exists to cover
the window that leaves — the weeks when the current season is too young
to say anything. `engine/cfb/talent.py` says so in a comment above the
exact loop that got it wrong:

    # Teams with a prior but no games yet exist in week 1 and are the
    # whole reason the prior is here.
    for team, p in prior.items():
        if team not in blended:
            report["prior_only"] += 1

It counted them and threw them away. `blended` is keyed off the RESULTS
ratings, so on the opening Saturday — when no team has played and
`ratings` is empty — every team's prior was computed, reported in
`prior_only`, and dropped. Zero ratings attached. No spread, no total, no
moneyline, on the one weekend the prior was built for.

Invisible in November, when every team has results and that loop matches
nothing. Which is why it survived a season of tests.

WHAT THE PRIOR IS ALLOWED TO SAY is the other half of this. Only the NET
rating comes from it. Offense and defense stay at league average because
a recruiting composite says a roster is good, not that it scores 34 a
game — and `games=0` is carried honestly, so every downstream weight can
see how little is behind the number.

Run directly: `python3 tests/test_cfb_opener.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import teamrates                                    # noqa: E402
from engine.cfb import ratings as cfbratings                    # noqa: E402
from engine.cfb import talent as T                              # noqa: E402
from engine.db import connect                                   # noqa: E402

#: A plausible opening-weekend field. Ten teams, because a talent prior is
#: a z-score and a two-team sample makes every team the mean — which is a
#: real trap: the first probe of this bug read "prior 0.0" and looked like
#: the fix had failed.
FIELD = {"OSU": 975.0, "MICH": 950.0, "BAMA": 965.0, "UGA": 970.0,
         "PSU": 905.0, "ORE": 900.0, "ISU": 790.0, "KSU": 800.0,
         "TOL": 620.0, "AKR": 560.0}


class _Game:
    def __init__(self, home, away):
        self.home, self.away = home, away
        self.home_rating = self.away_rating = 0.0
        self.home_off = self.home_def = 0.0
        self.away_off = self.away_def = 0.0


def _opener_ratings():
    prior = T.talent_prior(FIELD, T.PRIOR_FIT, {})
    return T.apply_prior({}, prior, {}, {})


# --- the bug ----------------------------------------------------------------
def test_a_team_that_has_not_played_still_gets_a_rating():
    """The whole finding, in one assertion."""
    blended, report = _opener_ratings()
    assert blended, "opening Saturday rates nobody — the prior is dropped again"
    assert len(blended) == len(FIELD)
    assert report["prior_only"] == len(FIELD)
    assert report["teams"] == 0, "nobody has played yet"


def test_the_prior_actually_separates_the_teams():
    """A rating every team shares is not a rating. If the blend ever
    returns a constant the board prices every game as a coin flip and
    nothing downstream can tell."""
    blended, _ = _opener_ratings()
    assert blended["OSU"].net > blended["ISU"].net > blended["AKR"].net


def test_the_board_can_price_an_opening_game():
    """Ratings that never reach a game are ratings nobody sees."""
    blended, _ = _opener_ratings()
    games = [_Game("OSU", "AKR"), _Game("PSU", "TOL")]
    assert teamrates.attach_ratings(games, blended) == len(games)
    from engine import gamebets
    conn = connect(":memory:")
    cfbratings.install(cfbratings.fit_from_history(conn, {}))
    for g in games:
        m = gamebets.game_margin("cfb", g.home_rating, g.away_rating)
        assert m > 0, f"{g.away} @ {g.home} projected the underdog ahead"


# --- what the prior is NOT allowed to say -----------------------------------
def test_the_prior_never_invents_an_offense_or_a_defense():
    """A recruiting composite says a roster is good, not that it scores 34
    a game. Splitting it would put a fabricated number into every total on
    the board — the talent module's own docstring makes this the rule."""
    blended, _ = _opener_ratings()
    for team, r in blended.items():
        assert r.off == 0.0 and r.def_ == 0.0, \
            f"{team} got an invented scoring split from a recruiting number"


def test_a_prior_only_rating_admits_it_has_no_games():
    blended, _ = _opener_ratings()
    assert all(r.games == 0 for r in blended.values())


def test_results_still_beat_the_prior_once_they_exist():
    """The fix must not reverse the blend. A team with games keeps its
    measured rating path; only the teams with none take the new branch."""
    from engine.teamrates import TeamRating
    prior = T.talent_prior(FIELD, T.PRIOR_FIT, {})
    measured = {"OSU": TeamRating(net=12.0, off=8.0, def_=-4.0, games=9)}
    blended, report = T.apply_prior(measured, prior, {}, {})
    assert report["teams"] == 1 and report["prior_only"] == len(FIELD) - 1
    assert blended["OSU"].off == 8.0, "a played team lost its measured offense"
    assert blended["OSU"].games == 9


# --- the variance layer says what it is -------------------------------------
def test_an_unfitted_variance_says_the_board_is_not_staked():
    """CFB prices from a prior until 400 games are in the database. That
    is a fine thing to publish and a bad thing to bet, and the note is
    what makes the difference visible."""
    conn = connect(":memory:")
    fit = cfbratings.fit_from_history(conn, {})
    assert fit.fitted is False
    assert "journaled and graded, not staked" in fit.note


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
