"""The heartbeat says why: each weekly job's last outcome, and where a failed
build stopped, in the public heartbeat.json — scrubbed.

The 30 October audit found the Lab's page five weeks old, and the reason
was only on the box: a line in the journal, a log under data/cache. The
same week the college board sat two hours on "exit 1: sqlite3.Operational
Error: database is locked" with nothing to say which write was waiting.
What these hold:

  * each weekly job's outcome is kept where the next process can read it
    (engine.maintenance weekly_jobs.json): started, ended, minutes, exit,
    cut off, and the last line of its log — which, for a run cut off at
    the hour, is the step the hour ran out in;
  * that holds for a job this process started and for one an earlier,
    since-exited process started (the chores run in short-lived children);
  * the heartbeat publishes them under each job's short name, with only
    the fields a reader needs;
  * a failed build's note names the frame in this checkout's code it died
    in, skipping the standard library's frames;
  * everything bound for the public file is scrubbed: no query-string
    secret (the odds key travels in URLs), no bearer token, no address.

Run directly: `python3 tests/test_the_heartbeat_says_why.py`
"""
import inspect
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance as M                              # noqa: E402


class _Proc:
    def __init__(self, code=None):
        self.code, self.pid, self.killed = code, 4242, False

    def poll(self):
        return self.code

    def kill(self):
        self.killed, self.code = True, -9

    def wait(self):
        return self.code


class _InTemp:
    """The chores' cache directory pointed at a scratch one for the test —
    never this checkout's data/cache."""
    def __enter__(self):
        self.td = tempfile.mkdtemp()
        self.keep = M._child_dir
        M._child_dir = lambda: Path(self.td)
        M._CHILDREN.clear()
        return Path(self.td)

    def __exit__(self, *exc):
        M._child_dir = self.keep
        M._CHILDREN.clear()


def test_a_line_bound_for_a_public_file_is_scrubbed():
    s = M.scrub_public("GET https://api.the-odds-api.com/v4/sports/nba/odds?apiKey=abc123&regions=us failed;"
                       " token=xyz; mailed you@example.com; Authorization: Bearer abc.def-ghi")
    for secret in ("abc123", "xyz", "you@example.com", "abc.def-ghi"):
        assert secret not in s, (secret, s)
    assert "apiKey=…" in s and "regions=us" in s and "…@…" in s
    assert len(M.scrub_public("x" * 500)) == 200


def test_a_finished_job_keeps_its_exit_minutes_and_last_line():
    with _InTemp() as td:
        logp = td / "weekly_lab.log"
        logp.write_text("  lab: replaying nba (1 of 6)…\n  lab: nba replayed\nlab: ok\n")
        M._CHILDREN["engine.lab"] = {"proc": _Proc(0), "started": 0.0, "log": logp, "fh": io.StringIO()}
        M.reap_children(lambda *_: None, now=1800.0)
        got = M.weekly_jobs_status()["engine.lab"]
        assert (got["exit"], got["minutes"], got["cut_off"], got["running"]) == (0, 30, False, False), got
        assert got["last"] == "lab: ok" and got["ended"]


def test_a_job_cut_off_at_the_hour_says_where_the_hour_ran_out():
    with _InTemp() as td:
        logp = td / "weekly_lab.log"
        logp.write_text("  lab: mlb replayed\n  lab: replaying nba (2 of 6)…\n")
        proc = _Proc(None)
        M._CHILDREN["engine.lab"] = {"proc": proc, "started": 0.0, "log": logp, "fh": io.StringIO()}
        M.reap_children(lambda *_: None, now=M.WEEKLY_JOB_TIMEOUT_S + 1)
        got = M.weekly_jobs_status()["engine.lab"]
        assert proc.killed and got["cut_off"] is True and got["exit"] == -9, got
        assert got["last"] == "lab: replaying nba (2 of 6)…"


def test_a_job_an_earlier_process_started_is_kept_too():
    keep_runs, keep_kill = M._pid_runs, os.killpg
    try:
        with _InTemp() as td:
            (td / "weekly_lab.log").write_text("  lab: replaying cfb (3 of 6)…\n")
            (td / "weekly_lab.pid").write_text(json.dumps({"pid": 4242, "module": "engine.lab", "started": 0.0}))
            M._pid_runs = lambda pid, module: True
            os.killpg = lambda *a: None                 # never signal a real process
            M._reap_pid_files(M.WEEKLY_JOB_TIMEOUT_S + 60)
            got = M.weekly_jobs_status()["engine.lab"]
            assert got["cut_off"] is True and got["last"] == "lab: replaying cfb (3 of 6)…", got
            # And one that finished on its own while nobody was its parent.
            (td / "weekly_deepfit.log").write_text("deepfit: done\n")
            (td / "weekly_deepfit.pid").write_text(json.dumps({"pid": 4243, "module": "engine.deepfit",
                                                               "started": 0.0}))
            M._pid_runs = lambda pid, module: False
            M._reap_pid_files(600.0)
            fit = M.weekly_jobs_status()["engine.deepfit"]
            assert fit["cut_off"] is False and fit["exit"] is None and fit["last"] == "deepfit: done", fit
            assert M.weekly_jobs_status()["engine.lab"]["cut_off"] is True, "one job's record leaves the others"
    finally:
        M._pid_runs, os.killpg = keep_runs, keep_kill


def test_a_job_reaped_after_a_restart_ends_at_its_last_word():
    """7 November: "107 minutes" for a refit inside its 50. The site
    restarted once the job ended (the updater waits for it), and the new
    process saw it gone an hour later; the job's log stopped when it did."""
    keep_runs = M._pid_runs
    try:
        with _InTemp() as td:
            t0 = 1_780_000_000.0
            logp = td / "weekly_deepfit.log"
            logp.write_text("deep refit: round of 2026-11-04: nothing done this run\n")
            os.utime(logp, (t0 + 50 * 60, t0 + 50 * 60))
            (td / "weekly_deepfit.pid").write_text(json.dumps({"pid": 4243, "module": "engine.deepfit",
                                                               "started": t0}))
            M._pid_runs = lambda pid, module: False
            said = M._reap_pid_files(t0 + 107 * 60)
            fit = M.weekly_jobs_status()["engine.deepfit"]
            assert fit["minutes"] == 50 and fit["ended"] == M._iso(t0 + 50 * 60), fit
            assert said[0] == "engine.deepfit: finished in about 50 min", said
            # A log written outside the run (a clock that jumped) is not
            # believed: the notice stands, as before.
            os.utime(logp, (t0 - 60, t0 - 60))
            (td / "weekly_deepfit.pid").write_text(json.dumps({"pid": 4244, "module": "engine.deepfit",
                                                               "started": t0}))
            M._reap_pid_files(t0 + 107 * 60)
            assert M.weekly_jobs_status()["engine.deepfit"]["minutes"] == 107
    finally:
        M._pid_runs = keep_runs


def test_a_job_this_process_reaps_a_cycle_late_ends_at_its_last_word_too():
    """The bug scan reads a few logs; the heartbeat gave it 38 minutes, the
    cycle that noticed it done. One cut off at the ceiling ends when cut."""
    with _InTemp() as td:
        t0 = 1_780_000_000.0
        logp = td / "weekly_bugscan.log"
        logp.write_text("bug scan: nothing broken\n")
        os.utime(logp, (t0 + 40, t0 + 40))
        M._CHILDREN["engine.bugscan"] = {"proc": _Proc(0), "started": t0, "log": logp, "fh": io.StringIO()}
        said = M.reap_children(lambda *_: None, now=t0 + 38 * 60)
        got = M.weekly_jobs_status()["engine.bugscan"]
        assert got["minutes"] == 1 and got["ended"] == M._iso(t0 + 40) and got["exit"] == 0, got
        assert said[0] == "engine.bugscan: finished in 1 min with exit 0", said
        lab = td / "weekly_lab.log"
        lab.write_text("lab: replaying nba (2 of 6)…\n")
        os.utime(lab, (t0 + 600, t0 + 600))
        M._CHILDREN["engine.lab"] = {"proc": _Proc(None), "started": t0, "log": lab, "fh": io.StringIO()}
        M.reap_children(lambda *_: None, now=t0 + M.WEEKLY_JOB_TIMEOUT_S + 1)
        got = M.weekly_jobs_status()["engine.lab"]
        assert got["cut_off"] is True and got["ended"] == M._iso(t0 + M.WEEKLY_JOB_TIMEOUT_S + 1), got


def test_a_job_started_is_kept_as_running():
    src = inspect.getsource(M._spawn_module)
    assert "_record_job(module, started=_iso(_time.time()), running=True" in src


def test_the_heartbeat_publishes_them_scrubbed():
    import launch
    from engine import lab as LB
    keep_lab = LB.LAB_PATH
    with _InTemp() as td:
        # No Lab page here, so no sport dates (tests/test_the_heartbeat_
        # names_each_sports_lab_date.py holds those).
        LB.LAB_PATH = td / "web" / "data" / "backtest.json"
        try:
            M._record_job("engine.lab", started="2026-11-03T04:00:00", ended="2026-11-03T05:00:01", minutes=60,
                          exit=-9, cut_off=True, running=False, last="lab: replaying nba (1 of 6)…", pid=4242)
            M._record_job("engine.bugscan", last="mailed owner@example.com with apiKey=abc")
            got = launch._weekly_jobs_public()
        finally:
            LB.LAB_PATH = keep_lab
    assert got["lab"] == {"started": "2026-11-03T04:00:00", "ended": "2026-11-03T05:00:01", "minutes": 60,
                          "exit": -9, "cut_off": True, "running": False, "last": "lab: replaying nba (1 of 6)…"}
    assert "owner@example.com" not in json.dumps(got) and "abc" not in got["bugscan"]["last"]
    assert '"weekly": _weekly_jobs_public()' in inspect.getsource(launch._write_heartbeat)


def test_a_failed_build_says_where_it_stopped():
    import launch
    root = str(launch.ROOT)
    out = ["Traceback (most recent call last):",
           f'  File "{root}/cfb_build.py", line 2851, in main',
           "    print(...)",
           f'  File "{root}/engine/ledger.py", line 812, in journal',
           "    conn.execute(...)",
           '  File "/usr/lib/python3.11/sqlite3/dbapi2.py", line 10, in execute',
           "sqlite3.OperationalError: database is locked"]
    assert launch._innermost_frame(out) == "engine/ledger.py:812 in journal"
    assert launch._failure_note(1, out[-1], out) == \
        "exit 1: sqlite3.OperationalError: database is locked (at engine/ledger.py:812 in journal)"
    assert launch._innermost_frame(['  File "cfb_build.py", line 5, in <module>', "NameError: x"]) == \
        "cfb_build.py:5 in <module>"
    assert launch._failure_note(2, "boom", ["boom"]) == "exit 2: boom"
    leaky = launch._failure_note(1, "HTTPError: https://x/odds?apiKey=SECRET1&markets=h2h", [])
    assert "SECRET1" not in leaky and "markets=h2h" in leaky
    src = inspect.getsource(launch._run_build)
    assert "_failure_note(proc.returncode, tail, out)" in src


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
