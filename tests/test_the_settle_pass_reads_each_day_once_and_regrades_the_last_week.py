"""The settle pass reads each day's stat file once and regrades the last week
(engine/ledger.name_index, _name_rows, resettle_mismatches(since=);
engine/maintenance.settle_open, RESETTLE_RECENT_DAYS).

The heartbeat's settle phases, Saturday 7 November (engine/maintenance
.LAST_SETTLE_PHASES): grade 419 s and regrade 240 s of one pass, every five
minutes. Every open prop whose player has no row under his own name read the
whole day's file for its market and normalized every name in it (and the
neighbouring days', for the drift), once per prop, every pass; the regrade
audited every bet the journal ever graded. What these hold:

  * inside `name_index()` the name-shape fallback answers exactly as it does
    outside, and reads each (day, market) once however many props ask;
    outside it, nothing is kept;
  * `resettle_mismatches(since=)` audits only the bets whose day is on or
    after ``since``; without it, every bet, as the daily chores ask;
  * the settle pass asks the regrade about the last RESETTLE_RECENT_DAYS,
    and runs the grade and the regrade inside a name index.

Run directly: `python3 tests/test_the_settle_pass_reads_each_day_once_and_regrades_the_last_week.py`
"""
import datetime as dt
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                          # noqa: E402
from engine import maintenance as M                                # noqa: E402


class _Counting:
    """A history connection that counts the name-shape reads."""
    def __init__(self, conn):
        self.conn, self.reads = conn, 0

    def execute(self, sql, args=()):
        if "SELECT player, value, team, game_id FROM player_game_logs" in sql:
            self.reads += 1
        return self.conn.execute(sql, args)


def _hist(day="2026-11-07"):
    from engine import db as hist_db
    h = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(h, [
        {"sport": "cfb", "season": 2026, "period": day, "game_id": "g", "player": name,
         "team": "T", "opponent": "O", "position": "WR", "home": 1,
         "market": "rec_yds", "value": v}
        for name, v in (("José Núñez Jr.", 81.0), ("A.J. Brown", 12.0), ("Chris Olave", 40.0))])
    return h


def test_inside_a_name_index_each_day_is_read_once_and_answers_the_same():
    from engine.sources.oddsapi import normalize_name
    h = _Counting(_hist())
    where, wargs = "sport=? AND period=?", ["cfb", "2026-11-07"]
    asks = ["Jose Nunez", "A J Brown", "Nobody Here", "Chris Olave"]
    plain = [[dict(r) for r in ledger._name_rows(h, where, wargs, "rec_yds", normalize_name(n))]
             for n in asks]
    assert h.reads == 4, "outside an index, one read per ask, as before"
    h.reads = 0
    with ledger.name_index():
        kept = [[dict(r) for r in ledger._name_rows(h, where, wargs, "rec_yds", normalize_name(n))]
                for n in asks]
        assert h.reads == 1, h.reads
        # Another market or another day is its own read.
        ledger._name_rows(h, where, ["cfb", "2026-11-08"], "rec_yds", "x")
        ledger._name_rows(h, where, wargs, "receptions", "x")
        assert h.reads == 3
    assert kept == plain
    assert [len(r) for r in plain] == [1, 1, 0, 1]
    assert ledger._name_index_now() is None, "nothing is kept once the block ends"


def test_an_index_inside_an_index_keeps_the_outer_one():
    with ledger.name_index():
        outer = ledger._name_index_now()
        with ledger.name_index():
            assert ledger._name_index_now() is outer
        assert ledger._name_index_now() is outer
    assert ledger._name_index_now() is None


def test_an_index_is_its_threads_own_and_its_databases_own():
    import threading
    seen = []
    with ledger.name_index():
        t = threading.Thread(target=lambda: seen.append(ledger._name_index_now()))
        t.start()
        t.join()
        a, b = _Counting(_hist()), _Counting(_hist())
        where, wargs = "sport=? AND period=?", ["cfb", "2026-11-07"]
        ledger._name_rows(a, where, wargs, "rec_yds", "chris olave")
        ledger._name_rows(b, where, wargs, "rec_yds", "chris olave")
        assert (a.reads, b.reads) == (1, 1), "two databases, two reads"
    assert seen == [None], "another thread never sees this one's index"


def _journal_with_two_wrong_grades():
    """Two total-bases bets graded 'lost' off a partial 0, one old and one
    recent; the history file now says each got 2."""
    from engine import db as hist_db
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for day, who in (("2026-07-29", "Austin Wells"), ("2026-11-05", "Aaron Judge")):
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
            "stake_units, stake_dollars, status, actual, pnl_units, pnl_dollars, category) "
            "VALUES ('t','mlb',?,?,'total_bases','OVER',0.5,'BetMGM',100,0.1,1.0,'lost',0.0,"
            "-0.1,-1.0,'main')", (day, who))
    conn.commit()
    hist = hist_db.connect(":memory:")
    for day, who in (("2026-07-29", "Austin Wells"), ("2026-11-05", "Aaron Judge")):
        hist_db.upsert_games(hist, [
            {"sport": "mlb", "season": 2026, "period": day, "game_id": f"NYY@CHW-{day}",
             "home": "CHW", "away": "NYY", "home_score": 2, "away_score": 5, "spread": 0.0,
             "total": 8.5, "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
        hist_db.upsert_player_logs(hist, [
            {"sport": "mlb", "season": 2026, "period": day, "game_id": f"w-{day}",
             "player": who, "team": "NYY", "opponent": "CHW", "position": "RF", "home": 0,
             "market": "total_bases", "value": 2.0}])
    return conn, hist


def test_the_regrade_since_a_day_audits_only_the_bets_from_it():
    conn, hist = _journal_with_two_wrong_grades()
    fixed = ledger.resettle_mismatches(conn, hist, since="2026-11-01")
    assert [f["player"] for f in fixed] == ["Aaron Judge"]
    old = conn.execute("SELECT status FROM bets WHERE player='Austin Wells'").fetchone()
    assert old["status"] == "lost", "the daily chores' full audit is where the old one heals"
    fixed = ledger.resettle_mismatches(conn, hist)
    assert [f["player"] for f in fixed] == ["Austin Wells"]
    assert ledger.resettle_mismatches(conn, hist) == []


def test_the_settle_pass_regrades_the_last_week_inside_a_name_index():
    seen = {}
    real = (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
            ledger.export_json)
    from engine import db
    real_db = db.connect
    conn = ledger.connect(":memory:")
    conn.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                 "VALUES ('mlb', '2026-11-07', 'P', 'total_bases', 'open', 'main')")
    conn.commit()

    def grade(lconn, hconn, sport=None):
        seen["grade_index"] = ledger._name_index_now() is not None
        return 0

    def regrade(lconn, hconn, since=None):
        seen["since"] = since
        seen["regrade_index"] = ledger._name_index_now() is not None
        return []
    ledger.connect = lambda path=None: conn
    db.connect = lambda path=None: None
    ledger.settle_from_history = grade
    ledger.resettle_mismatches = regrade
    ledger.export_json = lambda c, p: None
    saved_ingest = M.ingest_for_open_bets
    M.ingest_for_open_bets = lambda l, h, days, log: {"games": 0}
    try:
        with tempfile.TemporaryDirectory() as td:
            M.settle_open(log=lambda *_: None, state_path=Path(td) / "m.json",
                          today=dt.date(2026, 11, 7), now=1000.0, force=True)
    finally:
        (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
         ledger.export_json) = real
        db.connect = real_db
        M.ingest_for_open_bets = saved_ingest
    assert seen == {"grade_index": True, "regrade_index": True,
                    "since": (dt.date(2026, 11, 7)
                              - dt.timedelta(days=M.RESETTLE_RECENT_DAYS - 1)).isoformat()}, seen
    assert 3 <= M.RESETTLE_RECENT_DAYS <= 14
    assert ledger._name_index_now() is None


def test_the_daily_chores_still_audit_the_whole_journal():
    import inspect
    src = inspect.getsource(M._run_chores)
    assert "ledger.resettle_mismatches(lconn, hconn)" in src, "no since: the full audit, once a day"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
