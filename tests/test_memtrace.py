"""Which stage of the NFL build spends the memory.

Measured on the droplet 2026-09-03 with deploy/peakrss.py:

    exit=0 elapsed=305s peak_rss_mb=1692

On a machine with 1 GB. The build only finishes by swapping ~700 MB to
disk, and every other symptom that night is downstream of it: a cycle that
used to take 270 seconds still running 32 minutes later, load average 2.15
on one core, MLB never reached, and on 2026-09-02 an OOM crash loop.

`peakrss.py` gives ONE number for the whole run. That says the build is
too big and nothing at all about which part of it, which is the difference
between a fix and a guess. `--memtrace` prints the high-water mark after
each stage — the same thing `_STEP_S` already does for the refresh loop's
seconds, and for the same reason: the answer should arrive as a paste
rather than a profiling session on a box that is already thrashing.

THE PEAK IS THE NUMBER THAT MATTERS, not the resident size. A stage that
allocates a gigabyte and frees it leaves RSS looking innocent and is
exactly what the OOM killer acts on. `_peak_mb` reads VmHWM for that
reason, and `test_a_stage_that_frees_is_still_counted` is the case.

Run directly: `python3 tests/test_memtrace.py`
"""

import importlib.util as _u
import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = _u.spec_from_file_location("nfl_build_mod",
                                   os.path.join(ROOT, "nfl_build.py"))
NB = _u.module_from_spec(_spec)
_spec.loader.exec_module(NB)

BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()


def _fresh():
    NB._MEM.clear()


# --- the readings -----------------------------------------------------------
def test_it_reads_a_real_resident_size():
    """Not a stub. If this ever returns 0 on Linux the trace is furniture."""
    mb = NB._rss_mb()
    assert mb > 1.0, f"resident size read as {mb} MB"
    assert mb < 100000, mb


def test_the_peak_is_never_below_the_resident_size():
    assert NB._peak_mb() >= NB._rss_mb() - 1.0


def test_the_peak_never_falls_even_though_the_kernel_s_can():
    """VmHWM is documented as a peak and is not reliably monotonic across
    reads inside a container — measured in this repo's own sandbox at
    92,739 kB followed by 92,636 kB with nothing but a `del` between them.
    A hundred kilobytes is nothing, but a peak that can fall is not a peak,
    and it is wrong in the dangerous direction for a number whose entire
    job is to say how close a build came to the ceiling.

    Repeated, because the kernel's wobble is intermittent — a single pass
    reproduced it roughly one time in three."""
    seen = []
    for _ in range(8):
        seen.append(NB._peak_mb())
        junk = [dict(a=i) for i in range(50000)]
        seen.append(NB._peak_mb())
        del junk
        seen.append(NB._peak_mb())
    for a, b in zip(seen, seen[1:]):
        assert b >= a, f"the peak fell from {a:.3f} to {b:.3f} MB"


def test_a_stage_that_frees_is_still_counted():
    """THE CASE THE PEAK EXISTS FOR. A stage that allocates a lot and then
    frees it leaves RSS looking innocent — and it is what kills a 1 GB box,
    because the OOM killer acts on the high-water mark, not on what is
    resident when the stage happens to end."""
    _fresh()
    NB._mem("before")
    big = [dict(a=i, b="x" * 200) for i in range(300000)]
    NB._mem("allocates")
    peak_while = NB._MEM[-1][2]
    del big
    NB._mem("after it frees")
    stage, rss_after, peak_after = NB._MEM[-1]
    assert rss_after < peak_while, \
        "the fixture did not actually free anything, so this proves nothing"
    assert peak_after >= peak_while, \
        "the high-water mark fell when memory was freed — it is tracking RSS"


# --- the report -------------------------------------------------------------
def _report_for(readings):
    """The report for a fixed set of (stage, rss, peak) readings."""
    _fresh()
    NB._MEM.extend(readings)
    buf = io.StringIO()
    with redirect_stdout(buf):
        NB._mem_report()
    return buf.getvalue()


def test_the_report_ranks_by_the_peak_not_by_what_is_left_resident():
    """THE BUG THIS TOOL SHIPPED WITH, on the very metric its own docstring
    calls the wrong one. These are the real readings from the droplet,
    2026-09-03:

        build_slate      86     148      +60
        odds             75    1324      -19
        pipeline         73    1602       -2

    The first version ranked on the RESIDENT delta and announced
    build_slate at 60 MB. `odds` had just allocated and freed ELEVEN
    HUNDRED. Ranking on what a stage leaves behind rewards exactly the
    stage that cleans up after itself and hides exactly the one that
    spikes — and the spike is what the OOM killer acts on.
    """
    out = _report_for([("start", 26, 26), ("build_slate", 86, 148),
                       ("injuries + resets", 87, 148), ("depth charts", 94, 177),
                       ("odds", 75, 1324), ("pipeline", 73, 1602),
                       ("write + journal", 96, 1602)])
    assert "the largest was odds, which pushed it up 1147 MB" in out, out
    assert "build_slate" not in out.split("peak 1602")[1].split("(")[0], \
        "build_slate is still being named as the worst stage"
    # The stage that HOLDS the most is worth a line, but a secondary one.
    assert "build_slate holds the most afterwards" in out, out


def test_the_report_names_every_stage_and_the_worst_one():
    """The one line anybody reads. A table of numbers with no verdict is
    another thing to interpret on a box already in trouble."""
    out = _report_for([("start", 20, 20), ("the expensive one", 30, 500),
                       ("something cheap", 31, 505)])
    assert "the largest was the expensive one" in out, out
    assert "the biggest peak" in out, out
    for stage in ("start", "the expensive one", "something cheap"):
        assert stage in out, f"{stage} is missing from the table"


def test_a_stage_that_frees_everything_is_still_ranked_worst():
    """The exact shape of `odds`: resident goes DOWN, peak goes up by a
    gigabyte. If ranking ever returns to the resident delta this stage
    scores best in the table and the build stays broken."""
    out = _report_for([("start", 50, 50), ("frees it all", 40, 1200),
                       ("keeps a little", 60, 1200)])
    assert "the largest was frees it all" in out, out


def test_the_report_is_silent_when_nothing_was_traced():
    """Off by default; a build that never called `_mem` prints nothing."""
    _fresh()
    buf = io.StringIO()
    with redirect_stdout(buf):
        NB._mem_report()
    assert buf.getvalue() == ""


def test_tracing_is_off_unless_asked_for():
    _fresh()
    NB._mem("ignored", False)
    assert not NB._MEM, "the trace records even when the flag is off"


def test_a_reading_that_raises_never_costs_the_build():
    """Accounting must not be able to break a board — the same rule
    `log_spend` carries."""
    _fresh()
    real = NB._rss_mb
    NB._rss_mb = lambda: (_ for _ in ()).throw(OSError("no /proc"))
    try:
        NB._mem("stage")            # must not raise
    finally:
        NB._rss_mb = real
    assert True


# --- the wiring -------------------------------------------------------------
def test_every_stage_of_the_build_is_marked():
    """A trace that skips the stage doing the damage answers nothing."""
    for stage in ("start", "build_slate", "injuries + resets", "depth charts",
                  "odds", "pipeline", "write + journal"):
        assert f'_mem("{stage}"' in BUILD, f"{stage} is not marked"


def test_the_flag_exists_and_the_report_runs_last():
    assert '"--memtrace"' in BUILD
    i = BUILD.rindex('_mem("write + journal"')
    j = BUILD.rindex("_mem_report()")
    assert i < j, "the report prints before the last stage is recorded"
    assert BUILD.index('_mem("start"') < i


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
