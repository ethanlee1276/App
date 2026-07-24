"""Recency + two-sided betting behavior.

Covers the model's ability to (a) shade a cooling player's projection down,
(b) recommend the UNDER when that's where the value is, and (c) dock confidence
for betting against a player's trend. Shared helpers are exercised directly
since both the NFL and MLB betting layers route through them.

Run directly: `python3 tests/test_recency.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.form import compute_form
from engine.odds import best_under_line, best_over_line
from engine.betting import pick_side, _trend_alignment, evaluate_prop, temper_edge, MAX_CREDIBLE_EDGE
from engine.projection import build_projection
from engine.explain import headline
from engine.models import (
    SportsbookLine, GameLog, Prop, Game, Team, DefenseProfile, Weather, REC_YDS,
)


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


def _logs(vals):
    """Build game logs, most-recent-first (index 0 = latest game)."""
    return [GameLog(week=i, opponent="X", value=v, home=True) for i, v in enumerate(vals)]


# --- line shopping ---------------------------------------------------------

def test_best_under_line_shops_highest():
    lines = [
        SportsbookLine("A", 50.5, -110, -110),
        SportsbookLine("B", 52.5, -108, -112),  # highest line = best under cushion
        SportsbookLine("C", 51.5, -115, -105),
    ]
    best = best_under_line(lines)
    assert best.book == "B"
    assert best.line == 52.5


# --- two-sided selection ---------------------------------------------------

def test_pick_side_takes_under_when_projection_is_low():
    lines = [SportsbookLine("DK", 50.5, -110, -110)]   # fair ~0.5 / 0.5
    # p_over_at returns a low over probability -> the value is on the under.
    side, best, win, fair, edge = pick_side(lines, lambda ln: 0.20)
    assert side == "UNDER"
    assert approx(win, 0.80)          # 1 - 0.20
    assert edge > 0
    assert best.line == 50.5


def test_pick_side_takes_over_when_projection_is_high():
    lines = [SportsbookLine("DK", 50.5, -110, -110)]
    side, best, win, fair, edge = pick_side(lines, lambda ln: 0.75)
    assert side == "OVER"
    assert approx(win, 0.75)
    assert edge > 0


# --- recency shade (downward only) -----------------------------------------

def test_hot_streak_is_not_inflated():
    # Recent games far above the prior season -> trend up, but the projection
    # is deliberately NOT shaded up (chasing heat is a bettor trap).
    form = compute_form(_logs([120, 115, 110, 60, 62, 58, 64, 60, 59, 61]),
                        career_avg=70.0, vs_opponent_avg=None)
    assert form.trend == "up"
    assert form.trend_mult == 1.0


def test_cold_streak_shades_projection_down():
    form = compute_form(_logs([30, 28, 33, 90, 92, 88, 95, 91, 89, 93]),
                        career_avg=70.0, vs_opponent_avg=None)
    assert form.trend == "down"
    assert form.trend_mult < 1.0
    assert form.trend_mult >= 0.90        # bounded


# --- trend-aware confidence ------------------------------------------------

def test_trend_alignment_rewards_riding_and_penalizes_fighting():
    assert _trend_alignment("OVER", "down") < 0      # fighting a cool-off
    assert _trend_alignment("UNDER", "down") > 0     # fading the fader
    assert _trend_alignment("OVER", "up") > 0        # riding a hot streak
    assert _trend_alignment("UNDER", "up") < 0
    assert _trend_alignment("OVER", "flat") == 0.0
    # Fighting the trend costs more than riding it earns (asymmetric, cautious).
    assert abs(_trend_alignment("OVER", "down")) > _trend_alignment("OVER", "up")


# --- end to end: hot early, cold late --------------------------------------

def test_fading_player_flips_to_under():
    # Elite early (100+), fell off a cliff late (28-40). logs are most-recent
    # first, so the top entries are the cold games. Book line still sits at the
    # hot-era number.
    logs = _logs([28, 34, 31, 40, 95, 110, 120, 105, 98, 102])
    prop = Prop(player="Fading Wideout", team="AAA", opponent="BBB", position="WR",
                market=REC_YDS, logs=logs, career_avg=78.0, vs_opponent_avg=None,
                lines=[SportsbookLine("DK", 74.5, -110, -110)])
    game = Game(home="AAA", away="BBB", weather=Weather(dome=True))
    opp = Team(abbr="BBB", name="B Team", defense=DefenseProfile(team="BBB"))

    proj = build_projection(prop, game, opp)
    rec = evaluate_prop(prop, proj)

    assert proj.form.trend == "down"
    assert proj.form.trend_mult < 1.0
    assert rec.projection < proj.form.mean            # shaded down
    assert rec.side == "UNDER"                        # value is on the under
    assert rec.edge > 0
    assert "UNDER" in headline(rec)                   # headline reflects the side


def test_temper_edge_shrinks_and_flags_bad_data():
    # The real Caminero case: model 0.75 vs a broken market price of 0.27.
    hit, edge, credible = temper_edge(0.75, 0.27, "Hard Rock")
    assert not credible                         # a 48% raw gap is bad data, not alpha
    assert abs(edge) < abs(0.75 - 0.27)         # probability shrunk toward the market
    # A modest, believable edge on a real line survives (and is damped).
    hit, edge, credible = temper_edge(0.56, 0.50, "DraftKings")
    assert credible and 0 < edge < 0.06
    # A placeholder line is never credible.
    assert temper_edge(0.60, 0.50, "proxy")[2] is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
