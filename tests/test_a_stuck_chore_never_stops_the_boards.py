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


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
