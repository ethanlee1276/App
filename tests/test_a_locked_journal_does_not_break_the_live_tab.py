"""A busy journal does not put an error box on the Live tab.

Ethan's Live tab, 2026-10-04: "Open-bet tracker hit an error this build:
database is locked". The tracker only reads, but it opened the journal
with `ledger.connect`, which takes schema write locks on its first call in
a process. It now reads through `ledger.read_only`, and a lock that still
lands gets one more try. Checks: the tracker opens the journal read-only;
a lock that clears on the second try leaves no error; a lock that stays
is still written onto the board (a dead tracker must never read as "no
bets"); a different database error is not retried.

Run directly: `python3 tests/test_a_locked_journal_does_not_break_the_live_tab.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import livepicks as L                                   # noqa: E402

L.TRACKER_LOCK_WAIT_S = 0.0


def _with_once(behaviour):
    calls = []
    real = L._attach_tracker_once

    def fake(result, *a, **k):
        calls.append(1)
        out = behaviour(len(calls))
        if isinstance(out, Exception):
            raise out
        result.pop("live_picks_error", None)
        result["live_picks"] = []
        return ""
    L._attach_tracker_once = fake
    return calls, lambda: setattr(L, "_attach_tracker_once", real)


def test_the_tracker_reads_the_journal_read_only():
    src = (ROOT / "engine" / "livepicks.py").read_text()
    i = src.index("def _attach_tracker_once(")
    j = src.find("\ndef ", i + 10)
    body = src[i:j if j > 0 else len(src)]
    assert "_ledger.read_only()" in body and "_ledger.connect()" not in body
    assert "_lp_ledger.read_only()" in (ROOT / "mlb_build.py").read_text()


def test_a_lock_that_clears_leaves_no_error():
    calls, undo = _with_once(lambda n: sqlite3.OperationalError("database is locked") if n == 1 else None)
    try:
        res = {"live_picks_error": "old"}
        L.attach_tracker(res, "nfl")
        assert len(calls) == 2 and "live_picks_error" not in res and res["live_picks"] == []
    finally:
        undo()


def test_a_lock_that_stays_is_still_written_onto_the_board():
    calls, undo = _with_once(lambda n: sqlite3.OperationalError("database is locked"))
    try:
        res = {}
        line = L.attach_tracker(res, "nfl")
        assert len(calls) == 1 + L.TRACKER_LOCK_RETRIES
        assert res["live_picks_error"] == "database is locked" and "tracker error" in line
    finally:
        undo()


def test_another_database_error_is_not_retried():
    calls, undo = _with_once(lambda n: sqlite3.OperationalError("no such table: bets"))
    try:
        res = {}
        L.attach_tracker(res, "nfl")
        assert len(calls) == 1 and "no such table" in res["live_picks_error"]
    finally:
        undo()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
