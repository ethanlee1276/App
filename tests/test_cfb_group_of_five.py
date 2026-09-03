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
    assert out["why"] == M.NOT_A_POWER_GAME
    assert "No" in out["why"], "the decision stays attributed on the card"
    # the number is still on the card
    assert out["edge_raw"] > 0 and out["p_market"] > 0


def test_a_power_opponent_lifts_a_game_out_of_the_rule():
    out = CP.evaluate_play(_play("SEC", "Sun Belt"))
    assert out.get("why") != M.NOT_A_POWER_GAME
    out = CP.evaluate_play(_play("Mountain West", "Big 12"))
    assert out.get("why") != M.NOT_A_POWER_GAME


def test_unknown_conferences_do_not_trigger_the_rule():
    assert M.is_group_of_five({"home_conference": "", "away_conference": "MAC"}) is False
    assert M.is_group_of_five({"home_conference": "MAC", "away_conference": "Sun Belt"}) is True
    assert M.is_group_of_five({"home_conference": "FBS Independents", "away_conference": "American"}) is True
    assert M.is_group_of_five({"home_conference": "ACC", "away_conference": "American"}) is False


def test_the_rule_reaches_further_than_its_name(  ):
    """Seven of the eleven conferences the feed can name fail this test,
    and two of them are not Group of Five by any ordinary reading.

    The Pac-12 is a judgement about what the league is after the 2024
    realignment; FBS Independents is Notre Dame's conference, and
    CFB_READINESS.md's Phase 8 says so on purpose. Both are pinned here
    so that changing either is a deliberate act on a betting rule rather
    than a tidy-up of a set literal.
    """
    from engine.sources.cfbdata import CONFERENCE_IDS, conference_name

    named = {conference_name(v) for v in CONFERENCE_IDS.values()}
    refused = sorted(named - M.POWER_CONFERENCES)
    assert M.POWER_CONFERENCES == {"SEC", "Big Ten", "Big 12", "ACC"}
    assert refused == ["American", "Conference USA", "FBS Independents",
                       "MAC", "Mountain West", "Pac-12", "Sun Belt"], refused
    # The two a reader would not predict from the rule's name.
    for conf in ("Pac-12", "FBS Independents"):
        assert M.is_group_of_five({"home_conference": conf,
                                   "away_conference": "MAC"}) is True, conf
        assert M.is_group_of_five({"home_conference": conf,
                                   "away_conference": "SEC"}) is False, conf


def test_the_sentence_on_the_card_says_what_was_tested():
    """"Group of Five game" over Notre Dame at Navy is a sentence a reader
    would call wrong. Now that the refusal rides on the card rather than
    dying in an unrendered pass list, it names the four instead."""
    why = M.NOT_A_POWER_GAME
    assert "power conference" in why
    for conf in sorted(M.POWER_CONFERENCES):
        assert conf in why, conf
    assert "Group of Five" not in why


def test_both_boards_show_the_same_sentence():
    """One copy, two producers. `pipeline.evaluate_play` prices the game
    markets and `tds` the touchdown board; a sentence written out twice
    is this codebase's most-repeated bug."""
    import inspect
    from engine.cfb import tds

    assert "NOT_A_POWER_GAME" in inspect.getsource(CP.evaluate_play)
    assert "NOT_A_POWER_GAME" in inspect.getsource(tds.build_cfb_td_longshots)
    for src in (inspect.getsource(CP), inspect.getsource(tds)):
        assert "Group of Five game — priced" not in src, \
            "a second copy of the sentence has come back"


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
