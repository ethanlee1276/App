#!/usr/bin/env python3
"""Build the NBA (Scalpy) slate: minutes engine → distributions → clamp →
gate, against real de-vigged prices.

    python3 nba_build.py 2026-01-15 --cached-odds --out web/data/nba.json

Schedule from the free NBA CDN; player history from our own ingested logs
(minutes first — run `python3 ingest.py nba --from ... --to ...` to build
history); prices from The Odds API (budgeted, same pacer as MLB/NFL).
Offseason → an honest status page, not fake picks.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine.db import connect
from engine.hoops import for_league
from engine.sources.fetch import DataUnavailable
from engine.nba.pipeline import run_nba_slate


# The markets the slate prices. PRA rides along because it is the WNBA
# spec's headline tier-1 market and it is free — player props bill per
# event, not per market — and it is derived from three columns already
# ingested, so it needs no new feed.
SLATE_MARKETS = ("pts", "reb", "ast", "fg3m", "pra")


class _Game:
    def __init__(self, home, away, kickoff):
        self.home, self.away, self.kickoff = home, away, kickoff
        self.live = None
        self.spread = None
        self.home_ml = self.away_ml = 0
        self.total = None


class _Prop:
    def __init__(self, player, market):
        self.player, self.market = player, market
        self.lines = []


class _Slate:
    def __init__(self, games, props):
        self.games, self.props = games, props


def player_history(conn, teams: set[str], sport: str = "nba",
                   seasons: list[int] | None = None) -> dict:
    """{player: {"team", "starter", "minutes": [...], stat: [...]}} newest
    first, last 20 games, for players on tonight's teams.

    ``seasons`` bounds the read. Only 20 games survive the slice no matter
    how many are loaded, so an unbounded query on a backfilled history
    sorts several seasons of rows to throw nearly all of them away — and
    for a player who has not appeared this year it would hand back last
    year's form as if it were current.
    """
    hist: dict = {}
    q = ("SELECT player, team, position, period, market, value "
         "FROM player_game_logs WHERE sport=? AND team IN (%s)"
         % ",".join("?" * len(teams)))
    args: list = [sport, *teams]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    rows = conn.execute(q + " ORDER BY period DESC", args).fetchall()
    for r in rows:
        p = hist.setdefault(r["player"], {"team": r["team"], "starter": None,
                                          "by_week": {}})
        wk = p["by_week"].setdefault(r["period"], {})
        wk[r["market"]] = float(r["value"])
        if p["starter"] is None and r["market"] == "min":
            p["starter"] = r["position"] == "S"
    for p in hist.values():
        weeks = sorted(p["by_week"], reverse=True)[:20]
        p["minutes"] = [p["by_week"][w].get("min", 0.0) for w in weeks]
        p["dates"] = weeks                      # ISO dates, newest first
        for stat in ("pts", "reb", "ast", "fg3m"):
            p[stat] = [p["by_week"][w].get(stat, 0.0) for w in weeks]
        # PRA is the WNBA spec's headline tier-1 market and it needs no new
        # ingest — it is the sum of three columns we already store. Deriving
        # it here rather than fetching it also guarantees the history and
        # the line refer to the same three numbers.
        p["pra"] = [round(p["pts"][i] + p["reb"][i] + p["ast"][i], 1)
                    for i in range(len(weeks))]
    return hist


def schedule_density(schedule_days: dict, team: str, date: str) -> dict:
    """§6 — how compressed this team's last week has been.

    A ~44-game season inside ~4.5 months makes the WNBA schedule denser
    than the NBA's, and density is the part that survived charter flights:
    raw travel matters less now, games-per-days still matters.
    """
    import datetime as _d
    try:
        d0 = _d.date.fromisoformat(date)
    except ValueError:
        return {"rest": "1day", "games_in_4": 0, "games_in_6": 0}
    played = set()
    for offset in range(1, 7):
        day = (d0 - _d.timedelta(days=offset)).isoformat()
        for g in schedule_days.get(day, []):
            if team in (g.get("home"), g.get("away")):
                played.add(offset)
    in_4 = sum(1 for o in played if o <= 3)
    in_6 = sum(1 for o in played if o <= 5)
    if 1 in played:
        rest = "3in4" if in_4 >= 2 else "b2b_home"
    elif in_6 >= 3:
        rest = "4in6_road"
    elif not played:
        rest = "2plus"
    else:
        rest = "1day"
    return {"rest": rest, "games_in_4": in_4 + 1, "games_in_6": in_6 + 1}


def schedule_fit(density: dict) -> float:
    """0-1 for the §8 grade: a rested team is a clean spot, a team on its
    third game in four nights is not."""
    return {"2plus": 1.0, "1day": 0.85, "b2b_home": 0.55,
            "3in4": 0.4, "4in6_road": 0.35}.get(density.get("rest"), 0.7)


def defense_ratings(conn, sport: str) -> dict:
    """{team: points allowed per game} — the only matchup read the ingested
    data actually supports.

    The spec asks for points allowed PER POSSESSION and is right that
    per-game is pace-polluted. We do not ingest possessions, so this is
    labelled as what it is and scored as a directional input rather than
    the headline — which is also what §6 says to do with small-sample
    defensive splits.
    """
    rows = conn.execute(
        "SELECT home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL", (sport,)).fetchall()
    agg: dict = {}
    for r in rows:
        agg.setdefault(r["home"], [0.0, 0]);  agg[r["home"]][0] += float(r["away_score"]); agg[r["home"]][1] += 1
        agg.setdefault(r["away"], [0.0, 0]);  agg[r["away"]][0] += float(r["home_score"]); agg[r["away"]][1] += 1
    return {t: round(pa / n, 2) for t, (pa, n) in agg.items() if n >= 5}


def matchup_fit(defense: dict, opponent: str) -> float:
    """0-1: is this a defence worth attacking? Half when we can't tell."""
    if not defense or opponent not in defense:
        return 0.5
    vals = sorted(defense.values())
    rank = sum(1 for v in vals if v < defense[opponent]) / max(1, len(vals) - 1)
    # Leakier defence (higher points allowed) = better spot for an Over.
    return round(0.35 + 0.5 * rank, 3)


def best_two_way(lines) -> tuple | None:
    """Most-quoted line value, best Over and best Under across books."""
    by_line: dict = {}
    for ln in lines:
        if ln.over_odds and ln.under_odds:
            by_line.setdefault(ln.line, []).append(ln)
    if not by_line:
        return None
    line, quotes = max(by_line.items(), key=lambda kv: len(kv[1]))
    over = max(quotes, key=lambda l: l.over_odds)
    under = max(quotes, key=lambda l: l.under_odds)
    return line, over.over_odds, under.under_odds, over.book


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--out", default="web/data/nba.json")
    # One build, two leagues. The WNBA runs the same Scalpy pipeline on the
    # same JSON shapes from its own CDN; what differs is the tuning (a
    # 40-minute game) and the fact that its tuning has never been fitted to
    # WNBA results — see engine/hoops.py.
    ap.add_argument("--league", choices=["nba", "wnba"], default="nba")
    args = ap.parse_args()
    tune = for_league(args.league)
    # Swap in whatever this league's OWN results can measure. The WNBA
    # shipped inheriting the NBA's margin SD and stat spreads because
    # there was no WNBA sample to fit them against; there is one now, and
    # an inherited number that could be measured is just a wrong number
    # with a good excuse. Anything still unmeasurable keeps the inherited
    # value and says so — this never flips `calibrated`, because fitting
    # constants and earning the right to bet are different claims.
    try:
        from engine.db import connect as _fconn
        from engine.hoops_fit import fitted_tuning, describe
        _fc = _fconn()
        try:
            tune, _fit_report = fitted_tuning(_fc, args.league)
        finally:
            _fc.close()
        if _fit_report["fitted"]:
            print(describe(_fit_report))
    except Exception as exc:  # noqa: BLE001 — a failed fit must not stop a build
        print(f"⚠️  Tuning fit unavailable — using inherited numbers.\n   {exc}")
    if args.league == "wnba":
        # ESPN, not the WNBA CDN. The CDN path was written by analogy with
        # the NBA's and never returned JSON on a real machine; this is the
        # endpoint family that already carries NFL scores and the whole
        # college football board here.
        from engine.sources.wnbaespn import fetch_schedule, parse_schedule_day
    else:
        from engine.sources.nbadata import fetch_schedule, parse_schedule_day

    out: dict = {"generated_at": datetime.datetime.now()
                 .isoformat(timespec="seconds"), "date": args.date,
                 "sport": args.league,
                 "generated_from": f"live-{args.league}",
                 "probation": tune.probation,
                 "tuning": {"calibrated": tune.calibrated,
                            "inherited_from": tune.inherited_from,
                            "note": tune.note},
                 "recommendations": [], "game_bets": [], "long_shots": [],
                 "longshot_watch": [],
                 "market_scan": {"stale": [], "arbs": [], "middles": [],
                                 "low_holds": [], "longshots": []},
                 "counts": {"props_analyzed": 0, "recommended": 0}}

    try:
        games = parse_schedule_day(fetch_schedule(), args.date)
        yesterday = parse_schedule_day(
            fetch_schedule(), (datetime.date.fromisoformat(args.date)
                               - datetime.timedelta(days=1)).isoformat())
    except DataUnavailable as exc:
        out.update(status="unreachable", note=str(exc))
        games, yesterday = [], []

    # The slate's games ride in the JSON like every other board's: it's how
    # the launcher's pacer knows the slate is live, what a refresh costs,
    # and when the pre-game window opens (kickoffs are UTC ISO stamps).
    out["games"] = [{"home": g["home"], "away": g["away"], "date": args.date,
                     "kickoff": g.get("kickoff", "")} for g in games]

    if not games and "status" not in out:
        out.update(status="offseason",
                   note=f"No {tune.name} games on this date. The engine "
                        "(minutes model, "
                        "distributions, humility clamp, approval gate) is built "
                        "and tested — it goes live with the schedule.")

    picks_result = None
    if games:
        played_yday = {t for g in yesterday
                       for t in (g["home"], g["away"])}
        # §6 schedule density needs a week of schedule, not just yesterday:
        # "three games in four nights" and "four in six" are the reads that
        # survived charter flights, and one day of lookback cannot see them.
        sched_days: dict = {}
        try:
            _sched = fetch_schedule()
            for _off in range(1, 7):
                _day = (datetime.date.fromisoformat(args.date)
                        - datetime.timedelta(days=_off)).isoformat()
                sched_days[_day] = parse_schedule_day(_sched, _day)
        except DataUnavailable:
            sched_days = {}
        conn = connect()
        teams = {t for g in games for t in (g["home"], g["away"])}
        # This season and last: early in a year a player's most recent 20
        # games run back into the previous season, so one is too few — and
        # six is a different player.
        from engine.seasons import recent_seasons
        hist = player_history(conn, teams, sport=args.league,
                              seasons=recent_seasons(args.league, args.date))

        slate = _Slate([_Game(g["home"], g["away"], g["kickoff"])
                        for g in games], [])
        for player, h in hist.items():
            if len(h["minutes"]) >= 3:
                for stat in SLATE_MARKETS:
                    slate.props.append(_Prop(player, stat))

        # Every prop on this board is projected from stored game logs, so an
        # empty history produces an empty board that looks exactly like a
        # quiet night. It is not the same thing at all, and the WNBA hit it:
        # games on the schedule, a live season, and zero props, because the
        # league had never been ingested. Say which of the two it is — here
        # in the terminal, and on the page via `history_gap` below.
        if games and not slate.props:
            out["history_gap"] = {
                "teams": sorted(teams),
                "players_found": len(hist),
                "seasons": recent_seasons(args.league, args.date),
                "fix": f"python3 ingest.py {args.league} --seasons 2021-2026",
            }
            print(f"\n⚠️  {len(games)} {args.league.upper()} game(s) on the "
                  f"schedule and NO props to build.")
            print(f"    Props come from stored player logs, and this database "
                  f"has {len(hist)} player(s) with any history for tonight's "
                  f"teams (a prop needs 3+ games).")
            print(f"    Fix: python3 ingest.py {args.league} "
                  f"--seasons 2021-2026")

        odds_note = "no odds requested — engine ran with no bettable prices"
        if args.odds or args.cached_odds:
            from engine.sources import oddsapi
            try:
                res = oddsapi.apply_odds_to_slate(
                    slate, sport=args.league,
                    cache_only=args.cached_odds and not args.odds)
                odds_note = (f"matched {res.matched} props across "
                             f"{res.events_used} events"
                             + (" (cached)" if res.from_cache else ""))
            except oddsapi.OddsAPIError as exc:
                odds_note = f"odds unavailable: {exc}"

        # Stale-line scan across every book's quotes — the sampler signal
        # MLB and NFL already journal. It must run HERE: the pipeline only
        # ever sees the best two-way quote, and the scanner needs the field.
        try:
            from engine.marketscan import stale_quotes
            from engine.nba.pipeline import MARKET_LABELS as _ML
            started_teams: set = set()
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            for g in games:
                k = (g.get("kickoff") or "").replace("Z", "+00:00")
                try:
                    if datetime.datetime.fromisoformat(k) <= now_utc:
                        started_teams |= {g["home"], g["away"]}
                except ValueError:
                    pass
            scan_rows = [{
                "player": pr.player, "market": pr.market,
                "market_label": _ML.get(pr.market, pr.market),
                "game_date": args.date, "live": False,
                "warnings": (["Game already started"]
                             if hist.get(pr.player, {}).get("team")
                             in started_teams else []),
                "all_lines": [{"book": ln.book, "line": ln.line,
                               "over_odds": ln.over_odds,
                               "under_odds": ln.under_odds}
                              for ln in pr.lines],
            } for pr in slate.props if pr.lines]
            out["market_scan"] = {"stale": stale_quotes(scan_rows)}
        except Exception:
            out["market_scan"] = {"stale": []}

        spread_by_team: dict = {}
        for g in slate.games:
            if g.spread is not None:
                spread_by_team[g.home] = (float(g.spread), float(g.spread) < 0)
                spread_by_team[g.away] = (-float(g.spread), float(g.spread) > 0)

        defense = defense_ratings(conn, args.league)
        density = {t: schedule_density(sched_days, t, args.date) for t in teams}
        # §8 freshness: how recently the price we would bet was actually
        # fetched. There is no availability feed for either league, so this
        # tops out below 1.0 on purpose — and with it the grade, which is
        # why half-Kelly (A+, 90) stays out of reach until one exists.
        fresh = 0.9 if (args.odds and "cached" not in odds_note) else 0.5
        if "unavailable" in odds_note:
            fresh = 0.2

        props = []
        for prop in slate.props:
            two = best_two_way(prop.lines)
            h = hist.get(prop.player)
            if not two or not h:
                continue
            line, over_odds, under_odds, book = two
            spread, fav = spread_by_team.get(h["team"], (0.0, False))
            props.append({
                "player": prop.player, "team": h["team"],
                "opponent": next((g["away"] if g["home"] == h["team"]
                                  else g["home"] for g in games
                                  if h["team"] in (g["home"], g["away"])), ""),
                "market": prop.market, "line": line,
                "over_odds": over_odds, "under_odds": under_odds,
                "book": book, "minutes": h["minutes"],
                "values": h[prop.market], "is_starter": bool(h["starter"]),
                "spread": spread, "is_favorite": fav,
                "rest": density.get(h["team"], {}).get(
                    "rest", "b2b_home" if h["team"] in played_yday else "1day"),
                "density": density.get(h["team"], {}),
                "freshness": fresh,
                "schedule_fit": schedule_fit(density.get(h["team"], {})),
                "matchup_fit": matchup_fit(defense, next(
                    (g["away"] if g["home"] == h["team"] else g["home"]
                     for g in games if h["team"] in (g["home"], g["away"])), "")),
                # No per-prop line-movement feed exists for either league;
                # scoring this neutral is the honest answer, and it is
                # listed as parked rather than quietly assumed favourable.
                "movement_fit": 0.5,
            })

        picks_result = run_nba_slate(props, tune=tune, meta={
            "games": len(games), "odds": odds_note,
            "teams_on_b2b": sorted(played_yday & teams),
        })
        out.update(status="slate", **picks_result)

        # Shared-schema layer: the same slate shape NFL/MLB emit, so the
        # seven shared pages can render NBA. Scalpy's own keys stay put.
        try:
            from engine.nba.pipeline import shared_recommendations
            lines_map = {}
            for pr in slate.props:
                if pr.lines:
                    lines_map[(pr.player, pr.market)] = [
                        {"book": ln.book, "line": ln.line,
                         "over_odds": ln.over_odds, "under_odds": ln.under_odds}
                        for ln in pr.lines]
            dates_map = {name: h.get("dates", []) for name, h in hist.items()}
            recs = shared_recommendations(props, lines_map, dates_map,
                                          tune=tune)
            out["recommendations"] = recs
            out["counts"] = {**picks_result["counts"],
                             "props_analyzed": len(recs),
                             "recommended": sum(1 for r in recs
                                                if r["recommended"])}
            from engine.marketscan import scan_recommendations
            ms = scan_recommendations(recs)
            ms["stale"] = (out.get("market_scan") or {}).get("stale", [])
            out["market_scan"] = ms
            # Odds attach set spread/total on the slate games after the
            # games list was written — carry them across for game cards.
            by_pair = {(g.home, g.away): g for g in slate.games}
            for gd in out.get("games", []):
                g = by_pair.get((gd["home"], gd["away"]))
                if g is not None:
                    gd["spread"] = g.spread
                    gd["total"] = g.total
        except Exception as exc:
            print(f"⚠️  shared-schema layer skipped: {exc}")

        # Journal picks + stale flags (sport='nba') so the Record page and
        # the sampler grade them like every other module. Settles from our
        # own ingested boxscores — flags journal even on a no-pick night.
        try:
            from engine import ledger
            lconn = ledger.connect()
            n = 0
            if picks_result["picks"]:
                recs = [{"player": p["player"], "market": p["market"],
                         "side": p["side"], "line": p["line"],
                         "book": p["book"], "odds": p["odds"],
                         "projection": p["projection"],
                         "hit_prob": p["p_final"], "edge": p["edge"],
                         "confidence": round(p["p_final"] * 10, 1),
                         "grade": "Play", "stake_units": p["stake_units"],
                         # The assumption the whole bet rests on (§11.8),
                         # journaled so the loss review can separate a
                         # rotation miss from a shooting night.
                         "proj_minutes": p.get("proj_minutes"),
                         "recommended": True}
                        for p in picks_result["picks"]]
                # Same drawdown circuit-breaker as NFL/MLB: 10u off the
                # journal's peak halves every stake until recovery.
                try:
                    dd = ledger.drawdown_factor(lconn, sport=args.league)
                    if dd < 1.0:
                        for p in recs:
                            p["stake_units"] = round(p["stake_units"] * dd, 2)
                        print("  ⚠️  Drawdown rule active — NBA stakes halved")
                except Exception:
                    pass
                n = ledger.log_recommendations(
                    lconn, {"sport": "nba", "date": args.date,
                            "recommendations": recs})
            st = ledger.log_stale_flags(
                lconn, {"sport": "nba", "date": args.date,
                        "market_scan": out.get("market_scan") or {}})
            settled = ledger.settle_from_history(lconn, connect(), sport=args.league)
            if n or st or settled:
                ledger.export_json(lconn, "web/data/record.json")
                print(f"Journal: {n} NBA pick(s) + {st} stale flag(s) "
                      f"logged, {settled} settled.")
        except Exception as exc:
            print(f"⚠️  NBA journal skipped: {exc}")
        conn.close()

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    if picks_result:
        c = picks_result["counts"]
        print(f"NBA {args.date}: {c['props_analyzed']} props → "
              f"{c['picks']} pick(s), {c['near_misses']} near-miss(es). "
              f"Wrote {args.out}")
        if picks_result["no_qualifying"]:
            print("No qualifying plays at current lines — correct output, "
                  "not a failure.")
    else:
        print(f"NBA {args.date}: {out['status']}. Wrote {args.out}")


if __name__ == "__main__":
    main()
