"""The night the opener ended and nothing graded.

Ethan, 2026-09-10, about half an hour after the Week 1 Wednesday opener
(NE @ SEA) went final: "also none of the nfl bets settled from tonight yet.
game ended about 30 mins ago".

The intraday settle windows the journal to the last few days so it does not
re-read months of history every five minutes. It windowed on `bets.date` —
which is the SLATE LABEL, not the calendar. For the daily sports the label
IS the day; for the NFL it is a week, "2026-W01". Compared as text against
"2026-09-08" the 'W' sorts after every digit, so a week label falls outside
every window the function can build, and no NFL pick has ever appeared in
that list.

Two things followed, and the second is the one that cost the night:

  * `_has_open(lconn, "nfl", days)` matched the same raw column, so a
    football league could never answer yes — which is why no football
    results pull could be hung off that gate;
  * `settle_open` RETURNS EARLY when the day list is empty. On a night whose
    only open picks are football, the whole intraday pass — ingest, grade,
    parlay legs, record export — did not run.

`ledger.day_expr` already existed for exactly this: one expression for "the
day this bet belongs to", reading the kickoff date `game_day` and falling
back to `date` where the label already is the day. These tests pin that both
readers use it, that a real Wednesday-night NFL bet lands inside the window,
and that the daily sports are untouched.
"""

import datetime as _dt
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import maintenance as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()

TODAY = _dt.date(2026, 9, 10)


def _journal(*bets):
    """An in-memory journal holding exactly these rows.

    Each bet is (sport, date, game_day, player, status). No file, no
    fixture, nothing read off the box this runs on.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ledger.SCHEMA)
    for sport, date, game_day, player, status in bets:
        conn.execute(
            "INSERT INTO bets (sport, date, game_day, player, market, side, "
            "line, odds, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (sport, date, game_day, player, "moneyline", "OVER", 0.5, -110,
             status))
    conn.commit()
    return conn


# --- the night itself -------------------------------------------------------
def test_a_wednesday_night_nfl_bet_is_inside_tonights_window():
    """The whole report, in one assertion. The game kicked on the 9th, the
    bet is journalled under week label 2026-W01, and the settle pass runs
    on the 10th."""
    conn = _journal(("nfl", "2026-W01", "2026-09-09", "SEA", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == \
        ["2026-09-09"]


def test_the_week_label_alone_never_lands_in_a_calendar_window():
    """Why it needs the kickoff date rather than a cleverer comparison: the
    label carries no day at all, and text-sorting it puts it after every
    date the window could name."""
    assert not ("2026-09-08" <= "2026-W01" <= "2026-09-10"), \
        "a week label compares as a date — the premise of this fix is gone"


def test_a_football_only_night_is_not_an_empty_pass():
    """`settle_open` returns before it grades anything when this list is
    empty, so an empty list on a football night is the outage."""
    conn = _journal(("nfl", "2026-W01", "2026-09-09", "SEA", "open"),
                    ("nfl", "2026-W01", "2026-09-09", "NE@SEA", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS), \
        "the only open picks are football and the pass would do nothing"


def test_the_league_gate_answers_yes_for_that_same_night():
    """`_has_open` matched the raw column too, so the day list could name a
    day and the league still deny having a pick on it."""
    conn = _journal(("nfl", "2026-W01", "2026-09-09", "SEA", "open"))
    days = M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS)
    assert M._has_open(conn, "nfl", days) is True


def test_the_league_gate_is_still_scoped_to_one_league():
    """It is what stops a quiet night paying for every league's feed."""
    conn = _journal(("nfl", "2026-W01", "2026-09-09", "SEA", "open"))
    assert M._has_open(conn, "mlb", ["2026-09-09"]) is False


def test_a_settled_pick_does_not_hold_the_window_open():
    conn = _journal(("nfl", "2026-W01", "2026-09-09", "SEA", "win"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == []
    assert M._has_open(conn, "nfl", ["2026-09-09"]) is False


# --- the daily sports, unchanged --------------------------------------------
def test_a_baseball_bet_behaves_exactly_as_it_did():
    """MLB journals an ISO day as its label, so the expression falls back to
    it and the window is the window it always was."""
    conn = _journal(("mlb", "2026-09-09", "", "NYY", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == \
        ["2026-09-09"]
    assert M._has_open(conn, "mlb", ["2026-09-09"]) is True


def test_the_lookback_still_bounds_the_pass():
    """Anything older is the daily job's problem — that is the only reason
    this window exists, and widening it here would put months of history
    under a query that runs every five minutes."""
    old = (TODAY - _dt.timedelta(days=M.SETTLE_LOOKBACK_DAYS)).isoformat()
    conn = _journal(("nfl", "2026-W01", old, "SEA", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == []


def test_days_come_back_oldest_first():
    """`ingest_for_open_bets` hands `days[0]` and `days[-1]` to the MLB
    ranged results pull as (start, end); reversed, it fetches nothing."""
    conn = _journal(("mlb", "2026-09-10", "", "NYY", "open"),
                    ("mlb", "2026-09-08", "", "BOS", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == \
        ["2026-09-08", "2026-09-10"]


# --- the deliberate limit ---------------------------------------------------
def test_a_row_journalled_before_game_day_existed_stays_out():
    """It carries no kickoff date, so there is nothing to window on.
    Inventing a day for it would put a wrong number in the record, which is
    worse than an open bet; `--backfill-days` is what moves these."""
    conn = _journal(("nfl", "2026-W01", None, "SEA", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == []


def test_an_empty_string_game_day_is_treated_as_absent_not_as_a_day():
    """The journal writes "" when `game_day_for` cannot find a real day, so
    NULLIF is load-bearing: without it every such row windows as the empty
    string and sorts before every date."""
    conn = _journal(("nfl", "2026-W01", "", "SEA", "open"))
    assert M._open_bet_days(conn, TODAY, M.SETTLE_LOOKBACK_DAYS) == []


# --- one expression, both readers -------------------------------------------
def test_both_readers_use_the_shared_day_expression():
    """They must agree, or a day is open for the window and closed for the
    league gate. `day_expr`'s own docstring is written about that."""
    for name in ("def _open_bet_days(", "def _has_open("):
        i = SRC.index(name)
        block = SRC[i:SRC.index("\ndef ", i + 1)]
        assert "day_expr()" in block, f"{name} windows on the raw column"


def test_neither_reader_windows_on_the_raw_date_column():
    """The mutant this file exists to kill: `date >= ?` is what shipped, and
    it reads as perfectly ordinary SQL."""
    for name in ("def _open_bet_days(", "def _has_open("):
        i = SRC.index(name)
        block = SRC[i:SRC.index("\ndef ", i + 1)]
        sql = block[block.index("lconn.execute("):]
        assert "date >= ?" not in sql and "date <= ?" not in sql, \
            f"{name} compares the slate label against a calendar date"
        assert "AND date IN (" not in sql, \
            f"{name} matches the slate label against calendar days"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
