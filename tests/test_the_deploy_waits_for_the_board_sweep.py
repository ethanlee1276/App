"""A push no longer kills the board sweep in progress: the restart waits for it.

Ethan, 2026-10-14: "There's no most likely bets. There's no edge bets ...
make sure all our new pushes are being pushed correctly." The box's
updater (deploy/autoupdate.py, root, every five minutes) restarted the
unit the moment a push landed, and a restart kills the sweep and every
build in it. Pushes twenty to seventy minutes apart meant the boards late
in the sweep never finished, and past an hour old the page takes a board's
picks off.

Now the app writes data/cache/sweep.json (launch.py `_note_sweep`): is a
sweep running, since when, on which commit. The updater pulls as before —
the page and the trimmed shell are served new at once — but while a sweep
runs it holds the restart and leaves data/cache/restart_wanted.json, which
stops the app starting another sweep (`_restart_wanted`); the next run
after the sweep ends restarts. It never waits past RESTART_WAIT_MAX_S, a
sweep whose writer is gone or that has run past SWEEP_STALE_S is not
waited on, and an app too old to write the file restarts at once.

The updater half runs the real script against real git repositories with a
systemctl that records its arguments; the app half calls launch.py's own
functions on a scratch ROOT.

Run directly: `python3 tests/test_the_deploy_waits_for_the_board_sweep.py`
"""
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

import launch  # noqa: E402

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


def _sweep(repo, running=True, started=None, pid=None, commit="", handshake=1):
    path = Path(repo, "data", "cache", "sweep.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"handshake": handshake, "pid": os.getpid() if pid is None else pid,
                                "running": running, "started": time.time() - 120 if started is None else started,
                                "finished": None, "commit": commit}))


def _want(repo):
    p = Path(repo, "data", "cache", "restart_wanted.json")
    return json.loads(p.read_text()) if p.exists() else None


def _restarts(log):
    return open(log).read().count("restart qellys") if os.path.exists(log) else 0


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# --- the updater -----------------------------------------------------------------
def test_an_app_that_does_not_say_is_restarted_at_once_as_before():
    origin, repo = _repo()
    _push(origin, "two")
    bindir, log = _systemctl()
    state = _update(repo, bindir)
    assert state["ok"] and "restarted qellys" in state["note"] and _restarts(log) == 1, state
    assert _want(repo) is None


def test_new_code_waits_for_the_sweep_in_progress_then_restarts_when_it_ends():
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    state = _update(repo, bindir)
    head = _g(repo, "rev-parse", "--short", "HEAD")
    assert Path(repo, "f.txt").read_text() == "two\n", "the code is pulled at once"
    assert _restarts(log) == 0, "restarted in the middle of a sweep"
    assert state["ok"] and "waits for the board sweep" in state["note"], state
    want = _want(repo)
    assert want and want["commit"] == head, want
    # Still sweeping five minutes later: still waiting, the clock not reset.
    again = _update(repo, bindir)
    assert _restarts(log) == 0 and "waits for the board sweep" in again["note"], again
    assert _want(repo)["since"] == want["since"]
    # The sweep ends: the next run restarts and clears the request.
    _sweep(repo, running=False)
    done = _update(repo, bindir)
    assert _restarts(log) == 1 and "restarted qellys" in done["note"], done
    assert _want(repo) is None


def test_a_second_push_while_waiting_keeps_the_first_wait():
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    _update(repo, bindir)
    first = _want(repo)
    _push(origin, "three")
    _update(repo, bindir)
    second = _want(repo)
    assert _restarts(log) == 0 and second["since"] == first["since"]
    assert second["commit"] == _g(repo, "rev-parse", "--short", "HEAD") != first["commit"]


def test_the_wait_has_a_ceiling():
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    _update(repo, bindir)
    want = _want(repo)
    want["since"] -= AU.RESTART_WAIT_MAX_S + 60
    Path(repo, "data", "cache", "restart_wanted.json").write_text(json.dumps(want))
    state = _update(repo, bindir)
    assert _restarts(log) == 1 and "restarted qellys after waiting" in state["note"], state


def test_a_sweep_whose_writer_is_gone_or_that_ran_too_long_is_not_waited_on():
    for kw in ({"pid": _dead_pid()}, {"started": time.time() - AU.SWEEP_STALE_S - 60}):
        origin, repo = _repo()
        _sweep(repo, running=True, **kw)
        _push(origin, "two")
        bindir, log = _systemctl()
        state = _update(repo, bindir)
        assert _restarts(log) == 1 and "restarted qellys" in state["note"], (kw, state)


def test_an_app_already_serving_the_pulled_code_clears_the_request():
    origin, repo = _repo()
    _sweep(repo, running=True)
    _push(origin, "two")
    bindir, log = _systemctl()
    _update(repo, bindir)
    # It restarted on its own meanwhile (a crash, a hand restart) and now
    # sweeps on the new commit: nothing is left to wait for.
    _sweep(repo, running=True, commit=_g(repo, "rev-parse", "--short", "HEAD"))
    state = _update(repo, bindir)
    assert state["ok"] and state["note"] == "up to date" and _restarts(log) == 0, state
    assert _want(repo) is None


def test_the_ceilings_line_up():
    assert AU.RESTART_WAIT_MAX_S < launch.RESTART_WANT_TTL_S, \
        "the app must hold its sweeps for as long as the updater may wait"
    assert AU.RESTART_WAIT_MAX_S <= launch.RESTART_MAX_WAIT_S, "no longer than the app's own updater ever waited"
    assert AU.SWEEP_STATE[-1] == launch.SWEEP_STATE_NAME and AU.RESTART_WANT[-1] == launch.RESTART_WANT_NAME


# --- the app ---------------------------------------------------------------------
def _scratch_root():
    tmp = Path(tempfile.mkdtemp())
    saved = launch.ROOT
    launch.ROOT = tmp
    return tmp, saved


def test_the_app_says_when_a_sweep_runs_and_when_it_ended():
    tmp, saved = _scratch_root()
    try:
        launch._note_sweep(True)
        on = json.loads((tmp / "data" / "cache" / "sweep.json").read_text())
        time.sleep(0.05)
        launch._note_sweep(False)
        off = json.loads((tmp / "data" / "cache" / "sweep.json").read_text())
    finally:
        launch.ROOT = saved
    assert on["handshake"] == 1 and on["running"] is True and on["pid"] == os.getpid()
    assert on["commit"] == launch._running_commit() and on["finished"] is None
    assert off["running"] is False and off["started"] == on["started"] and off["finished"] >= on["started"]


def test_the_app_holds_its_sweeps_only_for_new_code_and_not_for_ever():
    tmp, saved = _scratch_root()
    mine = launch._running_commit()
    want = tmp / "data" / "cache" / "restart_wanted.json"
    want.parent.mkdir(parents=True)
    try:
        assert launch._restart_wanted() == "", "no request, no hold"
        want.write_text(json.dumps({"commit": "f00dfeed", "since": time.time() - 60}))
        assert launch._restart_wanted() == "f00dfeed"
        want.write_text(json.dumps({"commit": mine, "since": time.time()}))
        assert launch._restart_wanted() == "", "the code already running is not new"
        want.write_text(json.dumps({"commit": "f00dfeed", "since": time.time() - launch.RESTART_WANT_TTL_S - 5}))
        assert launch._restart_wanted() == "", "an old request nobody acted on stops holding the boards"
        want.write_text("not json")
        assert launch._restart_wanted() == ""
    finally:
        launch.ROOT = saved


def test_the_loop_skips_a_sweep_while_a_restart_is_wanted_and_marks_every_sweep():
    import inspect
    ref = inspect.getsource(launch._background_refresher)
    assert ref.index("_RESTART_PENDING[0]") < ref.index("_restart_wanted()") \
        < ref.index("_BUILD_LOCK.acquire(blocking=False)")
    lock = ref.index("_BUILD_LOCK.acquire(blocking=False)")
    assert ref.index("_note_sweep(True)", lock) < ref.index("refresh_all(quiet=True)", lock) \
        < ref.index("_note_sweep(False)", lock) < ref.index("_BUILD_LOCK.release()", lock)
    main = inspect.getsource(launch.main)
    start = main[main.index("def _startup_chores"):]
    assert start.index("_note_sweep(True)") < start.index("refresh_all()") < start.index("_note_sweep(False)")


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
