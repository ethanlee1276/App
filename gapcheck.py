#!/usr/bin/env python3
"""Is the over-claim the ENGINE, or is it baseball?

    python3 gapcheck.py
    python3 gapcheck.py --category loose     # the paper board, same question

Reads the journal. Writes nothing.

THE QUESTION NOTHING HAS ASKED
------------------------------
Every diagnostic in this repo takes ``--sport`` and defaults to ``mlb``.
guardfit, bleed, selcheck, selfit, barcheck: all of them measure one sport
at a time, and all of them have only ever been pointed at baseball. So the
+12-point over-claim has been measured six ways and never once compared
against another sport.

That comparison is the one that decides what to repair:

  * **The gaps agree across sports** → it is the ENGINE. The shrink, the
    de-vig, the credibility guard and the edge gate are shared by every
    sport, so a common miscalibration lives in something they share. NFL
    will inherit it at kickoff, and the correction belongs at engine level.
  * **The gaps differ** → it is baseball's projection layer, not the
    machinery around it. NFL may launch clean, and fitting one engine-wide
    correction would damage the sports that are already honest.

Both readings are actionable and they point opposite ways, which is why
guessing is worse than measuring.

TWO KINDS OF GAP, AND THEY ARE NOT INTERCHANGEABLE
---------------------------------------------------
This repo has been bitten three times in one week by comparing absolute
probability points across populations with different base rates — the loss
miner's five-point closure bar, the Lab's ROI tile, selfit's signed
threshold. A sport claiming 15% and one claiming 58% cannot be ranked on
points alone: three points is a fifth of the first claim and a twentieth
of the second.

So both are reported, always, and the heterogeneity test runs on whichever
:data:`SCALE` names. Relative is the default, because it is the one that
survives a mix of markets.

THE STATISTICS
--------------
Each sport gets a Poisson-binomial error — the sum of p(1−p) over its own
claims — rather than n·p̄(1−p̄), because a sport whose claims range from
12% to 70% is badly served by an average.

Whether the sports agree is Cochran's Q against a chi-square with k−1
degrees of freedom, with I² beside it. Not eyeballing the column: four
sports with wide bars will always LOOK different, and Q is the question of
whether they differ by more than their own noise.

A NON-RESULT IS THE LIKELY RESULT
---------------------------------
Outside baseball this journal is thin. A sport under :data:`MIN_SPORT`
settled bets is listed and excluded from the test, because a 30-bet sport
carries a ±18-point bar and would make any comparison come back
"consistent" no matter what is true. If only one sport clears the floor,
the honest output is that the question cannot be answered yet — and that
is what it prints.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import ledger

#: Below this a sport is shown but kept out of the heterogeneity test. Its
#: error bar would be wide enough to reconcile anything with anything.
MIN_SPORT = 60
#: Which scale the agreement test runs on. "relative" is gap divided by
#: the claim, which is comparable across sports whose base rates differ;
#: "points" is the raw difference and is not.
SCALE = "relative"
#: Q's p-value below this and the sports are called different.
ALPHA = 0.05


def load(conn, category: str = "main") -> list[dict]:
    q = ("SELECT sport, market, hit_prob, status FROM bets "
         "WHERE status IN ('won','lost') AND hit_prob IS NOT NULL")
    args: list = []
    if category != "all":
        q += " AND category=?"
        args.append(category)
    return [dict(r) for r in conn.execute(q, args)]


def _chi2_sf(x: float, df: int) -> float:
    """P(chi2_df > x), Wilson–Hilferty. No scipy in this repo.

    Accurate to about a thousandth over the range that matters here, which
    is far finer than a verdict at 0.05 needs.
    """
    if df <= 0 or x <= 0:
        return 1.0
    t = (x / df) ** (1.0 / 3.0)
    m = 1.0 - 2.0 / (9.0 * df)
    s = math.sqrt(2.0 / (9.0 * df))
    z = (t - m) / s
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def by_sport(rows: list[dict]) -> list[dict]:
    """Claimed vs landed per sport, on both scales."""
    g: dict = {}
    for r in rows:
        g.setdefault(r["sport"] or "?", []).append(r)
    out = []
    for sport, rs in sorted(g.items()):
        n = len(rs)
        claimed = sum(float(r["hit_prob"]) for r in rs) / n
        landed = sum(1 for r in rs if r["status"] == "won") / n
        var = sum(float(r["hit_prob"]) * (1 - float(r["hit_prob"])) for r in rs)
        se = math.sqrt(var) / n if var > 0 else 0.0
        gap = claimed - landed
        out.append({
            "sport": sport, "n": n, "claimed": claimed, "landed": landed,
            "points": gap, "se_points": se,
            # The same miss expressed as a share of what was claimed, which
            # is what makes a 15% market and a 58% market comparable.
            "relative": (gap / claimed) if claimed else 0.0,
            "se_relative": (se / claimed) if claimed else 0.0,
            "markets": len({r["market"] for r in rs}),
        })
    return sorted(out, key=lambda s: -s["n"])


def agree(sports: list[dict], scale: str = SCALE) -> dict:
    """Cochran's Q on the sports big enough to be worth testing."""
    usable = [s for s in sports if s["n"] >= MIN_SPORT
              and s[f"se_{scale}"] > 0]
    k = len(usable)
    if k < 2:
        return {"ok": False, "k": k,
               "usable": [s["sport"] for s in usable]}
    ws = [1.0 / s[f"se_{scale}"] ** 2 for s in usable]
    pooled = sum(w * s[scale] for w, s in zip(ws, usable)) / sum(ws)
    q = sum(w * (s[scale] - pooled) ** 2 for w, s in zip(ws, usable))
    df = k - 1
    p = _chi2_sf(q, df)
    return {"ok": True, "k": k, "usable": [s["sport"] for s in usable],
            "pooled": pooled, "se": math.sqrt(1.0 / sum(ws)),
            "q": q, "df": df, "p": p,
            "i2": max(0.0, (q - df) / q) if q > 0 else 0.0,
            "differ": p < ALPHA}


def report(conn, category: str = "main") -> int:
    rows = load(conn, category)
    sports = by_sport(rows)

    print("=" * 74)
    print(f"IS THE OVER-CLAIM THE ENGINE, OR IS IT BASEBALL?   (category="
          f"{category})")
    print("=" * 74)
    if not sports:
        print("  No settled bets on this machine.")
        return 0

    print("   sport    bets  mkts   claimed   landed      gap      "
          "as a share of claim")
    print("   " + "-" * 66)
    for s in sports:
        thin = "" if s["n"] >= MIN_SPORT else "  (thin)"
        print(f"   {s['sport']:6} {s['n']:6} {s['markets']:5}   "
              f"{s['claimed']:6.1%}   {s['landed']:6.1%}   "
              f"{s['points']:+6.1%}          {s['relative']:+6.1%}{thin}")
    print()
    print(f"  Both scales, always. A sport claiming 15% and one claiming 58%")
    print(f"  cannot be ranked on points — three points is a fifth of the")
    print(f"  first and a twentieth of the second. The test below runs on")
    print(f"  the {SCALE} column.")
    print()

    a = agree(sports)
    print("=" * 74)
    print("DO THEY AGREE?")
    print("=" * 74)
    if not a["ok"]:
        print(f"  CANNOT BE ANSWERED YET — only {a['k']} sport(s) have "
              f"{MIN_SPORT}+ settled bets"
              + (f" ({', '.join(a['usable'])})" if a["usable"] else ""))
        print()
        print("  This is a real answer, not a failure. A sport under")
        print(f"  {MIN_SPORT} bets carries an error bar wide enough to")
        print("  reconcile anything with anything, and including it would")
        print("  manufacture agreement rather than measure it.")
        print()
        print("  Until a second sport clears the floor, the +12 measured on")
        print("  baseball cannot be told apart from an engine-wide fault,")
        print("  and NFL should be treated as exposed to it. nflguard.py is")
        print("  the standing bet on that being wrong.")
        print()
        return 0

    print(f"  {a['k']} sports tested: {', '.join(a['usable'])}")
    print(f"  pooled {SCALE} gap {a['pooled']:+.1%} ±{2 * a['se']:.1%}")
    print(f"  Cochran's Q {a['q']:.2f} on {a['df']} df, p {a['p']:.3f}, "
          f"I² {a['i2']:.0%}")
    print()
    if a["differ"]:
        print("  → THEY DIFFER. The sports are not missing by the same")
        print("    amount, by more than their own noise explains. That")
        print("    points at what is NOT shared — the per-sport projection")
        print("    layers — rather than at the shrink, the de-vig, the")
        print("    credibility guard or the edge gate, which every sport")
        print("    runs through identically.")
        print()
        print("    One engine-wide correction would be wrong here: it would")
        print("    damage whichever sports are already honest.")
    else:
        print("  → CONSISTENT WITH ONE NUMBER. The sports are not")
        print("    distinguishable, so nothing here separates a shared")
        print("    engine fault from several coincidentally similar ones.")
        print()
        print("    Read that narrowly. Agreement at these sample sizes is")
        print("    weak evidence — Q fails to reject far more easily than it")
        print("    rejects. What it does mean is that there is no reason yet")
        print("    to believe NFL will be spared, so nflguard.py's boundary")
        print("    stands.")
    print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--category", default="main",
                   help="'main', a paper bucket, or 'all'")
    a = p.parse_args(argv)
    return report(ledger.connect(), category=a.category)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
