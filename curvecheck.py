#!/usr/bin/env python3
"""Is the receiving curve right for every kind of receiver? — held out, by volume.

    python3 curvecheck.py                     (the box's own history.db)
    python3 curvecheck.py --shrunk            (the projection's lean taken out first)
    python3 curvecheck.py --plain             (the plain normal, for comparison)
    python3 curvecheck.py --db PATH rec_yds   (another history, one market)

Ethan, 2026-10-22, Patriots at Bears, with Luther Burden III at 84 yards
in the first quarter: "the reports were right and you were wrong. The app
and you have to be better." The board had his 4+ catches at about 66% and
his 40+ yards at 59-67% (engine/yardagefit's fitted curve), under the
books' −260. The question this asks: is that curve too cautious on a
steady, high-volume receiver like him?

HOW. Leave one season out: the zero term and the width are fitted exactly
as `yardagefit.fit_market` fits them, on the other seasons; the held
season is priced at lines placed against each player's own projection
(k × projection, on the half — Burden's 40+ yards is k ≈ 0.73), and what
the curve claimed is set beside what landed, per volume tier.
`yardagefit` scores its fit at four fixed lines pooled over every
projection, and pooling can hide a miss that changes sign across tiers;
this is the per-tier look that one cannot give.

THE ANSWER, 2026-10-23, 2021 to 2026 week 7 rebuilt from nflverse's
weekly files exactly as the box stores them (`ingest.nfl_player_log_rows`;
the refit reproduced the box's curves: rec_yds zero −0.39/+0.61, width
0.66; receptions −0.81/+0.48, 0.46). In Burden's tier, at his kind of line:

                               claimed  landed
    rec_yds 45-60, k=0.75        59%     55%     the projection as it is
                                 58%     62%     its lean taken out
    receptions 4-5.5, k=0.75     64%     59%     the projection as it is
                                 62%     64%     its lean taken out
    the plain normal             66-69%  55-59%  the curve behind the 72%

NOT TOO CAUTIOUS: no change. The fitted curve misses those bets by four
points either way, and the sign follows how the projection leans, not the
curve. The plain normal, behind the 72% and 73% first put to Ethan,
over-claims them by 10 or 11 points. Within most tiers the outcomes
spread WIDER than the curve says (more duds at the low lines, more big
games at the high ones), so if anything a better width would lower these
bets, not raise them. Not applied: the fit runs on the trailing blend and
the board prices off its full projection, so a per-tier width fitted here
would carry the blend's own lean onto the board.

Standard library only; reads history.db, writes nothing.
"""
from __future__ import annotations

import math
import sqlite3
import sys
from collections import defaultdict

from engine import yardagefit as Y

#: Lines as a share of the projection: the low ones are where Most
#: Likely's likeliest rungs sit, 1.0 is about where a book hangs its main.
KS = (0.5, 0.65, 0.75, 0.85, 1.0, 1.2)
#: Tier edges by projection, per market.
TIERS = {"rec_yds": (1, 15, 30, 45, 60, 80, 999),
         "receptions": (1, 2, 3, 4, 5.5, 7, 99)}


def half(x: float) -> float:
    """A book's kind of number in x's own unit: 40.5 for 40.1 or 40.9."""
    return math.floor(x) + 0.5


def tier_of(mu: float, edges) -> str | None:
    for lo, hi in zip(edges, edges[1:]):
        if lo <= mu < hi:
            return f"{lo}-{hi if hi < 99 else '+'}"
    return None


def shrink(train) -> tuple:
    """(a, b) of actual ≈ a + b × projection on the training seasons: the
    trailing blend's lean toward its hot and cold hands, so a tier's miss
    can be read as the curve's rather than the projection's."""
    n = len(train)
    mx = sum(d["mu"] for d in train) / n
    my = sum(d["actual"] for d in train) / n
    sxx = sum((d["mu"] - mx) ** 2 for d in train)
    sxy = sum((d["mu"] - mx) * (d["actual"] - my) for d in train)
    b = sxy / sxx if sxx else 1.0
    return my - b * mx, b


def _with_mu(rows, a: float, b: float) -> list:
    return [dict(d, mu=max(a + b * d["mu"], Y.MIN_PROJECTION + 0.01)) for d in rows]


def cells(data, market: str, shrunk: bool = False, plain: bool = False,
          say=print) -> dict:
    """{(tier, k): [rows, claimed sum, landed]} over every held-out season."""
    out = defaultdict(lambda: [0, 0.0, 0])
    weight = Y.WIDTH_WEIGHT.get(market, 0.0)
    lines = Y.MARKETS[market]
    for season in sorted({d["season"] for d in data}):
        train = [d for d in data if d["season"] != season]
        test = [d for d in data if d["season"] == season]
        if len(test) < Y.MIN_TEST or len(train) < Y.MIN_TRAIN:
            continue
        if shrunk:
            a, b = shrink(train)
            train, test = _with_mu(train, a, b), _with_mu(test, a, b)
        beta = Y.fit_zero(train)
        typical = Y._typical_cv(train)
        sigma = Y.fit_sigma_on_over(train, beta, lines, weight=weight, typical=typical)
        say(f"  {market}, {season} held out: width {sigma:.2f}, {len(test):,} rows")
        for d in test:
            t = tier_of(d["mu"], TIERS[market])
            if t is None:
                continue
            w = Y._width_of(d, weight, typical)
            for k in KS:
                line = half(k * d["mu"])
                if line <= 0:
                    continue
                p = (Y.shipped_over(d, line, market) if plain
                     else Y.mixture_over(d, line, beta, sigma * w))
                c = out[(t, k)]
                c[0] += 1
                c[1] += p
                c[2] += 1 if d["actual"] > line else 0
    return out


def table(got: dict, market: str) -> list:
    edges = TIERS[market]
    lines = ["  " + f"{'projection':<11}" + "".join(f"{'k=' + str(k):>17}" for k in KS)]
    for lo in edges[:-1]:
        t = tier_of(lo, edges)
        row = f"  {t:<11}"
        for k in KS:
            n, claimed, landed = got.get((t, k), (0, 0.0, 0))
            if not n:
                row += f"{'-':>17}"
                continue
            cl, la = claimed / n, landed / n
            row += f"{cl:>7.0%}/{la:>4.0%} {100 * (la - cl):>+4.0f}"
        lines.append(row + f"   n={got.get((t, KS[0]), (0,))[0]:,}")
    lines.append("  each cell: claimed / landed, then landed minus claimed in points")
    return lines


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Y.DEFAULT_DB
    if "--db" in args:
        i = args.index("--db")
        path = args[i + 1]
        del args[i:i + 2]
    shrunk, plain = "--shrunk" in args, "--plain" in args
    markets = [a for a in args if not a.startswith("--")] or ["rec_yds", "receptions"]
    conn = sqlite3.connect(str(path))
    try:
        for market in markets:
            data = Y.rows(conn, market)
            curve = "the plain normal" if plain else "the fitted curve"
            lean = ", the projection's lean taken out" if shrunk else ""
            print(f"=== {market}: {curve}{lean} — {len(data):,} player-weeks, "
                  f"P(over k × projection) by projection, each season held out")
            got = cells(data, market, shrunk=shrunk, plain=plain)
            if not got:
                print("  too few player-weeks to hold a season out")
                continue
            for line in table(got, market):
                print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
