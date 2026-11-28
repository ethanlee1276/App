#!/usr/bin/env python3
"""How spread out is a player's game around his own mean? — the shape behind engine/fieldcurve.

    python3 fieldcurvefit.py                 (2022-2025, the numbers in engine/fieldcurve.PHI)
    python3 fieldcurvefit.py --seasons 2019 2020 2021

For every market the NFL board prices, each regular-season player-season
with at least MIN_GAMES games at a regular's level (FLOOR) gives its mean
and its game-to-game variance; PHI = the variance over the mean, pooled
with each season weighted by its games less one, overall and by low,
middle and high mean. engine/fieldcurve reads a count as a negative
binomial and yards as a gamma, each with variance PHI × mean, so the
question this answers is whether one PHI fits every level of mean (it
does, in all but rushing attempts — see engine/fieldcurve's docstring for
the 2022-2025 table this prints).

Quarterback markets count only games he really played
(engine.sources.nflverse.quarterbacked). Reads data/cache only.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.sources import nflverse as N                      # noqa: E402

MIN_GAMES = 6
#: A regular's level, per market: below it a player-season is a role
#: player's and his spread says more about his role than the market's.
FLOOR = {"receptions": 2, "rec_yds": 20, "rush_yds": 20, "rush_att": 5, "pass_att": 20, "pass_cmp": 12,
         "pass_yds": 150, "pass_td": 0.8, "pass_int": 0.4, "pass_rush_yds": 150, "rush_rec_yds": 30,
         "tackles_ast": 3, "fg_made": 1, "kick_pts": 5}
MARKETS = tuple(FLOOR)


def groups(rows) -> dict:
    """{(market, season, player, team): [his games' values]} from weekly rows."""
    out: dict = defaultdict(list)
    for r in rows:
        if (r.get("season_type") or "REG") != "REG":
            continue
        for m in MARKETS:
            if not N.quarterbacked(r, m):
                continue
            try:
                v = N.stat_value(r, m)
            except (KeyError, TypeError, ValueError):
                continue
            out[(m, r.get("season"), r.get("player_display_name"), r.get("team") or r.get("recent_team"))].append(v)
    return out


def phi(gs: dict, market: str) -> tuple:
    """(PHI pooled, [(mean, PHI) by low / middle / high mean], player-seasons)."""
    w = []
    for (m, *_rest), vs in gs.items():
        if m != market or len(vs) < MIN_GAMES:
            continue
        n = len(vs)
        mu = sum(vs) / n
        if mu < FLOOR[market] or mu <= 0:
            continue
        w.append((n - 1, mu, sum((v - mu) ** 2 for v in vs) / (n - 1)))
    if not w:
        return None, [], 0

    def pooled(part):
        return sum(k * s2 for k, _mu, s2 in part) / sum(k * mu for k, mu, _s2 in part)
    w.sort(key=lambda z: z[1])
    k = len(w) // 3
    thirds = [(sum(mu for _k, mu, _s in p) / len(p), pooled(p)) for p in (w[:k], w[k:2 * k], w[2 * k:]) if p]
    return pooled(w), thirds, len(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", nargs="*", type=int, default=[2022, 2023, 2024, 2025])
    a = ap.parse_args(argv)
    rows = []
    for s in a.seasons:
        with open(ROOT / "data" / "cache" / f"player_stats_{s}.csv", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    gs = groups(rows)
    print(f"variance over mean (PHI) by market, {a.seasons[0]}-{a.seasons[-1]} regular season, "
          f"player-seasons of {MIN_GAMES}+ games at a regular's level")
    for m in MARKETS:
        p, thirds, n = phi(gs, m)
        if p is None:
            print(f"  {m:<14} no player-seasons")
            continue
        parts = ", ".join(f"{mu:.1f}: {t:.2f}" for mu, t in thirds)
        print(f"  {m:<14} PHI {p:7.3f}  ({n} player-seasons; by mean {parts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
