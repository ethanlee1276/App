#!/usr/bin/env python3
"""Build the Fantasy Football page's data from the ingested NFL history.

    python3 fantasy_build.py --out web/data/fantasy.json

Reads only the local DB — usage rows land during the normal NFL ingest, so
this build costs zero network. Offseason: shows the last completed season,
labeled as such; game scripts appear as soon as next season's schedule
carries real spreads and totals.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine import fantasy, fantasy_draft
from engine.db import connect


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
        out = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "season": season,
            "usage": fantasy.usage_board(conn, season),
            "rates": fantasy.league_rates(conn, season),
            "buy_sell": fantasy.buy_sell_board(conn, season),
            "scripts": fantasy.game_scripts(conn),
            "draft_kit": fantasy_draft.build_draft_kit(conn, season),
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
