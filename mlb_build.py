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
    ap.add_argument("--cached-odds", action="store_true",
                    help="Attach the LAST PAID pull's prices from cache — zero API "
                         "spend. What keeps the board priced between budgeted pulls.")
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
    res = None
    odds_status = {"checked": bool(args.odds or args.cached_odds), "matched": 0,
                   "events": 0, "moneylines": 0, "error": None,
                   "quota_remaining": None, "source": None}
    if args.odds or args.cached_odds:
        from engine.sources import oddsapi
        try:
            res = oddsapi.apply_odds_to_slate(slate, sport="mlb",
                                              only_active=args.active_odds and not args.cached_odds,
                                              cache_only=args.cached_odds and not args.odds)
            real_odds = res.matched > 0 or res.events_used > 0
            odds_status.update(matched=res.matched, events=res.events_used,
                               moneylines=res.moneylines,
                               quota_remaining=res.quota.remaining,
                               source="cache" if res.from_cache else "fresh")
            src_note = " (cached — no API spend)" if res.from_cache else ""
            print(f"Odds API: matched {res.matched} props across {res.events_used} games"
                  f"{src_note} (quota remaining {res.quota.remaining}).")
            if res.moneylines:
                print(f"  Moneylines attached to {res.moneylines} game(s).")
        except oddsapi.OddsAPIError as exc:
            odds_status["error"] = str(exc)
            print(f"⚠️  Odds API unavailable — keeping proxy lines.\n   {exc}")

    # Book-menu props: players the books have priced who aren't on the slate
    # (lineup not posted, nothing to project). The books' menu says they're
    # playing — build their props from real prices + our own ingested logs.
    if res is not None and res.book_only:
        try:
            from engine.db import connect as _bconn
            from engine.mlb.bookmenu import add_book_listed_props
            conn_b = _bconn()
            n_menu = add_book_listed_props(slate, res.book_only, conn_b)
            conn_b.close()
            if n_menu:
                print(f"Book menu: built {n_menu} prop(s) for book-priced "
                      f"players not in a posted lineup yet.")
        except Exception as exc:
            print(f"⚠️  Book-menu props skipped: {exc}")

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

    # Bullpen fatigue: measured relief workload per pen over the last two
    # days (free MLB Stats boxscores) — tired arms give the late innings
    # back to opposing hitters.
    try:
        from engine.mlb.bullpen import attach_fatigue, TIRED_MIN
        from engine.mlb.sources.mlbstats import TEAM_ID_ABBR
        n_fat = attach_fatigue(slate, {ab: tid for tid, ab in TEAM_ID_ABBR.items()})
        if n_fat:
            tired = sum(1 for g in slate.games
                        for s in g.bullpen_fatigue.values() if s >= TIRED_MIN)
            print(f"Bullpen fatigue: workload measured for {n_fat} pens — "
                  f"{tired} clearly overworked ({TIRED_MIN:g}+ weighted relief IP).")
    except Exception as exc:
        print(f"⚠️  Bullpen fatigue unavailable — rested pens assumed.\n   {exc}")

    # Statcast (Baseball Savant): xSLG/xwOBA regression + barrel / hard-hit
    # power profiles — turns "season home-run rate only" into process-based
    # contact quality on props and the HR board.
    try:
        from engine.mlb.sources.savant import attach_statcast
        n_sc = attach_statcast(slate.props, int(args.date[:4]))
        hitters = sum(1 for p in slate.props if p.position != "SP")
        if hitters:
            print(f"Statcast: contact-quality profiles on {n_sc}/{hitters} "
                  f"hitter props.")
    except Exception as exc:
        print(f"⚠️  Statcast unavailable — season rates only.\n   {exc}")

    # Measured platoon splits from our own game logs (each hitter vs the
    # starter hand he actually faced) — replaces the generic +4% handedness
    # bump wherever a real split exists.
    try:
        from engine.db import connect as _pconn
        from engine.mlb.platoon import platoon_splits, attach_platoon
        from engine.mlb.models import TOTAL_BASES, HITS, HOME_RUNS
        conn_p = _pconn()
        splits = {m: platoon_splits(conn_p, m)
                  for m in (TOTAL_BASES, HITS, HOME_RUNS)}
        conn_p.close()
        measured = sum(len(v) for v in splits.values())
        n_pl = attach_platoon(slate, splits)
        if measured:
            print(f"Platoon: measured splits on {n_pl} props "
                  f"({len(splits[TOTAL_BASES])} hitters with 16+ games vs "
                  f"known-hand starters).")
        else:
            print("Platoon: no measured splits yet — starter handedness "
                  "backfills on the next full ingest; generic bump applies.")
    except Exception as exc:
        print(f"⚠️  Platoon splits unavailable — generic bump applies.\n   {exc}")

    # Official season splits (vs LHP / vs RHP) from the MLB Stats API —
    # a few batched, cached-daily requests. The HR model reads the power
    # split; hitters our own logs can't measure get an official SLG-split
    # platoon factor instead of the generic bump.
    try:
        import datetime as _spdt
        from engine.mlb.sources.mlbstats import fetch_batting_splits
        from engine.mlb.platoon import attach_official_splits
        pids = {p.person_id for p in slate.props
                if getattr(p, "person_id", 0) and p.position != "SP"}
        if pids:
            season = _spdt.date.fromisoformat(args.date).year
            n_off = attach_official_splits(
                slate, fetch_batting_splits(pids, season))
            print(f"Official splits: attached to {n_off} props "
                  f"({len(pids)} hitters queried).")
    except Exception as exc:
        print(f"⚠️  Official splits unavailable — flat platoon bump where "
              f"unmeasured.\n   {exc}")

    # Opportunity model: tonight's expected plate appearances (batting slot +
    # run environment) vs each hitter's OWN measured PA average — volume is
    # the most predictable half of any counting prop.
    try:
        from engine.db import connect as _oconn
        from engine.mlb.opportunity import avg_pa_by_player, attach_opportunity
        conn_o = _oconn()
        pa_hist = avg_pa_by_player(conn_o)
        conn_o.close()
        n_pa = attach_opportunity(slate, pa_hist)
        if pa_hist:
            print(f"Opportunity: PA volume measured for {len(pa_hist)} hitters "
                  f"— factor applied to {n_pa} props.")
        else:
            print("Opportunity: no PA history yet — accrues from tonight's "
                  "ingest; static lineup-slot bump applies.")
    except Exception as exc:
        print(f"⚠️  Opportunity model unavailable — static slot bump applies.\n   {exc}")

    # Streak reversion: measured from our own logs, league-wide — what the
    # game AFTER a hot/cold 5-game stretch actually looks like. Never a
    # hunch: if the data shows no reversion, no factor is applied.
    try:
        from engine.db import connect as _sconn
        from engine.mlb.streaks import (measure_reversion, attach_streaks,
                                        STREAK_MARKETS)
        conn_s = _sconn()
        streak_factors = {m: measure_reversion(conn_s, m) for m in STREAK_MARKETS}
        conn_s.close()
        measured_mkts = [m for m, v in streak_factors.items() if v]
        n_st = attach_streaks(slate, streak_factors)
        if measured_mkts:
            print(f"Streaks: reversion measured for {len(measured_mkts)} "
                  f"market(s) from own history; {n_st} prop(s) in a hot/cold "
                  f"stretch tonight.")
        else:
            print("Streaks: not enough ingested history to measure reversion "
                  "yet — no streak factors applied.")
    except Exception as exc:
        print(f"⚠️  Streak analysis unavailable.\n   {exc}")

    if not slate.props:
        print(f"No props built for {args.date} — lineups may not be posted yet. "
              f"Pitcher props need probable starters; hitter props need confirmed lineups.")

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    # IL awareness: one free transactions request marks who's on the
    # injured list (never a pick) and who just came back (form caveat).
    # Unreachable wire → None → the board behaves exactly as before.
    il_map = None
    try:
        import datetime as _ildt
        from engine.mlb.sources.mlbstats import fetch_transactions
        from engine.mlb.transactions import il_status
        _end = args.date
        _start = (_ildt.date.fromisoformat(args.date)
                  - _ildt.timedelta(days=60)).isoformat()
        il_map = il_status(fetch_transactions(_start, _end), args.date)
    except Exception:
        il_map = None

    result = run_mlb_slate(slate, config, il_map=il_map)

    # Team form: hot & cold from our own ingested results, plus the season
    # audit (did hot form predict the next game at all?). Track → measure →
    # only then adjust; the form SAMPLER below journals the hot side at
    # real prices so the Record can answer the question that matters.
    team_form_map = {}
    try:
        from engine.db import connect as hist_connect
        from engine.mlb.teamform import team_form, hot_cold, audit
        hconn = hist_connect()
        team_form_map = team_form(hconn, args.date)
        hot, cold = hot_cold(team_form_map)
        result["team_form"] = {"as_of": args.date, "window_days": 7,
                               "hot": hot, "cold": cold,
                               "audit": audit(hconn)}
        if hot or cold:
            print(f"Team form (7d): {len(hot)} hot / {len(cold)} cold — "
                  + ", ".join(f"{r['team']} {r['w']}-{r['l']}" for r in hot[:3]))
    except Exception as exc:
        print(f"⚠️  team form skipped: {exc}")

    # §10 drawdown circuit-breaker (docs/MLB_MODEL.md): after a 10u
    # peak-to-trough drawdown on the settled journal, every stake is halved
    # until the peak is recovered. Applied before journaling so the ledger
    # records what we'd actually bet.
    try:
        from engine import ledger as _ledger
        dd = _ledger.drawdown_factor(_ledger.connect(), sport="mlb")
        if dd < 1.0:
            for r in result["recommendations"] + result.get("game_bets", []):
                if r.get("recommended") and r.get("stake_units", 0) > 0:
                    r["stake_units"] = round(r["stake_units"] * dd, 2)
            result["staking_note"] = ("Drawdown rule active: stakes halved "
                                      "until the journal recovers its peak")
            print("  ⚠️  Drawdown rule active — all stakes halved (10u+ off peak)")
    except Exception:
        pass

    # Line movement: what the market has done since our first snapshot.
    # Movement is 10% of the quality grade: with-steam raises it, sharp
    # movement against can reject the pick (see engine/quality.py).
    if real_odds:
        try:
            from engine.linemoves import (load_history, analyze, summary_lines,
                                          todays_rows, annotate_recommendations)
            moves = analyze(todays_rows(load_history()))
            n_mv = annotate_recommendations(result["recommendations"], moves)
            if moves:
                print(f"Line movement: {len(moves)} prop(s) re-priced since "
                      f"open; verdict stamped on {n_mv} pick(s).")
                for line in summary_lines(moves, limit=6):
                    print(line)
        except Exception as exc:
            print(f"⚠️  Line-movement stamps skipped: {exc}")

    # HR board funnel — when the Long Shots page is empty, this line says why.
    dg = result.get("longshot_diag") or {}
    if dg:
        print(f"HR board: {dg['hr_props']} HR props → {dg['posted_half']} with a "
              f"0.5 line → {dg['real_priced']} real-priced → {dg['plus_money']} "
              f"plus-money in window → {len(result.get('long_shots') or [])} picks, "
              f"{len(result.get('longshot_watch') or [])} watchlist.")

    c = result["counts"]
    confirmed = sum(1 for g in slate.games if g.lineups_confirmed)
    print(f"\n{args.date}: {len(slate.games)} games ({confirmed} with confirmed lineups)")
    print(f"Analyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    gc = result.get("gate_census") or {}
    if gc:
        # The funnel, so a thin board is a diagnosis instead of a mystery.
        print("  Gate census: "
              + " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in gc.items() if v))
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
            ls_logged = ledger.log_longshots(lconn, result)
            st_logged = ledger.log_stale_flags(lconn, result)
            fm_logged = ledger.log_form_picks(lconn, result, team_form_map)
            settled = ledger.settle_from_history(lconn, hist_connect(), sport="mlb")
            ledger.export_json(lconn, "web/data/record.json")
            if logged or ls_logged or st_logged or fm_logged or settled:
                print(f"Journal: {logged} new pick(s) + {ls_logged} long shot(s) "
                      f"+ {st_logged} stale flag(s) + {fm_logged} form sample(s) "
                      f"logged, {settled} settled — see the Record tab or "
                      f"`python3 ledger.py report`")
        except Exception as exc:
            print(f"⚠️  Bet journal skipped: {exc}")


if __name__ == "__main__":
    main()
