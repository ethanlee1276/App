"""The write-ahead log grew all day and the builds died behind it.

Ethan's droplet, 2026-09-16. `history.db-wal` was truncated to zero and
was back to 230 MB twelve minutes later — nineteen megabytes a minute,
sustained — with six "database is locked" failures in the same window.
The night before it had reached 355 MB and cfb_build, pm_build, the MLB
results ingest and the NFL box scores were all failing every cycle.

WHY IT GROWS WITHOUT BOUND, which is not what most people expect of WAL
and is the whole of this file. SQLite's automatic checkpoint is PASSIVE:
it copies pages out of the log into the database, but it cannot rewind
the log to the start while any reader still holds an older snapshot.
This box serves a web server that keeps read connections open. So pages
are copied out, the file never rewinds, and it grows all day — and every
later checkpoint has more file to walk, holding locks longer, while
writers queue behind a thirty-second timeout.

Only a TRUNCATE (or RESTART) checkpoint waits for readers and rewinds.
`launch._checkpoint_wal` runs one at the end of every cycle, which is
the one moment when every build has finished writing.

Run directly: `python3 tests/test_wal_checkpoint.py`
"""

import contextlib
import io
import os
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch                                                 # noqa: E402
from engine import db, ledger                                 # noqa: E402


def _wal_db(rows=40000):
    """A WAL-mode database with an un-rewound log, in a temp directory.
    The suite must not touch the box it runs on.

    THE CONNECTION COMES BACK AND THE CALLER MUST HOLD IT. Closing the
    LAST connection to a WAL database checkpoints and deletes the `-wal`
    all by itself, so a fixture that tidied up after itself handed every
    test below a log that was already zero — and "it rewinds the log"
    then passed over nothing at all. Found by the ordering test failing
    beside it. An idle open connection does not block a TRUNCATE
    checkpoint; a reader mid-transaction does, which is its own test.
    """
    path = os.path.join(tempfile.mkdtemp(), "x.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")     # the state we are in
    conn.execute("CREATE TABLE t (x INTEGER, pad TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)",
                     [(i, "x" * 200) for i in range(rows)])
    conn.commit()
    return path, conn


def _sizes(*paths):
    out = []
    for p in paths:
        w = pathlib.Path(f"{p}-wal")
        out.append(w.stat().st_size if w.exists() else 0)
    return out


@contextlib.contextmanager
def _pointed_at(history, journal):
    """`_checkpoint_wal` reads the two module defaults. Repointed around
    the call and restored after, so nothing leaks into another test."""
    h, j = db.DEFAULT_DB, ledger.DEFAULT_DB
    db.DEFAULT_DB, ledger.DEFAULT_DB = pathlib.Path(history), pathlib.Path(journal)
    try:
        yield
    finally:
        db.DEFAULT_DB, ledger.DEFAULT_DB = h, j


def _run(history, journal):
    buf = io.StringIO()
    with _pointed_at(history, journal), contextlib.redirect_stdout(buf):
        launch._checkpoint_wal()
    return buf.getvalue()


# ── it rewinds ──────────────────────────────────────────────────────

def test_the_log_is_rewound_to_nothing():
    """The behaviour the whole thing exists for."""
    h, hc = _wal_db()
    j, jc = _wal_db()
    try:
        before = _sizes(h, j)
        assert min(before) > 0, "the fixture did not leave a log to rewind"
        _run(h, j)
        assert _sizes(h, j) == [0, 0], _sizes(h, j)
    finally:
        hc.close(); jc.close()


def test_both_databases_are_done_not_just_the_first():
    """The journal and the history are separate files and both grow. An
    early `return` on the first would leave half the problem in place."""
    h, hc = _wal_db()
    j, jc = _wal_db()
    try:
        assert _sizes(j)[0] > 0, "the fixture left nothing to rewind"
        _run(h, j)
        assert _sizes(j) == [0], "the journal's log was left alone"
    finally:
        hc.close(); jc.close()


# ── it stays quiet, except when it matters ──────────────────────────

def test_a_routine_rewind_says_nothing():
    """It runs every few minutes. A line each time is a line nobody
    reads, and this file already has the line-ledger note as the example
    of what that costs."""
    h, hc = _wal_db(rows=200)
    j, jc = _wal_db(rows=200)
    try:
        assert max(_sizes(h, j)) < launch.WAL_NOISY_BYTES, "fixture too big"
        assert _run(h, j).strip() == "", "a small rewind spoke"
    finally:
        hc.close(); jc.close()


def test_a_big_reclaim_is_worth_a_line():
    """Above the noise floor something wrote a lot, and a reader
    deserves to know it came back."""
    was = launch.WAL_NOISY_BYTES
    try:
        launch.WAL_NOISY_BYTES = 1024
        h, hc = _wal_db()
        j, jc = _wal_db()
        try:
            out = _run(h, j)
        finally:
            hc.close(); jc.close()
    finally:
        launch.WAL_NOISY_BYTES = was
    assert "rewound" in out, out
    assert "history" in out and "journal" in out, out


def test_a_reader_holding_the_log_is_reported_not_swallowed():
    """THE FINDING, NOT A ROUTINE SKIP. If this can never get a clear
    moment then a long-lived reader is the problem and no amount of
    checkpointing here will fix it. Swallowing that into silence is the
    failure shape this repository keeps finding in itself."""
    was = launch.WAL_CHECKPOINT_TIMEOUT_MS
    try:
        launch.WAL_CHECKPOINT_TIMEOUT_MS = 50      # so the test is not 5s
        h, hc = _wal_db(rows=2000)
        j, jc = _wal_db(rows=200)
        jc.close()
        # A reader mid-transaction, exactly like the web server's.
        reader = sqlite3.connect(h)
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM t").fetchone()
        try:
            out = _run(h, j)
        finally:
            reader.close(); hc.close()
    finally:
        launch.WAL_CHECKPOINT_TIMEOUT_MS = was
    assert "could not be rewound" in out, out
    assert "history" in out, out


def test_a_busy_report_says_whether_it_is_growing_or_holding():
    """On 2026-09-16 this printed the same "610 MB" every cycle for ten
    minutes. The number alone cannot say whether that is a stable ceiling
    — which would be survivable — or a spiral, which is what it was. The
    second report onward carries the delta."""
    was_t, was_l = launch.WAL_CHECKPOINT_TIMEOUT_MS, dict(launch._WAL_LAST)
    try:
        launch.WAL_CHECKPOINT_TIMEOUT_MS = 50
        launch._WAL_LAST.clear()
        h, hc = _wal_db(rows=2000)
        j, jc = _wal_db(rows=200)
        jc.close()
        reader = sqlite3.connect(h)
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM t").fetchone()
        try:
            first = _run(h, j)
            # More written, still pinned: the log is now bigger.
            hc.executemany("INSERT INTO t VALUES (?, ?)",
                           [(i, "y" * 400) for i in range(4000)])
            hc.commit()
            second = _run(h, j)
        finally:
            reader.close(); hc.close()
    finally:
        launch.WAL_CHECKPOINT_TIMEOUT_MS = was_t
        launch._WAL_LAST.clear(); launch._WAL_LAST.update(was_l)
    assert "MB)" in first, f"the first report should carry no delta: {first}"
    assert "+" in second and "MB)" in second, second


def test_the_ceiling_on_what_a_reset_leaves_behind_is_set():
    """`journal_size_limit` is what SQLite offers for this: when the log
    IS reset — a restart, or a real gap — the file comes back to the
    limit rather than staying at its high-water mark. Not a fix for the
    growth, and the constant says so; a ceiling on the damage."""
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "limited.db")
    conn = db.connect(path)
    got = conn.execute("PRAGMA journal_size_limit").fetchone()[0]
    assert got == db.WAL_SIZE_LIMIT, (got, db.WAL_SIZE_LIMIT)
    assert 0 < db.WAL_SIZE_LIMIT < 610 * 1024 * 1024, \
        "the ceiling must be below what this box actually reached"


def test_it_never_raises_and_never_stops_the_cycle():
    """It runs one line before the heartbeat. A database that has gone
    missing must cost the rewind and nothing else."""
    gone = os.path.join(tempfile.mkdtemp(), "nope", "x.db")
    out = _run(gone, gone)
    assert isinstance(out, str)          # got here at all


# ── where it sits in the cycle ──────────────────────────────────────

def test_it_runs_after_the_builds_and_before_the_heartbeat():
    """Ordering is the whole design. After the builds, because that is
    the only moment nothing is writing and a truncating checkpoint can
    succeed; before the heartbeat, because proof of life has to be the
    last thing the cycle does — `tests/test_doctor.py` holds that end."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "launch.py"), encoding="utf-8").read()
    # THE CYCLE IS `_background_refresher`, the function that ends with
    # the heartbeat — `tests/test_doctor.py` reads the same one the same
    # way. `refresh_all` is a single pass and is not where the loop goes
    # idle, which is the moment this needs.
    fn = src[src.index("def _background_refresher("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "_checkpoint_wal()" in fn, "the cycle does not rewind at all"
    assert fn.index("_checkpoint_wal()") < fn.index("_write_heartbeat(interval"), \
        "the rewind was written after the heartbeat"


if __name__ == "__main__":
    fails = ran = 0
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            try:
                _f(); ran += 1; print(f"  ok  {_n}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {_n}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {_n}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
