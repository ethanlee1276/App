"""Each stored NHL game's starting goalies, where the box score named none (2026-11-18, walk 15).

    python3 -m engine.nhlstarts              # what it would mark; writes nothing
    python3 -m engine.nhlstarts --apply      # mark them
    python3 -m engine.nhlstarts --season 2026

Connor Hellebuyck's player page read GS 0 beside seven games; Andrei Vasilevskiy's
351 saves came with six starts and Jeremy Swayman's 340 with five. A goalie's
`started` line is the NHL box score's `starter` flag (sources/nhldata.parse_boxscore),
and in many of this season's stored games neither of a side's goalies carries it.
The goalie model counts those flags to name each club's probable starter and its
backup (nhl/model.probable_starter, backup_goalie, starter_share), so a season with
starts missing reads an older, sometimes another club's, run of starts instead.

THIS MARKS WHAT WAS STORED, from the box itself and nothing else: for each game and
side whose goalies are all unflagged, the goalie with the most time in net is its
starter (the starter whenever one goalie played, and almost always when two did).
A side already flagged is left alone. The box reader names a starter the same way
from now on (nhldata.name_starter). Nothing is written without ``--apply``.
"""

from __future__ import annotations

import argparse
import sys

from . import db as _db


def found(conn, season: int | None = None) -> dict:
    """{"sides": [{season, period, game_id, team, player, toi}], "goalies": {name: n}} — each unflagged side's
    starter by time in net, oldest first."""
    args = ["nhl"]
    where = "sport=? AND position='G' AND market IN ('toi', 'started')"
    if season is not None:
        where += " AND season=?"
        args.append(int(season))
    sides: dict = {}
    for s, period, gid, player, team, market, value in conn.execute(
            f"SELECT season, period, game_id, player, team, market, value FROM player_game_logs WHERE {where}", args):
        g = sides.setdefault((int(s), str(period), str(gid), team), {}).setdefault(player, {})
        g[market] = float(value or 0.0)
    out, tally = [], {}
    for (s, period, gid, team), goalies in sorted(sides.items()):
        if any(v.get("started") for v in goalies.values()):
            continue
        played = {n: v for n, v in goalies.items() if v.get("toi")}
        if not played:
            continue
        name = max(sorted(played), key=lambda n: played[n]["toi"])
        out.append({"season": s, "period": period, "game_id": gid, "team": team, "player": name,
                    "toi": played[name]["toi"]})
        tally[name] = tally.get(name, 0) + 1
    return {"sides": out, "goalies": tally}


def apply(conn, report: dict) -> int:
    """Mark each listed side's starter. Returns the lines written."""
    n = 0
    for r in report["sides"]:
        n += conn.execute("INSERT OR REPLACE INTO player_game_logs (sport, season, period, game_id, player, team, "
                          "opponent, position, home, market, value) SELECT sport, season, period, game_id, player, "
                          "team, opponent, position, home, 'started', 1.0 FROM player_game_logs WHERE sport='nhl' "
                          "AND season=? AND period=? AND game_id=? AND player=? AND market='toi'",
                          (r["season"], r["period"], r["game_id"], r["player"])).rowcount
    conn.commit()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.nhlstarts",
                                 description="Mark the starting goalie of each stored NHL game side whose box "
                                             "score named none (by time in net).")
    ap.add_argument("--season", type=int, help="one season (default: every stored season)")
    ap.add_argument("--apply", action="store_true", help="write them (without it, nothing is written)")
    a = ap.parse_args(argv)
    conn = _db.connect()
    try:
        rep = found(conn, a.season)
        top = sorted(rep["goalies"].items(), key=lambda kv: -kv[1])[:12]
        print(f"NHL: {len(rep['sides'])} game side(s) with no starter named"
              + (" — most for " + ", ".join(f"{n} ({k})" for n, k in top) if top else ""))
        if a.apply and rep["sides"]:
            print(f"  marked {apply(conn, rep):,} start(s); the next build and the night's refit read them")
        elif not a.apply:
            print("\nNothing written. Run again with --apply to mark them.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
