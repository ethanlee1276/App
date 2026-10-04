"""The close banked beside a bet is its own book's, never one picked at random.

Ethan, 2026-10-04 ("yes do it"): the journal compared the BEST price on
the screen with one arbitrary book's close (the purchased history) or the
median of them (our own snapshots). Best-of-six against one book reads as
the market moving toward us when nothing moved — NFL Most Likely read +1.7
points that way and −2.0 against its own books. engine/closebook is the
rule: the posted book's pre-game close, else the best close across books.
Checks: the repair banks the posted book's close; with that book missing
it banks the best one, never the worst or the middle; the settle path and
the repair share the rule; the fair close is left alone.

Run directly: `python3 tests/test_the_close_is_the_same_books.py`
"""
import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import db, ledger                                       # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402


def _fixture():
    tmp = tempfile.mkdtemp()
    hist = db.connect(os.path.join(tmp, "h.db"))
    ledger.DEFAULT_DB = os.path.join(tmp, "l.db")
    return hist, ledger.connect()


def _books(hist, quotes, player="Aaron Judge", line=1.5, date="2025-08-01"):
    db.upsert_odds_history(hist, [{
        "sport": "mlb", "taken_at": f"{date}T23:00:00Z", "event_id": "e1", "home": "A", "away": "B",
        "player": normalize_name(player), "market": "hits", "book": book, "line": line,
        "over_odds": over, "under_odds": under} for book, over, under in quotes])


def _journal(led, book, side="OVER", odds=150):
    led.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,status,stake_units,category,book) "
        "VALUES ('mlb','2025-08-01','Aaron Judge','hits',?,1.5,?,'won',1.0,'main',?)", (side, odds, book))
    led.commit()


def _banked(led):
    return int(led.execute("SELECT closing_odds FROM bets").fetchone()[0])


def _run(quotes, book, side="OVER"):
    saved = ledger.DEFAULT_DB
    try:
        hist, led = _fixture()
        _books(hist, quotes)
        _journal(led, book, side)
        ledger.repair_closing_odds(led, apply=True, hist_conn=hist)
        return _banked(led)
    finally:
        ledger.DEFAULT_DB = saved


QUOTES = [("fanduel", 140, -170), ("draftkings", 125, -150), ("betmgm", 160, -200),
          ("williamhill_us", 130, -160)]


def test_the_repair_banks_the_posted_books_close():
    assert _run(QUOTES, "FanDuel") == 140
    assert _run(QUOTES, "Caesars") == 130, "williamhill_us is Caesars"
    assert _run(QUOTES, "FanDuel", side="UNDER") == -170


def test_with_its_book_missing_it_banks_the_best_close_not_one_at_random():
    assert _run(QUOTES, "Fanatics") == 160, "the longest over across the books"
    assert _run(QUOTES, "Fanatics", side="UNDER") == -150


def test_settling_and_the_repair_share_the_rule():
    settle = inspect.getsource(ledger.settle_from_history)
    repair = inspect.getsource(ledger.repair_closing_odds)
    assert "_same_book_close(" in settle and "_same_book_close(" in repair
    i = settle.index("_same_book_close(")
    assert "closing_fair" not in settle[i:i + 200], "the fair close stays the market's"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
