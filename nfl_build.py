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
    ap.add_argument("--live", action="store_true",
                    help="Overlay live scores/state from ESPN's scoreboard.")
    ap.add_argument("--depth", action="store_true",
                    help="Refine injury knock-on roles from nflverse depth charts.")
    ap.add_argument("--active-odds", action="store_true",
                    help="Only re-price live / soon-starting games (saves API quota).")
    ap.add_argument("--odds", action="store_true",
                    help="Attach real sportsbook lines via The Odds API (needs ODDS_API_KEY).")
    ap.add_argument("--cached-odds", action="store_true",
                    help="Attach the LAST PAID pull's prices from cache — zero "
                         "API spend between budgeted pulls.")
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

    qb_notes = None
    if args.depth:
        try:
            from engine.sources.depthcharts import (load_depth_charts,
                                                    refine_injury_roles,
                                                    qb_dependency)
            rows = load_depth_charts(args.season)
            all_inj = [i for g in slate.games for i in g.injuries]
            dres = refine_injury_roles(all_inj, rows, args.week)
            print(f"\nDepth charts: refined {dres.refined} role(s), "
                  f"demoted {dres.demoted} backup(s).")
            for d in dres.details[:8]:
                print(f"  · {d}")
            # The QB-dependency watch: a new QB1 or a dinged incumbent
            # stamps a warning on that team's pass-catcher props.
            qb_notes = qb_dependency(rows, args.week, all_inj)
            if qb_notes:
                print(f"\nQB watch: {len(qb_notes)} team(s) flagged.")
                for t, n in sorted(qb_notes.items()):
                    print(f"  · {t}: {n}")
        except DataUnavailable as exc:
            print(f"\n⚠️  Depth charts unavailable — keeping report-derived roles.\n   {exc}")

    real_odds = False
    odds_status = {"checked": bool(args.odds or args.cached_odds), "matched": 0,
                   "events": 0, "moneylines": 0, "error": None,
                   "quota_remaining": None, "source": None}
    if args.odds or args.cached_odds:
        try:
            books = args.books.split(",") if args.books else None
            res = oddsapi.apply_odds_to_slate(
                slate, books=books,
                only_active=args.active_odds and not args.cached_odds,
                cache_only=args.cached_odds and not args.odds)
            real_odds = res.matched > 0 or res.events_used > 0
            odds_status.update(matched=res.matched, events=res.events_used,
                               moneylines=res.moneylines,
                               quota_remaining=res.quota.remaining,
                               source="cache" if res.from_cache else "fresh")
            print(f"\nOdds API: matched {res.matched} props across {res.events_used} games "
                  f"(quota remaining {res.quota.remaining}).")
            if res.moneylines:
                print(f"  Moneylines attached to {res.moneylines} game(s).")
            if res.unmatched:
                print(f"  No line found for {len(res.unmatched)}: "
                      f"{', '.join(res.unmatched[:6])}{' …' if len(res.unmatched) > 6 else ''}")
            # Keep the spread and total we just paid for. Both were parsed,
            # attached and priced against, then dropped — which is why the
            # spread/total model has never had a stored close to be graded
            # on. Costs nothing; the numbers are already in memory.
            try:
                from engine import lineledger, db as _hdb
                _hc = _hdb.connect()
                lineledger.record(_hc, "nfl", slate.games)
                _hc.close()
            except Exception:
                pass
        except oddsapi.OddsAPIError as exc:
            odds_status["error"] = str(exc)
            print(f"\n⚠️  Odds API unavailable — keeping proxy lines.\n   {exc}")

        if real_odds:
            from engine.linemoves import load_history, analyze, summary_lines, todays_rows
            moves = analyze(todays_rows(load_history()))
            if moves:
                print("\nLine movement (open → current):")
                for line in summary_lines(moves):
                    print(line)

    if args.live:
        from engine.sources.livescores import attach_live
        n = attach_live(slate)
        live_now = sum(1 for g in slate.games if g.live and g.live.state == "live")
        print(f"\nLive scores: {n} game(s) matched, {live_now} in progress.")

    # Team ratings for the moneyline model, from ingested historical scores.
    try:
        from engine.db import connect
        from engine.teamrates import compute_team_ratings, attach_ratings
        conn = connect()
        ratings = compute_team_ratings(conn, "nfl", seasons=[args.season])
        conn.close()
        nr = attach_ratings(slate.games, ratings)
        priceable = sum(1 for g in slate.games
                        if g.home_ml and g.away_ml and (g.home_rating or g.away_rating))
        if nr:
            print(f"\nTeam ratings: attached to {nr} game(s); {priceable} moneyline(s) priceable.")
        else:
            print("\nTeam ratings: none in the DB yet — run `python3 ingest.py nfl` so the "
                  "moneyline model has team strength to find an edge.")
    except Exception as exc:
        print(f"\n⚠️  Team ratings unavailable — moneyline shows no edge.\n   {exc}")

    model = None
    if args.model:
        from engine.ml.model import MultiplierModel
        model = MultiplierModel.load(args.model)
        print(f"\nUsing learned model: {args.model}")

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    # Measured roles from ingested logs: red-zone usage (the TD model's
    # best predictor, finally read instead of inferred) and snap shares.
    # Missing ingests leave the maps empty and the model exactly as before.
    nfl_usage = None
    try:
        from engine.db import connect as _usage_connect
        from engine.nflusage import build_usage_maps
        nfl_usage = build_usage_maps(_usage_connect())
    except Exception:
        nfl_usage = None

    result = run_slate(slate, config, model=model, nfl_usage=nfl_usage,
                       team_notes=qb_notes)

    # §10 drawdown circuit-breaker: after a 10u peak-to-trough drawdown on
    # the settled journal, every stake is halved until the peak is recovered.
    # Applied before journaling so the ledger records what we'd actually bet.
    try:
        from engine import ledger as _ledger
        dd = _ledger.drawdown_factor(_ledger.connect(), sport="nfl")
        if dd < 1.0:
            for r in result["recommendations"] + result.get("game_bets", []):
                if r.get("recommended") and r.get("stake_units", 0) > 0:
                    r["stake_units"] = round(r["stake_units"] * dd, 2)
            result["staking_note"] = ("Drawdown rule active: stakes halved "
                                      "until the journal recovers its peak")
            print("  ⚠️  Drawdown rule active — all stakes halved (10u+ off peak)")
    except Exception:
        pass

    # Stamp each pick with how the market has moved relative to OUR side.
    # Movement is 15% of the quality grade: with-steam raises it, sharp
    # movement against can reject the pick (see engine/quality.py).
    if real_odds:
        try:
            from engine.linemoves import (load_history, analyze, todays_rows,
                                          annotate_recommendations)
            annotate_recommendations(result["recommendations"],
                                     analyze(todays_rows(load_history())))
        except Exception as exc:
            print(f"⚠️  Line-movement stamps skipped: {exc}")

    c = result["counts"]
    print(f"\nAnalyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    if not real_odds:
        print("(lines are recent-form proxies — pass --odds for real book edges)\n")
    else:
        print("(edges priced against real sportsbook lines)\n")
    for r in result["recommendations"][:25]:
        flag = "✅" if r["recommended"] else "  "
        # A good grade with no tick is confusing unless we say what blocked it.
        held = ""
        if not r["recommended"] and r["grade"] != "Pass" and r.get("warnings"):
            held = f"   ← held: {r['warnings'][0].split('—')[0].strip()}"
        print(f"  {flag} {r['grade']:>11}  conf {r['confidence']:>4}  "
              f"edge {r['edge']:+.1%}  {r['headline']}{held}")

    if args.out:
        import datetime as _dt
        from pathlib import Path
        result["generated_from"] = "live-odds" if real_odds else "live"
        odds_status["at"] = _dt.datetime.now().strftime("%H:%M")
        result["odds_status"] = odds_status
        result["built_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nWrote {args.out}")

    # Learning engine: journal real-priced picks; settle any whose results
    # have been ingested since. Proxy lines are never journaled.
    if real_odds:
        try:
            from engine import ledger
            from engine.db import connect as hist_connect
            lconn = ledger.connect()
            logged = ledger.log_recommendations(lconn, result)
            # Yardage-market flags settle from the weekly stats that
            # maintenance ingests daily in season (Aug–Feb).
            st_logged = ledger.log_stale_flags(lconn, result)
            settled = ledger.settle_from_history(lconn, hist_connect(), sport="nfl")
            ledger.export_json(lconn, "web/data/record.json")
            if logged or st_logged or settled:
                print(f"Journal: {logged} new pick(s) + {st_logged} stale "
                      f"flag(s) logged, {settled} settled — see the Record "
                      f"tab or `python3 ledger.py report`")
        except Exception as exc:
            print(f"⚠️  Bet journal skipped: {exc}")


if __name__ == "__main__":
    main()
