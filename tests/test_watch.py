"""A tripwire that fires on noise is worse than no tripwire.

The obvious way to automate a betting model is to let something run the
numbers nightly and tune until they improve. On 247 settled bets the 2-sigma
bar is +/- 6.3 points, so anything hunting for improvements finds one every
night and every one is luck. watch.py is the deliberate alternative: it
measures, compares against a bar fixed in advance, and stays silent.

What has to hold, or it becomes the thing it was built to avoid:

  * it changes nothing,
  * silence on a quiet night, so the report stays worth reading,
  * fires on CROSSING a bar, not on sitting past one,
  * a move only counts if it beats the sample's own error bar,
  * a crashed watch reports, because a silent broken check is the one
    failure that makes monitoring worthless.

Run directly: `python3 tests/test_watch.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import watch as w                                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Count:
    """Minimal stand-in for a connection that only gets counted."""

    def __init__(self, n):
        self.n = n

    def execute(self, q, *a):
        n = self.n
        return type("R", (), {"fetchone": lambda _s: (n,)})()


def _journal(n_main=260, n_loose=580, claim=0.58, land=0.46):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, "
                 "odds REAL, book TEXT, hit_prob REAL, edge REAL, status TEXT,"
                 " category TEXT, date TEXT, ts TEXT)")
    rows = []
    for cat, n, p, l in (("main", n_main, claim, land),
                         ("loose", n_loose, 0.59, 0.60)):
        for i in range(n):
            rows.append(("mlb", "total_bases", "OVER", -110, "DraftKings", p,
                         0.04, "won" if i < round(n * l) else "lost", cat,
                         f"2026-07-{10 + i % 20:02d}",
                         f"2026-07-{10 + i % 20:02d}T12:00:00"))
    conn.executemany("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def _tmp_state():
    w.STATE = Path(tempfile.mkdtemp()) / "watch.json"
    return w.STATE


# --- it must not act ---------------------------------------------------------
def test_it_writes_nothing_but_its_own_state():
    """The whole premise. A watch that can adjust a parameter is an
    optimiser, and an optimiser on 247 bets fits noise."""
    src = open(os.path.join(ROOT, "watch.py"), encoding="utf-8").read()
    body = src[src.index("# --- the watches"):]
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "commit()",
                      "save(", "apply_temperature"):
        assert forbidden not in body, forbidden
    # the one thing it may write
    assert "_save_state" in src and "STATE.write_text" in src


def test_the_report_says_it_changed_nothing():
    conn = _journal()
    _tmp_state()
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        w.run(conn, show_all=True)
    assert "Nothing here has been changed" in buf.getvalue() \
        or "nothing crossed a bar" in buf.getvalue()


# --- silence is the default --------------------------------------------------
def test_a_quiet_night_prints_nothing_at_all():
    """doctor.py's own comment: noise teaches you to ignore the run. A
    nightly report that always says something gets skimmed, including on
    the night it matters."""
    import contextlib
    import io
    conn = _journal()
    _tmp_state()
    with contextlib.redirect_stdout(io.StringIO()):
        w.run(conn)                       # first run establishes a baseline
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = w.run(conn)                  # nothing has changed since
    assert buf.getvalue() == "", buf.getvalue()
    assert rc == 0


def test_show_all_overrides_the_silence():
    import contextlib
    import io
    conn = _journal()
    _tmp_state()
    with contextlib.redirect_stdout(io.StringIO()):
        w.run(conn)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        w.run(conn, show_all=True)
    out = buf.getvalue()
    assert "journal size" in out and "calibration gap" in out


# --- crossing, not sitting ---------------------------------------------------
def test_a_milestone_fires_once_and_then_stops():
    """A tripwire that re-fires every night once tripped is a tripwire
    nobody reads."""
    assert w.watch_journal(_Count(360), {"journal_n": 340})["fired"] is True
    assert w.watch_journal(_Count(365), {"journal_n": 360})["fired"] is False


def test_the_milestones_say_why_each_one_matters():
    """A number with no reason attached gets moved the first time it is
    inconvenient. Each of these is quoted from selfit's measured power."""
    assert set(w.JOURNAL_MILESTONES) == {350, 500, 750}
    assert "70%" in w.JOURNAL_MILESTONES[500]
    for text in w.JOURNAL_MILESTONES.values():
        assert len(text) > 20, text


def test_the_selection_bar_is_the_one_named_in_advance():
    """z 2.5 was chosen while the estimate stood at z 1.87 — before the
    data could argue. Re-choosing it later is the move the whole file
    exists to prevent."""
    assert w.SELECTION_Z == 2.5
    src = open(os.path.join(ROOT, "watch.py"), encoding="utf-8").read()
    assert "1.87" in src, "the bar has to carry the reading it was set against"


def test_the_selection_watch_fires_on_the_crossing_only():
    conn = _journal()
    first = w.watch_selection(conn, {})
    assert first["fired"] is True and abs(first["value"]) >= w.SELECTION_Z
    again = w.watch_selection(conn, {"selection_z": first["value"]})
    assert again["fired"] is False


# --- a move must beat its own noise ------------------------------------------
def test_resampling_is_not_a_move():
    """+12.2% to +9.4% on 247 bets is the spread between selcheck's own
    adjustment schemes. If that fires, the tripwire fires every night."""
    assert w._moved(0.094, 0.122, 0.031) is False
    assert w._moved(0.030, 0.122, 0.031) is True


def test_a_missing_baseline_never_fires_a_move():
    """First run has nothing to compare against, and inventing a crossing
    out of that would greet every fresh install with a false alarm."""
    assert w._moved(0.50, None, 0.03) is False
    assert w._moved(0.50, 0.10, 0.0) is False


# --- a broken watch is a finding ---------------------------------------------
def test_closures_read_the_store_the_veto_loads_not_a_fresh_mine():
    """The tripwire has to report what will actually refuse picks. A fresh
    mine could disagree with the stored result and would be announcing a
    hypothetical pricing change rather than the real one."""
    import inspect
    src = inspect.getsource(w.watch_closures)
    assert "lp.load()" in src
    assert "records_from_ledger" not in src


def test_a_crashing_watch_reports_instead_of_going_quiet():
    """Swallowing would make a broken tripwire look like a quiet night —
    the same reasoning as doctor.py's _check helper."""
    import contextlib
    import io

    def boom(conn, state):
        raise RuntimeError("kaboom")

    was = w.WATCHES
    w.WATCHES = [boom]
    _tmp_state()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            w.run(_journal())
        out = buf.getvalue()
        assert "the watch itself failed" in out and "kaboom" in out
    finally:
        w.WATCHES = was


# --- the nightly runner ------------------------------------------------------
def _sh(name):
    return open(os.path.join(ROOT, "tools", name), encoding="utf-8").read()


def test_the_runner_puts_path_back_for_launchd():
    """launchd hands a job a nearly empty PATH. Without this the job dies
    with 'command not found' at 6am and the first sign is a week of missing
    ingest."""
    s = _sh("nightly.sh")
    assert "export PATH=" in s and "/opt/homebrew/bin" in s
    assert "command -v python3" in s


def test_the_runner_cannot_overlap_itself():
    s = _sh("nightly.sh")
    assert "mkdir \"$LOCK\"" in s and "trap" in s


def test_watch_runs_even_when_launch_failed():
    """A failed ingest is exactly when the readings are most worth having."""
    s = _sh("nightly.sh")
    assert "watch.py runs even if launch.py failed" in s
    i, j = s.index("LAUNCH_RC=$?"), s.index("watch.py 2>&1")
    assert i < j, "watch must be invoked after launch, unconditionally"


def test_a_quiet_night_sends_no_notification():
    """Same reasoning as the silent report: a daily 'all fine' ping trains
    you to swipe it away, including the one that mattered."""
    s = _sh("nightly.sh")
    # The logic, not the prose. An earlier version of this assertion named
    # a phrase that the file wraps across two comment lines, so it went red
    # on a reflow that changed nothing.
    assert 'elif [ -n "$WATCH_OUT" ]' in s, "notify only when watch spoke"
    assert 'if [ "$LAUNCH_RC" -ne 0 ]' in s, "…or when the run itself broke"
    assert "notify" in s and "display notification" in s


def test_the_installer_does_not_fire_on_install():
    s = _sh("install-nightly.sh")
    assert "<key>RunAtLoad</key><false/>" in s


def test_the_installer_can_be_removed_and_run_by_hand():
    s = _sh("install-nightly.sh")
    assert "--remove" in s and "--now" in s and "launchctl unload" in s


def test_launchd_is_chosen_for_the_sleep_behaviour():
    """A laptop shut at 6am simply skips a cron job, and skipped ingest is
    the failure this exists to prevent."""
    s = _sh("install-nightly.sh")
    assert "WAKES" in s or "wake" in s
    assert "StartCalendarInterval" in s


def test_the_logs_and_lock_are_gitignored():
    ig = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "logs/" in ig and ".nightly.lock" in ig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
