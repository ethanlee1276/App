#!/usr/bin/env python3
"""Re-measure what a teammate out at his position does to a player (engine/matefit.py).

    python3 matefit.py                     # 2022-2025
    python3 matefit.py --seasons 2021-2025
    python3 matefit.py --early             # weeks 2-3, form carried from last season
    python3 matefit.py --snaps             # depth ranked on snap share (what the board uses)
    python3 matefit.py --back              # a teammate BACK: the deflation, held out by season

Reads data/cache/player_stats_<season>.csv (the NFL build's box scores) and
prints, per market, position and case, the multiplier the games show, its
SE, per season, and what engine/teammates.EFFECT ships.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from engine import matefit as F
from engine import teammates as T

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2025")
    ap.add_argument("--early", action="store_true",
                    help="measure weeks 2-3 (ranked on the games so far, form carried)")
    ap.add_argument("--cross", action="store_true",
                    help="a target leader out at ANOTHER position (engine/matefit.cross_samples)")
    ap.add_argument("--snaps", action="store_true",
                    help="rank the depth order on snap share (data/cache/snap_counts_<season>.csv)")
    ap.add_argument("--back", action="store_true",
                    help="a teammate BACK tonight: the games he missed deflated by the measured "
                         "absence, each season held out (engine/matefit.back_check)")
    args = ap.parse_args()
    if args.back:
        args.snaps = True
    a, _, b = args.seasons.partition("-")
    seasons = {}
    for s in range(int(a) - (1 if args.early else 0), int(b or a) + 1):
        with open(ROOT / "data" / "cache" / f"player_stats_{s}.csv", newline="") as fh:
            seasons[s] = list(csv.DictReader(fh))
    snaps = None
    if args.snaps:
        snaps = {}
        for s in seasons:
            path = ROOT / "data" / "cache" / f"snap_counts_{s}.csv"
            if path.exists():
                with open(path, newline="") as fh:
                    snaps[s] = list(csv.DictReader(fh))
    if args.back:
        _back(seasons, snaps)
        return
    res = F.measure(F.cross_samples(seasons) if args.cross
                    else F.early_samples(seasons) if args.early else F.samples(seasons, snaps))
    rule = F.shipped(res)
    if args.cross:
        # Two games are not an effect: the plain rule passes a cell with
        # one season of data, and two of them did (engine/matefit.MIN_CROSS_N).
        rule = {k: v for k, v in rule.items() if res[k]["n"] >= F.MIN_CROSS_N}
    for (m, g, case), r in sorted(res.items()):
        now = (getattr(T, "EFFECT_CROSS", {}) if args.cross
               else T.EFFECT_SNAPS if args.snaps else T.EFFECT).get((m, g, case))
        print(f"  {m:<11}{g:<3}{case:<11} ×{r['mult']:.3f} ± {r['se']:.3f}  n {r['n']:<4} "
              + " ".join(f"{s}:{x:.3f}" for s, x in r["per"].items())
              + f"   rule: {'×%.3f' % rule[(m, g, case)] if (m, g, case) in rule else 'not applied'}"
              + f"   shipped: {'—' if now is None else '×%.3f' % now}")
    if args.snaps or args.cross:
        print(f"\n  {'EFFECT_CROSS' if args.cross else 'EFFECT_SNAPS'} = {{")
        for k, v in sorted(rule.items()):
            print(f"      {k!r}: {v:.3f},")
        print("  }")


def _back(seasons: dict, snaps: dict) -> None:
    """Print the held-out squared-error cut on the games a teammate came
    back to, per market, position and season, and the residual table the
    shipping rule passes on every season against teammates.BACK_RESIDUAL."""
    rep = F.back_check(seasons, snaps)
    print("Squared error cut on the games a teammate came back to, each season held out:")
    print("  market     pos season    n   deflated  +residual")
    for (m, g, s), h in sorted(rep["held"].items()):
        if not h["raw"]:
            continue
        print(f"  {m:<11}{g:<4}{s}  {h['n']:5}   {(1 - h['deflated'] / h['raw']) * 100:+6.1f}%  "
              f"{(1 - h['residual'] / h['raw']) * 100:+6.1f}%")
    print("\n  The bar per market and position (cut overall, at most one season worse):")
    for (m, g), ok in sorted(rep["cells"].items()):
        print(f"    {m:<11}{g:<4}{'passes' if ok else 'fails'}")
    print("\n  BACK_CELLS = {")
    for k, ok in sorted(rep["cells"].items()):
        if ok:
            print(f"      {k!r},")
    print("  }")
    print(f"  shipped: {sorted(T.BACK_CELLS)}")
    print("\n  BACK_RESIDUAL = {")
    for k, v in sorted(rep["residual"].items()):
        print(f"      {k!r}: {v:.3f},")
    print("  }")
    print(f"  shipped: {T.BACK_RESIDUAL}")


if __name__ == "__main__":
    main()
