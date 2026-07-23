"""Moneyline (game-level) betting model.

Covers the win-probability models for both sports and the shared pricing that
turns a model win probability into an edge-checked moneyline recommendation.

Run directly: `python3 tests/test_gamebets.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gamebets import (
    nfl_win_prob, mlb_win_prob, price_moneyline, moneyline_to_dict,
    LEAGUE_AVG_XERA,
)
from engine.pipeline import run_slate
from engine.mlb.pipeline import run_mlb_slate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NFL_SLATE = os.path.join(ROOT, "data", "sample_slate.json")
MLB_SLATE = os.path.join(ROOT, "data", "mlb_sample_slate.json")


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


# --- win-probability models ------------------------------------------------

def test_nfl_win_prob_rewards_the_stronger_team():
    even = nfl_win_prob(0.0, 0.0)
    assert even > 0.5                       # home-field edge
    assert nfl_win_prob(7.0, 0.0) > even    # stronger home team
    assert nfl_win_prob(0.0, 7.0) < 0.5     # stronger road team
    # A pick'em with home field should be a modest favorite, not a lock.
    assert 0.5 < even < 0.6


def test_mlb_win_prob_accounts_for_the_starter():
    base = mlb_win_prob(0.0, 0.0, LEAGUE_AVG_XERA, LEAGUE_AVG_XERA)
    # A better home starter (lower xERA) raises the home win probability.
    assert mlb_win_prob(0.0, 0.0, 3.0, LEAGUE_AVG_XERA) > base
    # A better away starter lowers it.
    assert mlb_win_prob(0.0, 0.0, LEAGUE_AVG_XERA, 3.0) < base
    # Run-diff rating moves it too.
    assert mlb_win_prob(0.5, 0.0) > base


# --- pricing ---------------------------------------------------------------

def test_price_moneyline_backs_the_side_with_the_edge():
    # Model gives home a 60% shot; book has home at -110 (≈52.4% fair).
    rec = price_moneyline("HOME", "AWAY", 0.60, -110, -110)
    assert rec.pick == "HOME"
    assert rec.pick_is_home is True
    assert rec.edge > 0
    assert rec.odds == -110


def test_price_moneyline_can_back_the_underdog():
    # Model thinks the road dog wins 55%; book prices them +150 (40% fair).
    rec = price_moneyline("HOME", "AWAY", 0.45, -175, 150)
    assert rec.pick == "AWAY"
    assert rec.pick_is_home is False
    assert approx(rec.win_prob, 0.55)
    assert rec.edge > 0


def test_price_moneyline_passes_when_it_agrees_with_the_market():
    # Model win prob equals the de-vigged line -> no edge -> Pass.
    rec = price_moneyline("HOME", "AWAY", 0.50, -110, -110)
    assert rec.grade == "Pass"
    assert abs(rec.edge) < 0.03


def test_moneyline_to_dict_shape():
    rec = price_moneyline("KC", "BUF", 0.58, -150, 130)
    d = moneyline_to_dict(rec)
    for key in ("bet_type", "market", "pick", "matchup", "win_prob",
                "fair_prob", "edge", "odds", "confidence", "grade", "headline"):
        assert key in d
    assert d["bet_type"] == "moneyline"


# --- pipeline integration --------------------------------------------------

def test_pipeline_emits_game_bets():
    for slate, runner in ((NFL_SLATE, run_slate), (MLB_SLATE, run_mlb_slate)):
        result = runner(slate)
        assert "game_bets" in result
        assert result["game_bets"], "expected at least one priced moneyline"
        for b in result["game_bets"]:
            assert 0.0 <= b["win_prob"] <= 1.0
            assert abs(b["edge"]) < 0.35        # no runaway edges
            assert b["headline"]
        # The sample slates are tuned so at least one moneyline is recommended.
        assert any(b["recommended"] for b in result["game_bets"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
