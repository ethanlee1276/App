"""The NBA's and the WNBA's stored games, league games only (2026-11-17).

    python3 -m engine.hoopsexhibitions                 # what it would remove; writes nothing
    python3 -m engine.hoopsexhibitions --apply         # remove it
    python3 -m engine.hoopsexhibitions --league wnba   # one league (default: both)

Checking the live player pages, Caitlin Clark's 2026 WNBA game log held 47
games and two clubs, and two of the games were no league's: the All-Star Game
(25 July, filed as "SPO" against "COOP", 129-122) and an exhibition against
Nigeria's national team (2 May, 105-57). ESPN files both as games of the
season, so the nightly kept their box scores, and every number read off a
player's games counted them: the page's averages and places, the boards' form
and hit rates, the Game Log. The live logs show every WNBA All-Star Game since
2023 and exhibitions against Puerto Rico and Japan's Toyota Antelopes, and the
NBA's All-Star games too (2025's tournament: CHK, KEN, SHQ and the Rising
Stars' CAN; 2026's WORLD, STARS and STRIPES), mini-games that sit in the NBA's
season-to-season rates.

The writer is fixed where it writes (sources/espnhoops.ingest_day stores a
pro league's game only when both sides are the league's own clubs, by the
division tables engine/divisions keeps, and says what it left out). THIS
REMOVES WHAT IT LEFT: every stored stat line and games row of the two leagues
with a side that is not one of the league's clubs, under any of the spellings
the feeds use (divisions.canonical). It lists each game first (the day, the
two sides, how many players' lines); nothing is written without ``--apply``.

A club that joins a league goes into engine/divisions first (the standings
need it there too): until it does, its games would read as no league's, and
this lists them rather than removing them unseen.
"""

from __future__ import annotations

import argparse
import sys

from . import db as _db
from . import divisions as _divisions

LEAGUES = ("nba", "wnba")


def is_club(league: str, team: str) -> bool:
    """Whether ``team`` (any of the feeds' spellings) is one of the league's own clubs."""
    return _divisions.canonical(league, team) in _divisions.MAPS.get(league, {})


def league_game(league: str, home: str, away: str) -> bool:
    """Both sides the league's own clubs: not an All-Star Game, not an exhibition against a national team."""
    return is_club(league, home) and is_club(league, away)


def found(conn, league: str) -> dict:
    """{"games": [{game_id, day, home, away, players, rows}], "rows": n, "game_rows": n} for one league:
    every stored game with a side that is not one of its clubs, newest first."""
    seen: dict = {}
    for gid, day, team, opp, players, rows in conn.execute(
            "SELECT game_id, MIN(period), team, opponent, COUNT(DISTINCT player), COUNT(*) FROM player_game_logs "
            "WHERE sport=? GROUP BY game_id, team, opponent", (league,)):
        if is_club(league, team) and is_club(league, opp):
            continue
        g = seen.setdefault(str(gid), {"game_id": str(gid), "day": str(day), "sides": set(), "players": 0, "rows": 0})
        g["sides"].update(x for x in (team, opp) if x)
        g["players"] += int(players)
        g["rows"] += int(rows)
    game_rows = 0
    for gid, day, home, away in conn.execute(
            "SELECT game_id, period, home, away FROM games WHERE sport=?", (league,)):
        if league_game(league, home, away):
            continue
        game_rows += 1
        g = seen.setdefault(str(gid), {"game_id": str(gid), "day": str(day), "sides": set(), "players": 0, "rows": 0})
        g["sides"].update(x for x in (home, away) if x)
    games = sorted(({**g, "sides": sorted(g["sides"])} for g in seen.values()),
                   key=lambda g: (g["day"], g["game_id"]), reverse=True)
    return {"games": games, "rows": sum(g["rows"] for g in games), "game_rows": game_rows}


def apply(conn, league: str, report: dict) -> int:
    """Remove the listed games' stat lines and games rows. Returns the rows removed."""
    ids = [g["game_id"] for g in report["games"]]
    gone = 0
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        marks = ",".join("?" * len(chunk))
        gone += conn.execute(f"DELETE FROM player_game_logs WHERE sport=? AND game_id IN ({marks})",
                             (league, *chunk)).rowcount
        gone += conn.execute(f"DELETE FROM games WHERE sport=? AND game_id IN ({marks})",
                             (league, *chunk)).rowcount
    conn.commit()
    return gone


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.hoopsexhibitions",
                                 description="List (and with --apply, remove) the NBA's and the WNBA's stored "
                                             "All-Star and exhibition games.")
    ap.add_argument("--league", choices=LEAGUES, action="append", help="one league (repeatable); default both")
    ap.add_argument("--apply", action="store_true", help="remove them (without it, nothing is written)")
    a = ap.parse_args(argv)
    conn = _db.connect()
    removed = 0
    try:
        for league in a.league or LEAGUES:
            rep = found(conn, league)
            print(f"{league.upper()}: {len(rep['games'])} game(s) with a side that is not a {league.upper()} club, "
                  f"{rep['rows']:,} stat line(s), {rep['game_rows']} games row(s)")
            for g in rep["games"][:40]:
                print(f"  {g['day']}  {' v '.join(g['sides']) or '?'}  ({g['players']} player(s), game {g['game_id']})")
            if len(rep["games"]) > 40:
                print(f"  … and {len(rep['games']) - 40} more")
            if a.apply and rep["games"]:
                removed += apply(conn, league, rep)
    finally:
        conn.close()
    print(f"removed {removed:,} row(s)" if a.apply else "nothing written (add --apply to remove them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
