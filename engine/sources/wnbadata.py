"""WNBA schedule + boxscores from the free, keyless WNBA CDN.

The WNBA publishes the same JSON shapes as the NBA on its own CDN — the
league's site is built on the same stack — so the parsers here are the
NBA ones, reused rather than rewritten:

  * ``staticData/scheduleLeagueV2.json``     → full season schedule
  * ``liveData/boxscore/boxscore_{id}.json`` → per-game player stats

Only the host and the cache keys differ. Importing the parsers instead of
copying them is deliberate: two copies of a boxscore parser drift, and the
first sign of it would be a WNBA board quietly missing a stat the NBA one
has. If the shapes ever diverge, that is the moment to fork — not before.
"""

from __future__ import annotations

import json

from .fetch import fetch_text
# Same payload shapes, so the same parsers. Re-exported so callers can
# treat this module as the WNBA equivalent of nbadata without importing
# both.
from .nbadata import (parse_minutes, parse_schedule_day, parse_boxscore,
                      log_rows)  # noqa: F401

CDN = "https://cdn.wnba.com/static/json"
WNBA_MARKETS = ("min", "pts", "reb", "ast", "fg3m")


def fetch_schedule(ttl: int = 21600) -> dict:
    return json.loads(fetch_text(f"{CDN}/staticData/scheduleLeagueV2.json",
                                 "wnba_schedule.json", ttl=ttl))


def fetch_boxscore(game_id: str, ttl: int = 21600) -> dict:
    return json.loads(fetch_text(f"{CDN}/liveData/boxscore/boxscore_{game_id}.json",
                                 f"wnba_box_{game_id}.json", ttl=ttl))


def ingest_wnba_date(conn, date: str) -> dict:
    """Store one date's player logs and finals. Mirrors ingest_nba_date."""
    from .. import db
    result = {"games": 0, "player_logs": 0, "skipped": []}
    try:
        sched = fetch_schedule()
    except Exception as exc:                       # noqa: BLE001
        result["skipped"].append(f"wnba schedule: {exc}")
        return result
    games = parse_schedule_day(sched, date)
    grows, prows = [], []
    for g in games:
        grows.append({
            "sport": "wnba", "season": int(date[:4]), "period": date,
            "game_id": g["game_id"], "home": g["home"], "away": g["away"],
            "home_score": g.get("home_score"), "away_score": g.get("away_score"),
            "spread": 0.0, "total": None, "roof": "indoor", "surface": "hardwood",
            "temp": None, "wind": None, "extra": None,
        })
        if g.get("home_score") is None:
            continue                               # not final — nothing to log
        try:
            box = fetch_boxscore(g["game_id"])
        except Exception as exc:                   # noqa: BLE001
            result["skipped"].append(f"wnba box {g['game_id']}: {exc}")
            continue
        rows = log_rows(parse_boxscore(box), date, g["game_id"])
        for r in rows:
            r["sport"] = "wnba"
        prows += rows
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    return result
