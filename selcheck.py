#!/usr/bin/env python3
"""Is the over-claim selection bias, or is it something else?

    python3 selcheck.py                     # MLB, main category
    python3 selcheck.py --sport all --category all

`guardfit` measured the shipped claim running about 12 points hot at every
price band — the same size at 42% implied as at 77%, so it is a level and
not a favourite problem. `docs/SELECTION_CORRECTION.md` proposes one
explanation: we bet the props where our number disagrees most with the
book, and a big disagreement happens either because we know something or
because our estimation error happened to be positive. Conditional on
selection that error no longer averages to zero, so the claim runs hot on
the bets placed while staying honest on the population the deep fitter
measured.

**This script exists to try to kill that explanation before anything is
built on it.** Several other faults produce an identical 12-point signature
and would be made worse by a selection shrink:

  * pricing against a line that has already moved
  * a de-vig or `fair` construction that is wrong
  * grading errors
  * a market-shrink weight that is simply too weak

Selection makes a prediction none of those make.

THE TEST
--------
A bet we thought had 2 points of edge was barely selected. One we thought
had 12 was selected precisely BECAUSE the error was large. So the curse
has to grow with the claimed edge:

    gap rising with claimed edge  → selection. proceed.
    gap flat in claimed edge      → a level error from something else,
                                    and a shrink is the wrong instrument.

The slope is fitted with a free intercept, deliberately. `guardfit` forced
its line through a hinge and converted a level into a slope, which is how
it came to recommend raising a favourite surcharge for a miscalibration
that every price shares. The intercept here is the level; the slope is the
thing being tested; they are reported apart.

THE SECOND PREDICTION
---------------------
Selection bias scales with estimation NOISE — the noisier the model in a
market, the more its selected subset is chosen on error rather than
signal. `ratecheck` measured strikeouts-per-out swinging 46.8% between
starts, which is very noisy, and the pitcher family is the worst-performing
one in the journal. So the by-market table below is a second, independent
look: the gap should be widest where the model is least sure.

Both predictions have to hold. One out of two is not a confirmation.

Reads the journal only. Writes nothing, prices nothing.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import ledger

#: Edge buckets, in points of claimed edge. The board's own bar sits near
#: 2-3 points, so the interesting range is narrow and the buckets are too.
EDGE_EDGES = [0.0, 0.02, 0.04, 0.06, 0.09, 0.13, 1.0]
#: A bucket thinner than this is printed but never fitted.
MIN_BUCKET_N = 20
#: Below this many settled bets, no verdict is offered at all.
MIN_TOTAL_N = 150


def load(conn, sport=None, category="main") -> list[dict]:
    q = ("SELECT sport, market, side, odds, hit_prob, edge, status "
         "FROM bets WHERE status IN ('won','lost') "
         "AND hit_prob IS NOT NULL AND edge IS NOT NULL")
    args: list = []
    if category != "all":
        q += " AND category=?"
        args.append(category)
    if sport and sport != "all":
        q += " AND sport=?"
        args.append(sport)
    return [dict(r) for r in conn.execute(q, args)]


def _stats(rs: list[dict]) -> dict:
    """Claimed vs landed for one group, with the Poisson-binomial error.

    The variance is the sum of p(1-p) over the bets' own claims rather
    than n*p̄(1-p̄): each bet is its own Bernoulli trial with its own
    probability, and pooling them into one average first understates the
    spread on a group whose claims vary.
    """
    n = len(rs)
    claimed = sum(float(b["hit_prob"]) for b in rs) / n
    landed = sum(1 for b in rs if b["status"] == "won") / n
    var = sum(float(b["hit_prob"]) * (1 - float(b["hit_prob"])) for b in rs)
    return {"n": n, "claimed": claimed, "landed": landed,
            "gap": claimed - landed,
            "se": (math.sqrt(var) / n) if var > 0 else 0.0}


def buckets(rows: list[dict]) -> list[dict]:
    groups: dict = {}
    for b in rows:
        e = float(b["edge"])
        for lo, hi in zip(EDGE_EDGES, EDGE_EDGES[1:]):
            if lo <= e < hi:
                groups.setdefault((lo, hi), []).append(b)
                break
    out = []
    for (lo, hi), rs in sorted(groups.items()):
        s = _stats(rs)
        s.update({"lo": lo, "hi": hi,
                  "edge": sum(float(b["edge"]) for b in rs) / len(rs)})
        out.append(s)
    return out


def fit_line(bs: list[dict]) -> dict:
    """Weighted least squares of gap on claimed edge, WITH an intercept.

    The intercept is the level — how hot the claim runs at zero edge — and
    the slope is the selection effect. Forcing the line through the origin
    would hand the whole level to the slope and manufacture the very
    finding this script is meant to be able to reject.
    """
    pts = [b for b in bs if b["n"] >= MIN_BUCKET_N and b["se"] > 0]
    if len(pts) < 3:
        return {"slope": None, "bands": len(pts),
                "n": sum(b["n"] for b in pts)}
    w = [1.0 / b["se"] ** 2 for b in pts]
    x = [b["edge"] for b in pts]
    y = [b["gap"] for b in pts]
    sw = sum(w)
    mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
    my = sum(wi * yi for wi, yi in zip(w, y)) / sw
    sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
    if sxx <= 0:
        return {"slope": None, "bands": len(pts),
                "n": sum(b["n"] for b in pts)}
    sxy = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y))
    slope = sxy / sxx
    return {"slope": slope, "se": math.sqrt(1.0 / sxx),
            "intercept": my - slope * mx,
            "bands": len(pts), "n": sum(b["n"] for b in pts)}


def by_market(rows: list[dict]) -> list[dict]:
    groups: dict = {}
    for b in rows:
        groups.setdefault(f"{b['sport']}:{b['market']}", []).append(b)
    out = []
    for key, rs in groups.items():
        if len(rs) < MIN_BUCKET_N:
            continue
        s = _stats(rs)
        s["key"] = key
        out.append(s)
    return sorted(out, key=lambda s: -s["gap"])


def report(rows: list[dict]) -> int:
    if len(rows) < MIN_TOTAL_N:
        print(f"Only {len(rows)} settled bets carry a claim and an edge. "
              f"Need {MIN_TOTAL_N} before this test says anything.")
        return 0

    bs = buckets(rows)
    print("=" * 74)
    print("THE GAP, BY HOW MUCH EDGE WE THOUGHT WE HAD")
    print("=" * 74)
    print("  claimed edge      n   claimed   landed      gap       ±")
    print("  " + "-" * 60)
    for b in bs:
        hi = "+" if b["hi"] >= 1.0 else f"–{b['hi'] * 100:.0f}%"
        thin = "  (thin)" if b["n"] < MIN_BUCKET_N else ""
        print(f"  {b['lo'] * 100:4.0f}%{hi:<6} {b['n']:6}   "
              f"{b['claimed']:6.1%}   {b['landed']:6.1%}   "
              f"{b['gap']:+6.1%}   {2 * b['se']:5.1%}{thin}")
    print()
    print("  Gap is claimed minus landed: positive means the model claimed")
    print("  more than it delivered. Selection predicts this GROWS to the")
    print("  right; every other explanation predicts a flat column.")
    print()

    f = fit_line(bs)
    print("=" * 74)
    print("DOES THE GAP GROW WITH THE EDGE WE CLAIMED?")
    print("=" * 74)
    if f["slope"] is None:
        print(f"  Not enough buckets clear {MIN_BUCKET_N} bets to fit a line "
              f"({f['bands']} usable). No verdict.")
        return 0
    z = f["slope"] / f["se"] if f["se"] else 0.0
    print(f"  level  (gap at zero claimed edge)   {f['intercept']:+.1%}")
    print(f"  slope  (extra gap per point of edge) {f['slope']:+.2f}  "
          f"±{2 * f['se']:.2f} (2σ)   z {z:+.2f}")
    print(f"  on {f['n']:,} bets in {f['bands']} buckets")
    print()
    if z >= 2.0:
        print("  → CONSISTENT WITH SELECTION. The gap widens where we")
        print("    claimed more edge, which is the winner's curse and is")
        print("    what nothing else on the suspect list predicts.")
        print("    Proceed to the by-market check below; BOTH have to hold.")
    elif z <= -2.0:
        print("  → BACKWARDS. The gap SHRINKS where we claimed more edge,")
        print("    which selection cannot produce. Something else is wrong,")
        print("    and a selection shrink would be the wrong instrument.")
    else:
        print("  → NOT SELECTION, on this evidence. The gap is flat in")
        print("    claimed edge, so the over-claim is a LEVEL error coming")
        print("    from somewhere else — stale lines, the de-vig, grading,")
        print("    or a market shrink that is too weak. Do not build the")
        print("    correction in docs/SELECTION_CORRECTION.md; go find it.")
        print(f"    (The level itself is {f['intercept']:+.1%} and real.)")
    print()

    ms = by_market(rows)
    if ms:
        print("=" * 74)
        print("THE SECOND PREDICTION — widest where the model is least sure")
        print("=" * 74)
        print("  market                     n   claimed   landed      gap")
        print("  " + "-" * 58)
        for m in ms:
            print(f"  {m['key']:22} {m['n']:6}   {m['claimed']:6.1%}   "
                  f"{m['landed']:6.1%}   {m['gap']:+6.1%}")
        print()
        print("  ratecheck measured pitcher strikeout RATE swinging 46.8%")
        print("  between starts — the noisiest thing the model estimates.")
        print("  Selection predicts pitcher markets sit at the top of this")
        print("  table. If they do not, that is evidence against it.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="mlb", help="sport, or 'all'")
    p.add_argument("--category", default="main",
                   help="journal category, or 'all'")
    a = p.parse_args(argv)
    conn = ledger.connect()
    return report(load(conn, sport=a.sport, category=a.category))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
