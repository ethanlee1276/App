#!/usr/bin/env python3
"""Does the referee know something the closing line does not? (NFL) — tried on seasons it never saw.

    python3 refcheck.py                 (downloads nflverse's games file, ~2 MB)
    python3 refcheck.py --file games.csv

Ethan, 2026-10-17: "new ways of gathering data ... new equations". The
officials are a data source the site has never read, and nflverse's games
file names every NFL game's referee back to 2006. Before any of it is
wired, the one question that decides whether it is worth wiring: does a
referee's past predict a game's total against the CLOSING total (or its
margin against the closing spread) in a season his estimate never saw?

THE TEST, WRITTEN BEFORE THE RUN. For each season S, every referee's mean
residual (points over the closing total; margin over the closing spread)
is read from the seasons before S only, shrunk toward zero by K games, and
used to predict S's games. It earns a place only if the held-out error is
lower than predicting zero in most seasons and the pooled correlation is
positive.

THE ANSWER, 2026-10-17, 7,340 games 2015 to week 4 of 2026 (run in the
sandbox off the public file): it does not. Held-out correlation −0.02 on
totals and −0.01 on margins at every shrink tried (K = 20, 50, 100), and the
error is worse than predicting nothing in 8 to 10 of the 11 seasons scored. Whatever a crew does to a
game, the closing number has it already. Nothing is wired, and the
officials are not a pre-game NFL input; this script stays so the question
is answered in one command rather than proposed again. (nflverse also
fills the referee only after a game is played, so it could not have been
a pre-game input from this file in any case.)

Read-only; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SHRINKS = (20, 50, 100)
FIRST_TEST = 2016


def rows_from(raw: list[dict]) -> list[dict]:
    """Played games with a referee and both closing numbers."""
    out = []
    for r in raw:
        try:
            hs, as_ = float(r["home_score"]), float(r["away_score"])
            tot, spr = float(r["total_line"]), float(r["spread_line"])
            season = int(r["season"])
        except (KeyError, TypeError, ValueError):
            continue
        ref = (r.get("referee") or "").strip()
        if not ref:
            continue
        out.append({"season": season, "ref": ref, "total": hs + as_ - tot,
                    "margin": hs - as_ - spr})
    return out


def _corr(a: list, b: list) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def heldout(games: list[dict], target: str, k: float) -> list[dict]:
    """Per season: the referees' shrunk means from earlier seasons only, scored."""
    seasons = sorted({g["season"] for g in games})
    out = []
    for s in seasons:
        if s < FIRST_TEST:
            continue
        prior = defaultdict(lambda: [0.0, 0])
        for g in games:
            if g["season"] < s:
                prior[g["ref"]][0] += g[target]
                prior[g["ref"]][1] += 1
        test = [g for g in games if g["season"] == s]
        if not test:
            continue
        pred = [prior[g["ref"]][0] / (prior[g["ref"]][1] + k) for g in test]
        ys = [g[target] for g in test]
        base = sum(y * y for y in ys) / len(ys)
        mse = sum((y - p) ** 2 for y, p in zip(ys, pred)) / len(ys)
        out.append({"season": s, "games": len(test), "corr": round(_corr(pred, ys), 3),
                    "gain_pct": round(100.0 * (base - mse) / base, 2) if base else 0.0})
    return out


def verdict(folds: list[dict]) -> dict:
    if not folds:
        return {"holds": False, "why": "no season to score"}
    better = sum(1 for f in folds if f["gain_pct"] > 0)
    tot = sum(f["games"] for f in folds)
    corr = sum(f["corr"] * f["games"] for f in folds) / tot
    holds = better > len(folds) / 2 and corr > 0
    return {"holds": holds, "seasons_better": better, "seasons": len(folds), "corr": round(corr, 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="a local copy of nflverse's games.csv")
    a = ap.parse_args(argv)
    if a.file:
        with open(a.file, newline="", encoding="utf-8") as fh:
            raw = list(csv.DictReader(fh))
    else:
        from engine.sources.nflverse import load_schedules
        raw = load_schedules()
    games = rows_from(raw)
    print(f"Referees against the closing line — {len(games):,} NFL games with a referee and both closes")
    for target, label in (("total", "points over the closing total"), ("margin", "margin over the closing spread")):
        for k in SHRINKS:
            folds = heldout(games, target, k)
            v = verdict(folds)
            print(f"  {label:<32} shrink {k:>3}: correlation {v.get('corr', 0):+.3f}, "
                  f"better than zero in {v.get('seasons_better', 0)}/{v.get('seasons', 0)} seasons — "
                  f"{'HOLDS' if v['holds'] else 'does not hold'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
