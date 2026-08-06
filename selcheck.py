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

#: Buckets are QUANTILES of the observed edge, not fixed cut points.
#:
#: The first cut used fixed bands (0-2, 2-4, 4-6, 6-9, …) and on the real
#: journal it could not run: 242 of 243 bets sat inside 2-6% claimed edge
#: and one sat above, so only two bands cleared the floor and a line needs
#: three. The board's bar decides where its edges live, and a test whose
#: resolution is chosen in advance has no leverage wherever that turns out
#: to be. Splitting the observed distribution instead puts the same number
#: of bets in every bucket wherever it sits, which is what the slope needs.
TARGET_BUCKETS = 5
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


def buckets(rows: list[dict], target: int = TARGET_BUCKETS) -> list[dict]:
    """Equal-count buckets over the observed edge, sorted low to high.

    The count per bucket is chosen so none falls under MIN_BUCKET_N — a
    thin bucket is a wide error bar, and a wide error bar at the end of the
    range is exactly where a spurious slope comes from.
    """
    ordered = sorted(rows, key=lambda b: float(b["edge"]))
    if not ordered:
        return []
    k = max(1, min(target, len(ordered) // MIN_BUCKET_N))
    size = len(ordered) / k
    out = []
    for i in range(k):
        rs = ordered[int(round(i * size)):int(round((i + 1) * size))]
        if not rs:
            continue
        s = _stats(rs)
        s.update({"lo": float(rs[0]["edge"]), "hi": float(rs[-1]["edge"]),
                  "edge": sum(float(b["edge"]) for b in rs) / len(rs)})
        out.append(s)
    return out


def fit_line(bs: list[dict]) -> dict:
    """Weighted least squares of gap on claimed edge, WITH an intercept.

    The level and the slope are reported apart. Forcing the line through
    the origin would hand the whole level to the slope and manufacture the
    very finding this script is meant to be able to reject — which is
    exactly what guardfit did one script over.

    `level` is quoted at the CENTRE of the observed edges, not at zero,
    because zero is outside the data and an extrapolated intercept swings
    with a slope that may not be significant.
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
    # `level` is the gap at the CENTRE of the observed edges, not at zero.
    #
    # Zero is outside the data — the board's bar means no bet is placed
    # under about 2.4% claimed edge — so a regression intercept there is an
    # extrapolation, and it swings with a slope that is not significant.
    # On the real journal it read +26.4% against an actual average gap of
    # +12.1%, because a non-significant slope of -3.56 was extended back
    # across four points of edge nobody ever bet. Printed as "the level
    # itself, and real", that is a number someone could act on.
    return {"slope": slope, "se": math.sqrt(1.0 / sxx),
            "level": my, "at_edge": mx,
            "intercept_at_zero": my - slope * mx,
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
    print("  claimed edge        n   claimed   landed      gap       ±")
    print("  " + "-" * 62)
    for b in bs:
        rng = f"{b['lo'] * 100:.1f}–{b['hi'] * 100:.1f}%"
        thin = "  (thin)" if b["n"] < MIN_BUCKET_N else ""
        print(f"  {rng:<14} {b['n']:6}   "
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
              f"({f['bands']} usable). No verdict on selection.")
        print()
        # NOT a return. The by-market check below is an independent
        # prediction and stays readable when this one cannot run — the
        # first cut returned here and printed nothing else, which threw
        # away the half of the evidence that was still available.
        _markets(rows)
        return 0
    z = f["slope"] / f["se"] if f["se"] else 0.0
    span = bs[-1]["edge"] - bs[0]["edge"]
    print(f"  level  (average gap, at {f['at_edge']:.1%} claimed edge)  "
          f"{f['level']:+.1%}")
    print(f"  slope  (extra gap per point of edge) {f['slope']:+.2f}  "
          f"±{2 * f['se']:.2f} (2σ)   z {z:+.2f}")
    print(f"  on {f['n']:,} bets in {f['bands']} buckets")
    # What this sample could and could not have seen. Simulated on null
    # data the |z|>=2 rule fires 4.7% of the time, which is right — but at
    # this n it also MISSES a real effect about half the time, so a flat
    # answer is much weaker evidence than a positive one and must not be
    # read as an all-clear.
    print(f"  smallest slope this sample could resolve: "
          f"{2 * f['se']:.2f}, which is {2 * f['se'] * span:+.1%} of gap "
          f"across the observed edge range")
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
        print("  → NOT PROVEN, and this is the weak direction. The gap is")
        print("    flat in claimed edge, which is what a LEVEL error from")
        print("    somewhere else looks like — stale lines, the de-vig,")
        print("    grading, or a market shrink that is too weak.")
        print(f"    (The level is {f['level']:+.1%} and IS significant —")
        print("     that part is not in doubt, only its cause.)")
        print()
        print("    But read the resolution line above before calling it dead.")
        print("    At this sample size the test misses a genuinely selected")
        print("    book about half the time. Flat here is")
        print("    no evidence for, not evidence against.")
        print("    So: do not build the correction on this, and")
        print("    do not close the question either.")
        print("    Chase the level, and re-run as bets accrue.")
    print()

    _markets(rows)
    return 0


def _markets(rows: list[dict]) -> None:
    ms = by_market(rows)
    if not ms:
        return
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
