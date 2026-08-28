"""7-for-40 at -48.9%, and no way to ask which forty.

The touchdown board's first book-priced result read:

    Anytime touchdown: 40 settled · basis book
      all bets  40  win 17.5%  roi -48.9%

Those two numbers point in different directions. At n=40 a 17.5% hit
rate has a standard error of 6 points, so it is statistically ordinary
for a market that needs ~20%. The ROI is not: -48.9% on 40 bets with 7
winners implies an average winning payout near +92, which is not a
longshot price at all.

A board quietly taking -150s and calling them longshots looks exactly
like a board with a broken model — until you print the prices. The
report kept only aggregates, so nobody could.

`BacktestReport.settled` keeps the rows and `lab.dump_bets` prints them,
banded by price. The band table is the part that settles the question:
if the bets cluster short, the selection is wrong; if they cluster long
and simply lost, 40 is too few to conclude anything.
"""

import io
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest as B
from engine import lab


def _settled(rows):
    """rows = [(player, odds, model_prob, scored)]"""
    recs, actuals = [], {}
    for player, odds, prob, scored in rows:
        recs.append({"player": player, "market": "anytime_td", "line": 0.5,
                     "odds": odds, "hit_prob": prob, "projection": prob,
                     "recommended": True, "book": "DK", "grade": "A",
                     "side": "OVER"})
        actuals[(B._norm(player), "anytime_td")] = float(scored)
    return B.settle_recommendations(recs, actuals)


def _dump(report, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab.dump_bets(report, **kw)
    return buf.getvalue()


# --- the rows survive the aggregation ---------------------------------------
def test_the_report_keeps_the_bets_behind_its_numbers():
    rep = B.evaluate(_settled([("A", 550, 0.18, 1), ("B", 400, 0.22, 0)]))
    assert len(rep.settled) == 2
    assert {s.player for s in rep.settled} == {"A", "B"}


def test_an_empty_report_keeps_an_empty_list_not_none():
    rep = B.evaluate([])
    assert rep.settled == []
    assert "no settled bets" in _dump(rep)


# --- the band table, which is the actual diagnostic --------------------------
def test_short_prices_are_visible_as_their_own_band():
    """The hypothesis the dump exists to test: a longshot board that is
    really betting favourites."""
    rep = B.evaluate(_settled([("A", -150, 0.70, 0), ("B", -200, 0.72, 0),
                               ("C", 500, 0.20, 1)]))
    out = _dump(rep)
    assert "-299..-150" in out
    assert "+351..+700" in out


def test_a_band_with_no_bets_is_not_printed_as_a_zero_row():
    rep = B.evaluate(_settled([("A", 500, 0.20, 1)]))
    out = _dump(rep)
    assert "+351..+700" in out
    assert "-300 and shorter" not in out


def test_the_band_roi_uses_the_price_actually_taken():
    """A winner at +500 returns 5 units of profit on 1 staked, so the
    band reads +500%. A table that assumed a flat -110 would report
    +91% for the same bet, which is the error this exists to prevent."""
    rep = B.evaluate(_settled([("A", 500, 0.20, 1)]))
    assert "+500.0%" in _dump(rep)
    # And a short-priced winner pays far less for being right.
    rep2 = B.evaluate(_settled([("B", -200, 0.70, 1)]))
    assert "+50.0%" in _dump(rep2)


def test_every_bet_is_listed_shortest_price_first():
    rep = B.evaluate(_settled([("Long", 600, 0.15, 0), ("Short", -140, 0.65, 1),
                               ("Mid", 250, 0.30, 0)]))
    out = _dump(rep)
    order = [out.index(n) for n in ("Short", "Mid", "Long")]
    assert order == sorted(order), out


def test_the_result_of_each_bet_is_named():
    rep = B.evaluate(_settled([("W", 500, 0.20, 1), ("L", 500, 0.20, 0)]))
    out = _dump(rep)
    assert "WON" in out and "lost" in out


def test_the_implied_probability_sits_beside_the_model_number():
    """The whole comparison. A pick at -150 claiming 18% is the board
    betting against itself; the dump has to make that impossible to
    miss."""
    rep = B.evaluate(_settled([("A", -150, 0.18, 0)]))
    out = _dump(rep)
    assert "18.0%" in out and "60.0%" in out


def test_only_recommended_rows_count_as_bets():
    recs = [{"player": "Bet", "market": "anytime_td", "line": 0.5,
             "odds": 500, "hit_prob": 0.2, "projection": 0.2,
             "recommended": True, "book": "DK", "grade": "A"},
            {"player": "Pass", "market": "anytime_td", "line": 0.5,
             "odds": 500, "hit_prob": 0.2, "projection": 0.2,
             "recommended": False, "book": "DK", "grade": "Pass"}]
    actuals = {(B._norm("Bet"), "anytime_td"): 1.0,
               (B._norm("Pass"), "anytime_td"): 1.0}
    out = _dump(B.evaluate(B.settle_recommendations(recs, actuals)))
    assert "Bet" in out and "Pass " not in out


def test_a_limit_caps_the_listing_but_never_the_band_table():
    """The bands are the diagnostic; truncating them would defeat the
    point of asking."""
    rep = B.evaluate(_settled([(f"P{i}", 500, 0.2, i % 2) for i in range(30)]))
    out = _dump(rep, limit=5)
    assert out.count("WON") + out.count("lost") == 5
    assert "+351..+700" in out and "30" in out


def test_the_helper_survives_a_junk_price():
    assert lab._implied(None) is None
    assert lab._implied(0) is None
    assert lab._implied("n/a") is None
    assert abs(lab._implied(-150) - 0.6) < 1e-9
    assert abs(lab._implied(300) - 0.25) < 1e-9


# --- the wiring --------------------------------------------------------------
def test_the_flag_exists_and_is_its_own_path():
    import inspect
    src = inspect.getsource(lab.main)
    assert "if args.bets:" in src
    assert "dump_bets(rep.longshots)" in src, \
        "the touchdown board is the reason this flag exists"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
