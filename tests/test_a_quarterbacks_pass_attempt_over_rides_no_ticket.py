"""A quarterback's pass-attempt over rides no ticket (step AAQ, 21 November).

Ethan, 2026-11-21: "We want to dial in the 3-leg parlays ... look at all the data, figure out
what we can use to our advantage to make better picks".

Read off every settled Most Likely pick the public day records hold: an NFL quarterback's
pass-attempt over that we and the book both rated 60% or better hit 20 of 41 (44% early, 50%
since) where we said 64%, while every other NFL leg as high hit 68% then 65%. The book rated
it as high as we did, so the book cap (step AAM) lets it through. In football it is now kept
off every ticket (gameparlays.QB_VOLUME_LEGS) and goes behind the other bets on a report's
card (gamereport._card_doubted); it stays a pick on the board.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402
from engine import gamereport as GR          # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")


def test_a_pass_attempt_over_is_the_rule_and_nothing_else_is():
    vol = GP.qb_volume_leg
    for sport in ("nfl", "cfb"):
        for side in ("OVER", "Over", "YES"):
            assert vol(sport, {"market": "pass_att", "side": side, "line": 33.5}), (sport, side)
            assert GP.off_parlays(sport, {"market": "pass_att", "side": side, "line": 33.5}) == "qb_volume_over"
    for leg in ({"market": "pass_att", "side": "UNDER", "line": 33.5}, {"market": "pass_yds", "side": "OVER", "line": 220.5},
                {"market": "pass_cmp", "side": "OVER", "line": 20.5}, {"market": "rush_att", "side": "OVER", "line": 14.5}):
        assert not vol("nfl", leg), leg
    assert not vol("nba", {"market": "pass_att", "side": "OVER"}) and not vol("nhl", {"market": "pass_att", "side": "OVER"})
    assert not vol("nfl", {"market": None, "side": None}), "nothing to read: no rule"
    assert "qb_volume_over" in GP.OFF_PARLAY_WORDS
    os.environ["QB_VOLUME_LEGS"] = "off"
    try:
        assert not vol("nfl", {"market": "pass_att", "side": "OVER"})
        assert GP.off_parlays("nfl", {"market": "pass_att", "side": "OVER", "line": 33.5}) == ""
    finally:
        os.environ.pop("QB_VOLUME_LEGS", None)


def test_the_board_keeps_the_pick_and_no_ticket_takes_it():
    rows = [EG._ml("Jared Goff", "NYG", "QB", "pass_att", "Over", 31.5, 0.66, -200, "Pass Attempts"),
            EG._ml("Jared Goff", "NYG", "QB", "pass_yds", "Over", 220.5, 0.66, -200, "Passing Yards"),
            EG._ml("Malik Nabers", "NYG", "WR", "receptions", "Over", 4.5, 0.66, -200, "Receptions")]
    board = {"date": "2099-W10", "games": [EG.GAME], "most_likely": rows, "recommendations": []}
    legs = {(l["player"], l["market"]) for l in GP.legs_for(board, "nfl")}
    assert legs == {("Jared Goff", "pass_yds"), ("Malik Nabers", "receptions")}, legs
    assert len(board["most_likely"]) == 3, "nothing is taken off the board"
    picks = [{"player": r["player"], "market": r["market"], "side": "OVER", "line": r["line"]} for r in rows]
    fates = GP._picks_census(board, "nfl", EG.GAME, picks, now=dt.datetime(2099, 11, 12, 12, 0))
    assert fates.get("our_rule") == 1 and fates.get("strong") == 2, fates


def _row(player, p, odds, market="receptions", side="OVER", line=3.5):
    return {"player": player, "team": "NYG", "opponent": "WAS", "market": market, "side": side, "line": line,
            "odds": odds, "model_prob": p, "bettable": True, "kind": "prop"}


def test_on_a_reports_card_it_goes_behind_the_other_bets():
    rows = [_row("Volume Arm", 0.68, -230, market="pass_att", line=32.5), _row("Wideout", 0.66, -200),
            _row("Lead Back", 0.65, -200, market="rush_yds", line=55.5), _row("Tight End", 0.64, -190),
            _row("Slot", 0.63, -180)]
    for sport in ("nfl", "cfb"):
        c = SimpleNamespace(result={"likely_board": {"rows": rows}}, teams=("NYG", "WAS"), featured=False, sport=sport)
        assert [r["player"] for r in GR._card_rows(c)] == ["Wideout", "Lead Back", "Tight End", "Slot"], sport
    c = SimpleNamespace(result={"likely_board": {"rows": rows}}, teams=("NYG", "WAS"), featured=True, sport="nfl")
    assert [r["player"] for r in GR._card_rows(c)][-1] == "Volume Arm", "a featured card still shows it, last"


def test_the_record_behind_it_is_in_its_words():
    assert GP.QB_VOLUME_LEGS == {"nfl": ("pass_att",), "cfb": ("pass_att",)}
    for words in ("hit 44% in the first 60% of days (9) and 50% since (32)", "20 of 41 at prices that needed 69%",
                  "68%\n#: early and 65% since (1,038)", "Switch: QB_VOLUME_LEGS=off"):
        assert words in SRC, words


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
