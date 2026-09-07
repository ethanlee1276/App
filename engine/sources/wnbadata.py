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

from .fetch import fetch_text, DataUnavailable  # noqa: F401
# Same payload shapes, so the same parsers. Re-exported so callers can
# treat this module as the WNBA equivalent of nbadata without importing
# both.
from .nbadata import (parse_minutes, parse_schedule_day, parse_boxscore,
                      log_rows)  # noqa: F401

CDN = "https://cdn.wnba.com/static/json"
WNBA_MARKETS = ("min", "pts", "reb", "ast", "fg3m")


# Candidate schedule paths. The first was written by analogy with the NBA
# CDN and could not be verified when it was written; on a real machine it
# returned something that was not JSON. They are tried in order and the
# probe below reports what each one actually says, so this stops being a
# guess the moment anyone runs it.
SCHEDULE_PATHS = (
    "/staticData/scheduleLeagueV2.json",
    "/staticData/scheduleLeagueV2_1.json",
    "/liveData/scheduleLeagueV2.json",
)


def fetch_schedule(ttl: int = 21600) -> dict:
    """The season schedule, from whichever CDN path answers with JSON."""
    from .fetch import fetch_json
    errors = []
    for i, path in enumerate(SCHEDULE_PATHS):
        try:
            return fetch_json(f"{CDN}{path}", f"wnba_schedule_{i}.json", ttl=ttl)
        except DataUnavailable as exc:
            errors.append(f"{path}: {exc}")
    raise DataUnavailable(
        "No WNBA CDN path returned JSON. Tried:\n  " + "\n  ".join(errors)
        + "\nThe ESPN feed (engine/sources/wnbaespn.py) is the supported "
          "route — run `python3 ingest.py wnba --probe` to see both.")


def fetch_boxscore(game_id: str, ttl: int = 21600) -> dict:
    from .fetch import fetch_json
    return fetch_json(f"{CDN}/liveData/boxscore/boxscore_{game_id}.json",
                      f"wnba_box_{game_id}.json", ttl=ttl)


def probe(date: str = "2026-07-15") -> list[dict]:
    """What every candidate WNBA endpoint ACTUALLY returns, right now.

    Written because the alternative was another round of me guessing at a
    URL from a sandbox that cannot reach it. One run of this replaces the
    guess with a fact.
    """
    import urllib.request
    from . import wnbaespn

    urls = [(f"CDN {p}", f"{CDN}{p}") for p in SCHEDULE_PATHS]
    urls.append(("ESPN scoreboard",
                 f"{wnbaespn.SCOREBOARD}?dates={date.replace('-', '')}&limit=60"))
    out = []
    for label, url in urls:
        row = {"label": label, "url": url}
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "qellys-book/0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                row["status"] = resp.status
            text = raw.decode("utf-8", errors="replace")
            row["bytes"] = len(text)
            try:
                data = json.loads(text)
                row["json"] = True
                row["top_keys"] = sorted(data)[:6] if isinstance(data, dict) else "list"
            except ValueError:
                row["json"] = False
                row["head"] = text.strip()[:70].replace("\n", " ")
        except Exception as exc:                       # noqa: BLE001
            row["status"] = "error"
            row["error"] = str(exc)[:90]
        out.append(row)
    return out


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
