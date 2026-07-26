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
from engine.sources.fetch import DataUnavailable
from engine.sources.nbadata import fetch_schedule, parse_schedule_day
from engine.nba.pipeline import run_nba_slate


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


def player_history(conn, teams: set[str]) -> dict:
    """{player: {"team", "starter", "minutes": [...], stat: [...]}} newest
    first, last 20 games, for players on tonight's teams."""
    hist: dict = {}
    rows = conn.execute(
        "SELECT player, team, position, period, market, value "
        "FROM player_game_logs WHERE sport='nba' AND team IN (%s) "
        "ORDER BY period DESC" % ",".join("?" * len(teams)),
        tuple(teams)).fetchall()
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
        for stat in ("pts", "reb", "ast", "fg3m"):
            p[stat] = [p["by_week"][w].get(stat, 0.0) for w in weeks]
    return hist


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
    args = ap.parse_args()

    out: dict = {"generated_at": datetime.datetime.now()
                 .isoformat(timespec="seconds"), "date": args.date}

    try:
        games = parse_schedule_day(fetch_schedule(), args.date)
        yesterday = parse_schedule_day(
            fetch_schedule(), (datetime.date.fromisoformat(args.date)
                               - datetime.timedelta(days=1)).isoformat())
    except DataUnavailable as exc:
        out.update(status="unreachable", note=str(exc))
        games, yesterday = [], []

    if not games and "status" not in out:
        out.update(status="offseason",
                   note="No NBA games on this date. The engine (minutes model, "
                        "distributions, humility clamp, approval gate) is built "
                        "and tested — it goes live with the schedule.")

    picks_result = None
    if games:
        played_yday = {t for g in yesterday
                       for t in (g["home"], g["away"])}
        conn = connect()
        teams = {t for g in games for t in (g["home"], g["away"])}
        hist = player_history(conn, teams)

        slate = _Slate([_Game(g["home"], g["away"], g["kickoff"])
                        for g in games], [])
        for player, h in hist.items():
            if len(h["minutes"]) >= 3:
                for stat in ("pts", "reb", "ast", "fg3m"):
                    slate.props.append(_Prop(player, stat))

        odds_note = "no odds requested — engine ran with no bettable prices"
        if args.odds or args.cached_odds:
            from engine.sources import oddsapi
            try:
                res = oddsapi.apply_odds_to_slate(
                    slate, sport="nba",
                    cache_only=args.cached_odds and not args.odds)
                odds_note = (f"matched {res.matched} props across "
                             f"{res.events_used} events"
                             + (" (cached)" if res.from_cache else ""))
            except oddsapi.OddsAPIError as exc:
                odds_note = f"odds unavailable: {exc}"

        spread_by_team: dict = {}
        for g in slate.games:
            if g.spread is not None:
                spread_by_team[g.home] = (float(g.spread), float(g.spread) < 0)
                spread_by_team[g.away] = (-float(g.spread), float(g.spread) > 0)

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
                "rest": ("b2b_home" if h["team"] in played_yday else "1day"),
            })

        picks_result = run_nba_slate(props, meta={
            "games": len(games), "odds": odds_note,
            "teams_on_b2b": sorted(played_yday & teams),
        })
        out.update(status="slate", **picks_result)

        # Journal picks (sport='nba') so the Record page and CLV grade them
        # like every other module. Settles from our own ingested boxscores.
        if picks_result["picks"]:
            try:
                from engine import ledger
                recs = [{"player": p["player"], "market": p["market"],
                         "side": p["side"], "line": p["line"],
                         "book": p["book"], "odds": p["odds"],
                         "projection": p["projection"],
                         "hit_prob": p["p_final"], "edge": p["edge"],
                         "confidence": round(p["p_final"] * 10, 1),
                         "grade": "Play", "stake_units": p["stake_units"],
                         "recommended": True}
                        for p in picks_result["picks"]]
                lconn = ledger.connect()
                n = ledger.log_recommendations(
                    lconn, {"sport": "nba", "date": args.date,
                            "recommendations": recs})
                ledger.settle_from_history(lconn, connect(), sport="nba")
                ledger.export_json(lconn, "web/data/record.json")
                print(f"Journal: {n} NBA pick(s) logged.")
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
