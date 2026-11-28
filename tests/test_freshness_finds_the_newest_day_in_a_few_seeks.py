"""The freshness check finds the newest day of player stats in a few seeks (step AEQ, 24 November 2026).

Every daily league's board says how current its stats are (engine/freshness.daily: the newest day with a player's
row on or before today). As one MAX over the sport's rows, SQLite (no statistics on the box's file) walked every
entry of the (sport, player, season, period) index: the "freshness" part of college basketball's build ran 20 to 26
seconds on game nights that evening. `latest_log_day` asks the newest two seasons on the table's own key, one seek
each, with the rows filed under no season beside them, and answers what the one read did.

Offline. Run directly: `python3 tests/test_freshness_finds_the_newest_day_in_a_few_seeks.py`
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, freshness as F                               # noqa: E402


def _rows(conn, days):
    db.upsert_player_logs(conn, [{"sport": "cbb", "season": s, "period": d, "game_id": f"g{d}", "player": "A B",
                                  "team": "T", "opponent": "U", "position": "G", "home": 1, "market": "pts",
                                  "value": 1.0} for s, d in days])
    conn.commit()


def _old(conn, day):
    return conn.execute(F._LOGS, ("cbb", day)).fetchone()[0]


def test_it_answers_what_the_one_read_did():
    d = tempfile.mkdtemp()
    try:
        conn = db.connect(os.path.join(d, "h.db"))
        assert F.latest_log_day(conn, "cbb", "2026-11-24") is None and _old(conn, "2026-11-24") is None
        _rows(conn, [(2024, "2025-03-01"), (2025, "2025-11-10"), (2025, "2026-03-20"), (2026, "2026-11-20"),
                     (2026, "2026-11-23")])
        for day in ("2026-11-24", "2026-11-21", "2026-11-19", "2026-04-01", "2025-11-01", "2025-01-01"):
            assert F.latest_log_day(conn, "cbb", day) == _old(conn, day), day
        _rows(conn, [(2026, "2026-11-30")])                      # a row dated after the day asked
        assert F.latest_log_day(conn, "cbb", "2026-11-24") == "2026-11-23" == _old(conn, "2026-11-24")
        _rows(conn, [(None, "2026-11-24")])                      # a row filed under no season
        assert F.latest_log_day(conn, "cbb", "2026-11-24") == "2026-11-24" == _old(conn, "2026-11-24")
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_each_read_is_a_seek_on_the_tables_own_key():
    d = tempfile.mkdtemp()
    try:
        conn = db.connect(os.path.join(d, "h.db"))
        seen = []
        conn.set_trace_callback(seen.append)
        _rows(conn, [(2025, "2025-11-10"), (2026, "2026-11-20")])
        seen.clear()
        F.latest_log_day(conn, "cbb", "2026-11-24")
        conn.set_trace_callback(None)
        reads = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
        assert reads, seen
        for q in reads:
            plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + q).fetchall())
            assert "COVERING INDEX sqlite_autoindex_player_game_logs_1" in plan and "idx_logs_player" not in plan, \
                (q, plan)
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_daily_check_uses_it():
    d = tempfile.mkdtemp()
    try:
        conn = db.connect(os.path.join(d, "h.db"))
        _rows(conn, [(2026, "2026-11-20")])
        import datetime as dt
        rep = F.daily(conn, "cbb", dt.date(2026, 11, 24))
        assert rep["tables"]["player stats"] == "2026-11-20", rep
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
