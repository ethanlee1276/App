"""A failure that reads as an ordinary empty result.

This repository keeps finding the same bug wearing different clothes.
The rankings section returned "" for a month. `lineledger.record`
returned 0 both when it threw and when there was nothing to write, and
two builds wrapped it in `except Exception: pass`. The Live tab could
not tell "nothing on" from "the feed failed". On 2026-09-15 the day's
top-pick writer raised NameError on every cycle for three commits and
printed a warning nobody read.

WHAT THEY SHARE is not the exception. It is that the VALUE RETURNED ON
FAILURE is a value the caller sees on ordinary quiet days: `{}`, `0`,
`""`, `(0, 0)`. So the broken state and the calm state are the same
state, and nothing downstream can tell them apart — least of all a
person glancing at a page.

THE FIX IS NEVER TO STOP SWALLOWING. Settling must not break because
CLV bookkeeping did; a board must not go dark because its telemetry
could not write. The fix is that the swallow SAYS SO, which costs one
line and turns an invisible outage into a visible one.

This file holds the two that a sweep of `engine/` on 2026-09-15 found
still silent. The sweep itself: every function whose whole body sits
under a bare `except Exception`, cross-referenced against whether any
test calls it.

Run directly: `python3 tests/test_silent_failures.py`
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import coverage, db, ledger, linemoves            # noqa: E402


def _blow_up(*_a, **_k):
    raise RuntimeError("the source is gone")


def _say(fn):
    """Run `fn` with stdout captured. Returns (value, printed)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        value = fn()
    return value, buf.getvalue()


# ── CLV, the metric the Pick of the Day is judged on ────────────────

def test_a_dead_clv_source_says_so_instead_of_reading_as_no_data():
    """`_snapshot_closes` returns {} on failure, which is exactly what it
    returns before any snapshot has accrued. CLV is the verdict metric
    for the Pick of the Day (docs/PICK_OF_THE_DAY.md §7), so its source
    going dark is the last thing that should be inferred from silence."""
    orig = linemoves.stream_history
    linemoves.stream_history = _blow_up
    try:
        value, said = _say(ledger._snapshot_closes)
    finally:
        linemoves.stream_history = orig
    assert value == {}, "it must still return empty — settling cannot break"
    assert said.strip(), "the failure was silent"
    assert "RuntimeError" in said, said
    assert "CLV" in said, said


def test_the_clv_source_says_nothing_when_it_works():
    """A warning printed on the happy path is a warning people learn to
    scroll past, which is how the next real one gets missed."""
    orig = linemoves.stream_history
    linemoves.stream_history = lambda *a, **k: iter(())
    try:
        _value, said = _say(ledger._snapshot_closes)
    finally:
        linemoves.stream_history = orig
    assert not said.strip(), f"it complained on a clean run: {said!r}"


def test_settling_still_survives_a_dead_clv_source():
    """THE TRADE-OFF THIS KEEPS. The swallow is correct — the fix was
    never to remove it. If this starts raising, a corrupt history file
    stops every bet on the site from settling."""
    orig = linemoves.stream_history
    linemoves.stream_history = _blow_up
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ledger._snapshot_closes()      # must not raise
    finally:
        linemoves.stream_history = orig


# ── coverage reporting ──────────────────────────────────────────────

def test_an_unreadable_coverage_query_is_not_reported_as_an_early_season():
    """(0, 0) is a real and common state — no settled props yet. A broken
    query returning it would look like April rather than like a bug, and
    the coverage report would keep saying the reassuring thing."""
    orig = ledger.connect
    ledger.connect = _blow_up
    try:
        value, said = _say(lambda: coverage._settled_props_with_close("nfl"))
    finally:
        ledger.connect = orig
    assert value == (0, 0), "it must still return a pair"
    assert "nfl" in said and "RuntimeError" in said, said


def test_the_coverage_query_is_quiet_when_the_answer_is_honestly_zero():
    """A sport with nothing settled yet is not a failure and must not
    print like one."""
    value, said = _say(lambda: coverage._settled_props_with_close("nfl"))
    assert isinstance(value, tuple) and len(value) == 2, value
    assert not said.strip(), f"it complained on a working query: {said!r}"


# ── the shape itself ────────────────────────────────────────────────

def test_no_new_whole_body_swallower_arrives_unnoticed():
    """THE SWEEP, KEPT. Every function in `engine/` whose whole body sits
    under a bare `except Exception` is a candidate for this bug. The ones
    below are the ones that have been looked at and judged — either they
    name their failure now, or the value they return on failure is not
    one a quiet day produces.

    A new name appearing here is not automatically wrong. It is a
    prompt: decide which of the two it is, then add it."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    judged = {
        # names its failure (this file holds them)
        "_snapshot_closes", "_settled_props_with_close",
        # already names the ACTUAL reason in its own return value
        "_week_day_for", "_reason", "_with_records", "_hypothesis_lab_block",
        # telemetry whose caller reports the miss (lineledger.record_note)
        "_write", "record", "log_decision", "log_spend", "series",
        "code_version", "_journal", "record_top_pick_claim", "top_pick_line",
        # network/IO wrappers whose empty return IS the documented answer
        "_post", "_get_json", "settle_open",
        # THE STAKING BREAKER, added 2026-09-19 and caught by this sweep
        # on the day it was written. It returns "run" when it cannot read
        # the journal, which IS a value a quiet day produces — so it
        # carries `readable: False` and a `why` naming the error, and
        # every caller that prints it says the check could not run. The
        # choice not to fail closed is argued on `live_verdict` itself:
        # stopping the bets Ethan asked for because a query threw is a
        # surprise he did not agree to.
        "live_verdict",
    }

    def broad(h):
        return h.type is None or (isinstance(h.type, ast.Name)
                                  and h.type.id == "Exception")

    found = set()
    for dirpath, dirnames, files in os.walk(os.path.join(root, "engine")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            try:
                tree = ast.parse(open(os.path.join(dirpath, f)).read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for t in ast.walk(node):
                    if not isinstance(t, ast.Try) or not any(
                            broad(h) for h in t.handlers):
                        continue
                    span = t.end_lineno - t.lineno
                    fspan = (node.end_lineno - node.lineno) or 1
                    if span / fspan > 0.7 and fspan > 8:
                        found.add(node.name)
                    break
    assert len(found) > 5, f"the sweep stopped finding anything: {found}"
    assert not (found - judged), (
        f"new whole-body swallower(s): {sorted(found - judged)} — decide "
        f"whether the value returned on failure is one a QUIET DAY also "
        f"produces. If it is, make the failure say so and add the name here.")


# ── the pragma whose result was thrown away ─────────────────────────

def test_a_journal_mode_that_is_not_wal_is_said_out_loud():
    """`PRAGMA journal_mode=WAL` is a REQUEST, not a command: it returns
    the mode the database ended up in, and comes back "delete" — with no
    exception at all — when another connection holds the file. The old
    body ran it under a bare `except: pass` and ignored the row, so a box
    that never entered WAL was indistinguishable from one that did.

    It is the difference between a slow cycle and four builds a cycle
    dying on "database is locked", which is where the droplet was on
    2026-09-15."""
    assert db.journal_warning("delete"), "a rollback journal said nothing"
    assert "database is locked" in db.journal_warning("delete")
    assert "WAL" in db.journal_warning("delete")


def test_the_two_healthy_answers_stay_quiet():
    """A warning that fires on every connection is a warning nobody
    reads. `:memory:` reports "memory" and can never be WAL; that is not
    a fault and must not print."""
    assert db.journal_warning("wal") == ""
    assert db.journal_warning("WAL") == "", "the check is case-sensitive"
    assert db.journal_warning("memory") == ""


def test_tune_reports_the_mode_actually_in_force():
    """Behavioural, over both real shapes, so the reader of `tune` is not
    taking the pragma's word for it from a docstring."""
    import tempfile
    assert db.tune(db.connect(":memory:")) == "memory"
    path = os.path.join(tempfile.mkdtemp(), "x.db")
    assert db.tune(db.connect(path)) == "wal"


def test_a_bad_mode_prints_once_and_not_once_per_connection():
    """`connect()` is called from every build, every tool and every
    request path. The fix for an invisible outage must not be a visible
    flood."""
    conn = db.connect(":memory:")
    real, printed = conn.execute, []

    class _Rollback:
        """A connection that answers the pragma the way a locked file
        does: a row, no exception, the wrong mode."""
        def execute(self, sql, *a):
            if "journal_mode" in sql:
                class _Cur:
                    def fetchone(self_):
                        return ("delete",)
                return _Cur()
            return real(sql, *a)

    was = db._JOURNAL_WARNED
    try:
        db._JOURNAL_WARNED = False
        for _ in range(3):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                assert db.tune(_Rollback()) == "delete"
            printed.append(buf.getvalue())
    finally:
        db._JOURNAL_WARNED = was
    assert printed[0].strip(), "the first connection said nothing"
    assert printed[1] == "" and printed[2] == "", printed


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
