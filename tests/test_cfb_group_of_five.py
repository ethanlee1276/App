"""Ethan, 2026-09-02, on the CFB readiness audit's first Ask ("Bet Group of
Five at all?"): "1. No".

A game in which neither side is a power-conference team is priced and
shown — number, edge, reason — and never becomes a play. The attention
dial still runs (it decides how much edge to believe); this decides
whether money follows.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cfb import model as M
from engine.cfb import pipeline as CP


def _play(home_conf, away_conf, weekday="Saturday"):
    game = {"home": "H", "away": "A", "label": "A @ H",
            "home_conference": home_conf, "away_conference": away_conf,
            "home_rank": None, "away_rank": None, "weekday": weekday,
            "kickoff": "2026-09-05T23:00Z", "qb_confirmed": True}
    return {"game": game, "market": "side", "selection": "H -3", "line": -3.0,
            "odds": -110, "opposing_odds": -110, "p_model": 0.62,
            "information_certainty": 1.0, "attention_fit": 1.0,
            "situational_fit": 0.6, "matchup_fit": 1.0, "environment_fit": 0.9,
            "situational_tags": [], "book": "DK"}


def test_the_rule_is_recorded_as_off():
    assert M.BET_GROUP_OF_FIVE is False


def test_a_group_of_five_game_is_priced_and_not_bet():
    out = CP.evaluate_play(_play("Sun Belt", "MAC"))
    assert out["kind"] == "pass" and out["grade_label"] == "Pass"
    assert "Group of Five" in out["why"] and "No" in out["why"]
    # the number is still on the card
    assert out["edge_raw"] > 0 and out["p_market"] > 0


def test_a_power_opponent_lifts_a_game_out_of_the_rule():
    out = CP.evaluate_play(_play("SEC", "Sun Belt"))
    assert "Group of Five" not in (out.get("why") or "")
    out = CP.evaluate_play(_play("Mountain West", "Big 12"))
    assert "Group of Five" not in (out.get("why") or "")


def test_unknown_conferences_do_not_trigger_the_rule():
    assert M.is_group_of_five({"home_conference": "", "away_conference": "MAC"}) is False
    assert M.is_group_of_five({"home_conference": "MAC", "away_conference": "Sun Belt"}) is True
    assert M.is_group_of_five({"home_conference": "FBS Independents", "away_conference": "American"}) is True
    assert M.is_group_of_five({"home_conference": "ACC", "away_conference": "American"}) is False


def test_the_touchdown_board_follows_the_same_rule():
    import inspect
    from engine.cfb import tds
    src = inspect.getsource(tds.build_cfb_td_longshots)
    assert "is_group_of_five(g)" in src and 'pick.grade = "Pass"' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
