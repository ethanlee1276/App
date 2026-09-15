"""Neither league may read the other's data, or borrow its numbers unsaid.

Two pairs on this site run one engine over two leagues — NBA/WNBA share
the Scalpy pipeline, NFL/CFB share the game-bet pricing — and that is the
right design. It also creates the failure mode nothing else here has: a
model that runs perfectly while quietly describing the wrong sport. It has
already happened once, when `shared_recommendations` graded WNBA picks
with NBA tuning, and the page beside them disagreed with no error anywhere.

So these tests seed leagues that are IMPOSSIBLE to confuse — the NBA
fixture scores 220 a night, the WNBA one scores 52 — and check whose
numbers come out the other end. A leak cannot hide behind a plausible
value when the values are absurd.

The second half is subtler and is the reason this file exists at all: an
inherited constant must never be indistinguishable from a fitted one.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_games, upsert_player_logs

NBA_T = ["BOS", "MIA", "LAL", "GSW"]
WN_T = ["ATL", "NYL", "LVA", "SEA"]
NFL_T = ["NE", "BUF", "KC", "DEN"]
CFB_T = ["Alabama", "Georgia", "Ohio State", "Texas"]


def _seed():
    """Four leagues whose numbers cannot be mistaken for each other."""
    conn = connect(":memory:")
    rows, logs, gid = [], [], 0
    d0 = datetime.date(2026, 1, 5)
    for i in range(120):
        day = (d0 + datetime.timedelta(days=i)).isoformat()
        for sport, season, period, teams, hs, as_ in (
                ("nba", 2025, day, NBA_T, 220, 180),      # 40-pt margins
                ("wnba", 2026, day, WN_T, 52, 50),        # 2-pt margins
                ("cfb", 2026, day, CFB_T, 24, 21),        # 3-pt margins
                ("nfl", 2025, f"{i % 18 + 1:03d}", NFL_T, 60, 20)):
            gid += 1
            rows.append({"sport": sport, "season": season, "period": period,
                         "game_id": f"{sport}{gid}", "home": teams[i % 2],
                         "away": teams[2 + i % 2],
                         "home_score": hs, "away_score": as_})
        for sport, team, val in (("nba", NBA_T[i % 4], 40.0),
                                 ("wnba", WN_T[i % 4], 5.0)):
            for mkt in ("min", "pts", "reb", "ast"):
                logs.append({
                    "sport": sport, "season": 2025 if sport == "nba" else 2026,
                    "period": day, "game_id": f"{sport}L{i}",
                    "player": f"{sport.upper()} Player {i % 4}", "team": team,
                    "opponent": "XXX", "position": "S", "home": 1,
                    "market": mkt, "value": val})
    upsert_games(conn, rows)
    upsert_player_logs(conn, logs)
    return conn


# --- does one league's DATA reach the other's model? -----------------------
def test_team_ratings_see_only_their_own_league():
    from engine import teamrates
    conn = _seed()
    spreads = {}
    for sport, season in (("nba", 2025), ("wnba", 2026),
                          ("nfl", 2025), ("cfb", 2026)):
        r = teamrates.compute_team_ratings(conn, sport, seasons=[season],
                                           shrink=0.0)
        spreads[sport] = max(x.net for x in r.values()) - min(
            x.net for x in r.values())
        # Case-insensitive: the ratings keep a sport's own spelling, and
        # college teams are proper nouns rather than abbreviations.
        want = {"nba": NBA_T, "wnba": WN_T, "nfl": NFL_T, "cfb": CFB_T}[sport]
        assert {k.lower() for k in r} <= {t.lower() for t in want}, \
            f"{sport} ratings saw a foreign team: {sorted(r)}"
    # 40-point leagues rate wide, 2- and 3-point leagues rate narrow. Any
    # bleed would drag the small ones up.
    assert spreads["wnba"] < 10 < spreads["nba"]
    assert spreads["cfb"] < 10 < spreads["nfl"]


def test_standings_never_list_another_leagues_team():
    from engine import standings
    conn = _seed()
    for sport, season, want in (("nba", 2025, NBA_T), ("wnba", 2026, WN_T),
                                ("nfl", 2025, NFL_T)):
        t = standings.compute(conn, sport, season=season, today="2026-06-01")
        got = {r["team"] for g in t["groups"] for r in g["teams"]}
        assert got == set(want), f"{sport} standings: {got}"


def test_rosters_do_not_cross_leagues():
    from engine import rosters
    conn = _seed()
    for sport, season, tag in (("nba", 2025, "NBA"), ("wnba", 2026, "WNBA")):
        out = rosters.from_game_logs(conn, sport, seasons=[season],
                                     today="2026-06-01")
        names = {p["player"] for t in out["teams"].values()
                 for p in t["players"]}
        assert names and all(n.startswith(tag) for n in names), names


def test_the_cfb_variance_is_not_fitted_on_nfl_games():
    from engine import teamrates
    from engine.cfb import ratings as R
    conn = _seed()
    r = teamrates.compute_team_ratings(conn, "cfb", seasons=[2026], shrink=0.0)
    fit = R.fit_from_history(conn, r, min_games=100)
    # These CFB fixtures are all 3-point games. An NFL-contaminated fit
    # (40-point blowouts) could not come out this tight.
    assert fit.margin_sd < 5.0, fit.note


# --- does one league BORROW the other's numbers without saying so? --------
def test_the_two_hoops_leagues_do_not_share_structural_facts():
    from engine.hoops import for_league
    nba, wnba = for_league("nba"), for_league("wnba")
    assert (nba.game_minutes, nba.roster_size) == (48, 15)
    assert (wnba.game_minutes, wnba.roster_size) == (40, 12)
    # Anything denominated in minutes must be scaled, or it means a
    # different fraction of a game in a shorter one.
    assert wnba.vacancy_cap_over_high < nba.vacancy_cap_over_high


def test_an_inherited_number_is_labelled_as_inherited():
    from engine.hoops import for_league
    wnba = for_league("wnba")
    assert wnba.inherited_from == "nba"
    assert wnba.calibrated is False and wnba.probation is True
    assert "inherited" in wnba.note.lower()


def test_fitting_one_league_never_moves_the_other():
    from engine import hoops
    from engine.hoops_fit import fitted_tuning
    conn = _seed()
    before = (hoops.NBA.margin_sd, dict(hoops.NBA.sd_cv))
    fitted_tuning(conn, "wnba")
    assert (hoops.NBA.margin_sd, dict(hoops.NBA.sd_cv)) == before, \
        "fitting the WNBA mutated the NBA's tuning"
    assert hoops.for_league("nba").margin_sd == before[0]


def test_fitting_the_constants_does_not_end_probation():
    """Two different claims. Fitted constants say our numbers describe this
    league; probation is about whether our PICKS have been graded against
    real prices in it. Only the journal's promotion bar answers the
    second, and a better model must not award itself the first."""
    from engine.hoops_fit import fitted_tuning
    conn = _seed()
    tune, _report = fitted_tuning(conn, "wnba")
    assert tune.calibrated is False and tune.probation is True


def test_a_stat_with_no_sample_keeps_the_inherited_value_and_says_so():
    from engine.hoops import for_league
    from engine.hoops_fit import fitted_tuning
    conn = _seed()
    tune, report = fitted_tuning(conn, "wnba")
    # The fixture logs no steals or blocks at all.
    assert tune.sd_cv["stl"] == for_league("nba").sd_cv["stl"]
    assert any("stl" in line for line in report["inherited"])


def test_the_nfl_and_cfb_margin_models_are_separate():
    from engine import gamebets
    from engine.cfb import ratings as R
    assert gamebets.MARGIN_SD["nfl"] == gamebets.NFL_MARGIN_SD
    R.install(R.PRIOR)
    assert gamebets.MARGIN_SD["cfb"] == R.PRIOR.margin_sd
    assert gamebets.MARGIN_SD["cfb"] != gamebets.MARGIN_SD["nfl"]
    # And a CFB build must never reach the NFL's curve.
    import cfb_build
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "cfb_build.py"), encoding="utf-8").read()
    assert "nfl_win_prob" not in src


def test_an_unsupported_sport_is_refused_rather_than_given_the_nfl_curve():
    """`else nfl_win_prob` meant a CFB backtest would replay college games
    through the NFL's margin model and produce a confident, wrong number
    that looked exactly like a real one."""
    from engine.gamebacktest import backtest_moneylines
    conn = _seed()
    try:
        backtest_moneylines(conn, "cfb")
    except ValueError as exc:
        assert "cfb" in str(exc) and "curve" in str(exc)
    else:
        raise AssertionError("a CFB backtest silently used the NFL's curve")


# --- the class of bug underneath all of it ---------------------------------
def test_a_measured_zero_is_not_a_missing_measurement():
    """The bug this pins, and it was live: `_sd(res) or PRIOR.margin_sd`
    swapped in the prior whenever the computed SD came out ZERO, then
    reported `fitted=True`. "No sample" and "the residuals were tiny" are
    opposite findings and must not share a return value."""
    from engine.cfb.ratings import _sd
    from engine.hoops_fit import _sd as hoops_sd
    for fn in (_sd, hoops_sd):
        assert fn([]) is None and fn([1.0]) is None
        assert fn([5.0, 5.0, 5.0]) == 0.0, "a real zero came back as None"


def test_the_coverage_scan_fits_on_real_ratings():
    """It called `fit_from_history(conn, {})`. With no ratings every row is
    skipped, nothing is measured, the PRIOR comes back — and the scan
    printed "Fitted on 4,005 CFB games". A prior wearing a fitted label is
    the one number on the board nobody would think to check."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "coverage.py"),
               encoding="utf-8").read()
    assert "fit_from_history(conn, {})" not in src
    assert "compute_team_ratings" in src[src.index("def cfb("):]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
