"""A book's main line and a rung of its ladder at the same number are two quotes (step AAF, 2026-11-21).

The parlays' one-book line (engine/gameparlays.one_book) reads every book's quotes through the slip's
index (engine/sliplive.quote_index). On the first NFL boards that counted it, 35 of 165 parlay legs had
their prop on file and no book at their number (the heartbeat's ``one_book_legs``, 20 November). Step AAE
took those for picks carried at a posted number and counted them apart; its count read 0 on the live board
with the same 35 still unquoted, so that was not it.

A cause, reproduced here: the index filed a book's quotes under (book, number). A book's main line
quotes both sides; its ladder ("5+ receptions") lists the same number again, mostly as the over alone.
The ladder was filed last and replaced the main line, so the under's price was gone: an under at a number
its book also laddered showed no book at all, on a parlay's one-book line and in a slip's live prices.
What these hold:

  * Both quotes are kept. An under reads the main line's price, an over the better of the two.
  * The market's fair chance is still taken from a book's own pair, never from one side of each.
  * A ladder that lists a number's two sides apart keeps both.
  * A scorer's price off the touchdown field is still filed once a book.
  * The parlays' one-book line and a slip's live prices name the books for an under.

    python3 tests/test_a_books_main_line_and_its_ladder_are_two_quotes.py
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, sliplive as SL  # noqa: E402


def _q(book, line, over, under):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _row():
    """One prop as two books quote it: the main line both ways, and each book's ladder, which lists the
    main number again as an over only."""
    return {"player": "Jayden Daniels", "market": "pass_cmp", "side": "UNDER", "line": 19.5,
            "all_lines": [_q("DraftKings", 19.5, -105, -119), _q("FanDuel", 19.5, -110, -114)],
            "alt_lines": [_q("DraftKings", 17.5, -220, 0), _q("DraftKings", 19.5, -108, 0),
                          _q("FanDuel", 19.5, -102, None), _q("FanDuel", 21.5, 150, 0)]}


def _quotes(board):
    return SL.quote_index(board)[("jayden daniels", "pass_cmp")]["quotes"]


def test_the_main_line_and_the_ladder_rung_are_both_kept():
    got = sorted(_quotes({"recommendations": [_row()]}))
    assert got == [(17.5, "DraftKings", -220, 0), (19.5, "DraftKings", -108, 0), (19.5, "DraftKings", -105, -119),
                   (19.5, "FanDuel", -110, -114), (19.5, "FanDuel", -102, 0), (21.5, "FanDuel", 150, 0)], got
    # The same row twice over (a board lists a prop on more than one list) files nothing twice.
    assert sorted(_quotes({"recommendations": [_row(), _row()]})) == got


def test_an_under_reads_the_main_lines_price_and_an_over_the_better_of_the_two():
    idx = GP.quote_index({"recommendations": [_row()]})
    under = {"player": "Jayden Daniels", "market": "pass_cmp", "side": "Under", "line": 19.5}
    assert GP.book_prices(under, idx) == {"draftkings": ("DraftKings", -119), "fanduel": ("FanDuel", -114)}
    assert GP.leg_quoted(under, idx) == "quoted", "it read no_quote while the ladder's rung replaced the main line"
    # DraftKings pays more on its main line (-105), FanDuel on its ladder (-102).
    assert GP.book_prices(dict(under, side="Over"), idx) == {"draftkings": ("DraftKings", -105), "fanduel": ("FanDuel", -102)}
    # A number only the ladder lists has its over and no under.
    assert GP.book_prices(dict(under, side="Over", line=17.5), idx) == {"draftkings": ("DraftKings", -220)}
    assert GP.book_prices(dict(under, line=17.5), idx) == {}


def test_a_slips_live_prices_name_the_books_for_an_under():
    idx = SL.quote_index({"recommendations": [_row()]})
    leg = {"player": "Jayden Daniels", "market": "pass_cmp", "side": "under", "line": 19.5, "odds": -119}
    got = SL.leg_prices(leg, idx, {})
    assert got["books"] == [{"book": "FanDuel", "odds": -114}, {"book": "DraftKings", "odds": -119}], got["books"]
    assert (got["best"], got["book"], got["n"]) == (-114, "FanDuel", 2) and got["beats_yours"] is True
    # The fair chance is each book's own pair with its margin out (0.515 and 0.505), their middle: never the
    # ladder's over set against the main line's under.
    assert got["fair"] == 0.5095, got["fair"]
    # The other side at the same number, best price first: what a hedge would be placed at.
    assert got["other"] == {"book": "FanDuel", "odds": -102}
    over = SL.leg_prices(dict(leg, side="over", odds=-110), idx, {})
    assert over["books"] == [{"book": "FanDuel", "odds": -102}, {"book": "DraftKings", "odds": -105}], over["books"]


def test_a_ladder_that_lists_a_numbers_sides_apart_keeps_both():
    row = {"player": "Jayden Daniels", "market": "pass_cmp", "side": "OVER", "line": 21.5,
           "all_lines": [], "alt_lines": [_q("BetMGM", 21.5, 140, 0), _q("BetMGM", 21.5, 0, -175),
                                          _q("BetMGM", 21.5, 135, 0)]}
    assert _quotes({"recommendations": [row]}) == [(21.5, "BetMGM", 140, -175)], "each side keeps its better price"
    assert SL._keep(140, 135) == 140 and SL._keep(-175, 0) == -175 and SL._keep(0, 0) == 0 and SL._keep(0, 120) == 120


def test_the_parlays_one_book_line_speaks_for_a_ticket_with_an_under():
    other = {"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
             "all_lines": [_q("DraftKings", 4.5, -150, 120), _q("FanDuel", 4.5, -140, 110)],
             "alt_lines": [_q("DraftKings", 4.5, -155, 0)]}
    idx = GP.quote_index({"recommendations": [_row(), other]})
    under = {"player": "Jayden Daniels", "market": "pass_cmp", "side": "Under", "line": 19.5,
             "book": "DraftKings", "odds": -119}
    over = {"player": "Malik Nabers", "market": "receptions", "side": "Over", "line": 4.5, "book": "FanDuel", "odds": -140}
    got = GP.one_book([under, over], idx)
    # FanDuel pays 1.877 x 1.714 = 3.22; DraftKings 1.840 x 1.667 = 3.07.
    assert got == {"book": "FanDuel", "odds": [-114, -140], "books": 2,
                   "words": "One book has every leg: FanDuel (-114, -140)"}, got
    # With the under's books unread the legs' own books (DraftKings, FanDuel) differed and nothing was said.


def test_a_scorer_off_the_touchdown_field_is_still_filed_once_a_book():
    board = {"recommendations": [{"player": "Cam Skattebo", "market": "anytime_td", "side": "OVER", "line": 0.5,
                                  "all_lines": [_q("FanDuel", 0.5, 130, 0)]}],
             "td_field": [{"player": "Cam Skattebo", "market": "anytime_td", "odds": 125, "book": "FanDuel"},
                          {"player": "Cam Skattebo", "market": "anytime_td", "odds": 140, "book": "BetMGM"}]}
    got = sorted(SL.quote_index(board)[("cam skattebo", "anytime_td")]["quotes"])
    assert got == [(0.5, "BetMGM", 140, 0), (0.5, "FanDuel", 130, 0)], got


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
