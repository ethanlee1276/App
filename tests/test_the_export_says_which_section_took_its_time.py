"""The record export says which of its sections took the time, sampled
(engine/stacksample.Sampler; engine/maintenance._export_record and the
settle pass's phases["export_parts"]).

The export wrote the record in 148.6 seconds on the box on Saturday
7 November, every ten minutes on a game day, and it is one call of some
seventy sections. What these hold:

  * a sampler credits each look at the stack to the function the measured
    call was running directly at that moment, so its totals are seconds per
    section (a function called deeper inside a section counts for the
    section), and nothing outside the call is counted;
  * the totals are the top sections by seconds, the rest summed;
  * a sampler that fails stops and reports what it had, never raising into
    the measured call;
  * the settle pass writes the record through it and puts the totals on
    its phases as ``export_parts``.

Run directly: `python3 tests/test_the_export_says_which_section_took_its_time.py`
"""
import datetime as dt
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import stacksample                                     # noqa: E402
from engine.stacksample import Sampler                             # noqa: E402


def _busy(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _inner(seconds):
    _busy(seconds)


def slow_section():
    _inner(0.6)          # deeper calls count for the section


def quick_section():
    _busy(0.25)


def measured():
    slow_section()
    quick_section()


def test_each_look_is_credited_to_the_section_running():
    _busy(0.2)                                        # outside the call: not counted
    with Sampler(measured.__code__, interval=0.01) as s:
        measured()
    secs = s.seconds()
    assert set(secs) <= {"slow_section", "quick_section", "(self)"}, secs
    assert secs.get("slow_section", 0) > secs.get("quick_section", 0) > 0, secs
    assert abs(secs["slow_section"] - 0.6) < 0.25, secs
    assert abs(sum(secs.values()) - s.elapsed) < 0.15, (secs, s.elapsed)


def test_nothing_is_counted_when_the_call_is_not_on_the_stack():
    with Sampler(measured.__code__, interval=0.01) as s:
        _busy(0.15)
    assert s.seconds() == {} and s.samples == 0


def test_the_totals_are_the_top_sections_and_the_rest():
    s = Sampler(measured.__code__)
    s.counts = {"a": 50, "b": 30, "c": 10, "d": 6, "e": 4}
    s.samples, s.elapsed = 100, 20.0
    assert s.seconds(top=3) == {"a": 10.0, "b": 6.0, "c": 2.0, "(rest)": 2.0}
    assert s.seconds(top=10) == {"a": 10.0, "b": 6.0, "c": 2.0, "d": 1.2, "e": 0.8}


def test_a_failing_sampler_never_raises_into_the_call():
    saved = stacksample.sys._current_frames

    def boom():
        raise RuntimeError("no frames for you")
    stacksample.sys._current_frames = boom
    try:
        with Sampler(measured.__code__, interval=0.01) as s:
            quick_section()
    finally:
        stacksample.sys._current_frames = saved
    assert s.seconds() == {}


def test_the_settle_pass_puts_the_exports_sections_on_its_phases():
    from engine import db, ledger
    from engine import maintenance as M
    real = (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
            ledger.export_json)
    real_db, saved_ingest, saved_due = db.connect, M.ingest_for_open_bets, M._export_due
    conn = ledger.connect(":memory:")
    conn.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                 "VALUES ('nba', '2026-11-07', 'P', 'points', 'open', 'main')")
    conn.commit()
    written = []

    def export(c, p):
        slow_section()
        written.append(str(p))
    ledger.connect = lambda path=None: conn
    db.connect = lambda path=None: None
    ledger.settle_from_history = lambda lconn, hconn, sport=None: 0
    ledger.resettle_mismatches = lambda lconn, hconn, since=None: []
    ledger.export_json = export
    M.ingest_for_open_bets = lambda l, h, days, log: {"games": 0}
    M._export_due = lambda state, now: True
    try:
        with tempfile.TemporaryDirectory() as td:
            M.settle_open(log=lambda *_: None, state_path=Path(td) / "m.json",
                          today=dt.date(2026, 11, 7), now=1000.0, force=True)
    finally:
        (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
         ledger.export_json) = real
        db.connect, M.ingest_for_open_bets, M._export_due = real_db, saved_ingest, saved_due
    assert written and written[0].endswith("record.json"), written
    parts = M.LAST_SETTLE_PHASES.get("export_parts") or {}
    assert parts.get("slow_section", 0) > 0.3, parts


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
