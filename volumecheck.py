#!/usr/bin/env python3
"""How much of an NFL team's volume does the betting line know? — tried on seasons it never saw.

    python3 volumecheck.py               (downloads nflverse's weekly team stats and games file)
    python3 volumecheck.py --dir DIR     (stats_team_week_<year>.csv and games.csv already in DIR)

Ethan, 2026-10-17: "new equations ... make the NFL elite". The loss
autopsy (engine/autopsy) names USAGE/VOLUME the step most often wrong, so
the first question is how much of a team's volume is knowable at all
before kickoff. A team's dropbacks (attempts + sacks), carries and plays
in a game are predicted two ways, each fitted on earlier seasons only and
scored on the next:

    base    its own last six games and what its opponent has allowed
    market  the same, plus the line's implied team points and the spread
            (from the team's side: positive = favoured)

THE ANSWER, 2026-10-17, 4,316 team-games 2016-2025 (run in the sandbox off
the public files): the line knows a little, consistently. Error falls 0.5
to 1.5% in most held-out seasons (dropbacks better in 6 of 7, carries 7 of
7, plays 6 of 7 with one tie). Each implied point is about +0.4 dropbacks
and −0.2 carries; each point of favour about −0.2 dropbacks and +0.26
carries. And the floor is high: a team's dropbacks miss by about eight a
game (on a mean near 37) whatever is known, which is game flow, not a
model. So the volume the autopsy blames is mostly the PLAYER's share of
it, not the team's total. The script tilt already in the projection
(engine/gamescript) carries the spread's part; this is recorded, not wired,
so the gain is not counted twice.

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

SEASONS = range(2016, 2026)
FIRST_TEST = 2019
TRAIL = 6
TARGETS = ("db", "car", "plays")
BASE = "https://github.com/nflverse/nflverse-data/releases/download/stats_team"


def team_games(games: list[dict], stats: list[dict]) -> list[dict]:
    """One row per team-game of the regular season with its volume and the line."""
    lines = {g["game_id"]: g for g in games if g.get("spread_line") and g.get("total_line")}
    out = []
    for r in stats:
        if r.get("season_type") != "REG":
            continue
        g = lines.get(r.get("game_id"))
        if not g:
            continue
        try:
            sp, tot = float(g["spread_line"]), float(g["total_line"])
            db = float(r["attempts"]) + float(r["sacks_suffered"])
            car = float(r["carries"])
            season, week = int(r["season"]), int(r["week"])
        except (KeyError, TypeError, ValueError):
            continue
        home = r["team"] == g["home_team"]
        out.append({"season": season, "week": week, "team": r["team"], "opp": r.get("opponent_team", ""),
                    "imp": tot / 2 + (sp / 2 if home else -sp / 2), "tsp": sp if home else -sp,
                    "db": db, "car": car, "plays": db + car})
    return out


def with_trailing(rows: list[dict]) -> list[dict]:
    """Each row's own and its opponent's-allowed means over the TRAIL games
    before it that season; rows with fewer than three behind them are left out."""
    own, allowed = defaultdict(list), defaultdict(list)
    for r in sorted(rows, key=lambda x: (x["season"], x["week"])):
        own[(r["season"], r["team"])].append(r)
        allowed[(r["season"], r["opp"])].append(r)

    def mean(lst, r, k):
        prev = [x[k] for x in lst if x["week"] < r["week"]][-TRAIL:]
        return sum(prev) / len(prev) if len(prev) >= 3 else None

    out = []
    for r in rows:
        d = dict(r)
        for k in TARGETS:
            d["own_" + k] = mean(own[(r["season"], r["team"])], r, k)
            d["opp_" + k] = mean(allowed[(r["season"], r["opp"])], r, k)
        if all(d["own_" + k] is not None and d["opp_" + k] is not None for k in TARGETS):
            out.append(d)
    return out


def ols(X: list, y: list) -> list:
    """Least squares by the normal equations (a handful of columns)."""
    n = len(X[0])
    A = [[0.0] * (n + 1) for _ in range(n)]
    for xi, yi in zip(X, y):
        for i in range(n):
            A[i][n] += xi[i] * yi
            for j in range(n):
                A[i][j] += xi[i] * xi[j]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(A[r][c]))
        A[c], A[p] = A[p], A[c]
        for r in range(n):
            if r != c and A[c][c]:
                f = A[r][c] / A[c][c]
                for k in range(c, n + 1):
                    A[r][k] -= f * A[c][k]
    return [A[i][n] / A[i][i] if A[i][i] else 0.0 for i in range(n)]


def features(r: dict, target: str, market: bool) -> list:
    base = [1.0, r["own_" + target], r["opp_" + target]]
    return base + [r["imp"], r["tsp"]] if market else base


def heldout(data: list[dict], target: str) -> list[dict]:
    out = []
    for s in sorted({r["season"] for r in data}):
        if s < FIRST_TEST:
            continue
        tr = [r for r in data if r["season"] < s]
        te = [r for r in data if r["season"] == s]
        if len(tr) < 200 or not te:
            continue
        res = {"season": s, "games": len(te)}
        for name, mk in (("base", False), ("market", True)):
            w = ols([features(r, target, mk) for r in tr], [r[target] for r in tr])
            err = [sum(a * b for a, b in zip(w, features(r, target, mk))) - r[target] for r in te]
            res[name] = round(math.sqrt(sum(e * e for e in err) / len(err)), 3)
            res[name + "_w"] = [round(x, 3) for x in w]
        out.append(res)
    return out


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", help="a folder holding games.csv and stats_team_week_<year>.csv")
    a = ap.parse_args(argv)
    if a.dir:
        d = Path(a.dir)
        games = _read(d / "games.csv")
        stats = [row for y in SEASONS if (d / f"stats_team_week_{y}.csv").exists()
                 for row in _read(d / f"stats_team_week_{y}.csv")]
    else:
        from engine.sources.fetch import fetch_csv
        from engine.sources.nflverse import load_schedules
        games = load_schedules()
        stats = [row for y in SEASONS
                 for row in fetch_csv(f"{BASE}/stats_team_week_{y}.csv", f"stats_team_week_{y}.csv")]
    data = with_trailing(team_games(games, stats))
    print(f"NFL team volume against the line — {len(data):,} team-games with six weeks behind them")
    names = {"db": "dropbacks", "car": "carries", "plays": "plays"}
    for t in TARGETS:
        folds = heldout(data, t)
        better = sum(1 for f in folds if f["market"] < f["base"])
        cut = (sum(f["base"] for f in folds) - sum(f["market"] for f in folds)) / max(1e-9, sum(f["base"] for f in folds))
        w = folds[-1]["market_w"] if folds else [0, 0, 0, 0, 0]
        print(f"  {names[t]:<9} error {sum(f['base'] for f in folds) / max(1, len(folds)):.2f} → "
              f"{sum(f['market'] for f in folds) / max(1, len(folds)):.2f} ({cut:+.1%}), better in {better}/{len(folds)} "
              f"seasons · per implied point {w[3]:+.2f}, per point of favour {w[4]:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
