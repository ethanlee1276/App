#!/usr/bin/env python3
"""The NBA's stored games and logs, in the league's own club codes.

    cd /srv/qellys && sudo -u qellys python3 nbacodes.py            # counts, changes nothing
    cd /srv/qellys && sudo -u qellys python3 nbacodes.py --apply    # rewrites the six codes

Found 2026-10-14 (runbook step 103): ESPN, which the NBA history has been
read from all along, spells six clubs its own way — GS, NY, NO, SA, UTAH,
WSH — and the odds feed, the club rosters, the board and every NBA bet
use the league's (GSW, NYK, NOP, SAS, UTA, WAS). A stored game under "GS"
never meets a moneyline on "GSW", and a defence rated under "NY" is never
found for a player facing "NYK". New rows are stored in the league's codes
from today (`espnhoops.ingest_day`); this rewrites the rows already there.

ONLY THE HISTORY DATABASE, ONLY THE NBA, ONLY THOSE COLUMNS: `games.home`,
`games.away`, `player_game_logs.team` and `.opponent`. Neither table keys
on a club, so no row merges with another; every stat, score, date and id
stays as it is, and the journal (`ledger.db`) is not opened.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

COLUMNS = (("games", "home"), ("games", "away"),
           ("player_game_logs", "team"), ("player_game_logs", "opponent"))


def plan(conn) -> list:
    """``[(table, column, espn_code, league_code, rows)]`` for every NBA row
    still carrying one of ESPN's six spellings."""
    from engine.divisions import ALIASES
    out = []
    for table, col in COLUMNS:
        for espn, league in sorted(ALIASES["nba"].items()):
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE sport='nba' AND {col}=?",
                             (espn,)).fetchone()[0]
            if n:
                out.append((table, col, espn, league, n))
    return out


def apply(conn, rows: list) -> int:
    done = 0
    for table, col, espn, league, _ in rows:
        done += conn.execute(f"UPDATE {table} SET {col}=? WHERE sport='nba' AND {col}=?",
                             (league, espn)).rowcount
    conn.commit()
    return done


def main(argv=None) -> int:
    from engine import db
    argv = sys.argv[1:] if argv is None else argv
    conn = db.connect()
    rows = plan(conn)
    if not rows:
        print("NBA CODES  every stored NBA game and log already uses the league's codes. Nothing to do.")
        return 0
    print("NBA CODES  rows still under ESPN's spelling:")
    for table, col, espn, league, n in rows:
        print(f"  {table}.{col:<9} {espn:>5} -> {league:<4} {n:>8,} row(s)")
    if "--apply" not in argv:
        print("Dry run: nothing changed. Run again with --apply to rewrite them.")
        return 0
    print(f"Rewrote {apply(conn, rows):,} value(s). Run it once more: it should say nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
