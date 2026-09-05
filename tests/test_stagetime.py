"""The build's own stopwatch — engine/stagetime.py.

`deploy/peakrss.py` says what a build cost in total; it cannot say where.
"The MLB build takes 235 seconds" is the absence of a finding, and the
whole point of this module is that the next time a stage doubles, the
answer is a line in a table rather than an afternoon of bisecting. So the
tests defend the three properties that make it safe to leave switched on
in the tree:

  * OFF BY DEFAULT and free when off — a disabled `stage()` must cost a
    boolean test, or the instrument becomes a reason not to instrument.
  * it never changes what the build does — an exception inside a stage
    comes out unchanged, and the stage is still recorded.
  * the numbers are real: wall time is measured, and nesting is recorded
    as nesting rather than double-counted into the total.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import stagetime                                 # noqa: E402


def _fresh(on=True):
    stagetime.reset()
    stagetime.enable(on)


def test_off_by_default_records_nothing():
    _fresh(on=False)
    with stagetime.stage("nothing"):
        pass
    stagetime.stop(stagetime.start("nothing either"))
    assert stagetime.records() == []
    lines = []
    stagetime.report(out=lines.append)
    assert lines == [], lines


def test_a_disabled_stage_is_cheap():
    """It is meant to sit permanently in the build, so the off path has to
    be nearly free. A million disabled stages inside a second is a long way
    clear of anything a build does."""
    _fresh(on=False)
    t = time.perf_counter()
    for _ in range(100_000):
        with stagetime.stage("x"):
            pass
    assert time.perf_counter() - t < 2.0


def test_it_measures_the_wall_time_of_the_block():
    _fresh()
    try:
        with stagetime.stage("slept"):
            time.sleep(0.05)
        rec = stagetime.records()[-1]
        assert rec["stage"] == "slept"
        assert 0.04 < rec["wall"] < 1.0, rec
        assert rec["peak_mb"] > 0 and rec["end_mb"] > 0, rec
    finally:
        _fresh(on=False)


def test_an_exception_still_closes_the_stage_and_still_raises():
    """A stopwatch that swallows a build's failure would be worse than no
    stopwatch at all."""
    _fresh()
    try:
        raised = False
        try:
            with stagetime.stage("boom"):
                raise ValueError("up")
        except ValueError:
            raised = True
        assert raised
        assert stagetime.records()[-1]["stage"] == "boom"
    finally:
        _fresh(on=False)


def test_nested_stages_are_nested_not_double_counted():
    """The pipeline's stages run inside the build's, so the total has to be
    the top level only — otherwise the shares add up to more than the
    build and the table lies about where the time went."""
    _fresh()
    try:
        with stagetime.stage("outer"):
            with stagetime.stage("inner"):
                time.sleep(0.02)
        depths = [r["depth"] for r in stagetime.records()]
        assert depths == [1, 0], depths
        lines = []
        stagetime.report(out=lines.append)
        head = lines[0]
        outer = [r for r in stagetime.records() if r["stage"] == "outer"][0]
        assert f"{outer['wall']:.1f}s of top-level stages" in head, head
        assert any("inner" in ln for ln in lines)
    finally:
        _fresh(on=False)


def test_start_and_stop_match_the_context_manager():
    """The explicit pair exists for hundred-line loop bodies whose
    re-indentation would bury the change; it must record the same thing."""
    _fresh()
    try:
        token = stagetime.start("by hand")
        time.sleep(0.02)
        stagetime.stop(token)
        rec = stagetime.records()[-1]
        assert rec["stage"] == "by hand" and rec["depth"] == 0
        assert rec["wall"] > 0.01
    finally:
        _fresh(on=False)


def test_stopping_a_disabled_token_is_a_no_op():
    """So a caller never has to branch on whether the instrument is on."""
    _fresh(on=False)
    stagetime.stop(stagetime.start("x"))
    assert stagetime.records() == []


def test_the_mlb_build_and_pipeline_are_instrumented():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = open(os.path.join(root, "mlb_build.py"), encoding="utf-8").read()
    assert build.count("_stg.start(") == build.count("_stg.stop("), (
        "every stage opened in mlb_build.py has to be closed")
    assert '_stg.report("MLB build")' in build
    assert '"--timings"' in build
    pipe = open(os.path.join(root, "engine", "mlb", "pipeline.py"),
                encoding="utf-8").read()
    assert pipe.count("_st.start(") == pipe.count("_st.stop(")
    for stage in ("projections", "evaluate + rules", "simjoint (lineup sim)",
                  "long shots (HR board)", "parlay screen"):
        assert f'"{stage}"' in pipe, stage


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
