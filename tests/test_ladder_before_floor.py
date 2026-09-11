"""A main line under the floor asks its ladder before the floor refuses it.

Ethan, 2026-09-08: "make sure the most likley bets are all good for nfl
and cfb. im still only seeing like 4 picks for the most likley bets so
we need to fix that and show more bc we have a full slate coming
sunday." His census off the droplet, the same morning:

    363 rows · 212 under the likelihood floor · 0 on the board · 0 on a rung

THE LADDERS WERE BOUGHT AND NEVER LOOKED AT. `from_prop` refused a row
on the main line's own probability — which for a line hung where the
book thinks the coin is fair is 50% on every prop — before `_best_rung`
was consulted. The alternate ladders (2026-09-07) exist for exactly
that row: the same stat at a lower number, priced heavier, where "most
likely" is actually for sale. Every rung fixture in the suite started
at 0.56, one point over the floor, so the case that empties a real
board was the one case nothing covered.

What this pins:

  * a coin-flip main line with a likely rung on its ladder is shown as
    that rung — `rung: "alt"`, the rung's line and price — and the
    census counts nothing;
  * a sharp-anchored row (the model's read is the number asked) does
    the same;
  * the floor still refuses a row whose every number is under it, a
    row with no ladder, a row with no real market, and a row with no
    probability at all — each without crashing;
  * end to end through `build`, the rung lands on the board and passes
    `admissible`.

Run directly: `python3 tests/test_ladder_before_floor.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K                                  # noqa: E402

# The same mixture fixture tests/test_likely_rungs.py prices with:
# projection 62 on a rush-yards row → P(over 40.5) 0.695, P(over 50.5)
# 0.550, P(over 62.5) 0.400.
FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}


def _always(_market):
    return True


def _ln(book, line, over, under=0):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _row(**kw):
    """The row the census counted 212 of: a main line at a coin flip."""
    got = {"player": "A Back", "team": "DET", "opponent": "CHI",
           "market": "rush_yds", "market_label": "rush_yds", "side": "over",
           "line": 62.5, "book": "DK", "odds": -110, "has_market": True,
           "fair_prob": 0.50, "projection": 62.0, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [55, 71, 48, 66],
           "date": "2026-09-14", "hit_prob": 0.50, "raw_prob": 0.50,
           "alt_lines": [_ln("DraftKings", 40.5, -240, 190),
                         _ln("FanDuel", 40.5, -230, 185),
                         _ln("DraftKings", 50.5, -160, 130)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def test_a_coin_flip_main_line_is_shown_as_its_likeliest_rung():
    census: dict = {}
    row = K.from_prop(_row(), _always, fits=FITS, census=census)
    assert row is not None, census
    assert row["rung"] == "alt" and row["line"] == 40.5 and row["side"] == "over"
    assert row["book"] == "FanDuel" and row["odds"] == -230, "the best price per rung"
    assert abs(row["model_prob"] - 0.695) < 0.01, row["model_prob"]
    assert row["main_line"] == 62.5 and row["main_odds"] == -110
    assert row["raw_prob"] == 0.50, "the main number stays on the row"
    assert census == {}, census


def test_a_sharp_anchored_coin_flip_asks_its_ladder_too():
    """`hit_prob` is the sharp fair on an anchored card; the model's own
    read is what the floor asks, and when that is a coin flip the
    ladder is still the place to look."""
    census: dict = {}
    row = K.from_prop(_row(sharp_anchored=True, sharp_fair=0.515,
                           hit_prob=0.515, raw_prob=0.51),
                      _always, fits=FITS, census=census)
    assert row is not None and row["rung"] == "alt" and row["line"] == 40.5, census
    assert row["sharp_anchored"] is True and row["raw_prob"] == 0.51


def test_the_floor_still_refuses_a_row_whose_every_number_is_under_it():
    """The mixture on a 62-yard projection: 0.523 at 52.5, 0.497 at
    54.5, 0.40 at 62.5, 0.276 at 75.5 — every rung on this ladder is
    under the floor, and the 54.5 rung sits in the band a slipped floor
    would admit. Nothing shows; the census says the floor."""
    census: dict = {}
    thin = _row(alt_lines=[_ln("DraftKings", 54.5, -120, 100),
                           _ln("DraftKings", 62.5, -110, -110),
                           _ln("FanDuel", 75.5, 150, -180)])
    assert K.from_prop(thin, _always, fits=FITS, census=census) is None
    assert census == {"under the likelihood floor": 1}, census


def test_no_ladder_no_market_and_no_probability_refuse_as_before():
    for kw, why in (({"alt_lines": []}, "under the likelihood floor"),
                    ({"has_market": False}, "under the likelihood floor"),
                    ({"hit_prob": None, "raw_prob": None}, "under the likelihood floor")):
        census: dict = {}
        assert K.from_prop(_row(**kw), _always, fits=FITS, census=census) is None, kw
        assert census == {why: 1}, (kw, census)


def test_the_rung_lands_on_the_board_end_to_end():
    census: dict = {}
    board = K.build([_row()], sport="nfl", fits=FITS, census=census)
    assert len(board) == 1 and board[0]["rung"] == "alt" and board[0]["line"] == 40.5, census
    assert census == {}, census
    # And a main line that clears the floor on its own still prefers the
    # likelier of the two, exactly as before.
    board = K.build([_row(hit_prob=0.56, raw_prob=0.58)], sport="nfl", fits=FITS)
    assert len(board) == 1 and board[0]["rung"] == "alt" and board[0]["line"] == 40.5


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
