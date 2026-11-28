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
                   "words": "One book has every leg now: FanDuel (-114, -140)"}, got
    # With the under's books unread the legs' own books (DraftKings, FanDuel) differed and nothing was said.


def test_a_scorer_off_the_touchdown_field_is_still_filed_once_a_book():
    board = {"recommendations": [{"player": "Cam Skattebo", "market": "anytime_td", "side": "OVER", "line": 0.5,
                                  "all_lines": [_q("FanDuel", 0.5, 130, 0)]}],
             "td_field": [{"player": "Cam Skattebo", "market": "anytime_td", "odds": 125, "book": "FanDuel"},
                          {"player": "Cam Skattebo", "market": "anytime_td", "odds": 140, "book": "BetMGM"}]}
    got = sorted(SL.quote_index(board)[("cam skattebo", "anytime_td")]["quotes"])
    assert got == [(0.5, "BetMGM", 140, 0), (0.5, "FanDuel", 130, 0)], got


# --- why a leg's number has no book, counted (the cause is read off the heartbeat, not guessed) -----
def _leg(player, market, side, line, **kw):
    return dict({"player": player, "market": market, "side": side, "line": line}, **kw)


def test_a_leg_with_no_book_at_its_number_says_which_kind_of_gap():
    board = {"recommendations": [
        _row(),
        {"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
         "all_lines": [_q("Pinnacle", 4.5, -120, 100), _q("DraftKings", 5.5, 120, -150)]},
        {"player": "Cam Skattebo", "market": "rush_att", "side": "OVER", "line": 11.5,
         "all_lines": [_q("proxy", 11.5, -110, -110)]},
        {"player": "Chig Okonkwo", "market": "receptions", "side": "OVER", "line": 2.5,
         "all_lines": [_q("DraftKings", 2.5, -160, 0)]}],
        # A pick row carries no book's list: its prop is "on file" and the build's prop rows hold nothing for it.
        "most_likely": [{"player": "Rachaad White", "market": "rush_yds", "side": "Over", "line": 29.5}]}
    gap = lambda *a, **kw: GP.leg_gap(_leg(*a, **kw), board)                      # noqa: E731
    assert gap("Jayden Daniels", "pass_cmp", "Under", 19.5) is None, "a book quotes it"
    assert gap("Nobody", "receptions", "Over", 2.5) is None, "its prop is not on file: no_row, not a gap"
    assert gap("Rachaad White", "rush_yds", "Over", 29.5) == {"why": "no_prop_row"}
    assert gap("Cam Skattebo", "rush_att", "Over", 11.5) == {"why": "no_lines"}, "a proxy price is no book's"
    assert gap("Malik Nabers", "receptions", "Over", 4.5) == {"why": "sharp_only"}
    assert gap("Jayden Daniels", "pass_cmp", "Under", 17.5) == {"why": "other_side"}, "the ladder's over alone"
    assert gap("Jayden Daniels", "pass_cmp", "Under", 20.5) == {"why": "other_numbers", "near": 1.0}
    assert gap("Jayden Daniels", "pass_cmp", "Over", 18.5) == {"why": "other_numbers", "near": 1.0}
    assert gap("Chig Okonkwo", "receptions", "Under", 3.5) == {"why": "side_unpriced"}
    assert GP.LEG_GAPS == ("no_prop_row", "no_lines", "sharp_only", "other_side", "other_numbers", "side_unpriced",
                           "error")
    assert GP.leg_gap(None, board) is None, "nothing to read"
    # A leg it cannot read is counted, never passed over as one a book quotes.
    assert GP.leg_gap(_leg("Jayden Daniels", "pass_cmp", "Under", None), board) == {"why": "error"}


def test_the_heartbeat_counts_each_gap_by_its_kind():
    import json
    import launch as L
    sys.path.insert(0, str(ROOT / "tests"))
    EG = __import__("test_each_game_gets_its_parlays")
    b = EG.board()
    # Every Most Likely row's own number at a book, but one prop's rows list another number only.
    b["recommendations"] = [
        {"player": r["player"], "market": r["market"], "side": r["side"],
         "line": r["line"], "all_lines": [_q("DraftKings", r["line"] + (1.0 if r["player"] == "Malik Nabers" else 0.0),
                                             -150, 120)]} for r in b["most_likely"]]
    GP.attach(b, "nfl")
    g = b["game_parlays"]["games"][0]
    n = sum(l["player"] == "Malik Nabers" and l["market"] == "receptions" for t in g["twos"] + g["threes"] for l in t["legs"])
    assert n >= 2
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["one_book_legs"]["no_quote"] == n and got["one_book_legs"]["unlisted"] == 0
    assert got["one_book_gaps"] == {"why": {"other_numbers": n}, "pool": {"likely": n}, "side": {"over": n},
                                    "market": {"receptions": n}, "own_book": {"real": n}, "near": {"1": n},
                                    "carried": {"no": n}}, got["one_book_gaps"]
    # A board with every leg quoted says nothing of gaps.
    b2 = EG.board()
    b2["recommendations"] = [{"player": r["player"], "market": r["market"], "side": r["side"], "line": r["line"],
                              "all_lines": [_q("DraftKings", r["line"], -150, 120)]} for r in b2["most_likely"]]
    GP.attach(b2, "nfl")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b2, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            assert "one_book_gaps" not in L._board_counts(path)
        finally:
            L._full_copy = was


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
