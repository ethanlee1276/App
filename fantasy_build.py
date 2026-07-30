#!/usr/bin/env python3
"""Build the Fantasy Football page's data from the ingested NFL history.

    python3 fantasy_build.py --out web/data/fantasy.json

Stats come from the local DB (usage rows land during the normal NFL
ingest). Two cache-first, once-a-day fetches keep the page current with
the league rather than with last season: the nflverse schedule (coaching
changes, and next season's lines for game scripts) and Sleeper's public
players feed (current teams, rookies, depth charts). Both fall back to
stale caches, then to nothing — the page labels what it couldn't refresh
instead of guessing.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine import fantasy, fantasy_draft, offseason, preseason
from engine.db import connect
from engine.sources.fetch import DataUnavailable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/fantasy.json")
    args = ap.parse_args()

    conn = connect()
    season = fantasy.latest_season(conn)
    if season is None:
        out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "season": None, "usage": [], "buy_sell": {}, "scripts": [],
               "note": "No NFL usage data ingested yet — run "
                       "`python3 ingest.py nfl` once."}
    else:
        kit = fantasy_draft.build_draft_kit(conn, season)
        try:
            from engine.sources.nflverse import load_schedules
            sched = load_schedules()
        except DataUnavailable:
            sched = []
        # build_offseason stamps the kit's rows with current teams, so it
        # must run before the kit is serialized.
        blob = offseason.load_sleeper_players()
        off = offseason.build_offseason(sched, blob, kit=kit)
        # Waiver-wire pulse: what every Sleeper league grabbed/dumped in
        # the last 24h. None (unreachable) simply omits the section.
        adds = offseason.load_trending("add", blob)
        drops = offseason.load_trending("drop", blob)
        trending = ({"adds": adds or [], "drops": drops or [],
                     "lookback_hours": 24}
                    if adds is not None or drops is not None else None)
        usage = fantasy.usage_board(conn, season)
        buy_sell = fantasy.buy_sell_board(conn, season)
        # Trades must show on EVERY board, not just the draft kit — usage
        # and buy/sell rows come out of the DB wearing last season's teams.
        # The kit was stamped inside build_offseason; these join its moves
        # list so the page's "player moves" section is complete.
        if blob is not None:
            idx = offseason.index_players(blob)
            moves = off.setdefault("moves", [])
            seen = {m["player"] for m in moves}
            for rows in (usage, buy_sell.get("buy_low") or [],
                         buy_sell.get("sell_high") or []):
                offseason.stamp_current_teams(rows, idx, moves=moves, seen=seen)
            moves.sort(key=lambda m: m["player"])
        # The launch-time roster check, visible in the terminal every cycle.
        synced = off.get("rosters_synced_at")
        mv = off.get("moves") or []
        print(f"Roster sync: Sleeper cache "
              + (f"written {synced}" if synced else "UNAVAILABLE — team "
                 "stamps may be stale")
              + f" · {len(mv)} board player(s) on new teams"
              + (": " + ", ".join(f"{m['player']} ({m['from']}→{m['to']})"
                                  for m in mv[:6])
                 + ("…" if len(mv) > 6 else "") if mv else ""))
        # Camp signals: snapshot today's depth charts, diff across the
        # preseason window. The chart is the coaching staff's own verdict
        # — tracked daily, it says who WON a job before Week 1 lines and
        # fantasy drafts have priced it.
        camp = preseason.camp_report(
            blob, datetime.date.today().isoformat())
        if camp and camp.get("days", 0) >= 2:
            ns = camp.get("new_starters") or []
            print(f"Camp watch ({camp['from']} → {camp['to']}): "
                  f"{len(ns)} new starter(s), {len(camp['risers'])} riser(s), "
                  f"{len(camp['fallers'])} faller(s)"
                  + (": " + ", ".join(
                      f"{r['player']} ({r['team']} {r['position']}1"
                      + (", rookie" if r.get("rookie") else "") + ")"
                      for r in ns[:5]) if ns else ""))
        out = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "season": season,
            "camp": camp,
            "usage": usage,
            "rates": fantasy.league_rates(conn, season),
            "buy_sell": buy_sell,
            "scripts": fantasy.game_scripts(conn),
            "draft_kit": kit,
            "offseason": off,
            "trending": trending,
        }
    conn.close()

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    bs = out.get("buy_sell") or {}
    print(f"Fantasy: season {out['season']}, {len(out['usage'])} usage rows, "
          f"{len(bs.get('buy_low', []))} buy-low / {len(bs.get('sell_high', []))} "
          f"sell-high, {len(out['scripts'])} game scripts. Wrote {args.out}")


if __name__ == "__main__":
    main()
