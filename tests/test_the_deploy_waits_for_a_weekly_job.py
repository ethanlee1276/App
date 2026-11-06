"""A push no longer kills a weekly job in progress: the restart waits for it.

Wednesday 2026-11-04: two afternoon pushes restarted the unit while the
weekly jobs ran, and a restart kills every child in the unit, detached or
not — the Lab 85 minutes in, board learning at 92, and the deep refit two
minutes into its round, each then owed another day (the heartbeat's
weekly block showed all of them ended with no exit, at the two restarts).

Now the updater (deploy/autoupdate.py) reads the app's pid files
(data/cache/weekly_<name>.pid): while one names a live process running
that job, the restart waits, up to WEEKLY_WAIT_MAX_S from the pull, and it
leaves data/cache/restart_pending.json — NOT restart_wanted.json, so the
boards keep sweeping. While that note is fresh the app starts no new deep
refit or Lab run (engine/maintenance `_hold`), and starts what it held the
moment the restart lands (`launch_held`), the same day, its attempt not
spent. Then the board sweep is waited on as before, on its own clock.

The updater half runs the real script against real git repositories with a
systemctl that records its arguments and a real process standing in for
the job; the app half calls engine/maintenance on a scratch state file.

Run directly: `python3 tests/test_the_deploy_waits_for_a_weekly_job.py`
"""
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance as M                   # noqa: E402

SPEC = importlib.util.spec_from_file_location("autoupdate", ROOT / "deploy" / "autoupdate.py")
AU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AU)

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


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


def _job(module="engine.lab"):
    """A live process whose command line names the job, as the app's are."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", module])


def _pid_file(repo, proc, module="engine.lab", started=None):
    p = Path(repo, "data", "cache", f"weekly_{module.rsplit('.', 1)[-1]}.pid")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": proc.pid if hasattr(proc, "pid") else proc, "module": module,
                             "started": time.time() - 600 if started is None else started}))
    return p


def _note(repo, name):
    p = Path(repo, "data", "cache", name)
    return json.loads(p.read_text()) if p.exists() else None


def _sweep(repo, running=True):
    path = Path(repo, "data", "cache", "sweep.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"handshake": 1, "pid": os.getpid(), "running": running,
                                "started": time.time() - 120, "finished": None, "commit": ""}))


# --- the updater -----------------------------------------------------------------
def test_new_code_waits_for_the_weekly_job_and_the_boards_keep_sweeping():
    origin, repo = _repo()
    proc = _job()
    try:
        _pid_file(repo, proc)
        _push(origin, "two")
        bindir, log = _systemctl()
        state = _update(repo, bindir)
        assert Path(repo, "f.txt").read_text() == "two\n", "the code is pulled at once"
        assert _restarts(log) == 0, "restarted in the middle of a weekly job"
        assert state["ok"] and "waits for the weekly lab in progress" in state["note"], state
        assert "the boards keep sweeping" in state["note"]
        pend = _note(repo, "restart_pending.json")
        assert pend and pend["commit"] == _g(repo, "rev-parse", "--short", "HEAD") and pend["job"] == "lab"
        assert _note(repo, "restart_wanted.json") is None, "a weekly wait never holds the board sweeps"
        # Five minutes on, still running: still waiting, the clock not reset.
        again = _update(repo, bindir)
        assert _restarts(log) == 0 and _note(repo, "restart_pending.json")["since"] == pend["since"], again
    finally:
        proc.kill(), proc.wait()
    # The job ends: the next run restarts and clears the note.
    done = _update(repo, bindir)
    assert _restarts(log) == 1 and "restarted qellys" in done["note"], done
    assert _note(repo, "restart_pending.json") is None and _note(repo, "restart_wanted.json") is None


def test_after_the_job_a_sweep_in_progress_is_waited_on_with_its_own_clock():
    origin, repo = _repo()
    proc = _job()
    try:
        _pid_file(repo, proc)
        _push(origin, "two")
        bindir, log = _systemctl()
        _update(repo, bindir)
        # Make the weekly wait look long: the sweep's clock must not inherit it.
        pend = _note(repo, "restart_pending.json")
        pend["since"] -= 40 * 60
        Path(repo, "data", "cache", "restart_pending.json").write_text(json.dumps(pend))
    finally:
        proc.kill(), proc.wait()
    _sweep(repo, running=True)
    state = _update(repo, bindir)
    assert _restarts(log) == 0 and "waits for the board sweep" in state["note"], state
    want = _note(repo, "restart_wanted.json")
    assert want and time.time() - want["since"] < 120, "the sweep's wait starts its own clock"
    assert _note(repo, "restart_pending.json") is None
    _sweep(repo, running=False)
    done = _update(repo, bindir)
    assert _restarts(log) == 1, done


def test_the_weekly_wait_has_a_ceiling():
    origin, repo = _repo()
    proc = _job()
    try:
        _pid_file(repo, proc)
        _push(origin, "two")
        bindir, log = _systemctl()
        _update(repo, bindir)
        pend = _note(repo, "restart_pending.json")
        pend["since"] -= AU.WEEKLY_WAIT_MAX_S + 60
        Path(repo, "data", "cache", "restart_pending.json").write_text(json.dumps(pend))
        state = _update(repo, bindir)
    finally:
        proc.kill(), proc.wait()
    assert _restarts(log) == 1 and "restarted qellys after waiting" in state["note"], state


def test_a_dead_stale_or_reused_pid_is_not_waited_on():
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])   # names no job
    try:
        for kw in ({"proc": dead.pid}, {"proc": other, "module": "engine.deepfit"},
                   {"proc": other, "module": "engine.lab", "started": time.time() - AU.WEEKLY_STALE_S - 60}):
            origin, repo = _repo()
            proc = kw.pop("proc")
            _pid_file(repo, proc, **kw)
            _push(origin, "two")
            bindir, log = _systemctl()
            state = _update(repo, bindir)
            assert _restarts(log) == 1 and "restarted qellys" in state["note"], (kw, state)
    finally:
        other.kill(), other.wait()


def test_an_app_already_serving_the_pulled_code_clears_the_weekly_note():
    origin, repo = _repo()
    proc = _job()
    try:
        _pid_file(repo, proc)
        _push(origin, "two")
        bindir, log = _systemctl()
        _update(repo, bindir)
        assert _note(repo, "restart_pending.json")
        path = Path(repo, "data", "cache", "sweep.json")
        path.write_text(json.dumps({"handshake": 1, "pid": os.getpid(), "running": False,
                                    "started": time.time(), "commit": _g(repo, "rev-parse", "--short", "HEAD")}))
        state = _update(repo, bindir)
    finally:
        proc.kill(), proc.wait()
    assert state["note"] == "up to date" and _restarts(log) == 0, state
    assert _note(repo, "restart_pending.json") is None


def test_the_ceilings_line_up():
    assert AU.WEEKLY_WAIT_MAX_S > M.WEEKLY_JOB_TIMEOUT_S, "a whole job's hour fits inside the wait"
    assert AU.WEEKLY_STALE_S > M.WEEKLY_JOB_TIMEOUT_S
    assert M.RESTART_PENDING_TTL_S > AU.WEEKLY_WAIT_MAX_S, \
        "the app holds new jobs for as long as the updater may wait"
    assert AU.RESTART_PENDING[-1] == M.RESTART_PENDING_NAME
    assert AU.WEEKLY_PIDS == ("data", "cache") and M._child_pid_path("engine.lab").name == "weekly_lab.pid"


# --- the app ---------------------------------------------------------------------
def _scratch():
    d = Path(tempfile.mkdtemp())
    return d / "maintenance_state.json"


def _with_note(fn, note=None):
    """Run ``fn`` with the app's data/cache pointed at a scratch directory
    holding ``note`` as restart_pending.json."""
    cache = Path(tempfile.mkdtemp())
    if note is not None:
        (cache / M.RESTART_PENDING_NAME).write_text(json.dumps(note))
    saved = M._child_dir
    M._child_dir = lambda: cache
    try:
        return fn()
    finally:
        M._child_dir = saved


def test_the_app_reads_the_updaters_note_and_lets_a_stale_one_go():
    now = time.time()
    assert _with_note(M.updater_waiting) == ""
    assert _with_note(M.updater_waiting, {"commit": "f00dfeed", "since": now - 60}) == "f00dfeed"
    assert _with_note(M.updater_waiting, {"commit": "f00dfeed",
                                          "since": now - M.RESTART_PENDING_TTL_S - 5}) == "", \
        "an updater that died must not hold the fitters back for ever"
    assert _with_note(M.updater_waiting, {"since": now}) == ""


def test_a_held_job_starts_once_the_restart_lands_the_same_day_its_attempt_unspent():
    sp = _scratch()
    wed = dt.date(2026, 11, 4)
    state = {}
    lines = []
    M._hold(state, sp, "deep", wed, lines.append)
    M._hold(state, sp, "lab", wed, lines.append)
    saved = M._load_state(sp)
    assert saved["held"] == {"deep": "2026-11-04", "lab": "2026-11-04"}
    assert "deep_attempted" not in saved and "lab_attempted" not in saved, "the day's attempt is not spent"
    assert any("held" in ln for ln in lines)
    ran = []
    deep = lambda log: ran.append("deep wednesday") or ["deep started"]
    nxt = lambda log: ran.append("deep next") or ["next started"]
    lab = lambda log: ran.append("lab") or ["lab started"]
    # Still waiting: nothing starts.
    _with_note(lambda: M.launch_held(sp, wed, lambda *_: None, deep, nxt, lab),
               {"commit": "f00dfeed", "since": time.time()})
    assert ran == []
    # The restart has landed: each starts once, its attempt marked — one at
    # a time, since the two never share the box's one CPU (2026-11-06,
    # tests/test_the_refit_round_carries_over_and_the_heavy_jobs_take_turns.py):
    # the refit now, the Lab on the next cycle (these stand-ins leave no
    # process running, so nothing holds it longer).
    out = _with_note(lambda: M.launch_held(sp, wed, lambda *_: None, deep, nxt, lab))
    assert ran == ["deep wednesday"] and out == ["deep started"], (ran, out)
    out = _with_note(lambda: M.launch_held(sp, wed, lambda *_: None, deep, nxt, lab))
    assert ran == ["deep wednesday", "lab"] and out == ["lab started"], (ran, out)
    after = M._load_state(sp)
    assert after["deep_attempted"] == after["lab_attempted"] == "2026-11-04" and not after["held"]
    _with_note(lambda: M.launch_held(sp, wed, lambda *_: None, deep, nxt, lab))
    assert ran == ["deep wednesday", "lab"], "each held job starts once"


def test_a_hold_from_another_day_is_left_to_that_jobs_own_schedule():
    sp = _scratch()
    M._hold({}, sp, "deep", dt.date(2026, 11, 4), lambda *_: None)
    ran = []
    _with_note(lambda: M.launch_held(sp, dt.date(2026, 11, 5), lambda *_: None,
                                     lambda log: ran.append("w") or [], lambda log: ran.append("n") or [],
                                     lambda log: ran.append("l") or []))
    assert ran == [] and not M._load_state(sp)["held"]
    # A Thursday hold of the round's next run starts the next run, not Wednesday's set.
    M._hold({}, sp, "deep", dt.date(2026, 11, 5), lambda *_: None)
    _with_note(lambda: M.launch_held(sp, dt.date(2026, 11, 5), lambda *_: None,
                                     lambda log: ran.append("w") or [], lambda log: ran.append("n") or [],
                                     lambda log: ran.append("l") or []))
    assert ran == ["n"]


def test_the_chores_hold_rather_than_start_while_the_updater_waits():
    import inspect
    src = inspect.getsource(M)
    for start in ('state["deep_attempted"] = today.isoformat()\n            _save_state(state_path, state)\n'
                  '            try:\n                for line in _run_deep_refit(log):',
                  'for line in _continue_deep_refit(log):',
                  'for line in _run_lab(log):'):
        i = src.index(start)
        before = src[max(0, i - 700):i]
        assert "if updater_waiting():" in before and "_hold(state, state_path," in before, start
    run = inspect.getsource(M.run_if_due)
    assert run.index("fill_charts_if_owed(log, today=today)") < run.index("launch_held(state_path, today, log)") \
        < run.index("return False")


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
            traceback.print_exc(limit=4)
    print(f"\n{len(fns) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
