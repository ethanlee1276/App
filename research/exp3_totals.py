#!/usr/bin/env python3
"""EXP-003a — can a residual-corrected model beat the closing total (NFL), not just our own baseline?

    python3 research/exp3_totals.py              (fit 2006-2017, validate 2018-2021)
    python3 research/exp3_totals.py --holdout    (adds 2022-2025; run ONCE, result recorded)

Research spec Part 8, Experiment 3, its game-totals arm (Ethan, 2026-10-17).
The spec puts player props first; props need timestamped prop prices this
sandbox does not hold, so their arm is research/exp3_props_box.py, run on
the box against the site's own journal. Totals are the closest market with
real prices here: nflverse's games file carries each game's closing total
with BOTH sides' prices, 2006 onward. Registry EXP-003a.

THE FOUR FORECASTS of P(over the closing total), pushes left out of scoring:

  A  BASELINE. Expected total mu = each side's points scored and allowed
     this season before the game (shrunk toward last season's league mean
     by SHRINK games), P = 1 - Phi((line - mu) / sigma), sigma fitted.
  B  A + RESIDUAL CORRECTION: ridge on (total - mu) from pre-game context
     known at the time — dome, surface, rest days each side, division game,
     week — fitted on training seasons only, then P recomputed.
  C  THE MARKET: the closing over/under prices, de-vigged multiplicatively
     (each side's raw implied chance over their sum). An estimate of the
     market's chance, not the truth.
  D  PRESPECIFIED BLEND: logit(D) = w logit(B) + (1 - w) logit(C), w from
     a fixed grid on 2006-2021.

Observed game-day temperature and wind are in the file and are NOT used:
they are measured at the game, not forecast before it.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-17). Score: log loss on over/under.
Two questions, each at alpha 0.025 (0.05 / 2), on 2022-2025 with a
week-clustered bootstrap, and each must also hold on 2018-2021:
  Q1 does B beat A?             (does the correction carry real information)
  Q2 does D beat C?             (does any of it beat the closing market)
A market edge is claimed ONLY if Q2 passes. The closing price is the
market's last word, not a price a bettor could reliably take before it, so
even a pass would say "information the close missed", not "a profit".

Reads data/cache/games.csv; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

from exp2_interactions import ridge                              # noqa: E402

TRAIN, VALID, HOLD = range(2006, 2018), range(2018, 2022), range(2022, 2026)
SHRINK = 4.0
LAMBDAS = (0.0, 10.0, 100.0, 1000.0)
W_GRID = tuple(i / 10 for i in range(11))
ALPHA = 0.05 / 2
BOOT = 1000
CTX = ("dome", "turf", "rest_h", "rest_a", "div", "week")


def american_to_prob(o: float) -> float:
    return -o / (-o + 100.0) if o < 0 else 100.0 / (o + 100.0)


def devig(over: float, under: float) -> float:
    po, pu = american_to_prob(over), american_to_prob(under)
    return po / (po + pu)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_games(path: Path | None = None) -> list[dict]:
    with open(path or ROOT / "data" / "cache" / "games.csv", newline="") as fh:
        return [g for g in csv.DictReader(fh) if g.get("game_type") == "REG"]


def rows(games: list[dict]) -> list[dict]:
    """One row per priced, played game with what was known before it."""
    by_season = defaultdict(list)
    for g in games:
        by_season[int(g["season"])].append(g)
    league = {}
    for s, gs in by_season.items():
        pts = [float(g["home_score"]) + float(g["away_score"]) for g in gs if g.get("home_score")]
        league[s] = sum(pts) / len(pts) / 2 if pts else 21.0
    out = []
    for s, gs in sorted(by_season.items()):
        prior = league.get(s - 1, 21.0)
        scored, allowed, n = defaultdict(float), defaultdict(float), defaultdict(int)
        for wk in sorted({int(g["week"]) for g in gs}):
            for g in [g for g in gs if int(g["week"]) == wk]:
                h, a = g["home_team"], g["away_team"]
                if g.get("total_line") and g.get("over_odds") and g.get("under_odds") and g.get("home_score") and wk >= 3:
                    def rate(t, book):
                        return (book[t] + SHRINK * prior) / (n[t] + SHRINK)
                    mu = (rate(h, scored) + rate(a, allowed)) / 2 + (rate(a, scored) + rate(h, allowed)) / 2
                    total = float(g["home_score"]) + float(g["away_score"])
                    line = float(g["total_line"])
                    if total != line:
                        out.append({"s": s, "wk": f"{s}-{wk:02d}", "mu": mu, "line": line, "y": total,
                                    "over": 1.0 if total > line else 0.0,
                                    "mkt": devig(float(g["over_odds"]), float(g["under_odds"])),
                                    "dome": 1.0 if g.get("roof") in ("dome", "closed") else 0.0,
                                    "turf": 0.0 if (g.get("surface") or "").startswith("grass") else 1.0,
                                    "rest_h": float(g.get("home_rest") or 7), "rest_a": float(g.get("away_rest") or 7),
                                    "div": float(g.get("div_game") or 0), "week": float(wk)})
            for g in [g for g in gs if int(g["week"]) == wk and g.get("home_score")]:
                h, a = g["home_team"], g["away_team"]
                hs, as_ = float(g["home_score"]), float(g["away_score"])
                scored[h] += hs
                allowed[h] += as_
                scored[a] += as_
                allowed[a] += hs
                n[h] += 1
                n[a] += 1
    return out


class Model:
    def __init__(self, train: list[dict], valid: list[dict]):
        self.sigma = math.sqrt(sum((x["y"] - x["mu"]) ** 2 for x in train) / len(train))
        self.m = {c: sum(x[c] for x in train) / len(train) for c in CTX}
        self.sd = {c: (math.sqrt(sum((x[c] - self.m[c]) ** 2 for x in train) / len(train)) or 1.0) for c in CTX}
        Xtr = [self._x(x) for x in train]
        rtr = [x["y"] - x["mu"] for x in train]
        best = None
        for lam in LAMBDAS:
            w = ridge(Xtr, rtr, lam)
            ll = sum(_ll(self._pb(x, w), x["over"]) for x in valid) / len(valid)
            if best is None or ll < best[0]:
                best = (ll, lam, w)
        self.lam, self.w = best[1], best[2]
        both = train + valid
        self.blend = min(W_GRID, key=lambda wt: sum(_ll(self.pd(x, wt), x["over"]) for x in both))

    def _x(self, x: dict) -> list:
        return [1.0] + [(x[c] - self.m[c]) / self.sd[c] for c in CTX]

    def pa(self, x: dict) -> float:
        return 1.0 - _phi((x["line"] - x["mu"]) / self.sigma)

    def _pb(self, x: dict, w: list) -> float:
        adj = sum(p * q for p, q in zip(w, self._x(x)))
        return 1.0 - _phi((x["line"] - x["mu"] - adj) / self.sigma)

    def pb(self, x: dict) -> float:
        return self._pb(x, self.w)

    def pd(self, x: dict, wt: float | None = None) -> float:
        wt = self.blend if wt is None else wt
        return _sig(wt * _logit(self.pb(x)) + (1 - wt) * _logit(x["mkt"]))


def _ll(p: float, y: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def compare(model: Model, rows_: list[dict], f1, f2, seed: int = 3) -> tuple:
    """Mean log loss of f1 minus f2 and its (1 - ALPHA) interval, resampling weeks."""
    by = defaultdict(list)
    for x in rows_:
        by[x["wk"]].append(_ll(f1(x), x["over"]) - _ll(f2(x), x["over"]))
    groups = [(sum(v), len(v)) for v in by.values()]
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


def report(label: str, model: Model, rs: list[dict]) -> dict:
    lls = {k: sum(_ll(f(x), x["over"]) for x in rs) / len(rs)
           for k, f in (("A", model.pa), ("B", model.pb), ("C", lambda x: x["mkt"]), ("D", model.pd))}
    q1 = compare(model, rs, model.pb, model.pa)
    q2 = compare(model, rs, model.pd, lambda x: x["mkt"])
    print(f"\n{label}: {len(rs):,} games")
    print("  log loss  " + "  ".join(f"{k} {v:.5f}" for k, v in lls.items()))
    print(f"  Q1 B - A  {q1[0]:+.5f} [{q1[1]:+.5f}, {q1[2]:+.5f}]")
    print(f"  Q2 D - C  {q2[0]:+.5f} [{q2[1]:+.5f}, {q2[2]:+.5f}]")
    return {"q1": q1, "q2": q2, "ll": lls}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="also score 2022-2025 (run once)")
    ap.add_argument("--file", help="a local copy of nflverse's games.csv")
    a = ap.parse_args(argv)
    allrows = rows(load_games(Path(a.file) if a.file else None))
    tr = [x for x in allrows if x["s"] in TRAIN]
    va = [x for x in allrows if x["s"] in VALID]
    model = Model(tr, va)
    print(f"EXP-003a totals — sigma {model.sigma:.2f}, ridge {model.lam:g}, blend weight on B {model.blend:.1f}, "
          f"{len(tr):,} training games")
    v = report(f"validation {VALID.start}-{VALID.stop - 1}", model, va)
    h = report(f"holdout {HOLD.start}-{HOLD.stop - 1}", model, [x for x in allrows if x["s"] in HOLD]) if a.holdout else None
    print("\nDecision (bar written before the run):")
    for q, name in (("q1", "Q1 correction beats baseline"), ("q2", "Q2 beats the closing market")):
        if v[q][0] >= 0:
            verdict = "REJECTED (validation)"
        elif h is None:
            verdict = "validation passed; holdout not yet read"
        elif h[q][0] >= 0:
            verdict = "REJECTED (holdout)"
        else:
            verdict = "PASSES" if h[q][2] < 0 else "INCONCLUSIVE"
        print(f"  {name:<32} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
