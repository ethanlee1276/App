"""Tests for live-score adapters (ESPN NFL + MLB Stats API) and live plumbing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources.livescores import parse_espn_scoreboard, _abbr
from engine.mlb.sources.live import parse_live
from engine.models import LiveStatus, live_to_dict


# --- ESPN NFL ---------------------------------------------------------------
ESPN = {"events": [
    {"date": "2026-01-04T21:00Z",
     "status": {"type": {"state": "in", "shortDetail": "Q3"}, "period": 3,
                "displayClock": "8:42"},
     "competitions": [{"competitors": [
         {"homeAway": "home", "team": {"abbreviation": "KC"}, "score": "17"},
         {"homeAway": "away", "team": {"abbreviation": "BUF"}, "score": "14"}],
         "situation": {"downDistanceText": "2nd & 6 at BUF 38"}}]},
    {"status": {"type": {"state": "post", "shortDetail": "Final"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "team": {"abbreviation": "WSH"}, "score": "20"},
         {"homeAway": "away", "team": {"abbreviation": "DAL"}, "score": "27"}]}]},
]}


def test_espn_live_game():
    board = parse_espn_scoreboard(ESPN)
    live = board[frozenset(("KC", "BUF"))]
    assert live.state == "live"
    assert live.home_score == 17 and live.away_score == 14
    assert live.period == "Q3" and live.clock == "8:42"
    assert "BUF 38" in live.detail


def test_espn_final_and_abbr_map():
    board = parse_espn_scoreboard(ESPN)
    # WSH -> WAS so it matches nflverse abbreviations.
    assert frozenset(("WAS", "DAL")) in board
    fin = board[frozenset(("WAS", "DAL"))]
    assert fin.state == "final" and fin.home_score == 20
    assert _abbr("LAR") == "LA"


# --- MLB Stats API ----------------------------------------------------------
SCHED = {"dates": [{"games": [
    {"status": {"abstractGameState": "Live", "detailedState": "In Progress"},
     "teams": {"home": {"team": {"id": 115}, "score": 5},
               "away": {"team": {"id": 147}, "score": 3}},
     "linescore": {"currentInningOrdinal": "6th", "inningState": "Top", "outs": 1,
                   "offense": {"second": {"id": 99}}}},
    {"status": {"abstractGameState": "Final"},
     "teams": {"home": {"team": {"id": 112}, "score": 2},
               "away": {"team": {"id": 143}, "score": 4}},
     "linescore": {}},
]}]}


def test_mlb_live_game():
    board = parse_live(SCHED)
    live = board[frozenset(("COL", "NYY"))]     # ids 115 / 147
    assert live.state == "live"
    assert live.home_score == 5 and live.away_score == 3
    assert live.period == "Top 6th"
    assert live.outs == 1 and live.bases == [2]     # runner on 2nd


def test_mlb_final_game():
    board = parse_live(SCHED)
    fin = board[frozenset(("CHC", "PHI"))]      # ids 112 / 143
    assert fin.state == "final" and fin.home_score == 2


# Braves @ Mets doubleheader: leg 1 (1:10) final, leg 2 (7:10) just live.
# ids 121 = NYM, 144 = ATL.
DH_SCHED = {"dates": [{"games": [
    {"gamePk": 111, "gameNumber": 1, "doubleHeader": "S",
     "status": {"abstractGameState": "Final"},
     "teams": {"home": {"team": {"id": 121}, "score": 4},
               "away": {"team": {"id": 144}, "score": 2}},
     "linescore": {}},
    {"gamePk": 222, "gameNumber": 2, "doubleHeader": "S",
     "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
     "teams": {"home": {"team": {"id": 121}, "score": 0},
               "away": {"team": {"id": 144}, "score": 0}},
     "linescore": {"currentInningOrdinal": "1st", "inningState": "Top",
                   "outs": 0}},
]}]}


def test_doubleheader_legs_keep_their_own_live_state():
    """The bug this pins: the live board was keyed by team pair alone, so a
    doubleheader's second leg overwrote the first and BOTH site cards wore
    one game's inning and score. Legs must key apart; the ambiguous bare
    pair key must not exist at all."""
    board = parse_live(DH_SCHED)
    pair = frozenset(("NYM", "ATL"))
    assert board[111].state == "final" and board[111].home_score == 4
    assert board[222].state == "live" and board[222].period == "Top 1st"
    assert board[(pair, 1)] is board[111]
    assert board[(pair, 2)] is board[222]
    assert pair not in board                    # bare key would lie — gone


def test_attach_live_routes_each_leg_by_game_pk():
    from types import SimpleNamespace as NS
    from engine.mlb.sources import live as live_mod
    slate = NS(games=[
        NS(home="NYM", away="ATL", game_pk=111, game_number=1, live=None),
        NS(home="NYM", away="ATL", game_pk=222, game_number=2, live=None),
    ])
    old = live_mod.fetch_live
    live_mod.fetch_live = lambda date: parse_live(DH_SCHED)
    try:
        assert live_mod.attach_live(slate, "2026-07-29") == 2
    finally:
        live_mod.fetch_live = old
    g1, g2 = slate.games
    assert g1.live.state == "final" and g1.live.home_score == 4
    assert g2.live.state == "live" and g2.live.period == "Top 1st"


# --- serialization + pipeline flag ------------------------------------------
def test_live_to_dict():
    assert live_to_dict(None) is None
    d = live_to_dict(LiveStatus(state="live", home_score=5, away_score=3,
                                period="Top 6th", outs=2, bases=[1, 3]))
    assert d["state"] == "live" and d["home_score"] == 5 and d["period"] == "Top 6th"
    assert d["outs"] == 2 and d["bases"] == [1, 3]


def test_pipeline_marks_live_props():
    from engine.pipeline import run_slate
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = run_slate(os.path.join(root, "data", "sample_slate.json"))
    live_games = [g for g in result["games"] if (g.get("live") or {}).get("state") == "live"]
    assert live_games and live_games[0]["live"]["home_score"] == 17
    # Props on the live game (KC/BUF) are flagged live.
    live_recs = [r for r in result["recommendations"] if r.get("live")]
    assert live_recs and all(r["team"] in ("KC", "BUF") for r in live_recs)


def test_mlb_pipeline_marks_live_props():
    from engine.mlb.pipeline import run_mlb_slate
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = run_mlb_slate(os.path.join(root, "data", "mlb_sample_slate.json"))
    assert any((g.get("live") or {}).get("state") == "live" for g in result["games"])
    assert any(r.get("live") for r in result["recommendations"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
