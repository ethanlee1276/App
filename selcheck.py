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
#: Selected vs rejected: the categories the --across test compares. `main`
#: is the published board; `loose` is the near-miss bucket — props that were
#: priced by the same model on the same night and did NOT clear the gate.
SELECTED, REJECTED = "main", "loose"
#: A stratum needs this many bets on BOTH sides before it can contribute a
#: within-stratum difference.
MIN_STRATUM = 12
#: The stratification schemes, coarse to fine. Reported side by side: one
#: adjusted number is one analyst's choice of cells, and the finest scheme
#: on the real journal threw away 37% of the sample. The SPREAD across
#: schemes is what says whether the answer is a property of the data or of
#: the grid someone drew over it.
#:
#: Book is not here and must not be — see across()'s docstring. It is a
#: mediator, not a confounder, and adjusting for it subtracts the effect.
SCHEMES = [
    ("market", lambda r: (r["market"],)),
    ("claim band", lambda r: (_band(r),)),
    ("market x claim band", lambda r: (r["market"], _band(r))),
]
#: The scheme quoted as THE adjusted answer, kept for continuity with the
#: earlier runs.
PRIMARY = "market x claim band"


def load(conn, sport=None, category="main") -> list[dict]:
    q = ("SELECT sport, market, side, odds, book, hit_prob, edge, status, category "
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


def _band(b: dict) -> float:
    """The bet's own claimed probability, in 10-point bands.

    Stratifying on the CLAIM rather than on the price, because the claim is
    what the gap is measured against and a 55% claim at -110 and at -130
    are the same forecast being scored.
    """
    return math.floor(float(b["hit_prob"]) * 10) / 10.0


def across(sel: list[dict], rej: list[dict]) -> dict:
    """Selected vs rejected: does the gate itself pick the worse bets?

    This is the comparison that has the leverage, and it took a real run to
    see it. Testing the slope WITHIN the selected board looks inside a band
    only 2.4-7% wide, where the curse is roughly constant; the winner's
    curse shows up at the selection BOUNDARY. `loose` is the near-miss
    bucket — the same model, the same night, the same markets, priced and
    then rejected by the gate — so the two differ by the gate and little
    else. That makes it as close to a control as this journal contains.

    Two numbers are returned and the second is the one to trust:

      * `raw` — the straight difference in gap. Simple, and confounded if
        the two groups differ in composition.
      * `adjusted` — the same difference computed WITHIN strata of
        (market, claimed-probability band) and pooled by inverse variance.
        If the gate is merely picking different markets or different price
        points, this collapses; if it survives, composition is not the
        explanation.

    It is still observational. The gate is not a coin flip and nothing here
    randomised anything.

    **BOOK IS DELIBERATELY NOT IN THE STRATA, and this is the one thing a
    future reader will want to change.** The balance table shows a violent
    book imbalance — on the real journal, ESPN BET was 76 selected against
    0 rejected, theScore Bet 13 against 214 — and that looks exactly like a
    confound crying out to be adjusted away.

    It is not a confound. It is the mechanism. A prop clears the bar
    BECAUSE some book hung a price out of line with the field; the book
    that offers the best number is the book that gets the bet over the
    threshold. Book therefore sits on the causal path between the gate and
    the outcome — a mediator, not a confounder — and adjusting for a
    mediator subtracts the very effect being measured.

    Market and claim level are different: some markets are simply harder to
    forecast, and that has nothing to do with the gate, so they are
    adjusted for.
    """
    a, b = _stats(sel), _stats(rej)
    raw = {"name": "raw (no adjustment)",
           "diff": a["gap"] - b["gap"],
           "se": math.sqrt(a["se"] ** 2 + b["se"] ** 2),
           "covered": len(sel) + len(rej), "strata": []}
    schemes = [raw] + [stratified(sel, rej, name, key) for name, key in SCHEMES]
    adj = next((s for s in schemes if s["name"] == PRIMARY and s["diff"] is not None),
               None)
    return {"sel": a, "rej": b, "raw": raw, "schemes": schemes,
            "adjusted": adj,
            "strata": adj["strata"] if adj else [],
            "covered": adj["covered"] if adj else 0}


def stratified(sel: list[dict], rej: list[dict], name: str, key) -> dict:
    """The selected-minus-rejected difference within strata, pooled.

    Inverse-variance weights over strata that clear MIN_STRATUM on BOTH
    sides. Everything else is dropped, which is where the coverage number
    comes from and why a finer scheme buys less precision than its extra
    control suggests.
    """
    groups: dict = {}
    for r in sel:
        groups.setdefault(key(r), ([], []))[0].append(r)
    for r in rej:
        groups.setdefault(key(r), ([], []))[1].append(r)

    strata, num, den = [], 0.0, 0.0
    for k, (s, j) in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(s) < MIN_STRATUM or len(j) < MIN_STRATUM:
            continue
        sa, sb = _stats(s), _stats(j)
        v = sa["se"] ** 2 + sb["se"] ** 2
        if v <= 0:
            continue
        strata.append({"key": k, "n_sel": len(s), "n_rej": len(j),
                       "diff": sa["gap"] - sb["gap"], "se": math.sqrt(v)})
        num += (sa["gap"] - sb["gap"]) / v
        den += 1.0 / v
    return {"name": name,
            "diff": num / den if den else None,
            "se": math.sqrt(1.0 / den) if den else None,
            "strata": strata,
            "covered": sum(s["n_sel"] + s["n_rej"] for s in strata)}


def stability(schemes: list[dict]) -> dict:
    """Does the answer survive the choice of cells?

    One adjusted number is one analyst's choice of strata. The finest
    scheme on the real journal discarded 37% of the sample, which is a lot
    of power spent on a scheme nobody validated — so the estimate is
    computed under every scheme and the SPREAD is the finding. An effect
    that holds from coarse to fine is not an artifact of the cells; one
    that only appears in a single scheme is.

    `spread` is the range of the adjusted point estimates, quoted against
    the median error bar so it can be read as "inside the noise" or not.
    """
    got = [s for s in schemes if s["name"] != "raw (no adjustment)"
           and s["diff"] is not None]
    if len(got) < 2:
        return {"stable": None, "n": len(got)}
    ds = [s["diff"] for s in got]
    ses = sorted(s["se"] for s in got)
    med = ses[len(ses) // 2]
    spread = max(ds) - min(ds)
    signs = {d > 0 for d in ds}
    return {"stable": len(signs) == 1 and spread <= 2 * med,
            "spread": spread, "median_se": med, "n": len(got),
            "lo": min(ds), "hi": max(ds), "one_sign": len(signs) == 1}


def balance(sel: list[dict], rej: list[dict], key) -> list[dict]:
    """Share of each group by some attribute — the confound check.

    If the gate systematically routes one market or one book into the
    selected side, then "selected bets are worse" could just be "that
    market is worse", and the adjusted difference above is what settles it.
    This table is how you SEE that rather than trusting the adjustment.
    """
    ks = sorted({key(r) for r in sel} | {key(r) for r in rej})
    out = []
    for k in ks:
        ns = sum(1 for r in sel if key(r) == k)
        nj = sum(1 for r in rej if key(r) == k)
        out.append({"key": k, "n_sel": ns, "n_rej": nj,
                    "p_sel": ns / len(sel) if sel else 0.0,
                    "p_rej": nj / len(rej) if rej else 0.0})
    return sorted(out, key=lambda r: -(r["n_sel"] + r["n_rej"]))


def _across_note(r: dict, total: int) -> None:
    """Composition, or just too few bets? Reported off the point
    estimate rather than off whether a z crossed two."""
    z = r["raw"]["diff"] / r["raw"]["se"] if r["raw"]["se"] else 0.0
    za = (r["adjusted"]["diff"] / r["adjusted"]["se"]
          if r.get("adjusted") and r["adjusted"]["se"] else None)
    if za is None or abs(z) < 2.0 or abs(za) >= 2.0:
        return
    keep = (abs(r["adjusted"]["diff"]) / abs(r["raw"]["diff"])
            if r["raw"]["diff"] else 0.0)
    print()
    if keep < 0.35:
        print(f"  NOTE: adjusting kept only {keep:.0%} of the raw difference.")
        print("  Composition — which markets and which claim levels land on")
        print("  each side — is doing most of the work, not the gate.")
    else:
        print(f"  NOTE: adjusting kept {keep:.0%} of the raw difference "
              f"({r['adjusted']['diff']:+.1%} against {r['raw']['diff']:+.1%}),")
        print("  so the significance went with the sample, not the effect.")
        print("  This is UNDER-POWERED, not explained away — a distinction")
        print("  worth being strict about, because the two point in opposite")
        print("  directions on what to do next. More bets, not a new theory.")


def report_across(sel: list[dict], rej: list[dict]) -> int:
    if len(sel) < 60 or len(rej) < 60:
        print(f"Need 60 settled on both sides; have {len(sel)} selected "
              f"and {len(rej)} rejected.")
        return 0
    r = across(sel, rej)
    print("=" * 74)
    print("SELECTED vs REJECTED — does the gate pick the worse bets?")
    print("=" * 74)
    for label, s in (("selected (main)", r["sel"]), ("rejected (loose)", r["rej"])):
        print(f"  {label:20} {s['n']:5} bets   claimed {s['claimed']:6.1%}   "
              f"landed {s['landed']:6.1%}   gap {s['gap']:+6.1%} ±{2 * s['se']:.1%}")
    z = r["raw"]["diff"] / r["raw"]["se"] if r["raw"]["se"] else 0.0
    total = len(sel) + len(rej)
    print()
    print("  adjusted for          difference        ±(2σ)       z   covered")
    print("  " + "-" * 62)
    for s in r["schemes"]:
        if s["diff"] is None:
            print(f"  {s['name']:20}  no stratum has enough on both sides")
            continue
        zs = s["diff"] / s["se"] if s["se"] else 0.0
        star = " *" if s["name"] == PRIMARY else ""
        print(f"  {s['name']:20} {s['diff']:+9.1%}    {2 * s['se']:6.1%}  "
              f"{zs:+6.2f}   {s['covered'] / total:4.0%}{star}")
    print()
    print("  Coarse to fine, top to bottom. Each row controls for more and")
    print("  pays for it in coverage — a stratum too thin on either side is")
    print("  dropped entirely. The SPREAD down this column is the finding:")
    print("  an effect that survives every scheme is a property of the data,")
    print("  one that appears in a single row is a property of the cells.")
    print()

    st = stability(r["schemes"])
    if st.get("stable") is not None:
        verdict_word = ("HOLDS across schemes" if st["stable"]
                        else "MOVES with the scheme")
        print(f"  → the estimate {verdict_word}: "
              f"{st['lo']:+.1%} to {st['hi']:+.1%}, a spread of "
              f"{st['spread']:.1%} against a typical bar of ±{2 * st['median_se']:.1%}")
        if not st["one_sign"]:
            print("    and it CHANGES SIGN, which means the cells are driving")
            print("    it rather than the gate. Treat the whole comparison as")
            print("    unsettled, not as a small effect.")
        print()

    za = r["adjusted"]["diff"] / r["adjusted"]["se"] if r["adjusted"] else None
    if r["adjusted"] is None:
        print("  within-strata        no stratum has enough on both sides")
        print()
    # Coverage first: stratifying throws away every bet in a stratum too
    # thin on one side, and that loss is why an adjusted estimate can keep
    # most of its size and still lose its significance.
    if r["adjusted"]:
        dropped = (len(sel) + len(rej)) - r["covered"]
        if dropped:
            print(f"  {dropped:,} of {len(sel) + len(rej):,} bets "
                  f"({dropped / (len(sel) + len(rej)):.0%}) sit in strata too "
                  f"thin on one side to contribute.")
            print()
    verdict = za if za is not None else z
    if verdict >= 2.0:
        print("  → THE GATE IS SELECTING THE WORSE BETS. Rejected props are")
        print("    better calibrated than the ones that cleared, on the same")
        print("    model and the same nights. That is the winner's curse at")
        print("    the boundary, and it survives adjusting for which markets")
        print("    and which claim levels each side contains.")
        print("    A selection correction is justified — fitted on THIS")
        print("    difference, not on the within-band slope.")
    elif verdict <= -2.0:
        print("  → THE GATE IS WORKING. Selected bets beat rejected ones.")
        print("    Whatever the over-claim is, the gate is not its cause.")
    else:
        print("  → NOT SEPARABLE on this sample. The two sides are not")
        print("    distinguishable, so the boundary shows nothing either way.")
    _across_note(r, len(sel) + len(rej))
    print()

    print("=" * 74)
    print("WHAT EACH SIDE IS MADE OF — the confound, shown not assumed")
    print("=" * 74)
    for name, key in (("market", lambda r: r["market"]),
                      ("book", lambda r: (r.get("book") or "?"))):
        print(f"  by {name}:")
        print(f"    {'':22} selected   rejected")
        for row in balance(sel, rej, key)[:8]:
            print(f"    {str(row['key'])[:20]:22} {row['p_sel']:7.0%}   "
                  f"{row['p_rej']:8.0%}   ({row['n_sel']}/{row['n_rej']})")
        print()
    return 0


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
    print("  market                     n   claimed   landed      gap    rel")
    print("  " + "-" * 65)
    for m in ms:
        # Relative, because +2.9 points on a 14.7% claim is a fifth of the
        # claim and +3.3 on a 58.9% claim is a twentieth. Ranking home runs
        # against main-board props on absolute points compares nothing.
        rel = m["gap"] / m["claimed"] if m["claimed"] else 0.0
        print(f"  {m['key']:22} {m['n']:6}   {m['claimed']:6.1%}   "
              f"{m['landed']:6.1%}   {m['gap']:+6.1%}  {rel:+5.0%}")
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
    p.add_argument("--across", action="store_true",
                   help=f"compare {SELECTED!r} (selected) against "
                        f"{REJECTED!r} (rejected by the gate)")
    a = p.parse_args(argv)
    conn = ledger.connect()
    if a.across:
        # Both sides at once, then split — one query, one set of filters,
        # so the two groups cannot differ by how they were fetched.
        rows = load(conn, sport=a.sport, category="all")
        sel = [r for r in rows if (r.get("category") or "") == SELECTED]
        rej = [r for r in rows if (r.get("category") or "") == REJECTED]
        return report_across(sel, rej)
    rows = load(conn, sport=a.sport, category=a.category)

    # NEVER pool categories. `bets.edge` is two different quantities: on a
    # main-board row it is an edge in probability points, and on a longshot
    # row engine/ledger.py falls back to `ev_per_unit` when no edge is
    # present — a per-unit expected value, which on a +900 price runs from
    # about -0.6 to +0.6. Bucketing the two together sorts on a mixture of
    # incompatible numbers, and it pools populations whose base rates run
    # from 10% (home runs) to 58% (main-board props), so the buckets differ
    # in WHAT THEY CONTAIN before they differ in anything measured.
    #
    # The first `--category all` run did exactly that and reported
    # "CONSISTENT WITH SELECTION" at z +2.13 across buckets whose claimed
    # probabilities were 10.3%, 15.1%, 53.0%, 45.6% and 27.2%. That slope
    # is category mix, not the winner's curse.
    groups: dict = {}
    for r in rows:
        groups.setdefault(r.get("category") or "main", []).append(r)
    for i, (cat, rs) in enumerate(sorted(groups.items())):
        if i:
            print("\n")
        print(f"### CATEGORY: {cat}   ({len(rs):,} settled)")
        print()
        report(rs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
