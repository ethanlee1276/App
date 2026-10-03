"""NHL schedule, finals and box scores from the league's own free API.

Ethan, 2026-10-03: "We want to get at least three years worth of NHL data
on the website ... every single feature we have for NFL and college
football and MLB for NHL as well."

Endpoints (api-web.nhle.com, keyless — the JSON nhl.com itself renders):
  * ``/v1/score/{date}``                 → that day's games, state and score
  * ``/v1/gamecenter/{id}/boxscore``     → every skater's and goalie's line
  * ``/v1/player/{id}/landing``          → a player's full name and headshot

THE NAME, LOOKED UP ONCE. The box score names a skater "C. McDavid"; every
sportsbook names him "Connor McDavid", and the odds join is by name. So the
full name comes from the player's own page, once per player, and is kept in
``player_assets`` (``espn_id`` carries the league's id — the column every
sport files its own id under) so a backfill asks for each player once, not
once per game.

WHAT IS STORED, per game, in ``player_game_logs`` (sport ``nhl``, keyed by
the real date like the other daily sports):
  skaters  goals, assists, points, sog (shots on goal), blocks, hits, ppg
           (power-play goals), toi (minutes), anytime_goal (1 if he scored)
  goalies  saves, shots_against, goals_against, toi, started (1/0)
and a ``games`` row per game with the final score (finals only — a live
score never lands here; see ``FINAL``). Preseason (game type 1) and the
All-Star game are never stored; regular season (2) and playoffs (3) are.

Parsers are pure and fixture-tested; fetches degrade with DataUnavailable.
This sandbox cannot reach the API, so ``probe`` exists for the box: it
fetches one of each and reports the shape, before a backfill is trusted.
"""
from __future__ import annotations

import json

from .fetch import fetch_json, DataUnavailable

API = "https://api-web.nhle.com/v1"
#: Game types kept: regular season and playoffs. 1 is preseason, 4 the
#: All-Star game — neither is anyone's form.
KEEP_TYPES = (2, 3)
#: States a game is over in. "OFF" is the API's settled final.
FINAL = ("OFF", "FINAL")
SKATER_MARKETS = ("goals", "assists", "points", "sog", "blocks", "hits", "ppg", "toi", "anytime_goal")
GOALIE_MARKETS = ("saves", "shots_against", "goals_against", "toi", "started")


def fetch_score(date: str, ttl: int = 1800) -> dict:
    return fetch_json(f"{API}/score/{date}", f"nhl_score_{date}.json", ttl=ttl)


def fetch_boxscore(game_id, ttl: int = 30 * 86400) -> dict:
    return fetch_json(f"{API}/gamecenter/{game_id}/boxscore", f"nhl_box_{game_id}.json", ttl=ttl)


def fetch_player(pid, ttl: int = 90 * 86400) -> dict:
    return fetch_json(f"{API}/player/{pid}/landing", f"nhl_player_{pid}.json", ttl=ttl)


def fetch_roster(team: str, ttl: int = 6 * 3600) -> dict:
    return fetch_json(f"{API}/roster/{team}/current", f"nhl_roster_{team}.json", ttl=ttl)


#: Every club, by the feed's own abbreviation — the roster pull's walk list.
TEAMS = ("ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA",
         "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
         "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH")
#: Where the day's rosters are kept for the board (nhl_build reads it to put
#: a traded player on his new team before he has played a game for it).
ROSTER_FILE = "nhl_rosters.json"


def _txt(v) -> str:
    """The API wraps names as {"default": "..."}; take the text either way."""
    if isinstance(v, dict):
        return str(v.get("default") or "")
    return str(v or "")


def parse_toi(t) -> float:
    """'18:42' → 18.7 minutes."""
    try:
        m, s = str(t or "").split(":")
        return round(int(m) + int(s) / 60.0, 2)
    except ValueError:
        return 0.0


def parse_score_day(payload: dict) -> list[dict]:
    """The day's games: id, type, state, teams, start, and the final score
    only when the game is over (a live score is never a result)."""
    out = []
    for g in (payload or {}).get("games") or []:
        state = str(g.get("gameState") or "")
        home, away = g.get("homeTeam") or {}, g.get("awayTeam") or {}
        final = state in FINAL
        out.append({
            "game_id": str(g.get("id") or ""),
            "type": int(g.get("gameType") or 0),
            "state": state,
            "final": final,
            "start": str(g.get("startTimeUTC") or ""),
            "home": str(home.get("abbrev") or ""), "away": str(away.get("abbrev") or ""),
            "home_name": _txt(home.get("name")), "away_name": _txt(away.get("name")),
            "home_score": float(home["score"]) if final and home.get("score") is not None else None,
            "away_score": float(away["score"]) if final and away.get("score") is not None else None,
            "home_sog": home.get("sog"), "away_sog": away.get("sog"),
            "ended_in": str(((g.get("periodDescriptor") or {}).get("periodType")) or
                            ((g.get("gameOutcome") or {}).get("lastPeriodType")) or ""),
            # THE RUNNING SCORE, for the live card only — under its own
            # names so settlement can never read a second-period score.
            "live": state in ("LIVE", "CRIT"),
            "live_home_score": home.get("score"), "live_away_score": away.get("score"),
            "clock": _clock(g) if state in ("LIVE", "CRIT") else "",
        })
    return out


def _clock(g: dict) -> str:
    """"P2 12:34", "OT 3:10" or "2nd INT" off the score feed."""
    pd = g.get("periodDescriptor") or {}
    num, kind = pd.get("number"), str(pd.get("periodType") or "")
    clock = g.get("clock") or {}
    label = kind if kind in ("OT", "SO") else (f"P{num}" if num else "")
    if clock.get("inIntermission"):
        return f"{label} INT".strip()
    return f"{label} {clock.get('timeRemaining') or ''}".strip()


def _saves(g: dict) -> tuple[float, float]:
    """(saves, shots against): the newer integer fields, or the older
    'saveShotsAgainst' string ("27/29")."""
    if g.get("saves") is not None and g.get("shotsAgainst") is not None:
        return float(g["saves"]), float(g["shotsAgainst"])
    ssa = str(g.get("saveShotsAgainst") or "")
    if "/" in ssa:
        a, b = ssa.split("/", 1)
        try:
            return float(a), float(b)
        except ValueError:
            pass
    return 0.0, 0.0


def parse_boxscore(box: dict) -> list[dict]:
    """One row per player who dressed: id, team, opponent, home, position,
    and the stat line (skater or goalie)."""
    box = box or {}
    teams = {"homeTeam": box.get("homeTeam") or {}, "awayTeam": box.get("awayTeam") or {}}
    stats = box.get("playerByGameStats") or {}
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = str(teams[side].get("abbrev") or "")
        opp = str(teams["awayTeam" if side == "homeTeam" else "homeTeam"].get("abbrev") or "")
        block = stats.get(side) or {}
        for group in ("forwards", "defense"):
            for p in block.get(group) or []:
                goals = float(p.get("goals") or 0)
                rows.append({
                    "pid": str(p.get("playerId") or ""), "short": _txt(p.get("name")),
                    "team": team, "opponent": opp, "home": side == "homeTeam",
                    "position": str(p.get("position") or ("D" if group == "defense" else "F")),
                    "goalie": False,
                    "goals": goals, "assists": float(p.get("assists") or 0),
                    "points": float(p.get("points") if p.get("points") is not None
                                    else goals + float(p.get("assists") or 0)),
                    "sog": float(p.get("sog") if p.get("sog") is not None else p.get("shots") or 0),
                    "blocks": float(p.get("blockedShots") or 0), "hits": float(p.get("hits") or 0),
                    "ppg": float(p.get("powerPlayGoals") or 0), "toi": parse_toi(p.get("toi")),
                    "anytime_goal": 1.0 if goals >= 1 else 0.0,
                })
        for g in block.get("goalies") or []:
            sv, sa = _saves(g)
            toi = parse_toi(g.get("toi"))
            if not toi and not sa:
                continue                       # dressed as the backup, never played
            rows.append({
                "pid": str(g.get("playerId") or ""), "short": _txt(g.get("name")),
                "team": team, "opponent": opp, "home": side == "homeTeam",
                "position": "G", "goalie": True,
                "saves": sv, "shots_against": sa, "goals_against": float(g.get("goalsAgainst") or 0),
                "toi": toi, "started": 1.0 if g.get("starter") else 0.0,
            })
    return rows


def parse_player(landing: dict) -> dict:
    """{"name": "Connor McDavid", "headshot": url, "position": "C"}."""
    p = landing or {}
    first, last = _txt(p.get("firstName")), _txt(p.get("lastName"))
    return {"name": f"{first} {last}".strip(), "headshot": str(p.get("headshot") or ""),
            "position": str(p.get("position") or "")}


def parse_roster(payload: dict, team: str) -> list[dict]:
    """[{pid, name, position, headshot, team}] from /roster/{team}/current."""
    out = []
    for group in ("forwards", "defensemen", "goalies"):
        for p in (payload or {}).get(group) or []:
            name = f"{_txt(p.get('firstName'))} {_txt(p.get('lastName'))}".strip()
            if not name or not p.get("id"):
                continue
            out.append({"pid": str(p["id"]), "name": name, "team": team,
                        "position": str(p.get("positionCode") or ("G" if group == "goalies" else "")),
                        "headshot": str(p.get("headshot") or "")})
    return out


def refresh_rosters(conn, date: str, teams=TEAMS, fetch=fetch_roster, out_dir=None) -> dict:
    """THE FACES, KEPT CURRENT (Ethan, 2026-10-03: "make sure we are pulling
    all the up to date headshots for nhl"). A headshot was stored the first
    time a player was seen and never asked for again — and the league's
    photo address carries the SEASON and the TEAM, so every trade and every
    new season left a face behind. One roster call per club (32 a day)
    re-states every current player's photo, and the day's rosters are kept
    in ROSTER_FILE for the board. A club whose call fails keeps yesterday's."""
    import json as _json
    from pathlib import Path as _P
    from .. import db
    rows, roster, failed = [], {}, []
    for team in teams:
        try:
            players = parse_roster(fetch(team), team)
        except DataUnavailable:
            failed.append(team)
            continue
        roster[team] = [{"name": p["name"], "pid": p["pid"], "position": p["position"]} for p in players]
        rows += [{"sport": "nhl", "player": p["name"], "espn_id": p["pid"], "headshot": p["headshot"],
                  "seen": date} for p in players]
    before = {r[0]: r[1] for r in conn.execute(
        "SELECT player, headshot FROM player_assets WHERE sport='nhl'")}
    db.upsert_player_assets(conn, rows)
    changed = sum(1 for r in rows if r["headshot"] and before.get(r["player"]) != r["headshot"])
    if roster:
        d = _P(out_dir) if out_dir else _P(__file__).resolve().parents[2] / "data"
        d.mkdir(parents=True, exist_ok=True)
        path = d / ROSTER_FILE
        old = {}
        try:
            old = _json.loads(path.read_text()).get("teams") or {}
        except (OSError, ValueError):
            pass
        old.update(roster)
        path.write_text(_json.dumps({"date": date, "teams": old}))
    return {"teams": len(roster), "players": len(rows), "faces_changed": changed, "failed": failed}


def load_rosters(max_age_days: int = 3, path=None) -> dict:
    """{player: team} from ROSTER_FILE when it is recent; {} otherwise, and
    the board then goes by each player's last game as before."""
    import datetime as _dt
    import json as _json
    from pathlib import Path as _P
    p = _P(path) if path else _P(__file__).resolve().parents[2] / "data" / ROSTER_FILE
    try:
        d = _json.loads(p.read_text())
        age = (_dt.date.today() - _dt.date.fromisoformat(d["date"])).days
    except (OSError, ValueError, KeyError):
        return {}
    if age > max_age_days:
        return {}
    return {pl["name"]: team for team, players in (d.get("teams") or {}).items() for pl in players}


def full_names(conn, pids: set, fetch=fetch_player) -> dict:
    """{pid: (full name, headshot)} — from player_assets first, the league's
    player page for anyone not yet seen. A failed lookup is simply absent."""
    out: dict = {}
    want = {p for p in pids if p}
    if not want:
        return out
    marks = ",".join("?" * len(want))
    try:
        for r in conn.execute(f"SELECT espn_id, player, headshot FROM player_assets WHERE sport='nhl' "
                              f"AND espn_id IN ({marks})", tuple(want)):
            out[str(r[0])] = (r[1], r[2])
    except Exception:                                    # noqa: BLE001
        pass
    for pid in want - set(out):
        try:
            info = parse_player(fetch(pid))
        except DataUnavailable:
            continue
        if info["name"]:
            out[pid] = (info["name"], info["headshot"])
    return out


def log_rows(players: list[dict], names: dict, date: str) -> list[dict]:
    """player_game_logs rows, one per market, for one game's players. A
    player whose full name could not be found is left out rather than
    filed under a short name no book will ever quote."""
    from ..seasons import season_of
    season = season_of("nhl", date)
    out = []
    for p in players:
        name = (names.get(p["pid"]) or (None,))[0]
        if not name:
            continue
        for market in (GOALIE_MARKETS if p["goalie"] else SKATER_MARKETS):
            out.append({"sport": "nhl", "season": season, "period": date,
                        "game_id": f"{name}-{date}", "player": name, "team": p["team"],
                        "opponent": p["opponent"], "position": p["position"],
                        "home": 1 if p["home"] else 0, "market": market, "value": p[market]})
    return out


def ingest_day(conn, date: str, scores_only: bool = False, fetch_box=fetch_boxscore,
               fetch_day=fetch_score, fetch_person=fetch_player) -> dict:
    """Store one date's finals and, unless ``scores_only``, every player's
    line. Shape matches the other daily sports' ingesters (ingest._walk_days)."""
    from .. import db
    from ..seasons import season_of
    result: dict = {"games": 0, "player_logs": 0, "assets": 0, "skipped": []}
    try:
        games = [g for g in parse_score_day(fetch_day(date)) if g["type"] in KEEP_TYPES]
    except DataUnavailable as exc:
        result["skipped"].append(f"nhl scores {date}: {exc}")
        return result
    grows, prows, arows = [], [], []
    for g in games:
        if not g["home"] or not g["away"]:
            continue
        grows.append({
            "sport": "nhl", "season": season_of("nhl", date), "period": date,
            "game_id": f"{g['away']}@{g['home']}", "home": g["home"], "away": g["away"],
            "home_score": g["home_score"], "away_score": g["away_score"],
            "spread": 0.0, "total": None, "roof": "dome", "surface": "ice",
            "temp": None, "wind": None, "date": date,
            "extra": json.dumps({"nhl_id": g["game_id"], "type": g["type"], "ended_in": g["ended_in"],
                                 "home_sog": g["home_sog"], "away_sog": g["away_sog"], "start": g["start"]}),
        })
        if scores_only or not g["final"] or not g["game_id"]:
            continue
        try:
            players = parse_boxscore(fetch_box(g["game_id"]))
        except DataUnavailable as exc:
            result["skipped"].append(f"nhl box {g['game_id']}: {exc}")
            continue
        names = full_names(conn, {p["pid"] for p in players}, fetch=fetch_person)
        prows += log_rows(players, names, date)
        arows += [{"sport": "nhl", "player": n, "espn_id": pid, "headshot": h, "seen": date}
                  for pid, (n, h) in names.items() if n]
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    result["assets"] = db.upsert_player_assets(conn, arows)
    if result["games"] or result["player_logs"]:
        db.log_ingest(conn, "nhl", "slate", date, result["games"] + result["player_logs"])
    return result


def schedule_day(date: str, fetch_day=fetch_score) -> list[dict]:
    """Tonight's games for the board: every kept game on the date, live or
    not, with its start (UTC) and team names."""
    return [g for g in parse_score_day(fetch_day(date)) if g["type"] in KEEP_TYPES
            and g["home"] and g["away"]]


def probe(date: str = "2025-10-08") -> list[dict]:
    """Fetch one of each endpoint and report what came back — run on the
    box before a backfill is trusted (this sandbox cannot reach the API)."""
    out = []
    try:
        day = fetch_score(date, ttl=0)
        games = parse_score_day(day)
        out.append({"label": f"scores {date}", "ok": bool(games),
                    "detail": f"{len(games)} game(s); first {games[0]['away']}@{games[0]['home']} "
                              f"state {games[0]['state']}" if games else "no games"})
    except DataUnavailable as exc:
        return [{"label": f"scores {date}", "ok": False, "detail": str(exc)}]
    final = next((g for g in games if g["final"]), None)
    if final:
        try:
            rows = parse_boxscore(fetch_boxscore(final["game_id"], ttl=0))
            sk = [r for r in rows if not r["goalie"]]
            gk = [r for r in rows if r["goalie"]]
            out.append({"label": f"boxscore {final['game_id']}", "ok": bool(sk and gk),
                        "detail": f"{len(sk)} skaters, {len(gk)} goalies; "
                                  f"shots on goal summed {sum(r['sog'] for r in sk):.0f}, "
                                  f"saves summed {sum(r['saves'] for r in gk):.0f}"})
            if sk:
                info = parse_player(fetch_player(sk[0]["pid"], ttl=0))
                out.append({"label": f"player {sk[0]['pid']}", "ok": bool(info["name"]),
                            "detail": f"{sk[0]['short']!r} → {info['name']!r}, "
                                      f"headshot {'yes' if info['headshot'] else 'no'}"})
        except DataUnavailable as exc:
            out.append({"label": "boxscore", "ok": False, "detail": str(exc)})
    return out
