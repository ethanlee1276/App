#!/usr/bin/env python3
"""Tripwires on the numbers that decide things. Reports, never acts.

    python3 watch.py            # print only what crossed a bar
    python3 watch.py --all      # print every reading, crossed or not
    python3 watch.py --reset    # re-baseline without reporting

WHAT THIS IS FOR
----------------
The obvious way to automate a betting model is to let something run the
numbers overnight and tune until they improve. That is a machine for
fooling yourself, and this file is the deliberate alternative to it.

The journal holds 247 settled selected MLB bets. The 2-sigma bar on a 58%
claim at that sample is **+/- 6.3 points** — selcheck prints exactly that.
Any "improvement" smaller than 6.3 points is indistinguishable from luck,
so anything hunting for improvements finds one every night, forever, and
every one is noise. It never gets bored and it never gets suspicious.

So nothing here adjusts anything. Every watch measures one number, compares
it against a bar fixed in advance, and stays silent unless it crossed. The
decision stays with a person.

WHY SILENCE IS THE DEFAULT
--------------------------
doctor.py's own workflow comment says it: "Six warnings that are all
correct behaviour is noise, and noise teaches you to ignore the run." A
nightly report that always prints something gets skimmed and then ignored,
and the one night it matters it gets skimmed too. This prints nothing on a
quiet night, and that silence is the signal.

THE BARS
--------
Two kinds, and they are not interchangeable:

  * **Fixed** — a number chosen in advance for a reason that is written
    down beside it. `SELECTION_Z`, `JOURNAL_MILESTONES`.
  * **Self-scaled** — a move only counts if it exceeds the sample's OWN
    error bar. A gap that wanders from +12.2% to +9.4% on 247 bets has not
    moved; it has been resampled. Any watch comparing against a previous
    reading uses this, because the alternative is a tripwire that fires on
    arithmetic noise every time the sample grows.

Standard library only. Writes one state file and nothing else.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

STATE = Path("data/models/watch.json")

#: The selection effect's pre-registered bar. Named in the last session
#: before the data could speak: the within-strata difference was +8.5% at
#: z 1.87, under-powered rather than absent, and z 2.5 is what would settle
#: it. Quoted here rather than re-chosen, which is the entire point.
SELECTION_Z = 2.5
#: Journal sizes worth being told about, and why each one matters. From
#: selfit's measured power table: at ~124 settled bets per side the
#: out-of-sample check finds a real 12-point over-claim 55% of the time;
#: at ~250 per side, 70%. So 500 total is when re-running it stops being
#: mostly a coin flip.
JOURNAL_MILESTONES = {
    350: "selcheck --across has meaningfully more power than at 247",
    500: "selfit's hold-out reaches ~70% power (was ~55%) — worth re-running",
    750: "a per-market correction becomes arguable; §5 says pooled until then",
}
#: A reading only counts as MOVED if it shifts by more than this many of
#: its own standard errors. Two is the usual bar and there is no reason to
#: be cleverer.
MOVE_SIGMAS = 2.0


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, sort_keys=True))


def _moved(now: float, was, se: float) -> bool:
    """Did a reading move by more than its own noise?

    `se` is the CURRENT reading's standard error, used for both sides. The
    strictly correct bar would combine both readings' errors, which is
    wider still — so this is the permissive version and it already refuses
    most of what would otherwise fire.
    """
    if was is None or se <= 0:
        return False
    return abs(now - float(was)) > MOVE_SIGMAS * se


# --- the watches ------------------------------------------------------------
def watch_journal(conn, state: dict) -> dict:
    """How much evidence exists. The answer to almost every open question
    in this project is "more bets", so the size itself is worth a tripwire.
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE status IN ('won','lost') "
        "AND category='main'").fetchone()[0]
    was = state.get("journal_n")
    crossed = [m for m in sorted(JOURNAL_MILESTONES)
               if n >= m and (was is None or was < m)]
    return {"name": "journal size", "value": n,
            "fired": bool(crossed),
            "reading": (f"{n:,} settled selected bets — passed "
                        f"{crossed[-1]}: {JOURNAL_MILESTONES[crossed[-1]]}"
                        if crossed else f"{n:,} settled selected bets"),
            "state": {"journal_n": n}}


def watch_selection(conn, state: dict) -> dict:
    """Does the gate still pick the worse bets, and has it settled yet?

    Fires on the PRE-REGISTERED z, not on the point estimate moving. The
    estimate wanders every night; the question is whether it has become
    distinguishable from zero.
    """
    import selcheck as sc
    sel = sc.load(conn, "mlb", "main")
    rej = sc.load(conn, "mlb", "loose")
    if len(sel) < 60 or len(rej) < 60:
        return {"name": "selection effect", "value": None, "fired": False,
                "reading": f"not enough settled ({len(sel)}/{len(rej)})",
                "state": {}}
    r = sc.across(sel, rej)
    adj = r.get("adjusted")
    if not adj or not adj.get("se"):
        return {"name": "selection effect", "value": None, "fired": False,
                "reading": "no stratum has enough on both sides", "state": {}}
    z = adj["diff"] / adj["se"]
    was_z = state.get("selection_z")
    # Fires on CROSSING the bar, not on sitting past it. A tripwire that
    # re-fires every night once tripped is a tripwire nobody reads.
    fired = abs(z) >= SELECTION_Z and (was_z is None
                                       or abs(float(was_z)) < SELECTION_Z)
    return {"name": "selection effect", "value": round(z, 3), "fired": fired,
            "reading": (f"{adj['diff']:+.1%} +/-{2 * adj['se']:.1%}, z {z:+.2f} "
                        f"on {len(sel)} vs {len(rej)}"
                        + (f"  ** crossed z {SELECTION_Z} — the selection "
                           f"correction is now supportable; see "
                           f"docs/SELECTION_CORRECTION.md §10 **" if fired
                           else "")),
            "state": {"selection_z": round(z, 3)}}


def watch_calibration(conn, state: dict) -> dict:
    """The over-claim itself: what the selected board said against what it
    landed. Self-scaled — this number is resampled every night and only a
    move past its own error bar means anything."""
    import selcheck as sc
    sel = sc.load(conn, "mlb", "main")
    if len(sel) < 60:
        return {"name": "calibration gap", "value": None, "fired": False,
                "reading": f"only {len(sel)} settled", "state": {}}
    s = sc._stats(sel)
    was = state.get("calibration_gap")
    fired = _moved(s["gap"], was, s["se"])
    note = ""
    if fired:
        note = (f"  ** moved from {float(was):+.1%} — more than "
                f"{MOVE_SIGMAS:.0f} sigma, so not just resampling **")
    return {"name": "calibration gap", "value": round(s["gap"], 4),
            "fired": fired,
            "reading": (f"claimed {s['claimed']:.1%}, landed {s['landed']:.1%}, "
                        f"gap {s['gap']:+.1%} +/-{2 * s['se']:.1%}" + note),
            "state": {"calibration_gap": round(s["gap"], 4)}}


def watch_movement(conn, state: dict) -> dict:
    """Is the movement veto finally measurable?

    `engine.quality.apply_movement` rejects picks outright when line
    movement against them drops their quality below 70, on a signal whose
    predictive value has never been measured. Nothing recorded what it did
    until 2026-08-07, so movecheck.py cannot say anything until enough
    stamped rows have settled on both sides.

    This exists so that moment arrives as a notification rather than as
    something remembered. A diagnostic nobody re-runs is a diagnostic that
    was never built.
    """
    import movecheck as mv
    rows = mv.load(conn, "mlb")
    loose = [r for r in rows if r.get("category") == "loose"]
    killed = [r for r in loose if (r.get("move_delta") or 0) < 0]
    spared = [r for r in loose if r.get("move_delta") is None]
    ready = len(killed) >= mv.MIN_SIDE and len(spared) >= mv.MIN_SIDE
    was = bool(state.get("movecheck_ready"))
    return {"name": "movement veto", "value": ready, "fired": ready and not was,
            "reading": (f"{len(killed)} killed / {len(spared)} spared"
                        + ("  ** movecheck.py can now run — the veto's own "
                           "record is finally readable **" if ready and not was
                           else f" (needs {mv.MIN_SIDE} each)")),
            "state": {"movecheck_ready": ready}}


def watch_bar(conn, state: dict) -> dict:
    """Would an honest edge floor fit inside the credibility window yet?

    barcheck's finding is arithmetic, not a fit: the floor a bet needs is
    the tier minimum plus the measured over-claim, and today that lands
    around three times the largest edge the gate will believe. It is
    therefore not a standing fact — it flips the moment the gap shrinks
    enough, and that is exactly the moment worth being told about, because
    it is the first point at which a board could honestly exist again.
    """
    import barcheck as bc
    rows = bc.load(conn, "mlb")
    if len(rows) < 60:
        return {"name": "honest edge floor", "value": None, "fired": False,
                "reading": f"only {len(rows)} settled recommendations",
                "state": {}}
    gap = bc.measured_gap(rows)["gap"]
    h = bc.honest_bar(1, gap)
    was = state.get("bar_reachable")
    return {"name": "honest edge floor", "value": h["reachable"],
            "fired": h["reachable"] and was is False,
            "reading": (f"gap {gap:+.1%} needs a {h['need']:.1%} floor against "
                        f"a {h['ceiling']:.1%} ceiling — "
                        + ("REACHABLE  ** an honest board is arithmetically "
                           "possible again **" if h["reachable"]
                           else f"short by {100 * h['short']:.1f} points")),
            "state": {"bar_reachable": h["reachable"]}}


def watch_closures(conn, state: dict) -> dict:
    """A slice closing is a PRICING change — it starts refusing bets on the
    next build. House rule is that a person sees it first, so a newly
    closing slice always fires.

    Reads the STORE rather than re-mining. The store is what veto() loads,
    so it is what will actually refuse picks; a fresh mine here could
    disagree with it and would be reporting a hypothetical. The settle pass
    refreshes the store, and tools/nightly.sh runs launch.py before this,
    so by the time it is read it is current.
    """
    from engine import losspatterns as lp
    res = lp.load()
    keys = sorted(f"{f['sport']}:{f['market']}:{f['dim']}={f['value']}"
                  for f in res.get("closed") or [])
    was = state.get("closures") or []
    new = [k for k in keys if k not in was]
    return {"name": "loss-miner closures", "value": keys, "fired": bool(new),
            "reading": (f"{len(keys)} slice(s) would close"
                        + (f"  ** NEW: {', '.join(new)} — this refuses picks "
                           f"on the next build **" if new else "")),
            "state": {"closures": keys}}


WATCHES = [watch_journal, watch_selection, watch_calibration, watch_closures,
           watch_movement, watch_bar]


def run(conn, show_all: bool = False, reset: bool = False) -> int:
    state = _load_state()
    rows, new_state = [], dict(state)
    for w in WATCHES:
        try:
            r = w(conn, state)
        except Exception as exc:                            # noqa: BLE001
            # A crashed watch is a finding, not a silence. Swallowing it
            # would make a broken tripwire look like a quiet night, which
            # is the one failure that makes monitoring worthless.
            rows.append({"name": getattr(w, "__name__", "?"), "fired": True,
                         "reading": f"the watch itself failed: {exc!r}"})
            continue
        new_state.update(r.get("state") or {})
        rows.append(r)

    new_state["checked"] = _dt.datetime.now().isoformat(timespec="seconds")
    _save_state(new_state)

    if reset:
        print(f"Baselined {len(rows)} watches. Nothing reported.")
        return 0

    fired = [r for r in rows if r["fired"]]
    if not fired and not show_all:
        return 0                                   # silence IS the signal

    print("=" * 74)
    print("WATCH" + ("" if fired else " — nothing crossed a bar"))
    print("=" * 74)
    for r in (rows if show_all else fired):
        mark = "**" if r["fired"] else "  "
        print(f" {mark} {r['name']:22} {r['reading']}")
    print()
    if fired:
        print("  Nothing here has been changed. These are readings, and every")
        print("  one of them is a decision for you rather than for a script.")
        print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--all", action="store_true",
                   help="print every reading, not only what crossed")
    p.add_argument("--reset", action="store_true",
                   help="re-baseline the state file without reporting")
    a = p.parse_args(argv)
    from engine import ledger
    return run(ledger.connect(), show_all=a.all, reset=a.reset)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
