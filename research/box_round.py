#!/usr/bin/env python3
"""Every read-only research run the box owes, in order, in one command — one paste back.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/box_round.py

Ethan, 2026-10-17: "tell me what to run i dont wanna have to search the
runbook". The runbook's block CP lists the lab's box runs one line at a
time; this runs the same lines in the same order, each in its own process
(so each one's memory is handed back before the next starts on the 1 GB
box), and prints each one's output under its own heading with how long it
took and how it exited. One that fails is reported and the round goes on.

It reads only: every script it runs opens the databases read-only. It
never reads a holdout: no step passes ``--holdout``, and a step that did
would be refused before anything runs. A holdout is read once, by hand,
after its validation paste has been checked (runbook block CP).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (heading, script and its arguments, keep only the last N lines or None).
STEPS = (
    ("EXP-R06: the board's thin picks priced from the main lines", ("research/thinmarket_box.py",), None),
    ("EXP-001c: the NFL models at the books' own lines", ("research/exp1_lines_box.py",), 20),
    ("EXP-007: MLB starters' strikeouts (validation only)", ("research/exp7_mlb_strikeouts_box.py",), None),
    ("EXP-004c: the college results at the books' own lines", ("research/exp4c_college_lines_box.py",), None),
    ("EXP-008: the NBA spread against a shape built from minutes (validation only)",
     ("research/exp8_nba_shape_box.py",), None),
)
#: Per step. The slowest measured in the sandbox took about a minute; the
#: box is slower and shares its one core with the site.
TIMEOUT = 1800


def refuse_holdouts(steps) -> None:
    """A round never reads a holdout; a step that asks to is a mistake in
    this file, and nothing runs."""
    bad = [h for h, args, _n in steps if any(a.startswith("--holdout") for a in args)]
    if bad:
        raise SystemExit("box_round: a step asks for a holdout read, which is done once by hand: " + "; ".join(bad))


def run_step(args, timeout: int = TIMEOUT, cwd=ROOT) -> tuple:
    """(exit code or None on a timeout, output, seconds)."""
    t = time.time()
    try:
        p = subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""               # bytes here even with text=True
        out = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        code = None
    return code, out, time.time() - t


def main(steps=STEPS, timeout: int = TIMEOUT, cwd=ROOT, out=print) -> int:
    refuse_holdouts(steps)
    started = time.time()
    summary = []
    for n, (heading, args, tail) in enumerate(steps, 1):
        out(f"\n===== {n}/{len(steps)} {heading}")
        out(f"      python3 {' '.join(args)}" + (f"  (last {tail} lines)" if tail else ""))
        code, text, secs = run_step(args, timeout, cwd)
        lines = text.rstrip("\n").splitlines()
        if tail:
            lines = lines[-tail:]
        for line in lines:
            out(line)
        how = "timed out" if code is None else ("ok" if code == 0 else f"exit {code}")
        out(f"----- {how}, {secs:.0f}s")
        summary.append(f"{n} {how}")
    out(f"\n===== round done in {time.time() - started:.0f}s: " + ", ".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
