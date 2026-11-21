"""Every MLB player's full line, game by game, from each final game's box score
(2026-11-17).

Ethan, asked whether the MLB player pages should carry the full batting and
pitching lines now or before spring: "yes build it all". The history held six
numbers a game, the ones the props grade (plate appearances, hits, total
bases, home runs; a pitcher's outs and strikeouts), and only for a player with
a prop that day, because the nightly read each priced player's own game log
(engine/ingest.ingest_mlb_date). A page needs the line a box score prints:

  batting   AB, R, H, 2B, 3B, HR, RBI, BB, SO, SB, HBP, SF, PA (and TB)
  pitching  IP (as outs), H, R, ER, BB, SO, HR, batters faced, pitches,
            and the win, loss or save

and for everyone who played, priced or not.

ONE REQUEST A GAME. Each final game's box score (statsapi's /game/{pk}/
boxscore, the one engine/mlb/livestats.box_rows already reads for the Live
tab) carries every player's line, so a night is about fifteen requests and a
season about 2,430: a box score a game, never a request a player.

NEVER A NUMBER THE RECORD GRADED. A row already in the history (the same
player, game and stat) is left exactly as it is: the full line only adds the
numbers and the players that were missing (`write`: INSERT OR IGNORE). A
batter's strikeouts are `batter_strikeouts`, because `strikeouts` is the
pitcher's (a two-way player has both).

ONE GAME, ONE KEY. A game is keyed as the nightly keys it from the player's
own game log: ``{player}-{date}``, and ``-G2`` for the second game that player
played that day (`rows`). So the whole line lands on the graded rows' own
game, and a doubleheader's second game is one game for a player who sat out
the first, not two. A day is read whole or left for the next read.

The nightly MLB ingest adds each final game's lines (engine/ingest.
ingest_mlb_date), and the nightly chores (engine/maintenance) read a season
not yet whole about FILL_PER_NIGHT games a night, newest first (`nightly`),
so a season played before the full lines were kept fills by itself. The
command does a season at once:

    python3 -m engine.mlb.fulllines --season 2026

which reads the season's schedule in one request and every final regular-
season and postseason game's box score (spring training, exhibitions and the
All-Star Game are no player's line). Standard library only.
"""
from __future__ import annotations

import json
import time
import urllib.request

#: A box score's batting numbers, and the market each is kept under.
BAT = (("atBats", "at_bats"), ("runs", "runs"), ("hits", "hits"), ("doubles", "doubles"),
       ("triples", "triples"), ("homeRuns", "home_runs"), ("rbi", "rbis"), ("baseOnBalls", "walks"),
       ("strikeOuts", "batter_strikeouts"), ("stolenBases", "stolen_bases"), ("hitByPitch", "hbp"),
       ("sacFlies", "sac_flies"), ("plateAppearances", "pa"))
#: …and its pitching numbers (innings are kept as outs, as the props keep them).
PIT = (("hits", "hits_allowed"), ("runs", "runs_allowed"), ("earnedRuns", "earned_runs"),
       ("baseOnBalls", "walks_allowed"), ("strikeOuts", "strikeouts"), ("homeRuns", "home_runs_allowed"),
       ("battersFaced", "batters_faced"), ("numberOfPitches", "pitches"), ("wins", "wins"),
       ("losses", "losses"), ("saves", "saves"))
#: The games a line is kept for: the regular season and the four postseason rounds.
GAME_TYPES = ("R", "F", "D", "L", "W")
#: Seconds between box scores on a backfill, as the other statsapi readers pace.
PAUSE_S = 0.25
#: Box scores the nightly chores read a night for a season not yet whole
#: (`nightly`): about three minutes of requests, a season in about twelve nights.
FILL_PER_NIGHT = 200


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _outs(ip) -> float | None:
    """Innings pitched as outs: "6.1" is 19."""
    try:
        whole, _, part = str(ip).partition(".")
        return float(int(whole or 0) * 3 + int(part or 0))
    except ValueError:
        return None


def player_lines(box: dict) -> dict:
    """``{side: [(name, position, {market: value})]}``: each player's full
    line off a box score, batting and pitching, for everyone who played."""
    out: dict = {}
    for side in ("home", "away"):
        players = ((box or {}).get("teams") or {}).get(side, {}).get("players") or {}
        for p in players.values():
            name = ((p.get("person") or {}).get("fullName")) or ""
            if not name:
                continue
            stats = p.get("stats") or {}
            bat, pit = stats.get("batting") or {}, stats.get("pitching") or {}
            line: dict = {}
            # A batter who came to the plate, or ran: a pinch runner who scored has a line too.
            if bat and (_num(bat.get("plateAppearances")) or any(_num(bat.get(k)) for k, _ in BAT)):
                for key, market in BAT:
                    v = _num(bat.get(key))
                    if v is not None:
                        line[market] = v
                h, d2, t3, hr = (line.get(m, 0.0) for m in ("hits", "doubles", "triples", "home_runs"))
                line["total_bases"] = h + d2 + 2 * t3 + 3 * hr
            # A pitcher who faced a batter (an out or not).
            if pit and (_num(pit.get("battersFaced")) or pit.get("inningsPitched") not in (None, "", "0.0")):
                outs = _outs(pit.get("inningsPitched"))
                if outs is not None:
                    line["outs"] = outs
                for key, market in PIT:
                    v = _num(pit.get(key))
                    if v is not None:
                        line[market] = v
            if line:
                # The box score's position is the one played that game: a pinch
                # hitter's or runner's says nothing of where they play, so none.
                pos = str(((p.get("position") or {}).get("abbreviation")) or "")
                out.setdefault(side, []).append((name, "" if pos in ("PH", "PR") else pos, line))
    return out


def rows(box: dict, home: str, away: str, date: str, legs: dict | None = None) -> list[dict]:
    """The box score as history rows (`player_game_logs`), one a player and
    stat. A game is keyed as the nightly keys it from the player's own game
    log (engine/ingest.mlb_rows_from_slate): ``{player}-{date}``, and
    ``-G2`` for the second game the player played that day. So a player who
    sat out a doubleheader's first game keys the second as the first, as the
    game log does, and it is one game, not two: ``legs`` counts each player's
    games so far that day, carried across the day's games in the order played."""
    legs = {} if legs is None else legs
    out = []
    season = int(str(date)[:4])
    for side, lines in player_lines(box).items():
        team, opp = (home, away) if side == "home" else (away, home)
        for name, pos, line in lines:
            leg = legs[name] = legs.get(name, 0) + 1
            gid = f"{name}-{date}" + (f"-G{leg}" if leg > 1 else "")
            for market, value in line.items():
                out.append({"sport": "mlb", "season": season, "period": str(date)[:10], "game_id": gid,
                            "player": name, "team": team, "opponent": opp, "position": pos,
                            "home": 1 if side == "home" else 0, "market": market, "value": value})
    return out


def write(conn, rws: list[dict]) -> int:
    """Add the rows the history does not hold; a row it holds is left as it is
    (the record graded on it). Returns the rows added."""
    if not rws:
        return 0
    from ..db import LOG_COLS
    # The statement's own count: the table's trigger (db.log_generations) adds changes of its own.
    cur = conn.executemany(f"INSERT OR IGNORE INTO player_game_logs ({', '.join(LOG_COLS)}) "
                           f"VALUES ({', '.join('?' * len(LOG_COLS))})",
                           [tuple(r.get(c) for c in LOG_COLS) for r in rws])
    conn.commit()
    return max(0, cur.rowcount)


def games_of(schedule: dict) -> list[dict]:
    """``[{pk, date, home, away, game_number}]``: every final regular-season and
    postseason game in a statsapi schedule payload."""
    from .sources.mlbstats import TEAM_ID_ABBR
    out, seen = [], set()
    for day in (schedule or {}).get("dates") or []:
        for g in day.get("games") or []:
            st = g.get("status") or {}
            if st.get("abstractGameState") != "Final" or str(g.get("gameType") or "R") not in GAME_TYPES:
                continue
            teams = g.get("teams") or {}
            h, a = (teams.get("home") or {}).get("team") or {}, (teams.get("away") or {}).get("team") or {}
            home = TEAM_ID_ABBR.get(h.get("id"), h.get("abbreviation", ""))
            away = TEAM_ID_ABBR.get(a.get("id"), a.get("abbreviation", ""))
            pk = g.get("gamePk")
            # A suspended game finished another day is on the schedule twice; it is one game.
            if pk and home and away and int(pk) not in seen:
                seen.add(int(pk))
                out.append({"pk": int(pk), "date": str(g.get("officialDate") or day.get("date") or "")[:10],
                            "home": home, "away": away, "game_number": int(g.get("gameNumber") or 1)})
    return out


def done_teams(conn, date: str) -> set:
    """The clubs whose whole lines for a day the history holds already: a
    hitter's at-bats are on file (the props' rows never carry them)."""
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT team FROM player_game_logs WHERE sport='mlb' AND season=? AND period=? AND market='at_bats'",
        (int(str(date)[:4]), str(date)[:10]))}


def slate_rows(slate, date: str, fetch=None, done=frozenset()) -> list[dict]:
    """The nightly's share: every final game on a slate, its box score's full
    lines, the day's games in the order played (engine/ingest.ingest_mlb_date).
    One box score that cannot be read leaves the day for the next read: a
    doubleheader's second game, read without its first, would key the
    players in both as their first game.

    A game whose clubs' lines are kept already (``done``, `done_teams`) is not
    read again: the settle pass reads an open day several times a game day,
    and each read would fetch the day's fifteen box scores anew. A
    doubleheader's clubs are read whole each time (their games key together)."""
    from collections import Counter
    from ..ingest import _game_state
    if fetch is None:
        from .sources.statslogs import fetch_boxscore as fetch
    finals = sorted((g for g in getattr(slate, "games", []) or []
                     if str(_game_state(g)).lower() == "final" and getattr(g, "game_pk", 0)),
                    key=lambda g: int(getattr(g, "game_number", 1) or 1))
    games = Counter(t for g in getattr(slate, "games", []) or [] for t in (g.home, g.away))
    finals = [g for g in finals
              if not (g.home in done and g.away in done and games[g.home] == 1 and games[g.away] == 1)]
    boxes = [(fetch(int(g.game_pk)), g) for g in finals]
    legs: dict = {}
    out = []
    for box, g in boxes:
        out += rows(box, g.home, g.away, date, legs)
    return out


def box_uncached(game_pk: int, timeout: int = 30) -> dict:
    """A box score read for the season's fill, not kept: statsapi's reader
    caches each one (statslogs.fetch_boxscore), and a season's 2,430 of them
    would be a few hundred megabytes on the box for one read each."""
    from ..sources.fetch import USER_AGENT
    from .sources.mlbstats import STATS_BASE
    req = urllib.request.Request(f"{STATS_BASE}/game/{int(game_pk)}/boxscore", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _by_day(games: list[dict]) -> dict:
    days: dict = {}
    for g in games:
        days.setdefault(g["date"], []).append(g)
    return days


def _fill(conn, days: dict, fetch_box, log, pause: float) -> dict:
    """``days`` ({day: [game]}) into the history, a day whole or not at all:
    a day with a box score that cannot be read is left for the next run."""
    added = failed = read = 0
    for day in sorted(days, reverse=True):
        boxes, broken = [], False
        for g in sorted(days[day], key=lambda g: g["game_number"]):
            try:
                boxes.append((fetch_box(g["pk"]), g))
            except Exception as exc:                         # noqa: BLE001 (one box score is not the season)
                broken = True
                log(f"  {g['date']} {g['away']}@{g['home']}: {type(exc).__name__}: {exc}")
            if pause:
                time.sleep(pause)
        if broken:
            failed += len(days[day])
            log(f"  {day} left for the next run: a box score could not be read")
            continue
        legs: dict = {}
        added += write(conn, [r for box, g in boxes for r in rows(box, g["home"], g["away"], day, legs)])
        before, read = read, read + len(days[day])
        if read // 100 > before // 100:
            log(f"  {read} games read, {added} numbers added")
    return {"games": read, "added": added, "failed": failed}


def backfill(conn, season: int, start: str | None = None, end: str | None = None, fetch_box=None,
             fetch_schedule=None, log=print, pause: float = PAUSE_S) -> dict:
    """Every final game of a season (or a stretch of it), its box score's full
    lines into the history. One schedule request, then a box score a game, a
    day at a time, newest first: a day with a box score that cannot be read is
    left whole for the next run (the command can be run again; what is kept
    stays)."""
    if fetch_schedule is None:
        from .sources.mlbstats import fetch_schedule
    start, end = start or f"{season}-03-01", end or f"{season}-11-30"
    games = games_of(fetch_schedule(start, end))
    out = _fill(conn, _by_day(games), fetch_box or box_uncached, log, pause)
    return {"games": len(games), "added": out["added"], "failed": out["failed"]}


def filled(conn, season: int) -> dict:
    """``{(day, club): second game kept}`` for each club's days whose whole
    lines the history holds (a hitter's at-bats), and whether a second game
    that day is (a doubleheader's ``-G2``)."""
    return {(str(day)[:10], team): bool(second) for day, team, second in conn.execute(
        "SELECT period, team, MAX(game_id LIKE '%-G2') FROM player_game_logs "
        "WHERE sport='mlb' AND market='at_bats' AND season=? GROUP BY period, team", (int(season),))}


def _day_done(day: str, games: list, have: dict) -> bool:
    from collections import Counter
    count = Counter(t for g in games for t in (g["home"], g["away"]))
    return all((day, t) in have and (n == 1 or have[(day, t)]) for t, n in count.items())


def nightly(conn, season: int, through: str, budget: int = FILL_PER_NIGHT, fetch_box=None, fetch_schedule=None,
            log=print, pause: float = PAUSE_S) -> dict:
    """The season's final games whose whole lines the history lacks, newest
    day first, about ``budget`` games a night (engine/maintenance's chores),
    until none are left: a season played before the full lines were kept
    fills by itself, and a night whose read missed a box score is mended.
    The schedule is the one the hit tracker's backfill reads the same night
    (statsapi's, cached for the day)."""
    if fetch_schedule is None:
        from .sources.mlbstats import fetch_schedule
    days = _by_day(games_of(fetch_schedule(f"{int(season)}-03-01", through)))
    have = filled(conn, season)
    todo = sorted((d for d in days if not _day_done(d, days[d], have)), reverse=True)
    picked, n = {}, 0
    for d in todo:
        if picked and n + len(days[d]) > budget:
            break
        picked[d] = days[d]
        n += len(days[d])
    out = _fill(conn, picked, fetch_box or box_uncached, log, pause)
    out["left"] = sum(len(days[d]) for d in todo) - out["games"]
    return out


def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Fill MLB players' full batting and pitching lines from box scores.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--start", help="first date (YYYY-MM-DD); the season's start by default")
    ap.add_argument("--end", help="last date (YYYY-MM-DD); the season's end by default")
    a = ap.parse_args(argv)
    from .. import db as _db
    conn = _db.connect(_db.DEFAULT_DB)
    try:
        out = backfill(conn, a.season, a.start, a.end)
    finally:
        conn.close()
    print(f"{out['games']} final games read, {out['added']} numbers added to the history"
          + (f", {out['failed']} box scores could not be read" if out["failed"] else ""))
    return 0 if not out["failed"] or out["added"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
