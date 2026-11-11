"""The settle pass's hourly learners, and the record export's two-leg
section, say where their time went (engine/maintenance._learn_sampled,
engine/stacksample.Sampler(qualify=True), engine/ledger.TWO_LEG_LAST).

The first settle pass after the 04:35 restart on 10 November learned for
528.6 seconds and exported for 144.9, 63.7 of them in the two-leg parlay
section, on a one-CPU box beside the board builds, with nothing to say
which learner or which half. What these hold:

  * a qualified sample names each section with its module, so six modules'
    ``refresh`` are six sections, not one;
  * the learners run through the sampler and their seconds land on the
    pass's phases as ``learn_parts``, at both places the pass learns;
  * the two-leg section times its two halves (the pools' record and the
    backtest, kept or worked out) and the settle pass puts them on its
    phases as ``export_two_leg``, cleared before each export;
  * every pass carries the last learning pass's breakdown and the last
    export's (``last_learned``, ``last_exported``) through the settle state,
    since the heartbeat shows only the latest pass (07:41 on 11 November: a
    quiet pass, every overnight one that learned replaced).

Run directly: `python3 tests/test_the_learners_say_which_took_their_time.py`
"""
import importlib
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.stacksample import Sampler                             # noqa: E402

LEARNER = '''
import time


def refresh(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass
'''


def _two_learners(folder):
    """Two modules, ``learner_a`` and ``learner_b``, each with a ``refresh``."""
    for name in ("learner_a", "learner_b"):
        (Path(folder) / f"{name}.py").write_text(LEARNER, encoding="utf-8")
    sys.path.insert(0, folder)
    try:
        return importlib.import_module("learner_a"), importlib.import_module("learner_b")
    finally:
        sys.path.remove(folder)


def test_a_qualified_sample_tells_two_refreshes_apart():
    with tempfile.TemporaryDirectory() as td:
        a, b = _two_learners(td)

        def learn():
            a.refresh(0.5)
            b.refresh(0.25)
        with Sampler(learn.__code__, interval=0.01, qualify=True) as s:
            learn()
        parts = s.seconds()
        assert parts.get("learner_a.refresh", 0) > 0.3 and parts.get("learner_b.refresh", 0) > 0.1, parts
        assert parts["learner_a.refresh"] > parts["learner_b.refresh"], parts
        with Sampler(learn.__code__, interval=0.01) as plain:
            learn()
        assert set(plain.seconds()) <= {"refresh", "(self)"}, "unqualified, the two are one"
        sys.modules.pop("learner_a", None)
        sys.modules.pop("learner_b", None)


def test_the_learners_seconds_land_on_the_phases():
    from engine import maintenance as M
    with tempfile.TemporaryDirectory() as td:
        a, b = _two_learners(td)

        def learn():
            a.refresh(0.4)
            b.refresh(0.2)
        phases: dict = {}
        M._learn_sampled(learn, phases)
        parts = phases.get("learn_parts") or {}
        assert parts.get("learner_a.refresh", 0) > 0.25 and parts.get("learner_b.refresh", 0) > 0.08, parts
        sys.modules.pop("learner_a", None)
        sys.modules.pop("learner_b", None)
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert src.count("_learn_sampled(learn, phases)") == 2, "both places the pass learns"
    i = src.index("def settle_open(")
    assert "                learn()\n" not in src[i:] and "            learn()\n" not in src[i:], \
        "the pass learns only through the sampler"


def test_the_two_leg_halves_are_timed_and_reach_the_phases():
    from engine import ledger
    from engine import maintenance as M
    conn = ledger.connect(":memory:")
    ledger._two_leg_record(conn)
    last = dict(ledger.TWO_LEG_LAST)
    assert {"report_s", "backtest_s", "backtest"} <= set(last), last
    assert last["backtest"] in ("kept", "worked out"), last
    if last["backtest"] == "worked out":
        assert {"schedule_s", "groups", "paired"} <= set(last), last
    real = ledger.export_json
    ledger.TWO_LEG_LAST.update(report_s=9.9)                 # a stale copy from an earlier export

    def export(c, p):
        ledger.TWO_LEG_LAST.update(report_s=0.1, backtest_s=0.2, backtest="kept")
    ledger.export_json = export
    try:
        phases: dict = {}
        M._export_record(conn, phases)
        assert phases["export_two_leg"] == {"report_s": 0.1, "backtest_s": 0.2, "backtest": "kept"}, phases

        def export_none(c, p):
            pass
        ledger.export_json = export_none
        phases = {}
        M._export_record(conn, phases)
        assert "export_two_leg" not in phases, "cleared before each export: never an earlier one's"
    finally:
        ledger.export_json = real


def test_every_pass_carries_the_last_learning_and_the_last_export():
    from engine import maintenance as M
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "maintenance.json"
        state = M._load_state(path)
        learned = {"learned": True, "learn": 12.3, "learn_parts": {"selectionfit.refresh": 9.1},
                   "exported": True, "export": 4.0, "export_parts": {"_two_leg_record": 2.5},
                   "export_two_leg": {"report_s": 0.4, "backtest_s": 2.1, "backtest": "kept"}}
        M._keep_last_parts(state, learned, 1000.0)
        M._save_state(path, state)
        assert learned["last_learned"]["parts"] == {"selectionfit.refresh": 9.1}
        assert learned["last_learned"]["learn"] == 12.3
        assert learned["last_exported"]["two_leg"]["backtest"] == "kept"
        # The next pass, in its own process, does neither: both come back from the file.
        quiet: dict = {"learned": False, "learn": 0.0, "export": 0.0}
        again = M._load_state(path)
        M._keep_last_parts(again, quiet, 2000.0)
        assert quiet["last_learned"] == learned["last_learned"], quiet
        assert quiet["last_exported"] == learned["last_exported"], quiet
        assert quiet["last_learned"]["at"] < M._dt.datetime.fromtimestamp(2000.0).isoformat(timespec="seconds")
        # A later learning replaces it; an export without a two-leg half carries none.
        later = {"learn": 3.0, "learn_parts": {"journalfit.refresh": 2.0}, "export_parts": {"performance": 1.0}}
        M._keep_last_parts(again, later, 3000.0)
        assert later["last_learned"]["parts"] == {"journalfit.refresh": 2.0}
        assert "two_leg" not in later["last_exported"]
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("def settle_open(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert body.count("_keep_last_parts(state, phases, now)\n") == 2, "both places a pass ends"
    assert body.count('_keep_last_parts(state, phases, now)\n            state["last_settle_ts"] = now') == 1
    assert body.count('_keep_last_parts(state, phases, now)\n    state["last_settle_ts"] = now') == 1


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
