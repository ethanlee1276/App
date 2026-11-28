"""A board build's stage times reach the heartbeat, and a build killed at
its limit keeps its log (launch._run_build, _stages_of, _timed_out_lines,
_note_board; engine/stageclock.parse).

The NFL build ran 577 of its 600 seconds on the morning of Sunday 8
November, one stage away from the loop's kill, and nothing public said
which stage held the time: the stage clock printed each stage's seconds
into the build's log on the box, and a killed build's log was never
written at all. What these hold:

  * the stage clock's own lines read back as ``{stage: seconds}``, in
    order, a stage marked twice adding up, other lines ignored;
  * a finished build's stages ride on its board's heartbeat entry, taken
    once, so a refresh that ran no build cannot wear the last one's;
  * a build killed at its limit keeps its log (what it printed, and a line
    saying it was killed) and its stages, the stage the kill fell in named
    with the seconds it had;
  * a build with no stage clock adds nothing.

Run directly: `python3 tests/test_a_builds_stage_times_reach_the_heartbeat.py`
"""
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import launch                                                       # noqa: E402
from engine import stageclock                                       # noqa: E402


def _script(body: str) -> str:
    p = Path(tempfile.mkdtemp()) / "fake_build.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


class _Logs:
    """The build logs in scratch."""

    def __enter__(self):
        self.keep = launch.BUILD_LOG_DIR
        launch.BUILD_LOG_DIR = Path(tempfile.mkdtemp())
        return launch.BUILD_LOG_DIR

    def __exit__(self, *exc):
        launch.BUILD_LOG_DIR = self.keep


def test_the_stage_clocks_lines_read_back_in_order():
    said, t = [], iter([0.0, 12.4, 40.0, 41.2, 500.6])
    clock = lambda: next(t)                                         # noqa: E731
    stageclock.start(clock=clock)
    for stage in ("build_slate", "odds", "journal", "pipeline"):
        stageclock.mark(stage, out=said.append, clock=clock)
    said += ["Analyzed 610 props", "  ⏱ journal: 3s (at 503s of 600)", "⚠️  not a mark: 9s"]
    got = stageclock.parse(said)
    assert list(got) == ["build_slate", "odds", "journal", "pipeline"], got
    assert got == {"build_slate": 12, "odds": 28, "journal": 1 + 3, "pipeline": 459}, got
    assert stageclock.parse(None) == {} and stageclock.parse(["nothing here"]) == {}


def test_a_finished_builds_stages_ride_its_board_entry_once():
    build = _script("""
        print("  ⏱ build_slate: 4s (at 4s of 600)")
        print("Analyzed 12 props")
        print("  ⏱ pipeline: 21s (at 25s of 600)")
    """)
    with _Logs() as logs:
        ok, tail = launch._run_build([build], timeout=60)
        assert ok and "pipeline" in tail
        launch._note_board("zz_test_board", ok)
        assert launch._BOARD_RUNS["zz_test_board"]["stages"] == {"build_slate": 4, "pipeline": 21}
        assert (logs / "fake_build.log").read_text(encoding="utf-8").count("⏱") == 2
        # The next refresh of the board ran no build: no stages to wear.
        launch._note_board("zz_test_board", True)
        assert "stages" not in launch._BOARD_RUNS["zz_test_board"]
    launch._BOARD_RUNS.pop("zz_test_board", None)


def test_a_build_killed_at_its_limit_keeps_its_log_and_its_stages():
    build = _script("""
        import sys, time
        print("  ⏱ build_slate: 1s (at 1s of 600)", flush=True)
        print("  ⏱ odds: 0s (at 1s of 600)", flush=True)
        time.sleep(60)
        print("never printed")
    """)
    with _Logs() as logs:
        ok, why = launch._run_build([build], timeout=3)
        assert not ok and "timed out" in why.lower(), why
        stages = launch._LAST_BUILD_STAGES[0]
        assert stages == {"build_slate": 1, "odds": 0, "(killed in the next stage)": 2}, stages
        log = (logs / "fake_build.log").read_text(encoding="utf-8")
        assert "exit -9" in log and "⏱ odds" in log and "# killed at its 3s limit" in log, log
        assert "never printed" not in log
        launch._note_board("zz_test_board", ok)
        assert launch._BOARD_RUNS["zz_test_board"]["stages"]["(killed in the next stage)"] == 2
    launch._BOARD_RUNS.pop("zz_test_board", None)


def test_a_build_with_no_stage_clock_adds_nothing():
    build = _script('print("built 3 rows")\n')
    with _Logs():
        ok, _tail = launch._run_build([build], timeout=60)
        launch._note_board("zz_test_board", ok)
    assert ok and "stages" not in launch._BOARD_RUNS["zz_test_board"]
    launch._BOARD_RUNS.pop("zz_test_board", None)
    assert launch._timed_out_lines(ValueError("not a timeout")) == []


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
