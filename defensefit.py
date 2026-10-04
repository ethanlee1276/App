#!/usr/bin/env python3
"""Re-measure how much a defence's matchup reaches one player (engine/defensefit.py).

    python3 defensefit.py                      # every cached season, each held out in turn
    python3 defensefit.py --seasons 2022-2025

Reads nflverse weekly box scores (data/cache/player_stats_<season>.csv, the
same files the NFL build reads) and prints, per market and position:

  * the transfer b — how much of a defence's rating moves a player's line;
  * the held-out gain — the share of squared error it removes on a season
    it was not fitted on, for every season held out in turn;
  * the same for the ratings the model used before 2026-09-23.

engine/defensevs.TRANSFER and MODEL_STAT are set from this output. Change
them only when a re-run says to, and say so in the commit.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from engine import defensefit as F
from engine import defensevs as D

ROOT = Path(__file__).resolve().parent


def _load(season: int) -> list[dict]:
    p = ROOT / "data" / "cache" / f"player_stats_{season}.csv"
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="", help="e.g. 2022-2025 (default: every complete cached season)")
    args = ap.parse_args()
    if args.seasons:
        a, _, b = args.seasons.partition("-")
        years = list(range(int(a), int(b or a) + 1))
    else:
        years = sorted(int(p.stem.rsplit("_", 1)[1]) for p in (ROOT / "data" / "cache").glob("player_stats_*.csv"))
        years = [y for y in years if len({r.get("week") for r in _load(y)}) >= 17]      # complete seasons
    seasons = {y: _load(y) for y in years}
    if len(seasons) < 2:
        raise SystemExit("need at least two complete seasons of data/cache/player_stats_<season>.csv")
    F.SHRINK_GRID = (D.SHRINK_GAMES,)
    for label, kw in (("ratings before 2026-09-23", {"legacy": True}),
                      ("the model now (defensevs.MODEL_STAT, shrunk toward last season)",
                       {"with_prior": True, "model": True})):
        print(f"\n== {label}")
        table: dict = {}
        for test in years:
            r = F.study(seasons, test, **kw)
            for m, x in r["markets"].items():
                for g, xg in (x.get("by_group") or {"all": x}).items():
                    table.setdefault((m, g), []).append((test, xg["b"], xg["held_out_gain"]))
        for (m, g), rows in sorted(table.items()):
            mean = sum(h for _t, _b, h in rows) / len(rows)
            print(f"  {m:<11} {g:<4} held out " + "  ".join(f"{t}:{100 * h:+.2f}%" for t, _b, h in rows)
                  + f"   mean {100 * mean:+.2f}%   b " + " ".join(f"{b:+.2f}" for _t, b, _h in rows))
    whole = F.study(seasons, None, with_prior=True, model=True)
    print(f"\n== fitted on every season (shrink {D.SHRINK_GAMES:g} games) against what the model uses")
    for m, x in whole["markets"].items():
        for g, xg in (x.get("by_group") or {}).items():
            now = D.TRANSFER.get((m, g))
            print(f"  {m:<11} {g:<4} b = {xg['b']:+.3f} ± {xg.get('se') or 0:.3f} (n {xg['n']})   "
                  f"in use: {'—' if now is None else f'{now:.2f}'}")


if __name__ == "__main__":
    main()
