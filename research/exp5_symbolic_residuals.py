#!/usr/bin/env python3
"""EXP-005 — can a small, searched equation explain the direct model's misses?

    python3 research/exp5_symbolic_residuals.py              (search on 2017-21, choose on 2022-23)
    python3 research/exp5_symbolic_residuals.py --holdout    (scores the chosen equations once)

Research spec Part 5.1 (symbolic regression) and 5.4 (residual discovery):
search for interpretable equations that predict a baseline's errors, with
the equation's complexity penalised, nothing from after kickoff, and the
winner judged on games the search never saw. Registry entry EXP-005.

THE BASELINE is EXP-001's direct model A (research/exp1_two_stage): its
centre mu_a is the board's form blend, its shape the training pool. The
residual is r = y - mu_a, for NFL receptions, receiving yards and rushing
yards.

THE SEARCH SPACE, fixed before any run. Six pre-game quantities per row:

    a  mu_a, A's centre                 b  B's centre (the two-stage mean)
    o  his age-weighted opportunities   e  production per opportunity so far
    w  the week                         v  his opportunities so far this season

Four one-place functions: x, sqrt(x), log(1 + x), 1 / (1 + x). An equation
is g = f1(t1) or g = f1(t1) (+ - x /) f2(t2) — every pair, the division
protected as p / (|q| + 1) — and the correction it makes is
r_hat = c0 + c1 * g, with c0, c1 by least squares on the training rows.
Complexity: one per quantity, one per function other than x, one per
operator. 24 one-term and 1,656 two-term equations per market (1,680).

HOW ONE IS CHOSEN, per market. Each equation is fitted on 2017-2021 (a
seeded sample of up to 12,000 rows, to keep the search on one core) and
scored on all of 2022-2023 by mean squared error of the residual, times
(1 + LAMBDA * complexity), LAMBDA = 0.01. The lowest wins, and only if it
beats predicting no correction at all (the squared residual) on that same
score. "b - a" — blending in the two-stage centre — is in the space, so a
plain blend competes with every searched shape on equal terms.

THE TEST, WRITTEN BEFORE ANY RUN (2026-10-17). The chosen equation is
refitted (c0, c1 only) on 2017-2023 and frozen. On the holdout, A's shape
is moved to the corrected centre max(0.05, mu_a + r_hat) and scored by
EXP-001's CRPS against A unchanged. Per market it ADVANCES only if the
player-season-clustered upper bound on CRPS(corrected) - CRPS(A) is under
zero at 98.33% (0.05 / 3 markets); right direction with the bound over zero
is INCONCLUSIVE; wrong direction is REJECTED. A market whose search finds
nothing better than no correction is REJECTED (search) and never scored.

THE HOLDOUT, AND WHAT IT HAS SEEN. 2024, 2025 and 2026 to date. 2024-25
were EXP-001's holdout: read for A against B, never for any relation
between A's misses and these quantities; the search reads none of it. 2026
is printed on its own beside the pooled verdict, as description.

PRIOR ART. Symbolic regression by genetic programming (Koza 1992) and its
modern forms (e.g. PySR, Cranmer 2023) search far larger spaces; boosting a
baseline's residuals is standard. This is a deliberately small, exhaustive
search with a complexity price — a new application, not a new method.

THE SEARCH'S CHOICE (2026-10-17, search and choice run, holdout NOT read;
frozen in the commit that adds this paragraph):

  market      no correction   best (penalised)   chosen, refitted on 2017-23
  receptions  MSE 4.5270      4.5037             r_hat = +0.4522 - 0.15380 * a
  rec_yds     MSE 929.4244    none beat it       REJECTED (search)
  rush_yds    MSE 1124.6396   1122.4149          r_hat = +7.7994 - 0.15990 * a

Out of 1,680 shapes the penalty chose the plainest: a straight line in A's
own centre, slope about -0.15 in both markets — A's centres are spread too
wide, too high when high and too low when low, and want shrinking about 15%
toward the middle. That is regression to the mean, a rediscovery (novelty
class 5), and the same direction as pricetrust's finding on the published
picks. The holdout says whether it holds.

THE RESULT (2026-10-17, holdout read once, after the freeze commit bc72d027):

  market      holdout 2024-26   CRPS A    corrected  diff [98.33% clustered]   decision
  receptions  4,343 rows         1.1835    1.1768    -0.0067 [-0.0108, -0.0024]  ADVANCE
  rush_yds    1,519 rows        18.2534   18.2593    +0.0059 [-0.1140, +0.1306]  REJECTED (holdout)
  rec_yds     —                 —         —          —                           REJECTED (search)

Receptions' direct centre, shrunk about 15% toward the middle, is a better
forecast on games the search never saw — small (a fifth of B's gain over A
in EXP-001), and plain shrinkage, not a new mathematics. Rushing yards'
squared error fell a little but its distribution did not improve, so it
fails the bar as written. Nothing moves a pick.

Reads data/cache (nflverse weekly player stats); writes nothing.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import exp1_two_stage as E1                        # noqa: E402

TRAIN = range(2017, 2022)
VALID = range(2022, 2024)
HOLD = range(2024, 2027)
MARKETS = ("receptions", "rec_yds", "rush_yds")
LAMBDA = 0.01
SEARCH_ROWS = 12_000
ALPHA = 0.05 / 3
TERMS = ("a", "b", "o", "e", "w", "v")
UNARY = {"x": (lambda x: x, 0), "sqrt": (lambda x: math.sqrt(max(0.0, x)), 1),
         "log1p": (lambda x: math.log1p(max(0.0, x)), 1), "inv": (lambda x: 1.0 / (1.0 + max(0.0, x)), 1)}
BINARY = ("+", "-", "*", "/")


def features(x: dict, fit) -> dict:
    """The six pre-game quantities for one row (see THE SEARCH SPACE)."""
    return {"a": x["mu_a"], "b": fit.mean_b(x), "o": x["mu_o"],
            "e": x["prod"] / x["opps"] if x["opps"] > 0 else 0.0,
            "w": float(x["week"]), "v": x["opps"]}


def leaves() -> list:
    return [(u, t) for t in TERMS for u in UNARY]


def equations() -> list:
    """Every equation in the space: (name, complexity, spec)."""
    out, ls = [], leaves()
    for u, t in ls:
        out.append((_leaf(u, t), 1 + UNARY[u][1], ("leaf", (u, t))))
    for i, (u1, t1) in enumerate(ls):
        for j, (u2, t2) in enumerate(ls):
            if t1 == t2 and u1 == u2:
                continue
            for op in BINARY:
                if op in "+*" and j < i:
                    continue                      # commutative: each pair once
                c = 3 + UNARY[u1][1] + UNARY[u2][1]
                out.append((f"{_leaf(u1, t1)} {op} {_leaf(u2, t2)}", c, ("pair", (u1, t1), op, (u2, t2))))
    return out


def _leaf(u, t) -> str:
    return t if u == "x" else f"{u}({t})"


def values(spec, feats: list) -> list:
    """g for every row."""
    def leaf(ut, f):
        u, t = ut
        return UNARY[u][0](f[t])
    if spec[0] == "leaf":
        return [leaf(spec[1], f) for f in feats]
    _k, l1, op, l2 = spec
    out = []
    for f in feats:
        p, q = leaf(l1, f), leaf(l2, f)
        out.append(p + q if op == "+" else p - q if op == "-" else p * q if op == "*" else p / (abs(q) + 1.0))
    return out


def ols(g: list, r: list):
    n = len(g)
    mg, mr = sum(g) / n, sum(r) / n
    sgg = sum((x - mg) ** 2 for x in g)
    if sgg <= 1e-12 or not math.isfinite(sgg):
        return None
    c1 = sum((x - mg) * (y - mr) for x, y in zip(g, r)) / sgg
    return mr - c1 * mg, c1


def mse(g: list, r: list, c) -> float:
    c0, c1 = c
    return sum((y - c0 - c1 * x) ** 2 for x, y in zip(g, r)) / len(r)


def search(train: list, valid: list, fit, seed: int = 11) -> list:
    """[(score, mse_valid, name, complexity, spec, coef)] best first, plus the no-correction line."""
    rng = random.Random(seed)
    tr = train if len(train) <= SEARCH_ROWS else rng.sample(train, SEARCH_ROWS)
    ft, fv = [features(x, fit) for x in tr], [features(x, fit) for x in valid]
    rt = [x["y"] - x["mu_a"] for x in tr]
    rv = [x["y"] - x["mu_a"] for x in valid]
    out = [(sum(v * v for v in rv) / len(rv), sum(v * v for v in rv) / len(rv), "no correction", 0, None, (0.0, 0.0))]
    for name, comp, spec in equations():
        gt = values(spec, ft)
        if not all(math.isfinite(v) for v in gt):
            continue
        c = ols(gt, rt)
        if c is None:
            continue
        gv = values(spec, fv)
        m = mse(gv, rv, c)
        if math.isfinite(m):
            out.append((m * (1 + LAMBDA * comp), m, name, comp, spec, c))
    out.sort(key=lambda z: z[0])
    return out


def corrected_scores(rows: list, fit, spec, coef) -> list[dict]:
    """EXP-001's CRPS for A, and for A's shape at the corrected centre."""
    feats = [features(x, fit) for x in rows]
    g = values(spec, feats)
    out = []
    for x, gi in zip(rows, g):
        grid = E1.GRID[x["m"]]
        m2 = max(0.05, x["mu_a"] + coef[0] + coef[1] * gi)
        fa = [fit.cdf_a(x, t) for t in grid]
        fc = [fit.cdf_a(x, t, mean=m2) for t in grid]
        out.append({"m": x["m"], "s": x["s"], "who": x["who"], "a": E1.crps(fa, grid, x["y"]),
                    "c": E1.crps(fc, grid, x["y"]), "se_a": (x["y"] - x["mu_a"]) ** 2, "se_c": (x["y"] - m2) ** 2})
    return out


def bounded(scored: list) -> tuple:
    keep = E1.ALPHA
    E1.ALPHA = ALPHA
    try:
        return E1.boot_diff(scored, key_b="c")
    finally:
        E1.ALPHA = keep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="score the chosen equations on 2024-26 (run once)")
    a = ap.parse_args(argv)
    train_all = [x for s in TRAIN for x in E1.rows_for(s)]
    fit = E1.Fit(train_all)
    valid_all = [x for s in VALID for x in E1.rows_for(s)]
    print(f"EXP-005 symbolic residual search — {len(equations()):,} equations per market; "
          f"A and B fitted on {TRAIN.start}-{TRAIN.stop - 1} ({len(train_all):,} rows)")
    hold_all = [x for s in HOLD for x in E1.rows_for(s)] if a.holdout else []
    verdicts = []
    for m in MARKETS:
        tr = [x for x in train_all if x["m"] == m]
        va = [x for x in valid_all if x["m"] == m]
        ranked = search(tr, va, fit)
        base = next(z for z in ranked if z[4] is None)
        best = ranked[0]
        print(f"\n{m}: train {len(tr):,} (searched on {min(len(tr), SEARCH_ROWS):,}), validation {len(va):,}")
        print(f"  no correction: residual MSE {base[1]:.4f}")
        for z in ranked[:5]:
            print(f"  {z[0]:.4f}  MSE {z[1]:.4f}  complexity {z[3]}  r_hat = {z[5][0]:+.4f} {z[5][1]:+.5f} * [{z[2]}]")
        if best[4] is None:
            verdicts.append((m, "REJECTED (search: nothing beat no correction)"))
            print("  chosen: none — nothing beat no correction on the penalised score")
            continue
        both = tr + va
        g = values(best[4], [features(x, fit) for x in both])
        coef = ols(g, [x["y"] - x["mu_a"] for x in both])
        print(f"  chosen: r_hat = {coef[0]:+.4f} {coef[1]:+.5f} * [{best[2]}]  (refitted on {TRAIN.start}-{VALID.stop - 1})")
        if not a.holdout:
            verdicts.append((m, f"chosen [{best[2]}]; holdout not yet read"))
            continue
        ho = [x for x in hold_all if x["m"] == m]
        sc = corrected_scores(ho, fit, best[4], coef)
        mean, lo, hi = bounded(sc)
        n = len(sc)
        ca, cc = sum(p["a"] for p in sc) / n, sum(p["c"] for p in sc) / n
        ma, mc = sum(p["se_a"] for p in sc) / n, sum(p["se_c"] for p in sc) / n
        print(f"  holdout {HOLD.start}-{HOLD.stop - 1}: n={n:,}  CRPS A {ca:.4f}  corrected {cc:.4f}  "
              f"diff {mean:+.4f} [{lo:+.4f}, {hi:+.4f}]  | MSE A {ma:.3f} corrected {mc:.3f}")
        s26 = [p for p in sc if p["s"] == 2026]
        if s26:
            print(f"    2026 alone (description): n={len(s26):,}  diff "
                  f"{(sum(p['c'] for p in s26) - sum(p['a'] for p in s26)) / len(s26):+.4f}")
        d = "REJECTED (holdout)" if mean >= 0 else "ADVANCE" if hi < 0 else "INCONCLUSIVE"
        verdicts.append((m, d))
    print("\nDecision (bar written before the run): " + "; ".join(f"{m}: {d}" for m, d in verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
