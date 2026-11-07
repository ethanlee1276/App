"""The inventions, re-measured every week — so one that holds joins Most Likely and Edge on its own.

Ethan, 2026-10-22: "Are all of our new data and changes being pushed to
the most likely bets too bc it should be. And the edge bets."

engine/ideagate moves Most Likely and Edge the moment an invention's saved
verdict holds, and not before. But nothing on the box ever measured them:
each was run by hand once (the runbook's BX to CE, 2026-10-17), a third of
a season in — 66 questionable listings against the practice bar's 300,
menus and recipes with no newer season to hold out — and never again. A
reading that would hold by November could not join a pick.

This runs each one's own measurement with ``--save``, one at a time and
each in its own process with its own ceiling, every Thursday from
engine/maintenance (as a niced, detached child like the deep refit):
Monday's results are in by then, and Wednesday is the deep refit's. Then
it prints each gate's state, so the weekly log says which inventions are
moving picks.

ONLY THE ONES ALREADY RUN BY HAND, AS THEY WERE RUN: the NFL's (playsim
keeps one verdict for every sport, so a college run would replace the
NFL's), the NHL's endgame and the NBA's vacancy. Nothing here spends an
odds credit — each reads what the box already stores; attention without
``--backfill`` reads the page views the builds keep, and practice reads
nflverse's injury files. A measurement that fails or runs past its
ceiling is a logged line, and the rest still run.

    python3 -m engine.inventionfit          # what the Thursday job runs
    python3 -m engine.inventionfit --list   # the jobs, nothing run

Standard library only.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (what it measures, the command after the interpreter): the holds first
#: (a man unlikely to play), then the Most Likely chances, then the
#: projection's own inputs, then the other sports'.
JOBS = (
    ("practice", ("-m", "engine.practice", "--save")),
    ("menu", ("-m", "engine.bookmenu", "--sport", "nfl", "--save")),
    ("recipe", ("-m", "engine.bookrecipe", "--sport", "nfl", "--save")),
    ("copies", ("-m", "engine.bookclusters", "--sport", "nfl", "--save")),
    ("attention", ("-m", "engine.attention", "--sport", "nfl", "--save")),
    ("range", ("-m", "engine.conformal", "--save")),
    ("kicks", ("-m", "engine.kickphysics", "--save")),
    ("rookie", ("-m", "engine.rookies", "--save")),
    ("role", ("-m", "engine.rolechange", "--save")),
    ("sim", ("-m", "engine.playsim", "--sport", "nfl", "--save")),
    ("endgame", ("-m", "engine.nhl.endgame", "--save")),
    ("vacancy", ("nbavacancy.py", "--heldout", "--save")),
)
#: One measurement's ceiling; the longest the runbook saw was a few minutes.
JOB_TIMEOUT_S = 15 * 60
#: Past this no new one starts: engine/maintenance cuts a weekly child off
#: at an hour (WEEKLY_JOB_TIMEOUT_S), and one cut off mid-save is worse
#: than one left for next week.
BUDGET_S = 50 * 60
#: Lines of each one's own output kept in the weekly log (its verdict
#: lines are its last).
TAIL = 6


def _run_one(cmd) -> tuple:
    """(status, its last lines) for one measurement, in its own process."""
    try:
        p = subprocess.run([sys.executable, "-u", *cmd], cwd=str(ROOT), capture_output=True,
                           text=True, timeout=JOB_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return f"cut off after {JOB_TIMEOUT_S // 60} min", []
    except Exception as exc:                                 # noqa: BLE001
        return f"could not start ({exc})", []
    lines = [x for x in (p.stdout or "").splitlines() if x.strip()]
    if p.returncode != 0:
        return f"failed (code {p.returncode})", lines + [x for x in (p.stderr or "").splitlines()
                                                          if x.strip()][-3:]
    return "ok", lines


def run(jobs=JOBS, runner=None, now=time.monotonic, say=print) -> dict:
    """Each job in turn → {name: "ok" | "failed (code N)" | "cut off …" |
    "not started"}. One that fails is said, and the next one runs."""
    runner = runner or _run_one
    start = now()
    out = {}
    for name, cmd in jobs:
        if now() - start > BUDGET_S:
            out[name] = "not started"
            say(f"  {name}: not started — the hour is nearly spent; it runs next week")
            continue
        t0 = now()
        status, lines = runner(cmd)
        out[name] = status
        say(f"  {name}: {status} in {round(now() - t0)}s")
        for line in lines[-TAIL:]:
            say(f"      {line}")
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list" in argv:
        for name, cmd in JOBS:
            print(f"  {name:<10} python3 {' '.join(cmd)}")
        return 0
    print("The inventions, re-measured (engine/inventionfit)")
    run()
    from . import ideagate
    for sport in ("nfl", "nhl"):
        print(f"The inventions in the picks — {sport}")
        for name, mod, moves, st in ideagate.state(sport):
            print(f"  {name:<10} {st:<26} {moves}  (engine/{mod})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
