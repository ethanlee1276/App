"""NBA schedule + boxscores from the free, keyless NBA CDN.

Endpoints (cdn.nba.com — the same JSON the league's own site renders):
  * ``staticData/scheduleLeagueV2.json``     → full season schedule
  * ``liveData/boxscore/boxscore_{id}.json`` → per-game player stats
  * ``liveData/playbyplay/playbyplay_{id}.json`` → every action of a game,
    every shot with where it was taken (the shot chart, engine/nba/shots)

Parsers are pure and fixture-tested; fetches degrade with DataUnavailable.
Ingestion stores per-game player logs — minutes (the stat that drives
everything), points, rebounds, assists, threes, plus starter flags via the
games table — keyed by real date like the MLB path.
"""

from __future__ import annotations

import json
import re

from .fetch import fetch_json, DataUnavailable

CDN = "https://cdn.nba.com/static/json"
#: Every box-score stat stored per player-game. Steals, blocks and
#: turnovers since 2026-10-13: stored for the charts and the reads, not
#: priced — no board asks the odds feed for them.
NBA_MARKETS = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

#: The league's own headshot for a boxscore personId. CONSTRUCTED, not
#: taken — the CDN boxscore carries the id and no photo URL, the same
#: shape as MLB's Stats API, and this is the path nba.com's own pages
#: request. A wrong guess degrades to the initials chip the card draws
#: today (the <img> removes itself on error), and `assets.py --probe`
#: carries this pattern so a real network can confirm it.
HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{pid}.png"


def fetch_schedule(ttl: int = 21600) -> dict:
    return fetch_json(f"{CDN}/staticData/scheduleLeagueV2.json",
                      "nba_schedule.json", ttl=ttl)


def fetch_boxscore(game_id: str, ttl: int = 21600) -> dict:
    return fetch_json(f"{CDN}/liveData/boxscore/boxscore_{game_id}.json",
                      f"nba_box_{game_id}.json", ttl=ttl)


#: A final's actions never change: a day's cache is plenty for the
#: nightly that reads it once.
PBP_TTL = 86400


def fetch_playbyplay(game_id: str, ttl: int = PBP_TTL) -> dict:
    """Every action of one game (engine/nba/shots folds its shots)."""
    return fetch_json(f"{CDN}/liveData/playbyplay/playbyplay_{game_id}.json",
                      f"nba_pbp_{game_id}.json", ttl=ttl)


def parse_minutes(pt: str) -> float:
    """NBA CDN minutes come as ISO-ish durations ("PT31M12.00S")."""
    m = re.match(r"PT(\d+)M([\d.]+)S", pt or "")
    if not m:
        return 0.0
    return round(int(m.group(1)) + float(m.group(2)) / 60.0, 2)


def parse_schedule_day(sched: dict, date: str) -> list[dict]:
    """Games on a YYYY-MM-DD date: id, teams, final scores when played.

    Scores carry ONLY when gameStatus is 3 (final). The CDN schedule updates
    scores live, so an in-progress game arrives here with a real partial
    score attached — and everything downstream treats a scored games row as
    proof the game ended, because every other results parser in this repo
    only emits finals (parse_results: "the history DB never learns from a
    partial game"). The old `score or None` guard only caught the PRE-game
    case, where the feed says 0: during a live game the partial score flowed
    into the games table, moneylines and totals graded against it on the
    next settle pass, and — since a scored row is also the finality evidence
    `_team_day_final` looks for — the whole team-day unlocked for prop
    grading while the game was still being played. WNBA imports this parser,
    so the fix covers both leagues at the source.
    """
    out = []
    for day in (sched.get("leagueSchedule", {}) or {}).get("gameDates", []) or []:
        for g in day.get("games", []) or []:
            if (g.get("gameDateEst") or "")[:10] != date:
                continue
            home, away = g.get("homeTeam", {}) or {}, g.get("awayTeam", {}) or {}
            status = g.get("gameStatus", 1)         # 1 sched · 2 live · 3 final
            final = status == 3
            out.append({
                "game_id": g.get("gameId", ""),
                "preseason": is_preseason(g.get("gameId", "")),
                "home": home.get("teamTricode", ""),
                "away": away.get("teamTricode", ""),
                "home_score": (home.get("score") or None) if final else None,
                "away_score": (away.get("score") or None) if final else None,
                "status": status,
                "kickoff": g.get("gameDateTimeUTC", ""),
            })
    return out


def is_preseason(game_id) -> bool:
    """The NBA's own game ids carry the season type in their first three
    digits: 001 preseason, 002 regular season, 004 playoffs, 005 play-in.

    NBA readiness, 2026-09-24. The CDN schedule lists the preseason with
    everything else and nothing here told them apart, so the first two
    weeks of October would have been priced as real games — starters on
    regular-season minutes in games they play half of — and their box
    scores stored as the form a player carries into opening night."""
    return str(game_id or "").startswith("001")


def parse_boxscore(box: dict) -> list[dict]:
    """Per-player rows from a boxscore: minutes, the four prop stats, and
    the starter flag."""
    game = box.get("game", {}) or {}
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = game.get(side, {}) or {}
        opp = game.get("awayTeam" if side == "homeTeam" else "homeTeam", {}) or {}
        for p in team.get("players", []) or []:
            st = p.get("statistics", {}) or {}
            rows.append({
                "player": p.get("name", ""),
                "team": team.get("teamTricode", ""),
                "opponent": opp.get("teamTricode", ""),
                "home": side == "homeTeam",
                "starter": str(p.get("starter", "0")) == "1",
                # Identity, which this parser used to throw away — the
                # exact omission that left NBA the only league with an
                # empty player_assets on 2026-08-18: WNBA's ESPN box
                # scores hand over a photo href, this CDN hands over the
                # id the photo is filed under, and nothing kept it.
                "person_id": str(p.get("personId") or ""),
                "min": parse_minutes(st.get("minutes", "")),
                "pts": float(st.get("points", 0) or 0),
                "reb": float(st.get("reboundsTotal", 0) or 0),
                "ast": float(st.get("assists", 0) or 0),
                "fg3m": float(st.get("threePointersMade", 0) or 0),
                "stl": float(st.get("steals", 0) or 0),
                "blk": float(st.get("blocks", 0) or 0),
                "tov": float(st.get("turnovers", 0) or 0),
            })
    return rows


def log_rows(players: list[dict], date: str, game_id: str) -> list[dict]:
    """player_game_logs rows (one per market) for one game's players. The
    position column carries the starter flag — the minutes engine's gate."""
    # THE SEASON IT STARTED IN (engine.seasons.season_of), the label the
    # ESPN backfill writes and every query reads. This was the calendar
    # year, so from January every game went in under next year's label —
    # outside the board's `season IN recent_seasons(...)` — and a
    # player's form stopped at December (NBA readiness, 2026-09-24).
    from ..seasons import season_of
    season = season_of("nba", date)
    out = []
    for p in players:
        if not p["player"]:
            continue
        for market in NBA_MARKETS:
            if market not in p:
                continue            # a row from before a stat was kept stores what it has
            out.append({
                "sport": "nba", "season": season, "period": date,
                "game_id": f"{p['player']}-{date}", "player": p["player"],
                "team": p["team"], "opponent": p["opponent"],
                "position": "S" if p["starter"] else "B",
                "home": 1 if p["home"] else 0,
                "market": market, "value": p[market],
            })
    return out


#: THE SEASON FILE IS SIX HOURS OLD BY DESIGN, AND A FINAL IS NOT
#: (2026-10-13). `fetch_schedule` caches the whole season for six hours —
#: right for a board that wants tonight's fixtures, wrong for a settle pass
#: asking whether tonight's games are over: a copy read at 7pm says every
#: game is scheduled until 1am, so nothing tipped that night could grade
#: before then. Ethan: "It should not take a day for all bets to settle."
#: When the copy on disk has a game that tipped in the last day and is not
#: final, the settle asks the CDN again, at most this often.
RECENT_TTL = 300
#: How far back a tip-off still counts as "tonight" for that question.
RECENT_HOURS = 24


def owed_finals(games: list, now=None) -> bool:
    """Does this copy of a date hold a game that has tipped (within
    RECENT_HOURS) and is not final yet? Preseason games never count."""
    import datetime as _d
    now = now or _d.datetime.now(_d.timezone.utc)
    for g in games:
        if g.get("preseason") or g.get("status") == 3:
            continue
        try:
            tip = _d.datetime.fromisoformat(str(g.get("kickoff") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if tip.tzinfo is None:
            tip = tip.replace(tzinfo=_d.timezone.utc)
        if now - _d.timedelta(hours=RECENT_HOURS) <= tip <= now:
            return True
    return False


def day_games(date: str) -> list[dict]:
    """The date's games off the season file, re-read fresh when a game
    on it has tipped and the cached copy does not have it final yet."""
    games = parse_schedule_day(fetch_schedule(), date)
    if owed_finals(games):
        games = parse_schedule_day(fetch_schedule(ttl=RECENT_TTL), date)
    return games


def box_is_final(box: dict) -> bool:
    """The box score's own word on whether the game is over. A box with no
    status at all is taken as final — the schedule already said so, and an
    unknown shape must not strand a night."""
    status = ((box or {}).get("game") or {}).get("gameStatus")
    return status is None or status == 3


def ingest_nba_date(conn, date: str) -> dict:
    """Ingest one date: schedule game rows + boxscore player logs."""
    from .. import db
    result = {"games": 0, "player_logs": 0, "skipped": []}
    try:
        games = day_games(date)
    except DataUnavailable as exc:
        result["skipped"].append(f"nba schedule: {exc}")
        return result
    from ..seasons import season_of
    grows, prows, arows = [], [], []
    for g in games:
        if g.get("preseason"):
            continue                # never a result, never a player's form
        grows.append({
            "sport": "nba", "season": season_of("nba", date), "period": date,
            "game_id": f"{g['away']}@{g['home']}", "home": g["home"],
            "away": g["away"], "home_score": g["home_score"],
            "away_score": g["away_score"], "spread": 0.0, "total": None,
            "roof": "dome", "surface": "court", "temp": None, "wind": None,
            "extra": None,
        })
        if g["status"] == 3 and g["game_id"]:
            try:
                box = fetch_boxscore(g["game_id"])
                if not box_is_final(box):
                    # A copy cached before the buzzer: ask once more, and
                    # store nothing from a game the box says is still on.
                    box = fetch_boxscore(g["game_id"], ttl=0)
                if not box_is_final(box):
                    result["skipped"].append(f"nba box {g['game_id']}: not final yet")
                    continue
                players = parse_boxscore(box)
                prows += log_rows(players, date, g["game_id"])
                # Faces ride the same fetch: one row per player who has an
                # id, constructed via HEADSHOT (see its comment for how a
                # wrong pattern degrades). Same capture point the WNBA
                # ingest has used since #89 — NBA just never had one.
                arows += [{"sport": "nba", "player": p["player"],
                           "espn_id": p["person_id"],
                           "headshot": HEADSHOT.format(pid=p["person_id"]),
                           "seen": date}
                          for p in players
                          if p["player"] and p.get("person_id")]
            except DataUnavailable as exc:
                result["skipped"].append(f"nba box {g['game_id']}: {exc}")
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    result["assets"] = db.upsert_player_assets(conn, arows)
    if result["games"] or result["player_logs"]:
        db.log_ingest(conn, "nba", "slate", date,
                      result["games"] + result["player_logs"])
    return result
