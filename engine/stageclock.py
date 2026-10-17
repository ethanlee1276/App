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
