#!/usr/bin/env python3
"""Build a live MLB slate from the free MLB Stats API and run the model.

    python3 mlb_build.py 2024-06-20              # a given date (YYYY-MM-DD)
    python3 mlb_build.py 2024-06-20 --out web/data/mlb_recommendations.json

Pulls the schedule, probable pitchers and per-park weather (Open-Meteo), plus
confirmed lineups and per-player game logs. Hitter props come from posted
lineups (held otherwise); pitcher strikeout props from the probable starters.
Lines are recent-form proxies — attach an odds feed for real book edges.

Needs statsapi.mlb.com / api.open-meteo.com to be reachable (blocked in some
sandboxes; see the README).
"""

from __future__ import annotations

import argparse
import json
import sys

from engine.mlb.sources.statslogs import build_live_slate
from engine.mlb.pipeline import run_mlb_slate
from engine.sources.fetch import DataUnavailable
from engine.rules import RuleConfig


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a live MLB slate and run the model.")
    ap.add_argument("date", help="slate date, YYYY-MM-DD")
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--out", default=None, help="write recommendations JSON here")
    args = ap.parse_args()

    try:
        slate = build_live_slate(args.date)
    except DataUnavailable as exc:
        print("⚠️  Live MLB data unavailable.\n")
        print(exc)
        sys.exit(2)

    if not slate.props:
        print(f"No props built for {args.date} — lineups may not be posted yet. "
              f"Pitcher props need probable starters; hitter props need confirmed lineups.")

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    result = run_mlb_slate(slate, config)

    c = result["counts"]
    confirmed = sum(1 for g in slate.games if g.lineups_confirmed)
    print(f"\n{args.date}: {len(slate.games)} games ({confirmed} with confirmed lineups)")
    print(f"Analyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    print("(lines are recent-form proxies — attach an odds feed for real book edges)\n")
    for r in result["recommendations"][:30]:
        flag = "✅" if r["recommended"] else "  "
        print(f"  {flag} {r['grade']:>11}  conf {r['confidence']:>4}  "
              f"edge {r['edge']:+.1%}  {r['headline']}")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
