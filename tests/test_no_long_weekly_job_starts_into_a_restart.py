"""No long weekly job starts while the box's updater waits to restart into
new code, whether it waits for a weekly job or for the board sweep.

Tuesday 10 November 2026: a push was pulled while a board sweep ran, so
the updater left data/cache/restart_wanted.json and waited for the sweep.
The app read only the weekly job's note (restart_pending.json), and at
00:20:49 the day's chores started the deep refit, the bug scan and the
referees' fit inside that wait. When the sweep ended, the updater found
the refit running and waited for it instead, up to WEEKLY_WAIT_MAX_S: an
hour for code due within minutes, with the boards' new code already in
every build and the server still on the old one.

Now `engine/maintenance.updater_waiting` reads both notes, the sweep's with
launch.py's own TTL, so the long jobs (HOLDABLE: the deep refit, the Lab,
the inventions' re-measure, the backup, the referees' fit) are held
(`_hold`) and started once the restart lands (`launch_held`), the same day,
their attempts unspent. The last three are held now too (the re-measure
ran 76 minutes on 5 November, the backup 25), and none of them waits for
the heavy jobs, as none did. Board learning, on the settle pass's clock, is
put off to the next pass that learns, its clock not reset. A job held
without its runner is never started for real from a test's state.

The updater half runs the real script against real git repositories, as
tests/test_the_deploy_waits_for_a_weekly_job.py does; the app half calls
engine/maintenance on scratch state.

Run directly: `python3 tests/test_no_long_weekly_job_starts_into_a_restart.py`
"""
import datetime as dt
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import launch                                         # noqa: E402
from engine import maintenance as M                   # noqa: E402
from engine import modelstate                         # noqa: E402

SPEC = importlib.util.spec_from_file_location("autoupdate", ROOT / "deploy" / "autoupdate.py")
AU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AU)

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
TUE, WED, THU = dt.date(2026, 11, 10), dt.date(2026, 11, 11), dt.date(2026, 11, 12)


def _g(cwd, *a):
    return subprocess.run(("git", "-C", cwd) + a, env=ENV, check=True, capture_output=True, text=True).stdout.strip()


def _repo():
    origin, clone = tempfile.mkdtemp(), tempfile.mkdtemp()
    _g(origin, "init", "-q", "-b", "main")
    Path(origin, "f.txt").write_text("one\n")
    Path(origin, ".gitignore").write_text("data/\n")
    _g(origin, "add", "."), _g(origin, "commit", "-qm", "one")
    subprocess.run(("git", "clone", "-q", origin, clone), env=ENV, check=True, capture_output=True)
    return origin, clone


def _push(origin, text):
    Path(origin, "f.txt").write_text(text + "\n")
    _g(origin, "add", "."), _g(origin, "commit", "-qm", text)


def _systemctl():
    bindir = tempfile.mkdtemp()
    log = os.path.join(bindir, "calls")
    Path(bindir, "systemctl").write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    os.chmod(os.path.join(bindir, "systemctl"), 0o755)
    return bindir, log


def _update(repo, bindir):
    subprocess.run((sys.executable, str(ROOT / "deploy" / "autoupdate.py"), "--repo", repo, "--service", "qellys"),
                   env={**ENV, "PATH": bindir + os.pathsep + os.environ["PATH"],
                        "QB_ENV_FILE": "/nonexistent", "QB_UPDATE_REQUIRE": "off"},
                   check=True, capture_output=True, text=True)
    return json.loads(Path(repo, "data", "autoupdate.json").read_text())


def _restarts(log):
    return open(log).read().count("restart qellys") if os.path.exists(log) else 0


def _sweep(repo, running=True):
    path = Path(repo, "data", "cache", "sweep.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"handshake": 1, "pid": os.getpid(), "running": running,
                                "started": time.time() - 120, "finished": None, "commit": ""}))


def _refit(repo):
    """A live process standing in for the deep refit, with the pid file the
    app's `_spawn_module` leaves."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "engine.deepfit"])
    p = Path(repo, "data", "cache", "weekly_deepfit.pid")
    p.write_text(json.dumps({"pid": proc.pid, "module": "engine.deepfit", "started": time.time()}))
    return proc


class _Cache:
    """The app's data/cache pointed at ``where`` for the block."""
    def __init__(self, where):
        self.where = Path(where)

    def __enter__(self):
        self.keep = M._child_dir
        M._child_dir = lambda: self.where
        return self.where

    def __exit__(self, *exc):
        M._child_dir = self.keep


def _cache(**notes):
    d = Path(tempfile.mkdtemp())
    for name, note in notes.items():
        (d / name).write_text(note if isinstance(note, str) else json.dumps(note))
    return d


# --- the night of 10 November, end to end ----------------------------------------
def test_the_night_of_10_november_both_ways():
    # Then: the refit started inside the wait for the sweep, so the end of
    # the sweep brought no restart; the updater waited for the refit.
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    first = _update(repo, bindir)
    assert _restarts(log) == 0 and "waits for the board sweep in progress" in first["note"], first
    proc = _refit(repo)
    try:
        _sweep(repo, running=False)
        after = _update(repo, bindir)
        assert _restarts(log) == 0 and "waits for the weekly deepfit in progress" in after["note"], after
    finally:
        proc.kill(), proc.wait()

    # Now: the sweep's note holds the refit, so the sweep's end is the
    # restart's, and the held refit starts once it has landed.
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    _update(repo, bindir)
    pulled = _g(repo, "rev-parse", "--short", "HEAD")
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    ran, lines = [], []
    with _Cache(Path(repo, "data", "cache")):
        assert M.updater_waiting() == pulled, "the updater's own note, as it writes it"
        state = {}
        M._hold(state, sp, "deep", TUE, lines.append)          # as the chores' deep refit site does
        assert any("held" in ln and "sweep" in ln for ln in lines), lines
        M.launch_held(sp, TUE, lambda *_: None, deep_next=lambda log: ran.append("refit") or [])
        assert ran == [], "nothing starts into the restart"
        _sweep(repo, running=False)
        done = _update(repo, bindir)
        assert _restarts(log) == 1 and "restarted qellys" in done["note"], done
        assert M.updater_waiting() == ""
        M.launch_held(sp, TUE, lambda *_: None, deep_next=lambda log: ran.append("refit") or [])
    assert ran == ["refit"]
    assert M._load_state(sp)["deep_attempted"] == TUE.isoformat()


# --- the note ----------------------------------------------------------------------
def test_the_sweeps_note_holds_the_long_jobs_and_a_stale_or_empty_one_does_not():
    now = time.time()
    want = M.RESTART_WANT_NAME
    with _Cache(_cache()):
        assert M.updater_waiting() == ""
    with _Cache(_cache(**{want: {"commit": "f00dfeed", "since": now - 60}})):
        assert M.updater_waiting() == "f00dfeed"
    with _Cache(_cache(**{want: {"commit": "f00dfeed", "since": now - M.RESTART_WANT_TTL_S - 5}})):
        assert M.updater_waiting() == "", "an updater that died must not hold the fitters for ever"
    for broken in ({"since": now}, {"commit": "", "since": now}, "not json", ["a", "list"]):
        with _Cache(_cache(**{want: broken})):
            assert M.updater_waiting() == "", broken
    # A stale weekly note does not hide a fresh sweep note, nor the other way.
    stale = {"commit": "0ld", "since": now - M.RESTART_PENDING_TTL_S - 5}
    with _Cache(_cache(**{M.RESTART_PENDING_NAME: stale, want: {"commit": "f00dfeed", "since": now}})):
        assert M.updater_waiting() == "f00dfeed"
    with _Cache(_cache(**{M.RESTART_PENDING_NAME: {"commit": "beef", "since": now},
                          want: {"commit": "0ld", "since": now - M.RESTART_WANT_TTL_S - 5}})):
        assert M.updater_waiting() == "beef"


def test_the_note_is_the_one_the_updater_leaves_and_the_sweeps_read():
    assert AU.RESTART_WANT[-1] == launch.RESTART_WANT_NAME == M.RESTART_WANT_NAME
    assert AU.RESTART_WANT[:-1] == ("data", "cache") and M._child_dir() == ROOT / "data" / "cache"
    assert M.RESTART_WANT_TTL_S == launch.RESTART_WANT_TTL_S, "the fitters held as long as the sweeps are"
    assert M.RESTART_WANT_TTL_S > AU.RESTART_WAIT_MAX_S, "for as long as the updater may wait for the sweep"


# --- the holds ---------------------------------------------------------------------
def test_held_inventions_and_backup_start_once_the_restart_lands_their_attempts_unspent():
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    lines = []
    state = {"last_backup": "2026-11-05"}
    M._hold(state, sp, "inventions", THU, lines.append)
    M._hold(state, sp, "backup", THU, lines.append)
    saved = M._load_state(sp)
    assert saved["held"] == {"inventions": "2026-11-12", "backup": "2026-11-12"}
    assert "inventions_attempted" not in saved and saved["last_backup"] == "2026-11-05", "nothing spent"
    assert any("the inventions' re-measure: held" in ln for ln in lines), lines
    assert any("the backup: held" in ln for ln in lines), lines
    ran = []
    runners = dict(inventions_run=lambda log: ran.append("inventions") or ["inv started"],
                   backup_run=lambda log: ran.append("backup") or ["backup started"])
    with _Cache(_cache(**{M.RESTART_WANT_NAME: {"commit": "f00dfeed", "since": time.time()}})):
        assert M.launch_held(sp, THU, lambda *_: None, **runners) == [] and ran == []
    with _Cache(_cache()):
        out = M.launch_held(sp, THU, lambda *_: None, **runners)
        assert ran == ["inventions", "backup"] and out == ["inv started", "backup started"], (ran, out)
        after = M._load_state(sp)
        assert after["inventions_attempted"] == after["last_backup"] == "2026-11-12" and not after["held"]
        M.launch_held(sp, THU, lambda *_: None, **runners)
    assert ran == ["inventions", "backup"], "each held job starts once"
    # Held on Thursday, not started by Friday: Friday leaves it to its own schedule.
    M._hold({}, sp, "inventions", THU, lambda *_: None)
    with _Cache(_cache()):
        M.launch_held(sp, THU + dt.timedelta(days=1), lambda *_: None, **runners)
    assert ran == ["inventions", "backup"] and not M._load_state(sp)["held"]


def test_a_held_referees_fit_starts_once_the_restart_lands_the_same_tuesday():
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    lines, ran = [], []
    M._hold({}, sp, "refs", TUE, lines.append)
    assert any("the referees' fit: held" in ln for ln in lines), lines
    assert "nflrefs_attempted" not in M._load_state(sp)
    with _Cache(_cache(**{M.RESTART_PENDING_NAME: {"commit": "f00dfeed", "since": time.time()}})):
        M.launch_held(sp, TUE, lambda *_: None, refs_run=lambda log: ran.append("refs") or [])
    assert ran == []
    with _Cache(_cache()):
        M.launch_held(sp, TUE, lambda *_: None, refs_run=lambda log: ran.append("refs") or [])
    assert ran == ["refs"] and M._load_state(sp)["nflrefs_attempted"] == TUE.isoformat()

def test_the_light_jobs_never_wait_for_the_heavy_ones():
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    state = {}
    for job in ("deep", "lab", "backup"):
        M._hold(state, sp, job, WED, lambda *_: None)
    ran = []
    kw = dict(deep=lambda log: ran.append("deep") or [], lab_run=lambda log: ran.append("lab") or [],
              backup_run=lambda log: ran.append("backup") or [])
    with _Cache(_cache()):
        M.launch_held(sp, WED, lambda *_: None, **kw)
        assert ran == ["deep", "backup"], "one heavy job a cycle; the backup beside it, as before"
        assert M._load_state(sp)["held"] == {"lab": "2026-11-11"}
        M.launch_held(sp, WED, lambda *_: None, **kw)
    assert ran == ["deep", "backup", "lab"]


def test_a_held_job_without_its_runner_is_never_started_for_real_from_a_tests_state():
    spawned = []
    keep = (M._spawn_module, os.environ.get(modelstate.ENV_VAR), M.STATE_PATH)
    M._spawn_module = lambda module, log, args=(): spawned.append((module, tuple(args))) or [f"{module} started"]
    try:
        # In the suite's sandbox: a held job whose runner was not given stays held.
        os.environ[modelstate.ENV_VAR] = keep[1] or tempfile.mkdtemp()
        sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
        state = {}
        for job in ("inventions", "backup", "lab"):
            M._hold(state, sp, job, THU, lambda *_: None)
        with _Cache(_cache()):
            M.launch_held(sp, THU, lambda *_: None, lab_run=lambda log: ["lab"])
        assert spawned == [] and M._load_state(sp)["held"] == {"inventions": "2026-11-12", "backup": "2026-11-12"}
        # Outside it, on a scratch state file: the real re-measure is the one
        # wired in, but the backup is only ever the real state file's.
        os.environ.pop(modelstate.ENV_VAR, None)
        with _Cache(_cache()):
            M.launch_held(sp, THU, lambda *_: None)
        assert spawned == [("engine.inventionfit", ())], spawned
        assert M._load_state(sp)["held"] == {"backup": "2026-11-12"}
        M.STATE_PATH = sp                                    # this scratch file standing in for the real one
        with _Cache(_cache()):
            M.launch_held(sp, THU, lambda *_: None)
        assert spawned[-1] == ("engine.backupzip", ("2026-11-12",)), spawned
        assert M._load_state(sp)["last_backup"] == "2026-11-12" and not M._load_state(sp)["held"]
    finally:
        M._spawn_module, M.STATE_PATH = keep[0], keep[2]
        if keep[1] is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = keep[1]


def _settle_harness():
    """The settle pass offline, as its own tests run it."""
    name = "test_the_settle_pass_learns_hourly_and_says_where_its_time_went"
    spec = importlib.util.spec_from_file_location("_settle_" + name, ROOT / "tests" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_board_learning_is_put_off_into_a_restart_and_runs_at_the_next_pass_that_learns():
    ST = _settle_harness()
    mp, calls, ran = ST.MP(), [], []
    box = {"lconn": ST._journal([ST.TODAY.isoformat()]), "settled": 3}
    ST._stub(mp, calls, box)
    mp.setattr(M, "_run_board_learning", lambda lconn, hconn, log: ran.append("board learning") or [])
    try:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "m.json"
            lines = []
            with _Cache(_cache(**{M.RESTART_WANT_NAME: {"commit": "f00dfeed", "since": time.time()}})):
                M.settle_open(log=lines.append, state_path=state, today=ST.TODAY, now=1000.0, force=True)
            assert calls.count("learn") == 1, "the pass still learns"
            assert ran == [] and any("board learning: put off" in ln for ln in lines), lines
            assert "last_boardlearn_ts" not in M._read_state(state), "its clock is not reset"
            with _Cache(_cache()):
                ST._pass(state, 1000.0 + M.LEARN_EVERY_S + 1)
            assert ran == ["board learning"]
            assert M._read_state(state)["last_boardlearn_ts"] == 1000.0 + M.LEARN_EVERY_S + 1
    finally:
        mp.undo()

def test_every_long_jobs_start_holds_while_the_updater_waits():
    src = inspect.getsource(M)
    for start, job in (('for line in _run_deep_refit(log):', "deep"),
                       ('for line in _continue_deep_refit(log):', "deep"),
                       ('for line in _run_lab(log):', "lab"),
                       ('for line in _run_inventions(log):', "inventions"),
                       ('for line in _run_nflrefs(log):', "refs"),
                       ('for line in _spawn_module("engine.backupzip", log, (today.isoformat(),)):', "backup")):
        i = src.index(start)
        before = src[max(0, i - 700):i]
        assert "if updater_waiting():" in before and f'_hold(state, state_path, "{job}", today, log' in before, start
    assert set(M.HOLDABLE) == {"deep", "lab", "inventions", "backup", "refs"}
    for job, (mark, _name) in M.HOLDABLE.items():
        assert f'state["{mark}"] = today.isoformat()' in src, (job, mark)
    assert set(M.HEAVY_WEEKLY) <= set(M.HOLDABLE)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=6)
    print(f"\n{len(fns) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
