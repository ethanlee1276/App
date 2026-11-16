"""A player's game log, one line a game, in every league (2026-11-16).

Ethan, with ESPN's game log for Joe Burrow: "we should have game logs for
every player too that you can look up and see for each player."

The history file already keeps one row per player, stat and game in every
league (`player_game_logs`). `season_log` turns one player's season into a
line a game: the day (and the week, in football), the opponent and where,
the result and the score off the `games` table, and the league's own columns
grouped the way a box score groups them (passing, rushing and receiving; the
basketball box; a skater's or a goalie's line; a hitter's or a pitcher's).
The season's totals and its per-game averages close it. A group is shown
only where the player has a number in it, a column only where the file keeps
it, so a receiver's log is no wall of empty passing columns.

Facts, not picks: served free (server.py /api/players/gamelog) on the same
footing as the logs behind the player page, and drawn by js/gamelog.js.
"""
from __future__ import annotations

import datetime as _dt
import os
import re

from . import db as _db

# How a column is worked out from one game's stats (and from the season's):
#   ("sum", m, ...)   the first of the markets the file keeps
#   ("pct", made, tried)  made over tried, as a percentage
#   ("avg", num, den)     num over den
#   ("made", made, tried) "made-tried"
#   ("rating",)           the passer rating (the NFL's; college's efficiency)
#   ("toi", m)            time on ice in minutes, an average over the season
#   ("ip", outs)          innings pitched from outs ("6.1")
FOOTBALL = (
    ("passing", "Passing", ("pass_att",), (
        ("cmp", "CMP", "Completions", ("sum", "pass_cmp")),
        ("att", "ATT", "Passing attempts", ("sum", "pass_att")),
        ("yds", "YDS", "Passing yards", ("sum", "pass_yds")),
        ("pct", "CMP%", "Completion percentage", ("pct", "pass_cmp", "pass_att")),
        ("avg", "AVG", "Yards per pass attempt", ("avg", "pass_yds", "pass_att")),
        ("td", "TD", "Passing touchdowns", ("sum", "pass_td")),
        ("int", "INT", "Interceptions thrown", ("sum", "pass_int")),
        ("rtg", "RTG", "Passer rating", ("rating",)))),
    ("rushing", "Rushing", ("carries", "rush_att"), (
        ("car", "CAR", "Rushing attempts", ("sum", "carries", "rush_att")),
        ("yds", "YDS", "Rushing yards", ("sum", "rush_yds")),
        ("avg", "AVG", "Yards per rush", ("avg", "rush_yds", "carries")),
        ("td", "TD", "Rushing touchdowns", ("sum", "rush_td")))),
    ("receiving", "Receiving", ("receptions", "targets"), (
        ("rec", "REC", "Receptions", ("sum", "receptions")),
        ("tgt", "TGT", "Targets", ("sum", "targets")),
        ("yds", "YDS", "Receiving yards", ("sum", "rec_yds")),
        ("avg", "AVG", "Yards per catch", ("avg", "rec_yds", "receptions")),
        ("td", "TD", "Receiving touchdowns", ("sum", "rec_td")))),
)
HOOPS = (
    ("box", "", ("min", "pts"), (
        ("min", "MIN", "Minutes", ("sum", "min")),
        ("pts", "PTS", "Points", ("sum", "pts")),
        ("reb", "REB", "Rebounds", ("sum", "reb")),
        ("ast", "AST", "Assists", ("sum", "ast")),
        ("stl", "STL", "Steals", ("sum", "stl")),
        ("blk", "BLK", "Blocks", ("sum", "blk")),
        ("tov", "TO", "Turnovers", ("sum", "tov")),
        ("fg", "FG", "Field goals made-attempted", ("made", "fgm", "fga")),
        ("fgp", "FG%", "Field goal percentage", ("pct", "fgm", "fga")),
        ("fg3", "3PT", "Three-pointers made-attempted", ("made", "fg3m", "fg3a")),
        ("ft", "FT", "Free throws made-attempted", ("made", "ftm", "fta")),
        ("oreb", "OREB", "Offensive rebounds", ("sum", "oreb")))),
)
HOCKEY = (
    ("skater", "", ("goals", "assists", "sog", "points"), (
        ("g", "G", "Goals", ("sum", "goals")),
        ("a", "A", "Assists", ("sum", "assists")),
        ("pts", "PTS", "Points", ("sum", "points")),
        ("sog", "SOG", "Shots on goal", ("sum", "sog")),
        ("blk", "BLK", "Blocked shots", ("sum", "blocks")),
        ("hit", "HIT", "Hits", ("sum", "hits")),
        ("ppg", "PPG", "Power-play goals", ("sum", "ppg")),
        ("toi", "TOI", "Time on ice", ("toi", "toi")))),
    ("goalie", "Goalie", ("shots_against", "saves"), (
        ("sa", "SA", "Shots against", ("sum", "shots_against")),
        ("sv", "SV", "Saves", ("sum", "saves")),
        ("ga", "GA", "Goals against", ("sum", "goals_against")),
        ("svp", "SV%", "Save percentage", ("pct", "saves", "shots_against")),
        ("toi", "TOI", "Time on ice", ("toi", "toi")))),
)
BASEBALL = (
    ("batting", "Batting", ("pa", "hits", "total_bases"), (
        ("pa", "PA", "Plate appearances", ("sum", "pa")),
        ("h", "H", "Hits", ("sum", "hits")),
        ("tb", "TB", "Total bases", ("sum", "total_bases")),
        ("hr", "HR", "Home runs", ("sum", "home_runs")))),
    ("pitching", "Pitching", ("outs",), (
        ("ip", "IP", "Innings pitched", ("ip", "outs")),
        ("k", "K", "Strikeouts", ("sum", "strikeouts")))),
)
LAYOUTS = {"nfl": FOOTBALL, "cfb": FOOTBALL, "nba": HOOPS, "wnba": HOOPS, "cbb": HOOPS, "nhl": HOCKEY,
           "mlb": BASEBALL}
#: A league whose `period` is a week number, not a day.
WEEKLY = ("nfl", "cfb")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _first(stats: dict, markets) -> float | None:
    for m in markets:
        if stats.get(m) is not None:
            return float(stats[m])
    return None


def _rating(sport: str, s: dict) -> float | None:
    att = s.get("pass_att") or 0.0
    if att <= 0:
        return None
    cmp_, yds = s.get("pass_cmp") or 0.0, s.get("pass_yds") or 0.0
    td, ints = s.get("pass_td") or 0.0, s.get("pass_int") or 0.0
    if sport == "cfb":
        # College's passer efficiency, the number ESPN's college logs print.
        return round((8.4 * yds + 330 * td + 100 * cmp_ - 200 * ints) / att, 1)
    clip = lambda x: max(0.0, min(2.375, x))                     # noqa: E731
    a, b = clip((cmp_ / att - 0.3) * 5), clip((yds / att - 3) * 0.25)
    c, d = clip(td / att * 20), clip(2.375 - ints / att * 25)
    return round((a + b + c + d) / 6 * 100, 1)


def value(sport: str, how: tuple, s: dict, games: int = 1):
    """One column's value from a game's stats, or from the season's summed
    stats (``games`` played, for the averages a sum cannot carry)."""
    kind = how[0]
    if kind == "sum":
        return _first(s, how[1:])
    if kind in ("pct", "avg"):
        num, den = s.get(how[1]), s.get(how[2])
        if num is None or not den:
            return None
        return round(100.0 * num / den, 1) if kind == "pct" else round(num / den, 1)
    if kind == "made":
        made, tried = s.get(how[1]), s.get(how[2])
        return None if made is None or tried is None else f"{int(made)}-{int(tried)}"
    if kind == "rating":
        return _rating(sport, s)
    if kind == "toi":
        t = s.get(how[1])
        return None if t is None else round(t / max(1, games), 2)
    if kind == "ip":
        outs = s.get(how[1])
        return None if outs is None else f"{int(outs) // 3}.{int(outs) % 3}"
    return None


def _played(sport: str, s: dict) -> bool:
    """A basketball line of no minutes is a game he did not play."""
    return not (sport in ("nba", "wnba", "cbb") and s.get("min") is not None and float(s["min"]) <= 0)


#: Leagues where one player's rows a day or less apart are one game. Football is
#: played once a week, and college's history holds copies of one game from more
#: than one writer (seen live 2026-11-16, after engine/cfbdedupe's pass of the
#: 14th): the play file's row, whose completions went to nobody when its passer
#: split missed (Arch Manning, 0 of 9 for 0 yards at Oklahoma), beside the box
#: score's (19 of 31 for 260); a copy a day off; a copy keyed by ESPN's team
#: number ("espn:194" for Ohio State). Read as one game, each box-score group
#: from whichever copy carries the fuller line.
ONE_A_WEEK = ("cfb",)


def _group_markets(sport: str) -> list:
    out = []
    for _, _, marks, cols in LAYOUTS.get(sport, ()):
        ms = set(marks)
        for c in cols:
            if c[3][0] in ("sum", "pct", "avg", "made", "toi", "ip"):
                ms.update(c[3][1:])
            elif c[3][0] == "rating":
                ms.update(("pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int"))
        out.append(ms)
    return out


def _day(period) -> "_dt.date | None":
    try:
        return _dt.date.fromisoformat(str(period)[:10])
    except (TypeError, ValueError):
        return None


def collapse(sport: str, games: list) -> list:
    """One player's game dicts (period, game_id, team, opponent, stats), copies
    of one game merged where the league plays once a week (ONE_A_WEEK); each
    merged game says how many rows it was made of (``copies``)."""
    if sport not in ONE_A_WEEK or len(games) < 2:
        return games
    groups = _group_markets(sport)
    grouped = set().union(*groups) if groups else set()
    out: list = []
    for g in sorted(games, key=lambda g: str(g["period"])):
        d = _day(g["period"])
        head = out[-1] if out else None
        if head is not None and d and head["_day"] and (d - head["_day"]).days <= 1:
            for key in ("team", "opponent"):
                if str(head.get(key) or "").startswith("espn:") and g.get(key) and not str(g[key]).startswith("espn:"):
                    head[key] = g[key]
            mine, theirs = head["stats"], g["stats"]
            for ms in groups:
                if sum(theirs.get(m) or 0 for m in ms) > sum(mine.get(m) or 0 for m in ms):
                    for m in ms:
                        mine.pop(m, None)
                        if theirs.get(m) is not None:
                            mine[m] = theirs[m]
            for m, v in theirs.items():
                if m not in grouped and v is not None and (mine.get(m) is None or v > mine[m]):
                    mine[m] = v
            head["copies"] += 1
            continue
        out.append(dict(g, stats=dict(g["stats"]), copies=1, _day=d))
    for g in out:
        g.pop("_day", None)
    return out


def has_line(sport: str, s: dict) -> bool:
    """Does a game's row carry a box-score line in the league's layout? Seen on
    the live file 2026-11-16: Joe Burrow's Sunday game had a row the night of
    the game (a touchdown flag) and no passing line until the week's box
    scores land, and it was counted as a game played, so his averages fell by
    a ninth. A row with no line is a game whose numbers are still to come."""
    return any(_first(s, marks) is not None for _, _, marks, _ in LAYOUTS.get(sport, ()))


def _results(conn, sport: str, season: int) -> tuple[dict, dict]:
    """The season's games, by game id and by (period, the two clubs)."""
    by_id, by_pair = {}, {}
    for r in conn.execute("SELECT period, game_id, home, away, home_score, away_score, date FROM games "
                          "WHERE sport=? AND season=?", (sport, season)):
        g = {"period": str(r[0]), "home": r[2], "away": r[3], "hs": r[4], "as": r[5], "date": r[6]}
        by_id[str(r[1])] = g
        by_pair[(str(r[0]), frozenset((r[2], r[3])))] = g
    return by_id, by_pair


def seasons_of(conn, sport: str, player: str) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND player=? ORDER BY season DESC",
        (sport, player)) if r[0] is not None]


def season_log(sport: str, player: str, season: int | None = None, db_path=None) -> dict:
    """``{player, sport, season, seasons, team, position, groups, games, totals,
    per_game}`` for one player's season, the newest game first; ``{}`` where
    the league has no layout, the file is missing or he has no games."""
    layout = LAYOUTS.get(sport)
    path = str(db_path or _db.DEFAULT_DB)
    if not layout or not player or not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        seasons = seasons_of(conn, sport, player)
        if not seasons:
            from .statlogs import resolve_player
            found = resolve_player(conn, sport, player)
            if found and found != player:
                player = found
                seasons = seasons_of(conn, sport, player)
        if not seasons:
            return {}
        season = int(season) if season and int(season) in seasons else seasons[0]
        rows = conn.execute(
            "SELECT period, game_id, team, opponent, position, home, market, value FROM player_game_logs "
            "WHERE sport=? AND player=? AND season=?", (sport, player, season)).fetchall()
        by_id, by_pair = _results(conn, sport, season)
    finally:
        conn.close()
    games: dict = {}
    for period, gid, team, opp, pos, home, market, val in rows:
        g = games.setdefault((str(period), str(gid)), {"period": str(period), "game_id": str(gid), "team": team,
                                                       "opponent": opp, "position": pos, "home": home, "stats": {}})
        if val is not None:
            g["stats"][market] = float(val)
    games = {(g["period"], g["game_id"]): g for g in collapse(sport, list(games.values()))}
    # The groups this player has a number in, and the columns the file keeps.
    groups = []
    for key, title, marks, cols in layout:
        if not any(_first(g["stats"], marks) for g in games.values()):
            continue
        kept = [c for c in cols if any(value(sport, c[3], g["stats"]) is not None for g in games.values())]
        if kept:
            groups.append((key, title, kept))
    if not groups:
        return {}
    out_games, played, summed = [], 0, {}
    for g in games.values():
        s = g["stats"]
        res = by_id.get(g["game_id"]) or by_pair.get((g["period"], frozenset((g["team"], g["opponent"]))))
        home = (res["home"] == g["team"]) if res else bool(g["home"])
        line = {"opponent": g["opponent"], "home": home, "team": g["team"]}
        if sport in WEEKLY and not _ISO.match(g["period"]):
            try:
                line["week"] = int(g["period"])
            except ValueError:
                pass
            line["date"] = str((res or {}).get("date") or "")[:10]
        else:
            line["date"] = g["period"][:10]
        if res and res["hs"] is not None and res["as"] is not None:
            mine, theirs = (res["hs"], res["as"]) if home else (res["as"], res["hs"])
            line["result"] = "W" if mine > theirs else "L" if mine < theirs else "T"
            line["score"] = f"{int(mine)}-{int(theirs)}"
        if not _played(sport, s):
            line["dnp"] = True
        elif not has_line(sport, s):
            line["pending"] = True             # out of the games played until its line lands
        else:
            played += 1
            for m, v in s.items():
                summed[m] = summed.get(m, 0.0) + v
        line["values"] = {f"{k}.{c[0]}": value(sport, c[3], s) for k, _, cols in groups for c in cols}
        out_games.append(line)
    out_games.sort(key=lambda x: (x.get("date") or "", x.get("week") or 0), reverse=True)
    totals = {f"{k}.{c[0]}": value(sport, c[3], summed, played) for k, _, cols in groups for c in cols}
    per_game = {f"{k}.{c[0]}": (round(summed[_first_key(summed, c[3][1:])] / played, 1)
                                if c[3][0] == "sum" and played and _first_key(summed, c[3][1:]) else None)
                for k, _, cols in groups for c in cols}
    last = max(games.values(), key=lambda g: g["period"])
    return {"sport": sport, "player": player, "season": season, "seasons": seasons,
            "team": last["team"] or "", "position": last["position"] or "",
            "groups": [{"key": k, "title": t, "cols": [{"key": c[0], "label": c[1], "title": c[2]} for c in cols]}
                       for k, t, cols in groups],
            "games": out_games, "played": played, "totals": totals, "per_game": per_game}


def _first_key(s: dict, markets) -> str | None:
    for m in markets:
        if m in s:
            return m
    return None
