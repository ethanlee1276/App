#!/usr/bin/env python3
"""Do Next Gen Stats tell us anything the box score does not? — measured.

    python3 ngsfit.py                 # fit 2021-2024, held-out 2025
    python3 ngsfit.py 2022 2025       # other first/held-out seasons

Ethan, 2026-09-28: "do all the free shit first". engine/sources/ngs.py
pulls the league's tracking numbers; this is the information test they
have to pass before any of them reaches a projection.

THE HARNESS IS marketfit's (walk-forward, held out): every game in the
last season is projected from the games before it only, and scored
against a trailing-average line by ranking AUC — the chance a game that
went over is ranked above one that went under. Here each market is
scored twice on the same games: the box-score projection alone (marketfit
as shipped), and the same projection tilted by a Next Gen number from
the player's last six charted weeks — the tilt's size fitted on the seasons
BEFORE the held-out one (a grid over k, the tilt per standard deviation
of the metric), so the held-out figure is never fitted on itself. The
number that matters is the DIFFERENCE, with its bootstrap ±, per metric.

THE RULE, as everywhere in this repo: a metric ships only if the held-out
gain is two standard errors from zero and positive in at least three of
the fit seasons. Anything else is shown and left alone.

RESULT (2026-09-28, fitted 2021-2024, held out 2025): none of the eleven
clears. Separation on receiving yards is the best of them, +0.002 ± 0.003
AUC (n 1060) — inside one standard error; cushion, YAC over expected,
intended-air-yards share, rushing yards over expected, efficiency,
eight-man boxes, CPOE and time to throw all fit at k = 0 or move the
held-out season the wrong way. The tracking numbers are already in the
box score by the time a man has three games of it. The pull stays (the
game page may quote them one day), nothing in a projection reads them.
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

import marketfit as M
from engine.sources import ngs as NGS

#: (market, position, NGS file, metric, the tilt's sign — +1 when more of
#: it should mean more of the stat)
TESTS = [
    ("rec_yds", "WR", "receiving", "avg_separation", +1),
    ("rec_yds", "WR", "receiving", "avg_cushion", +1),
    ("rec_yds", "WR", "receiving", "avg_yac_above_expectation", +1),
    ("receptions", "WR", "receiving", "avg_separation", +1),
    ("receptions", "WR", "receiving", "percent_share_of_intended_air_yards", +1),
    ("rush_yds", "RB", "rushing", "rush_yards_over_expected_per_att", +1),
    ("rush_yds", "RB", "rushing", "efficiency", -1),
    ("rush_att", "RB", "rushing", "percent_attempts_gte_eight_defenders", -1),
    ("pass_yds", "QB", "passing", "completion_percentage_above_expectation", +1),
    ("pass_yds", "QB", "passing", "avg_time_to_throw", -1),
    ("pass_cmp", "QB", "passing", "completion_percentage_above_expectation", +1),
]
KS = (0.0, 0.03, 0.06, 0.1, 0.15, 0.2)
COLS = dict(M.COLS, rec_yds="receiving_yards", receptions="receptions", rush_yds="rushing_yards",
            pass_yds="passing_yards")
LINE_GAMES = getattr(M, "LINE_GAMES", 5)


def _z(vals: list) -> tuple:
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5 or 1.0
    return m, sd


def _league(rows, market, pos, before: int) -> float:
    """The league average of the stat for men in the role, seasons before
    ``before`` — marketfit's anchor, for a market its list may not carry."""
    vals = [M._f(r, COLS[market]) for yr, _wk, _name, p, r in rows
            if yr < before and p == pos and M._f(r, M.ROLE_COL[pos]) >= M.ROLE_FLOOR[pos]]
    return sum(vals) / len(vals) if vals else 0.0


def _cases(rows, hist_ngs, market, pos, metric, seasons):
    """One record per scoreable game in ``seasons``: (season, projection,
    sd, line, metric prior, outcome)."""
    league = {market: _league(rows, market, pos, max(seasons) + 1)}
    hist: dict = defaultdict(list)
    out = []
    for yr, wk, name, p, r in rows:
        if p != pos:
            continue
        y = M._f(r, COLS[market])
        h, rh = hist[(name, market)], hist[(name, "role")]
        if (yr in seasons and len(h) >= M.MIN_GAMES and len(rh) >= 3
                and sum(rh[:3]) / 3 >= M.ROLE_FLOOR[pos]):
            proj = M.blend(h, league[market])
            last = h[:LINE_GAMES]
            line = max(0.5, round(sum(last) / len(last) * 2) / 2 - 0.5)
            career = sum(h) / len(h)
            sd = (sum((v - career) ** 2 for v in h) / max(1, len(h) - 1)) ** 0.5 or 1.0
            pri = NGS.prior(hist_ngs.get(name) or [], yr, wk, metric)
            if y != line and pri is not None:
                out.append((yr, proj, sd, line, pri, y > line))
        h.insert(0, y)
        hist[(name, "role")].insert(0, M._f(r, M.ROLE_COL[pos]))
    return out


def _score(cases, k, sign, mu, sd_m):
    pairs = []
    for _yr, proj, sd, line, pri, hit in cases:
        tilt = 1.0 + k * sign * (pri - mu) / sd_m
        p = 1 - M._norm_cdf((line + 0.5 - proj * tilt) / sd)
        pairs.append((p, hit))
    return pairs


def _boot_diff(a_pairs, b_pairs, reps=200, seed=1) -> float:
    rnd = random.Random(seed)
    diffs = []
    n = len(a_pairs)
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        a = M.auc([a_pairs[i] for i in idx])[0]
        b = M.auc([b_pairs[i] for i in idx])[0]
        if a is not None and b is not None:
            diffs.append(b - a)
    if len(diffs) < 2:
        return 0.0
    m = sum(diffs) / len(diffs)
    return (sum((d - m) ** 2 for d in diffs) / (len(diffs) - 1)) ** 0.5


def run(first: int, held: int, out=print) -> list:
    rows = M.load(range(first, held + 1))
    files = {}
    results = []
    out(f"Next Gen Stats, walk-forward: fitted on {first}-{held - 1}, held out {held}. "
        f"AUC of the box-score projection alone → with the tracking number tilted in (Δ ± bootstrap).\n")
    for market, pos, kind, metric, sign in TESTS:
        if kind not in files:
            files[kind] = NGS.by_player(NGS.fetch(kind), kind)
        hist_ngs = files[kind]
        fit = _cases(rows, hist_ngs, market, pos, metric, set(range(first, held)))
        test = _cases(rows, hist_ngs, market, pos, metric, {held})
        if len(fit) < 100 or len(test) < 60:
            out(f"  {market:10} {pos:3} {metric:40} too few charted games (fit {len(fit)}, held {len(test)})")
            continue
        mu, sd_m = _z([c[4] for c in fit])
        # The tilt, chosen on the fit seasons only.
        best_k, best = 0.0, None
        for k in KS:
            a = M.auc(_score(fit, k, sign, mu, sd_m))[0]
            if a is not None and (best is None or a > best + 1e-9):
                best_k, best = k, a
        base = _score(test, 0.0, sign, mu, sd_m)
        tilted = _score(test, best_k, sign, mu, sd_m)
        a0, a1 = M.auc(base)[0], M.auc(tilted)[0]
        se = _boot_diff(base, tilted)
        per = {}
        for yr in range(first, held):
            fy = [c for c in fit if c[0] == yr]
            if len(fy) >= 40:
                b0 = M.auc(_score(fy, 0.0, sign, mu, sd_m))[0]
                b1 = M.auc(_score(fy, best_k, sign, mu, sd_m))[0]
                if b0 is not None and b1 is not None:
                    per[yr] = round(b1 - b0, 4)
        delta = (a1 - a0) if a0 is not None and a1 is not None else 0.0
        up = sum(1 for v in per.values() if v > 0)
        ships = best_k > 0 and delta >= 2 * se and up >= min(3, len(per))
        results.append({"market": market, "pos": pos, "metric": metric, "k": best_k, "auc0": a0, "auc1": a1,
                        "delta": delta, "se": se, "n": len(test), "per": per, "ships": ships})
        out(f"  {market:10} {pos:3} {metric:40} {a0:.3f} → {a1:.3f}  Δ {delta:+.4f} ± {se:.4f}  "
            f"k {best_k:.2f}  n {len(test)}  fit seasons up {up}/{len(per)}  "
            f"{'CLEARS' if ships else 'stays a signal'}")
    return results


def main(argv) -> int:
    first = int(argv[1]) if len(argv) > 1 else 2021
    held = int(argv[2]) if len(argv) > 2 else 2025
    run(first, held)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
