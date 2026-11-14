"""One line per build stage, printed as the build goes.

The loop gives a build 600 seconds and then kills it (launch._run_build),
so a timing table printed at the end never prints for the builds that need
it: on Ethan's box paste of 2026-10-17 every college build of the day and
most NFL builds were killed, and nothing said where the time had gone. A
mark prints when the stage ends, so the build's log (data/logs/<sport>_
build.log) shows every stage that finished and how long it took, and the
last line before the kill names the one that did not.

Standard library only. Never raises.
"""
from __future__ import annotations

import time

#: The loop's limit, for the running total each line prints beside.
LIMIT = 600

_STATE: dict = {"t0": None, "last": None}


def start(clock=time.monotonic) -> None:
    """Begin a build's clock (a second build in one process starts afresh)."""
    now = clock()
    _STATE["t0"] = _STATE["last"] = now


def parse(lines) -> dict:
    """``{stage: seconds}`` from a build's output, in the order its marks
    printed them (a stage marked twice adds up): what `mark` said, read back
    by the loop (launch._run_build) so the heartbeat can carry where a
    build's time went. Lines that are not marks are ignored."""
    import re
    out: dict = {}
    for ln in lines or ():
        m = re.match(r"^\s*⏱ (.+): (\d+)s \(at \d+s of \d+\)\s*$", str(ln))
        if m:
            out[m.group(1)] = out.get(m.group(1), 0) + int(m.group(2))
    return out


def mark(stage: str, out=print, clock=time.monotonic) -> float:
    """Print how long ``stage`` took and where the build stands against the
    limit; returns the stage's seconds."""
    try:
        now = clock()
        if _STATE["t0"] is None:
            _STATE["t0"] = _STATE["last"] = now
        secs = now - _STATE["last"]
        _STATE["last"] = now
        out(f"  ⏱ {stage}: {secs:.0f}s (at {now - _STATE['t0']:.0f}s of {LIMIT})")
        return secs
    except Exception:                                        # noqa: BLE001
        return 0.0


# THE PARTS OF A STAGE (2026-11-08). A stage's one number says where a
# build's time went but not what inside it: the NFL build's pricing ran 37
# seconds at 07:57 and 112 at 08:09, and its inventions' readings 33. A part
# line names what inside a stage took the time, read back the same way
# (`parse_parts`) for the heartbeat beside the stages.
#
# SILENT UNLESS A BUILD STARTED THE CLOCK. The backtest and the Lab price
# thousands of slates through the same code (engine/pipeline.run_slate);
# a part prints only in a process whose build called `start` (or `mark`).
# Its own shape, with no "(at …)", so `parse` never counts a part as a
# stage and the stages still add up to the build.

def lap(stage: str, part: str, since: float, out=print, clock=time.monotonic) -> float:
    """Print how long ``part`` of ``stage`` took since ``since`` and return
    now, the next part's ``since``. Never raises."""
    try:
        now = clock()
    except Exception:                                        # noqa: BLE001
        return since
    try:
        if _STATE["t0"] is not None:
            out(f"  ⏱ {stage} › {part}: {now - since:.1f}s")
    except Exception:                                        # noqa: BLE001
        pass
    return now


def part(stage: str, name: str, secs: float, out=print) -> None:
    """Print one part's seconds measured by its own code (the readings time
    their own sections). Never raises."""
    try:
        if _STATE["t0"] is not None:
            out(f"  ⏱ {stage} › {name}: {float(secs):.1f}s")
    except Exception:                                        # noqa: BLE001
        pass


def parse_parts(lines) -> dict:
    """``{stage: {part: seconds}}`` from a build's output, in the order
    they printed (a part named twice adds up). Lines that are not part
    lines are ignored."""
    import re
    out: dict = {}
    for ln in lines or ():
        m = re.match(r"^\s*⏱ (.+?) › (.+): (\d+(?:\.\d+)?)s\s*$", str(ln))
        if m:
            parts = out.setdefault(m.group(1), {})
            parts[m.group(2)] = round(parts.get(m.group(2), 0.0) + float(m.group(3)), 1)
    return out
