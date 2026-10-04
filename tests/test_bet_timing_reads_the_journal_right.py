"""When to bet is read off the journal correctly.

Ethan, 2026-10-04: "do all of it" — first, whether a Most Likely pick's
price gets better or worse between posting and kickoff. bettiming.py reads
it. Checks: a pick posted Saturday night Eastern for a Sunday game is "day
before" even though its UTC stamp is Sunday; profit at a price is right on
both sides; a price that shortened is CLV toward us; the verdict needs the
sample and the size before it says anything.

Run directly: `python3 tests/test_bet_timing_reads_the_journal_right.py`
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bettiming as T                                                # noqa: E402


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
    s = T.summarize(T.rows(few))
    assert "not enough" in T.verdict(s)
    import random
    rnd = random.Random(1)
    many = [("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150,
             rnd.choice((-170, -165, -160, -150, -145)), rnd.choice(("won", "lost")), 0.6) for _ in range(300)]
    s = T.summarize(T.rows(_db(many)))
    assert T.verdict(s).startswith("BET WHEN POSTED"), T.verdict(s)
    flat = [("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150,
             rnd.choice((-160, -140)), "won", 0.6) for _ in range(300)]
    assert "no difference" in T.verdict(T.summarize(T.rows(_db(flat))))


def test_only_published_books_and_settled_rows():
    c = _db([("nfl", "stale", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "won", 0.6),
             ("nfl", "likely_live", "2026-10-03T15:00:00", "2026-10-04", -150, -170, "open", 0.6),
             ("nfl", "board", "2026-10-03T15:00:00", "2026-10-04", -150, None, "lost", 0.6)])
    rs = T.rows(c)
    assert len(rs) == 1 and rs[0]["clv"] is None


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
