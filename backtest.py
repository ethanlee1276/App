#!/usr/bin/env python3
"""Backtest the model over historical nflverse weeks.

    python3 backtest.py 2024 --weeks 6-17
    python3 backtest.py 2023 --weeks 8,9,10 --min-confidence 7

Needs weekly stats for the season (release-gated → drop a CSV at
data/cache/player_stats_<season>.csv; see the README). Projections for each week
are built from prior weeks only (walk-forward), then settled against that week's
actual box score.
"""

from __future__ import annotations

import argparse
import sys

from engine.backtest import backtest_from_stats
from engine.sources.fetch import DataUnavailable
from engine.rules import RuleConfig


def parse_weeks(spec: str) -> list[int]:
    weeks: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            weeks.extend(range(int(a), int(b) + 1))
        elif part:
            weeks.append(int(part))
    return sorted(set(weeks))


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest & calibration report.")
    ap.add_argument("season", type=int)
    ap.add_argument("--weeks", default="6-17", help="e.g. 6-17 or 8,9,10")
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    args = ap.parse_args()

    weeks = parse_weeks(args.weeks)
    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)

    try:
        report = backtest_from_stats(args.season, weeks, config)
    except DataUnavailable as exc:
        print("⚠️  Backtest needs weekly stats.\n")
        print(exc)
        sys.exit(2)

    print(f"\n{args.season} · weeks {weeks[0]}–{weeks[-1]}")
    print(report.summary())
    if report.n == 0:
        print("\n(No settled props — check that the stats CSV covers these weeks.)")


if __name__ == "__main__":
    main()
