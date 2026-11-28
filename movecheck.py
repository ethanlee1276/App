#!/usr/bin/env python3
"""Does line movement earn its veto? Measure it, don't argue about it.

    python3 movecheck.py
    python3 movecheck.py --sport mlb

WHAT THIS IS FOR
----------------
`engine/quality.apply_movement` moves a graded pick's quality score by
+/-4 points, +/-7 on steam, can raise the letter, and — when the drop puts
a pick under 70 — sets ``grade="Pass"``, ``recommended=False`` and
``stake_units=0``. It rejects the pick outright.

For months the docstring above its only caller said the opposite:

    Purely informational — it never changes a grade, because we
    haven't measured its predictive value on our own picks yet.

Both halves of that sentence were wrong in the same direction. It does
change grades, and the stated reason for believing it did not — that its
predictive value was unmeasured — was true and remains true. A signal with
veto power over the board, on no evidence, is the exact thing the rest of
this repo is built to refuse.

THE HONEST PROBLEM: THERE IS NOTHING TO MEASURE YET
---------------------------------------------------
Until 2026-08-07 nothing journalled what movement did. The stamp lived on
the in-memory recommendation, was rendered to the site, and was gone. So
this cannot be run backwards over the existing journal — every row reads
NULL, and that is a real answer rather than a bug.

What it can do is start being answerable. `move_delta` and `move_steam`
are now written by both journal paths, and this script reports the moment
there is enough to report. Same shape as the `closing_odds` capture:
recorded now so the history exists whenever the question is finally asked.

THE TWO QUESTIONS, AND WHY BOTH ARE NEEDED
-------------------------------------------
**Among picks that survived** (category `main`): did movement-against
picks land worse than movement-with ones? This is the easy comparison and
the weaker one — it can only see picks the veto did NOT kill, so it is
conditioned on surviving and understates the effect either way.

**Among picks that were rejected** (category `loose`): did the ones
movement killed lose more than the near-misses rejected for other
reasons? This is the question that actually decides whether the veto pays,
because these are the bets the veto cost you. They land in `loose` with a
quality just under 70, which is precisely how a rejected pick ends up in
that bucket, and without `move_delta` they are indistinguishable from a
prop that simply graded low.

A veto is worth keeping if the bets it killed would have lost. Nothing
else about it matters.

Standard library only. Reads the journal; writes nothing.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import ledger

#: Below this on either side, a comparison is noise wearing a number.
#: Deliberately low — this is a diagnostic that ships nothing, and the
#: alternative to a wide-barred answer is no answer at all.
MIN_SIDE = 30
#: The pre-registered bar. Movement keeps its veto if the picks it killed
#: landed at least this many points below the near-misses it spared —
#: i.e. it was picking the losers out of a bucket that was already
#: marginal. Fixed here, before the first row exists, because a threshold
#: chosen after seeing the answer is not a threshold.
KEEP_VETO_PTS = 0.05


def load(conn, sport=None) -> list[dict]:
    q = ("SELECT sport, market, side, category, hit_prob, status, "
         "move_delta, move_steam, stake_units, pnl_units "
         "FROM bets WHERE status IN ('won','lost')")
    args: list = []
    if sport and sport != "all":
        q += " AND sport=?"
        args.append(sport)
    return [dict(r) for r in conn.execute(q, args)]


def _rate(rows: list[dict]) -> dict:
    """Landed rate with its binomial error, plus the claim for context."""
    n = len(rows)
    if not n:
        return {"n": 0, "landed": 0.0, "se": 0.0, "claimed": 0.0}
    w = sum(1 for r in rows if r["status"] == "won")
    p = w / n
    claims = [float(r["hit_prob"]) for r in rows if r.get("hit_prob") is not None]
    return {"n": n, "landed": p, "se": math.sqrt(p * (1 - p) / n),
            "claimed": (sum(claims) / len(claims)) if claims else 0.0}


def split_by_movement(rows: list[dict]) -> dict:
    """Three groups, and the third is not the absence of the other two.

    A NULL `move_delta` means no movement was observed for that prop —
    which is a different fact from a movement of zero, and a different
    population from one the market moved on. Folding them together would
    let "the market never moved" dilute whatever the moves are worth.
    """
    against = [r for r in rows if (r.get("move_delta") or 0) < 0]
    with_us = [r for r in rows if (r.get("move_delta") or 0) > 0]
    unseen = [r for r in rows if r.get("move_delta") is None]
    return {"against": against, "with": with_us, "unseen": unseen}


def compare(a: list[dict], b: list[dict]) -> dict:
    """a minus b, on landed rate, with a pooled two-sigma bar."""
    ra, rb = _rate(a), _rate(b)
    if ra["n"] < MIN_SIDE or rb["n"] < MIN_SIDE:
        return {"ok": False, "a": ra, "b": rb}
    se = math.sqrt(ra["se"] ** 2 + rb["se"] ** 2)
    d = ra["landed"] - rb["landed"]
    return {"ok": True, "a": ra, "b": rb, "diff": d, "se": se,
            "z": (d / se) if se else 0.0}


def _line(label: str, r: dict) -> str:
    if not r["n"]:
        return f"  {label:28} —"
    return (f"  {label:28} {r['n']:5} bets   claimed {r['claimed']:5.1%}   "
            f"landed {r['landed']:5.1%} ±{2 * r['se']:.1%}")


def _snapshot_depth() -> None:
    """WHY SO FEW STAMPS — the question the headline count provokes and
    could not answer.

    A pick can only carry a movement stamp if `linemoves.analyze` saw the
    prop move, and that needs at least TWO snapshots of the same
    (player, market, book) with different numbers. One snapshot is not a
    low reading, it is no reading: a prop pulled once a day is invisible
    to this instrument forever, however much it moved in between.

    So the binding constraint on measuring the veto is usually the PULL
    CADENCE, not the sample of bets. Saying "14 of 3,366" without saying
    which one is short sends you off to wait for more bets when more bets
    will not help.
    """
    try:
        from engine.linemoves import load_history
        rows = load_history()
    except Exception:                                       # noqa: BLE001
        return
    if not rows:
        return
    series: dict = {}
    for r in rows:
        k = (r.get("player"), r.get("market"), r.get("book"))
        series.setdefault(k, set()).add(
            (r.get("line"), r.get("over_odds"), r.get("under_odds")))
    once = sum(1 for v in series.values() if len(v) < 2)
    many = len(series) - once
    if not series:
        return
    print("  SNAPSHOT DEPTH — can movement be SEEN at all?")
    print(f"    {many:,} of {len(series):,} (player, market, book) series have "
          f"two or more\n    distinct readings. The other {once:,} were "
          f"pulled once and can never\n    show movement, whatever they did.")
    if once > many:
        print("    ** CADENCE IS THE BINDING CONSTRAINT, not the bet count. "
              "More settled")
        print("    ** bets will not fix this; more pulls per day will. A "
              "second daily")
        print("    ** pull roughly doubles what is observable "
              "(`install-nightly.sh --pre-kickoff`).")
    print()


def report(conn, sport: str = "mlb") -> int:
    rows = load(conn, sport)
    stamped = [r for r in rows if r.get("move_delta") is not None]

    print("=" * 74)
    print("DOES LINE MOVEMENT EARN ITS VETO?")
    print("=" * 74)
    print(f"  {len(rows):,} settled {sport} bets, {len(stamped):,} carrying a "
          f"movement stamp")
    print()
    _snapshot_depth()

    if not stamped:
        print("  NOTHING TO MEASURE YET — and this is a real answer, not a bug.")
        print()
        print("  Nothing recorded what movement did to a pick until")
        print("  2026-08-07. The stamp lived on the in-memory recommendation,")
        print("  was rendered to the site, and was gone. Every row here")
        print("  predates the capture.")
        print()
        print("  Meanwhile apply_movement has been rejecting picks outright")
        print("  on a signal whose predictive value has never been measured —")
        print("  which is what its own caller's docstring gave as the reason")
        print("  for believing it was harmless.")
        print()
        print("  Run this again once a few slates have been journalled.")
        print(f"  It needs {MIN_SIDE} on each side to say anything.")
        print()
        return 0

    # From ALL rows, not from `stamped`. The comparison groups here are the
    # UNSTAMPED ones — "the market never moved on this prop" is the control
    # for "it moved against us", and filtering to stamped rows first empties
    # every control by construction. The first cut of this did exactly that
    # and reported "not enough on one side" against a journal that had
    # plenty, which is the quietest way for a diagnostic to be wrong.
    main = [r for r in rows if r.get("category") == "main"]
    loose = [r for r in rows if r.get("category") == "loose"]

    # --- the survivors ------------------------------------------------------
    print("-" * 74)
    print("AMONG PICKS THAT SURVIVED (category `main`)")
    print("-" * 74)
    g = split_by_movement(main)
    print(_line("movement against, survived", _rate(g["against"])))
    print(_line("movement with", _rate(g["with"])))
    print(_line("no movement seen", _rate(g["unseen"])))
    c = compare(g["against"], g["with"])
    if c["ok"]:
        print()
        print(f"  against minus with: {c['diff']:+.1%} ±{2 * c['se']:.1%}  "
              f"z {c['z']:+.2f}")
    print()
    print("  This is the WEAKER question. It can only see picks the veto")
    print("  did not kill, so it is conditioned on surviving and understates")
    print("  whatever is there, in either direction.")
    print()

    # --- the ones it killed -------------------------------------------------
    print("-" * 74)
    print("AMONG PICKS IT REJECTED (category `loose`)")
    print("-" * 74)
    killed = [r for r in loose if (r.get("move_delta") or 0) < 0]
    spared = [r for r in loose if r.get("move_delta") is None]
    print(_line("killed by movement", _rate(killed)))
    print(_line("near-missed for other reasons", _rate(spared)))
    k = compare(killed, spared)
    if not k["ok"]:
        print()
        print(f"  Not enough on one side ({len(killed)} killed, "
              f"{len(spared)} other) — {MIN_SIDE} needed each.")
        print()
        return 0

    print()
    print(f"  killed minus spared: {k['diff']:+.1%} ±{2 * k['se']:.1%}  "
          f"z {k['z']:+.2f}")
    print()
    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    # A veto pays if what it killed landed WORSE than what it spared.
    if k["diff"] <= -KEEP_VETO_PTS and k["z"] <= -2.0:
        print("  THE VETO EARNS ITS KEEP. The picks movement killed landed")
        print(f"  {abs(k['diff']):.1%} below the near-misses it spared, on the")
        print("  same nights and the same bar. It is finding losers.")
    elif k["diff"] >= KEEP_VETO_PTS and k["z"] >= 2.0:
        print("  THE VETO IS COSTING YOU. The picks movement killed landed")
        print(f"  {k['diff']:.1%} ABOVE the near-misses it spared. It has been")
        print("  removing the better half of a marginal bucket.")
        print("  apply_movement's rejection branch should come out.")
    else:
        print("  NOT SEPARABLE on this sample. The two groups are not")
        print("  distinguishable, so this says nothing either way — which")
        print("  is itself worth knowing about a signal currently holding a")
        print("  veto over the board on no evidence at all.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="mlb")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
