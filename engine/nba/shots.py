"""Every shot an NBA player took, for the shot chart (kind "shots").

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list he
said yes to had the NBA's shot chart on it.

WHAT THE LEAGUE PUBLISHES. The CDN that already gives this site every NBA
box score (engine/sources/nbadata) publishes each game's play-by-play
beside it, `liveData/playbyplay/playbyplay_{gameId}.json`, the JSON the
league's own game pages draw from. Its `game.actions` carry, for every
field-goal attempt (`actionType` "2pt" or "3pt"): the shooter
(`personId`) and his team (`teamTricode`), the period and the clock, the
result (`shotResult` "Made" or "Missed"), the kind of shot (`subType`:
Jump Shot, Layup, Dunk, Hook...) and its `descriptor` (pullup, driving,
step back...), the distance in feet (`shotDistance`), where it was taken
(`xLegacy`, `yLegacy`: the legacy court coordinates, tenths of a foot from
the middle of the basket), who assisted a make, who blocked a miss, and
the qualifiers (fast break, second chance, in the paint, off a turnover).
A free throw is `actionType` "freethrow". That field list is the one the
nba_api project documents for this endpoint; the runbook's box check
prints a real action's keys before anything more is trusted.

THE NAMES come from the same game's box score. The play-by-play carries an
initial and a surname; the box score's full name is the spelling the
player logs, and so the boards, already use.

WHAT IS STORED: one row per field-goal attempt and per free throw
(`nba_shots`). Nothing here is a model. The zones are the league's own
(restricted area, the rest of the paint, mid-range, the corner three,
above the break), taken from the feed's `area` where an action carries
one and otherwise read off where the shot was taken; the league's
percentage in each zone is every stored shot of that season.

WHERE THE GAMES COME FROM. This season's finals are on the CDN's season
file. Last season's are not (it holds one season), so its regular season
is read by the league's own numbering: 1,230 games, "002" + the season's
two digits + 00001 to 01230. The nightly reads the last few days' finals
and the backfill older ones, a budget a night; neither keeps a copy of a
play-by-play in data/cache once its shots are stored.
"""

from __future__ import annotations

import math
import re

FIELD_GOALS = ("2pt", "3pt")
FREE_THROW = "freethrow"

SHOT_COLS = ["game_id", "action", "season", "date", "person_id", "player", "team", "opponent", "home",
             "period", "clock", "kind", "made", "shot", "descriptor", "distance", "x", "y", "zone",
             "area", "assist", "blocked", "quals"]

#: The league's shot zones, in the order the page lists them.
ZONES = (("ra", "Restricted area"), ("paint", "In the paint"), ("mid", "Mid-range"),
         ("corner3", "Corner 3"), ("above3", "Above the break 3"))
ZONE_NAME = dict(ZONES)
#: The feed's own area words (a newer feed carries them on a shot) to ours.
AREA = {"restricted area": "ra", "in the paint (non-ra)": "paint", "mid-range": "mid",
        "left corner 3": "corner3", "right corner 3": "corner3", "above the break 3": "above3",
        "backcourt": "above3"}
#: The court in the feed's units (tenths of a foot, the basket at 0, 0):
#: the restricted area's radius, the lane's half-width and the free-throw
#: line, and how far up from the baseline the corner three runs.
RA_R, LANE_HALF, FT_LINE, CORNER_TOP = 40.0, 80.0, 142.5, 92.5

#: A regular season, numbered by the league.
REGULAR_GAMES = 1230
#: Games read per night by the backfill (two files each).
BACKFILL_PER_NIGHT = 300
#: Distance bands for the splits, in feet.
DIST_BANDS = ((0, 4, "0-4 ft"), (5, 9, "5-9 ft"), (10, 14, "10-14 ft"), (15, 19, "15-19 ft"),
              (20, 24, "20-24 ft"), (25, 99, "25+ ft"))


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _int(v):
    f = _num(v)
    return None if f is None else int(f)


def clock(pt) -> str:
    """The feed's period clock ("PT07M04.00S") as a scoreboard reads it."""
    m = re.match(r"PT(\d+)M(\d+)(?:\.\d+)?S", str(pt or ""))
    return f"{int(m.group(1))}:{int(m.group(2)):02d}" if m else ""


def zone(kind: str, x, y, dist, area: str = "") -> str:
    """The league's zone for a field-goal attempt."""
    own = AREA.get(str(area or "").strip().lower())
    if own:
        return own
    if kind == "3pt":
        return "corner3" if y is not None and y <= CORNER_TOP else "above3"
    if x is not None and y is not None:
        if math.hypot(x, y) <= RA_R:
            return "ra"
        return "paint" if abs(x) <= LANE_HALF and y <= FT_LINE else "mid"
    if dist is None:
        return "mid"
    return "ra" if dist <= RA_R / 10 else "paint" if dist <= 8 else "mid"


def _date_of(game: dict) -> str:
    """A box score's game date, Eastern (the date the schedule uses)."""
    et = str(game.get("gameEt") or "")
    if re.match(r"\d{4}-\d{2}-\d{2}", et):
        return et[:10]
    code = str(game.get("gameCode") or "")
    if re.match(r"\d{8}/", code):
        return f"{code[:4]}-{code[4:6]}-{code[6:8]}"
    return ""


def fold(pbp: dict, box: dict, date: str = "") -> list[dict]:
    """One final's shots and free throws as `nba_shots` rows. Nothing when
    the box score cannot say whose game it is."""
    from ..seasons import season_of
    game = (box or {}).get("game") or {}
    gid = str(game.get("gameId") or ((pbp or {}).get("game") or {}).get("gameId") or "")
    home = str((game.get("homeTeam") or {}).get("teamTricode") or "")
    away = str((game.get("awayTeam") or {}).get("teamTricode") or "")
    date = date or _date_of(game)
    if not gid or not date or not home or not away:
        return []
    names = {}
    for side in ("homeTeam", "awayTeam"):
        for p in (game.get(side) or {}).get("players") or []:
            pid = _int(p.get("personId"))
            if pid and p.get("name"):
                names[pid] = str(p["name"])
    season = season_of("nba", date)
    out = []
    for a in ((pbp or {}).get("game") or {}).get("actions") or []:
        t = str(a.get("actionType") or "").lower()
        if t not in FIELD_GOALS and t != FREE_THROW:
            continue
        res = str(a.get("shotResult") or "")
        pid = _int(a.get("personId"))
        team = str(a.get("teamTricode") or "")
        if res not in ("Made", "Missed") or not pid or team not in (home, away):
            continue
        fg = t in FIELD_GOALS
        x, y = (_num(a.get("xLegacy")), _num(a.get("yLegacy"))) if fg else (None, None)
        dist = _num(a.get("shotDistance")) if fg else None
        if fg and dist is None and x is not None and y is not None:
            dist = round(math.hypot(x, y) / 10, 1)
        quals = sorted({q for q in (a.get("qualifiers") or []) if isinstance(q, str)})
        made = res == "Made"
        out.append({"game_id": gid, "action": _int(a.get("actionNumber")), "season": season, "date": date,
                    "person_id": pid,
                    "player": names.get(pid) or str(a.get("playerNameI") or a.get("playerName") or ""),
                    "team": team, "opponent": away if team == home else home, "home": 1 if team == home else 0,
                    "period": _int(a.get("period")), "clock": clock(a.get("clock")),
                    "kind": t if fg else "ft", "made": 1 if made else 0,
                    "shot": str(a.get("subType") or ""), "descriptor": str(a.get("descriptor") or ""),
                    "distance": dist, "x": x, "y": y,
                    "zone": zone(t, x, y, dist, a.get("area")) if fg else "",
                    "area": str(a.get("area") or ""),
                    "assist": str(a.get("assistPlayerNameInitial") or "") if made else "",
                    "blocked": 1 if a.get("blockPersonId") else 0,
                    "quals": ",".join(quals)})
    return out


# --- the games ------------------------------------------------------------------
def schedule_finals(sched: dict, before: str) -> list[dict]:
    """``[{game_id, date}]`` — every final on the CDN's season file before a
    date: the regular season, the play-in, the Cup final and the playoffs;
    never the preseason or the All-Star Game."""
    out = []
    for day in ((sched or {}).get("leagueSchedule") or {}).get("gameDates") or []:
        for g in day.get("games") or []:
            gid = str(g.get("gameId") or "")
            date = str(g.get("gameDateEst") or "")[:10]
            if not gid or gid[:3] in ("001", "003") or g.get("gameStatus") != 3 or not date or date >= before:
                continue
            out.append({"game_id": gid, "date": date})
    return out


def season_ids(season: int) -> list[dict]:
    """A past regular season by the league's own numbering, newest first."""
    yy = f"{int(season) % 100:02d}"
    return [{"game_id": f"002{yy}{n:05d}", "date": ""} for n in range(REGULAR_GAMES, 0, -1)]


def stored(conn, season: int | None = None) -> set:
    """The games already folded (a final's shots never change)."""
    q, args = "SELECT DISTINCT game_id FROM nba_shots", ()
    if season is not None:
        q, args = q + " WHERE season=?", (int(season),)
    try:
        return {str(r[0]) for r in conn.execute(q, args)}
    except Exception:                                              # noqa: BLE001
        return set()


def read_once(game_id: str) -> tuple:
    """``(play-by-play, box score)`` for one game, or ``(None, None)``, read
    without keeping the files the read wrote: nothing reads a play-by-play
    again once its shots are stored, and a season of them is ~500 MB. A
    box score already on disk (the results ingest's) stays as it was."""
    from ..sources import fetch as F
    from ..sources import nbadata as N
    names = (f"nba_pbp_{game_id}.json", f"nba_box_{game_id}.json")
    had = [F._cache_path(n).exists() for n in names]
    try:
        return N.fetch_playbyplay(game_id), N.fetch_boxscore(game_id)
    except Exception:                                              # noqa: BLE001
        return None, None
    finally:
        for n, was in zip(names, had):
            if not was:
                try:
                    F._cache_path(n).unlink()
                except OSError:
                    pass


#: Games read, folded and stored at a time (engine/mlb/charts.CHUNK has the
#: why): a play-by-play and its box score are a few MB parsed, and the
#: night's 300 held at once were most of a gigabyte in a 1,600 MB service.
CHUNK = 8


def ingest_games(conn, games: list, read=None, workers: int = 4, chunk: int = CHUNK) -> dict:
    """Fold and store every game in ``games`` not already stored, ``chunk``
    at a time, each chunk written before the next is read. A chunk none of
    whose games could be read ends the run; the rest wait for the next.
    ``{"games", "shots", "failed"}``."""
    from concurrent.futures import ThreadPoolExecutor
    from .. import db
    have = stored(conn)
    todo = [g for g in games if str(g["game_id"]) not in have]
    out = {"games": 0, "shots": 0, "failed": 0}
    if not todo:
        return out
    read = read or read_once
    step = max(1, int(chunk))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i in range(0, len(todo), step):
            part = todo[i:i + step]
            pairs = list(pool.map(lambda g: read(str(g["game_id"])), part))
            if not any(pbp and box for pbp, box in pairs):
                out["failed"] += len(part)
                break
            for g, (pbp, box) in zip(part, pairs):
                rows = fold(pbp, box, g.get("date") or "") if pbp and box else []
                if not rows:
                    out["failed"] += 1
                    continue
                out["shots"] += db.upsert_nba_shots(conn, rows)
                out["games"] += 1
            pairs = None
    return out


def ingest_recent(conn, today, days: int = 3, read=None) -> dict:
    """The last few days' finals, off the season file the results ingest
    just read."""
    import datetime as _dt
    from ..sources import nbadata as N
    first = (today - _dt.timedelta(days=days)).isoformat()
    games = [g for g in schedule_finals(N.fetch_schedule(), today.isoformat()) if g["date"] >= first]
    return ingest_games(conn, games, read=read)


def backfill(conn, today, budget: int = BACKFILL_PER_NIGHT, read=None) -> dict:
    """This season's finals, then last season's, newest first, ``budget``
    games at a time. Last season's are asked for by number; five misses in
    a row on its newest say the CDN no longer has that season, and it is
    left for the night."""
    from ..seasons import season_of
    from ..sources import nbadata as N
    cur = season_of("nba", today.isoformat())
    have = stored(conn)
    todo = []
    try:
        todo = [g for g in sorted(schedule_finals(N.fetch_schedule(), today.isoformat()),
                                  key=lambda g: g["date"], reverse=True) if g["game_id"] not in have]
    except Exception:                                              # noqa: BLE001
        todo = []
    out = {"games": 0, "shots": 0, "failed": 0, "left": 0, "last_season": ""}
    take = todo[:budget]
    if take:
        got = ingest_games(conn, take, read=read)
        for k in ("games", "shots", "failed"):
            out[k] += got[k]
    room = budget - len(take)
    past = [g for g in season_ids(cur - 1) if g["game_id"] not in have]
    if room > 0 and past:
        probe = ingest_games(conn, past[:5], read=read)
        for k in ("games", "shots", "failed"):
            out[k] += probe[k]
        if probe["games"]:
            got = ingest_games(conn, past[5:room], read=read)
            for k in ("games", "shots", "failed"):
                out[k] += got[k]
        else:
            out["last_season"] = "not on the CDN"
    out["left"] = max(0, len(todo) + len(past) - out["games"] - out["failed"])
    return out


# --- what the page draws -------------------------------------------------------------
def season_label(season: int) -> str:
    """2025 → "2025-26": an NBA season is named for both its years."""
    return f"{int(season)}-{(int(season) + 1) % 100:02d}"


def resolve(conn, player: str) -> tuple:
    """``(person id, stored name)``, or ``(None, "")``."""
    from ..carries import _fold
    q = (player or "").strip()
    if not q:
        return None, ""
    row = conn.execute("SELECT person_id, player FROM nba_shots WHERE player=? ORDER BY date DESC LIMIT 1",
                       (q,)).fetchone()
    if row:
        return row[0], row[1]
    want = _fold(q)
    if not want:
        return None, ""
    hits = {}
    for pid, name in conn.execute("SELECT DISTINCT person_id, player FROM nba_shots"):
        if _fold(name) == want:
            hits[pid] = name
    return next(iter(hits.items())) if len(hits) == 1 else (None, "")


def _line(shots: list) -> dict:
    """A game's or a split's shooting line, the box score's way."""
    fg = [s for s in shots if s["k"] in FIELD_GOALS]
    three = [s for s in fg if s["k"] == "3pt"]
    ft = [s for s in shots if s["k"] == "ft"]
    fgm, fg3m, ftm = sum(s["m"] for s in fg), sum(s["m"] for s in three), sum(s["m"] for s in ft)
    rate = lambda m, n: round(m / n, 3) if n else None  # noqa: E731
    return {"n": len(fg), "fga": len(fg), "fgm": fgm, "fg3a": len(three), "fg3m": fg3m,
            "fta": len(ft), "ftm": ftm, "pts": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
            "fg_pct": rate(fgm, len(fg)), "fg3_pct": rate(fg3m, len(three)), "ft_pct": rate(ftm, len(ft)),
            "assisted": sum(1 for s in fg if s["m"] and s["a"]),
            "paint": sum(1 for s in fg if s["z"] in ("ra", "paint"))}


def _splits(rows: list, key, order=None) -> list:
    by: dict = {}
    for s in rows:
        k = key(s)
        if k:
            by.setdefault(k, []).append(s)
    keys = [k for k in (order or sorted(by, key=lambda k: -len(by[k]))) if k in by]
    out = []
    for k in keys:
        xs = by[k]
        made = sum(s["m"] for s in xs)
        out.append({"key": k, "name": k, "fga": len(xs), "fgm": made, "pct": round(made / len(xs), 3)})
    return out


def _league(conn, season: int) -> dict:
    """The league's field-goal percentage in each zone that season, from
    every stored shot."""
    out = {}
    for z, n, m in conn.execute("SELECT zone, COUNT(*), SUM(made) FROM nba_shots WHERE season=? "
                                "AND kind IN ('2pt', '3pt') GROUP BY zone", (int(season),)):
        if z and n:
            out[z] = round((m or 0) / n, 3)
    return out


#: The box-score stats drawn beside a game's shots, off the player logs.
BOX = ("min", "reb", "ast", "stl", "blk", "tov")


def chart(conn, player: str, season: int | None = None) -> dict:
    """Everything the shot chart draws for one player-season.

    ``{player, sport, seasons, season, season_label, team, games: [{id, date,
    opp, home, team, line, box, shots}], season_line, zones, by_type,
    by_period, by_dist}`` — games newest first, each shot ``{i, x, y, m, k,
    d, t, ds, p, c, a, b, z, q}`` in the order taken."""
    pid, name = resolve(conn, player)
    if pid is None:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM nba_shots WHERE person_id=? ORDER BY season DESC", (pid,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    games: dict = {}
    for (gid, act, date, team, opp, home, per, clk, kind, made, shot, desc, dist, x, y, zn, ast,
         blk, quals) in conn.execute(
            "SELECT game_id, action, date, team, opponent, home, period, clock, kind, made, shot, descriptor, "
            "distance, x, y, zone, assist, blocked, quals FROM nba_shots WHERE person_id=? AND season=? "
            "ORDER BY date DESC, game_id, action", (pid, pick)):
        g = games.setdefault(gid, {"id": gid, "date": date, "opp": opp, "home": bool(home), "team": team,
                                   "shots": []})
        g["shots"].append({"i": act, "x": x, "y": y, "m": int(made or 0), "k": kind,
                           "d": dist, "t": shot, "ds": desc, "p": per, "c": clk, "a": ast or "",
                           "b": int(blk or 0), "z": zn or "", "q": quals or ""})
    out_games = list(games.values())
    logs: dict = {}
    if out_games:
        dates = sorted({g["date"] for g in out_games})
        marks = ",".join("?" * len(BOX))
        for date, market, value in conn.execute(
                f"SELECT period, market, value FROM player_game_logs WHERE sport='nba' AND player=? "
                f"AND period BETWEEN ? AND ? AND market IN ({marks})", (name, dates[0], dates[-1], *BOX)):
            logs.setdefault(date, {})[market] = value
    every = []
    for g in out_games:
        g["line"] = _line(g["shots"])
        g["box"] = logs.get(g["date"], {})
        every += g["shots"]
    fg = [s for s in every if s["k"] in FIELD_GOALS]
    league = _league(conn, pick)
    zones = []
    for key, label in ZONES:
        xs = [s for s in fg if s["z"] == key]
        made = sum(s["m"] for s in xs)
        zones.append({"key": key, "name": label, "fga": len(xs), "fgm": made,
                      "pct": round(made / len(xs), 3) if xs else None,
                      "share": round(len(xs) / len(fg), 3) if fg else None, "league": league.get(key)})
    line = _line(every)
    n = len(out_games)
    line.update({"games": n, "ppg": round(line["pts"] / n, 1) if n else None,
                 "fga_pg": round(line["fga"] / n, 1) if n else None,
                 "fg3a_pg": round(line["fg3a"] / n, 1) if n else None})
    by_type = _splits(fg, lambda s: s["t"] or "Other")
    by_period = _splits(fg, lambda s: (f"Q{s['p']}" if (s["p"] or 0) <= 4 else "OT") if s["p"] else "",
                        order=["Q1", "Q2", "Q3", "Q4", "OT"])
    by_dist = _splits(fg, lambda s: next((lab for lo, hi, lab in DIST_BANDS
                                          if s["d"] is not None and lo <= s["d"] < hi + 1), ""),
                      order=[lab for _lo, _hi, lab in DIST_BANDS])
    # The final over the game's building (the chart's frame, 2026-10-14).
    from ..carries import scoreboard
    scoreboard(conn, "nba", pick, out_games)
    latest = out_games[0] if out_games else {}
    return {"player": name, "sport": "nba", "seasons": seasons, "season": pick,
            "season_label": season_label(pick), "team": latest.get("team", ""), "games": out_games,
            "season_line": line, "zones": zones, "by_type": by_type, "by_period": by_period,
            "by_dist": by_dist}
