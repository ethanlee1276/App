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
    project_total, project_team_points, game_margin,
    price_total, price_team_total, price_spread, LEAGUE_AVG_XERA,
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


def test_project_total_combines_offense_and_defense():
    base = 2 * 22.6
    # All-average teams project to twice the league baseline.
    assert approx(project_total("nfl", 0, 0, 0, 0), base)
    # Two good offenses + two leaky defenses project higher.
    assert project_total("nfl", 3, 2, 4, 1) > base


def test_price_total_backs_over_when_projection_is_high():
    # Projection well above the market number -> value on the over.
    t = price_total("nfl", "KC", "BUF", proj_total=52.0, market_total=45.0)
    assert t["bet_type"] == "total"
    assert t["side"] == "Over"
    assert t["edge"] > 0
    # And the under when the projection is well below.
    u = price_total("nfl", "KC", "BUF", proj_total=38.0, market_total=45.0)
    assert u["side"] == "Under"
    assert u["edge"] > 0


def test_project_team_points_uses_offense_vs_opp_defense():
    base = 22.6
    assert approx(project_team_points("nfl", 0, 0), base)
    assert project_team_points("nfl", 4, 2) > base     # good offense, leaky opp D


def test_price_team_total_backs_the_value_side():
    # Team projected well above its posted number -> over.
    over = price_team_total("nfl", "KC", "KC", "BUF", proj_points=30.0, line=24.5)
    assert over["bet_type"] == "team_total"
    assert over["team"] == "KC" and over["side"] == "Over"
    assert over["edge"] > 0
    # And under when projected below.
    under = price_team_total("nfl", "KC", "KC", "BUF", proj_points=18.0, line=24.5)
    assert under["side"] == "Under" and under["edge"] > 0


def test_price_spread_backs_the_value_side():
    # Home projected to win by 7 but only laying 3 -> home covers.
    home = price_spread("nfl", "KC", "BUF", proj_margin=7.0, home_spread=-3.0)
    assert home["bet_type"] == "spread"
    assert home["team"] == "KC" and home["line"] == -3.0
    assert home["edge"] > 0
    # Home projected to lose by 7 while laying 3 -> the dog covers.
    away = price_spread("nfl", "KC", "BUF", proj_margin=-7.0, home_spread=-3.0)
    assert away["team"] == "BUF" and away["line"] == 3.0
    assert away["edge"] > 0


def test_game_margin_includes_home_field():
    assert game_margin("nfl", 0.0, 0.0) > 0     # pick'em + home field
    assert game_margin("nfl", 5.0, 0.0) > game_margin("nfl", 0.0, 0.0)


def test_moneyline_to_dict_shape():
    rec = price_moneyline("KC", "BUF", 0.58, -150, 130)
    d = moneyline_to_dict(rec)
    for key in ("bet_type", "market", "pick", "matchup", "win_prob",
                "fair_prob", "edge", "odds", "confidence", "grade", "headline"):
        assert key in d
    assert d["bet_type"] == "moneyline"


def test_price_moneyline_sharp_finds_price_value():
    """Sharp pair -155/+135 de-vigs home to ~60%; a soft -125 implies 55.6%
    -> ~+7% EV on the price alone, graded Play, no model needed."""
    from engine.gamebets import price_moneyline_sharp
    rec = price_moneyline_sharp("KC", "BUF", -155, 135, -125, -120)
    assert rec is not None
    assert rec.pick == "KC" and rec.pick_is_home
    assert 0.05 < rec.ev_per_unit < 0.10
    assert rec.grade == "Play" and rec.stake_units > 0
    assert "Sharp anchor" in rec.reasons[0]


def test_price_moneyline_sharp_passes_and_filters():
    from engine.gamebets import price_moneyline_sharp
    # Soft prices identical to sharp -> implied worse than de-vigged fair.
    assert price_moneyline_sharp("KC", "BUF", -155, 135, -155, 135) is None
    # A live/stale gap (+88% EV) is a broken price, not a bet.
    assert price_moneyline_sharp("KC", "BUF", -1200, 750, 105, -120) is None


# --- pipeline integration --------------------------------------------------

def test_pipeline_emits_game_bets():
    for slate, runner in ((NFL_SLATE, run_slate), (MLB_SLATE, run_mlb_slate)):
        result = runner(slate)
        assert "game_bets" in result
        assert result["game_bets"], "expected at least one priced game bet"
        for b in result["game_bets"]:
            assert 0.0 <= b["win_prob"] <= 1.0
            assert abs(b["edge"]) < 0.35        # no runaway edges
            assert b["headline"] and b["pick_label"]
        # All four game-bet types are produced.
        types = {b["bet_type"] for b in result["game_bets"]}
        assert types == {"moneyline", "total", "team_total", "spread"}
        # The sample slates are tuned so at least one bet is recommended.
        assert any(b["recommended"] for b in result["game_bets"])


def test_mlb_moneylines_are_informational_only():
    """The walk-forward vs real closes measured the MLB moneyline model at
    -12.4% ROI with a Brier worse than the base rate — so its picks must
    render as market info, never as recommendations, until a model beats the
    close in moneyline_backtest.py."""
    result = run_mlb_slate(MLB_SLATE)
    mls = [b for b in result["game_bets"] if b["bet_type"] == "moneyline"]
    assert mls, "expected moneyline cards to still be shown"
    # The sample slate carries no sharp reference prices, so every card takes
    # the model-only path — which must never recommend.
    for b in mls:
        assert b["recommended"] is False
        assert b["grade"] == "Pass" and b["stake_units"] == 0.0
        assert any("hasn't beaten the close" in w for w in b.get("warnings", []))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
