"""A September contract filed under the August day the desk spoke.

Found 2026-09-10 in Ethan's own open journal:

    weather kalshi_wx  date=2026-09-09  game_day=(NONE)      x37
    weather kalshi_wx  date=2026-09-09  game_day=2026-09-09  x25
    nfl     kalshi_ml  date=2026-08-11  game_day=2026-08-11  x10
    ...                date=2026-08-21                       x13

Two faults, one bucket.

THE NULLS. `log_predmarket`'s INSERT never named `game_day`, so every row
it has ever written left that column empty. `day_expr` — the one
expression for "the day this bet belongs to", which the profit calendar,
the curve and the intraday settle window all read — then falls back to
`date`. The split above is the tell: the rows with a day are the ones
`--backfill-days` has since run over, the rows without are everything
journalled since.

THE WRONG DAYS. For this bucket alone, `date` is the day the DESK
RECOMMENDED, not the day the event happens, and `log_predmarket`'s own
docstring says so. The two can be a month apart — the August rows above
are NFL game contracts for September. So the backfill did not rescue
them; it wrote the wrong day with full confidence, because route 1 ("date
is already an ISO day — a copy, not an inference") matched first and a
copy of the wrong column is still wrong.

`predmarket_event_date` already existed for precisely this, one layer
down in the stuck-bet diagnostic. Both writers read it now: the journal
at insert time so the hole cannot reopen, and the backfill ahead of route
1 so the rows already written can be corrected.

THE ROWS ARE NOT STUCK, which is worth saying because they look it. A
Kalshi contract grades against the exchange's own settlements, not
ingested game results, and one for a game a month out is correctly open —
`_why_open_predmarket` is the function written about that. What was
broken was the DAY they sit on, not their status.
"""

import datetime as _dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()

# A Dallas/NY game contract for 2026-09-13, and a New York high-temp
# contract for 2026-09-09 — the two desks Ethan's journal carries.
GAME_TICKER = "KXNFLGAME-26SEP13DALNYG-DA"
WX_TICKER = "KXHIGHNY-26SEP09-B78"


def _journal():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _rec(ticker, sport="nfl"):
    return {"rec": True, "ticker": ticker, "prob": 0.41, "rec_side": "YES",
            "model_p": 0.52, "edge_pts": 11.0, "sport": sport,
            "desk": "kalshi_ml", "title": "Dallas at NY"}


def _day(conn, ticker):
    r = conn.execute("SELECT date, game_day FROM bets WHERE player=?",
                     (ticker,)).fetchone()
    return (r["date"], r["game_day"])


# --- the journal stamps it -------------------------------------------------
def test_a_contract_is_dated_by_the_event_not_by_the_desk():
    """The desk spoke on the 11th about a game on the 13th."""
    conn = _journal()
    assert ledger.log_predmarket(conn, [_rec(GAME_TICKER)],
                                 date="2026-08-11") == 1
    assert _day(conn, GAME_TICKER) == ("2026-08-11", "2026-09-13")


def test_the_slate_date_is_kept_as_the_settle_key():
    """`date` is what every other reader keys on, and a backfill that
    moved it would unsettle the journal to tidy a chart."""
    conn = _journal()
    ledger.log_predmarket(conn, [_rec(GAME_TICKER)], date="2026-08-11")
    assert _day(conn, GAME_TICKER)[0] == "2026-08-11"


def test_a_weather_contract_gets_its_own_day_too():
    conn = _journal()
    ledger.log_predmarket(conn, [_rec(WX_TICKER, sport="weather")],
                          date="2026-09-08")
    assert _day(conn, WX_TICKER) == ("2026-09-08", "2026-09-09")


def test_a_ticker_with_no_date_in_it_falls_back_to_the_slate():
    """Which is the state every row was already in — the fallback may
    not be worse than what it replaces."""
    conn = _journal()
    ledger.log_predmarket(conn, [_rec("NOTATICKER")], date="2026-09-08")
    assert _day(conn, "NOTATICKER") == ("2026-09-08", "2026-09-08")


def test_no_row_is_left_with_an_empty_day():
    """The 37 nulls: `day_expr` falls back to `date` on an empty one, and
    for this bucket that is the wrong column."""
    conn = _journal()
    ledger.log_predmarket(conn, [_rec(GAME_TICKER), _rec("NOTATICKER")],
                          date="2026-08-11")
    n = conn.execute("SELECT COUNT(*) FROM bets WHERE category='predmarket' "
                     "AND (game_day IS NULL OR game_day='')").fetchone()[0]
    assert n == 0


# --- the backfill corrects what is already written --------------------------
def _stale(conn, ticker, date, sport="nfl"):
    """A row as `log_predmarket` used to write it: no game_day at all."""
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, status, category) VALUES (?,?,?,'kalshi_ml','YES',"
        "41.0,-139,0.10,'open','predmarket')", (sport, date, ticker))
    conn.commit()


def test_the_backfill_reads_the_ticker_rather_than_copying_the_date():
    conn = _journal()
    _stale(conn, GAME_TICKER, "2026-08-11")
    out = ledger.backfill_game_days(conn, hist_conn=conn)
    assert out["filled"] == 1
    assert out["by_route"].get("ticker event date") == 1, out["by_route"]
    assert _day(conn, GAME_TICKER)[1] == "2026-09-13"


def test_it_runs_ahead_of_the_route_that_copies_the_date():
    """Route 1 matches a Kalshi row — its `date` IS an ISO day — so
    ordering is the entire fix. A copy of the wrong column is still
    wrong, however exact the copy."""
    i = SRC.index("def backfill_game_days(")
    block = SRC[i:SRC.index("\ndef ", i + 1)]
    assert block.index('"predmarket"') < block.index('"already a day"'), \
        "route 1 still claims a prediction-market row first"


def test_a_predmarket_row_whose_ticker_says_nothing_still_takes_the_date():
    conn = _journal()
    _stale(conn, "NOTATICKER", "2026-09-08")
    ledger.backfill_game_days(conn, hist_conn=conn)
    assert _day(conn, "NOTATICKER")[1] == "2026-09-08"


def test_it_leaves_every_other_bucket_exactly_where_it_was():
    """Route 1 is right for the daily sports and this must not disturb
    it — an MLB slate label IS the day it was played."""
    conn = _journal()
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, status, category) VALUES ('mlb','2026-09-09',"
        "'Aaron Judge','hits','OVER',0.5,-110,0.10,'open','main')")
    conn.commit()
    out = ledger.backfill_game_days(conn, hist_conn=conn)
    assert out["by_route"].get("already a day") == 1
    assert _day(conn, "Aaron Judge")[1] == "2026-09-09"


def test_the_backfill_still_never_moves_the_settle_key():
    conn = _journal()
    _stale(conn, GAME_TICKER, "2026-08-11")
    ledger.backfill_game_days(conn, hist_conn=conn)
    assert _day(conn, GAME_TICKER)[0] == "2026-08-11"


def test_a_stamped_row_is_never_overwritten():
    """The backfill only ever fills a NULL — someone may have corrected
    a row by hand."""
    conn = _journal()
    _stale(conn, GAME_TICKER, "2026-08-11")
    conn.execute("UPDATE bets SET game_day='2026-09-14' WHERE player=?",
                 (GAME_TICKER,))
    conn.commit()
    ledger.backfill_game_days(conn, hist_conn=conn)
    assert _day(conn, GAME_TICKER)[1] == "2026-09-14"


# --- what this means downstream --------------------------------------------
def test_the_shared_day_expression_now_reads_the_event_day():
    """`day_expr` is what the profit calendar, the curve and the settle
    window all bucket on. This is the assertion that says the fix
    actually reaches them."""
    conn = _journal()
    ledger.log_predmarket(conn, [_rec(GAME_TICKER)], date="2026-08-11")
    got = conn.execute(
        f"SELECT {ledger.day_expr()} AS d FROM bets").fetchone()["d"]
    assert got == "2026-09-13"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
