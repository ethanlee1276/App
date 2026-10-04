"""A chore that will not come back must never stop the boards.

Ethan, 2026-10-04, 4:26 in the morning: every board on the status page
"rebuilt 4 hours ago", NFL through the injury board, all red. The boards
had stopped together at the first cycle of the new day — the cycle that
runs the daily chores, which ran INSIDE the board loop, ahead of the sweep.
Checks, one rule each: the chores run on their own thread and the caller
does not wait for them; a second kick while one is running starts nothing;
a chore past the stuck mark publishes the line it is waiting on; the status
page says so; a pulled update waits for the build in progress instead of
abandoning it, and gives up waiting at its ceiling; the refresher starts no
sweep while an update waits; the watchdog sees a loop with no step landing.
On the box each lane is a niced child process, killed at its ceiling and
rested before it runs again; a fitter it started stays guarded after it
exits.

Run directly: `python3 tests/test_a_stuck_chore_never_stops_the_boards.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import launch                                                        # noqa: E402


def _wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_a_hanging_chore_runs_on_its_own_thread_and_says_where_it_is_stuck():
    gate = threading.Event()
    ran = []

    def hangs_in_ingest():
        ran.append("maintenance")
        gate.wait(10)                                   # the chore that will not come back

    saved = (launch._run_maintenance, launch._run_autosettle, launch._run_doctor)
    launch._run_maintenance = hangs_in_ingest
    launch._run_autosettle = lambda force=False: ran.append(f"settle force={force}")
    launch._run_doctor = lambda: ran.append("doctor")
    try:
        t0 = time.time()
        assert launch._kick_chores() == {"daily": "started", "settle": "started"}
        assert time.time() - t0 < 1.0, "the board loop must not wait on the chores"
        assert _wait_for(lambda: launch._LANES["daily"]["step"] == "maintenance")
        # The settle is NOT held behind the stuck daily pass.
        assert _wait_for(lambda: "settle force=False" in ran and launch._LANES["settle"]["step"] is None)
        assert launch._kick_chores() == {"daily": "still running", "settle": "started"}, \
            "a lane still running is left to finish; the free one runs again"
        st = launch._chores_status()
        assert st["daily"]["step"] == "maintenance" and st["daily"]["stuck"] is False
        later = time.time() + launch.CHORES_STUCK_S + 60
        st = launch._chores_status(now=later)
        assert st["daily"]["stuck"] is True and st["settle"]["stuck"] is False
        assert any("hangs_in_ingest" in ln or "gate.wait" in ln for ln in st["daily"]["stack"]), st["daily"]["stack"]
        gate.set()
        assert _wait_for(lambda: launch._LANES["daily"]["step"] is None and launch._LANES["daily"]["done_at"])
        assert ran[0] == "maintenance" and "doctor" in ran
        assert set(launch._chores_last_s()) == {"maintenance", "autosettle", "doctor"}
    finally:
        gate.set()
        launch._run_maintenance, launch._run_autosettle, launch._run_doctor = saved


def test_the_board_loop_and_the_startup_kick_the_chores_and_the_heartbeat_carries_them():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    refresher = src[src.index("def _background_refresher("):]
    refresher = refresher[:refresher.index("\n\n\n")]
    assert "_kick_chores()" in refresher
    for inline in ("_run_maintenance()", "_run_autosettle()", "_run_doctor()"):
        assert inline not in refresher, f"{inline} back in the board loop"
    assert "_kick_chores(force_settle=True)" in src
    assert '"chores": _chores_status()' in src


def test_a_pulled_update_waits_for_the_build_in_progress():
    restarts, naps = [], []
    launch._BUILD_LOCK.acquire()                         # a sweep is running
    try:
        def release_after_two_naps(_s):
            naps.append(_s)
            if len(naps) == 2:
                launch._BUILD_LOCK.release()
        got = launch._restart_when_idle(max_wait=3600, poll=1, sleep=release_after_two_naps,
                                        restart=lambda: restarts.append("execv"))
    finally:
        if launch._BUILD_LOCK.locked():
            launch._BUILD_LOCK.release()
    assert got == "restarted" and restarts == ["execv"] and len(naps) == 2
    assert launch._RESTART_PENDING[0] is False
    assert not launch._BUILD_LOCK.locked(), "the lock is given back if the restart returns"


def test_a_wedged_build_does_not_hold_a_fix_back_forever():
    clock = [1000.0]
    launch._BUILD_LOCK.acquire()
    try:
        def tick(_s):
            clock[0] += 600
        got = launch._restart_when_idle(max_wait=1800, poll=600, sleep=tick, now=lambda: clock[0],
                                        restart=lambda: None)
    finally:
        launch._BUILD_LOCK.release()
    assert got == "forced" and launch._RESTART_PENDING[0] is False


def test_no_sweep_starts_while_an_update_waits_and_the_updater_uses_the_wait():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    refresher = src[src.index("def _background_refresher("):]
    refresher = refresher[:refresher.index("\n\n\n")]
    assert refresher.index("_RESTART_PENDING[0]") < refresher.index("_BUILD_LOCK.acquire(blocking=False)")
    upd = src[src.index("def _auto_updater("):]
    upd = upd[:upd.index("\n\n\n")]
    assert "_restart_when_idle()" in upd and "_restart_into_new_code()" not in upd


def test_the_watchdog_sees_a_loop_where_no_step_lands():
    saved = launch._PROGRESS_AT[0]
    try:
        launch._PROGRESS_AT[0] = time.time() - launch.LOOP_STUCK_S - 60
        assert launch._loop_wedged()
        launch._note_progress()
        assert not launch._loop_wedged()
    finally:
        launch._PROGRESS_AT[0] = saved
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    ra = src[src.index("def refresh_all("):]
    assert "_note_progress()" in ra[:ra.index("with _isolated(")], "every board step marks progress"
    assert "target=_loop_watchdog" in src and "faulthandler.dump_traceback(all_threads=True)" in src


def test_the_nightly_nhl_catch_up_stops_at_its_budget_and_resumes_later():
    import datetime as dt
    from engine import maintenance as M
    clock = [0.0]
    seen = []

    def slow_ingest(day):                             # every day costs five minutes
        seen.append(day)
        clock[0] += 300
        return {"games": 2, "player_logs": 40, "skipped": []}

    lines = []
    g, l, stopped = M.nhl_catch_up(slow_ingest, dt.date(2026, 8, 20), dt.date(2026, 10, 3), lines.append,
                                   budget_s=1200, clock=lambda: clock[0])
    assert len(seen) == 5 and stopped == "2026-08-25", (seen, stopped)
    assert g == 10 and l == 200 and "resumes on the next run" in lines[-1]
    clock[0] = 0.0
    g, l, stopped = M.nhl_catch_up(slow_ingest, dt.date(2026, 10, 1), dt.date(2026, 10, 3), lines.append,
                                   budget_s=1200, clock=lambda: clock[0])
    assert stopped is None and g == 6, "a short window finishes inside the budget"
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert "nhl_catch_up(\n                    lambda day: _nhl.ingest_day(hconn2, day)" in src


def test_the_status_page_says_the_chore_is_stuck_and_where():
    node = shutil.which("node")
    if not node:
        return
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function loopRowsHTML(")
    fn = app[i:app.index("\nfunction ", i + 10)]
    j = app.index("function ageText(")
    age = app[j:app.index("\nfunction ", j + 10)]
    hb = {"at_epoch": 1000, "cycle_p50_s": 300,
          "chores": {"daily": {"step": "maintenance", "running_s": 14400, "stuck": True,
                               "stack": ['File "engine/maintenance.py", line 1638, in run_if_due',
                                         "res = _nhl.ingest_day(hconn2, d.isoformat())"]},
                     "settle": {"step": None, "done_epoch": 1000 + 4 * 3600 - 120, "stuck": False}}}
    prog = ("const escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n" + age + "\n" + fn
            + f"\nconsole.log(loopRowsHTML({json.dumps(hb)}, 1000 + 4 * 3600));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    html = out.stdout
    assert "Refresh loop" in html and "st-bad" in html, "a loop four hours quiet reads red"
    assert "Daily chores" in html and "stuck in maintenance" in html and "ingest_day" in html
    assert "Settling" in html and "idle · last finished" in html


def test_on_the_box_a_lane_is_a_niced_child_that_is_killed_at_its_ceiling():
    # Ethan, an hour after the thread fix: "site is still not working". A
    # thread shares the server's CPU priority, memory and interpreter and can
    # never be stopped; a child process can.
    d = tempfile.mkdtemp()
    script = ("import json, os, sys, time\n"
              f"p = {os.path.join(d, 'chores_daily.json')!r}\n"
              "open(p, 'w').write(json.dumps({'pid': os.getpid(), 'step': 'maintenance', "
              "'since': time.time(), 'last_s': {}}))\n"
              "print('nice', os.nice(0), flush=True)\n"
              "time.sleep(60)\n")
    saved = (launch._chores_in_process, launch._chore_cmd, launch.CHORE_STATE_DIR, dict(launch.CHORE_TIMEOUT_S))
    launch._chores_in_process = lambda: False
    launch._chore_cmd = lambda arg: [sys.executable, "-c", script, arg]
    launch.CHORE_STATE_DIR = launch.Path(d)
    launch.CHORE_TIMEOUT_S["daily"] = 3
    try:
        t0 = time.time()
        st = {"last_s": {}}
        launch._LANES["daily"]["proc"] = None
        out = subprocess.run([sys.executable, "-c", "pass"])            # warm the interpreter cache
        assert out.returncode == 0
        launch._lane_child("daily", False, st)
        took = time.time() - t0
        assert 3 <= took < 30, f"killed at the ceiling, not left to run ({took:.1f}s)"
        assert st["proc"].returncode is not None and st["proc"].returncode != 0
        # While a child runs, the status reads the step the CHILD reports.
        launch._LANES["daily"].update(proc=st["proc"], step="starting", since=time.time())
        assert launch._chores_status()["daily"]["step"] == "maintenance"
        # Killed, it rests: a daily pass that never marked the day done must
        # not start straight back into whatever hung it.
        assert st["rest_until"] > time.time() + launch.CHORE_REST_S - 60
        launch._LANES["daily"].update(proc=None, step=None, since=None, rest_until=st["rest_until"])
        settle_saved = launch._LANES["settle"].get("rest_until")
        launch._LANES["settle"]["rest_until"] = time.time() + 600
        try:
            assert launch._kick_chores() == {"daily": "resting after a timeout",
                                             "settle": "resting after a timeout"}
            assert "resting_until_epoch" in launch._chores_status()["daily"]
        finally:
            launch._LANES["settle"]["rest_until"] = settle_saved
    finally:
        launch._LANES["daily"].update(proc=None, step=None, since=None, rest_until=None)
        (launch._chores_in_process, launch._chore_cmd, launch.CHORE_STATE_DIR) = saved[:3]
        launch.CHORE_TIMEOUT_S.clear()
        launch.CHORE_TIMEOUT_S.update(saved[3])
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _lane_child("):src.index("def _lane_run(")]
    assert "os.nice(10)" in body and "start_new_session=True" in body and "os.killpg" in body


def test_the_child_runs_its_steps_says_what_it_did_and_cleans_up():
    d = tempfile.mkdtemp()
    ran = []
    saved = (launch._run_autosettle, launch.CHORE_STATE_DIR)
    launch._run_autosettle = lambda force=False: ran.append(force)
    launch.CHORE_STATE_DIR = launch.Path(d)
    try:
        assert launch.chore_child("settle", force_settle=True) == 0
    finally:
        launch._run_autosettle, launch.CHORE_STATE_DIR = saved
    assert ran == [True]
    state = json.loads(open(os.path.join(d, "chores_settle.json")).read())
    assert state["step"] is None and "autosettle" in state["last_s"]
    assert not os.path.exists(os.path.join(d, "chores_settle.stack")), "no stack left behind when it finished"
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    main = src[src.index("def main() -> None:"):]
    assert main.index('if "--chore" in argv:') < main.index("serve_forever"), "a chore child never starts a server"


def test_a_fitter_started_by_an_exited_chore_is_still_guarded_and_cut_off():
    from engine import maintenance as M
    d = tempfile.mkdtemp()
    saved = (M._child_dir, M._child_log_path)
    M._child_dir = lambda: launch.Path(d)
    M._child_log_path = lambda module: launch.Path(d) / f"weekly_{module.rsplit('.', 1)[-1]}.log"
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "engine.fakefit"],
                            start_new_session=True)
    # Until the child has exec'd, /proc shows the parent's command line; a
    # loaded machine can ask in that window, so wait for the real one.
    assert _wait_for(lambda: M._pid_runs(live.pid, "engine.fakefit"), timeout=10)
    try:
        with open(os.path.join(d, "weekly_fakefit.pid"), "w") as fh:
            json.dump({"pid": live.pid, "module": "engine.fakefit", "started": time.time()}, fh)
        msg = M._spawn_module("engine.fakefit", print)
        assert "still running" in msg[0] and "engine.fakefit" not in M._CHILDREN, msg
        assert M.reap_children(log=lambda *_: None) == [], "a job inside its ceiling is left alone"
        out = M.reap_children(log=lambda *_: None, now=time.time() + M.WEEKLY_JOB_TIMEOUT_S + 60)
        assert any("cut off" in ln for ln in out), out
        assert live.wait(timeout=10) != 0
        with open(os.path.join(d, "weekly_gonefit.pid"), "w") as fh:
            json.dump({"pid": live.pid, "module": "engine.gonefit", "started": time.time() - 120}, fh)
        out = M.reap_children(log=lambda *_: None)
        assert any("engine.gonefit: finished" in ln for ln in out), out
        assert not os.listdir(d) or all(not f.endswith(".pid") for f in os.listdir(d))
    finally:
        M._child_dir, M._child_log_path = saved
        if live.poll() is None:
            live.kill()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
