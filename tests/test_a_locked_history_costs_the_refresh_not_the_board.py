"""A locked history file costs a write a wait, then a retry — never the board.

3 November, from 07:56: the college board failed every build on
"sqlite3.OperationalError: database is locked", 46 seconds in (thirty of
them SQLite's busy timeout), and its note — which names the frame since
that morning — said where: engine/db.py in `_chunked`, the bulk upsert.
Other writers on the same file (the daily chores, the settle pass) write in
5,000-row slices, which was meant to let a waiting writer in between them;
it did not, because the writer that just committed takes the lock straight
back within microseconds while the waiter's busy handler sleeps up to 100
ms between tries. What these hold:

  * `_chunked` pauses between slices (not after the last), long enough for
    one busy-handler sleep to land in the gap;
  * a slice that cannot take the lock in SQLite's own timeout is tried
    again, twice, before the error reaches the caller; any other error —
    "database table is locked" too — goes up at once;
  * before it is tried again its transaction is ended, because SQLite
    fails a write at once, without waiting, from a transaction that has
    already read the file — but a caller's open transaction is ended only
    where that cannot cost it a write (WAL mode, how the box opens it);
  * against a real file, a writer holding the lock a little longer than one
    timeout, or a stale read left open, no longer fails the waiting write;
  * the college build's results refresh — idempotent upserts of results
    already stored — names a lock, ends its transaction and builds on,
    instead of exiting; any other database error still stops it.

Run directly: `python3 tests/test_a_locked_history_costs_the_refresh_not_the_board.py`
"""
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db                                            # noqa: E402

LOCKED = "database is locked"


class _Conn:
    """executemany fails with each of ``errors`` in turn, then succeeds; it
    opens a transaction the way Python's sqlite3 does, before the write."""
    def __init__(self, errors=(), mode="wal", in_tx=False):
        self.errors, self.calls, self.commits, self.rollbacks = list(errors), [], 0, 0
        self.mode, self.in_transaction = mode, in_tx

    def executemany(self, sql, chunk):
        self.calls.append(len(chunk))
        self.in_transaction = True
        if self.errors:
            raise self.errors.pop(0)

    def execute(self, sql):
        assert sql == "PRAGMA journal_mode", sql
        mode = self.mode
        return type("Cur", (), {"fetchone": lambda self: (mode,)})()

    def commit(self):
        self.commits += 1
        self.in_transaction = False

    def rollback(self):
        self.rollbacks += 1
        self.in_transaction = False


def _idle(_s):
    pass


def test_it_pauses_between_slices_and_not_after_the_last():
    slept = []
    rows = [{}] * (db.WRITE_CHUNK * 3 + 1)
    conn = _Conn()
    assert db._chunked(conn, "x", rows, sleep=slept.append) == len(rows)
    assert conn.calls == [db.WRITE_CHUNK] * 3 + [1] and conn.commits == 4
    assert slept == [db.WRITE_YIELD_S] * 3, slept
    one = []
    db._chunked(_Conn(), "x", [{}] * 10, sleep=one.append)
    assert one == [], "a write of one slice never waits"
    assert 0.1 <= db.WRITE_YIELD_S <= 0.5


def test_a_locked_slice_is_tried_again_and_anything_else_goes_up_at_once():
    conn = _Conn([sqlite3.OperationalError(LOCKED)])
    assert db._chunked(conn, "x", [{}] * 3, sleep=_idle) == 3
    assert conn.calls == [3, 3] and conn.commits == 1, "tried twice, committed once"
    assert conn.rollbacks == 1, "its own transaction ended before it was tried again"
    conn = _Conn([sqlite3.OperationalError(LOCKED)] * (db.WRITE_RETRIES + 1))
    try:
        db._chunked(conn, "x", [{}] * 3, sleep=_idle)
        raise AssertionError("a lock that never lifts must reach the caller")
    except sqlite3.OperationalError as exc:
        assert str(exc) == LOCKED and len(conn.calls) == db.WRITE_RETRIES + 1
    for other in ("no such table: games", "database table is locked", "disk I/O error"):
        conn = _Conn([sqlite3.OperationalError(other)])
        try:
            db._chunked(conn, "x", [{}] * 3, sleep=_idle)
            raise AssertionError(f"{other!r} is not a lock to wait out")
        except sqlite3.OperationalError:
            assert len(conn.calls) == 1 and conn.rollbacks == 0, other


def test_a_callers_open_transaction_is_ended_only_where_that_costs_it_nothing():
    # In WAL mode a write that could not take the lock holds no writes, so
    # ending the caller's transaction loses nothing and buys the retry a wait.
    conn = _Conn([sqlite3.OperationalError(LOCKED)], mode="wal", in_tx=True)
    db._chunked(conn, "x", [{}] * 3, sleep=_idle)
    assert conn.rollbacks == 1 and conn.commits == 1
    # In any other mode it might hold the caller's writes: left alone.
    conn = _Conn([sqlite3.OperationalError(LOCKED)], mode="delete", in_tx=True)
    db._chunked(conn, "x", [{}] * 3, sleep=_idle)
    assert conn.rollbacks == 0 and conn.calls == [3, 3] and conn.commits == 1


def _file():
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    db.connect(path).close()
    return path


def _game(gid):
    return {"sport": "cfb", "season": 2026, "period": "1", "game_id": gid, "home": "OHIO", "away": "BGSU"}


def test_against_a_real_file_a_held_lock_no_longer_fails_the_waiting_write():
    path = _file()
    holder = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO games (sport, season, period, game_id) VALUES ('cfb', 2026, '1', 'h')")
    waiter = db.connect(path)
    waiter.execute("PRAGMA busy_timeout=200")          # the box's 30 s, scaled down
    t = threading.Timer(0.3, lambda: holder.execute("COMMIT"))
    t.start()
    t0 = time.time()
    try:
        n = db.upsert_games(waiter, [_game("w")])
    finally:
        t.join()
    assert n == 1 and time.time() - t0 >= 0.25, "it waited out the holder, then wrote"
    got = waiter.execute("SELECT game_id FROM games WHERE sport='cfb' ORDER BY game_id").fetchall()
    assert [r[0] for r in got] == ["h", "w"]
    holder.close()
    waiter.close()


def test_against_a_real_file_a_stale_read_no_longer_fails_the_write_at_once():
    path = _file()
    a, b = db.connect(path), db.connect(path)
    # What a caught failed write leaves behind: its transaction still open,
    # and a read inside it pins the file as it was...
    a.execute("BEGIN")
    a.execute("SELECT count(*) FROM games").fetchone()
    # ...then another writer moves the file on. SQLite refuses a's write at
    # once (SQLITE_BUSY_SNAPSHOT, "database is locked"), with no wait at all.
    b.execute("INSERT INTO games (sport, season, period, game_id) VALUES ('cfb', 2026, '1', 'b')")
    b.commit()
    assert db.upsert_games(a, [_game("a")]) == 1
    got = b.execute("SELECT game_id FROM games WHERE sport='cfb' ORDER BY game_id").fetchall()
    assert [r[0] for r in got] == ["a", "b"]
    a.close()
    b.close()


def test_the_college_build_names_a_locked_refresh_and_builds_on():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    i = src.index("A LOCKED HISTORY TABLE COSTS THE REFRESH, NOT THE BOARD")
    block = src[i:src.index("builds on the history already stored", i)]
    assert "ingest_results(conn, [g for g in history if g[\"completed\"]])" in block
    assert "except sqlite3.OperationalError as exc:" in block
    j = block.index("except sqlite3.OperationalError as exc:")
    tail = block[j:]
    assert 'if not str(exc).startswith("database is locked"):\n            raise' in tail, \
        "only a lock is excused; any other database error still stops the build"
    assert tail.index("raise") < tail.index("conn.rollback()") < tail.index("CFB results not stored this build")
    assert "\nimport sqlite3\n" in src


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
