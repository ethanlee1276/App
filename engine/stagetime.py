"""Per-stage wall time and peak RSS for a build, when it is asked for.

    QELLYS_STAGE_TIMES=1 python3 mlb_build.py 2026-09-02 --cached-odds
    python3 deploy/peakrss.py python3 mlb_build.py 2026-09-02   # whole-run peak

`deploy/peakrss.py` says what a build cost in total. It cannot say WHERE,
and "the MLB build takes 235 seconds" is not a finding — it is the absence
of one. The NFL memory hunt (`engine/sources/depthcharts.py`, 780 MB to
178 MB) only became actionable once an RSS sampler put a number against
each step; this is that instrument, kept in the tree so the next
regression is a line in a table instead of an afternoon of bisecting.

OFF UNLESS ASKED, and cheap when off: a disabled `stage()` is one boolean
test and a `yield`, so the calls can sit permanently in the build without
costing the board a thing. The sampler thread is only started by the first
enabled stage.

PEAK RSS IS SAMPLED, NOT INFERRED. `resource.getrusage` reports a
high-water mark for the whole process, which can only ever say "the peak
happened at or before here" — enough to find the step that raised the
ceiling, useless for a step that allocates and frees inside itself. So a
background thread reads /proc/self/statm every 20 ms and each stage keeps
the largest sample it saw, which is what makes a transient spike visible.
Where /proc is not readable (macOS), the rusage high-water mark is used
instead and the report says `peak≥` rather than `peak` to keep the weaker
claim honest.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time

#: Sampling period. 20 ms is fine grain against stages measured in
#: seconds, and about 0.1% of one core — small enough that the instrument
#: does not move the number it reports.
SAMPLE_S = 0.02

_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096

_enabled = False
_records: list[dict] = []
_depth = 0
_sampler: threading.Thread | None = None
_stop = threading.Event()
_peak_lock = threading.Lock()
_peak_mb = 0.0
_sampled = True                    # False once we fall back to rusage


def _rss_mb() -> float:
    """This process's resident size, right now."""
    global _sampled
    if _sampled:
        try:
            with open("/proc/self/statm", "rb") as fh:
                return int(fh.read().split()[1]) * _PAGE / (1024 * 1024)
        except (OSError, IndexError, ValueError):
            _sampled = False
    import resource
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes, macOS bytes. Four million of either is
    # 4 GB on Linux (which this would be reporting for a 40 MB build) and
    # 4 MB on macOS (which no CPython process is), so the units are
    # unambiguous from the magnitude.
    return ru / (1024.0 * 1024.0) if ru > 1 << 22 else ru / 1024.0


def _pump() -> None:
    global _peak_mb
    while not _stop.wait(SAMPLE_S):
        mb = _rss_mb()
        with _peak_lock:
            if mb > _peak_mb:
                _peak_mb = mb


def enabled() -> bool:
    return _enabled


def enable(on: bool = True) -> None:
    """Turn the instrument on. Idempotent; the sampler starts once."""
    global _enabled, _sampler
    _enabled = bool(on)
    if _enabled and _sampler is None:
        _stop.clear()
        _sampler = threading.Thread(target=_pump, name="stagetime",
                                    daemon=True)
        _sampler.start()


if os.environ.get("QELLYS_STAGE_TIMES", "").strip() not in ("", "0", "no"):
    enable()


def _peak_since(reset: bool = False) -> float:
    """The largest RSS the sampler has seen, optionally re-armed."""
    global _peak_mb
    with _peak_lock:
        mb = _peak_mb
        if reset:
            _peak_mb = 0.0
    return mb


def start(name: str):
    """Open a stage explicitly; pass the token back to `stop`.

    `stage()` below is the normal way in. This pair exists for the one
    shape a `with` block reads badly: a hundred-line loop body whose
    re-indentation would bury a two-line instrumentation change in a
    diff nobody can review. Returns None when the instrument is off, and
    `stop(None)` is a no-op, so a caller never branches.
    """
    if not _enabled:
        return None
    global _depth, _peak_mb
    _peak_since(reset=True)
    rss0 = _rss_mb()
    with _peak_lock:
        _peak_mb = max(_peak_mb, rss0)
    _depth += 1
    return (name, rss0, time.perf_counter())


def stop(token) -> None:
    """Close a stage opened by `start`."""
    if token is None:
        return
    global _depth
    name, rss0, started = token
    _depth -= 1
    wall = time.perf_counter() - started
    rss1 = _rss_mb()
    _records.append({"stage": name, "depth": _depth, "wall": wall,
                     "peak_mb": max(_peak_since(), rss0, rss1),
                     "end_mb": rss1})


@contextlib.contextmanager
def stage(name: str):
    """Time one build step, and record the peak RSS reached inside it."""
    if not _enabled:
        yield
        return
    token = start(name)
    try:
        yield
    finally:
        stop(token)


def records() -> list[dict]:
    return list(_records)


def report(title: str = "Stage profile", out=print) -> None:
    """Print the table, slowest-first rank alongside build order.

    Build order is what a reader follows; the rank column is what they
    are looking for. Both, because a table that only sorts by cost
    loses the shape of the build, and one that only runs in order makes
    the reader do the comparison themselves.
    """
    if not _enabled or not _records:
        return
    total = sum(r["wall"] for r in _records if r["depth"] == 0)
    order = sorted(range(len(_records)),
                   key=lambda i: -_records[i]["wall"])
    rank = {i: n + 1 for n, i in enumerate(order)}
    width = max(len(r["stage"]) + 2 * r["depth"] for r in _records)
    label = "peak" if _sampled else "peak≥"
    out(f"\n{title} — {total:.1f}s of top-level stages"
        + ("" if _sampled else "  (rusage high-water; no /proc)"))
    out(f"  {'#':>3}  {'stage':<{width}}  {'wall':>8}  {'share':>6}  "
        f"{label:>9}  {'rss end':>8}")
    for i, r in enumerate(_records):
        share = (f"{r['wall'] / total:>5.1%}" if total and r["depth"] == 0
                 else "     ·")
        out(f"  {rank[i]:>3}  {'  ' * r['depth']}{r['stage']:<{width - 2 * r['depth']}}  "
            f"{r['wall']:>7.2f}s  {share}  {r['peak_mb']:>7.0f}MB  "
            f"{r['end_mb']:>6.0f}MB")


def reset() -> None:
    """Drop the recorded stages (tests, and repeated runs in one process)."""
    _records.clear()
