"""Tonight in fantasy points: NBA, WNBA and NHL, off our own boards.

Ethan, 2026-10-27, after the football Fantasy room: the next on the list was
"NBA and NHL fantasy from the props we already project". Every night the
basketball and hockey builds project each priced player's points, rebounds,
assists, threes, steals, blocks and turnovers (hockey: goals, assists,
shots and blocks); a fantasy player wants those added up in fantasy points,
which is what this does, beside each board, the way engine/fantasyweek does
for the NFL week.

THE SCORING is the common daily-fantasy scoring, said on the page:
basketball a point a point, 0.5 a three, 1.25 a rebound, 1.5 an assist,
2 a steal or a block, -0.5 a turnover; hockey 8.5 a goal, 5 an assist,
1.5 a shot on goal, 1.3 a blocked shot. The double-double, triple-double
and hat-trick bonuses need two stats at once and are not counted; neither
are a goalie's win and goals against, so goalies are left out rather than
scored on saves alone.

EACH PART is the board's own projection where it priced him in that stat,
and his season average from the game logs where it did not (`filled`,
named on the row, never hidden). Early in a season his few games are
steadied by last season's average, worth PRIOR_GAMES games. A hockey board
that prices his points and not his goals and assists splits the points by
his own goals to assists. A player listed out is left out; any other
designation rides on the row as it is, at full value, because no
basketball or hockey play chance has been measured here.

POSITIONS are hockey's only (C, W, D, from the logs). Basketball's logs
keep whether he started in that column (S or B: nbadata.log_rows), which
is not a position, so a basketball row carries none.

FREE POINTS, PAID WORKINGS: the stat line (`proj`) is the board's own
median on every market, read beside a book's line a pick, so engine/gate
keeps it for members (ROW_PAID_KEYS_BY_FILE), as for the NFL week.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt

SCORING = {
    "nba": {"pts": 1.0, "fg3m": 0.5, "reb": 1.25, "ast": 1.5, "stl": 2.0, "blk": 2.0, "tov": -0.5},
    "nhl": {"goals": 8.5, "assists": 5.0, "sog": 1.5, "blocks": 1.3},
}
SCORING["wnba"] = SCORING["nba"]
FILES = {"nba": "fantasy_nba.json", "wnba": "fantasy_wnba.json", "nhl": "fantasy_nhl.json"}
#: Designations that mean he will not play.
OUT = {"OUT", "O", "INACTIVE", "SUSPENDED", "IR", "INJURED RESERVE", "NOT WITH TEAM"}
#: A hockey points line split by his own goals-to-assists when the logs
#: hold too few games to say: about the league's skater mix.
GOAL_SHARE = 0.4
#: Last season's average stands for this many games beside this season's.
PRIOR_GAMES = 10
#: Hockey's position codes as a fantasy game lists them.
POS = {"L": "W", "R": "W", "LW": "W", "RW": "W"}


def _pos(sport: str, raw) -> str:
    p = str(raw or "").strip().upper()
    return POS.get(p, p) if sport == "nhl" else ""


def season_means(conn, sport: str, season: int | None = None) -> dict:
    """{player: {market: per game, "_games": n, "position": pos}}: the
    sport's latest logged season (or ``season``), steadied by the one
    before at PRIOR_GAMES games."""
    if conn is None:
        return {}
    try:
        if season is None:
            season = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()[0]
        if season is None:
            return {}
        rows = conn.execute(
            "SELECT season, player, market, COUNT(*), AVG(value), MAX(position) FROM player_game_logs "
            "WHERE sport=? AND season IN (?, ?) GROUP BY season, player, market",
            (sport, int(season), int(season) - 1)).fetchall()
    except Exception:                                             # noqa: BLE001 — no logs, no fill
        return {}
    now, before = {}, {}
    for s, player, market, n, avg, pos in rows:
        (now if int(s) == int(season) else before)[(player, market)] = (int(n or 0), float(avg or 0.0), pos)
    out: dict = {}
    for key in set(now) | set(before):
        player, market = key
        n1, a1, p1 = now.get(key) or (0, 0.0, None)
        n0, a0, p0 = before.get(key) or (0, 0.0, None)
        w0 = PRIOR_GAMES if n0 else 0
        if not n1 and not w0:
            continue
        who = out.setdefault(player, {"_games": 0, "position": ""})
        who[market] = (n1 * a1 + w0 * a0) / (n1 + w0)
        who["_games"] = max(who["_games"], n1 + n0)
        who["position"] = who["position"] or _pos(sport, p1 or p0)
    return out


def _games(games: list) -> dict:
    out = {}
    for g in games or []:
        for side in ("home", "away"):
            if g.get(side):
                out[g[side]] = {"date": g.get("date"), "kickoff": g.get("kickoff"),
                                "home": g.get("home"), "away": g.get("away")}
    return out


def project(sport: str, rows: list, means: dict | None = None, games: list | None = None) -> list:
    """Each priced player's night in fantasy points, best first."""
    weights = SCORING[sport]
    people: dict = {}
    for r in rows or []:
        name, team = r.get("player"), r.get("team")
        if not name or not team or not isinstance(r.get("projection"), (int, float)):
            continue
        p = people.setdefault((team, name), {"player": name, "team": team, "opponent": r.get("opponent"),
                                             "proj": {}, "status": "", "headshot": ""})
        m = r.get("market")
        if m in weights or (sport == "nhl" and m in ("points", "saves")):
            p["proj"].setdefault(m, float(r["projection"]))
        if r.get("injury_status") and not p["status"]:
            p["status"] = str(r["injury_status"])
        if r.get("headshot") and not p["headshot"]:
            p["headshot"] = r["headshot"]
        if _pos(sport, r.get("position")) and not p.get("position"):
            p["position"] = _pos(sport, r.get("position"))
    kick = _games(games)
    out = []
    for (team, name), p in people.items():
        if p["status"].strip().upper() in OUT:
            continue
        mean = (means or {}).get(name) or {}
        proj = dict(p["proj"])
        if sport == "nhl":
            if set(proj) <= {"saves"} or (p.get("position") or mean.get("position")) == "G":
                continue                       # a goalie: his win and goals against are not projected
            if "points" in proj and "goals" not in proj and "assists" not in proj:
                g, a = float(mean.get("goals") or 0.0), float(mean.get("assists") or 0.0)
                share = g / (g + a) if (g + a) > 0 and int(mean.get("_games") or 0) >= 10 else GOAL_SHARE
                proj["goals"], proj["assists"] = proj["points"] * share, proj["points"] * (1 - share)
            proj.pop("points", None)
            proj.pop("saves", None)
        filled = []
        for k in weights:
            if k not in proj and k in mean:
                proj[k] = float(mean[k])
                filled.append(k)
        if not proj:
            continue
        pts = sum(weights[k] * float(v) for k, v in proj.items() if k in weights)
        row = {"player": name, "team": team, "opponent": p["opponent"],
               "position": p.get("position") or mean.get("position") or "",
               "points": round(pts, 2), "proj": {k: round(v, 2) for k, v in proj.items()},
               "board": sorted(k for k in p["proj"] if k in weights or k == "points"),
               "filled": filled}
        if p["status"]:
            row["status"] = p["status"]
        if p["headshot"]:
            row["headshot"] = p["headshot"]
        if team in kick:
            row["game"] = kick[team]
        out.append(row)
    out.sort(key=lambda r: (-r["points"], r["player"]))
    return out


def from_board(sport: str, result: dict, means: dict | None = None, built_at: str | None = None) -> dict:
    """The night's file off a built board (nba_build / nhl_build)."""
    games = (result or {}).get("games") or []
    return {"sport": sport, "date": (result or {}).get("date") or (games[0].get("date") if games else ""),
            "built_at": built_at or _dt.datetime.now().isoformat(timespec="seconds"),
            "scoring": SCORING[sport], "players": project(sport, (result or {}).get("recommendations") or [],
                                                          means, games),
            "games": [{k: g.get(k) for k in ("home", "away", "date", "kickoff")} for g in games]}


def publish(doc: dict, board_out) -> tuple[str, str] | None:
    """Beside the board's public path, through the gate (free points, paid
    stat lines)."""
    if not board_out:
        return None
    from pathlib import Path
    from . import gate
    name = FILES[doc["sport"]]
    return gate.publish(doc, Path(board_out).parent / name, name)


def summary_line(doc: dict) -> str:
    ps = (doc or {}).get("players") or []
    if not ps:
        return f"Fantasy tonight ({(doc or {}).get('sport', '').upper()}): no priced players"
    top = ps[0]
    return (f"Fantasy tonight ({doc['sport'].upper()}): {len(ps)} players, top {top['player']} "
            f"{top['points']:.1f}")


def build(sport: str, result: dict, board_out) -> str:
    """The builds' one call: the season means, the file, the log line.
    Never raises: a night without it is a night without it."""
    try:
        from .db import connect
        conn = connect()
        try:
            means = season_means(conn, sport)
        finally:
            conn.close()
        doc = from_board(sport, result, means)
        publish(doc, board_out)
        return summary_line(doc)
    except Exception as exc:                                      # noqa: BLE001
        return f"Fantasy tonight ({sport.upper()}) skipped: {type(exc).__name__}: {exc}"
