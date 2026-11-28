"""When to bet is read off the journal correctly.

Ethan, 2026-10-04: "do all of it" — first, whether a Most Likely pick's
price gets better or worse between posting and kickoff. bettiming.py reads
it. Checks: a pick posted Saturday night Eastern for a Sunday game is "day
before" even though its UTC stamp is Sunday; profit at a price is right on
both sides; a price that shortened is CLV toward us; the verdict needs the
sample and the size before it says anything.

2026-10-04, after the first box run: the journal's close is one arbitrary
book's quote while we post the best price on the screen, so best-of-books
against one book read as "the price moved toward us" with nothing moving.
The verdict now reads the SAME book's close from the odds history; checks
that a best-price post with no movement is no CLV, and that the same-book
close is found, pre-game only, at the same line and side.

Run directly: `python3 tests/test_bet_timing_reads_the_journal_right.py`
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
import bettiming as T                                                # noqa: E402


class _Closes:
    """Same-book close = the 6th column, as if the odds history had it."""
    def same_and_best(self, b):
        return b["closing_odds"], b["closing_odds"]


def test_the_day_is_eastern_not_utc():
    assert T.days_ahead("2026-10-04T02:30:00", "2026-10-04") == 1, "10:30pm Saturday ET"
    assert T.days_ahead("2026-10-04T15:00:00", "2026-10-04") == 0
    assert T.bucket(3) == "2+ days" and T.bucket(None) == "unknown"


def test_profit_and_clv_read_the_price_both_ways():
    assert T.profit(-150, "won") == 100 / 150 and T.profit(120, "won") == 1.2
    assert T.profit(-150, "lost") == -1.0 and T.profit(-150, "push") == 0.0
    took, closed = T.implied(-150), T.implied(-170)
    assert closed > took, "a price that shortened moved toward us"


def _db(rows):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE bets (sport, category, ts, game_day, odds, closing_odds, status, hit_prob)")
    c.executemany("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)", rows)
    return c


def test_the_verdict_waits_for_the_sample_and_the_size():
    few = _db([("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "won", 0.6)] * 20)
    s = T.summarize(T.rows(few, closes=_Closes()))
    assert "not enough" in T.verdict(s)
    import random
    rnd = random.Random(1)
    many = [("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150,
             rnd.choice((-170, -165, -160, -150, -145)), rnd.choice(("won", "lost")), 0.6) for _ in range(300)]
    s = T.summarize(T.rows(_db(many), closes=_Closes()))
    assert T.verdict(s).startswith("BET WHEN POSTED"), T.verdict(s)
    flat = [("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150,
             rnd.choice((-160, -140)), "won", 0.6) for _ in range(300)]
    assert "no difference" in T.verdict(T.summarize(T.rows(_db(flat), closes=_Closes())))


def test_only_published_books_and_settled_rows():
    c = _db([("nfl", "stale", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "won", 0.6),
             ("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "open", 0.6),
             ("nfl", "board", "2026-10-03T15:00:00", "2026-10-04", -150, None, "lost", 0.6)])
    rs = T.rows(c, closes=_Closes())
    assert len(rs) == 1 and rs[0]["clv"] is None


def test_the_journal_close_alone_never_makes_a_verdict():
    # 300 picks whose journal close is shorter than our price: without a
    # same-book close that is the best-of-books bias, not movement.
    rows = [("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "won", 0.6)] * 300
    s = T.summarize(T.rows(_db(rows)))
    assert s["with_close"] == 0 and s["journal_n"] == 300 and "not enough" in T.verdict(s)


def _hist(quotes):
    h = sqlite3.connect(":memory:")
    h.row_factory = sqlite3.Row
    h.execute("CREATE TABLE odds_history (sport, taken_at, event_id, home, away, player, market, book, "
              "line, over_odds, under_odds, commence_time)")
    h.executemany("INSERT INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", quotes)
    return h


def _bet_row(book="FanDuel", side="OVER", line=4.5):
    return {"sport": "nfl", "category": "likely_live", "ts": "2026-10-04T14:00:00", "game_day": "2026-10-04",
            "date": "2026-10-04", "player": "Tee Higgins", "market": "receptions", "side": side,
            "line": line, "book": book, "lead_min": 180.0, "odds": -110}


def test_the_same_book_close_is_found_pregame_at_the_same_line():
    from engine.sources.oddsapi import normalize_name
    who = normalize_name("Tee Higgins")
    h = _hist([
        ("nfl", "2026-10-04T16:30:00", "e1", "", "", who, "receptions", "fanduel", 4.5, -125, 105, "2026-10-04T17:00:00"),
        ("nfl", "2026-10-04T16:30:00", "e1", "", "", who, "receptions", "draftkings", 4.5, -105, -115, "2026-10-04T17:00:00"),
        ("nfl", "2026-10-04T16:30:00", "e1", "", "", who, "receptions", "betmgm", 5.5, 120, -150, "2026-10-04T17:00:00"),
        # in play: never a close
        ("nfl", "2026-10-04T18:00:00", "e1", "", "", who, "receptions", "fanduel", 4.5, -400, 300, "2026-10-04T17:00:00"),
    ])
    same, best = T.BookCloses(h).same_and_best(_bet_row())
    assert same == -125, "FanDuel's own pre-game close"
    assert best == -105, "the longest over at 4.5; BetMGM's 5.5 is another bet"
    same_u, _ = T.BookCloses(h).same_and_best(_bet_row(side="UNDER"))
    assert same_u == 105
    none, _ = T.BookCloses(h).same_and_best(_bet_row(book="Caesars"))
    assert none is None, "no Caesars quote: no same-book close"



def test_the_same_book_close_is_read_from_our_own_snapshots_too():
    import datetime as dt
    start = dt.datetime(2026, 10, 4, 17, 0, tzinfo=dt.timezone.utc).timestamp()
    snap = lambda book, mins, over, under, line=4.5: {
        "player": "Tee Higgins", "market": "receptions", "line": line, "book": book,
        "over_odds": over, "under_odds": under, "ts": start + mins * 60, "start_ts": start}
    rows = [snap("FanDuel", -120, -115, -105), snap("FanDuel", -30, -130, 110),     # FanDuel's close: -130
            snap("DraftKings", -30, -110, -110), snap("williamhill_us", -30, -125, 105),
            snap("FanDuel", 45, -300, 240),                                       # in play: never a close
            snap("BetMGM", -30, 140, -170, line=5.5)]                              # another line
    c = T.BookCloses(None, snapshots=rows)
    b = _bet_row()
    c.prepare([b])
    same, best = c.same_and_best(b)
    assert same == -130 and best == -110
    assert c.same_and_best(_bet_row(book="Caesars"))[0] == -125, "williamhill_us is Caesars"
    assert c.same_and_best(_bet_row(side="UNDER"))[0] == 110


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
