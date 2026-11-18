"""The NBA's and the WNBA's stored seasons, without their preseason (2026-11-18, walk 11).

    python3 -m engine.hoopspreseason                 # what it would move; writes nothing
    python3 -m engine.hoopspreseason --apply         # move it
    python3 -m engine.hoopspreseason --league nba    # one league (default: both)

The Cavaliers' team page ranked them "6 of 36" for 2025–26 at 61-43: thirty
clubs and six All-Star sides (engine/hoopsexhibitions removes those), and a
season of 104 games, which was 82, eighteen in the playoffs and four in the
preseason (7, 9, 12 and 14 October 2025: the Bulls twice, the Celtics and the
Pistons). Every NBA season stored before 24 September 2026 holds its preseason,
four or five games a club and one against Maccabi Ra'anana in 2023: the history
backfill read ESPN's scoreboard day by day from 1 October, and the scoreboard
lists the preseason on those days. The nightly has skipped it since
(sources/espnhoops.ingest_day: "never a result, never a player's form"); the
WNBA's 2026 season was stored before that too. A preseason box score is starters
on half minutes, and it sat in every average, form window, hit rate and learner
that reads a player's season, and in a club's season record and ranks.

THIS MOVES WHAT WAS STORED. For each stored season it reads ESPN's own
scoreboard again for every day in the season's first weeks that holds a stored
game, and takes the games it calls preseason (season type 1); nothing is
guessed from a date. A game's row and its stat lines go to the preseason tables
the NFL's already use (`preseason_games`, `preseason_player_logs`: out of every
reader's way, and kept), and its shots and opening tip are dropped. It lists
each game first; nothing is written without ``--apply``, and a day the
scoreboard did not answer is named and left alone.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from . import db as _db
from . import seasons as _seasons

LEAGUES = ("nba", "wnba")

#: How far into a season's window its preseason can reach. The NBA's window
#: opens on 1 October and its preseason is over by the third week; the WNBA's
#: opens on 25 April with two to three weeks of it.
SCAN_DAYS = 40


def _scoreboard(league: str):
    """The day's games off ESPN's scoreboard, each with its `preseason` flag."""
    from .sources import espnhoops
    return lambda day: espnhoops.load_day(day, league=league)


def season_days(conn, league: str, season: int) -> list[str]:
    """The days in a season's first `SCAN_DAYS` that hold a stored game: the only days worth asking about."""
    try:
        start = _seasons.window(league, int(season))[0]
    except ValueError:
        return []
    end = (_dt.date.fromisoformat(start) + _dt.timedelta(days=SCAN_DAYS)).isoformat()
    rows = conn.execute("SELECT DISTINCT substr(period, 1, 10) FROM games WHERE sport=? AND season=? "
                        "AND period >= ? AND period < ? ORDER BY 1", (league, int(season), start, end)).fetchall()
    return [str(r[0]) for r in rows if r[0]]


def found(conn, league: str, load=None) -> dict:
    """{"games": [{game_id, season, day, home, away, rows}], "rows": n, "unread": [days]} for one league:
    every stored game the scoreboard calls preseason, oldest first."""
    load = load or _scoreboard(league)
    seasons = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM games WHERE sport=? AND season IS NOT NULL ORDER BY season", (league,))]
    games, unread = [], []
    for season in seasons:
        for day in season_days(conn, league, season):
            try:
                listed = load(day) or []
            except Exception as exc:                          # noqa: BLE001
                unread.append(f"{day}: {exc}")
                continue
            for g in listed:
                if not g.get("preseason"):
                    continue
                gid = str(g.get("game_id") or "")
                row = conn.execute("SELECT season, period, home, away FROM games WHERE sport=? AND game_id=?",
                                   (league, gid)).fetchone() if gid else None
                if not row:
                    continue
                lines = conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport=? AND game_id=?",
                                     (league, gid)).fetchone()[0]
                games.append({"game_id": gid, "season": int(row[0]), "day": str(row[1])[:10],
                              "home": row[2], "away": row[3], "rows": int(lines)})
    games.sort(key=lambda g: (g["day"], g["game_id"]))
    return {"games": games, "rows": sum(g["rows"] for g in games), "unread": unread}


def apply(conn, league: str, report: dict) -> dict:
    """Move the listed games to the preseason tables. Returns what moved and what was dropped."""
    out = {"games": 0, "lines": 0, "shots": 0, "tips": 0}
    for g in report["games"]:
        gid = g["game_id"]
        for season, period, home, away, hs, as_ in conn.execute(
                "SELECT season, period, home, away, home_score, away_score FROM games WHERE sport=? AND game_id=?",
                (league, gid)).fetchall():
            conn.execute("INSERT OR REPLACE INTO preseason_games (sport, season, week, game_id, date, home, away, "
                         "home_score, away_score, completed, venue) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (league, season, 0, gid, str(period)[:10], home, away, hs, as_,
                          int(hs is not None and as_ is not None), ""))
        out["games"] += conn.execute("DELETE FROM games WHERE sport=? AND game_id=?", (league, gid)).rowcount
        conn.execute("INSERT OR REPLACE INTO preseason_player_logs (sport, season, week, game_id, player, team, "
                     "opponent, position, home, market, value) SELECT sport, season, 0, game_id, player, team, "
                     "opponent, position, home, market, value FROM player_game_logs WHERE sport=? AND game_id=?",
                     (league, gid))
        out["lines"] += conn.execute("DELETE FROM player_game_logs WHERE sport=? AND game_id=?",
                                     (league, gid)).rowcount
        if league == "nba":
            out["shots"] += conn.execute("DELETE FROM nba_shots WHERE game_id=?", (gid,)).rowcount
            out["tips"] += conn.execute("DELETE FROM nba_tips WHERE game_id=?", (gid,)).rowcount
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.hoopspreseason",
                                 description="List (and with --apply, move to the preseason tables) the NBA's "
                                             "and the WNBA's stored preseason games.")
    ap.add_argument("--league", choices=LEAGUES, action="append", help="one league (repeatable); default both")
    ap.add_argument("--apply", action="store_true", help="move them (without it, nothing is written)")
    a = ap.parse_args(argv)
    conn = _db.connect()
    try:
        for league in a.league or LEAGUES:
            rep = found(conn, league)
            by = {}
            for g in rep["games"]:
                by[g["season"]] = by.get(g["season"], 0) + 1
            print(f"{league.upper()}: {len(rep['games'])} stored preseason game(s), {rep['rows']:,} stat line(s)"
                  + (" — " + ", ".join(f"{s}: {n}" for s, n in sorted(by.items())) if by else ""))
            for g in rep["games"][:40]:
                print(f"  {g['day']}  {g['away']} at {g['home']}  ({g['rows']} line(s), game {g['game_id']})")
            if len(rep["games"]) > 40:
                print(f"  … and {len(rep['games']) - 40} more")
            for u in rep["unread"][:10]:
                print(f"  not read, left alone: {u}")
            if a.apply and rep["games"]:
                moved = apply(conn, league, rep)
                print(f"  moved {moved['games']} game(s) and {moved['lines']:,} stat line(s) to the preseason "
                      f"tables; dropped {moved['shots']:,} shot(s) and {moved['tips']} opening tip(s)")
        if not a.apply:
            print("\nNothing written. Run again with --apply to move them; the next build and the night's refit "
                  "read the seasons without them.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
