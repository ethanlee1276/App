#!/usr/bin/env python3
"""EXP-002 — does a player-by-defence interaction add anything beyond the two alone?

    python3 research/exp2_interactions.py              (fit 2017-2021, choose ridge on 2022-2023)
    python3 research/exp2_interactions.py --holdout    (adds 2024-2025; run ONCE, result recorded)

Research spec Part 8, Experiment 2 (Ethan, 2026-10-17). Registry EXP-002.

THE MODEL. For one market, a player-game's stat y is predicted by

    base       y = b0 + b1 * mu + b2 * A + b3 * D
    candidate  y = b0 + b1 * mu + b2 * A + b3 * D + b4 * A * D

mu is the board's form mean for him (the direct model of EXP-001), A a trait
of his and D a trait of tonight's defence, all from games BEFORE this one
this season (the defence's from every receiver or back it has faced). Each
column is standardised on the training seasons; both are fitted by ridge,
the penalty chosen on 2022-2023 from a fixed grid.

THE FIVE INTERACTIONS, chosen for a football reason before any run:

  I1 rec_yds     his air yards a target  x  the defence's completed air yards allowed a target
                 (a deep receiver against a secondary that gives up the deep ball)
  I2 rec_yds     his yards after catch a reception  x  the defence's YAC allowed a reception
                 (a runner after the catch against poor tackling)
  I3 receptions  his share of his team's targets  x  targets the defence faces a game
                 (a share of a bigger pie)
  I4 rush_yds    his carries a game  x  the defence's yards allowed a carry
                 (a workhorse against a soft front)
  I5 rush_yds    his yards a carry  x  the defence's yards allowed a carry
                 (efficiency meeting efficiency)

Rates are shrunk toward the position's (or the league's) by fixed counts.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-17). Score: mean squared error on
y. An interaction ADVANCES only if adding it lowers the error on 2022-2023
AND on 2024-2025, with the paired, player-season-clustered bootstrap's
upper bound on MSE(candidate) - MSE(base) under zero at 99% (0.05 / 5,
Bonferroni over the five). Right direction, bound over zero: INCONCLUSIVE.
Wrong direction anywhere: REJECTED. A coefficient that is merely
"significant" in training counts for nothing.

PRIOR ART. Defence-versus-position adjustments are standard practice, and
this site already multiplies every projection by a measured defence step
(engine/defensevs, TRANSFER from engine/defensefit) — which is itself an
interaction in levels. So the real question here is narrower: does a
SPECIFIC trait pairing add beyond the generic defence quality? The
coefficient estimates below are not inventions; only a pairing that holds
on unseen seasons would be a finding, and even that is a new application of
an established idea, not new mathematics.

Reads data/cache (nflverse weekly player stats); writes nothing.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

from exp1_two_stage import load                                  # noqa: E402
from engine import carry as C                                    # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402

TRAIN, VALID, HOLD = range(2017, 2022), range(2022, 2024), range(2024, 2026)
LAMBDAS = (0.0, 1.0, 10.0, 100.0, 1000.0)
ALPHA = 0.05 / 5
BOOT = 1000
#: id -> (market, positions, his trait, the defence's trait)
PAIRS = {"I1": ("rec_yds", ("WR", "TE", "RB"), "adot", "d_cay"),
         "I2": ("rec_yds", ("WR", "TE", "RB"), "yac", "d_yac"),
         "I3": ("receptions", ("WR", "TE", "RB"), "tshare", "d_tgt"),
         "I4": ("rush_yds", ("RB",), "carpg", "d_ypc"),
         "I5": ("rush_yds", ("RB",), "ypc", "d_ypc")}


def _n(r: dict, c: str) -> float:
    try:
        return float(r.get(c) or 0)
    except (TypeError, ValueError):
        return 0.0


def defence_table(rows: list[dict]) -> dict:
    """{(team, week): {d_cay, d_yac, d_tgt, d_ypc}} from every game the
    defence played BEFORE that week (three at least), summed over the
    receivers and backs it faced."""
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in rows:
        d, w = r.get("opponent_team"), int(float(r["week"]))
        g = per[d][w]
        g["tgt"] += _n(r, "targets")
        g["rec"] += _n(r, "receptions")
        g["ryd"] += _n(r, "receiving_yards")
        g["yac"] += _n(r, "receiving_yards_after_catch")
        g["car"] += _n(r, "carries") if str(r.get("position") or "").upper() == "RB" else 0.0
        g["rush"] += _n(r, "rushing_yards") if str(r.get("position") or "").upper() == "RB" else 0.0
    out = {}
    for d, weeks in per.items():
        for w in range(4, 23):
            prev = [weeks[x] for x in weeks if x < w]
            if len(prev) < 3:
                continue
            s = defaultdict(float)
            for g in prev:
                for k, v in g.items():
                    s[k] += v
            out[(d, w)] = {"d_cay": (s["ryd"] - s["yac"]) / max(1.0, s["tgt"]),
                           "d_yac": s["yac"] / max(1.0, s["rec"]),
                           "d_tgt": s["tgt"] / len(prev),
                           "d_ypc": s["rush"] / max(1.0, s["car"])}
    return out


def rows_for(season: int) -> list[dict]:
    now, before = load(season), load(season - 1)
    dtab = defence_table(now)
    team_tgt = defaultdict(float)
    for r in now:
        team_tgt[(r.get("team"), int(float(r["week"])))] += _n(r, "targets")
    prev = defaultdict(list)
    for r in before:
        prev[r["player_display_name"]].append(r)
    mine = defaultdict(list)
    for r in now:
        mine[(r["player_display_name"], r.get("team"))].append(r)
    out = []
    for (name, team), games in mine.items():
        games.sort(key=lambda r: int(float(r["week"])))
        pos = str(games[0].get("position") or "").upper()
        for m in ("receptions", "rec_yds", "rush_yds"):
            if pos not in (("RB",) if m == "rush_yds" else ("WR", "TE", "RB")):
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            gs = [r for r in games if quarterbacked(r, m)]
            k = C.SEASON_PRIOR_GAMES.get(m)
            for i, r in enumerate(gs):
                w = int(float(r["week"]))
                if w < 4 or i < 3:
                    continue
                d = dtab.get((r.get("opponent_team"), w))
                if not d:
                    continue
                hist = gs[:i]
                vals = [stat_value(x, m) for x in hist]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v) for x, v in zip(hist, vals)][::-1]
                career = sum(vals) / len(vals)
                if compute_form(logs, career, None).mean < C.SEASON_PRIOR_FLOOR[m]:
                    continue
                anchored = bool(k) and len(last) >= C.MIN_PRIOR_GAMES
                form = (compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                     prior_games=k) if anchored else compute_form(logs, career, None))
                tg = sum(_n(x, "targets") for x in hist)
                rc = sum(_n(x, "receptions") for x in hist)
                ca = sum(_n(x, "carries") for x in hist)
                if (m != "rush_yds" and tg < 12) or (m == "rush_yds" and ca < 20):
                    continue
                tteam = sum(team_tgt[(team, int(float(x["week"])))] for x in hist)
                feats = {"adot": (sum(_n(x, "receiving_air_yards") for x in hist) + 50 * 8.0) / (tg + 50),
                         "yac": (sum(_n(x, "receiving_yards_after_catch") for x in hist) + 20 * 5.0) / (rc + 20),
                         "tshare": tg / max(1.0, tteam),
                         "carpg": ca / len(hist),
                         "ypc": (sum(_n(x, "rushing_yards") for x in hist) + 50 * 4.2) / (ca + 50)}
                out.append({"m": m, "s": season, "who": f"{name}|{season}", "y": stat_value(r, m),
                            "mu": form.mean, **feats, **d})
    return out


# --- ridge, by the normal equations ------------------------------------------
def solve(A: list, b: list) -> list:
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def ridge(X: list, y: list, lam: float) -> list:
    n = len(X[0])
    A = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for xi, yi in zip(X, y):
        for i in range(n):
            b[i] += xi[i] * yi
            for j in range(n):
                A[i][j] += xi[i] * xi[j]
    for i in range(1, n):          # the intercept is not penalised
        A[i][i] += lam
    return solve(A, b)


class Design:
    """Columns standardised on the training rows: [1, mu, A, D] (+ A*D)."""

    def __init__(self, train: list[dict], a: str, d: str):
        self.a, self.d = a, d
        self.stats = {}
        for c in ("mu", a, d, "ad"):
            vals = [self._raw(x, c) for x in train]
            m = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) or 1.0
            self.stats[c] = (m, sd)

    def _raw(self, x: dict, c: str) -> float:
        if c == "ad":
            return x[self.a] * x[self.d]
        return x[c]

    def row(self, x: dict, inter: bool) -> list:
        cols = ["mu", self.a, self.d] + (["ad"] if inter else [])
        return [1.0] + [(self._raw(x, c) - self.stats[c][0]) / self.stats[c][1] for c in cols]


def boot(diffs_by: dict, seed: int = 11) -> tuple:
    groups = [(sum(v), len(v)) for v in diffs_by.values()]
    n = sum(c for _s, c in groups)
    mean = sum(s for s, _c in groups) / n
    rng = random.Random(seed)
    stats = []
    for _ in range(BOOT):
        tot = cnt = 0.0
        for _ in range(len(groups)):
            s, c = groups[rng.randrange(len(groups))]
            tot += s
            cnt += c
        stats.append(tot / cnt)
    stats.sort()
    return mean, stats[int(BOOT * ALPHA / 2)], stats[min(BOOT - 1, int(BOOT * (1 - ALPHA / 2)))]


def evaluate(pid: str, train: list, valid: list, hold: list | None) -> dict:
    m, _poss, a, d = PAIRS[pid]
    tr = [x for x in train if x["m"] == m]
    va = [x for x in valid if x["m"] == m]
    des = Design(tr, a, d)
    res = {"pair": pid, "market": m, "n_train": len(tr)}
    fits = {}
    for inter in (False, True):
        Xtr = [des.row(x, inter) for x in tr]
        ytr = [x["y"] for x in tr]
        best = None
        for lam in LAMBDAS:
            w = ridge(Xtr, ytr, lam)
            mse = sum((sum(p * q for p, q in zip(w, des.row(x, inter))) - x["y"]) ** 2 for x in va) / len(va)
            if best is None or mse < best[0]:
                best = (mse, lam, w)
        fits[inter] = best
    res["lam"] = (fits[False][1], fits[True][1])
    res["coef_ad"] = round(fits[True][2][-1], 3)

    def diffs(rows):
        by = defaultdict(list)
        for x in rows:
            eb = (sum(p * q for p, q in zip(fits[False][2], des.row(x, False))) - x["y"]) ** 2
            ec = (sum(p * q for p, q in zip(fits[True][2], des.row(x, True))) - x["y"]) ** 2
            by[x["who"]].append(ec - eb)
        return by
    res["valid"] = (len(va), fits[False][0], fits[True][0]) + boot(diffs(va))
    if hold is not None:
        ho = [x for x in hold if x["m"] == m]
        base = sum((sum(p * q for p, q in zip(fits[False][2], des.row(x, False))) - x["y"]) ** 2 for x in ho) / len(ho)
        cand = sum((sum(p * q for p, q in zip(fits[True][2], des.row(x, True))) - x["y"]) ** 2 for x in ho) / len(ho)
        res["hold"] = (len(ho), base, cand) + boot(diffs(ho))
    return res


def decide(res: dict) -> str:
    v = res["valid"]
    if v[2] >= v[1]:
        return "REJECTED (validation)"
    if "hold" not in res:
        return "validation passed; holdout not yet read"
    h = res["hold"]
    if h[2] >= h[1]:
        return "REJECTED (holdout)"
    return "ADVANCE" if h[5] < 0 else "INCONCLUSIVE"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="also score 2024-2025 (run once)")
    a = ap.parse_args(argv)
    train = [x for s in TRAIN for x in rows_for(s)]
    valid = [x for s in VALID for x in rows_for(s)]
    hold = [x for s in HOLD for x in rows_for(s)] if a.holdout else None
    print(f"EXP-002 matchup interactions — {len(train):,} training rows, {len(valid):,} validation"
          + (f", {len(hold):,} holdout" if hold is not None else ""))
    for pid in PAIRS:
        r = evaluate(pid, train, valid, hold)
        _m, _p, ta, td = PAIRS[pid]
        line = (f"  {pid} {r['market']:<10} {ta} x {td:<6} coef(AxD, standardised) {r['coef_ad']:+.3f}  "
                f"ridge {r['lam'][0]:g}/{r['lam'][1]:g}\n"
                f"      validation n={r['valid'][0]:,}  MSE base {r['valid'][1]:.3f} cand {r['valid'][2]:.3f}  "
                f"diff {r['valid'][3]:+.4f} [{r['valid'][4]:+.4f}, {r['valid'][5]:+.4f}]")
        if "hold" in r:
            h = r["hold"]
            line += (f"\n      holdout    n={h[0]:,}  MSE base {h[1]:.3f} cand {h[2]:.3f}  "
                     f"diff {h[3]:+.4f} [{h[4]:+.4f}, {h[5]:+.4f}]")
        print(line + f"\n      -> {decide(r)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
