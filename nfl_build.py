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


def show_games(season: int, week: int) -> list:
    games = build_games(season, week)
    if not games:
        print(f"No games found for {season} week {week}.")
        return []
    # THE FORECAST, BEFORE ANYTHING READS THE WEATHER. nflverse fills a
    # schedule row's temp and wind from the PLAYED game, so every outdoor
    # game on a forward board arrives blank and takes the engine's
    # mild-day prior — flagged as one since 2026-08-26, and pulled for
    # real here (engine/nflwx.py, the same Open-Meteo join college has
    # used since 2026-08-24). Every game this cannot answer keeps the
    # prior and keeps `measured=False`; nothing is invented, and the
    # whole pass costs the board nothing if the host is unreachable.
    try:
        from engine import nflwx
        n_wx = nflwx.attach(games)
        outdoor = sum(1 for g in games if not g.weather.dome)
        print(f"\nWeather: {n_wx} of {len(games)} game(s) stamped "
              f"({outdoor} outdoor)")
    except Exception as exc:                                  # noqa: BLE001
        print(f"\nWeather: skipped — {type(exc).__name__}: {exc}")
    print(f"\n{len(games)} games — {season} week {week}\n")
    for g in games:
        w = g.weather
        cond = ("dome" if w.dome else
                f"{w.temp_f:.0f}°F, wind {w.wind_mph:.0f}mph"
                if getattr(w, "measured", False) else "not pulled")
        fav = g.home if g.spread < 0 else g.away
        print(f"  {g.away:>3} @ {g.home:<3}  spread {g.spread:+.1f} (fav {fav})  "
              f"total {g.total:.1f}  · {cond}")
    return games


def price_games_only(games, season: int, week: int, config: RuleConfig,
                     cached_odds: bool = False) -> dict:
    """Price the GAME markets on a slate whose player layer does not exist yet.

    Ethan, 2026-08-19: "yes I want the 2nd -9th priced". The window he
    means is Sep 2 → ~Sep 9, between the day `_current_nfl_week()` first
    calls Week 1 current and the day nflverse publishes the season's first
    weekly player stats. The full build exits 2 in that window, so the
    fallback is the only thing writing the board — and it published a bare
    schedule.

    It does not have to. Only the PLAYER layer is missing. Totals, team
    totals and spreads price off team ratings against the schedule's own
    lines, and the ratings come from games already played and ingested
    (last season pooled in while this one is thin — see
    engine.teamrates.ratings_for_season). Moneylines are the one game
    market that needs a book price, so they appear only when a cached odds
    pull has one; without it the market is absent rather than guessed.

    Returns a report dict; the pricing lands on ``games`` in place.
    """
    # Two failure fields, not one. A ratings failure means nothing can be
    # priced; a cached-odds failure means only the moneyline is missing,
    # and the first version reported the second as the first — printing
    # "Game markets not priced" one line above "64 game bet(s)".
    rep = {"rated": 0, "seasons": [], "moneylines": 0, "bets": [],
           "error": None, "odds_error": None}
    try:
        from engine.db import connect
        from engine.teamrates import ratings_for_season, attach_ratings
        conn = connect()
        try:
            ratings, seasons_used = ratings_for_season(conn, "nfl", season)
        finally:
            conn.close()
        rep["rated"] = attach_ratings(games, ratings)
        rep["seasons"] = seasons_used
    except Exception as exc:                                   # noqa: BLE001
        rep["error"] = str(exc)
        return rep

    # Zero API spend: the LAST paid pull's prices, if one is on disk. This
    # is the only way a moneyline can be priced here, and it is also where
    # real spread/total prices come from instead of the -110 default.
    if cached_odds and rep["rated"]:
        try:
            from engine.data_loader import Slate
            shell = Slate(date=f"{season}-W{week:02d}", teams={},
                          games=games, props=[])
            res = oddsapi.apply_odds_to_slate(shell, only_active=False,
                                              cache_only=True)
            rep["moneylines"] = res.moneylines
        except Exception as exc:                               # noqa: BLE001
            rep["odds_error"] = str(exc)

    if rep["rated"]:
        from engine.pipeline import _game_bets
        rep["bets"] = _game_bets(games, config)
        # STAMP THE PROVENANCE ON THE ROW, not just on the page. Without a
        # cached pull these price at the standard −110 against the
        # schedule's own spread and total, and the ledger stores
        # r.get("book", "best") — so an unstamped row would enter the
        # record claiming a shopped book price it never had. CLV work can
        # exclude "schedule" rows; it cannot un-mix them later.
        #
        # It matters most in the case this path was NOT built for. Week 1
        # is safe by the calendar: nflverse publishes weekly stats only
        # after the games are played, so the full build never re-prices a
        # Week 1 slate before kickoff and there is no second row to
        # collide with. A TRANSIENT mid-season failure is different — the
        # fallback's row lands first, and INSERT OR IGNORE means the
        # later real-priced row is the one dropped. The stamp is what
        # makes that visible in the record rather than silent.
        if not rep["moneylines"]:
            for b in rep["bets"]:
                b.setdefault("book", "schedule")
    return rep

def _journal_game_bets(payload: dict) -> None:
    """Journal the fallback's recommended game bets, then settle and export.

    The same call the full build makes. `log_recommendations` walks
    `recommendations` (empty here — there are no props) and then
    `game_bets`, so one call covers it.

    Double-journalling was the objection to pricing here at all, and it is
    answered by the schema rather than by restraint: bets is UNIQUE on
    (sport, date, player, market, category) with INSERT OR IGNORE, and this
    payload's date is the same "<season>-W<week>" key build_slate() stamps.
    When the full build runs later in the week it re-offers these same
    rows and the database ignores them.
    """
    try:
        from engine import ledger
        from engine.db import connect as hist_connect
        payload = dict(payload, sport="nfl")
        lconn = ledger.connect()
        logged = ledger.log_recommendations(lconn, payload)
        settled = ledger.settle_from_history(lconn, hist_connect(), sport="nfl")
        ledger.export_json(lconn, "web/data/record.json")
        if logged or settled:
            print(f"Journal: {logged} new game bet(s) logged, {settled} "
                  f"settled — see the Record tab.")
    except Exception as exc:                                   # noqa: BLE001
        print(f"⚠️  Bet journal skipped: {exc}")

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
    ap.add_argument("--carry", action="store_true",
                    help="top thin logs up from last season, so weeks 1-3 "
                         "have a board at all (see engine/carry.py)")
    args = ap.parse_args()

    games = show_games(args.season, args.week)
    if args.games_only:
        # A SCHEDULE IS WORTH PUBLISHING, AND ITS GAME MARKETS ARE WORTH
        # PRICING.
        #
        # Found by the Phase 3 dress rehearsal, 2026-08-19: the full build
        # exits 2 when nflverse has no weekly player stats yet, which is
        # the normal state of the world until Week 1 has been PLAYED. The
        # launcher runs one build and keeps the old data when it fails, so
        # from Sep 2 (when _current_nfl_week() first calls Week 1 current)
        # until roughly Sep 9, every nightly NFL refresh would fail and
        # the board would carry nothing — through exactly the week the
        # season is arriving. The games and their lines are available that
        # whole time; only the PLAYER layer is missing.
        #
        # The first version of this fallback published the slate and
        # nothing else, on the reasoning that pricing here could
        # double-journal the same slate when the full build later
        # succeeded. That caution was worth raising and turned out to be
        # unnecessary: the ledger's bets table is UNIQUE on
        # (sport, date, player, market, category) and every insert is an
        # INSERT OR IGNORE, and the fallback's date is the same
        # "<season>-W<week>" key build_slate() stamps — so the second
        # write of a row is a no-op at the schema level, not a duplicate.
        #
        # Ethan, 2026-08-19, deciding it: "yes I want the 2nd -9th priced".
        # So the game markets price here, off team ratings against the
        # schedule's own lines. The player layer still does not, because
        # it does not exist yet, and the page says which is which.
        if args.out:
            import datetime as _dt
            from engine import gate
            from engine.pipeline import _game_to_dict
            config = RuleConfig(min_confidence=args.min_confidence,
                                min_edge=args.min_edge)
            rep = price_games_only(games, args.season, args.week, config,
                                   cached_odds=args.cached_odds)
            bets = rep["bets"]
            n_rec = sum(1 for b in bets if b.get("recommended"))
            if rep["error"]:
                print(f"\n⚠️  Game markets not priced — {rep['error']}")
            elif not rep["rated"]:
                print("\nGame markets not priced: no SCORED games for this "
                      "season or the one before it, so there are no team "
                      "ratings to price against.")
            else:
                span = "%d" % rep["seasons"][0] if len(rep["seasons"]) == 1 \
                    else "%d-%d" % (rep["seasons"][0], rep["seasons"][-1])
                print(f"\nGame markets: {len(bets)} priced off {rep['rated']} "
                      f"game(s) of ratings ({span}), {n_rec} recommended.")
                if rep["moneylines"]:
                    print(f"  Moneylines priced on {rep['moneylines']} game(s) "
                          f"from the last cached odds pull.")
                elif rep["odds_error"]:
                    print(f"  No moneylines — the cached odds pull is "
                          f"unreadable: {rep['odds_error']}")
                else:
                    print("  No moneylines — that market needs a book price "
                          "and no cached pull has one.")
            # THE CHART THE GAME BETS OPEN ONTO. Ethan, 2026-08-26:
            # "on nfl im not able to click on the game props and it show
            # me the bar graph and information and shit." He was reading
            # THIS payload — the fallback is what the site publishes
            # every day between the schedule appearing and Week 1 being
            # played — and it shipped without `team_recent`, so all
            # sixty-four game bets opened onto "No recent results for
            # this team yet". The full build has attached it since the
            # chart existed; the fallback was written as a stopgap and
            # never caught up. The data was already ingested and one
            # call away: the same call, with the same guard, so the two
            # paths cannot drift again.
            try:
                from engine.db import connect as _tl_connect
                from engine.teamlogs import recent_games as _recent_games
                _tlc = _tl_connect()
                _team_recent = _recent_games(
                    _tlc, "nfl",
                    {t for g in games for t in (g.home, g.away) if t},
                    before=f"{args.season}-W{args.week:02d}")
                _tlc.close()
            except Exception as exc:                          # noqa: BLE001
                print(f"  ⚠️  team logs skipped: {exc}")
                _team_recent = {}
            payload = {
                "date": f"{args.season}-W{args.week:02d}",
                "built_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "generated_from": "schedule-only",
                "team_recent": _team_recent,
                "games": [_game_to_dict(g) for g in games],
                "recommendations": [], "long_shots": [],
                "longshot_watch": [],
                # SHAPES, NOT JUST EMPTINESS. These two are DICTS on every
                # other board — `market_scan` is {stale, arbs, middles, …}
                # and `parlays` is the screen's own report — and shipping
                # them as empty LISTS here was a lie about which. It cost a
                # real sentence on the live site: renderParlays guards on
                # `!z`, an empty list is truthy, and every reader of the
                # schedule-only NFL board was told "Screened undefined
                # candidate tickets built from undefined eligible legs on
                # tonight's board". `parlays` is dropped outright rather
                # than emptied, because the screen did not run — it needs
                # player props, which is the one layer this build does not
                # have — and the page has an honest empty state for that.
                "market_scan": {},
                "game_bets": bets,
                # Two notes, because two things can be true and the page
                # must not claim the wrong one. With ratings in hand the
                # game markets ARE priced and only the player layer is
                # missing; without them nothing is priced at all, and
                # saying otherwise on an empty board is exactly the kind
                # of small lie the render spec exists to stop.
                "note": (
                    "Game lines are priced — totals, team totals and "
                    "spreads, off team ratings. Player props are not: "
                    "nflverse publishes weekly player stats only after a "
                    "season's first games have been played, so no prop has "
                    "been built yet. They appear on their own once the "
                    "season starts."
                    if bets else
                    "Schedule, lines and weather only — nflverse has not "
                    "published weekly player stats for this season yet, and "
                    "there are no scored games to rate the teams from, so "
                    "nothing is priced. Props and picks appear once the "
                    "first games have been played."),
            }
            gate.publish(payload, args.out)
            print(f"\nWrote {args.out} — {len(games)} game(s), "
                  f"{len(bets)} game bet(s), no player props yet.")
            _journal_game_bets(payload)
        return

    carry_report: dict = {}
    try:
        slate = build_slate(args.season, args.week, carry=args.carry,
                            report=carry_report)
    except DataUnavailable as exc:
        print("\n⚠️  Full projections need weekly player stats.\n")
        print(exc)
        print("\nTip: run with --games-only to use just the live schedule/weather layer.")
        sys.exit(2)

    if carry_report.get("carried_n"):
        n = carry_report["carried_n"]
        moved = sum(1 for e in carry_report["carried"].values() if e.get("reset"))
        print(f"\nCarried {n} projection(s) from {args.season - 1} — the "
              f"current season has too few games yet.")
        if moved:
            print(f"  {moved} of them changed team or head coach in the "
                  f"offseason; flagged on the card, not discarded "
                  f"(see engine/carry.py for why).")

    # THE BOARD MUST RECORD WHETHER §7 ACTUALLY RAN, not just whether it
    # was asked to. Found by the Phase 3 rehearsal, 2026-08-20: building
    # real Week 1 printed "⚠️  Injury feed unavailable — projecting
    # without it", priced all 16 games anyway, and left NOTHING in the
    # payload to say so. `odds_status` has recorded exactly this for the
    # price layer since the beginning; the injury layer had no equivalent,
    # so a prop on a player listed OUT was indistinguishable from a prop
    # on a healthy one.
    #
    # It is not hypothetical for Week 1. nflverse publishes
    # injuries_<season>.csv during the season, so before a season's first
    # games the file is a 404 — verified here, 2026-08-20: 2026 → HTTP
    # 404, 2025 → 6,068 rows including 197 for its own Week 1. The data
    # is not missing in principle, it simply is not published yet, and
    # exactly when it appears is nflverse's call and not ours. So the
    # board says which of the two states it is in rather than guessing.
    injury_status = {"asked": bool(args.injuries), "applied": False,
                     "total": 0, "holds": 0, "by_status": {},
                     "source": "nflverse", "error": None}
    if args.injuries:
        try:
            ir = injuries_feed.attach_injuries_to_slate(slate, args.season, args.week)
            summary = ", ".join(f"{n}×{s}" for s, n in sorted(ir.by_status.items()))
            print(f"\nInjuries: {ir.total} designations this week ({summary}).")
            if ir.holds:
                print(f"  Holding {len(ir.holds)} prop(s) on injured players: "
                      f"{', '.join(ir.holds)}")
            injury_status.update(applied=True, total=ir.total,
                                 holds=len(ir.holds), by_status=dict(ir.by_status))
        except DataUnavailable as exc:
            print(f"\n⚠️  Injury feed unavailable — projecting without it.\n   {exc}")
            injury_status["error"] = str(exc)

    # §5's reset rule: a traded player, a new head coach or a snap-share
    # promotion makes the older games evidence about a job that no longer
    # exists. Truncate to the post-reset sample before anything projects
    # off it — "three games in the real current role beat twelve games in
    # a role that no longer exists".
    reset_report = {}
    try:
        from engine import reset as _reset
        from engine.db import connect as _reset_connect
        _rc = _reset_connect()
        try:
            reset_report = _reset.apply_to_slate(
                slate, _rc, args.season, load_schedules())
        finally:
            _rc.close()
        n_reset, n_held = len(reset_report["reset"]), len(reset_report["held"])
        if n_reset or n_held:
            print(f"\nSample resets: {n_reset} player(s) re-projected from "
                  f"post-change games only, {n_held} flagged stale but too "
                  f"thin to reset.")
            for who, e in list(reset_report["reset"].items())[:6]:
                print(f"  · {who}: {e['detail']} — kept {e['kept']}, "
                      f"dropped {e['dropped']}")
    except Exception as exc:                       # noqa: BLE001
        print(f"\n⚠️  Reset rule skipped — projecting on full samples.\n   {exc}")

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
            if res.scorers_matched:
                print(f"  Anytime-TD quotes attached to {res.scorers_matched} "
                      f"player(s) — the long-shot board prices these.")
                # Journal the WHOLE quoted board — every player, every
                # book, identities and prices only — so the one-sided
                # hold can be measured off settled quotes instead of
                # assumed at 6% forever (engine/holdwatch; Ethan circled
                # that caveat, 2026-08-26). Best-effort: a journal miss
                # must never cost the build.
                try:
                    from engine import db as _hdb, holdwatch
                    _nq = holdwatch.record_slate(
                        _hdb.connect(), slate, sport="nfl",
                        season=args.season, period=f"{int(args.week):03d}")
                    print(f"  Quote journal: {_nq} anytime-TD quotes recorded "
                          f"for the hold measurement.")
                except Exception as _exc:  # noqa: BLE001
                    print(f"  ⚠️  quote journal skipped: {_exc}")
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
        from engine.teamrates import ratings_for_season, attach_ratings
        conn = connect()
        ratings, seasons_used = ratings_for_season(conn, "nfl", args.season)
        conn.close()
        nr = attach_ratings(slate.games, ratings)
        priceable = sum(1 for g in slate.games
                        if g.home_ml and g.away_ml and (g.home_rating or g.away_rating))
        if nr:
            span = ("%d" % seasons_used[0] if len(seasons_used) == 1
                    else "%d-%d" % (seasons_used[0], seasons_used[-1]))
            carried = " (last season pooled in — this one is too thin yet)" \
                if len(seasons_used) > 1 else ""
            # Report the WHOLE game board, not just the moneylines. The
            # first version printed "0 moneyline(s) priceable" and nothing
            # else, on a run that had in fact priced 64 game bets and
            # recommended 13 — because moneylines are the one game market
            # that needs a book price, while totals and spreads price off
            # team ratings against the schedule's own lines. A reader who
            # sees only the zero concludes the board is dead.
            print(f"\nTeam ratings: attached to {nr} game(s) from {span}"
                  f"{carried}.")
            if not priceable:
                print("  Moneylines need book prices and the schedule "
                      "carries none — pass --odds for those.")
            else:
                print(f"  {priceable} moneyline(s) priceable.")
            print("  Totals and spreads do NOT need odds; they price off "
                  "the ratings against the schedule's own lines.")
        else:
            print("\nTeam ratings: no SCORED games for this season or the one "
                  "before it. `python3 ingest.py nfl` fills them once games "
                  "have been played — before that there is nothing to fill.")
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

    # WHO HAS PRODUCTION BUT NO MEASURED USAGE. The two feeds in
    # player_game_logs are joined by name, and when that join fails
    # nothing errors — the player simply carries no red-zone work, no
    # snap share and no xFP, and every model that asks about him answers
    # confidently from nothing. That was true for 32 players a season
    # until a touchdown card turned up missing its explanation.
    if nfl_usage:
        try:
            from engine.nflusage import join_audit
            unmatched = join_audit(_usage_connect())
            if unmatched:
                print(f"  ⚠️  {len(unmatched)} player(s) with real volume have "
                      f"no play-by-play match — they carry NO measured usage:")
                for name, team, touches in unmatched[:5]:
                    print(f"        {name} ({team}), {touches:.0f} touches")
                print("        add them to engine.fantasy.NAME_ALIASES, or "
                      "check the ingest")
        except Exception as exc:                              # noqa: BLE001
            # Bookkeeping must never be the thing that kills a build.
            print(f"  usage join audit skipped: {exc}")
    result = run_slate(slate, config, model=model, nfl_usage=nfl_usage,
                       team_notes=qb_notes)
    # Say on each card what the sample rule did — the reset that was
    # applied, or the stale sample that was too thin to reset.
    if reset_report:
        from engine import reset as _reset
        _reset.decorate(result["recommendations"], reset_report)
        result["sample_resets"] = {
            k: v for k, v in reset_report.items() if k != "index"}

    # …and say when the number came from last season at all. A carried
    # projection that reads like a played one is this feature's whole risk.
    if carry_report.get("carried"):
        from engine import carry as _carry
        _carry.decorate(result["recommendations"], carry_report)
        result["carried"] = {
            p: {"season": e["season"], "games": e["games"],
                "weight": round(e["weight"], 3), "position": e["position"],
                "reset": list(e["reset"]) if e.get("reset") else None}
            for p, e in carry_report["carried"].items()}

    # The last ten results for every club on the card — what a GAME bet
    # charts, the way a player prop charts its game log. Same source we
    # grade our own game bets against.
    try:
        from engine.db import connect as _tl_connect
        from engine.teamlogs import recent_games
        _tlc = _tl_connect()
        result["team_recent"] = recent_games(
            _tlc, "nfl", {t for g in slate.games for t in (g.home, g.away) if t},
            before=result.get("date"))
        _tlc.close()
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ⚠️  team logs skipped: {exc}")

    # §10 drawdown circuit-breaker: after a 10u peak-to-trough drawdown on
    # the settled journal, every stake is halved until the peak is recovered.
    # Applied before journaling so the ledger records what we'd actually bet.
    try:
        from engine import ledger as _ledger
        dd = _ledger.drawdown_factor(_ledger.connect(), sport="nfl")
        if dd < 1.0:
            # One rule for a scale-down, in one place: halve, and drop
            # anything that falls under the floor — the same thing
            # `correlation.apply_exposure_caps` does one step earlier.
            from engine.staking import apply_drawdown as _dd_apply
            _sc, _dr = _dd_apply(
                result["recommendations"] + result.get("game_bets", []), dd)
            result["staking_note"] = ("Drawdown rule active: stakes halved "
                                      "until the journal recovers its peak"
                                      + (f"; {_dr} bet(s) fell under the "
                                         f"minimum and came off the board"
                                         if _dr else ""))
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

    # THE LINE, AS A PICTURE — see the same block in mlb_build.py.
    # lineledger.record has been writing a row per observed minute since it
    # shipped and nothing read it back. No API credit, no extra fetch.
    try:
        from engine import linetape, db as _tdb
        _tc = _tdb.connect()
        _n_tape = linetape.attach_tapes(
            _tc, result["recommendations"] + result.get("game_bets", []), "nfl")
        _tc.close()
        if _n_tape:
            print(f"Line tape: {_n_tape} pick(s) carry their own movement.")
    except Exception as exc:                                   # noqa: BLE001
        print(f"⚠️  Line tape skipped: {exc}")

    c = result["counts"]
    print(f"\nAnalyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    # THE FUNNEL UNDER THE COUNT. engine/census exists for this and says
    # so in its own docstring — "NFL and CFB never emitted one, which is
    # why this module exists ... a quiet Sunday board would have said
    # 'nothing qualified' and offered nothing to check". The pipeline has
    # been publishing gate_census into recommendations.json all along;
    # nothing printed it, so the terminal showed 285 -> 0 and no reason.
    gc = result.get("gate_census") or {}
    if gc:
        print("  Gate census: "
              + " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in gc.items()
                           if v and k != "calibration_markets"))
        if gc.get("calibration_markets"):
            print("  ⚠️  Markets closed by calibration (fit at search boundary): "
                  + ", ".join(gc["calibration_markets"])
                  + " — refits nightly; comes back when the fit lands inside "
                    "the range")
    if not real_odds:
        print("(lines are recent-form proxies — pass --odds for real book edges)\n")
    else:
        print("(edges priced against real sportsbook lines)\n")

    # The game board is a separate product from the props and was invisible
    # in this output: a run that priced 64 game bets and recommended 13
    # printed nothing about any of them, so it read as a dead board.
    gb = result.get("game_bets", [])
    if gb:
        from collections import Counter as _C
        mix = _C(b.get("bet_type") or b.get("market") for b in gb)
        rec = sum(1 for b in gb if b.get("recommended"))
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(mix.items()))
        print(f"Game board: {len(gb)} bet(s) → {rec} recommended  ({kinds})")
        for b in sorted(gb, key=lambda x: (x.get("recommended", False),
                                           x.get("confidence", 0)),
                        reverse=True)[:8]:
            flag = "✅" if b.get("recommended") else "  "
            # A spread carries its pick in `team` and leaves `side` empty,
            # while a total does the reverse. Printing only `side` left
            # every spread reading as a market with no selection.
            what = " ".join(x for x in (b.get("team", ""),
                                        b.get("market", ""),
                                        b.get("side", "")) if x)
            print(f"  {flag} conf {b.get('confidence', 0):4.1f}  "
                  f"edge {b.get('edge', 0):+6.1%}  "
                  f"{what} {b.get('line', '')}")
        print()
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
        # `at` IS THE BUILD'S CLOCK, NOT THE PRICE'S, and beside a price
        # it reads like the price's. On a board that rebuilds every cycle
        # off a paid pull that does NOT — `--cached-odds` keeps the last
        # paid prices on purpose — those are hours apart, and only one of
        # them answers "is this line still live". MLB has stamped the
        # real one since the pacing telemetry went in and the page draws
        # it already (`oddsClockHTML`); NFL never did. Ethan, 2026-09-03:
        # "A lot of the money lines and shit are wrong."
        try:
            from engine import oddsbudget as _ob
            _st = _ob.load()
            odds_status["priced_at"] = (_st.sport_ts("nfl")
                                        or _st.last_refresh_ts or None)
        except Exception:                                 # noqa: BLE001
            pass                   # never cost the board a freshness note
        result["odds_status"] = odds_status
        result["injury_status"] = injury_status
        # The measured market haircut, on the BOARD and not only on the
        # cards it produced — see `engine.gamecal.board_notes`. The NFL
        # spread and moneyline are both measured at no edge, so this is
        # the same Sunday-morning case college football has: a priced
        # card with nothing on it, which must not read as a late feed.
        try:
            from engine.gamecal import board_notes
            result["line_calibration"] = board_notes("nfl")
        except Exception:                                    # noqa: BLE001
            result["line_calibration"] = {}
        result["built_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        # NFL_MODEL §2.3: label the knowledge tier of every reason, so a
        # post-mortem can tell a stale feed from a bad inference. Reads
        # the finished strings and prices nothing.
        from engine.knowledge import stamp as _tier_stamp
        _tier_stamp(result)
        # The live win-probability track, same wiring mlb_build carries
        # (2026-08-18, Ethan: "we should be showing that for ALL live
        # games"). One credit a pull for the whole slate, paid only while
        # a game is actually live; attaching from the on-disk history is
        # free and runs every build.
        try:
            from engine import livelines as _ll
            _live_games = [g for g in result["games"]
                           if (g.get("live") or {}).get("state") == "live"]
            if _live_games and real_odds:
                _n, _note = _ll.pull_and_record("nfl", oddsapi.TEAM_ABBR)
                if _n:
                    print(f"  Live line: {_note}")
            _midnight = _dt.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0).timestamp()
            _tracked = _ll.attach(result["games"], "nfl", since=_midnight)
            if _tracked:
                print(f"  Live line: charting {_tracked} game(s)")
        except Exception as _exc:                             # noqa: BLE001
            print(f"  ⚠️  live line tracking unavailable: {_exc}")
        # The drive sim rides every priced game: one pass stamps the
        # page's diagnostics panel (g["sim"] — shares and shape, never a
        # pick) and journals the same claims pre-kickoff for the
        # Weeks 1-4 reconciliation. drivesim.ENABLED stays False and
        # nothing here prices.
        try:
            from engine import drivesim
            _sim_recs = drivesim.attach(result.get("games"), "nfl")
            drivesim.journal(_sim_recs)
            if _sim_recs:
                print(f"  Drive sim: {len(_sim_recs)} game(s) replayed — "
                      f"page panels stamped, journal appended.")
        except Exception as _exc:                             # noqa: BLE001
            print(f"  ⚠️  drive-sim journal skipped: {_exc}")
        # Team shapes — the game page's two-team radar. Percentile ranks
        # over the last RANKABLE season's finals (in August that is last
        # season, and the panel's label says so). Never fatal: a fresh DB
        # ships no shapes and the page keeps its fallback table.
        try:
            from engine import db as _sdb
            from engine import teamshape as _ts
            _sconn = _sdb.connect()
            # args.SEASON, not the calendar year and not args.year —
            # which never existed. argparse defines `season`, so this line
            # raised AttributeError on every NFL build ever run, the broad
            # except below turned it into one warning line, and the radar
            # has therefore never appeared on the board. Found by the
            # Phase 3 rehearsal, 2026-08-20, building real Week 1.
            #
            # The board's own season is the right argument even though
            # today's calendar year would also work in August. A build of
            # `nfl_build.py 2024 5` must rank 2024/2023 shapes, not this
            # year's — the panel describes the teams on THIS board.
            _season = _ts.latest_shaped_season(_sconn, "nfl", args.season)
            if _season:
                result["team_shapes"] = _ts.team_shapes(_sconn, "nfl", _season)
                result["team_shapes_season"] = _season
                print(f"  Team shapes: {len(result['team_shapes'])} team(s) "
                      f"ranked on season {_season}.")
        except Exception as _exc:                             # noqa: BLE001
            print(f"  ⚠️  team shapes skipped: {_exc}")
        from engine import gate
        gate.publish(result, args.out)
        print(f"\nWrote {args.out}")

    # Learning engine: journal real-priced picks; settle any whose results
    # have been ingested since. Proxy lines are never journaled.
    if real_odds:
        try:
            from engine import ledger
            from engine.db import connect as hist_connect
            lconn = ledger.connect()
            logged = ledger.log_recommendations(lconn, result)
            # The TD long-shot board journals to its own bucket, same as
            # MLB's home runs: measured in public, never in the headline
            # record. `sport` is stamped explicitly — log_longshots
            # defaults to "mlb", and run_slate's payload carries no
            # sport key to correct it.
            ls_logged = ledger.log_longshots(
                lconn, {"sport": "nfl", "date": result.get("date", ""),
                        "long_shots": result.get("long_shots") or []})
            if ls_logged:
                print(f"Long shots: {ls_logged} TD pick(s) journaled.")
            # THE LIKELIHOOD BOARD, to its own bucket. Ethan, 2026-08-30:
            # "which bets do we trust more as now its confusing. also
            # which ones are we recording?" The answer was that we
            # recorded the board built on the signal that measures as
            # noise and recorded nothing from the board built on the two
            # that measure well. Same shape as the long shots above —
            # flat stake, zero dollars, never the headline record — so
            # that in a few weeks the ledger rather than an AUC says
            # which board to trust.
            ml_logged = ledger.log_most_likely(
                lconn, {"sport": "nfl", "date": result.get("date", ""),
                        "most_likely": result.get("most_likely") or []})
            if ml_logged:
                print(f"Most likely: {ml_logged} row(s) journaled.")
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
