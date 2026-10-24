#!/usr/bin/env python3
"""Re-measure what a missing starting quarterback does to his team (engine/qbfit.py).

    python3 qbfit.py                     # 2022-2025
    python3 qbfit.py --seasons 2021-2025

Reads data/cache/player_stats_<season>.csv (the NFL build's box scores) and
prints, per market, position and replacement tier, the multiplier the games
show, its SE, per season, and what engine/qbchange.EFFECT ships.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from engine import qbfit as F
from engine import qbchange as Q

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    a, _, b = ap.parse_args().seasons.partition("-")
    seasons = {}
    for s in range(int(a), int(b or a) + 1):
        with open(ROOT / "data" / "cache" / f"player_stats_{s}.csv", newline="") as fh:
            seasons[s] = list(csv.DictReader(fh))
    res = F.measure(F.samples(seasons))
    rule = F.shipped(res)
    for (m, g, tier), r in res.items():
        now = Q.EFFECT.get((m, g, tier))
        print(f"  {m:<11}{g:<3}{tier:<10} ×{r['mult']:.3f} ± {r['se']:.3f}  n {r['n']:<4} "
              + " ".join(f"{s}:{x:.3f}" for s, x in r["per"].items())
              + f"   rule: {'×%.3f' % rule[(m, g, tier)] if (m, g, tier) in rule else 'not applied'}"
              + f"   shipped: {'—' if now is None else '×%.3f' % now}")


if __name__ == "__main__":
    main()
