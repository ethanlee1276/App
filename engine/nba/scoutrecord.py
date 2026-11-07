"""Each settled NBA Most Likely pick's scout situation, rebuilt from the box's
own stored games — so the graded record can say which flags cost us.

The football scout's corrections learn from the record (engine/likelyctx): a
flag lowers a chance only once picks carrying it have hit less often than we
said, on games the fit never saw. The NBA's flags (engine/nba/scout) reached
the cards on 2026-11-04, measured on two seasons of box scores. This hands
the same record-learning OUR NBA picks, each with the situation it was taken
in, so the measurement that put a flag on the card keeps being checked
against the bets themselves, and a flag the record proves gets a number.

WHAT WAS KNOWN BEFORE THE GAME, read the way the board reads it
(nba_build.scout_context, from nba_build.player_history's twenty games):

  starter          he started his newest game before the day
  values, minutes  his last ten in the market and in minutes, newest first,
                   for the club he played for that night (a trade resets
                   the sample, as the board's roster rule does)
  games_season     his games for that club this season
  missed_last      he did not play the club's previous game
  rest             the club's schedule over the six days before
                   (nba_build.rest_from's names)
  mate_out         a regular teammate (24+ minutes a game over his last
                   ten) who played in one of the club's last three games
                   did not play that night
  mate_back        a regular teammate back from missing the club's last two
                   or more games played that night
  spread, total    the books' last numbers before the start, where a build
                   stored them (engine/lineledger; the NBA build from
                   2026-11-04 on) — None before, and a flag that needs one
                   does not fire

TWO READS ARE AFTER THE FACT, and said so. The board reads "sits tonight" off
the injury report and "back tonight" off the books pricing him; the record
reads both off who played. A late scratch counts here and did not on the
board. The lab measured the flags the same after-the-fact way
(docs/NBA_LAB.md, "The scout"), so the record and the lab agree on what a
flag meant.

THREE READS OF THE HISTORY DATABASE, whatever the number of picks: the
league's games, every man's games, and the stored game lines, from about a
season before the first pick. The settle loop's board learning runs this
every few hours on a one-CPU box; a query per pick would not do.

Standard library only. Never writes.
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict

from . import scout as SC
from .minutes import RETURN_MISSED, RETURN_REGULAR_MIN

#: The stored columns a pick can read: minutes, and every market's parts.
COLUMNS = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
#: Summed markets and their parts (engine/hoops.SUMS).
SUMS = {"pra": ("pts", "reb", "ast"), "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"),
        "reb_ast": ("reb", "ast")}
#: Counts a box score did not always store (engine/hoops.COUNTS): a game
#: without the row is not a zero, so the run of his newest games carrying it
#: is all a count reads (engine/hoops.carried).
COUNTS = ("stl", "blk", "tov")
#: nba_build.player_history keeps his newest twenty games.
HISTORY_GAMES = 20
#: nba_build.NEW_ABSENCE_GAMES: an absence counts for a man who played in one
#: of his club's last three games (tests pin the two equal).
NEW_ABSENCE_GAMES = 3
#: How far before the first pick the read starts: a man's twenty games on
#: opening night run back into last season.
LOOKBACK_DAYS = 400
#: The book whose game lines the builds store (engine/lineledger.BEST_BOOK).
BOOK = "best"


def _canon(team) -> str:
    from engine import divisions
    return divisions.canonical("nba", str(team or ""))


def _day(value) -> str:
    return str(value or "")[:10]


def rest_label(played: set) -> str:
    """nba_build.rest_from, kept here so the engine never imports a build
    script: the club played ``played`` days before (1 = the night before,
    up to 6). Tests pin the two equal on every schedule."""
    in_4 = sum(1 for o in played if o <= 3)
    in_6 = sum(1 for o in played if o <= 5)
    if 1 in played:
        return "3in4" if in_4 >= 2 else "b2b_home"
    if in_6 >= 3:
        return "4in6_road"
    if not played:
        return "2plus"
    return "1day"


def _eastern_day(stamp: str) -> str:
    """The US Eastern calendar day of a UTC stamp: a 10 p.m. Eastern tip is
    the next day in UTC, and the game's day is the Eastern one."""
    try:
        t = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return ""
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                         # noqa: BLE001 — no tz data
        return (t - _dt.timedelta(hours=5)).date().isoformat()


def load(hist, first_day: str, sport: str = "nba") -> dict:
    """Everything `context` reads, from three queries.

    ``{"games": {player: {day: {"team", "start", column: value}}},
       "club_days": {club: [days, oldest first]},
       "played": {(club, day): {men who logged minutes}},
       "matchups": {(club, day): "AWAY@HOME"},
       "lines": {(club, day): {"spread": his club's, "total": the game's}}}``"""
    try:
        lo = (_dt.date.fromisoformat(_day(first_day)) - _dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    except ValueError:
        lo = "0000-00-00"
    club_days: dict = defaultdict(set)
    matchups: dict = {}
    # Columns by position throughout: a caller's connection may or may not
    # hand back named rows.
    try:
        found = hist.execute("SELECT period, home, away FROM games WHERE sport=? AND period >= ?",
                             (sport, lo)).fetchall()
    except Exception:                                         # noqa: BLE001 — no games table
        found = []
    for period, home, away in found:
        d, home, away = _day(period), _canon(home), _canon(away)
        club_days[home].add(d)
        club_days[away].add(d)
        matchups[(home, d)] = matchups[(away, d)] = f"{away}@{home}"
    games: dict = defaultdict(dict)
    marks = ",".join("?" * len(COLUMNS))
    try:
        rows = hist.execute(
            "SELECT player, period, team, position, market, value FROM player_game_logs "
            f"WHERE sport=? AND period >= ? AND market IN ({marks})", (sport, lo, *COLUMNS)).fetchall()
    except Exception:                                         # noqa: BLE001 — no logs table
        rows = []
    for player, period, team, position, market, value in rows:
        g = games[player].setdefault(_day(period), {"team": _canon(team)})
        g[market] = float(value or 0.0)
        if market == "min":
            g["start"] = str(position or "") == "S"
    played: dict = defaultdict(set)
    members: dict = defaultdict(set)
    for name, mine in games.items():
        for d, g in mine.items():
            # A club game none of the games rows hold still happened.
            club_days[g["team"]].add(d)
            members[g["team"]].add(name)
            if float(g.get("min", 1.0) or 0.0) > 0:
                played[(g["team"], d)].add(name)
    lines: dict = {}
    try:
        snaps = hist.execute(
            "SELECT taken_at, event_id, home, away, market, line, commence_time FROM odds_history "
            "WHERE sport=? AND book=? AND market IN ('spread','total') AND taken_at >= ? "
            "ORDER BY taken_at", (sport, BOOK, lo)).fetchall()
    except Exception:                                         # noqa: BLE001 — no odds table
        snaps = []
    for taken, eid, home, away, market, line, start in snaps:  # oldest first: the last one stands
        start = str(start or "")
        if start and str(taken or "") >= start:
            continue                                          # in play: not a pre-game number
        if line is None:
            continue
        eid = str(eid or "")
        d = eid[:10] if eid[:4].isdigit() and eid[4:5] == "-" else _eastern_day(start)
        if not d:
            continue
        home, away = _canon(home), _canon(away)
        mine, theirs = lines.setdefault((home, d), {}), lines.setdefault((away, d), {})
        if market == "spread":                                # stored as the HOME club's number
            mine["spread"], theirs["spread"] = float(line), -float(line)
        else:
            mine["total"] = theirs["total"] = float(line)
    return {"games": dict(games), "club_days": {t: sorted(ds) for t, ds in club_days.items()},
            "played": dict(played), "members": dict(members), "matchups": matchups, "lines": lines,
            "news": {}}


def _value(g: dict, market: str):
    if market in SUMS:
        return round(sum(float(g.get(p, 0.0) or 0.0) for p in SUMS[market]), 1)
    return float(g.get(market, 0.0) or 0.0)


def _series(rows: list[dict], market: str) -> list[float]:
    """His values in the market, newest first, as the board's history holds
    them: a count reads only the run of newest games that stored it."""
    if market in COUNTS:
        out = []
        for g in rows:
            if market not in g:
                break
            out.append(float(g[market] or 0.0))
        return out
    return [_value(g, market) for g in rows]


def _missed(days_before: list, played: set):
    """nba_build.return_read's first half: how many of the club's games in a
    row, newest back, he missed (None when he played none of them)."""
    n = 0
    for d in days_before:
        if d in played:
            return n
        n += 1
    return None


def _usual(mine: dict, team: str, day: str) -> tuple:
    """``(his average minutes, games)`` over his last ten for the club before
    ``day`` — the ten nba_build.absences and nba_build.returning both read."""
    mins = [float(mine[d].get("min", 0.0) or 0.0)
            for d in sorted((d for d in mine if d < day and mine[d].get("team") == team), reverse=True)[:10]]
    return (sum(mins) / len(mins) if mins else 0.0), len(mins)


def news(team: str, day: str, prior: list, data: dict) -> tuple:
    """``(regulars who sat, regulars back)`` on one club-night, as two sets of
    names, or ``(None, None)`` where the night's box is not stored. Once per
    club-night: every pick from that game reads the same two sets.

    SAT (nba_build.absences): 24+ minutes a game over his last ten, logged
    for the club in one of its last three games, and no minutes that night.
    BACK (nba_build.returning): 24+ over his last ten on three games or more,
    had missed the club's last two or more, and played that night."""
    cache = data.setdefault("news", {})
    if (team, day) in cache:
        return cache[(team, day)]
    played = data.get("played") or {}
    there = played.get((team, day)) or set()
    if not there:
        cache[(team, day)] = (None, None)
        return cache[(team, day)]
    recent = set(prior[:NEW_ABSENCE_GAMES])
    sat, back = set(), set()
    games = data.get("games") or {}
    for other in (data.get("members") or {}).get(team) or ():
        theirs = games.get(other) or {}
        avg, n = _usual(theirs, team, day)
        if avg < RETURN_REGULAR_MIN:
            continue
        if other not in there:
            if any(d in theirs and theirs[d].get("team") == team for d in recent):
                sat.add(other)
        elif n >= 3:
            ours = {d for d in theirs if d < day and theirs[d].get("team") == team
                    and float(theirs[d].get("min", 1.0) or 0.0) > 0}
            gone = _missed(prior, ours)
            if gone is not None and gone >= RETURN_MISSED:
                back.add(other)
    cache[(team, day)] = (sat, back)
    return sat, back


def context(pick: dict, data: dict) -> dict | None:
    """The scout's side-free facts for one settled pick (the keys
    nba_build.scout_context writes), plus ``team`` and ``game_id``; None
    when his game or his history cannot be found."""
    day = _day(pick.get("day") or pick.get("game_day") or pick.get("date"))
    name = pick.get("player") or ""
    mine = (data.get("games") or {}).get(name) or {}
    if not day or not mine:
        return None
    tonight = mine.get(day)
    team = (tonight or {}).get("team") or _canon(pick.get("team"))
    if not team:
        older = sorted((d for d in mine if d < day), reverse=True)
        team = mine[older[0]]["team"] if older else ""
    before = sorted((d for d in mine if d < day and mine[d].get("team") == team), reverse=True)[:HISTORY_GAMES]
    if not team or not before:
        return None
    rows = [mine[d] for d in before]
    from . import window as _w
    from ..seasons import season_of
    try:
        games_season = _w.this_season(before, "nba", season_of("nba", day))
    except (ValueError, TypeError):
        games_season = None
    days = data.get("club_days", {}).get(team) or []
    prior = [d for d in reversed(days) if d < day]            # newest first
    mine_played = {d for d in before if float(mine[d].get("min", 1.0) or 0.0) > 0}
    missed = _missed(prior, mine_played)
    try:
        d0 = _dt.date.fromisoformat(day)
        seen = set(days)
        rest = rest_label({o for o in range(1, 7) if (d0 - _dt.timedelta(days=o)).isoformat() in seen})
    except ValueError:
        rest = None
    # WHO SAT AND WHO CAME BACK, read off who played — only where the night's
    # box is stored at all, or every regular on the club would read as out.
    sat, back = news(team, day, prior, data)
    mate_out = None if sat is None else bool(sat - {name})
    mate_back = None if back is None else bool(back - {name})
    line = (data.get("lines") or {}).get((team, day)) or {}
    return {"starter": bool(rows[0].get("start")), "spread": line.get("spread"), "total": line.get("total"),
            "rest": rest, "values": _series(rows, pick.get("market") or "")[:10],
            "minutes": [float(g.get("min", 0.0) or 0.0) for g in rows][:10],
            "games_season": games_season, "missed_last": bool(missed),
            "mate_out": mate_out, "mate_back": mate_back,
            "team": team, "game_id": f"{day}|{(data.get('matchups') or {}).get((team, day)) or team}"}


def flagged(rows: list[dict], hist, sport: str = "nba") -> list[dict]:
    """``rows`` (engine/likelyctx.journal) with ``ctx`` and ``flags`` — every
    flag the pick raised, measured or not (engine/nba/scout.every) — on
    each."""
    days = [_day(r.get("day") or r.get("game_day") or r.get("date")) for r in rows]
    days = [d for d in days if d]
    data = load(hist, min(days), sport) if days else {}
    for r in rows:
        ctx = context(r, data) if data else None
        r["ctx"] = ctx
        r["flags"] = SC.every(ctx, r.get("market") or "", str(r.get("side") or ""), r.get("line")) if ctx else []
    return rows
