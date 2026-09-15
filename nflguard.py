#!/usr/bin/env python3
"""The NFL board's stopping rule, written down before it has a record.

    python3 nflguard.py
    python3 nflguard.py --sport cfb

Reads the journal. Writes nothing. Disables nothing.

WHY THIS EXISTS, AND WHY NOW
----------------------------
NFL prices through the SAME gate MLB does. `MARKET_TIER` is entirely NFL
markets — receptions tier 1, pass/rush/rec yards tier 2 — and they share
`TIER_MIN_EDGE` and `TIER_SHRINK` with everything else. So the window is
identical: a post-haircut edge between 2.5% and 5.0% in tier 1, 3.0% and
4.5% in tier 2.

barcheck.py showed what a 12-point over-claim does to a window that size:
an honest floor lands around three times the ceiling, and no bet can
satisfy both ends. If NFL over-claims the way MLB does, there is no honest
NFL board either.

MLB took **247 settled bets** to make that visible, and it was invisible
the whole way because the deep fitter — 282,862 samples — kept saying the
model was fine. It is blind to selection by construction (§2 of
docs/SELECTION_CORRECTION.md), and so was everything downstream of it.

NFL will not produce 247 bets until late in the season. Waiting for a
fixed sample means finding out in December. So this watches SEQUENTIALLY:
it looks after every week and fires the moment the evidence is there.

THE RULE, FIXED BEFORE THE FIRST NFL BET SETTLES
------------------------------------------------
This is the whole point of writing it in August. A stopping rule chosen
after seeing a season is not a stopping rule.

  * Look after each week, never before :data:`MIN_LOOK` settled bets.
  * The statistic is the cumulative calibration z: ``(Σp − wins) / √Σp(1−p)``.
    Positive means the board claimed more than it delivered.
  * Fire at :data:`BOUNDARY`.

**BOUNDARY is not a single-look z.** Looking every week and firing at 2.0
would false-alarm on roughly one honest season in ten — repeated looks
inflate it. 2.5 was chosen by simulating honest seasons and measuring:

  ==========  =======  ========  ========
  boundary    8/week   15/week   25/week
  ==========  =======  ========  ========
  z 2.00        8.9%      9.5%     11.8%
  z 2.50        3.2%      3.0%      4.3%
  z 3.00        0.7%      1.1%      1.5%
  ==========  =======  ========  ========

WHAT IT CAN AND CANNOT CATCH — measured, not hoped
---------------------------------------------------
Simulated over 1,200 seasons per cell, at the z 2.5 boundary:

  ============  =========  ============  ==============
  true gap      volume     caught        median at
  ============  =========  ============  ==============
  12 points     8/week     74%           72 bets (wk 9)
  12 points     15/week    96%           105 bets (wk 7)
  12 points     25/week    100%          100 bets (wk 4)
  8 points      15/week    64%           135 bets (wk 9)
  5 points      15/week    30%           150 bets (wk 10)
  ============  =========  ============  ==============

Read the bottom rows before trusting a quiet season. **A 5-point
over-claim will probably run all year undetected** — and 5 points is
already enough to invert the edge window (it needs a 7.5% floor against a
5.0% ceiling). Silence here is not proof the board is honest; it is only
proof that it is not catastrophically dishonest.

The top row is the one that matters: it catches MLB's failure mode around
**100 bets instead of 247**, mid-season instead of never.

WHAT FIRING MEANS
-----------------
It reports. It does not disable the board, and it must not: that is a
pricing change and belongs to a person. What it buys is that the person
finds out in week 7 rather than after the season, which is the entire
difference between this and what happened to MLB.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import ledger

#: Fire here. Calibrated by simulation against REPEATED weekly looks, not
#: chosen as a single-look significance level — see the module docstring.
#: Same value watch.py already pre-registered for the selection effect,
#: which is a coincidence of arithmetic rather than a shared derivation.
BOUNDARY = 2.5
#: No look before this many settled bets. An early look on a handful of
#: bets is where a sequential test spends its false alarms.
MIN_LOOK = 25


def load(conn, sport: str = "nfl") -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT date, market, hit_prob, status FROM bets "
        "WHERE sport=? AND category='main' AND status IN ('won','lost') "
        "AND hit_prob IS NOT NULL ORDER BY date, rowid", (sport,))]


def path(rows: list[dict]) -> list[dict]:
    """The running z after each date, which is when a look happens.

    Grouped by DATE rather than by bet: a look after every individual
    settle is more looks than the boundary was calibrated for, and would
    quietly raise the false-alarm rate above the number in the docstring.
    """
    looks, sum_p, sum_var, wins, n = [], 0.0, 0.0, 0, 0
    for date in sorted({r["date"] for r in rows if r.get("date")}):
        for r in [x for x in rows if x["date"] == date]:
            p = float(r["hit_prob"])
            sum_p += p
            sum_var += p * (1 - p)
            wins += 1 if r["status"] == "won" else 0
            n += 1
        if n < MIN_LOOK or sum_var <= 0:
            continue
        looks.append({"date": date, "n": n,
                      "claimed": sum_p / n, "landed": wins / n,
                      "gap": (sum_p - wins) / n,
                      "z": (sum_p - wins) / math.sqrt(sum_var)})
    return looks


def verdict(looks: list[dict]) -> tuple[str, dict | None]:
    """First crossing wins — that is what sequential means. A later look
    falling back under the boundary does not un-fire it."""
    for lk in looks:
        if lk["z"] >= BOUNDARY:
            return "FIRED", lk
    return ("WATCHING" if looks else "TOO EARLY"), (looks[-1] if looks else None)


def report(conn, sport: str = "nfl") -> int:
    rows = load(conn, sport)
    looks = path(rows)
    state, lk = verdict(looks)

    print("=" * 74)
    print(f"{sport.upper()} BOARD — SEQUENTIAL OVER-CLAIM GUARD")
    print("=" * 74)
    print(f"  rule fixed in advance: look after each date once {MIN_LOOK}+ bets"
          f" have settled, fire at z {BOUNDARY}")
    print(f"  {len(rows):,} settled {sport} recommendations, {len(looks)} look(s)")
    print()

    if state == "TOO EARLY":
        print(f"  TOO EARLY — under {MIN_LOOK} settled bets, so no look has")
        print("  happened. This is the intended state before Week 1 and says")
        print("  nothing about the model.")
        print()
        return 0

    print("   date          bets   claimed    landed      gap       z")
    print("   " + "-" * 56)
    for x in looks[-8:]:
        print(f"   {x['date']:12} {x['n']:6}   {x['claimed']:6.1%}   "
              f"{x['landed']:6.1%}   {x['gap']:+6.1%}  {x['z']:+6.2f}")
    print()

    print("=" * 74)
    print(f"VERDICT: {state}")
    print("=" * 74)
    if state == "FIRED":
        print(f"  Crossed z {BOUNDARY} on {lk['date']} at {lk['n']} bets: claimed")
        print(f"  {lk['claimed']:.1%}, landed {lk['landed']:.1%}, gap "
              f"{lk['gap']:+.1%}.")
        print()
        print("  The board is claiming more than it delivers, established on")
        print("  its own record rather than inferred from MLB's. Read")
        print("  barcheck.py next: if the gap exceeds 2.5 points, no edge")
        print("  floor exists that is both high enough to be honest and low")
        print("  enough to be believed, and the question stops being how to")
        print("  tune the gate.")
        print()
        print("  NOTHING HAS BEEN DISABLED. That is a pricing change and it")
        print("  belongs to a person. What this bought is finding out now")
        print("  instead of after the season, which is the whole difference")
        print("  between this and what happened to MLB.")
    else:
        print(f"  No look has reached z {BOUNDARY}. Latest: {lk['n']} bets, "
              f"gap {lk['gap']:+.1%}, z {lk['z']:+.2f}.")
        print()
        print("  Read this narrowly. At this boundary a 12-point over-claim is")
        print("  caught in most seasons, an 8-point one about two thirds of")
        print("  the time, and a 5-point one usually not at all — while a")
        print("  5-point gap is already enough to invert the edge window.")
        print("  Quiet means not catastrophically dishonest. It does not mean")
        print("  honest.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="nfl")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
