"""The settle pass learns at most hourly and says where its time went
(engine/maintenance.settle_open, LEARN_EVERY_S, LAST_SETTLE_PHASES;
launch._lane_steps_run, _chores_status).

The heartbeat, Saturday 7 November: one settle pass at 571 seconds (97 in
September), every SETTLE_EVERY_S, so the settle child ran back to back
beside the board builds and the weekly refit on the box's one CPU. On every
pass that graded anything it refitted its learners in line: the loss
patterns, the journal fitters, the selection haircut, the correlation
priors, the game-line calibration, the hypotheses. What these hold:

  * a pass that grades learns when an hour has passed since the last
    learning; a grading pass inside the hour does not, and leaves the
    grade owed; the first pass past the hour learns from it, even one that
    grades nothing, even one with nothing left open;
  * grades still land and the record still exports on the pass that makes
    them, learning or not;
  * the pass records what it spent by phase, what it graded and whether it
    learned; the lane carries that to the heartbeat (chores.settle.phases).

Run directly: `python3 tests/test_the_settle_pass_learns_hourly_and_says_where_its_time_went.py`
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance as M                               # noqa: E402

TODAY = dt.date(2026, 11, 7)


class MP:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, val):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)

    def undo(self):
        for obj, name, val in reversed(self._undo):
            setattr(obj, name, val)


def _journal(open_days):
    from engine import ledger
    conn = ledger.connect(":memory:")
    for d in open_days:
        conn.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                     "VALUES ('mlb', ?, ?, 'total_bases', 'open', 'main')", (d, "P" + d))
    conn.commit()
    return conn


def _stub(mp, calls, box):
    """The settle pass offline: one journal (``box["lconn"]``), a grade count
    (``box["settled"]``), and every learner recording that it ran."""
    from engine import corrfit, gamecal, hypotheses, ingest, journalfit, lab, ledger
    from engine import db, losspatterns, prose, selectionfit
    mp.setattr(ledger, "connect", lambda path=None: box["lconn"])
    mp.setattr(db, "connect", lambda path=None: None)
    mp.setattr(ingest, "ingest_mlb_results",
               lambda conn, s, e, with_logs=True, progress=None: calls.append("ingest") or {"games": 4})
    mp.setattr(ledger, "settle_from_history",
               lambda conn, h, sport=None: calls.append("grade") or box["settled"])
    mp.setattr(ledger, "export_json", lambda c, p: calls.append("export"))
    mp.setattr(losspatterns, "refresh", lambda c: calls.append("learn") or {"closed": []})
    mp.setattr(journalfit, "refresh",
               lambda c: {"temperatures": {"fitted": []}, "memory": {"fitted": []}})
    mp.setattr(selectionfit, "refresh", lambda c: {"pooled": {}, "sports": {}})
    mp.setattr(selectionfit, "bands", lambda c: [])
    mp.setattr(selectionfit, "band_lines", lambda b: [])
    mp.setattr(corrfit, "refresh", lambda h: {"adopted": []})
    mp.setattr(gamecal, "refresh", lambda h: {"adopted": []})
    mp.setattr(hypotheses, "retest", lambda c: {"hypotheses": []})
    for name in ("nightly", "weekly", "weekly_lab"):
        mp.setattr(prose, name, lambda c, log: None)
    mp.setattr(M, "_run_board_learning", lambda l, h, log: [])
    mp.setattr(lab, "_due", lambda path, today: False)


def _pass(state, now, force=True):
    return M.settle_open(log=lambda *_: None, state_path=state, today=TODAY,
                         now=now, force=force)


def test_a_grading_pass_learns_once_an_hour_and_never_misses_a_grade():
    mp, calls = MP(), []
    box = {"lconn": _journal([TODAY.isoformat()]), "settled": 3}
    _stub(mp, calls, box)
    try:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "m.json"
            assert _pass(state, 1000.0) == 3
            assert calls.count("learn") == 1 and "export" in calls
            # Five minutes on, grading again: graded and exported, not learned.
            calls.clear()
            assert _pass(state, 1000.0 + M.SETTLE_EVERY_S + 1) == 3
            assert "grade" in calls and "export" in calls and "learn" not in calls
            assert M._read_state(state).get("learn_owed") is True
            # Past the hour, grading nothing: the owed grade is learned from.
            box["settled"] = 0
            calls.clear()
            _pass(state, 1000.0 + M.LEARN_EVERY_S + 1)
            assert calls.count("learn") == 1
            saved = M._read_state(state)
            assert saved.get("learn_owed") is False
            assert saved.get("last_learn_ts") == 1000.0 + M.LEARN_EVERY_S + 1
            # Nothing owed: the next hour passes without learning.
            calls.clear()
            _pass(state, 1000.0 + 2 * M.LEARN_EVERY_S + 2)
            assert "learn" not in calls
    finally:
        mp.undo()


def test_an_owed_grade_is_learned_even_when_nothing_is_left_open():
    mp, calls = MP(), []
    empty = _journal([])            # before the stub: _journal opens through ledger.connect
    box = {"lconn": _journal([TODAY.isoformat()]), "settled": 2}
    _stub(mp, calls, box)
    try:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "m.json"
            _pass(state, 1000.0)                                   # learns
            _pass(state, 1000.0 + M.SETTLE_EVERY_S + 1)            # owed
            box["lconn"] = empty                                   # all settled now
            calls.clear()
            _pass(state, 1000.0 + M.LEARN_EVERY_S + 5)
            assert "grade" not in calls, "nothing open: nothing graded"
            assert calls.count("learn") == 1, calls
            assert M.LAST_SETTLE_PHASES["learned"] is True
    finally:
        mp.undo()


def test_the_pass_says_where_its_time_went():
    mp, calls = MP(), []
    box = {"lconn": _journal([TODAY.isoformat()]), "settled": 4}
    _stub(mp, calls, box)
    try:
        with tempfile.TemporaryDirectory() as td:
            _pass(Path(td) / "m.json", 1000.0)
    finally:
        mp.undo()
    ph = dict(M.LAST_SETTLE_PHASES)
    for k in ("prep", "ingest", "grade", "desk", "resettle", "parlays", "learn", "export"):
        assert k in ph and ph[k] >= 0.0, (k, ph)
    assert ph["graded"] == 4 and ph["learned"] is True
    assert ph["at"].startswith(dt.datetime.fromtimestamp(1000.0).date().isoformat())


def test_the_lane_carries_the_phases_to_the_heartbeat():
    import launch
    mp = MP()
    seen = {"prep": 0.4, "ingest": 61.0, "learn": 402.5, "graded": 9, "learned": True}

    def fake_autosettle(force=False):
        M.LAST_SETTLE_PHASES.clear()
        M.LAST_SETTLE_PHASES.update(seen)
    mp.setattr(launch, "_run_autosettle", fake_autosettle)
    st = {"step": None, "since": None, "last_s": {}}
    try:
        launch._lane_steps_run("settle", False, st)
        assert st["phases"] == seen and "autosettle" in st["last_s"]
        lane = launch._LANES["settle"]
        mp.setattr(launch, "_LANES", dict(launch._LANES, settle=dict(lane, phases=seen)))
        assert launch._chores_status()["settle"]["phases"] == seen
    finally:
        mp.undo()


def test_the_learners_still_live_in_the_settle_pass_and_are_due_hourly():
    import inspect
    src = inspect.getsource(M.settle_open)
    for name in ("losspatterns.refresh(lconn)", "journalfit.refresh(lconn)",
                 "selectionfit.refresh(lconn)", "corrfit.refresh(hconn)",
                 "gamecal.refresh(hconn)", "hypotheses.retest(lconn)",
                 "_run_board_learning(lconn, hconn, log)"):
        assert name in src, name
    assert src.count("_learn_due(state, now)") == 2, "the grading path and the nothing-open path"
    assert M.LEARN_EVERY_S == 3600 and M.LEARN_EVERY_S > M.SETTLE_EVERY_S


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
