"""The weekly refit's round runs to its end, and the box's two hour-long jobs
take turns (engine/deepfit.run_round, _refit_sport; engine/maintenance
heavy_running, _hold, launch_held).

The live heartbeat, 6 November: the round of 4 November still owed nine
pieces after three runs; the NFL's recency dial ran its 45 minutes and the
run ended "nothing done this run; ... part-way: nfl (recency dial cut off
after 45 min)"; and four weekly jobs, the Lab (00:20), the refit (00:42),
board learning (00:58) and the bug scan (01:31), shared the box's one CPU.
On a machine to itself the NFL's dial takes about five minutes (77 seconds
a market, timed on a copy of the NFL's 2022-26 logs). Each Wednesday began a
new round whatever the last one owed, and took the dial's kept markets and
each sport's fitters done with it. What these hold:

  * a round that still owes pieces carries on past its own week, keeping
    each sport's fitters done and handing the dial the round's own first
    day; a new round begins once it is done, or once it is older than
    ROUND_CARRY_MAX_DAYS;
  * a dial run that ran its whole time and kept no market more is a stall:
    the first is tried again, the second in a row sets the dial aside (its
    last fit stands) and the sport's other fitters finish; a run that kept a
    market starts the count again, and a run cut short of its whole time is
    never a stall;
  * the Lab and the deep refit never run together: whichever would start
    second is held, the hold says why, and it starts the cycle after the
    other ends; of two held at once, one starts at a time.

Run directly:
`python3 tests/test_the_refit_round_carries_over_and_the_heavy_jobs_take_turns.py`
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import time as _t
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                  # noqa: E402
from engine import maintenance as M                              # noqa: E402

WED = dt.date(2026, 11, 4)
THU, FRI = WED + dt.timedelta(days=1), WED + dt.timedelta(days=2)
NEXT_WED = WED + dt.timedelta(days=7)
NEXT_THU, NEXT_FRI = NEXT_WED + dt.timedelta(days=1), NEXT_WED + dt.timedelta(days=2)


class _Fitters:
    """subprocess.run for the three fitters; every one adopts something."""
    def __init__(self):
        self.ran, self.cmds = [], []

    def __call__(self, cmd, **kw):
        self.ran.append(Path(cmd[1]).name)
        self.cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "  receptions: adopted 0.9\n", "")


def _round(path, today, fitters, rows=None):
    # The extras run in process and read the real stores: none here, so a
    # new round owes the sports alone.
    keep_rows, keep_run, keep_extras = D._row_counts, subprocess.run, D.EXTRAS
    D._row_counts = lambda db="data/history.db": dict(rows or {"nfl": 330_000})
    subprocess.run, D.EXTRAS = fitters, {}
    try:
        lines = D.run_round(db="unused", state_path=path, today=today, budget_s=3600)
    finally:
        D._row_counts, subprocess.run, D.EXTRAS = keep_rows, keep_run, keep_extras
    return lines, json.loads(path.read_text())


def _write(path, round_of, left, pieces=None):
    path.write_text(json.dumps({"round": round_of.isoformat(), "left": list(left),
                                "pieces": pieces or {}}))


# --- the round runs to its end ---------------------------------------------------
def test_an_unfinished_round_carries_on_past_its_week_and_keeps_what_it_did():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path, WED, ["nfl"], {"nfl": {"fitters_done": {"round": WED.isoformat(),
                                                         "done": ["recency dial"]}}})
    f = _Fitters()
    lines, st = _round(path, NEXT_THU, f)
    assert st["round"] == WED.isoformat(), ("last week's round carries on", st["round"])
    assert any("the round of 2026-11-04 carries on" in ln for ln in lines), lines
    assert f.ran == ["playerfit.py", "calibrate.py"], ("the dial it did is kept", f.ran)
    assert st["left"] == [] and st["pieces"]["nfl"]["done"] == NEXT_THU.isoformat()
    assert "round of 2026-11-04 complete" in lines[-1], lines[-1]
    # Done: the next run begins this week's round.
    f2 = _Fitters()
    lines, st = _round(path, NEXT_FRI, f2, rows={"nfl": 331_000})
    assert st["round"] == NEXT_WED.isoformat(), st["round"]
    assert any("the round of 2026-11-11 owes" in ln for ln in lines), lines
    assert f2.ran == ["formfit.py", "playerfit.py", "calibrate.py"], "a new round starts every fitter again"


def test_the_dial_is_handed_the_carried_rounds_own_first_day():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path, WED, ["nfl"])
    f = _Fitters()
    _round(path, NEXT_THU, f)
    dial = [c for c in f.cmds if Path(c[1]).name == "formfit.py"][0]
    assert dial[dial.index("--resume-after") + 1] == "2026-11-04", \
        ("the markets it fitted since 4 November are kept", dial)


def test_a_round_too_old_to_carry_gives_way_to_a_new_one():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    old = dt.date(2026, 10, 14)
    assert (NEXT_THU - old).days > D.ROUND_CARRY_MAX_DAYS
    _write(path, old, ["nfl"], {"nfl": {"fitters_done": {"round": old.isoformat(),
                                                         "done": ["recency dial"]}}})
    f = _Fitters()
    lines, st = _round(path, NEXT_THU, f)
    assert st["round"] == NEXT_WED.isoformat(), "nothing owed for ever holds every other fit back"
    assert f.ran == ["formfit.py", "playerfit.py", "calibrate.py"], f.ran
    assert not D._carries("not a date", NEXT_THU) and D._carries(WED.isoformat(), NEXT_THU)


def test_this_weeks_round_and_a_finished_one_are_as_before():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path, WED, [])
    lines, st = _round(path, NEXT_THU, _Fitters())
    assert st["round"] == NEXT_WED.isoformat(), "a finished round: this week's begins"
    assert not any("carries on" in ln for ln in lines), lines
    path2 = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path2, NEXT_WED, ["nfl"])
    lines, st = _round(path2, NEXT_THU, _Fitters())
    assert st["round"] == NEXT_WED.isoformat() and not any("carries on" in ln for ln in lines)


# --- a dial that keeps nothing has stalled ---------------------------------------
def _dial_cut(kept_after, deadline_s=2 * D.TIMEOUT_S):
    """`_refit_sport` for the NFL with the dial timing out on its whole time
    (or what is left of ``deadline_s``), the store holding two markets
    before and ``kept_after`` after."""
    now = [10_000.0]
    told, ran = [], []

    def fake_run(cmd, **kw):
        ran.append(Path(cmd[1]).name)
        if Path(cmd[1]).name == "formfit.py":
            now[0] += kw["timeout"]
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        now[0] += 60
        return subprocess.CompletedProcess(cmd, 0, "  receptions: adopted 0.9\n", "")
    counts = iter([2, kept_after])
    keep = subprocess.run, _t.monotonic, D._dial_kept
    subprocess.run, _t.monotonic = fake_run, (lambda: now[0])
    D._dial_kept = lambda sport, round_of, path=None: next(counts)
    try:
        lines, finished = D._refit_sport("nfl", deadline=now[0] + deadline_s, round_of=WED.isoformat(),
                                         on_done=lambda label, secs, status: told.append((label, status)))
    finally:
        subprocess.run, _t.monotonic, D._dial_kept = keep
    return lines, finished, told, ran


def test_a_dial_that_ran_its_whole_time_and_kept_nothing_more_has_stalled():
    lines, finished, told, ran = _dial_cut(kept_after=2)
    assert ("recency dial", "stalled") in told, told
    assert not finished, "the sport is not done"
    assert any("kept no market it had not kept before — stalled" in ln for ln in lines), lines
    # Settings kept, not markets (formfit.GridCheckpoint): a run that had to
    # start a market's grid afresh and ended with fewer than it found has
    # not moved either.
    _lines, _f, told, _r = _dial_cut(kept_after=1)
    assert ("recency dial", "stalled") in told, told


def test_a_dial_that_kept_a_market_or_was_cut_short_has_not():
    _lines, _f, told, _r = _dial_cut(kept_after=3)
    assert ("recency dial", "cut_off") in told and ("recency dial", "stalled") not in told, told
    _lines, _f, told, _r = _dial_cut(kept_after=2, deadline_s=0.5 * D.TIMEOUT_S)
    assert ("recency dial", "cut_off") in told and ("recency dial", "stalled") not in told, \
        ("a run that gave it half its time proves nothing", told)


def _fake_sport(statuses):
    """`_refit_sport` that reports ``statuses`` for the dial, one per run,
    and the other two fitters fine; the dial's skip is recorded."""
    seen = []

    def fake(sport, db, say=None, deadline=None, skip=(), on_done=None, **kw):
        seen.append(set(skip))
        if "recency dial" in skip:
            for label in ("player memory", "temperatures"):
                if label not in skip:
                    on_done(label, 60, "ok")
            return ["nfl fitted"], True
        on_done("player memory", 60, "ok")
        on_done("temperatures", 60, "ok")
        on_done("recency dial", 2700, statuses.pop(0))
        return ["nfl: the dial cut off"], False
    return fake, seen


def _round_with(path, today, fake):
    keep_rows, keep_sport, keep_extras = D._row_counts, D._refit_sport, D.EXTRAS
    D._row_counts = lambda db="data/history.db": {"nfl": 330_000}
    D._refit_sport, D.EXTRAS = fake, {}
    try:
        lines = D.run_round(db="unused", state_path=path, today=today, budget_s=D.DEEP_BUDGET_S)
    finally:
        D._row_counts, D._refit_sport, D.EXTRAS = keep_rows, keep_sport, keep_extras
    return lines, json.loads(path.read_text())


def test_the_second_stall_in_a_row_sets_the_dial_aside_and_the_sport_finishes():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path, WED, ["nfl"])
    fake, seen = _fake_sport(["stalled", "stalled"])
    lines, st = _round_with(path, THU, fake)
    e = st["pieces"]["nfl"]
    assert e["stalled"]["n"] == 1 and "recency dial" not in e["fitters_done"]["done"], e
    assert "stall 1 of 2" in lines[-1], lines[-1]
    lines, st = _round_with(path, FRI, fake)
    e = st["pieces"]["nfl"]
    assert "recency dial" in e["fitters_done"]["too_long"], e
    assert "recency dial set aside" in lines[-1], lines[-1]
    lines, st = _round_with(path, FRI + dt.timedelta(days=1), fake)
    assert "recency dial" in seen[-1], "set aside: not run again this round"
    assert st["left"] == [] and "stalled" not in st["pieces"]["nfl"], st["pieces"]["nfl"]


def test_a_run_that_moved_starts_the_count_again():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    _write(path, WED, ["nfl"])
    fake, _seen = _fake_sport(["stalled", "cut_off", "stalled"])
    _round_with(path, THU, fake)
    _l, st = _round_with(path, FRI, fake)
    assert "stalled" not in st["pieces"]["nfl"], "it kept a market: not stuck"
    _l, st = _round_with(path, FRI + dt.timedelta(days=1), fake)
    assert st["pieces"]["nfl"]["stalled"]["n"] == 1, st["pieces"]["nfl"]
    assert "recency dial" not in (st["pieces"]["nfl"]["fitters_done"].get("too_long") or [])


# --- the Lab and the refit take turns --------------------------------------------
def _scratch_cache():
    cache = Path(tempfile.mkdtemp())
    saved = M._child_dir
    M._child_dir = lambda: cache
    return cache, saved


def _a_job(module):
    """A live process whose command line names ``module``, with its pid file.

    Popen returns once the child's exec has closed the pipe it waits on,
    which on Linux is a moment before the kernel fills in the new command
    line; on a loaded gate (78, eight files at once) the check read an empty
    one and found no job running. So this waits until the command line says
    ``module``, as a job started long before any check always does."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", module])
    M._child_pid_path(module).write_text(json.dumps({"pid": proc.pid, "module": module,
                                                     "started": _t.time()}))
    for _ in range(200):
        if M._pid_runs(proc.pid, module):
            break
        _t.sleep(0.025)
    return proc


def test_heavy_running_names_the_other_job_by_its_live_pid_file():
    cache, saved = _scratch_cache()
    try:
        assert M.heavy_running() == ""
        proc = _a_job("engine.deepfit")
        try:
            assert M.heavy_running("lab") == "engine.deepfit"
            assert M.heavy_running("deep") == "", "a job is never held behind itself"
        finally:
            proc.kill()
            proc.wait()
        assert M.heavy_running("lab") == "", "a dead pid holds nothing"
    finally:
        M._child_dir = saved


def test_the_lab_waits_while_the_refit_runs_and_starts_the_cycle_after():
    cache, saved = _scratch_cache()
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    fri = dt.date(2026, 11, 6)
    proc = _a_job("engine.deepfit")
    try:
        lines = []
        M._hold({}, sp, "lab", fri, lines.append, behind=M.heavy_running("lab"))
        assert any("the deep refit is running" in ln and "never share the box's one CPU" in ln
                   for ln in lines), lines
        ran = []
        lab = lambda log: ran.append("lab") or ["lab started"]
        M.launch_held(sp, fri, lambda *_: None, lab_run=lab)
        assert ran == [] and M._load_state(sp)["held"] == {"lab": "2026-11-06"}, "still held"
    finally:
        proc.kill()
        proc.wait()
    try:
        M.launch_held(sp, fri, lambda *_: None, lab_run=lab)
        assert ran == ["lab"] and M._load_state(sp)["lab_attempted"] == "2026-11-06"
        assert not M._load_state(sp)["held"]
    finally:
        M._child_dir = saved


def test_of_two_held_jobs_one_starts_at_a_time():
    cache, saved = _scratch_cache()
    sp = Path(tempfile.mkdtemp()) / "maintenance_state.json"
    wed = dt.date(2026, 11, 4)
    try:
        state = {}
        M._hold(state, sp, "deep", wed, lambda *_: None)
        M._hold(state, sp, "lab", wed, lambda *_: None)
        ran = []
        deep = lambda log: ran.append("deep") or []
        lab = lambda log: ran.append("lab") or []
        M.launch_held(sp, wed, lambda *_: None, deep, deep, lab)
        assert ran == ["deep"] and M._load_state(sp)["held"] == {"lab": "2026-11-04"}, ran
        M.launch_held(sp, wed, lambda *_: None, deep, deep, lab)
        assert ran == ["deep", "lab"], ran
    finally:
        M._child_dir = saved


def test_every_place_that_starts_the_lab_or_the_refit_asks_first():
    import inspect
    src = inspect.getsource(M)
    for start in ('state["deep_attempted"] = today.isoformat()\n            _save_state(state_path, state)\n'
                  '            try:\n                for line in _run_deep_refit(log):',
                  'for line in _continue_deep_refit(log):',
                  'for line in _run_lab(log):'):
        i = src.index(start)
        assert "heavy_running(" in src[max(0, i - 700):i], start
    assert set(M.HEAVY_WEEKLY.values()) == {"engine.deepfit", "engine.lab"}


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - fails} tests passed." if not fails else f"\n{fails} of {len(fns)} failed.")
    sys.exit(1 if fails else 0)
