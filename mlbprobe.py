#!/usr/bin/env python3
"""Why is the MLB board blank and are the standings current? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 mlbprobe.py

Ethan, 2026-09-28: "mlb isn't showing any post season games or anything
like that. The rankings didn't even update." Prints what the site holds
and what the league says, side by side: the board's date, its `upcoming`
stamp and game count; the standings file's season, source, note and
bracket state; the last MLB final ingested; the league's season dates
and the next few days' schedule. Writes nothing.
"""

import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"_error": str(exc)}


def main() -> int:
    today = _dt.date.today().isoformat()
    b = _load(ROOT / "web" / "data" / "mlb_recommendations.json")
    print(f"BOARD  built_at {b.get('built_at')}  date {b.get('date')}  games {len(b.get('games') or [])}  "
          f"status {b.get('status')}  upcoming {b.get('upcoming')}")
    s = _load(ROOT / "web" / "data" / "standings_mlb.json")
    br = s.get("bracket") or {}
    print(f"STANDINGS  season {s.get('season')}  source {s.get('source')}  teams {s.get('team_count')}  "
          f"season_wait {s.get('season_wait')}  bracket started {br.get('started')} rounds {len(br.get('rounds') or [])}")
    if s.get("note"):
        print(f"  note: {s['note'][:200]}")
    for g in (s.get("groups") or [])[:6]:
        top = (g.get("teams") or [{}])[0]
        print(f"  {str(g.get('label') or g.get('conference'))[:22]:22} leader {top.get('team')} {top.get('record')}")
    try:
        c = sqlite3.connect(f"file:{ROOT / 'data' / 'history.db'}?mode=ro", uri=True)
        r = c.execute("SELECT MAX(period), COUNT(*) FROM games WHERE sport='mlb' AND season=? "
                      "AND home_score IS NOT NULL", (int(today[:4]),)).fetchone()
        print(f"INGEST  last MLB final {r[0]}  finals this season {r[1]}")
    except sqlite3.Error as exc:
        print(f"INGEST  unreadable: {exc}")
    try:
        from engine.mlb.sources.mlbstats import season_dates, next_game_day
        print(f"LEAGUE  {season_dates(int(today[:4]))}")
        print(f"LEAGUE  next game day after {today}: {next_game_day(today, 7)}")
    except Exception as exc:                                    # noqa: BLE001
        print(f"LEAGUE  unreachable: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
