#!/usr/bin/env python3
"""Build a slate from real nflverse data and run the model over it.

    python3 nfl_build.py 2024 5              # season 2024, week 5
    python3 nfl_build.py 2024 5 --out web/data/recommendations.json
    python3 nfl_build.py 2024 5 --games-only # just show real games + weather

Schedules, weather, spreads and totals come live from nflverse. Per-player game
logs and defense profiles need weekly stats, which require GitHub release access
(or a local CSV at data/cache/player_stats_<season>.csv). See the README.
"""

from __future__ import annotations

import argparse
import json
import sys

from engine.sources.nflverse import build_games, build_slate, weather_from_row, load_schedules
from engine.sources.fetch import DataUnavailable
from engine.sources import oddsapi
from engine.sources import injuries as injuries_feed
from engine.pipeline import run_slate
from engine.rules import RuleConfig


def show_games(season: int, week: int) -> None:
    games = build_games(season, week)
    if not games:
        print(f"No games found for {season} week {week}.")
        return
    print(f"\n{len(games)} games — {season} week {week}\n")
    for g in games:
        w = g.weather
        cond = "dome" if w.dome else f"{w.temp_f:.0f}°F, wind {w.wind_mph:.0f}mph"
        fav = g.home if g.spread < 0 else g.away
        print(f"  {g.away:>3} @ {g.home:<3}  spread {g.spread:+.1f} (fav {fav})  "
              f"total {g.total:.1f}  · {cond}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build an nflverse slate and run the model.")
    ap.add_argument("season", type=int)
    ap.add_argument("week", type=int)
    ap.add_argument("--games-only", action="store_true",
                    help="Only print real games + weather (no stats needed).")
    ap.add_argument("--injuries", action="store_true",
                    help="Attach real nflverse injury reports (holds + knock-on effects).")
    ap.add_argument("--odds", action="store_true",
                    help="Attach real sportsbook lines via The Odds API (needs ODDS_API_KEY).")
    ap.add_argument("--books", default=None,
                    help="Comma-separated Odds API bookmaker keys (default: all supported).")
    ap.add_argument("--model", default=None,
                    help="Path to a trained model JSON (uses learned projections).")
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--out", default=None, help="Write recommendations JSON here.")
    args = ap.parse_args()

    show_games(args.season, args.week)
    if args.games_only:
        return

    try:
        slate = build_slate(args.season, args.week)
    except DataUnavailable as exc:
        print("\n⚠️  Full projections need weekly player stats.\n")
        print(exc)
        print("\nTip: run with --games-only to use just the live schedule/weather layer.")
        sys.exit(2)

    if args.injuries:
        try:
            ir = injuries_feed.attach_injuries_to_slate(slate, args.season, args.week)
            summary = ", ".join(f"{n}×{s}" for s, n in sorted(ir.by_status.items()))
            print(f"\nInjuries: {ir.total} designations this week ({summary}).")
            if ir.holds:
                print(f"  Holding {len(ir.holds)} prop(s) on injured players: "
                      f"{', '.join(ir.holds)}")
        except DataUnavailable as exc:
            print(f"\n⚠️  Injury feed unavailable — projecting without it.\n   {exc}")

    real_odds = False
    if args.odds:
        try:
            books = args.books.split(",") if args.books else None
            res = oddsapi.apply_odds_to_slate(slate, books=books)
            real_odds = True
            print(f"\nOdds API: matched {res.matched} props across {res.events_used} games "
                  f"(quota remaining {res.quota.remaining}).")
            if res.unmatched:
                print(f"  No line found for {len(res.unmatched)}: "
                      f"{', '.join(res.unmatched[:6])}{' …' if len(res.unmatched) > 6 else ''}")
        except oddsapi.OddsAPIError as exc:
            print(f"\n⚠️  Odds API unavailable — keeping proxy lines.\n   {exc}")

    model = None
    if args.model:
        from engine.ml.model import MultiplierModel
        model = MultiplierModel.load(args.model)
        print(f"\nUsing learned model: {args.model}")

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    result = run_slate(slate, config, model=model)

    c = result["counts"]
    print(f"\nAnalyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    if not real_odds:
        print("(lines are recent-form proxies — pass --odds for real book edges)\n")
    else:
        print("(edges priced against real sportsbook lines)\n")
    for r in result["recommendations"][:25]:
        flag = "✅" if r["recommended"] else "  "
        print(f"  {flag} {r['grade']:>11}  conf {r['confidence']:>4}  "
              f"edge {r['edge']:+.1%}  {r['headline']}")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
