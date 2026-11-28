#!/usr/bin/env python3
"""Can a higher edge bar fix a 12-point over-claim? Arithmetic first.

    python3 barcheck.py
    python3 barcheck.py --sport mlb

Writes nothing. Changes nothing. This is the dry run that was supposed to
come before any decision about raising the gate.

THE ANSWER IS NO, AND IT DOES NOT NEED THE JOURNAL TO SEE IT
------------------------------------------------------------
The gate allows a post-haircut edge inside a window with two ends. The
floor is :data:`engine.quality.TIER_MIN_EDGE`. The ceiling is
:data:`engine.betting.MAX_CREDIBLE_EDGE` times the tier's shrink — beyond
that a disagreement is treated as bad data rather than alpha, which is
correct and is not in question here.

    tier 1:  2.5%  to  5.0%     a 2.5-point window
    tier 2:  3.0%  to  4.5%     a 1.5-point window

The model has been claiming about 12 points more than it delivers.
guardfit measured it by price band (+10.0% below the 55% hinge on 99 bets,
+13.8% above on 138); selcheck's four adjustment schemes and its
within-book floor all land between +9.1% and +13.6%.

An honest bar has to cover that gap: require ``bar + gap`` before betting.

    tier 1:  needs 14.5%,  ceiling is 5.0%   — short by 9.5 points
    tier 2:  needs 15.0%,  ceiling is 4.5%   — short by 10.5 points

**The required bar is about three times the largest edge the model is
permitted to claim.** The window is not narrowed by this, it is inverted:
there is no edge value that is simultaneously big enough to survive an
honest bar and small enough to be believed. Every bet fails one end or the
other.

So "raise the edge bar" is not a conservative version of the current
system. It is arithmetically the same as switching the board off, and
§8 of docs/SELECTION_CORRECTION.md predicted exactly that in words.

WHAT THAT MEANS, SAID PLAINLY
-----------------------------
The over-claim is not a threshold problem and cannot be fixed with one.
Either the CLAIMS come down — the calibration or selection correction,
which selfit.py currently cannot validate on 13 days of a drifting board
— or there is nothing on this board worth betting. Those are the two
branches. A higher bar is not a third.

THE TRAP THIS FILE REFUSES TO WALK INTO
---------------------------------------
Sweeping bars over settled history and picking the one with the best ROI
is the single most inviting mistake available here, and it would produce a
number that looks like a finding every time. 247 settled bets carry a 2σ
bar of ±6.3 points; the best of a dozen retrospective subsets is a
maximum-of-draws, not a measurement.

So the sweep below is printed as CONTEXT and this file never names a
recommended bar. The only bar it computes is DERIVED — the current floor
plus the measured gap — which is arithmetic, not a fit.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import ledger
from engine.betting import MAX_CREDIBLE_EDGE
from engine.quality import TIER_MIN_EDGE, TIER_SHRINK

#: Bars to show, as multiples of the tier floor. Context for reading the
#: curve's shape — explicitly NOT a menu to choose from.
SWEEP = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
#: Below this a survivor row is not worth quoting.
MIN_ROW = 20


def window(tier: int) -> tuple[float, float]:
    """(floor, ceiling) of the post-haircut edge the gate accepts."""
    return TIER_MIN_EDGE[tier], MAX_CREDIBLE_EDGE * TIER_SHRINK[tier]


def honest_bar(tier: int, gap: float) -> dict:
    """What the floor would have to be, and whether that is reachable.

    `reachable` is the whole report. A bar above the credibility ceiling
    does not make the board smaller — it makes it empty, because no edge
    can satisfy both ends at once.
    """
    lo, hi = window(tier)
    need = lo + gap
    return {"tier": tier, "floor": lo, "ceiling": hi, "need": need,
            "reachable": need <= hi, "short": need - hi}


def load(conn, sport=None) -> list[dict]:
    q = ("SELECT sport, market, hit_prob, edge, status, stake_units, "
         "pnl_units FROM bets WHERE status IN ('won','lost') "
         "AND category='main' AND edge IS NOT NULL AND hit_prob IS NOT NULL")
    args: list = []
    if sport and sport != "all":
        q += " AND sport=?"
        args.append(sport)
    return [dict(r) for r in conn.execute(q, args)]


def measured_gap(rows: list[dict]) -> dict:
    """Claimed minus landed on the settled board, Poisson-binomial error."""
    n = len(rows)
    if not n:
        return {"n": 0, "gap": 0.0, "se": 0.0}
    claimed = sum(float(r["hit_prob"]) for r in rows) / n
    landed = sum(1 for r in rows if r["status"] == "won") / n
    var = sum(float(r["hit_prob"]) * (1 - float(r["hit_prob"])) for r in rows)
    return {"n": n, "claimed": claimed, "landed": landed,
            "gap": claimed - landed,
            "se": math.sqrt(var) / n if var > 0 else 0.0}


def survivors(rows: list[dict], bar: float) -> dict:
    """Who clears `bar`, and what they did. Raising a bar is a pure subset
    operation on the journal, which is why this can be read at all — no
    bet that failed the old bar is being invented back in."""
    kept = [r for r in rows if float(r["edge"] or 0) >= bar]
    staked = sum(float(r["stake_units"] or 0) for r in kept)
    pnl = sum(float(r["pnl_units"] or 0) for r in kept)
    won = sum(1 for r in kept if r["status"] == "won")
    return {"bar": bar, "n": len(kept), "won": won,
            "landed": (won / len(kept)) if kept else 0.0,
            "staked": staked, "pnl": pnl,
            "roi": (pnl / staked) if staked else 0.0}


def report(conn, sport: str = "mlb") -> int:
    print("=" * 74)
    print("CAN A HIGHER EDGE BAR FIX THE OVER-CLAIM?")
    print("=" * 74)
    print("  The gate accepts a post-haircut edge between a floor and a")
    print("  credibility ceiling. Both ends are already in the code.")
    print()
    print("   tier    floor   ceiling   window")
    print("   " + "-" * 34)
    for t in (1, 2):
        lo, hi = window(t)
        print(f"    {t}     {lo:6.1%}    {hi:6.1%}   {100 * (hi - lo):5.1f} pts")
    print()

    rows = load(conn, sport)
    g = measured_gap(rows)
    if not g["n"]:
        print(f"  No settled {sport} recommendations on this machine, so the")
        print("  gap below is the one measured previously rather than read")
        print("  from the journal. The arithmetic does not depend on it.")
        gap = 0.12
    else:
        gap = g["gap"]
        print(f"  Measured on {g['n']:,} settled {sport} recommendations:")
        print(f"    claimed {g['claimed']:.1%}, landed {g['landed']:.1%}, "
              f"gap {gap:+.1%} ±{2 * g['se']:.1%}")
        print()

    print("=" * 74)
    print("WHAT AN HONEST FLOOR WOULD HAVE TO BE")
    print("=" * 74)
    print("  A bet is only worth taking if the edge survives the over-claim,")
    print("  so the floor has to cover it: floor + gap.")
    print()
    empty = []
    for t in (1, 2):
        h = honest_bar(t, gap)
        verdict = "reachable" if h["reachable"] else \
            f"IMPOSSIBLE — short by {100 * h['short']:.1f} points"
        print(f"    tier {t}: need {h['need']:6.1%}   ceiling {h['ceiling']:6.1%}"
              f"   {verdict}")
        if not h["reachable"]:
            empty.append(t)
    print()

    if empty:
        print("  → THE WINDOW IS NOT NARROWED, IT IS INVERTED.")
        print("    No edge is simultaneously big enough to survive an honest")
        print("    floor and small enough to be believed. Every candidate")
        print("    fails one end or the other, so raising the bar is")
        print("    arithmetically the same as switching the board off.")
        print()
        print("    This is not a conservative setting. It is the two real")
        print("    branches showing themselves: either the CLAIMS come down")
        print("    (the calibration or selection correction), or there is")
        print("    nothing on this board worth betting. A higher bar is not")
        print("    a third option.")
    else:
        print("  → An honest floor sits inside the credibility window. Raising")
        print("    the bar is a real option; read the survivor curve below")
        print("    for what it costs in volume.")
    print()

    if not rows:
        return 0

    print("=" * 74)
    print("SURVIVORS AT HIGHER BARS — CONTEXT, NOT A MENU")
    print("=" * 74)
    base = TIER_MIN_EDGE[1]
    print("   bar        bets   landed    staked      P&L      ROI")
    print("   " + "-" * 52)
    for mult in SWEEP:
        s = survivors(rows, base * mult)
        if s["n"] < MIN_ROW:
            print(f"   {s['bar']:5.1%}   {s['n']:6}   (under {MIN_ROW}, not quoted)")
            continue
        print(f"   {s['bar']:5.1%}   {s['n']:6}   {s['landed']:6.1%}   "
              f"{s['staked']:7.2f}u  {s['pnl']:+7.2f}u  {s['roi']:+7.1%}")
    print()
    print("  DO NOT PICK THE BEST ROW. That is the whole reason this table")
    print("  is labelled context: these are nested subsets of one 247-bet")
    print("  journal carrying a 2-sigma bar around ±6 points, so the best of")
    print("  six retrospective cuts is a maximum-of-draws and would be a")
    print("  'finding' on data with no signal in it at all.")
    print()
    print("  The only bar this file computes is the DERIVED one above —")
    print("  floor plus measured gap — because that is arithmetic rather")
    print("  than a fit, and it comes out impossible.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="mlb")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
