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

from engine import fantasy, fantasy_draft, offseason
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
        off = offseason.build_offseason(sched, offseason.load_sleeper_players(),
                                        kit=kit)
        out = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "season": season,
            "usage": fantasy.usage_board(conn, season),
            "rates": fantasy.league_rates(conn, season),
            "buy_sell": fantasy.buy_sell_board(conn, season),
            "scripts": fantasy.game_scripts(conn),
            "draft_kit": kit,
            "offseason": off,
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
