#!/usr/bin/env python3
"""Does a basketball defence's rating reach one player's line? — measured.

    python3 hoopsdvpfit.py            # NBA and WNBA, every stored season
    python3 hoopsdvpfit.py wnba

Walk-forward over the box's player logs (engine/hoopsdvp.measure): per
stat, how much of the opposing defence's shrunk factor shows up in a
player's result against his own recent average. The matchup cards under
basketball picks move no projection until this says a stat earns it.
Reads only; writes nothing.
"""
import sys

from engine import hoopsdvp
from engine.db import connect


def main(argv):
    leagues = argv or ["nba", "wnba"]
    conn = connect()
    for lg in leagues:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM player_game_logs WHERE sport=? ORDER BY season", (lg,)).fetchall()]
        if not seasons:
            print(f"{lg.upper()}: no stored logs")
            continue
        got = hoopsdvp.measure(hoopsdvp.load_with_players(conn, lg, seasons))
        print(f"\n{lg.upper()} — seasons {seasons[0]}–{seasons[-1]}")
        for m, r in got.items():
            b = "—" if r["slope"] is None else f"{r['slope']:+.3f} ± {r['se']:.3f}"
            print(f"   {hoopsdvp.MARKETS[m]:<9} {r['rows']:>7} player-games  transfer {b}  — {r['verdict']}")


if __name__ == "__main__":
    main(sys.argv[1:])
