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
    ap.add_argument("--active-odds", action="store_true",
                    help="Only re-price live / soon-starting games (saves API quota).")
    ap.add_argument("--odds", action="store_true",
                    help="Attach real (live during a game) sportsbook lines via The Odds API.")
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

    # Overlay live scores / inning state.
    from engine.mlb.sources.live import attach_live
    live_n = attach_live(slate, args.date)
    if live_n:
        live_now = sum(1 for g in slate.games if g.live and g.live.state == "live")
        print(f"Live scores: {live_n} game(s) matched, {live_now} in progress.")

    real_odds = False
    odds_status = {"checked": bool(args.odds), "matched": 0, "events": 0,
                   "moneylines": 0, "error": None, "quota_remaining": None}
    if args.odds:
        from engine.sources import oddsapi
        try:
            res = oddsapi.apply_odds_to_slate(slate, sport="mlb", only_active=args.active_odds)
            real_odds = True
            odds_status.update(matched=res.matched, events=res.events_used,
                               moneylines=res.moneylines,
                               quota_remaining=res.quota.remaining)
            print(f"Odds API: matched {res.matched} props across {res.events_used} games "
                  f"(quota remaining {res.quota.remaining}).")
            if res.moneylines:
                print(f"  Moneylines attached to {res.moneylines} game(s).")
        except oddsapi.OddsAPIError as exc:
            odds_status["error"] = str(exc)
            print(f"⚠️  Odds API unavailable — keeping proxy lines.\n   {exc}")

    # Team ratings for the moneyline model, from ingested historical scores.
    try:
        from engine.db import connect
        from engine.teamrates import compute_team_ratings, attach_ratings
        season = int(args.date[:4])
        conn = connect()
        ratings = compute_team_ratings(conn, "mlb", seasons=[season])
        conn.close()
        nr = attach_ratings(slate.games, ratings)
        priceable = sum(1 for g in slate.games
                        if g.home_ml and g.away_ml and (g.home_rating or g.away_rating))
        if nr:
            print(f"Team ratings: attached to {nr} game(s); {priceable} moneyline(s) priceable.")
        else:
            print("Team ratings: none in the DB yet — run "
                  "`python3 ingest.py mlb --dates <recent dates>` so the moneyline "
                  "model has team strength to find an edge.")
    except Exception as exc:
        print(f"⚠️  Team ratings unavailable — moneyline shows no edge.\n   {exc}")

    # Home-plate umpire profiles (announced hours before first pitch) — a
    # measured K/run-environment adjustment from our own ingested history.
    try:
        from engine.db import connect as _uconn
        from engine.mlb.umpires import umpire_profiles, attach_umpires
        profs = umpire_profiles(_uconn())
        announced = sum(1 for g in slate.games if g.plate_umpire)
        n_ump = attach_umpires(slate.games, profs)
        if announced:
            print(f"Umpires: {announced} announced, {n_ump} with a non-neutral "
                  f"profile ({len(profs)} umps profiled from history).")
    except Exception as exc:
        print(f"⚠️  Umpire profiles unavailable — neutral zones assumed.\n   {exc}")

    if not slate.props:
        print(f"No props built for {args.date} — lineups may not be posted yet. "
              f"Pitcher props need probable starters; hitter props need confirmed lineups.")

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    result = run_mlb_slate(slate, config)

    c = result["counts"]
    confirmed = sum(1 for g in slate.games if g.lineups_confirmed)
    print(f"\n{args.date}: {len(slate.games)} games ({confirmed} with confirmed lineups)")
    print(f"Analyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    if real_odds:
        print("(edges priced against real sportsbook lines)\n")
    else:
        print("(lines are recent-form proxies — pass --odds for real book edges)\n")
    for r in result["recommendations"][:30]:
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
        import datetime as _dt2
        odds_status["at"] = _dt2.datetime.now().strftime("%H:%M")
        result["odds_status"] = odds_status
        result["built_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nWrote {args.out}")

    # Learning engine: journal today's real-priced picks and settle any open
    # ones whose results have since been ingested. Only real book prices are
    # journaled — a proxy line isn't a bet anyone could place. Never let the
    # journal break a build.
    if real_odds:
        try:
            from engine import ledger
            from engine.db import connect as hist_connect
            lconn = ledger.connect()
            logged = ledger.log_recommendations(lconn, result)
            settled = ledger.settle_from_history(lconn, hist_connect(), sport="mlb")
            if logged or settled:
                print(f"Journal: {logged} new pick(s) logged, {settled} settled "
                      f"— see `python3 ledger.py report`")
        except Exception as exc:
            print(f"⚠️  Bet journal skipped: {exc}")


if __name__ == "__main__":
    main()
