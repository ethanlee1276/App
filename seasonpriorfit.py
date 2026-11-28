#!/usr/bin/env python3
"""Should a player's form lean on his own last season after week 3? — measured.

    python3 seasonpriorfit.py                 # 2022-2025, data/cache's box scores
    python3 seasonpriorfit.py --seasons 2021-2025

Ethan, 2026-10-12, four outside reports on Bills @ Rams, every one of them
anchored on last season. The model stopped reading it once a player had
three games this season. For every player-game from week 4 with three or
more games this season and MIN_PRIOR_GAMES last season, the form is taken
the way the board takes it (engine/form.compute_form over his games so
far, quarterback games filtered as player_game_logs filters them) and then
pulled toward last season's per-game number by compute_form's own prior,
w = n/(n+k). For each market, k is chosen on three seasons and the squared
error scored on the fourth, each season in turn.

THE BAR, set before the first run: a market ships only if the held-out
error falls in every season. Prints the table engine/carry.SEASON_PRIOR_GAMES
carries and the k fitted on every season. Reads the cache; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import carry as C                                    # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402

#: market -> positions measured, and the form floor below which a player
#: is no starter at it (as engine/matefit floors its markets). The board
#: applies the anchor only above the same floor (carry.SEASON_PRIOR_FLOOR).
MARKETS = {m: (pos, C.SEASON_PRIOR_FLOOR.get(m, floor)) for m, (pos, floor) in {
    "rec_yds": (("WR", "TE", "RB"), 15.0), "receptions": (("WR", "TE", "RB"), 1.5),
    "rush_yds": (("RB", "QB"), 15.0), "rush_att": (("RB",), 5.0),
    "pass_yds": (("QB",), 120.0), "pass_att": (("QB",), 18.0), "pass_cmp": (("QB",), 12.0),
    "rush_rec_yds": (("RB",), 30.0), "pass_rush_yds": (("QB",), 130.0)}.items()}
KS = (0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 10, 12, 16, 24)
FIRST_WEEK = 4


def load(season: int) -> list[dict]:
    with open(ROOT / "data" / "cache" / f"player_stats_{season}.csv", newline="") as fh:
        return [r for r in csv.DictReader(fh) if str(r.get("season_type") or "REG") == "REG"]


def points(now: list[dict], before: list[dict], season: int) -> list[dict]:
    """[{m, s, logs, career, prior, pn, y}] — one per player-game and market."""
    prev: dict = defaultdict(list)
    for r in before:
        prev[r["player_display_name"]].append(r)
    mine: dict = defaultdict(list)
    for r in now:
        mine[r["player_display_name"]].append(r)
    out = []
    for name, rows in mine.items():
        rows.sort(key=lambda r: int(float(r["week"])))
        pos = str(rows[0].get("position") or "").upper()
        for m, (poss, floor) in MARKETS.items():
            if pos not in poss:
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            if len(last) < C.MIN_PRIOR_GAMES:
                continue
            games = [r for r in rows if quarterbacked(r, m)]
            for i, r in enumerate(games):
                if int(float(r["week"])) < FIRST_WEEK or i < 3:
                    continue
                vals = [stat_value(x, m) for x in games[:i]]
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(games[:i], vals)][::-1]
                career = sum(vals) / len(vals)
                if compute_form(logs, career, None).mean < floor:
                    continue
                out.append({"m": m, "s": season, "logs": logs, "career": career,
                            "prior": sum(last) / len(last), "pn": len(last), "y": stat_value(r, m)})
    return out


def estimate(p: dict, k: float) -> float:
    if k <= 0:
        return compute_form(p["logs"], p["career"], None).mean
    return compute_form(p["logs"], p["career"], None, prior=p["prior"], prior_n=p["pn"], prior_games=k).mean


def sse(pts: list[dict], k: float) -> float:
    return sum((p["y"] - estimate(p, k)) ** 2 for p in pts)


def check(by_season: dict) -> dict:
    """{market: {"held": [(season, k, n, cut %)], "k": k on every season,
    "ships": bool}} — the bar: every held-out season's error falls."""
    out = {}
    seasons = sorted(by_season)
    for m in MARKETS:
        held = []
        for s in seasons:
            train = [p for t in seasons if t != s for p in by_season[t] if p["m"] == m]
            test = [p for p in by_season[s] if p["m"] == m]
            if not train or not test:
                continue
            k = min(KS, key=lambda kk: sse(train, kk))
            raw = sse(test, 0)
            held.append((s, k, len(test), (1 - sse(test, k) / raw) * 100 if raw else 0.0))
        allp = [p for s in seasons for p in by_season[s] if p["m"] == m]
        out[m] = {"held": held, "k": min(KS, key=lambda kk: sse(allp, kk)) if allp else 0,
                  "ships": bool(held) and all(c > 0 for *_x, c in held)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    a = ap.parse_args(argv)
    lo, _, hi = a.seasons.partition("-")
    seasons = range(int(lo), int(hi or lo) + 1)
    by_season = {s: points(load(s), load(s - 1), s) for s in seasons}
    rep = check(by_season)
    print("Held-out squared error cut, last season as the form's anchor (k chosen on the other seasons):")
    for m, r in rep.items():
        cells = "  ".join(f"{s}: k {k:g} n {n} {c:+.1f}%" for s, k, n, c in r["held"])
        print(f"  {m:<11} {cells}   {'SHIPS, k ' + format(r['k'], 'g') if r['ships'] else 'fails'}")
    print("\n  SEASON_PRIOR_GAMES = {" + ", ".join(f'"{m}": {r["k"]:g}' for m, r in rep.items() if r["ships"]) + "}")
    print(f"  shipped:             {C.SEASON_PRIOR_GAMES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
