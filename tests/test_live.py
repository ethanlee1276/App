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
     "linescore": {"currentInningOrdinal": "6th", "inningState": "Top", "outs": 1}},
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
    assert live.period == "Top 6th" and live.detail == "1 out"


def test_mlb_final_game():
    board = parse_live(SCHED)
    fin = board[frozenset(("CHC", "PHI"))]      # ids 112 / 143
    assert fin.state == "final" and fin.home_score == 2


# --- serialization + pipeline flag ------------------------------------------
def test_live_to_dict():
    assert live_to_dict(None) is None
    d = live_to_dict(LiveStatus(state="live", home_score=5, away_score=3, period="Top 6th"))
    assert d["state"] == "live" and d["home_score"] == 5 and d["period"] == "Top 6th"


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
