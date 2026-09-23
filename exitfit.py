#!/usr/bin/env python3
"""Games a player left early: measure them on this box's own history (engine/exitfit.py).

    python3 exitfit.py mlb     # starters by outs, hitters by plate appearances
    python3 exitfit.py wnba    # minutes, by minutes
    python3 exitfit.py nba

READ-ONLY: opens the results database with mode=ro, fetches nothing,
writes nothing — safe mid-cycle. For each market it prints, by where a
left-early game sits in the history (clean / only older than the last
five / in the last five), how centred the next game's projection is with
every game kept ("all"), with older early exits dropped when the last
five are clean ("old", the hoops rule) and with every early exit dropped
("none"). 0.50 "above" is centred.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

from engine import db
from engine import exitfit as X

#: sport -> [(label, value market, usage market, role floor, window, projection)]
PLANS = {
    "mlb": [("starter strikeouts by outs", "strikeouts", "outs", 12.0, 15),
            ("starter outs by outs", "outs", "outs", 12.0, 15),
            ("hitter hits by plate appearances", "hits", "pa", 3.0, 15),
            ("hitter total bases by plate appearances", "total_bases", "pa", 3.0, 15)],
    "wnba": [("minutes by minutes", "min", "min", 15.0, 20),
             ("points by minutes", "pts", "min", 15.0, 20)],
    "nba": [("minutes by minutes", "min", "min", 15.0, 20),
            ("points by minutes", "pts", "min", 15.0, 20)],
}


def _series(conn, sport: str, value_m: str, usage_m: str) -> dict:
    rows = conn.execute(
        "SELECT player, season, period, game_id, market, value FROM player_game_logs "
        "WHERE sport=? AND market IN (?, ?) ORDER BY period", (sport, value_m, usage_m))
    games: dict = defaultdict(dict)
    for player, season, period, gid, market, value in rows:
        games[(player, gid or period)].setdefault("k", (player, int(season), str(period)))
        games[(player, gid or period)][market] = float(value)
    series: dict = defaultdict(list)
    for g in games.values():
        if value_m in g and usage_m in g:
            player, season, period = g["k"]
            series[player].append((season, period, g[usage_m], g[value_m]))
    for v in series.values():
        v.sort(key=lambda t: t[1])
    return series


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sport = (argv or [""])[0]
    if sport not in PLANS:
        print(__doc__.strip())
        return 2
    conn = sqlite3.connect(f"file:{db.DEFAULT_DB}?mode=ro", uri=True)
    if sport == "mlb":
        from engine.form import MLB_WINDOW_WEIGHTS, CAREER_PRIOR_GAMES
        project = X.form_projection(MLB_WINDOW_WEIGHTS, CAREER_PRIOR_GAMES)
    else:
        from engine.hoops import NBA, WNBA
        tune = WNBA if sport == "wnba" else NBA
        minutes = X.minutes_projection(tune)
        project = None
    for label, value_m, usage_m, floor, window in PLANS[sport]:
        series = _series(conn, sport, value_m, usage_m)
        if sport != "mlb":
            if value_m == "min":
                project = minutes
            else:
                # Points as the board prices them: the kept games' rate per
                # minute times their minutes base.
                def project(values, usage, _m=minutes):
                    base, tm = _m(usage, usage), sum(usage)
                    return None if base is None or not tm else sum(values) / tm * base
        res = X.measure(series, project, floor, window)
        print("\n".join(X.lines(f"{sport} {label} — {len(series)} players", res)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
