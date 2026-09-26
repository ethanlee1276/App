#!/usr/bin/env python3
"""Is the favourite guard steep enough? Ask the record, don't argue.

    python3 guardfit.py                  # every settled bet
    python3 guardfit.py --sport mlb
    python3 guardfit.py --category all   # the paper buckets too

WHAT THE GUARD IS

engine/betting.favourite_surcharge charges extra net edge as the price
shortens:

    surcharge(odds) = FAV_GUARD_SLOPE x max(0, implied(odds) - FAV_GUARD_FROM)

with FROM = 0.55 and SLOPE = 0.18 today. It exists because the same edge
buys less at a short price — EV is edge x decimal odds, so 3% is worth
5.7% at -110 and 4.0% at -300 — while Kelly sizes the short bet larger for
that same edge. Both effects push the wrong way at once.

WHY THE SLOPE IS MEASURABLE RATHER THAN A TASTE

The gate passes a bet when its net edge beats the surcharge. If, at
implied probability q, this model's claims run over by g(q) points, then a
bet that passed at net n really had n - g(q), and the surcharge that would
have made the gate honest IS g(q). So:

    the right surcharge at a price = the calibration gap at that price

which is a number the journal already contains. This bands settled bets by
the implied probability of the price actually taken, measures the gap in
each band, and fits the slope through the hinge.

THE SELECTION QUESTION, AND WHY IT DOES NOT BITE HERE

Measured gaps are contaminated by the winner's curse — we bet where the
model's own noise ran high, so actuals regress. That normally makes a
measured bias untrustworthy. It does not here, because the guard is
applied to exactly the same selected population: the bets that clear a
gate are the ones this number has to be right about. Measuring on selected
bets is not a flaw in this particular fit, it is the point of it.

WHAT IT WILL NOT DO

Change the constant. It prints what the record supports, with the error on
the estimate, and says plainly when the shipped value is already inside
that interval — which on a young journal is the usual answer.
"""

from __future__ import annotations

import argparse
import math
import sys

#: Width of the implied-probability bands, in points. Narrow enough that a
#: slope has something to bite on, wide enough that a band is not noise.
BAND_PTS = 5
#: Bands thinner than this are shown but never fitted.
MIN_BAND_N = 15
#: Total bets above the hinge before a fitted slope is reported at all.
MIN_FIT_N = 60


def implied(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return (100.0 / (o + 100.0)) if o > 0 else (-o / (-o + 100.0))


def band_of(q: float) -> float:
    """Lower edge of the band, as a probability."""
    return math.floor(q * 100 / BAND_PTS) * BAND_PTS / 100.0


def load(conn, sport=None, category="main"):
    q = ("SELECT sport, market, side, odds, hit_prob, status "
         "FROM bets WHERE status IN ('won','lost') AND hit_prob IS NOT NULL")
    args = []
    if category != "all":
        q += " AND category=?"
        args.append(category)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    return [dict(r) for r in conn.execute(q, args)]


def bands(rows: list[dict]) -> list[dict]:
    """Per implied-probability band: what was claimed, what landed."""
    groups: dict = {}
    for b in rows:
        q = implied(b["odds"])
        if q is None:
            continue
        groups.setdefault(band_of(q), []).append((q, float(b["hit_prob"]),
                                                  b["status"] == "won"))
    out = []
    for lo, rs in sorted(groups.items()):
        n = len(rs)
        claimed = sum(p for _q, p, _w in rs) / n
        landed = sum(1 for _q, _p, w in rs if w) / n
        var = sum(p * (1 - p) for _q, p, _w in rs)
        out.append({
            "lo": lo, "hi": lo + BAND_PTS / 100.0, "n": n,
            "implied": sum(q for q, _p, _w in rs) / n,
            "claimed": claimed, "landed": landed,
            # Gap is CLAIMED minus LANDED, so positive = the model claimed
            # more than it delivered, which is the direction a surcharge
            # has to cover.
            "gap": claimed - landed,
            "se": (math.sqrt(var) / n) if var > 0 else 0.0,
        })
    return out


def fit_slope(rows: list[dict], hinge: float) -> dict:
    """Weighted least squares through the hinge: gap ≈ slope · (q − hinge).

    Through the hinge and not a free intercept, because that is the shape
    the guard actually has — zero below FROM, linear above. Fitting an
    intercept would produce a number the engine cannot express.
    """
    pts = [b for b in rows if b["implied"] > hinge
           and b["n"] >= MIN_BAND_N and b["se"] > 0]
    n_bets = sum(b["n"] for b in pts)
    if not pts or n_bets < MIN_FIT_N:
        return {"slope": None, "se": None, "n": n_bets, "bands": len(pts)}
    sxy = sxx = 0.0
    for b in pts:
        x = b["implied"] - hinge
        w = 1.0 / (b["se"] ** 2)
        sxy += w * x * b["gap"]
        sxx += w * x * x
    if sxx <= 0:
        return {"slope": None, "se": None, "n": n_bets, "bands": len(pts)}
    return {"slope": sxy / sxx, "se": math.sqrt(1.0 / sxx),
            "n": n_bets, "bands": len(pts)}


def report(rows: list[dict], hinge: float, shipped: float) -> int:
    if not rows:
        print("No settled bets with a claimed probability. Nothing to fit.")
        return 0
    bs = bands(rows)
    print("=" * 74)
    print("CALIBRATION BY PRICE — the gap a surcharge has to cover")
    print("=" * 74)
    print(f"  {'implied band':<16}{'n':>6}{'claimed':>10}{'landed':>9}"
          f"{'gap':>9}{'±':>8}")
    print("  " + "-" * 62)
    for b in bs:
        mark = "  ←hinge" if b["lo"] <= hinge < b["hi"] else ""
        thin = "" if b["n"] >= MIN_BAND_N else "  (thin)"
        print(f"  {b['lo']:.0%}–{b['hi']:.0%}{'':<8}{b['n']:>6}"
              f"{b['claimed']:>10.1%}{b['landed']:>9.1%}{b['gap']:>+9.1%}"
              f"{b['se']:>8.1%}{mark}{thin}")
    print()
    print(f"  Gap is claimed minus landed: positive means the model claimed")
    print(f"  more than it delivered, which is what a surcharge must cover.")

    f = fit_slope(bs, hinge)
    print()
    print("=" * 74)
    print(f"THE SLOPE ABOVE THE HINGE ({hinge:.0%} implied)")
    print("=" * 74)
    if f["slope"] is None:
        print(f"  Not enough above the hinge to fit: {f['n']} bets across "
              f"{f['bands']} usable band(s),")
        print(f"  floor is {MIN_FIT_N}. The shipped slope stands because "
              f"nothing here can move it.")
        return 0
    lo, hi = f["slope"] - 2 * f["se"], f["slope"] + 2 * f["se"]
    print(f"  fitted slope   {f['slope']:+.3f}   ±{2 * f['se']:.3f} (2σ)")
    print(f"  95% interval   {lo:+.3f} to {hi:+.3f}")
    print(f"  shipped slope  {shipped:+.3f}")
    print(f"  on {f['n']} bets in {f['bands']} band(s) above the hinge")
    print()
    if lo <= shipped <= hi:
        print("  → THE SHIPPED SLOPE IS INSIDE THE INTERVAL. The record")
        print("    cannot distinguish it from what it would fit, so there is")
        print("    no evidence to change it. That is the usual answer on a")
        print("    young journal and it is a real one.")
        # The number that turns "can't tell" into a plan. Error falls as
        # 1/sqrt(n), so the bets needed to resolve a given difference is
        # exact arithmetic rather than a guess — and it is usually large
        # enough to be worth knowing before anyone waits on it.
        print()
        print("    To resolve a difference of this size at two sigma:")
        for d, label in ((0.10, "a slope 0.10 out"),
                         (0.20, "a slope 0.20 out")):
            need = f["n"] * (2 * f["se"] / d) ** 2
            print(f"      {label:<18} needs ~{need:,.0f} bets above the "
                  f"hinge (have {f['n']:,})")
    elif shipped < lo:
        need = f["slope"] - shipped
        print(f"  → THE GUARD IS TOO SHALLOW, by {need:+.3f} and the record")
        print("    can show it. At the hinge that costs nothing; at 75%")
        print(f"    implied (−300) it is {need * (0.75 - hinge):.1%} of net edge")
        print("    the gate is letting through that it should not.")
        print()
        print("    That is a PRICING change: raising it removes bets from the")
        print("    board. Worth doing on this evidence, worth doing")
        print("    deliberately — engine/betting.FAV_GUARD_SLOPE.")
    else:
        print("  → THE GUARD IS TOO STEEP for what the record shows. It is")
        print("    refusing short-priced bets the journal says were fine.")
        print("    Loosening a guard is the direction to be careful in:")
        print("    being wrong here costs money rather than opportunity.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="What surcharge does the record actually support?")
    p.add_argument("--sport")
    p.add_argument("--category", default="main",
                   help="main (default) or 'all' to pool the paper buckets")
    p.add_argument("--db")
    a = p.parse_args(argv)

    from engine.betting import FAV_GUARD_FROM, FAV_GUARD_SLOPE
    from engine import ledger
    conn = ledger.connect(a.db) if a.db else ledger.connect()
    return report(load(conn, a.sport, a.category),
                  FAV_GUARD_FROM, FAV_GUARD_SLOPE)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
