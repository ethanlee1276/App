"""WNBA from ESPN's public API — the feed this app already knows works.

The original WNBA source pointed at ``cdn.wnba.com`` on the theory that the
league runs the same stack as the NBA and would therefore publish the same
JSON at the same paths. That was a guess made without a way to verify it,
and on Ethan's machine it returned something that wasn't JSON for every
date in the season.

This module is the answer that does not require a guess. ESPN's site API
already feeds NFL live scores and the entire college football board in
this repo, in exactly this shape, against endpoints that demonstrably
work:

    /apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD
    /apis/site/v2/sports/basketball/wnba/summary?event={id}

The scoreboard gives the day's games and finals; the summary gives the box
score. Both are keyless.

**The box-score parse reads by column NAME, never by position.** ESPN
returns a ``names`` array alongside each athlete's ``stats`` array, and
the order of those columns is not a promise anyone made us. Indexing by
position would work until the day a column moved, and the failure would
be silent — minutes quietly read as rebounds, and a board full of
confident nonsense. Mapping by name costs nothing and cannot drift.
"""

from __future__ import annotations

from .fetch import fetch_json, DataUnavailable

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
SCOREBOARD = BASE + "/scoreboard"
SUMMARY = BASE + "/summary"

# ESPN's box-score column names → our market keys. Anything not listed is
# ignored rather than guessed at.
STAT_MAP = {"MIN": "min", "PTS": "pts", "REB": "reb", "AST": "ast",
            "3PT": "fg3m"}


def _num(raw) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_scoreboard(payload: dict) -> list[dict]:
    """One day's games: ids, teams, finals."""
    out: list[dict] = []
    for ev in payload.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        home = away = None
        for c in comp.get("competitors", []) or []:
            side = {"abbr": ((c.get("team") or {}).get("abbreviation") or "").strip(),
                    "score": _num(c.get("score"))}
            if c.get("homeAway") == "home":
                home = side
            else:
                away = side
        if not home or not away or not home["abbr"] or not away["abbr"]:
            continue
        status = (comp.get("status") or ev.get("status") or {})
        completed = bool((status.get("type") or {}).get("completed"))
        out.append({
            "game_id": str(ev.get("id") or ""),
            "home": home["abbr"], "away": away["abbr"],
            "home_score": home["score"] if completed else None,
            "away_score": away["score"] if completed else None,
            "completed": completed,
            "kickoff": ev.get("date", ""),
        })
    return out


def parse_summary(payload: dict) -> list[dict]:
    """A game summary → per-player stat rows.

    Columns are matched by NAME. ESPN gives a ``names``/``keys`` array per
    team block and an aligned ``stats`` array per athlete; reading by
    position would silently mis-assign every stat the day a column moves.
    """
    rows: list[dict] = []
    box = payload.get("boxscore") or {}
    for team_block in box.get("players", []) or []:
        team = ((team_block.get("team") or {}).get("abbreviation") or "").strip()
        for group in team_block.get("statistics", []) or []:
            names = [str(n).upper() for n in (group.get("names") or [])]
            if not names:
                continue
            for ath in group.get("athletes", []) or []:
                info = ath.get("athlete") or {}
                player = (info.get("displayName") or "").strip()
                if not player:
                    continue
                stats = ath.get("stats") or []
                vals: dict = {}
                for i, col in enumerate(names):
                    if col not in STAT_MAP or i >= len(stats):
                        continue
                    raw = stats[i]
                    if col == "MIN":
                        vals["min"] = _num(raw) or 0.0
                    elif col == "3PT":
                        # "5-11" → makes. Attempts are the denominator and
                        # are not a market we price.
                        made = str(raw).split("-")[0]
                        vals["fg3m"] = _num(made) or 0.0
                    else:
                        v = _num(raw)
                        if v is not None:
                            vals[STAT_MAP[col]] = v
                if not vals:
                    continue
                rows.append({
                    "player": player, "team": team,
                    "position": "S" if ath.get("starter") else "B",
                    "stats": vals,
                })
    return rows


def fetch_scoreboard(date: str, ttl: int = 21600) -> dict:
    day = date.replace("-", "")
    return fetch_json(f"{SCOREBOARD}?dates={day}&limit=60",
                      f"espn_wnba_{day}.json", ttl=ttl)


def fetch_summary(game_id: str, ttl: int = 7 * 24 * 3600) -> dict:
    return fetch_json(f"{SUMMARY}?event={game_id}",
                      f"espn_wnba_box_{game_id}.json", ttl=ttl)


def load_day(date: str, ttl: int = 21600) -> list[dict]:
    return parse_scoreboard(fetch_scoreboard(date, ttl=ttl))


def ingest_day(conn, date: str) -> dict:
    """Store one date's finals and player logs. Mirrors ingest_nba_date."""
    from .. import db

    result: dict = {"games": 0, "player_logs": 0, "skipped": []}
    try:
        games = load_day(date)
    except DataUnavailable as exc:
        result["skipped"].append(f"wnba scoreboard {date}: {exc}")
        return result

    grows, prows = [], []
    for g in games:
        grows.append({
            "sport": "wnba", "season": int(date[:4]), "period": date,
            "game_id": g["game_id"], "home": g["home"], "away": g["away"],
            "home_score": g["home_score"], "away_score": g["away_score"],
            "spread": 0.0, "total": None, "roof": "indoor",
            "surface": "hardwood", "temp": None, "wind": None, "extra": None,
        })
        if not g["completed"]:
            continue                       # nothing to log from an unplayed game
        try:
            summary = fetch_summary(g["game_id"])
        except DataUnavailable as exc:
            result["skipped"].append(f"wnba box {g['game_id']}: {exc}")
            continue
        opp = {g["home"]: g["away"], g["away"]: g["home"]}
        for row in parse_summary(summary):
            for market, value in row["stats"].items():
                prows.append({
                    "sport": "wnba", "season": int(date[:4]), "period": date,
                    "game_id": g["game_id"], "player": row["player"],
                    "team": row["team"], "opponent": opp.get(row["team"], ""),
                    "position": row["position"],
                    "home": 1 if row["team"] == g["home"] else 0,
                    "market": market, "value": value,
                })
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    return result


# --- drop-in shims for the shared basketball build ---------------------------
# nba_build calls ``parse_schedule_day(fetch_schedule(), date)``, a shape
# that assumes a single season-wide schedule file. ESPN is per-day, so
# ``fetch_schedule`` has nothing to hand over and the day fetch happens
# inside ``parse_schedule_day``. The odd-looking signature is deliberate:
# it keeps ONE call site in nba_build for both leagues, and a second code
# path for the WNBA board is exactly how the two would drift apart.
def fetch_schedule(ttl: int = 21600) -> dict:
    return {}


def parse_schedule_day(_schedule: dict, date: str) -> list[dict]:
    """One day's games in the shape the shared build expects."""
    try:
        games = load_day(date)
    except DataUnavailable:
        return []
    return [{"game_id": g["game_id"], "home": g["home"], "away": g["away"],
             "kickoff": g.get("kickoff", ""),
             "home_score": g["home_score"], "away_score": g["away_score"]}
            for g in games]
