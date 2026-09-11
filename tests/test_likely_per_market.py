"""Every market keeps its best rows on the Most Likely board.

Ethan, 2026-09-07: "for some reason its only displaying tight ends for
reciving props and thats it. that seems strang and wrong and we need to
look into that."

The board kept the forty highest probabilities across every player
market in one list. The highest probabilities belong to the lowest
lines — a tight end over 2.5 receptions at 68% — so the forty filled
with those and a receiver's honest 58% on 64.5 yards never reached the
receiving shelf. The cut is now two passes: each market's best eight,
then the best of the rest, forty in all, still in probability order.

Run directly: `python3 tests/test_likely_per_market.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K                                # noqa: E402


def _row(i, market, prob, team="T"):
    return {"kind": "prop", "player": f"P{market}{i}", "team": team, "market": market,
            "model_prob": prob, "implied_prob": prob - 0.03, "odds": -110,
            "book": "DraftKings", "bettable": True}


def test_each_market_keeps_its_best_rows_and_the_board_stays_forty():
    rows = ([_row(i, "receptions", 0.70 - i * 0.001) for i in range(30)]
            + [_row(i, "rec_yds", 0.58 - i * 0.001) for i in range(12)]
            + [_row(i, "rush_yds", 0.57 - i * 0.001) for i in range(12)]
            + [_row(i, "pass_yds", 0.56) for i in range(3)])
    got = K._cut_players(rows, K.LIMIT)
    assert len(got) == K.LIMIT
    by = {}
    for r in got:
        by[r["market"]] = by.get(r["market"], 0) + 1
    # Every market has its eight (three, where only three exist), and
    # the seats left over go to the best of the rest — receptions.
    assert by["rec_yds"] == K.PER_MARKET and by["rush_yds"] == K.PER_MARKET
    assert by["pass_yds"] == 3
    assert by["receptions"] == K.LIMIT - K.PER_MARKET * 2 - 3
    # The kept receiving rows are the best receiving rows, not any eight.
    kept = [r["model_prob"] for r in got if r["market"] == "rec_yds"]
    assert kept == sorted((0.58 - i * 0.001 for i in range(K.PER_MARKET)), reverse=True)
    # Still one order, by probability.
    probs = [r["model_prob"] for r in got]
    assert probs == sorted(probs, reverse=True)


def test_a_board_with_fewer_rows_than_seats_is_untouched():
    rows = [_row(i, "receptions", 0.60) for i in range(5)] + [_row(0, "rec_yds", 0.56)]
    got = K._cut_players(rows, K.LIMIT)
    assert len(got) == 6 and got[-1]["market"] == "rec_yds"


def test_the_old_cut_is_reproduced_when_one_market_is_all_there_is():
    rows = [_row(i, "receptions", 0.70 - i * 0.001) for i in range(60)]
    got = K._cut_players(rows, K.LIMIT)
    assert len(got) == K.LIMIT and got[0]["model_prob"] == 0.70


def test_the_board_uses_the_cut_and_game_rows_keep_their_own_cap():
    import inspect
    src = inspect.getsource(K.build)
    assert "_cut_players(" in src and "[:GAME_LIMIT]" in src
    assert K.PER_MARKET * 5 == K.LIMIT, "five player markets, eight each, forty in all"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
