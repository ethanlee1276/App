"""One grade for every board — §10's 0–100 score.

Ethan, 2026-09-02, closing the NFL readiness audit's first open question
("which grade gates publication?"): "1. 0-100". Before this the prop board
graded A+/A/B+/Pass on the §10 score while game lines graded Strong Play /
Play / Pass and the long-shot boards Strong Play / Play / Lean / Pass on
two hand-drawn ladders — three vocabularies, and one of them published
Leans at 1.5% of edge. Every number here is worked by hand from §10's
weights and the NEUTRAL values in engine/quality.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import quality as Q
from engine import gamebets as G
from engine import longshots as L

LETTERS = {"A+", "A", "B+", "Pass"}


def test_the_prop_score_did_not_move():
    """The shared arithmetic was refactored under the prop score; these
    three were computed before the change and must not shift."""
    assert Q.quality_score(edge=0.03, market="receptions", side="OVER",
                           favored=True, spread_abs=3.0, matchup_mult=1.05,
                           weather_mult=1.0, cv=0.3, cv_typical=0.35,
                           sample_games=8)[0] == 78
    assert Q.quality_score(edge=0.045, market="rec_yds", side="UNDER",
                           favored=False, spread_abs=8.0, matchup_mult=0.96,
                           weather_mult=0.97, cv=0.5, cv_typical=0.45,
                           sample_games=3, movement_pts=12.0)[0] == 81
    assert Q.quality_score(edge=0.0, market="pass_yds", side="OVER",
                           favored=None, spread_abs=0.0, matchup_mult=1.0,
                           weather_mult=1.0, cv=0.0, cv_typical=0.3,
                           sample_games=0)[0] == 32


def test_a_game_bet_scores_its_edge_over_neutral_context():
    # 1% edge on a Tier 1 line: 0.01/0.0375 × 40 = 10.67, + 35 neutral = 46
    assert Q.game_bet_score(0.01, "total") == 46
    assert Q.letter(Q.game_bet_score(0.01, "total")) == "Pass"
    # 3.2% → 34.13 + 35 = 69 → Pass; 3.3% → 35.2 + 35 = 70 → B+
    assert Q.game_bet_score(0.032, "spread") == 69
    assert Q.game_bet_score(0.033, "spread") == 70
    assert Q.letter(70) == "B+"
    # full edge credit at 3.75%: 75, and never higher — every context
    # component is neutral, so a game bet is the minimum stake at best
    assert Q.game_bet_score(0.0375, "moneyline") == 75
    assert Q.game_bet_score(0.20, "moneyline") == 75
    assert Q.letter(75) == "B+"


def test_game_lines_are_tier_one_with_the_two_and_a_half_percent_bar():
    for m in ("moneyline", "spread", "total", "team_total"):
        assert Q.market_tier(m) == 1 and Q.tier_min_edge(m) == 0.025


def test_a_long_shot_needs_more_than_a_lean_ever_did():
    # the old ladder's Lean: 1.5% edge. 0.015/0.09 × 40 = 6.67 + 15 + 27 = 48.67 → 49
    assert Q.longshot_score(0.015, "anytime_td", 4.5, 4.5) == 49
    assert Q.letter(49) == "Pass"
    # §3's Tier 3 bar is 6%; 6.3% with a full role: 28 + 15 + 27 = 70 → B+
    assert Q.longshot_score(0.063, "anytime_td", 4.5, 4.5) == 70
    # 9% with a full role and clean data is the ceiling, 82 → A
    assert Q.longshot_score(0.09, "home_runs", 4.5, 4.5, 1.0) == 82
    assert Q.letter(82) == "A"
    # a thin role costs stability: 40% of the target → 40 + 6 + 27 = 73
    assert Q.longshot_score(0.09, "anytime_td", 1.8, 4.5) == 73
    # inferred red-zone data (0.85) discounts the same component: 40 + 12.75 + 27 = 79.75 → 80
    assert Q.longshot_score(0.09, "anytime_td", 4.5, 4.5, 0.85) == 80


def test_every_board_speaks_the_one_vocabulary():
    card = G.price_total("nfl", "KC", "LAC", 49.0, 45.5)
    assert card["grade"] in LETTERS and isinstance(card["quality"], int)
    assert card["confidence"] == round(card["quality"] / 10.0, 1)
    ml = G.price_moneyline("KC", "LAC", 0.62, -150, 130, sport="nfl")
    assert ml.grade in LETTERS and ml.quality == G.game_bet_score(ml.edge, "moneyline")
    assert G.moneyline_to_dict(ml)["quality"] == ml.quality
    pick = L.build_pick("X", "AAA", "BBB", "home_runs", "Home Runs", "DK", 400,
                        model_prob=0.24, under_odds=-600, opportunities=4.5,
                        opp_target=4.5, primary_reason="", reasons=[],
                        caveats=[], sport="mlb")
    assert pick.grade in LETTERS and pick.to_dict()["quality"] == pick.quality
    assert pick.confidence == round(pick.quality / 10.0, 1)


def test_a_price_that_does_not_pay_still_cannot_carry_a_grade():
    """The one rule of the old long-shot ladder that was never about a
    threshold: beating the consensus while losing to the price is not a
    bet. Model 20% at +300 is EV −20%; whatever the score says, Pass."""
    pick = L.build_pick("X", "AAA", "BBB", "home_runs", "Home Runs", "DK", 300,
                        model_prob=0.20, under_odds=-400, opportunities=4.5,
                        opp_target=4.5, primary_reason="", reasons=[],
                        caveats=[], sport="mlb")
    assert pick.ev_per_unit <= 0 and pick.grade == "Pass" and pick.stake_units == 0.0


def test_the_word_ladders_are_gone_from_new_cards():
    import inspect
    src = inspect.getsource(G) + inspect.getsource(L.build_pick)
    assert '"Lean"' not in src.replace("# ", "")  or "Lean" not in [
        w for w in ("Lean",) if f'grade = "{w}"' in src]
    for name in ("Strong Play", "Play", "Lean"):
        assert f'"{name}"' not in inspect.getsource(G._game_bet)
        assert f'"{name}"' not in inspect.getsource(G._sharpify)
        assert f'"{name}"' not in inspect.getsource(L.build_pick)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
