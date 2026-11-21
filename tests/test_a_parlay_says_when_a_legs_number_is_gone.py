"""A parlay says when a leg's number is on no book now, and the one-book line cites only today's quotes
(step AAE, 2026-11-21).

A Most Likely pick stays up at the number, price and book it was posted at while the books move
(engine/likely `lock`: "The number, the price and the book stay as posted"), and a parlay leg made from it
carries those. Sunday's picks go up from the Thursday. (This step took the 35 NFL legs the heartbeat
counted with no book at their number for such picks; its own count read 0 on the live board. Step AAF
then found the quote index losing an under's price: tests/test_a_books_main_line_and_its_ladder_are_two_quotes.py.)
What these hold of a carried pick:

  * A CARRIED PICK'S POSTED PRICE IS NO QUOTE TODAY. Step AAD counted every leg's own book and price as a
    quote, so the line could name a book at a price it no longer showed. Only today's quotes speak for a
    carried pick; a leg priced on this build still counts its own.
  * A TICKET WITH A LEG NO BOOK LISTS NOW SAYS SO in the line's place: it cannot be placed as written,
    which leg, and the nearest number a book has for it.
  * A SHARP BOOK IS NEVER THE ONE BOOK: nobody here can bet it (engine/odds.is_sharp_book).
  * A TICKET NOT POSTED BEFORE TAKES NO SUCH LEG, nor does a backup. One already posted stays (ZQ: a
    game's posted parlays stay until a leg breaks) and says which leg.
  * The card and the page mark it, Report Picks does not lead with it, Ask is told, and the heartbeat
    counts such tickets and legs.

    python3 tests/test_a_parlay_says_when_a_legs_number_is_gone.py
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME
GONE = ("Can't be placed as written now: no book in our latest pull lists Malik Nabers over 4.5 receptions "
        "(the nearest number a book has is 5.5, FanDuel +110). It was listed when the pick went up")


def _quotes(*books):
    return [{"book": b, "line": line, "over_odds": o, "under_odds": u} for b, line, o, u in books]


def _board(moved=("Malik Nabers",)):
    """The fixture board with every Most Likely pick's number at two books today, except the picks of
    ``moved``: posted on an earlier build (the lock's row) and the books now a point higher."""
    b = EG.board()
    b["recommendations"] = []
    for r in b["most_likely"]:
        gone = r["player"] in moved and r["market"] != "pass_cmp"
        line = r["line"] + 1.0 if gone else r["line"]
        b["recommendations"].append({
            "player": r["player"], "market": r["market"], "side": r["side"], "line": line,
            "all_lines": _quotes(("DraftKings", line, 105 if gone else -150, -135 if gone else 120),
                                 ("FanDuel", line, 110 if gone else -160, -140 if gone else 125))})
        if gone:
            r.update(locked=True, lock_why="number moved", now_listed=False, now_odds=None, now_book="")
    return b


def _leg(b, player, market="receptions"):
    r = next(r for r in b["most_likely"] if r["player"] == player and r["market"] == market)
    return {k: r[k] for k in ("player", "market", "market_label", "side", "line", "odds", "book")}


def _has(t, player="Malik Nabers", market="receptions"):
    return any(l.get("player") == player and l.get("market") == market for l in t["legs"])


def _js(name):
    return (ROOT / "web" / "js" / f"{name}.js").read_text(encoding="utf-8")


# --- which picks are carried, and where a leg's books stand ---------------------------------------
def test_a_carried_pick_is_found_and_its_leg_reads_unlisted():
    b = _board()
    carried, idx = GP.carried_picks(b), GP.quote_index(b)
    assert list(carried) == [GP._pick_key(_leg(b, "Malik Nabers"))], list(carried)
    assert carried[GP._pick_key(_leg(b, "Malik Nabers"))]["lock_why"] == "number moved"
    nabers, daniels = _leg(b, "Malik Nabers"), _leg(b, "Jayden Daniels", "rush_yds")
    assert GP.leg_quoted(nabers, idx, carried) == "unlisted"
    assert GP.leg_quoted(nabers, idx) == "no_quote", "with no word on which picks are carried it is only unquoted"
    assert GP.leg_quoted(daniels, idx, carried) == "quoted"
    assert GP.leg_quoted({"player": "Nobody", "market": "receptions", "side": "Over", "line": 2.5}, idx, carried) == "no_row"
    assert GP.LEG_QUOTES == ("quoted", "unlisted", "no_quote", "no_row")
    # A game line the board carries forward is no player pick, and a board with none has none.
    b["most_likely"].append({"player": "Giants", "kind": "game", "market": "spread", "side": "Over", "line": -2.5,
                             "locked": True})
    assert len(GP.carried_picks(dict(b))) == 1 and GP.carried_picks(EG.board()) == {} and GP.carried_picks(None) == {}
    # The one board's rows are read too.
    lb = {"recommendations": b["recommendations"], "likely_board": {"rows": [r for r in b["most_likely"] if r.get("locked")]}}
    assert len(GP.carried_picks(lb)) == 1


def test_a_board_is_read_once_until_it_changes():
    from engine import sliplive
    calls = []
    was = sliplive.quote_index

    def counted(board):
        calls.append(1)
        return was(board)
    sliplive.quote_index = counted
    try:
        b = _board()                                         # (no matchup picks, no one-board rows: empty lists)
        for _ in range(3):
            GP.quote_index(b), GP.carried_picks(b)
        GP.legs_for(b, "nfl")
        GP.build(b, "nfl")
        assert len(calls) == 1, f"read {len(calls)} times"
        b["likely_board"] = {"rows": [r for r in b["most_likely"] if r.get("locked")]}
        for _ in range(3):
            GP.quote_index(b), GP.carried_picks(b)
        assert len(calls) == 2, "and once more when a list arrives"
    finally:
        sliplive.quote_index = was


def test_the_reads_follow_the_board_as_its_lists_fill():
    b = _board()
    rows, b["most_likely"] = b["most_likely"], []
    assert GP.carried_picks(b) == {}
    b["most_likely"] = rows                                  # the same board object, a list filled since
    assert len(GP.carried_picks(b)) == 1
    # A row swapped for another in place (as the lock swaps a posted pick's row in) is read again too.
    i = next(i for i, r in enumerate(rows) if r["player"] == "Chig Okonkwo")
    rows[i] = dict(rows[i], locked=True, lock_why="number moved", now_listed=False)
    assert len(GP.carried_picks(b)) == 2
    j = next(j for j, r in enumerate(b["recommendations"]) if r["player"] == "Chig Okonkwo")
    assert GP.leg_quoted(_leg(b, "Chig Okonkwo"), GP.quote_index(b), GP.carried_picks(b)) == "quoted"
    b["recommendations"][j] = dict(b["recommendations"][j], all_lines=_quotes(("DraftKings", 3.5, 105, -135)))
    assert GP.leg_quoted(_leg(b, "Chig Okonkwo"), GP.quote_index(b), GP.carried_picks(b)) == "unlisted"


# --- the line ---------------------------------------------------------------------------------------
def test_a_posted_price_is_never_a_quote_today():
    b = _board()
    carried, idx = GP.carried_picks(b), GP.quote_index(b)
    nabers, daniels = _leg(b, "Malik Nabers"), _leg(b, "Jayden Daniels", "rush_yds")
    assert (nabers["book"], nabers["odds"]) == ("DraftKings", -250), "the price it went up at"
    got = GP.one_book([nabers, daniels], idx, carried)
    assert got == {"gone": True, "legs": 1, "words": GONE}, got
    # A leg priced on this build still counts its own book and price (no carried pick among these).
    fresh = GP.one_book([nabers, daniels], idx)
    assert fresh["book"] == "DraftKings" and fresh["odds"] == [-250, -150], fresh
    # A carried pick whose number a book still lists: today's price speaks, never the posted one.
    b2 = _board(moved=())
    for r in b2["most_likely"]:
        if r["player"] == "Jayden Daniels" and r["market"] == "rush_yds":
            r.update(locked=True, lock_why="a likelier pick took its seat", now_listed=True, now_odds=-150,
                     now_book="DraftKings")
    posted = _leg(b2, "Jayden Daniels", "rush_yds")
    assert posted["odds"] == -200
    still = GP.one_book([posted, _leg(b2, "Malik Nabers")], GP.quote_index(b2), GP.carried_picks(b2))
    assert still == {"book": "DraftKings", "odds": [-150, -150], "books": 2,
                     "words": "One book has every leg: DraftKings (-150, -150)"}, still


def test_two_legs_gone_and_a_prop_no_book_prices_on_that_side():
    b = _board(moved=("Malik Nabers", "Chig Okonkwo"))
    carried, idx = GP.carried_picks(b), GP.quote_index(b)
    got = GP.one_book([_leg(b, "Malik Nabers"), _leg(b, "Chig Okonkwo"), _leg(b, "Isaiah Likely")], idx, carried)
    assert got["gone"] is True and got["legs"] == 2
    assert got["words"] == (
        "Can't be placed as written now: no book in our latest pull lists Malik Nabers over 4.5 receptions "
        "(the nearest number a book has is 5.5, FanDuel +110) or Chig Okonkwo over 2.5 receptions "
        "(the nearest number a book has is 3.5, FanDuel +110). They were listed when the picks went up"), got["words"]
    # Its prop priced on the other side only, or by no book at all: no nearest number to say.
    for r in b["recommendations"]:
        if r["player"] == "Malik Nabers":
            r["all_lines"] = _quotes(("DraftKings", 5.5, 0, -135))
    b["recommendations"] = list(b["recommendations"])        # (a new list: the board is read again)
    assert GP.book_prices(_leg(b, "Malik Nabers"), GP.quote_index(b)) == {}
    one = GP.one_book([_leg(b, "Malik Nabers"), _leg(b, "Isaiah Likely")], GP.quote_index(b), GP.carried_picks(b))
    assert one["words"] == ("Can't be placed as written now: no book in our latest pull lists Malik Nabers "
                            "over 4.5 receptions. It was listed when the pick went up"), one["words"]
    assert GP._and_or(["a"]) == "a" and GP._and_or(["a", "b"]) == "a or b" and GP._and_or(["a", "b", "c"]) == "a, b or c"


def test_a_sharp_book_is_never_the_one_book():
    b = {"recommendations": [
        {"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
         "all_lines": _quotes(("Pinnacle", 4.5, -120, 100), ("DraftKings", 4.5, -150, 120))},
        {"player": "Jayden Daniels", "market": "rush_yds", "side": "OVER", "line": 24.5,
         "all_lines": _quotes(("Pinnacle", 24.5, -130, 105), ("DraftKings", 24.5, -180, 140))}]}
    idx = GP.quote_index(b)
    a = {"player": "Malik Nabers", "market": "receptions", "side": "Over", "line": 4.5}
    c = {"player": "Jayden Daniels", "market": "rush_yds", "side": "Over", "line": 24.5}
    assert GP.book_prices(a, idx) == {"draftkings": ("DraftKings", -150)}, "Pinnacle pays more and nobody here can bet it"
    assert GP.one_book([a, c], idx)["book"] == "DraftKings"
    # Nor does a leg's own sharp book count.
    lone = {"player": "Chig Okonkwo", "market": "receptions", "side": "Over", "line": 2.5, "book": "Pinnacle", "odds": -140}
    assert GP.one_book([lone, dict(lone, player="Rachaad White")], {}) is None


# --- which tickets take such a leg ------------------------------------------------------------------
def test_a_new_ticket_takes_no_leg_whose_number_is_gone():
    plain = GP.build(EG.board(), "nfl")["games"][0]
    assert any(_has(t) for t in plain["twos"]) and any(_has(t) for t in plain["threes"]), \
        "with its number listed the game's likeliest pick rides its tickets"
    g = GP.build(_board(), "nfl")["games"][0]
    assert len(g["twos"]) == 3 and len(g["threes"]) == 3, "the game still makes its three of each from the rest"
    assert not any(_has(t) for t in g["twos"] + g["threes"])
    assert not any(b["leg"].get("player") == "Malik Nabers" and b["leg"].get("market") == "receptions"
                   for t in g["twos"] + g["threes"] for b in t.get("backups") or []), "nor is it a backup"
    assert all((t.get("one_book") or {}).get("book") == "DraftKings" for t in g["twos"] + g["threes"])
    # The mark is working state: no published leg carries it.
    assert not any("_unlisted" in l for t in g["twos"] + g["threes"] for l in t["legs"])
    b = _board()
    legs = GP.legs_for(b, "nfl")
    assert [l["player"] for l in legs if l.get("_unlisted")] == ["Malik Nabers"]


def test_a_posted_ticket_stays_and_says_which_leg():
    plain = GP.build(EG.board(), "nfl")["games"][0]
    two = next(t for t in plain["twos"] if _has(t))
    three = next(t for t in plain["threes"] if _has(t))
    b = _board()
    legs = GP.enrich(GP.legs_for(b, "nfl"), b)
    for size, key, was in ((2, "twos", two), (3, "threes", three)):
        fresh = GP.tickets_of("nfl", GAME, legs, size=size)[key]
        assert not any(_has(t) for t in fresh), key
        # (An identity read back from the kept file is lists, not tuples.)
        posted = {key: [[list(x) for x in GP.ident(was)]]}
        kept = GP.tickets_of("nfl", GAME, legs, posted=posted, size=size)[key]
        assert GP.ident(kept[0]) == GP.ident(was), f"{key}: the posted ticket is posted again, first"
        assert sum(_has(t) for t in kept) == 1, f"{key}: and no other ticket takes the leg"
        x = GP.label_tickets({key: kept}, "nfl", GP.quote_index(b), GP.carried_picks(b))
        assert x[key][0]["one_book"] == {"gone": True, "legs": 1, "words": GONE}, x[key][0].get("one_book")
        assert all((t.get("one_book") or {}).get("book") for t in x[key][1:])


def test_the_pick_census_says_unlisted():
    """What became of each report pick as a leg (the heartbeat's pick_fates): a pick at a number no book lists
    now is its own count, never "strong", which is what a ticket is made of."""
    tp = __import__("test_the_parlays_are_made_of_the_reports_picks")
    b = _board()
    b["game_parlays"] = GP.build(b, "nfl")
    x = GP.from_report(b, "nfl", GAME, tp.PICKS)
    assert x["pick_fates"].get("unlisted") == 1, x["pick_fates"]
    assert not any(_has(t) for t in x["twos"] + x["threes"])
    plain = EG.board()
    plain["game_parlays"] = GP.build(plain, "nfl")
    was = GP.from_report(plain, "nfl", GAME, tp.PICKS)["pick_fates"]
    assert "unlisted" not in was and was.get("strong", 0) == x["pick_fates"].get("strong", 0) + 1
    assert GP.PICK_FATES.index("unlisted") == GP.PICK_FATES.index("low") + 1


def test_the_number_coming_back_clears_the_mark():
    b = _board()
    legs = GP.legs_for(b, "nfl")
    assert sum(bool(l.get("_unlisted")) for l in legs) == 1
    back = _board()
    back["recommendations"].append({"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
                                    "all_lines": _quotes(("BetMGM", 4.5, -240, 180))})
    assert not any(l.get("_unlisted") for l in GP.mark_unlisted(legs, back))
    # No board, no legs: nothing to mark, and nothing went wrong.
    assert GP.mark_unlisted([{"player": "X"}, None], None) == [{"player": "X"}, None]
    assert GP.mark_unlisted(None, {}) is None and GP.UNLISTED_ERROR is None


def test_a_board_it_cannot_read_marks_nothing_and_says_so():
    import contextlib
    import io
    b = _board()
    legs = GP.legs_for(b, "nfl")
    assert sum(bool(l.get("_unlisted")) for l in legs) == 1
    was = GP._pick_key

    def broken(_row):
        raise ValueError("no rows")
    GP._pick_key = broken
    try:
        bad = _board()                                       # (a new board: read afresh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert GP.mark_unlisted(legs, bad) is legs, "never raises"
            GP.mark_unlisted(legs, bad)
            assert GP.quote_index(bad) and GP.carried_picks(bad) == {}, "the quotes are still read"
        said = "could not read which picks' numbers a book still lists (RuntimeError: ValueError: no rows)"
        assert out.getvalue().count(said) == 1, "said once a process, not once a game: " + out.getvalue()
        assert GP.UNLISTED_ERROR == "RuntimeError: ValueError: no rows"
        # The build still makes its tickets, and its counts carry the failure, which no quiet day's do.
        with contextlib.redirect_stdout(io.StringIO()):
            built = GP.build(bad, "nfl")
        assert built["counts"]["unlisted_error"] == "RuntimeError: ValueError: no rows"
        assert len(built["games"][0]["twos"]) == 3 and len(built["games"][0]["threes"]) == 3
    finally:
        GP._pick_key = was
    assert "unlisted_error" not in GP.build(_board(), "nfl")["counts"] and GP.UNLISTED_ERROR is None


# --- the card, the page and the heartbeat -----------------------------------------------------------
def _posted_board():
    """The moved board holding the tickets it posted while every number was listed."""
    b = _board()
    b["game_parlays"] = GP.build(EG.board(), "nfl")
    for e in b["game_parlays"]["games"]:
        GP.label_tickets(e, "nfl", GP.quote_index(b), GP.carried_picks(b))
    return b


def test_the_card_and_the_page_mark_a_ticket_that_cannot_be_placed():
    g = _posted_board()["game_parlays"]["games"][0]
    gone = next(t for t in g["twos"] if _has(t))
    c = GP.card(gone, 1, "two", "nfl")
    assert c["one_book"] == GONE and c["one_book_gone"] is True
    fine = GP.card(next(t for t in g["twos"] if not _has(t)), 2, "two", "nfl")
    assert fine["one_book"].startswith("One book has every leg: ") and "one_book_gone" not in fine
    report = _js("report")
    assert '<p class="gr-parlay-book${t.one_book_gone ? " gone" : ""}">${escapeHtml(t.one_book)}</p>' in report
    assert "one_book_gone: !!(t.one_book || {}).gone," in report, "the page's own card carries it too"
    # No "Bet it" on a ticket that cannot be placed as written.
    assert "(t.bet_legs || []).length && !CLOSED && !t.one_book_gone" in report
    # Where to place a ticket is said of a game still to play: not once it has started or finished.
    assert '${t.one_book && !CLOSED ? `<p class="gr-parlay-book' in report
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    assert ".gr-parlay-book.gone { color: var(--warn); }" in css
    # Ask reads the same words off the ticket.
    from engine import askbot
    assert askbot._game_ticket(gone, "nfl", "two", g)["one_book"] == GONE


def test_report_picks_does_not_lead_with_a_ticket_that_cannot_be_placed():
    RP = __import__("test_report_picks_leads_with_the_likeliest_tickets")
    b = RP._board()
    # The day's likeliest ticket (Pacers at Celtics, two legs, 58%) has a leg no book lists now.
    b["game_parlays"]["games"][0]["twos"][0]["one_book"] = {"gone": True, "legs": 1, "words": GONE}
    got = RP._run(b, ["IND@BOS", "MIA@CHI", "DEN@UTA", "LAL@GSW", "NYK@PHI"])
    if got is None:
        print("      (skipped: no Node)")
        return
    top = got[0]
    assert top == [["DEN@UTA", "two", 0.52], ["MIA@CHI", "three", 0.41], ["IND@BOS", "three", 0.34]], top
    # Ask says the same of it (our_picks' parlays).
    from engine import askbot
    g = _posted_board()["game_parlays"]["games"][0]
    gone = next(t for t in g["twos"] if _has(t))
    assert askbot._game_ticket(gone, "nfl", "two", g)["cannot_be_placed_now"] is True
    assert "cannot_be_placed_now" not in askbot._game_ticket(next(t for t in g["twos"] if not _has(t)), "nfl", "two", g)
    assert "one marked cannot_be_placed_now has a leg whose number no book lists any more" in \
        (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")


def test_a_proxy_priced_pick_was_never_a_books_listing():
    b = _board()
    carried, idx = GP.carried_picks(b), GP.quote_index(b)
    proxy = dict(_leg(b, "Malik Nabers"), book="proxy")
    assert GP.one_book([proxy, _leg(b, "Jayden Daniels", "rush_yds")], idx, carried) is None, \
        "nothing to say: no book listed it, so none stopped"


def test_the_heartbeat_counts_gone_tickets_and_unlisted_legs():
    import launch as L
    b = _posted_board()
    g = b["game_parlays"]["games"][0]
    n_gone = sum(_has(t) for t in g["twos"] + g["threes"])
    n_legs = sum(len(t["legs"]) for t in g["twos"] + g["threes"])
    assert n_gone >= 2
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
    assert got["one_book"] == {"one": 6 - n_gone, "none": 0, "gone": n_gone, "unknown": 0}, got.get("one_book")
    assert got["one_book_legs"] == {"quoted": n_legs - n_gone, "unlisted": n_gone, "no_quote": 0, "no_row": 0}, \
        got.get("one_book_legs")


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
