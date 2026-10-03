"""Every NHL shot, from the league's own play-by-play.

Ethan, 2026-10-03, on what NHL still needed: "the opposing goalie, the
shot quality, the power play role, starting goalies". Box scores say how
many shots a player took; they cannot say how good the shots were. The
play-by-play on the same keyless host (``/v1/gamecenter/{id}/play-by-play``)
places every attempt on the ice — x and y in feet from centre, the shot
type, who was in net and how many skaters were on each side — which is
what an expected-goals model is built from (engine/nhl/xg.py).

WHAT A ROW IS. One shot attempt: a goal, a shot on goal, a miss or a
block. Distance and angle are measured to the net the shooter attacks
(x = ±89; ``homeTeamDefendingSide`` says which end, the sign of x where it
is missing). Strength is the shooter's: "EV" level, "PP" up a skater, "SH"
down one; ``empty_net`` when the other side had pulled its goalie.
``rebound`` is a second attempt by the same team within 3 seconds of the
first; ``rush`` an attempt within 4 seconds of play at the other end or in
the neutral zone. Shootouts are not shots and are never stored.

Pure parsers, read by key name; a play with no shooter or no coordinates
is not a row. This sandbox cannot reach the API — `probe` runs on the box.
"""
from __future__ import annotations

import math

from .fetch import DataUnavailable, fetch_json

API = "https://api-web.nhle.com/v1"
#: The attempt types kept, and what each is called in a row.
KINDS = {"goal": "goal", "shot-on-goal": "sog", "missed-shot": "miss", "blocked-shot": "block"}
NET_X = 89.0
REBOUND_S, RUSH_S = 3, 4


def fetch_pbp(game_id, ttl: int = 30 * 86400) -> dict:
    return fetch_json(f"{API}/gamecenter/{game_id}/play-by-play", f"nhl_pbp_{game_id}.json", ttl=ttl)


def _txt(v) -> str:
    return str(v.get("default") or "") if isinstance(v, dict) else str(v or "")


def _secs(period: int, clock: str) -> int:
    try:
        m, s = str(clock).split(":")
        return (max(period, 1) - 1) * 1200 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return 0


def _strength(code: str, home_shooter: bool) -> tuple[str, int]:
    """("EV"|"PP"|"SH", empty_net) from a 4-digit situation code:
    away goalie, away skaters, home skaters, home goalie."""
    c = str(code or "")
    if len(c) != 4 or not c.isdigit():
        return "EV", 0
    ag, ask, hsk, hg = (int(ch) for ch in c)
    mine, theirs = (hsk, ask) if home_shooter else (ask, hsk)
    their_goalie = ag if home_shooter else hg
    strength = "EV" if mine == theirs else "PP" if mine > theirs else "SH"
    return strength, 0 if their_goalie else 1


def geometry(x: float, y: float, attack_right: bool | None) -> tuple[float, float]:
    """(distance in feet, angle in degrees off the goal line's normal) to
    the net being attacked."""
    if attack_right is None:
        attack_right = x >= 0
    nx = NET_X if attack_right else -NET_X
    dx, dy = abs(nx - x), abs(y)
    dist = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx)) if dx or dy else 0.0
    return round(dist, 1), round(angle, 1)


def parse_shots(payload: dict, date: str = "", season: int | None = None) -> list[dict]:
    """Every kept attempt in one game's play-by-play, in order."""
    p = payload or {}
    home, away = p.get("homeTeam") or {}, p.get("awayTeam") or {}
    hid, aid = home.get("id"), away.get("id")
    habbr, aabbr = str(home.get("abbrev") or ""), str(away.get("abbrev") or "")
    names = {}
    for r in p.get("rosterSpots") or []:
        if isinstance(r, dict) and r.get("playerId"):
            names[str(r["playerId"])] = f"{_txt(r.get('firstName'))} {_txt(r.get('lastName'))}".strip()
    out: list[dict] = []
    last_attempt: dict = {}          # team -> seconds of its last unblocked attempt
    last_play = None                 # (seconds, x)
    for play in p.get("plays") or []:
        if not isinstance(play, dict):
            continue
        per = play.get("periodDescriptor") or {}
        if str(per.get("periodType") or "") == "SO":
            continue
        period = int(per.get("number") or 0)
        t = _secs(period, play.get("timeInPeriod") or "")
        d = play.get("details") or {}
        x, y = d.get("xCoord"), d.get("yCoord")
        kind = KINDS.get(str(play.get("typeDescKey") or ""))
        if kind is None:
            if isinstance(x, (int, float)):
                last_play = (t, float(x))
            continue
        owner = d.get("eventOwnerTeamId")
        shooter = d.get("scoringPlayerId") if kind == "goal" else d.get("shootingPlayerId")
        if owner not in (hid, aid) or not shooter or not isinstance(x, (int, float)) \
                or not isinstance(y, (int, float)):
            continue
        is_home = owner == hid
        side = str(play.get("homeTeamDefendingSide") or "")
        attack_right = None
        if side in ("left", "right"):
            # The home team attacks the end it is not defending.
            attack_right = (side == "left") if is_home else (side == "right")
        dist, angle = geometry(float(x), float(y), attack_right)
        strength, empty = _strength(play.get("situationCode"), is_home)
        team = habbr if is_home else aabbr
        rebound = int(kind != "block" and team in last_attempt and 0 <= t - last_attempt[team] <= REBOUND_S)
        rush = 0
        if last_play is not None and 0 <= t - last_play[0] <= RUSH_S:
            px = last_play[1]
            toward = 1 if (attack_right if attack_right is not None else x >= 0) else -1
            rush = int(abs(px) < 25 or px * toward < 0)
        goalie = str(d.get("goalieInNetId") or "")
        out.append({
            "game_id": int(p.get("id") or 0), "event_id": int(play.get("eventId") or 0),
            "date": date, "season": season, "team": team, "opponent": aabbr if is_home else habbr,
            "shooter_id": str(shooter), "shooter": names.get(str(shooter), ""),
            "goalie_id": goalie, "goalie": names.get(goalie, ""), "kind": kind,
            "x": float(x), "y": float(y), "dist": dist, "angle": angle,
            "shot_type": str(d.get("shotType") or ""), "strength": strength, "empty_net": empty,
            "rebound": rebound, "rush": rush, "is_goal": int(kind == "goal"), "period": period,
        })
        if kind != "block":
            last_attempt[team] = t
        last_play = (t, float(x))
    return out


def ingest_game(conn, game_id, date: str, season: int, fetch=fetch_pbp) -> int:
    """Store one final's shots; 0 when the play-by-play will not load."""
    from .. import db
    try:
        rows = parse_shots(fetch(game_id), date, season)
    except DataUnavailable:
        return 0
    return db.upsert_nhl_shots(conn, rows)


def backfill(conn, seasons=None, fetch=fetch_pbp, limit: int | None = None) -> dict:
    """Shots for every stored NHL final that has none yet — safe to stop and
    rerun, a game already stored is skipped. ``limit`` caps one run."""
    import json as _json
    have = {r[0] for r in conn.execute("SELECT DISTINCT game_id FROM nhl_shots")}
    q = "SELECT date, season, extra FROM games WHERE sport='nhl' AND home_score IS NOT NULL"
    args: list = []
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    todo = []
    for date, season, extra in conn.execute(q + " ORDER BY date", args):
        try:
            gid = int((_json.loads(extra or "{}")).get("nhl_id") or 0)
        except (ValueError, TypeError):
            gid = 0
        if gid and gid not in have:
            todo.append((gid, date, season))
    if limit:
        todo = todo[:limit]
    shots = games = failed = 0
    for i, (gid, date, season) in enumerate(todo, 1):
        n = ingest_game(conn, gid, date, season, fetch=fetch)
        shots += n
        games += bool(n)
        failed += not n
        if i % 200 == 0:
            conn.commit()
            print(f"      {i}/{len(todo)} games · {shots:,} shots", flush=True)
    conn.commit()
    return {"games": games, "shots": shots, "failed": failed, "todo": len(todo)}
