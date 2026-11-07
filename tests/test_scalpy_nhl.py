"""Scalpy NHL 1.0 — Ethan's win-first NHL model, as far as our data carries it.

Ethan, 2026-10-03: "here is the model to use for most likely nhl betting ...
We are hunting the outcome with the highest realistic probability of
cashing." Checked here, one rule each: the grades (A+ 75 / A 70 / B 65 /
C 55, a risk flag keeps a row out of A+); the NHL on the other leagues'
55% Most Likely floor (it was 65% for a day); early-season mode (last season carries 75% of a team's strength
through the first two weeks, 30% by game 30); volume over finishing (a
goal is shots × a hard-regressed shooting %); the opposing goalie replaces
the team goals-against tilt instead of stacking on it; no saves bet on an
unsettled starter, and the starter of last night's game is unsettled
tonight; an unstable role is a pass; a lopsided game is a pass on saves.

Run directly: `python3 tests/test_scalpy_nhl.py`
"""
import importlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import nhl_build as B                                          # noqa: E402
from engine import db, likely, rankfit                         # noqa: E402
from engine.nhl import model as M                              # noqa: E402
T = importlib.import_module("test_nhl_board_builds")   # the board fixture, shared


def test_the_grades_and_what_keeps_a_row_out_of_a_plus():
    assert [M.scalpy_grade(p) for p in (0.80, 0.72, 0.66, 0.60, 0.54)] == ["A+", "A", "B", "C", "Pass"]
    assert M.scalpy_grade(0.80, ["second night of a back-to-back"]) == "A"
    assert M.PROP_TIER["sog"] < M.PROP_TIER["saves"] < M.PROP_TIER["points"] < M.PROP_TIER["anytime_goal"]


def test_the_nhl_floor_is_the_other_leagues_55():
    """Ethan, 2026-10-03: "drop that to like 50% or something, how we have
    the other sports" — hockey is on the shared bar, so a 60% row is a pick
    on the NHL board exactly as it is on the NBA's."""
    assert likely.SPORT_MIN_PROB == {} and likely.MIN_PROB == 0.55
    row = {"player": "A", "team": "EDM", "opponent": "CGY", "market": "sog", "market_label": "Shots on Goal",
           "side": "OVER", "line": 2.5, "odds": -150, "book": "DraftKings", "hit_prob": 0.60, "fair_prob": 0.58,
           "has_market": True, "projection": 3.1, "recent_values": [3, 4, 2]}
    real = rankfit.rank_auc
    rankfit.rank_auc = lambda s, m, store=None: 0.66
    try:
        nhl = likely.build([dict(row)], sport="nhl")
        nba = likely.build([dict(row, market="pts")], sport="nba")
    finally:
        rankfit.rank_auc = real
    assert nhl and not nhl[0].get("reserve"), "60% is a pick on the NHL board now"
    assert nba and not nba[0].get("reserve"), "and on every other league's"


def test_early_season_leans_on_last_season():
    assert M.season_weight(4) == 0.25 and M.season_weight(10) == 0.35
    assert M.season_weight(20) == 0.50 and M.season_weight(40) == 0.70
    conn = db.connect(Path(tempfile.mkdtemp()) / "h.db")
    rows = []
    for i in range(30):            # last season: EDM scores 5 a night
        rows.append({"sport": "nhl", "season": 2024, "period": f"2025-01-{i + 1:02d}", "game_id": f"x{i}",
                     "home": "EDM", "away": "CGY", "home_score": 5, "away_score": 2, "date": f"2025-01-{i + 1:02d}",
                     "extra": "{}"})
    for i in range(3):             # this season: three quiet nights
        rows.append({"sport": "nhl", "season": 2025, "period": f"2025-10-0{i + 1}", "game_id": f"y{i}",
                     "home": "EDM", "away": "CGY", "home_score": 1, "away_score": 2, "date": f"2025-10-0{i + 1}",
                     "extra": "{}"})
    db.upsert_games(conn, rows)
    prof = M.team_profiles(conn)["EDM"]
    assert prof["gp_season"] == 3 and prof["season_weight"] == 0.25
    assert abs(prof["gf"] - (0.25 * 1 + 0.75 * 5)) < 0.01, prof["gf"]


def test_a_goal_is_volume_times_a_regressed_finish():
    league = {"F": {"sog": 8.0, "goals": 0.9, "points": 2.0, "assists": 1.1, "blocks": 1.0, "sh": 0.10}, "sv": 0.9}
    hot = {"position": "C", "games": [{"date": f"2025-10-{i:02d}", "toi": 18.0, "sog": 1.4, "goals": 0.5}
                                      for i in range(1, 29)]}       # 14 goals on 39 shots: a 36% shooter
    proj = M.skater_projection(hot, "anytime_goal", league, {}, "")
    assert proj["sh"] < 0.20, "regressed hard toward the league's 10%"
    assert proj["mean"] < 0.5 * 28 / 28, "the hot streak is not projected forward"


def test_the_goalie_replaces_the_goals_against_tilt():
    league = {"F": {"sog": 8.0, "goals": 0.9, "points": 2.0, "assists": 1.1, "blocks": 1.0, "sh": 0.10}, "sv": 0.900}
    p = {"position": "C", "games": [{"date": f"2025-10-{i:02d}", "toi": 18.0, "sog": 3.0, "goals": 0.3,
                                     "points": 0.8, "assists": 0.5} for i in range(1, 21)]}
    teams = {"BAD": {"gf": 3.0, "ga": 4.5, "sog_for": 30, "sog_against": 30, "n": 82},
             "AVG": {"gf": 3.0, "ga": 3.0, "sog_for": 30, "sog_against": 30, "n": 82}}
    team_only = M.skater_projection(p, "points", league, teams, "BAD")
    with_elite = M.skater_projection(p, "points", league, teams, "BAD", opp_sv=0.925)
    assert team_only["opp"] > 1.05, "goals-against alone reads the team as leaky"
    assert with_elite["opp"] < 1.0, "an elite starter in net is what tonight's goals answer to"
    assert M.goalie_factor(0.880, league) == 1.2 and M.goalie_factor(None, league) == 1.0


def test_no_saves_bet_on_an_unsettled_or_tired_starter():
    conn = T._history()
    players = M.player_games(conn)
    league = M.league_rates(players)
    teams = M.team_profiles(conn)
    games = [{"home": "EDM", "away": "CGY", "start": ""}]
    ctx = B.scalpy_context(games, players, league, teams, "2025-10-30")
    assert ctx["EDM"]["starter"] == "Stuart Skinner" and ctx["EDM"]["starter_sure"]
    # The last fixture game is 2025-10-26: build "tomorrow" and Skinner
    # started last night — he is not tonight's sure thing.
    tired = B.scalpy_context(games, players, league, teams, "2025-10-27")
    assert tired["EDM"]["b2b"] and not tired["EDM"]["starter_sure"]
    slate = B.build_slate(games, players, "2025-10-27")
    T._odds(slate)
    recs, census = B.price_slate(slate, games, players, league, teams, {}, "2025-10-27", ctx=tired)
    assert not any(r["market"] == "saves" and r["team"] == "EDM" for r in recs)
    assert census["starter_unconfirmed"] >= 1


def test_an_unstable_role_and_a_blowout_are_passes():
    out, _ = T._board()
    for r in out["recommendations"]:
        assert "scalpy_grade" in r and "Risk factors" not in " ".join(r["reasons"][:1])
    rec = dict(out["recommendations"][0])
    assert "scalpy_pass" in rec
    # A goalie whose team is expected to lose by a goal or more: a pass.
    ctx = {"EDM": {"starter": "Stuart Skinner", "starter_sure": True, "starter_share": 1.0, "xg": 2.0,
                   "last10": set()},
           "CGY": {"xg": 3.2, "last10": set()}}
    prop = B._Prop("Stuart Skinner", "saves", "EDM")
    from engine.models import SportsbookLine as L
    prop.lines = [L("DraftKings", 26.5, -110, -110)]
    proj = {"mean": 28.0, "sd": 4.0, "shots": 31.0, "sv": 0.905, "n": 20, "recent": [27.0] * 10}
    r = B.price_prop(prop, proj, {"position": "G", "games": []}, "CGY", {}, "2025-10-30", ctx=ctx)
    assert r["scalpy_grade"] == "Pass" and "blowout" in r["scalpy_pass"]
    # Ice time that jumped 40% over the last five games: a pass.
    games = [{"date": f"2025-10-{i:02d}", "toi": 24.0 if i > 25 else 15.0, "sog": 3.0} for i in range(30, 9, -1)]
    proj2 = M.skater_projection({"position": "C", "games": games},
                                "sog", {"F": {"sog": 8.0, "sh": 0.1}, "sv": 0.9}, {}, "")
    assert proj2["toi_swing"] > M.ROLE_SWING


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
