"""The grade says which of its reads took the time
(engine/ledger.settle_from_history, take_grade_parts;
engine/maintenance.settle_open, phases["grade_parts"]).

The heartbeat's settle phases, Saturday 7 November: grading 366 seconds of
one pass, and the phase is a single call. Inside it are the reads that
could cost that much: the purchased closes (one read of odds_history per
sport and market graded), three streams of our own snapshot file (the
lines, the prices, the same book's close), the game lines' closes, the
no-show sweep and the loss tagging. What these hold:

  * a grading pass keeps, per thread, the seconds each of those took, how
    many bets were open, and the whole call; every named part fits inside
    the whole;
  * `take_grade_parts` hands them over once and forgets them, and another
    thread never sees this one's;
  * the settle pass puts them on its phases as ``grade_parts``.

Run directly: `python3 tests/test_the_grade_says_which_read_took_its_time.py`
"""
import datetime as dt
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                          # noqa: E402
from engine import maintenance as M                                # noqa: E402

KNOWN = {"open", "closes", "snapshot_lines", "snapshot_prices", "same_book",
         "game_close", "game_rows", "stat_rows", "absent", "too_early", "noshow",
         "causes", "total"}


def _journal_and_history():
    """One open total-bases over, its game final and its stat row stored."""
    from engine import db as hist_db
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, category) "
        "VALUES ('t','mlb','2026-09-05','Aaron Judge','total_bases','OVER',0.5,'BetMGM',"
        "100,0.1,1.0,'open','main')")
    conn.commit()
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-09-05", "game_id": "NYY@CHW-0905",
         "home": "CHW", "away": "NYY", "home_score": 2, "away_score": 5, "spread": 0.0,
         "total": 8.5, "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-09-05", "game_id": "NYY@CHW-0905",
         "player": "Aaron Judge", "team": "NYY", "opponent": "CHW", "position": "RF",
         "home": 0, "market": "total_bases", "value": 2.0}])
    return conn, hist


def test_a_grading_pass_says_where_its_time_went():
    conn, hist = _journal_and_history()
    ledger.take_grade_parts()
    assert ledger.settle_from_history(conn, hist) == 1
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "won"
    parts = ledger.take_grade_parts()
    assert set(parts) <= KNOWN, set(parts) - KNOWN
    for k in ("open", "stat_rows", "too_early", "closes", "same_book", "noshow", "causes",
              "total"):
        assert k in parts, (k, parts)
    assert parts["open"] == 1
    secs = {k: v for k, v in parts.items() if k != "open"}
    assert all(isinstance(v, float) and v >= 0.0 for v in secs.values()), secs
    # Each part is rounded to 0.1 s on its own, so the sum may pass the
    # whole by a rounding step per part.
    assert sum(v for k, v in secs.items() if k != "total") <= parts["total"] + 0.1 * len(secs)
    assert ledger.take_grade_parts() == {}, "handed over once"


def test_a_pass_with_nothing_open_still_says_so():
    from engine import db as hist_db
    conn = ledger.connect(":memory:")
    ledger.settle_from_history(conn, hist_db.connect(":memory:"))
    parts = ledger.take_grade_parts()
    assert parts["open"] == 0 and "total" in parts and "closes" not in parts


def test_another_thread_never_takes_this_ones_parts():
    conn, hist = _journal_and_history()
    ledger.settle_from_history(conn, hist)
    seen = []
    t = threading.Thread(target=lambda: seen.append(ledger.take_grade_parts()))
    t.start()
    t.join()
    assert seen == [{}]
    assert ledger.take_grade_parts().get("open") == 1


def test_the_settle_pass_puts_them_on_its_phases():
    from engine import db
    real = (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
            ledger.export_json)
    real_db, saved_ingest = db.connect, M.ingest_for_open_bets
    conn = ledger.connect(":memory:")
    conn.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                 "VALUES ('mlb', '2026-11-07', 'P', 'total_bases', 'open', 'main')")
    conn.commit()

    def grade(lconn, hconn, sport=None):
        ledger._GRADE_LOCAL.parts = {"open": 1, "closes": 12.34, "total": 40.06}
        return 0
    ledger.connect = lambda path=None: conn
    db.connect = lambda path=None: None
    ledger.settle_from_history = grade
    ledger.resettle_mismatches = lambda lconn, hconn, since=None: []
    ledger.export_json = lambda c, p: None
    M.ingest_for_open_bets = lambda l, h, days, log: {"games": 0}
    try:
        with tempfile.TemporaryDirectory() as td:
            M.settle_open(log=lambda *_: None, state_path=Path(td) / "m.json",
                          today=dt.date(2026, 11, 7), now=1000.0, force=True)
    finally:
        (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
         ledger.export_json) = real
        db.connect, M.ingest_for_open_bets = real_db, saved_ingest
    assert M.LAST_SETTLE_PHASES["grade_parts"] == {"open": 1, "closes": 12.3, "total": 40.1}
    assert ledger.take_grade_parts() == {}, "the pass took them"


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
