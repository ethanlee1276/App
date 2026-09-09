"""The calendar day, kept apart from the settle key.

`bets.date` is a JOIN KEY, not a date. Every daily sport files its
results under the calendar day, so for them the two are the same string.
The NFL does not: nflverse files results under season + week, the board
journals "2026-W01", and `_hist_where` resolves that onto period "001".
ledger.py says twice what happens if you "fix" that by writing an ISO
day instead — "a TD bet dated with the game's ISO Sunday would query a
period nothing is filed under and sit open forever".

So the key stays and the calendar gets a column. Before it existed,
everything that asked a DATE question was reading a join key:

  * the profit calendar collapsed every Week 1 bet into ONE bucket;
  * "W" sorts above every digit, so that bucket landed at the far right
    of the equity curve regardless of when the games were played;
  * `date >= '2026-08-01'` is TRUE of every week label ever written, so
    a one-month window silently contained every NFL bet in the journal.

Found 2026-09-08 asking whether the site was ready for the Wednesday
opener. It was the only thing on the readiness list that was broken
rather than merely unmeasured.
"""

import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger                                    # noqa: E402


def _db():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))
    return conn


def _settled(conn, sport, date, player, pnl, game_day=None, market="moneyline"):
    conn.execute(
        "INSERT INTO bets (sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, pnl_units, pnl_dollars, "
        "category) VALUES (?,?,?,?,?,'OVER',0.5,-110,1.0,10.0,?,?,?, 'main')",
        (sport, date, game_day, player, market,
         "won" if pnl > 0 else "lost", pnl, pnl * 10))
    conn.commit()


# ------------------------------------------------------ the column exists

def test_the_column_survives_a_database_that_predates_it():
    """Ethan's ledger is 2.2 MB of real history. The migration has to add
    the column to it in place, not on a rebuild nobody will run."""
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    old = sqlite3.connect(path)
    old.executescript(ledger._BETS_TABLE)          # the table as it was
    old.execute("INSERT INTO bets (sport, date, player) "
                "VALUES ('nfl','2026-W01','Puka Nacua')")
    old.commit()
    old.execute("ALTER TABLE bets DROP COLUMN game_day")
    old.commit()
    old.close()
    conn = ledger.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)")]
    assert "game_day" in cols, cols
    # and the row that predates it is still there, carrying NULL
    row = conn.execute("SELECT date, game_day FROM bets").fetchone()
    assert row["date"] == "2026-W01"
    assert row["game_day"] is None


# ------------------------------------------------------ what counts as a day

def test_a_week_label_is_never_mistaken_for_a_day():
    """`date.fromisoformat("2026-W01")` returns 2025-12-29 on 3.11+ — a
    real date, in the wrong year, with no error. A parse-only guard here
    would have made the calendar confidently wrong instead of empty."""
    assert ledger.game_day_for({"date": "2026-W01"}) == ""
    assert ledger.game_day_for({}, "2026-W01") == ""


def test_the_games_own_date_beats_the_slates():
    assert ledger.game_day_for({"game_date": "2026-09-13"},
                               "2026-W01") == "2026-09-13"


def test_a_daily_sport_falls_through_to_the_slate():
    assert ledger.game_day_for({}, "2026-07-04") == "2026-07-04"


def test_a_utc_kickoff_instant_is_not_treated_as_a_day():
    """Every odds row carries `commence_time`, and a Sunday-night kickoff
    is 00:20Z on MONDAY. Slicing ten characters off it files half the NFL
    week a day late — the same UTC drift that cost thirty home-run bets
    their settle in July."""
    assert ledger.game_day_for({"commence_time": "2026-09-14T00:20:00Z"},
                               "2026-W01") == ""


# --------------------------------------------------- the calendar and curve

def test_a_weeks_bets_land_on_the_days_they_were_played():
    """The whole point. Two NFL bets in one week label, played Thursday
    and Sunday, are two days on the calendar."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-10")
    _settled(conn, "nfl", "2026-W01", "PHI", -1.0, game_day="2026-09-13")
    days = [r["date"] for r in ledger.pnl_curve(conn)]
    assert days == ["2026-09-10", "2026-09-13"], days


def test_a_week_label_no_longer_sorts_to_the_end_of_the_curve():
    """"W" outranks every digit, so an NFL week used to land after every
    ISO day in its own year — the equity curve drew September's football
    to the right of October's baseball."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-13")
    _settled(conn, "mlb", "2026-10-02", "NYY", 1.0, game_day="2026-10-02")
    days = [r["date"] for r in ledger.pnl_curve(conn)]
    assert days == ["2026-09-13", "2026-10-02"], days


def test_a_date_window_no_longer_admits_every_week_label():
    """`'2026-W01' >= '2026-10-01'` is TRUE in SQLite, so a one-month
    window contained every NFL bet ever journalled — the count under the
    chart disagreed with the chart and nothing said why."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-13")
    _settled(conn, "mlb", "2026-10-02", "NYY", 1.0, game_day="2026-10-02")
    rows = ledger.pnl_curve(conn, since="2026-10-01")
    assert [r["date"] for r in rows] == ["2026-10-02"], rows


def test_a_row_with_no_day_still_appears_rather_than_vanishing():
    """Every row journalled before this column exists carries NULL. It
    keeps its old, wrong bucket — which is not good, and is not made
    worse by this change. Dropping it from the record to tidy the
    calendar would be losing real money from the ledger to fix a
    display."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day=None)
    rows = ledger.pnl_curve(conn)
    assert [r["date"] for r in rows] == ["2026-W01"], rows
    assert rows[0]["day_u"] == 0.9


def test_a_daily_sport_reads_exactly_as_it_did_before():
    """The negative control. MLB's date IS its day, and this change must
    be invisible there."""
    conn = _db()
    _settled(conn, "mlb", "2026-07-04", "NYY", 1.0, game_day="2026-07-04")
    _settled(conn, "mlb", "2026-07-05", "BOS", -1.0, game_day="2026-07-05")
    rows = ledger.pnl_curve(conn)
    assert [r["date"] for r in rows] == ["2026-07-04", "2026-07-05"]
    assert [r["day_u"] for r in rows] == [1.0, -1.0]


# ------------------------------------------------- the settle key is intact

def test_the_settle_key_is_untouched():
    """The reason `date` cannot simply be corrected: NFL results are
    filed under season + period, and `_hist_where` resolves the week
    label onto them. A bet whose `date` became an ISO Sunday would query
    a period nothing is filed under and sit open forever."""
    where, args = ledger._hist_where(
        {"sport": "nfl", "date": "2026-W01"})
    assert "season=?" in where and "period=?" in where
    assert args == ["nfl", 2026, "001"]


def test_the_journal_writes_both_and_they_disagree_only_for_football():
    """One row through the real writer, so the column list and the value
    tuple cannot drift apart — the failure mode of adding a column to a
    positional INSERT."""
    conn = _db()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": "2026-W01",
        "recommendations": [{
            "player": "Puka Nacua", "market": "receptions", "side": "OVER",
            "line": 4.5, "odds": -115, "hit_prob": 0.62, "edge": 0.04,
            "confidence": 7.5, "grade": "Play", "stake_units": 0.3,
            "recommended": True, "has_market": True,
            "game_date": "2026-09-13", "book": "FanDuel"}]})
    row = conn.execute("SELECT date, game_day FROM bets").fetchone()
    assert row["date"] == "2026-W01", dict(row)
    assert row["game_day"] == "2026-09-13", dict(row)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
