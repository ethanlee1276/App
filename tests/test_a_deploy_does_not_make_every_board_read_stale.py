"""A deploy no longer makes every board read stale.

Ethan, 2026-10-14, 12:42, a screenshot of the Status page: "Also everything
is stale". NFL 3 minutes old, then MLB 25, NBA 22, WNBA 22, NHL 20 and
college 36, all red. On this box a sweep of every board takes about half an
hour, so those ages were normal; the page's line was wrong.

The page calls a board late past twice the machine's median cycle (plus a
minute), never under its own floor. The median came from launch.py
`_CYCLE_S`, and two things broke it:

  * A SKIPPED CYCLE WAS TIMED. After every restart the startup build holds
    the build lock for about thirty minutes; the refresher, waking every
    minute, skipped and still timed itself at a fraction of a second. Thirty
    of those in a median of twenty put the line at the 8-minute floor.
  * THE TIMINGS DIED WITH THE PROCESS. Every deploy started from nothing;
    until two sweeps were timed the page used a 16-minute floor. Four pushes
    that afternoon kept it there.

And every pull restarted the site, the runbook's included; each restart
costs the boards a sweep. Now:

  * only a cycle that swept (or failed trying) is timed;
  * the startup build is timed as the sweep it is;
  * the heartbeat carries the timings (`cycles_s`) and the next process
    starts from them;
  * deploy/autoupdate.py pulls a docs- or tests-only change without a
    restart (code waiting from an earlier pull still restarts), and
    `launch.py --boards` says so instead of calling it a failed restart.

The refresher runs for real with its collaborators stubbed; the updater runs
as a script against real git repositories with a systemctl that records its
arguments.

Run directly: `python3 tests/test_a_deploy_does_not_make_every_board_read_stale.py`
"""
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import launch  # noqa: E402

SPEC = importlib.util.spec_from_file_location("autoupdate", ROOT / "deploy" / "autoupdate.py")
AU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AU)

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


# --- the refresher ------------------------------------------------------------------
class _Stop(Exception):
    pass


def _cycles(n, hold_lock=False, pending=False, wanted=False):
    """Run `_background_refresher` for ``n`` cycles with everything around
    it stubbed. Returns (the timings it kept, each cycle's `swept`)."""
    swepts, sleeps = [], [0]

    def sleep(_s):
        sleeps[0] += 1
        if sleeps[0] > n:
            raise _Stop()
    names = ("time", "_seed_cycles", "_kick_chores", "_chores_last_s", "_restart_wanted",
             "_note_sweep", "refresh_all", "_write_day_top_pick", "_checkpoint_wal",
             "_write_heartbeat")
    saved = {k: getattr(launch, k) for k in names}
    saved_cycles, saved_pending = list(launch._CYCLE_S), launch._RESTART_PENDING[0]
    launch.time = types.SimpleNamespace(sleep=sleep, time=time.time)
    launch._seed_cycles = lambda *a, **k: 0
    launch._kick_chores = lambda *a, **k: None
    launch._chores_last_s = lambda: {}
    launch._restart_wanted = lambda: wanted
    launch._note_sweep = lambda *a, **k: None
    launch.refresh_all = lambda quiet=False: None
    launch._write_day_top_pick = lambda: None
    launch._checkpoint_wal = lambda: None
    launch._write_heartbeat = lambda interval, swept="ran": swepts.append(swept)
    launch._RESTART_PENDING[0] = pending
    launch._CYCLE_S[:] = []
    held = launch._BUILD_LOCK.acquire(blocking=False) if hold_lock else False
    try:
        try:
            launch._background_refresher(60)
        except _Stop:
            pass
        return list(launch._CYCLE_S), swepts
    finally:
        if held:
            launch._BUILD_LOCK.release()
        for k, v in saved.items():
            setattr(launch, k, v)
        launch._CYCLE_S[:] = saved_cycles
        launch._RESTART_PENDING[0] = saved_pending


def test_a_cycle_skipped_behind_the_startup_build_is_not_timed():
    kept, swepts = _cycles(3, hold_lock=True)
    assert swepts == ["skipped — a build was already running"] * 3, swepts
    assert kept == [], f"a skip was timed as a cycle: {kept}"


def test_a_cycle_skipped_for_new_code_is_not_timed_either():
    kept, swepts = _cycles(2, pending=True)
    assert swepts == ["skipped — restarting into new code"] * 2 and kept == [], (swepts, kept)
    kept, swepts = _cycles(2, wanted=True)
    assert swepts == ["skipped — the updater restarts into new code"] * 2 and kept == [], (swepts, kept)


def test_a_cycle_that_swept_is_timed_as_before():
    kept, swepts = _cycles(2)
    assert swepts == ["ran", "ran"] and len(kept) == 2, (swepts, kept)


def test_the_startup_build_is_timed_as_the_sweep_it_is():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    chores = src[src.index("def _startup_chores"):]
    chores = chores[:chores.index("\n    threading.Thread(target=_startup_chores")]
    assert chores.index("refresh_all()") < chores.index("_note_cycle(time.time() - _swept_from)")
    assert chores.index("_swept_from = time.time()") < chores.index("refresh_all()")


# --- the timings outlive the restart ---------------------------------------------------
def _beat(**over):
    d = Path(tempfile.mkdtemp())
    beat = {"at_epoch": round(time.time()) - 600, "cycles_s": [1810.4, 1755.0, 1902.3]}
    beat.update(over)
    (d / "heartbeat.json").write_text(json.dumps(beat))
    return d / "heartbeat.json"


def _seed(path, now=None, start=()):
    saved = list(launch._CYCLE_S)
    launch._CYCLE_S[:] = list(start)
    try:
        n = launch._seed_cycles(path=path, now=now)
        return n, list(launch._CYCLE_S), launch._cycle_p50()
    finally:
        launch._CYCLE_S[:] = saved


def test_a_restart_starts_from_the_last_process_timings():
    n, kept, p50 = _seed(_beat())
    assert n == 3 and kept == [1810.4, 1755.0, 1902.3] and p50 == 1810.4, (n, kept, p50)


def test_a_heartbeat_a_day_old_or_from_before_the_field_seeds_nothing():
    assert _seed(_beat(at_epoch=round(time.time()) - 2 * 86400))[:2] == (0, [])
    # The old heartbeat's median is the one the skips polluted: never read.
    old = _beat(cycles_s=None, cycle_p50_s=0.4, cycle_s=0.3)
    assert _seed(old)[:2] == (0, []), "seeded from a median the skips had polluted"
    assert _seed(Path(tempfile.mkdtemp()) / "none.json")[:2] == (0, [])
    bad = Path(tempfile.mkdtemp()) / "heartbeat.json"
    bad.write_text("not json")
    assert _seed(bad)[:2] == (0, [])


def test_only_sane_timings_are_seeded_and_never_over_a_running_count():
    n, kept, _ = _seed(_beat(cycles_s=[1800, "x", -5, 0, True, 99999, 1700.04]))
    assert kept == [1800.0, 1700.0] and n == 2, kept
    n, kept, _ = _seed(_beat(), start=[42.0])
    assert n == 0 and kept == [42.0], "a process that has timed its own cycles keeps them"
    n, kept, _ = _seed(_beat(cycles_s=[float(i + 100) for i in range(40)]))
    assert n == launch._CYCLE_KEEP == len(kept), n


def test_the_heartbeat_carries_the_timings_for_the_next_process():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    saved_root, saved_cycles = launch.ROOT, list(launch._CYCLE_S)
    launch.ROOT = tmp
    launch._CYCLE_S[:] = [1700.0, 1800.0, 1900.0]
    try:
        launch._write_heartbeat(60)
    finally:
        launch.ROOT = saved_root
        launch._CYCLE_S[:] = saved_cycles
    beat = json.loads((tmp / "web" / "data" / "heartbeat.json").read_text())
    assert beat["cycles_s"] == [1700.0, 1800.0, 1900.0] and beat["cycle_p50_s"] == 1800.0, beat
    n, kept, p50 = _seed(tmp / "web" / "data" / "heartbeat.json")
    assert (n, p50) == (3, 1800.0), "the next process reads back what this one wrote"


def test_the_refresher_seeds_before_its_first_cycle():
    src = inspect.getsource(launch._background_refresher)
    assert src.index("_seed_cycles()") < src.index("while True:")


# --- the updater: a docs-only pull is not restarted into ------------------------------
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


def _push(origin, **files):
    for name, text in files.items():
        p = Path(origin, *name.split("__"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n")
    _g(origin, "add", "."), _g(origin, "commit", "-qm", "+".join(files))


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


def test_a_runbook_push_is_pulled_without_a_restart():
    origin, repo = _repo()
    _push(origin, docs__WHEN_YOU_ARE_HOME_md="step 88")
    bindir, log = _systemctl()
    state = _update(repo, bindir)
    assert Path(repo, "docs", "WHEN_YOU_ARE_HOME_md").exists(), "the docs are pulled"
    assert state["ok"] and "no restart" in state["note"] and _restarts(log) == 0, state


def test_tests_audit_and_a_top_level_readme_are_not_restarted_into_either():
    origin, repo = _repo()
    _push(origin, tests__test_x_py="x", audit__notes_md="y", **{"README.md": "z"})
    bindir, log = _systemctl()
    state = _update(repo, bindir)
    assert "no restart" in state["note"] and _restarts(log) == 0, state


def test_code_in_the_pull_restarts_as_before():
    origin, repo = _repo()
    _push(origin, docs__a_md="a", **{"f.txt": "two"})
    bindir, log = _systemctl()
    state = _update(repo, bindir)
    assert "restarted qellys" in state["note"] and _restarts(log) == 1, state
    # Markdown below the top level is not assumed inert: engine/ and deploy/ restart.
    origin, repo = _repo()
    _push(origin, deploy__notes_md="b")
    bindir, log = _systemctl()
    assert _restarts(log) == 0 and "restarted qellys" in _update(repo, bindir)["note"]
    assert _restarts(log) == 1


def test_code_waiting_from_an_earlier_pull_still_restarts_with_a_docs_pull_on_top():
    origin, repo = _repo()
    sweep = Path(repo, "data", "cache", "sweep.json")
    sweep.parent.mkdir(parents=True, exist_ok=True)
    sweep.write_text(json.dumps({"handshake": 1, "pid": os.getpid(), "running": True,
                                 "started": time.time() - 120, "finished": None, "commit": ""}))
    _push(origin, **{"f.txt": "code"})
    bindir, log = _systemctl()
    assert "waits for the board sweep" in _update(repo, bindir)["note"] and _restarts(log) == 0
    sweep.write_text(json.dumps({"handshake": 1, "pid": os.getpid(), "running": False,
                                 "started": time.time() - 120, "finished": time.time(), "commit": ""}))
    _push(origin, docs__b_md="docs on top")
    state = _update(repo, bindir)
    assert _restarts(log) == 1 and "restarted qellys" in state["note"], state


def test_git_that_cannot_say_means_a_restart():
    origin, repo = _repo()
    assert AU._needs_restart(repo, "deadbeef", "cafebabe") is True
    assert AU._needs_restart(repo, "HEAD", "HEAD") is True, "no path named: restart, as before"


# --- one rule, in both places ---------------------------------------------------------
PATHS = ("docs/X.md", "docs/research/claims.json", "tests/test_x.py", "audit/work/a.js", "README.md",
         "CHANGELOG.MD", "launch.py", "engine/x.py", "engine/README.md", "deploy/notes.md",
         "web/js/app.js", "docsy/x.md", "", "  ")


def test_launch_and_the_updater_use_the_same_rule():
    assert launch.NO_RESTART == AU.NO_RESTART
    for p in PATHS:
        assert launch._runs_nothing(p) == AU._runs_nothing(p), p
    assert [p for p in PATHS if AU._runs_nothing(p)] == [
        "docs/X.md", "docs/research/claims.json", "tests/test_x.py", "audit/work/a.js", "README.md",
        "CHANGELOG.MD"]


def test_boards_says_a_docs_only_gap_is_not_a_failed_restart():
    saved = launch._git
    try:
        launch._git = lambda *a, **k: (True, "docs/WHEN_YOU_ARE_HOME.md\ntests/test_x.py")
        assert launch._restart_needed_for("aaa", "bbb") is False
        launch._git = lambda *a, **k: (True, "docs/x.md\nlaunch.py")
        assert launch._restart_needed_for("aaa", "bbb") is True
        launch._git = lambda *a, **k: (False, "fatal: bad revision")
        assert launch._restart_needed_for("aaa", "bbb") is True
        launch._git = lambda *a, **k: (True, "")
        assert launch._restart_needed_for("aaa", "bbb") is True
    finally:
        launch._git = saved
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("is on disk but not running")
    block = src[i - 300:i + 400]
    assert "_restart_needed_for(served, disk)" in block and "nothing to restart into" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
