#!/usr/bin/env python3
"""Is the model biased toward one SIDE, and can anything currently fix it?

    python3 sidebias.py                  # every market
    python3 sidebias.py --market total_bases
    python3 sidebias.py --sport mlb --min-n 20

WHY A PLAIN PROJECTION-VS-ACTUAL COMPARISON WILL LIE TO YOU

The obvious test — average the projections on OVER bets, average what
happened, call the difference the bias — is contaminated, and badly. We
only bet OVER when the projection sits above the line, so the overs we
select are disproportionately the ones where the projection's own noise
happened to land high. Actuals then regress and the gap looks like bias
when a perfectly unbiased model would produce it. That is the winner's
curse, and it guarantees a finding whether or not one is there.

WHAT IS CLEAN

The ASYMMETRY. Both sides are selected the same way, on the same edge
bar, so both carry the same winner's curse. If overs miss their claimed
probability by four points and unders miss theirs by one, the difference
between those is not explained by selection — it is the model leaning.

So this reports each side's calibration gap (claimed probability against
what actually landed), then tests the DIFFERENCE between the sides. The
per-side gaps are printed for context and are not the finding; the
difference is.

WHY IT MATTERS THAT IT IS A SIDE BIAS

A temperature cannot fix one. ``apply_temperature`` is applied to P(over)
before the side is chosen, and its intercept is the only parameter that
can push a model off one side — but the journal fitter pairs each bet's
own hit_prob with won/lost, so an over's claim and an under's claim enter
the same fit as the same quantity. A directional lean contributes +gap on
one side and −gap on the other and cancels itself out of the fit designed
to catch it. (The deep fitter in engine/backtest.py does convert to
P(over) first, which is why the two disagree.)

That is the difference between "this market needs a bigger correction"
and "the correction has nowhere to put this".
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict

MIN_N = 20


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - _phi(abs(z)))


def calibration_gap(rows: list[dict]) -> dict:
    """Claimed probability against what landed, with the gap's own error.

    Gap is realised minus claimed, so negative = the model claimed more
    than it delivered. The standard error is the Poisson-binomial one:
    each bet has its own claim, so the variance is Σp(1-p), not n·p̄(1-p̄).
    """
    n = len(rows)
    if not n:
        return {"n": 0, "claimed": 0.0, "realised": 0.0, "gap": 0.0,
                "se": 0.0, "z": 0.0}
    claimed = sum(float(b["hit_prob"]) for b in rows) / n
    wins = sum(1 for b in rows if b["status"] == "won")
    var = sum(float(b["hit_prob"]) * (1 - float(b["hit_prob"])) for b in rows)
    se = math.sqrt(var) / n if var > 0 else 0.0
    gap = wins / n - claimed
    return {"n": n, "claimed": claimed, "realised": wins / n, "gap": gap,
            "se": se, "z": (gap / se) if se else 0.0}


def asymmetry(over: dict, under: dict) -> dict:
    """The clean test: is the OVER gap different from the UNDER gap?

    Both sides pass the same edge bar, so both carry the same selection
    effect; differencing them removes it. Independent samples, so the
    errors add in quadrature.
    """
    diff = over["gap"] - under["gap"]
    se = math.sqrt(over["se"] ** 2 + under["se"] ** 2)
    z = (diff / se) if se else 0.0
    return {"diff": diff, "se": se, "z": z, "p": two_sided_p(z)}


def load(conn, sport=None, market=None, category="main"):
    q = ("SELECT sport, market, side, hit_prob, status, projection, actual, "
         "line, odds FROM bets WHERE status IN ('won','lost') AND category=? "
         "AND hit_prob IS NOT NULL")
    args = [category]
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if market:
        q += " AND market=?"
        args.append(market)
    return [dict(r) for r in conn.execute(q, args)]


def _split(rows):
    o = [b for b in rows if (b["side"] or "OVER").upper() == "OVER"]
    u = [b for b in rows if (b["side"] or "OVER").upper() == "UNDER"]
    return o, u


def _line(label, s):
    if not s["n"]:
        return f"  {label:<10}      —  (no bets)"
    return (f"  {label:<10}{s['n']:>5}   claimed {s['claimed']:>6.1%}   "
            f"landed {s['realised']:>6.1%}   gap {s['gap']:>+6.1%}"
            f"   z {s['z']:>+5.2f}")


def report(rows: list[dict], min_n: int = MIN_N) -> int:
    if not rows:
        print("No settled bets with a claimed probability. Nothing to test.")
        return 0
    over, under = _split(rows)
    print("=" * 74)
    print("THE SPLIT")
    print("=" * 74)
    n = len(rows)
    print(f"  {len(over)} OVER  ·  {len(under)} UNDER  ·  "
          f"{len(over) / n:.0%} of bets are overs")
    print()
    print("  A lean here is not itself a fault — the model bets where it")
    print("  disagrees with the book, and books shade overs on popular")
    print("  markets, so disagreeing downward less often is expected.")
    print("  What matters is whether the overs it does take PERFORM.")

    print()
    print("=" * 74)
    print("CALIBRATION, BY SIDE")
    print("=" * 74)
    so, su = calibration_gap(over), calibration_gap(under)
    print(_line("OVER", so))
    print(_line("UNDER", su))
    print()
    print("  Both numbers are pulled down by the same selection effect: we")
    print("  bet the side we like, so we bet the props where this model's")
    print("  own noise ran that way. Read the DIFFERENCE, not the levels.")

    print()
    print("=" * 74)
    print("THE ASYMMETRY — the part selection cannot explain")
    print("=" * 74)
    if so["n"] < min_n or su["n"] < min_n:
        print(f"  Not enough on one side ({so['n']} over, {su['n']} under; "
              f"floor is {min_n}).")
        print("  A difference needs both halves to mean anything.")
        return 0
    a = asymmetry(so, su)
    print(f"  OVER gap {so['gap']:+.1%}  minus  UNDER gap {su['gap']:+.1%}"
          f"  =  {a['diff']:+.1%}")
    print(f"  z = {a['z']:+.2f}   (p = {a['p']:.3f})")
    print()
    if abs(a["z"]) >= 2:
        worse = "OVER" if a["diff"] < 0 else "UNDER"
        print(f"  → REAL. The {worse} side misses its own claim by "
              f"{abs(a['diff']):.1%} more")
        print("    than the other does, and selection affects both equally,")
        print("    so that difference is the model leaning.")
        print()
        print("    A temperature cannot correct this. It is applied to")
        print("    P(over) BEFORE the side is chosen, and the journal fitter")
        print("    pools an over's claim with an under's as if they were the")
        print("    same quantity — so a directional lean cancels itself out")
        print("    of the one fit that could catch it. See --explain.")
    elif abs(a["z"]) >= 1.0:
        # The branch that matters most and is easiest to write badly. A
        # twelve-point difference at z = -1.8 is NOT "the two sides look
        # alike" — it is a large difference the sample cannot yet confirm,
        # and calling that "no lean" throws away the strongest hypothesis
        # on the page.
        worse = "OVER" if a["diff"] < 0 else "UNDER"
        scale = (a["se"] * 2 / abs(a["diff"])) ** 2 if a["diff"] else 0
        print(f"  → SUGGESTIVE, NOT PROVEN. The {worse} side misses its claim")
        print(f"    by {abs(a['diff']):.1%} more than the other — that is a big")
        print(f"    difference, and it is the right size to be the thing")
        print(f"    costing money. But at z {a['z']:+.2f} this sample cannot")
        print(f"    rule out chance; a gap this size needs roughly "
              f"{scale * len(rows):,.0f} bets")
        print(f"    to reach two sigma, against {len(rows)} here.")
        print()
        print("    Treat it as the leading hypothesis, not a finding. It is")
        print("    the one worth watching every week rather than acting on")
        print("    today — and if it is real it will harden, not fade.")
    else:
        print(f"  → NO LEAN VISIBLE. The two sides miss their claims by "
              f"{abs(a['diff']):.1%}")
        print("    of each other, well inside the noise. Whatever is costing")
        print("    money, the evidence does not put it on the side choice.")

    # Per market — EVERY market, not only the ones with enough on both
    # sides. Showing the testable ones and silently dropping the rest let
    # the aggregate be driven by bets that never appeared: on the real
    # journal the table printed hits +0.9% and total_bases -7.6% under an
    # aggregate of -9.7%, and the 40 bets it had dropped carried -36.7%.
    # A reader would have concluded the lean was in total_bases. It was not.
    by_market: dict = defaultdict(list)
    for b in rows:
        by_market[b["market"] or "?"].append(b)
    print()
    print("=" * 74)
    print("BY MARKET")
    print("=" * 74)
    print(f"  {'market':<18}{'over n':>8}{'gap':>9}{'under n':>9}"
          f"{'gap':>9}{'diff':>9}{'z':>7}")
    print("  " + "-" * 68)
    testable = []
    thin_rows: list[dict] = []
    for m, rs in sorted(by_market.items()):
        o, u = _split(rs)
        go, gu = calibration_gap(o), calibration_gap(u)
        am = asymmetry(go, gu)
        ok = go["n"] >= min_n and gu["n"] >= min_n
        if ok:
            testable.append((m, am))
        else:
            thin_rows += rs
        print(f"  {m[:17]:<18}{go['n']:>8}{go['gap']:>+9.1%}"
              f"{gu['n']:>9}{gu['gap']:>+9.1%}{am['diff']:>+9.1%}"
              + (f"{am['z']:>+7.2f}" if ok else f"{'thin':>7}"))
    if thin_rows:
        to, tu = _split(thin_rows)
        gto, gtu = calibration_gap(to), calibration_gap(tu)
        atm = asymmetry(gto, gtu)
        print("  " + "-" * 68)
        print(f"  {'(all thin, pooled)':<18}{gto['n']:>8}{gto['gap']:>+9.1%}"
              f"{gtu['n']:>9}{gtu['gap']:>+9.1%}{atm['diff']:>+9.1%}"
              f"{atm['z']:>+7.2f}")

    # By FAMILY. This is the cut that makes the thin markets add up to
    # something: strikeouts and outs are both pitcher props, and a pitcher
    # prop lives or dies on how long the manager leaves him in, which is a
    # decision rather than a talent measurement. A model can have the
    # strikeout RATE right and the innings wrong and lose every over.
    #
    # The taxonomy is engine/parlays.FAMILY, which predates this file — the
    # grouping is not invented to fit the data. But it was CHOSEN after
    # seeing the data, so what follows generates a hypothesis; it does not
    # confirm one. That distinction is the whole discipline here.
    try:
        from engine.parlays import FAMILY, HITTER_FAMILIES, PITCHER_FAMILIES
    except Exception:
        FAMILY, PITCHER_FAMILIES, HITTER_FAMILIES = {}, set(), set()
    if FAMILY:
        groups: dict = defaultdict(list)
        for b in rows:
            groups[FAMILY.get(b["market"], "other")].append(b)
        shown = [(f, rs) for f, rs in groups.items() if len(rs) >= min_n]
        if len(shown) > 1:
            print()
            print("=" * 74)
            print("BY FAMILY — markets that share a mechanism")
            print("=" * 74)
            print(f"  {'family':<20}{'over n':>8}{'gap':>9}{'under n':>9}"
                  f"{'gap':>9}{'diff':>9}{'z':>7}")
            print("  " + "-" * 70)
            for f, rs in sorted(shown, key=lambda x: -len(x[1])):
                o, u = _split(rs)
                go, gu = calibration_gap(o), calibration_gap(u)
                af = asymmetry(go, gu)
                label = f + (" (pitcher)" if f in PITCHER_FAMILIES
                             else " (hitter)" if f in HITTER_FAMILIES else "")
                print(f"  {label[:19]:<20}{go['n']:>8}{go['gap']:>+9.1%}"
                      f"{gu['n']:>9}{gu['gap']:>+9.1%}{af['diff']:>+9.1%}"
                      f"{af['z']:>+7.2f}")
            print()
            print("  Grouped by the taxonomy the parlay engine already uses,")
            print("  not one drawn to fit these numbers. Still a hypothesis:")
            print("  the cut was chosen after reading the table above, so it")
            print("  needs confirming on bets not yet made.")

    # Simpson's check. If the whole book leans harder than any market in
    # it, the lean is not a property of those markets — it is composition,
    # or it is concentrated somewhere the per-market rows are too thin to
    # test. Either way the aggregate is the wrong place to act.
    if testable:
        comp = [am["diff"] for _, am in testable]
        if a["diff"] < min(comp) - 1e-9 or a["diff"] > max(comp) + 1e-9:
            print()
            print("  ⚠  The book-wide asymmetry "
                  f"({a['diff']:+.1%}) sits OUTSIDE the range")
            print(f"     of every market that could be tested "
                  f"({min(comp):+.1%} to {max(comp):+.1%}).")
            print("     A whole that leans harder than any of its parts is not")
            print("     those parts leaning. Read the pooled thin row above:")
            print("     that is where the book-wide number is coming from, and")
            print("     it is a handful of bets in markets too small to test")
            print("     — not a property of the model's side choice at large.")
    return 0


EXPLAIN = """
WHY A TEMPERATURE CANNOT CORRECT A SIDE BIAS
--------------------------------------------

engine/mlb/betting.py prices P(over) and calibrates it BEFORE choosing a
side, on purpose — an uncalibrated probability would still decide the
direction, so correcting after the fact would only shave an edge the model
had already committed to.

    logit(p') = logit(p) / T + b

T controls spread and has 50% as a fixed point. The INTERCEPT b is the only
parameter that can push a model off one side: a negative b lowers every
P(over), which flips the marginal overs to unders.

That intercept is fitted in two places, and they do not agree:

  engine/backtest.py (the deep fit) converts every settled bet to P(over)
  before pairing — an under bet at 0.60 becomes a P(over) of 0.40 — and
  pairs it against whether the over actually hit. Consistent quantity.
  This fit CAN see a directional lean.

  engine/journalfit.py (the journal fit) pairs each bet's own hit_prob
  against won/lost. An over claiming 0.58 and an under claiming 0.58 enter
  the same bucket as the same number, though one is a claim about the
  over landing and the other about it NOT landing. A model leaning over
  contributes a negative gap on its overs and a positive one on its
  unders, and the two cancel. The fit that could catch the lean is blind
  to it by construction.

So: a market fitted by the deep walk can be corrected for a lean. A market
fitted from the journal cannot, and will report itself calibrated while
leaning.
"""


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description="Is the model leaning on a side?")
    p.add_argument("--sport")
    p.add_argument("--market")
    p.add_argument("--category", default="main")
    p.add_argument("--min-n", type=int, default=MIN_N)
    p.add_argument("--db")
    p.add_argument("--explain", action="store_true",
                   help="why a temperature cannot fix a side bias")
    a = p.parse_args(argv)
    if a.explain:
        print(EXPLAIN)
        return 0
    from engine import ledger
    conn = ledger.connect(a.db) if a.db else ledger.connect()
    return report(load(conn, a.sport, a.market, a.category), a.min_n)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
