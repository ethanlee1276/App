"""#253: would buying alternate spreads and totals have bought anything?

The Pick of the Day is game markets only, and `likely.rungs` /
`_best_rung` can already walk a ladder — but `oddsapi` buys h2h, spreads
and totals, all MAIN LINES, and never `alternate_spreads` or
`alternate_totals`. So the ladder machinery has an empty source and
"walk the ladder from potd.choose" is machinery over nothing.

THE DECISION IS A PURCHASE, NOT A WIRING JOB, and the budget is real
(`oddsapi` already puts MLB on a limited allowance behind NFL and CFB).
`potd.price_gap` counts what a purchase could possibly have addressed,
off a board already on disk, for free.

WHAT IT REFUSES TO DO, and this is most of the file. An alternate line
changes BOTH the price and the true probability of the side: a team at
-1.5 is a different bet from the same team at -2.5, not the same bet at a
better number. So nothing here re-prices a refused row at a hypothetical
alternate and asks whether it would then clear — that would invent the
answer the purchase is meant to provide.

THE FINDING IT CAN PRODUCE TODAY, and it may well decide this outright:
A MONEYLINE HAS NO ALTERNATE LINE. There is one number and it is the
price. So a board whose price refusals are all moneylines is a board
saying "do not buy", and that sentence costs nothing to obtain.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402


def _row(market="spread", odds=-110, **kw):
    """A game row that clears everything except whatever `kw` breaks."""
    r = {"kind": "game", "market": market, "sharp_anchored": True,
         "sharp_fair": 0.55, "bettable": True, "rank_auc": 0.71,
         "book": "DraftKings", "odds": odds, "team": "BBB",
         "home": "BBB", "away": "AAA", "matchup": "AAA @ BBB"}
    r.update(kw)
    return r


# --- the count itself ---------------------------------------------------------
def test_a_board_with_no_price_refusals_says_so():
    gap = potd.price_gap([_row(), _row("total", side="Over", line=8.5)])
    assert gap["game_rows"] == 2
    assert gap["refused_on_price"] == 0
    assert gap["addressable"] == 0
    out = "\n".join(potd.price_gap_lines(gap))
    assert "would have bought nothing" in out, out


def test_a_spread_refused_on_price_is_addressable():
    gap = potd.price_gap([_row("spread", odds=-400)])
    assert gap["refused_on_price"] == 1
    assert gap["addressable"] == 1
    assert gap["by_market"]["spread"]["addressable"] == 1
    assert gap["prices"] == [-400]


def test_a_total_refused_on_price_is_addressable_too():
    gap = potd.price_gap([_row("total", odds=350, side="Over", line=8.5)])
    assert gap["addressable"] == 1
    assert gap["by_market"]["total"]["n"] == 1


# --- THE ASYMMETRY THAT MAY DECIDE IT ----------------------------------------
def test_a_moneyline_refused_on_price_is_not_addressable_at_any_budget():
    """The finding this file exists for. There is no `alternate_h2h` to
    buy — a moneyline is one number and that number is the price."""
    assert "moneyline" not in potd.ALT_MARKETS
    gap = potd.price_gap([_row("moneyline", odds=-400)])
    assert gap["refused_on_price"] == 1
    assert gap["addressable"] == 0, \
        "a moneyline was counted as something alternates could rescue"
    assert gap["by_market"]["moneyline"]["addressable"] == 0


def test_a_board_of_moneyline_refusals_says_do_not_buy():
    """The whole point of counting before spending."""
    gap = potd.price_gap([_row("moneyline", odds=-400),
                          _row("moneyline", odds=-900)])
    out = "\n".join(potd.price_gap_lines(gap))
    assert "no alternate line to buy" in out, out
    assert "DO NOT BUY" in out, out


def test_the_report_names_which_markets_have_no_alternates():
    gap = potd.price_gap([_row("moneyline", odds=-400),
                          _row("spread", odds=-400)])
    out = "\n".join(potd.price_gap_lines(gap))
    assert "NO alternates exist" in out, out
    assert "addressable" in out, out


# --- what it refuses to claim -------------------------------------------------
def test_it_never_reprices_a_row_at_an_imagined_alternate():
    """An alternate line is a DIFFERENT BET, so a function that re-priced
    a refused row at a hypothetical number and reported it as rescued
    would be answering the question the purchase is supposed to answer.
    Read off the source, because the absence of a thing cannot be
    observed from the output."""
    import inspect
    src = inspect.getsource(potd.price_gap)
    for invented in ("MIN_ODDS", "MAX_ODDS", "in_band("):
        assert invented not in src, (
            f"`price_gap` references {invented!r} — it is re-pricing rows "
            f"at a band edge rather than counting what was refused")


def test_a_row_failing_other_bars_too_is_counted_apart():
    """A better number does not rescue a row that also fails on evidence
    or on the fair. Counting those as addressable would overstate the
    purchase, which is the one direction this must not err in."""
    # A 30% fair at -400. The band refuses it first (hard), and
    # `MIN_FAIR` would refuse it at ANY price — so no alternate number
    # rescues this row and it must not be counted as though one might.
    #
    # NOT `sharp_fair=None`, which was the first fixture here: that is
    # hard-refused as "no fair probability to price against" before the
    # band check runs, so the row never reaches this counter at all and
    # the test was measuring nothing.
    both = _row("spread", odds=-400, sharp_fair=0.30)
    gap = potd.price_gap([both])
    assert gap["addressable"] == 1          # the market has alternates…
    assert gap["other_bars_too"] == 1       # …but price is not its only problem
    out = "\n".join(potd.price_gap_lines(gap))
    assert "clear every OTHER bar" in out, out


def test_a_player_prop_is_not_counted_at_all():
    """Game markets only — the prop ladder is a different question and
    was already bought (#178)."""
    prop = {"kind": "prop", "market": "rush_yds", "odds": -400,
            "player": "X", "book": "DraftKings"}
    gap = potd.price_gap([prop])
    assert gap["game_rows"] == 0
    assert gap["refused_on_price"] == 0


def test_it_never_raises_on_a_board_of_rubbish():
    """It runs inside `potd_report`, which must not die on a board."""
    assert potd.price_gap([None, 7, "x", {}])["game_rows"] >= 0
    assert potd.price_gap(None)["refused_on_price"] == 0


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
