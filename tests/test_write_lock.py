"""A season-sized backfill must not lock the board builds out of the file.

Ethan on the droplet, 2026-09-03, running the college backfill the CFB
build's own diagnostic told him to run:

    python3 ingest.py cfb --seasons 2022-2026
      2022  player-log rows: 114,047
      2023  player-log rows: 115,230
      2024  games: 548 finished
    sqlite3.OperationalError: database is locked

Two seasons in, 229,277 rows written, and the third died. Nothing was
wrong with the data.

SQLite in WAL mode lets readers run during a write. It does NOT let two
writers overlap. `_upsert` sent every row of a season in a single
`executemany` — one transaction, holding the one write lock for as long
as the whole write took — while the refresh loop on the same one-core box
was building boards against the same file. Whichever asked second waited,
and `busy_timeout` is 30 seconds, and a season is longer than that.

The fix is not a longer timeout. A longer timeout makes the loser wait
longer; it does not stop one writer owning the file for minutes. Holding
the lock in slices does: `WRITE_CHUNK` rows, commit, release, repeat, so
the longest anyone waits is one slice rather than one season.

MEASURED on this container against a concurrent board writer, 115,000
rows — the real per-season size:

    one transaction   a board write waited up to 1333 ms
    chunked                                       432 ms

The trade is that a killed ingest leaves part of its rows written. Every
writer here is an upsert keyed on identity, so re-running is idempotent
and picks up where it stopped — against the alternative, which is losing
the season and being told about a lock instead of a fix.

Run directly: `python3 tests/test_write_lock.py`
"""

import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                        # noqa: E402


def _rows(n, sport="cfb"):
    return [{"sport": sport, "season": 2024, "period": "001",
             "game_id": f"g{i}", "player": f"P{i}", "team": "UGA",
             "opponent": "BAMA", "market": "rush_yds",
             "value": float(i), "home": 1} for i in range(1, n + 1)]


def _fresh():
    return db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


# --- the mechanism ----------------------------------------------------------
def test_a_bulk_write_is_not_one_transaction():
    """The whole defect in one assertion. A season in a single
    `executemany` owns the write lock until it finishes."""
    import inspect
    src = inspect.getsource(db._upsert)
    assert "_chunked(" in src, "the upsert writes every row in one go again"
    assert "executemany" not in src, \
        "the upsert calls executemany directly, bypassing the chunking"
    chunked = inspect.getsource(db._chunked)
    assert "range(0, len(params), WRITE_CHUNK)" in chunked
    assert "conn.commit()" in chunked, "the lock is never released mid-write"


def test_every_bulk_writer_goes_through_it():
    """Four call sites wrote in bulk and any one of them left un-chunked is
    the same outage under a different table name."""
    src = open(os.path.join(ROOT, "engine", "db.py"), encoding="utf-8").read()
    body = src[src.index("def _chunked("):]
    body = body[body.index("\n\n"):]          # everything after the helper
    assert "conn.executemany" not in body, \
        "a bulk writer still holds the lock for its whole write"


def test_the_chunk_is_a_size_a_slow_box_can_finish():
    assert 500 <= db.WRITE_CHUNK <= 20000, db.WRITE_CHUNK


# --- executed --------------------------------------------------------------
def test_every_row_still_lands():
    """Chunking must not lose or duplicate a row."""
    conn = _fresh()
    n = db.WRITE_CHUNK * 2 + 17               # deliberately not a whole number
    assert db.upsert_player_logs(conn, _rows(n)) == n
    got = conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]
    assert got == n, f"{got} rows landed of {n}"


def test_re_running_lands_in_the_same_place():
    """The trade this makes is a partial write on a kill, and it is only
    an acceptable trade because the writers are upserts. If a second run
    doubled the table, a killed backfill would need a manual repair."""
    conn = _fresh()
    rows = _rows(db.WRITE_CHUNK + 5)
    db.upsert_player_logs(conn, rows)
    db.upsert_player_logs(conn, rows)
    got = conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]
    assert got == len(rows), f"a re-run left {got} rows for {len(rows)} inputs"


def test_a_board_build_gets_the_file_during_a_backfill():
    """THE OUTAGE, reproduced: a season-sized write and a board build on
    one file at once. The board writes must get through.

    Sized to stay quick in the suite; the mechanism does not depend on the
    row count, only on whether the lock is ever released."""
    conn = _fresh()
    path = conn.execute("PRAGMA database_list").fetchone()[2]

    ok, blocked, waits = [], [], []
    stop = threading.Event()

    def board():
        c2 = db.connect(path)
        while not stop.is_set():
            t0 = time.time()
            try:
                db.upsert_games(c2, [{"sport": "nfl", "season": 2026,
                                      "period": "001", "game_id": "x",
                                      "home": "BUF", "away": "HOU"}])
                ok.append(1)
                waits.append(time.time() - t0)
            except Exception as exc:                         # noqa: BLE001
                blocked.append(str(exc))
            time.sleep(0.005)
        c2.close()

    t = threading.Thread(target=board)
    t.start()
    try:
        db.upsert_player_logs(conn, _rows(db.WRITE_CHUNK * 6))
    finally:
        stop.set()
        t.join()

    assert not blocked, f"a board write was locked out: {blocked[:1]}"
    assert ok, "the board thread never got a write in at all"
    # Not a timing assertion — a generous ceiling that still catches a
    # regression to one-transaction, where the wait is the whole write.
    assert max(waits) < 5.0, f"a board write waited {max(waits):.1f}s"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
