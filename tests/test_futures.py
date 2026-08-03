"""Season futures — playing the rest of the year out, many times.

A futures number is a claim about months of games, so the tests that matter
are the ones that would catch it being quietly impossible. Four of these
are conservation laws: exactly one champion, exactly one winner per
division, exactly ``berths`` playoff teams per conference. A simulator can
look completely reasonable on a printout and still be leaking probability,
and only the sums say so.

The rest guard the two ways a futures page misleads: reporting a certainty
(nothing is certain over a season) and presenting a preseason prior as
though games had been played.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import futures as F
from engine.divisions import MLB, NFL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _round_robin(teams, repeats=1):
    """Every team plays every other, home and away alternating."""
    out = []
    for r in range(repeats):
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                out.append(F.Fixture(a, b) if r % 2 == 0 else F.Fixture(b, a))
    return out


#: as_dict rounds every probability to 4dp for display, so a sum over N
#: rows can be off by N x 5e-5. The conservation tests below are about the
#: model, not the formatting, so they carry exactly that tolerance and no
#: more — a slack figure would hide a real leak.
def _tol(rows):
    return len(rows) * 5e-5 + 1e-12


def _league(sport, spread=4.0, n=None):
    """Ratings and blank records for a league.

    ``n`` trims to the first N teams, and the records are trimmed WITH it —
    handing simulate() thirty-two records and twelve teams' worth of
    fixtures is how the empty-team bug was found, and a fixture that keeps
    doing it is testing the guard rather than the model.
    """
    import random
    rng = random.Random(11)
    teams = list(NFL if sport == "nfl" else MLB)[:n]
    ratings = {t: rng.gauss(0, spread) for t in teams}
    return teams, ratings, {t: (0, 0) for t in teams}


# --- conservation -----------------------------------------------------------
def test_exactly_one_champion_every_trial():
    """The sum of title probabilities is 1, or probability is leaking. A
    bracket that drops a team on an odd field, or double-counts a bye, shows
    up here and nowhere else on a printout."""
    teams, ratings, recs = _league("nfl", n=16)
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=800)
    assert abs(sum(t["p_title"] for t in r["teams"]) - 1.0) < _tol(r["teams"])


def test_exactly_one_division_winner_per_division():
    teams, ratings, recs = _league("mlb")
    r = F.simulate("mlb", ratings, recs, _round_robin(teams), trials=400)
    n_div = len({F.group_of("mlb", t) for t in teams})
    assert abs(sum(t["p_division"] for t in r["teams"]) - n_div) < _tol(r["teams"])


def test_the_playoff_field_is_exactly_the_right_size():
    teams, ratings, recs = _league("nfl")
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=400)
    confs = len({t["conference"] for t in r["teams"]})
    want = r["berths"] * confs
    assert abs(sum(t["p_playoffs"] for t in r["teams"]) - want) < _tol(r["teams"])


def test_conference_winners_are_one_per_conference():
    teams, ratings, recs = _league("mlb")
    r = F.simulate("mlb", ratings, recs, _round_robin(teams), trials=400)
    confs = len({t["conference"] for t in r["teams"]})
    assert abs(sum(t["p_conference"] for t in r["teams"]) - confs) < _tol(r["teams"])


# --- nothing is ever certain ------------------------------------------------
def test_a_single_game_is_never_a_coin_flip_or_a_certainty():
    """Clamped at both ends on purpose. A season simulation that treats one
    game as certain will report a certainty at the end of it, and there is
    no such thing over six months."""
    assert 0.01 <= F.win_prob("nfl", 400.0, -400.0) <= 0.99
    assert 0.01 <= F.win_prob("nfl", -400.0, 400.0) <= 0.99


def test_home_advantage_is_worth_something_and_not_everything():
    even = F.win_prob("nfl", 0.0, 0.0)
    assert 0.5 < even < 0.65, even
    assert F.win_prob("nfl", 0.0, 0.0, neutral=True) == 0.5


def test_a_better_team_is_more_likely_to_win_the_thing():
    """The floor. If rating does not move the title number, none of the rest
    of this file is measuring a model."""
    teams = list(NFL)
    ratings = {t: 0.0 for t in teams}
    ratings[teams[0]] = 12.0
    recs = {t: (0, 0) for t in teams}
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=600)
    best = {t["team"]: t for t in r["teams"]}[teams[0]]
    field = [t for t in r["teams"] if t["team"] != teams[0]]
    assert best["p_title"] > max(t["p_title"] for t in field)
    assert best["proj_wins"] > max(t["proj_wins"] for t in field)


# --- the preseason honesty flag ---------------------------------------------
def test_a_preseason_run_reports_that_it_is_all_prior():
    """In August the ratings are last season's and no game this year has
    been played. The arithmetic is real and the inputs are stale, and a page
    that does not say so is presenting a prior as a projection."""
    teams, ratings, recs = _league("nfl", n=8)
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=200)
    assert r["prior_weight"] == 1.0


def test_a_finished_season_rests_on_no_prior_at_all():
    teams, ratings, _ = _league("nfl")
    recs = {t: (10, 7) for t in teams}
    r = F.simulate("nfl", ratings, recs, [], trials=50)
    assert r["prior_weight"] == 0.0


def test_the_prior_falls_as_the_season_is_played():
    teams, ratings, _ = _league("nfl", n=8)
    fx = _round_robin(teams)
    early = F.simulate("nfl", ratings, {t: (1, 1) for t in teams}, fx, trials=50)
    late = F.simulate("nfl", ratings, {t: (8, 8) for t in teams}, fx, trials=50)
    assert late["prior_weight"] < early["prior_weight"]


# --- the shape of each league -----------------------------------------------
def test_wins_already_banked_carry_into_the_projection():
    """A team 20 games up does not start the simulation level with everyone
    else — the whole point of running this in August rather than March."""
    teams, ratings, _ = _league("mlb", n=10)
    recs = {t: (40, 40) for t in teams}
    recs[teams[0]] = (70, 10)
    fx = _round_robin(teams)
    r = F.simulate("mlb", ratings, recs, fx, trials=200)
    row = {t["team"]: t for t in r["teams"]}[teams[0]]
    assert row["proj_wins"] >= 70
    assert row["wins"] == 70 and row["played"] == 80


def test_a_division_winner_can_be_seeded_over_a_better_record():
    """A 9-win division champion outranking a 10-win wildcard is a real
    feature of the NFL and MLB, not a rounding error — a model that sorted
    the field purely on record would price it away."""
    assert F.SHAPES["nfl"].divisions_seed is True
    assert F.SHAPES["mlb"].divisions_seed is True
    # The NBA seeds a conference on record alone; its divisions decide
    # nothing, and claiming otherwise would invent a market.
    assert F.SHAPES["nba"].divisions_seed is False


def test_a_seven_game_series_favours_the_better_team_more_than_one_game():
    """Series length is the single biggest structural difference between
    these leagues' postseasons, and a bracket that ignored it would price
    the NBA like the NFL."""
    import random
    ratings = {"A": 6.0, "B": 0.0}
    one = sum(F._play_series("nba", "A", "B", ratings, 1, random.Random(i)) == "A"
              for i in range(400)) / 400
    seven = sum(F._play_series("nba", "A", "B", ratings, 7, random.Random(i)) == "A"
                for i in range(400)) / 400
    assert seven > one + 0.05, (one, seven)


# --- reproducibility --------------------------------------------------------
def test_two_runs_of_the_same_board_agree():
    """A futures page whose numbers jitter every refresh reads as noise even
    when the model is stable, and nobody can tell a real move from the
    sampler."""
    teams, ratings, recs = _league("nfl", n=12)
    fx = _round_robin(teams)
    a = F.simulate("nfl", ratings, recs, fx, trials=300)
    b = F.simulate("nfl", ratings, recs, fx, trials=300)
    assert a["teams"] == b["teams"]


def test_an_empty_league_does_not_divide_by_zero():
    assert F.simulate("nfl", {}, {}, [], trials=10)["teams"] == []


def test_the_output_is_ordered_by_how_likely_the_title_is():
    teams, ratings, recs = _league("nfl", n=12)
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=300)
    titles = [t["p_title"] for t in r["teams"]]
    assert titles == sorted(titles, reverse=True)


def test_the_projection_carries_a_range_not_just_a_point():
    """One number for a season is a forecast pretending to be a fact. The
    10th-90th band is what makes 9.5 wins mean something."""
    teams, ratings, recs = _league("nfl", n=12)
    r = F.simulate("nfl", ratings, recs, _round_robin(teams), trials=400)
    for row in r["teams"]:
        assert row["proj_wins_lo"] <= row["proj_wins"] <= row["proj_wins_hi"]
    # A MIDDLING team, not the best one: a side that wins every game in more
    # than 90% of trials has a legitimately collapsed band, and asserting on
    # the leader would be testing the fixture rather than the model.
    mid = sorted(r["teams"], key=lambda t: t["proj_wins"])[len(r["teams"]) // 2]
    assert mid["proj_wins_hi"] > mid["proj_wins_lo"]
def test_a_team_with_no_season_is_left_out_entirely():
    """Found by the simulator, not by a printout: handed 32 records and 12
    teams' worth of fixtures, a team with ZERO games came out first by title
    probability. Nothing played and nothing left is not an 0-win team, it is
    a team we know nothing about — a stale abbreviation, a relocation, a feed
    naming one side differently. Left in, it joined its division level with
    everyone else, took it on the random tiebreak whenever its rivals were
    also empty, and then won the bracket on rating alone.
    """
    teams = list(NFL)
    ratings = {t: 0.0 for t in teams}
    ratings[teams[0]] = 25.0                 # a ghost with a huge rating
    recs = {t: (0, 0) for t in teams}
    playing = teams[1:9]
    for t in playing:
        recs[t] = (2, 2)
    r = F.simulate("nfl", ratings, recs, _round_robin(playing), trials=200)
    named = {t["team"] for t in r["teams"]}
    assert teams[0] not in named, "a team with no season is in the table"
    assert named == set(playing)


def test_a_team_with_games_left_but_none_played_still_counts():
    """The control. A season that has not started yet is exactly the case
    Ethan asked for, so the guard must key on "no season at all", not on
    "no games played"."""
    teams = list(NFL)[:8]
    ratings = {t: 0.0 for t in teams}
    r = F.simulate("nfl", ratings, {t: (0, 0) for t in teams},
                   _round_robin(teams), trials=100)
    assert {t["team"] for t in r["teams"]} == set(teams)
    assert r["prior_weight"] == 1.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
