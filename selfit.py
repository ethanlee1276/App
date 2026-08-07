#!/usr/bin/env python3
"""Fit the selection correction, and try to fail it out of sample.

    python3 selfit.py                   # fit, hold out, report. Writes nothing.
    python3 selfit.py --sport mlb

This is steps 2 and 3 of docs/SELECTION_CORRECTION.md §10. It does NOT
apply anything and does not touch any store — step 4 is a separate
decision, and §8 says out loud that applying this may empty the board.

WHY THERE IS A HELD-OUT HALF AT ALL
-----------------------------------
A temperature fitted on a sample will improve that sample. That is what
fitting is; it demonstrates nothing. `guardfit` already produced one
confident recommendation off an in-sample fit that turned out to be an
artifact of forcing a line through a hinge, and the only reason it was
caught was that somebody checked the model against data it had not seen.

So the journal is split by date. The correction is fitted on the earlier
half and measured on the later half, which it has never touched.

THE BAR, WRITTEN DOWN BEFORE THE ANSWER
---------------------------------------
Chosen from the arithmetic, not from the result. The held-out half is
about 124 bets claiming near 58%, so the 2-sigma bar on its gap is roughly

    2 * sqrt(0.58 * 0.42 / 124) = +/- 8.9 points

which is wide enough that "it got a bit better" would be indistinguishable
from noise. Hence :data:`PASS_GAP` and :data:`FAIL_GAP`:

  * held-out gap falls below **+5.0 points** AND at least half the original
    gap is gone -> PASS. Ship-able, subject to §6's caps.
  * held-out gap stays at or above **+8.0 points** -> FAIL. The correction
    is fitting noise. §9 says abandon.
  * anything between -> INCONCLUSIVE. Not a soft pass. Wait for bets.

These constants are the contract. Changing them after seeing a run is
exactly the move this file exists to prevent, so they live at the top
where a diff shows them moving.

HOW OFTEN THIS TEST IS RIGHT — measured, not assumed
----------------------------------------------------
Simulated over 300 synthetic journals with claims spread 0.50-0.70, which
is roughly the real board's shape:

  ================================  ======  =============  ======
  truth                             PASS    INCONCLUSIVE   FAIL
  ================================  ======  =============  ======
  a real 12-point over-claim, 124   55%     26%            15%
  a real 12-point over-claim, 250   70%     20%             9%
  honest model (no over-claim)       6%      5%            11%
  ================================  ======  =============  ======

(The honest row's remaining 79% is NOTHING TO CORRECT, which is the right
answer there.)

Read that before reading any verdict this prints. **At the journal's
current size the test finds a real effect only about half the time**, and
it returns FAIL on a genuinely correctable one 15% of the time. A FAIL is
therefore not proof the correction is worthless; it is one draw. A PASS is
worth more, because the false-positive rate on an honest model is 6%.

The other thing that simulation showed: the fitted temperature is barely
identified at this sample size. Its 5th-95th range across those runs was
**0.70 to 6.00** — the top of which is the search grid's ceiling, i.e. no
answer at all. §6's cap is not a nicety; it is load-bearing, and a fit
that lands on the boundary should never be shipped.

WHAT IT FITS
------------
One pooled (S, c) per sport, not per market — §5. Selection bias is a
property of the selection process, not of the market, and 247 bets will
not support four separate pairs.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import calibrate as cal
from engine import journalfit as jf
from engine import ledger

#: Held-out gap below this, with at least HALVED of the gap removed, passes.
PASS_GAP = 0.050
#: Held-out gap at or above this fails outright.
FAIL_GAP = 0.080
#: …and a pass must also remove at least this share of the original gap.
#: Without it, a journal that started at +5.5 points could "pass" by not
#: moving at all.
HALVED = 0.50
#: Fewer than this on either side of the date split and the comparison is
#: not worth running. Well below journalfit's 200: this is a diagnostic
#: that ships nothing, and the alternative to a wide-barred answer here is
#: no answer at all.
MIN_SIDE = 80


def load(conn, sport: str, category: str = "main") -> list[dict]:
    """Settled, journalled, carrying a claim and a date. Selected side only.

    The correction is FOR the selected population — that is the whole
    hypothesis — so `loose` is not training data. It reappears later as a
    control, never as a fit input.
    """
    q = ("SELECT sport, market, side, hit_prob, status, date, ts "
         "FROM bets WHERE status IN ('won','lost') AND hit_prob IS NOT NULL "
         "AND category=?")
    args: list = [category]
    if sport and sport != "all":
        q += " AND sport=?"
        args.append(sport)
    rows = [dict(r) for r in conn.execute(q, args)]
    return sorted((r for r in rows if r.get("date")), key=lambda r: r["date"])


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split by DATE, never by row index.

    Splitting on the row index would cut a slate in half and put the same
    night on both sides of the boundary. Nights are correlated — one
    pitcher, one park, one weather — so that leaks the thing being held
    out. Whole dates only, at the date closest to a 50/50 split.
    """
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    best, best_diff = dates[0], len(rows)
    for d in dates[1:]:
        n_early = sum(1 for r in rows if r["date"] < d)
        diff = abs(n_early - (len(rows) - n_early))
        if diff < best_diff:
            best, best_diff = d, diff
    return ([r for r in rows if r["date"] < best],
            [r for r in rows if r["date"] >= best])


def _pairs(rows: list[dict]) -> list[tuple[float, int]]:
    """Restated as P(over), the one quantity the fit runs on."""
    out = []
    for r in rows:
        pair = jf.as_over(r["hit_prob"], r["side"], r["status"])
        if pair is not None:
            out.append(pair)
    return out


def corrected(r: dict, temp: float, icept: float) -> float:
    """A row's claim with the selection layer applied, back in its own
    orientation.

    The fit lives in P(over) space; a bet on the UNDER claims 1-p there and
    must come back through the same mirror, or the correction lands with
    the wrong sign on half the board.
    """
    p = float(r["hit_prob"])
    side = (r.get("side") or "").strip().lower()
    if side.startswith("u"):
        return 1.0 - cal.apply_temperature(1.0 - p, temp, icept)
    return cal.apply_temperature(p, temp, icept)


def measure(rows: list[dict], temp: float = 1.0, icept: float = 0.0) -> dict:
    """Claimed vs landed, with the Poisson-binomial bar — same statistic
    selcheck reports, so the two can be read against each other."""
    n = len(rows)
    if not n:
        return {"n": 0, "claimed": 0.0, "landed": 0.0, "gap": 0.0, "se": 0.0}
    ps = [corrected(r, temp, icept) for r in rows]
    claimed = sum(ps) / n
    landed = sum(1 for r in rows if r["status"] == "won") / n
    var = sum(p * (1 - p) for p in ps)
    return {"n": n, "claimed": claimed, "landed": landed,
            "gap": claimed - landed,
            "se": math.sqrt(var) / n if var > 0 else 0.0}


def verdict(before: float, after: float) -> tuple[str, str]:
    """The pre-registered decision. No arguments beyond the two numbers, so
    it cannot quietly consult anything else.

    **Every bar here is on the ABSOLUTE gap, and the first cut of this
    function got that wrong.** It compared the signed gap against a
    positive threshold, so driving the claim far BELOW what landed counted
    as success: a synthetic where the model over-claimed early and was
    honest later had the correction take a clean -1.1% held-out gap to
    -18.2%, and the verdict called it INCONCLUSIVE rather than harmful. An
    under-claim is not a free lunch — it is the same miscalibration with
    the sign flipped, and it silently kills good bets instead of taking bad
    ones. Same absolute-vs-relative family of fault as the loss miner's
    closure bar and the Lab's ROI tile.
    """
    b, a = abs(before), abs(after)
    removed = (b - a) / b if b > 0 else 0.0
    # Damage is checked BEFORE "nothing to correct", and the order matters:
    # the first cut had them the other way round, so a correction that took
    # an already-honest -1.1% held-out half to -18.2% was excused as having
    # nothing to demonstrate. Wrecking a clean half is the loudest possible
    # failure, not an absence of evidence.
    #
    # "Materially" is what keeps that from being hair-trigger: a gap that
    # drifts from +1.0% to +1.5% is worse and means nothing, so the damage
    # must also carry the result past the pass line before it convicts.
    if a > b and a >= PASS_GAP:
        return "FAIL", (f"the correction made the held-out half WORSE: "
                        f"{before:+.1%} -> {after:+.1%}")
    if b < PASS_GAP:
        return "NOTHING TO CORRECT", (
            f"the held-out half was already within {PASS_GAP:.1%} "
            f"({before:+.1%}); this journal cannot demonstrate anything")
    if a >= FAIL_GAP:
        return "FAIL", (f"held-out gap {after:+.1%} is {a:.1%} from honest, "
                        f"at or past the {FAIL_GAP:.1%} fail line")
    if a < PASS_GAP and removed >= HALVED:
        return "PASS", (f"held-out gap {after:+.1%} is within {PASS_GAP:.1%} "
                        f"of honest and {removed:.0%} of the miss is gone")
    return "INCONCLUSIVE", (
        f"held-out gap {after:+.1%} sits between the bars "
        f"({PASS_GAP:.1%} / {FAIL_GAP:.1%}); {removed:.0%} of the miss removed")


def report(conn, sport: str = "mlb") -> int:
    rows = load(conn, sport)
    if len(rows) < 2 * MIN_SIDE:
        print(f"Need {2 * MIN_SIDE} settled selected bets; have {len(rows)}.")
        return 0
    early, late = split(rows)
    if len(early) < MIN_SIDE or len(late) < MIN_SIDE:
        print(f"Date split is too lopsided: {len(early)} early, {len(late)} "
              f"late, and {MIN_SIDE} is the minimum per side.")
        return 0

    print("=" * 74)
    print(f"SELECTION CORRECTION — fit on the past, tested on the future")
    print("=" * 74)
    print(f"  {sport}   {len(rows)} settled selected bets   "
          f"{rows[0]['date']} to {rows[-1]['date']}")
    print(f"  fit on   {len(early):4} bets  {early[0]['date']} to {early[-1]['date']}")
    print(f"  held out {len(late):4} bets  {late[0]['date']} to {late[-1]['date']}")
    print()
    print(f"  BAR, fixed before this ran:  pass under {PASS_GAP:.1%} with "
          f"{HALVED:.0%}+ removed;  fail at {FAIL_GAP:.1%}+")
    print()

    pairs = _pairs(early)
    if len(pairs) < MIN_SIDE:
        print(f"  Only {len(pairs)} of {len(early)} early bets could be "
              f"restated as P(over) — nothing to fit.")
        return 0
    c = cal.fit(pairs, sport=sport, market="selection", min_samples=MIN_SIDE)
    print("=" * 74)
    print("WHAT THE EARLY HALF ASKS FOR")
    print("=" * 74)
    print(f"  temperature {c.temperature:.4f}   intercept {c.intercept:+.4f}"
          f"   on {c.samples} bets")
    print(f"  Brier {c.brier_before:.5f} -> {c.brier_after:.5f}")
    if c.at_boundary:
        print("  ** the fit ran to the edge of the search grid. That is not a")
        print("     parameter, it is a failure to converge, and §6's cap would")
        print("     be binding immediately. Treat what follows as suspect. **")
    print()

    for label, part in (("early (fitted on)", early), ("held out", late)):
        b = measure(part)
        a = measure(part, c.temperature, c.intercept)
        print(f"  {label:20} n {b['n']:4}   "
              f"gap {b['gap']:+6.1%} -> {a['gap']:+6.1%}   "
              f"(2σ ±{2 * a['se']:.1%})")
    print()
    print("  The first line is the correction grading its own homework and is")
    print("  expected to improve. Only the second line is evidence.")
    print()

    b_late = measure(late)
    a_late = measure(late, c.temperature, c.intercept)
    v, why = verdict(b_late["gap"], a_late["gap"])
    print("=" * 74)
    print(f"VERDICT: {v}")
    print("=" * 74)
    print(f"  {why}")
    print()
    if v == "PASS":
        print("  Next is step 4, and it is a decision rather than a script:")
        print("  §8 says correcting a 12-point over-claim honestly may not")
        print("  trim the board but empty it. That is the correct outcome if")
        print("  the measurement is right, and it should be chosen on purpose.")
    elif v == "FAIL":
        print("  §9: the held-out gap did not close, so the correction is")
        print("  fitting noise. Do not apply it. The over-claim is real —")
        print("  guardfit and selcheck both measure it — but this is not")
        print("  the instrument for it.")
    else:
        print("  Not a soft pass. The honest reading is that this journal")
        print("  cannot yet tell a working correction from a lucky one, and")
        print("  the answer is more settled bets rather than a decision.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="mlb")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
