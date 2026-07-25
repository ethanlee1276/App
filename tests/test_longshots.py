"""Long-shot engines — NFL anytime touchdowns and MLB home runs.

These markets are where undisciplined models lose money, so the tests assert the
*discipline* as much as the maths: opportunity beats recent scoring, the odds
windows hold, concentration limits hold, and implausible edges are refused.

Run directly: `python3 tests/test_longshots.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.longshots import (
    prob_at_least_one, in_odds_window, select, build_pick,
    NFL_TD_ODDS, MLB_HR_ODDS,
)
from engine.touchdowns import (
    td_probability, team_implied_total, expected_team_tds, build_td_longshots,
)
from engine.mlb.homeruns import hr_probability, plate_appearances, build_hr_longshots
from engine.models import (
    Prop, Game, Team, DefenseProfile, Weather, GameLog, SportsbookLine, ANYTIME_TD,
)
from engine.mlb.models import (
    MLBProp, MLBGame, MLBGameLog, MLBWeather, Pitcher, StatcastProfile,
)


# --- shared ----------------------------------------------------------------
def test_prob_at_least_one_is_a_poisson_tail():
    assert prob_at_least_one(0.0) == 0.0
    assert 0.6 < prob_at_least_one(1.0) < 0.65      # 1 - e^-1
    assert prob_at_least_one(5.0) < 1.0             # never certain


def test_odds_windows_match_the_strategy():
    assert in_odds_window(-140, NFL_TD_ODDS) and in_odds_window(190, NFL_TD_ODDS)
    assert not in_odds_window(-260, NFL_TD_ODDS)     # too much juice
    assert not in_odds_window(420, NFL_TD_ODDS)      # lottery ticket
    assert in_odds_window(300, MLB_HR_ODDS) and in_odds_window(640, MLB_HR_ODDS)
    assert not in_odds_window(180, MLB_HR_ODDS)      # too short for a HR
    assert not in_odds_window(900, MLB_HR_ODDS)


def test_implausible_edge_is_refused():
    """A 30-point disagreement with an efficiently-priced market is a data or
    modelling error, not an edge — it must not grade as a play."""
    pick = build_pick("X", "AAA", "BBB", "home_runs", "Home Runs", "DK", 400,
                      model_prob=0.55, under_odds=-600, opportunities=4.3,
                      opp_target=4.5, primary_reason="", reasons=[], caveats=[],
                      sport="mlb")
    assert pick.grade == "Pass"
    assert any("too large to trust" in c for c in pick.caveats)


# --- NFL touchdowns --------------------------------------------------------
def _nfl(pos, share, spread, total, weather=None, tds=None, vs_d=1.0):
    g = Game(home="KC", away="BUF", weather=weather or Weather(dome=True),
             spread=spread, total=total)
    opp = Team(abbr="BUF", name="Bills",
               defense=DefenseProfile(team="BUF", vs_rb_rush=vs_d, vs_wr1=vs_d, vs_te=vs_d))
    logs = [GameLog(week=i, opponent="X", value=float(v)) for i, v in enumerate(tds or [], 1)]
    p = Prop(player="Test", team="KC", opponent="BUF", position=pos, market=ANYTIME_TD,
             logs=logs, career_avg=0.4, vs_opponent_avg=None,
             lines=[SportsbookLine("DK", 0.5, 120, -160)])
    return td_probability(p, g, opp, share)


def test_implied_total_follows_the_spread():
    g = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-7.0, total=50.0)
    assert team_implied_total(g, "KC") == 28.5      # favourite gets the points
    assert team_implied_total(g, "BUF") == 21.5
    assert expected_team_tds(28.5) > expected_team_tds(21.5)


def test_game_script_moves_touchdown_probability():
    """The same back is worth far more as a big favourite in a high total."""
    good, _ = _nfl("RB", 0.65, -7.0, 51.0, tds=[1, 0, 1, 1, 0, 1])
    bad, _ = _nfl("RB", 0.65, +7.0, 38.0, tds=[1, 0, 1, 1, 0, 1])
    assert good > bad + 0.15


def test_scoreless_backup_is_not_rated_like_a_starter():
    """Six scoreless games is evidence of a low rate, not missing data — the
    old fallback to a position baseline badly overrated players like this."""
    backup, _ = _nfl("RB", 0.10, -3.0, 45.0, tds=[0, 0, 0, 0, 0, 0])
    starter, _ = _nfl("RB", 0.65, -3.0, 45.0, tds=[1, 0, 1, 1, 0, 1])
    assert backup < 0.15
    assert starter > backup * 2


def test_severe_weather_suppresses_passing_touchdowns():
    clear, _ = _nfl("WR", 0.28, -7.0, 51.0)
    windy, _ = _nfl("WR", 0.28, -7.0, 51.0,
                    weather=Weather(dome=False, wind_mph=25, temp_f=18))
    assert windy < clear


def test_red_zone_proxy_is_disclosed():
    _, info = _nfl("RB", 0.5, -3.0, 45.0, tds=[1, 0, 0, 1])
    assert any("inferred" in c for c in info["caveats"])


def test_td_board_respects_the_per_game_cap():
    """Three qualifying players in one game must yield at most two picks."""
    g = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-7.0, total=52.0)
    opp = Team(abbr="BUF", name="Bills", defense=DefenseProfile(team="BUF", vs_rb_rush=1.2))
    cands = []
    for name in ("A", "B", "C"):
        p = Prop(player=name, team="KC", opponent="BUF", position="RB", market=ANYTIME_TD,
                 logs=[GameLog(week=i, opponent="X", value=1.0) for i in range(1, 7)],
                 career_avg=1.0, vs_opponent_avg=None,
                 lines=[SportsbookLine("DK", 0.5, 150, -200)])
        cands.append({"prop": p, "game": g, "opponent": opp,
                      "opportunity_share": 0.5, "odds": 150, "book": "DK",
                      "under_odds": -200})
    assert len(build_td_longshots(cands, limit=6, per_game=2)) <= 2


# --- MLB home runs ---------------------------------------------------------
def _mlb(park="coors", wind="cross", mph=5, temp=72, barrel=0.13, spot=4, every=6):
    g = MLBGame(home="COL", away="NYY", park=park,
                weather=MLBWeather(temp_f=temp, wind_mph=mph, wind_dir_rel=wind),
                pitchers={"COL": Pitcher(name="P", throws="R", slg_allowed_vs_r=0.44,
                                         k_rate=0.20, xera=4.6)})
    p = MLBProp("Slugger", "NYY", "COL", "RF", "home_runs",
                [MLBGameLog(i, "X", 1.0 if i % every == 0 else 0.0) for i in range(1, 31)],
                0.2, None, [SportsbookLine("DK", 0.5, 350, -480)],
                bats="R", lineup_spot=spot,
                statcast=StatcastProfile(barrel_pct=barrel, hard_hit_pct=0.50,
                                         xslg=0.560, slg=0.530))
    return hr_probability(p, g)


def test_wind_direction_moves_home_run_probability():
    """Wind is one of the few edges the market is sometimes slow to price, so
    blowing out must beat calm, which must beat blowing in."""
    out, _ = _mlb(wind="out", mph=15)
    calm, _ = _mlb(wind="cross", mph=3)
    into, _ = _mlb(wind="in", mph=15)
    assert out > calm > into


def test_park_and_cold_suppress_home_runs():
    coors, _ = _mlb(park="coors", temp=85)
    pitchers_park, _ = _mlb(park="loandepot", temp=45)
    assert coors > pitchers_park


def test_contact_quality_beats_recent_results():
    elite, _ = _mlb(barrel=0.15)
    weak, _ = _mlb(barrel=0.04)
    assert elite > weak


def test_lineup_spot_changes_plate_appearances():
    assert plate_appearances(1) > plate_appearances(9)
    top, _ = _mlb(spot=2)
    bottom, _ = _mlb(spot=9)
    assert top > bottom


def test_missing_statcast_is_disclosed():
    g = MLBGame(home="COL", away="NYY", park="coors")
    p = MLBProp("NoData", "NYY", "COL", "RF", "home_runs",
                [MLBGameLog(i, "X", 0.0) for i in range(1, 11)], 0.1, None,
                [SportsbookLine("DK", 0.5, 500, -700)], bats="R", lineup_spot=5)
    _, info = hr_probability(p, g)
    assert any("Statcast" in c for c in info["caveats"])


def test_hr_board_caps_one_pick_per_team():
    g = MLBGame(home="COL", away="NYY", park="coors",
                weather=MLBWeather(temp_f=88, wind_mph=15, wind_dir_rel="out"),
                pitchers={"COL": Pitcher(name="P", throws="R", slg_allowed_vs_r=0.47)})
    cands = []
    for name in ("A", "B", "C"):
        p = MLBProp(name, "NYY", "COL", "RF", "home_runs",
                    [MLBGameLog(i, "X", 1.0 if i % 5 == 0 else 0.0) for i in range(1, 31)],
                    0.2, None, [SportsbookLine("DK", 0.5, 400, -550)],
                    bats="R", lineup_spot=3,
                    statcast=StatcastProfile(barrel_pct=0.13, hard_hit_pct=0.5))
        cands.append({"prop": p, "game": g, "odds": 400, "book": "DK", "under_odds": -550})
    assert len(build_hr_longshots(cands, limit=3, per_team=1)) <= 1


def test_board_ranks_by_edge_not_by_payout():
    """The biggest price is almost never the best bet — ranking by odds is how
    long-shot cards go broke."""
    from engine.longshots import LongShot

    def ls(name, edge, odds):
        return LongShot(player=name, team=name, opponent="X", market="home_runs",
                        market_label="Home Runs", book="DK", odds=odds,
                        model_prob=0.2, implied_prob=0.2 - edge, edge=edge,
                        ev_per_unit=0.1, confidence=8.0, stake_units=0.5,
                        grade="Play", expected_opportunities=4.3, primary_reason="")

    picks = [ls("LongPrice", 0.02, 900), ls("BestEdge", 0.06, 300)]
    ranked = select(picks, per_key_cap=1, key=lambda p: p.team, limit=2)
    assert ranked[0].player == "BestEdge"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
