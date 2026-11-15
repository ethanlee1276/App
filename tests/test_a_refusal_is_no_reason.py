"""A gate's refusal is never shown as a reason for a pick (2026-11-15).

Ethan's screenshot of a game's parlays showed, under "why" for DeMario Douglas
over 2.5 receptions: "The record shows a blind spot here: nfl receptions, OVER
— said 63%, hit 57% over 732 bets — ran hot; this slice closed itself", and
"Usage bridge: 5.2 targets/gm × 0.67 per target — measured role says 3.5 …".
The first is the Edge board's loss-pattern veto, which engine/betting puts
first in a refused pick's reasons; the Most Likely row and the parlay leg on
the same bet copied the reasons whole. The second is the projection's
arithmetic. Now (engine/refusals) the rows that borrow an Edge card's reasons
leave every gate's refusal out, and a parlay leg leaves the arithmetic out.

    python3 tests/test_a_refusal_is_no_reason.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gameparlays as GP, likely as L, refusals as RF  # noqa: E402

VETO = ("The record shows a blind spot here: nfl receptions, OVER — said 63%, hit 57% over 732 bets — "
        "ran hot; this slice closed itself")
BRIDGE = ("Usage bridge: 5.2 targets/gm × 0.67 per target — measured role says 3.5, pulled 31% toward his "
          "1.9 last season to 3.0, weighted 31% against form")


def test_every_gates_refusal_is_known_by_its_opening():
    for x in (VETO,
              "Rule proposed by the hypothesis lab (an AI model) and confirmed on 80 graded bets: unders …",
              "This shelf is stopped: nfl rush_att is down over its whole settled record",
              "Model disagrees with the market by more than 10 points — treated as a modelling or data error",
              "Edge +2.1% is under the Tier B bar (3.0% post-haircut) — pass, not a lean"):
        assert RF.is_refusal(x), x
    for x in ("DET gives up the most passing yards (276 a game)", "Trending up — last 3 games +29 vs prior form",
              BRIDGE, "Edge looks real", ""):
        assert not RF.is_refusal(x), x
    assert RF.reasons_only([VETO, "Soft matchup", None, ""]) == ["Soft matchup"]


def test_the_most_likely_row_leaves_the_edge_boards_refusal_out():
    row = {"player": "DeMario Douglas", "team": "NE", "opponent": "DET", "market": "receptions",
           "market_label": "Receptions", "side": "OVER", "line": 2.5, "book": "Caesars", "odds": -240,
           "reasons": [VETO, "DET gives up the most passing yards (276 a game)", "Scout: thin sample", BRIDGE]}
    got = L._row_from(row, "receptions", "nfl", lambda m: True, 0.69, shown=0.69)
    assert got["reasons"] == ["DET gives up the most passing yards (276 a game)", BRIDGE], got["reasons"]


def test_a_parlay_leg_says_its_reasons_and_not_the_arithmetic():
    leg = {"player": "DeMario Douglas", "market": "receptions", "side": "OVER", "line": 2.5}
    row = {"reasons": [VETO, BRIDGE, "DET gives up the most passing yards (276 a game)",
                       "Trending up — last 3 games +0.8 vs prior form"]}
    why = GP.why_lines(leg, row, None)
    assert why == ["DET gives up the most passing yards (276 a game)",
                   "Trending up — last 3 games +0.8 vs prior form"], why


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
