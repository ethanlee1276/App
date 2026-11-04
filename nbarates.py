"""Do the rates read past his last twenty games come out closer on this box's own seasons?

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbarates.py          # read-only
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbarates.py --save   # the weekly refit's run

engine/nba/rates reads the per-minute rebounds, assists, steals, blocks
and turnovers past his last twenty games: his older games (his last sixty,
any club) at a weight a minute, and some minutes of the league's rate for
his role, joined to the twenty's. Measured in the NBA lab on two full
seasons of the league's own box scores, each season held out: steals 4.5%
closer, turnovers 3.3%, blocks 2.7-4.0%, rebounds 2.0-3.2%, assists
1.6-2.4% (docs/NBA_LAB.md, "Twenty games is not enough for a rate").

This asks the box's own stored seasons the same question at the board's
own constants: every player-game of 10+ minutes with 5+ earlier games for
his club, his rate as the board reads it (his last twenty for the club)
times the minutes he played, against what he did, with the read past the
twenty and without it. The minutes are the
ones he played, so the minutes model's own error stays out of it.

THE BAR, written before the first box run: in every season with
MIN_ROWS or more such games of a stat, the squared error of that stat is
lower with the read, for every stat it moves (rebounds, assists, steals,
blocks, turnovers). HOLDS, or the seasons and stats where it does
not. ``--save`` (the weekly deep refit runs it so) files the verdict and the
switch follows it at once (engine/nba/switches ``rates``); a box with no
season big enough to judge files nothing. ``QB_NBA_RATES`` in
/etc/qellys/env still decides first.

Opened read-only. Changes nothing but that one verdict. Standard library only.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: The rows measured: a game of this many minutes, with this many earlier
#: games for his club (the lab's).
MIN_MINUTES = 10.0
PRIOR_GAMES = 5
#: The bar's floor: a season with fewer games of a stat is shown, not judged.
MIN_ROWS = 2000
STATS = ("reb", "ast", "stl", "blk", "tov")


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load(conn, sport: str = "nba") -> dict:
    """``{player: [game, ...] oldest first}``, each game ``{"season", "team",
    "date", "starter", market: value}`` — every stored column the reads use."""
    from engine.nba import rates as RT
    cols = sorted({"min", *RT.KEYS})
    games: dict = {}
    for player, season, team, date, pos, market, value in conn.execute(
            "SELECT player, season, team, period, position, market, value FROM player_game_logs "
            "WHERE sport=? AND market IN (%s)" % ",".join("?" * len(cols)), (sport, *cols)):
        g = games.setdefault(str(player), {}).setdefault(str(date), {"season": int(season or 0),
                                                                     "team": str(team or ""),
                                                                     "date": str(date)})
        g[str(market)] = float(value or 0.0)
        if market == "min":
            g["starter"] = pos == "S"
    return {p: [by_day[d] for d in sorted(by_day)] for p, by_day in games.items()}


def cases(players: dict) -> list:
    """Every measured player-game: ``{"season", stat: (actual, without, with)}``."""
    from engine.nba import rates as RT
    out = []
    for rows in players.values():
        played = [g for g in rows if float(g.get("min") or 0.0) > 0]
        for i, g in enumerate(played):
            if float(g.get("min") or 0.0) < MIN_MINUTES:
                continue
            past = played[:i]
            club = [x for x in past if x["team"] == g["team"]]
            if len(club) < PRIOR_GAMES:
                continue
            recent = club[-RT.WINDOW:][::-1]
            longrun = [(x["date"], x) for x in past[-RT.LONG_GAMES:]][::-1]
            read = RT.bundle(recent, [x["date"] for x in recent], longrun, bool(recent[0].get("starter")))
            mins = float(g["min"])
            row = {"season": g["season"]}
            for stat in STATS:
                if stat not in g:
                    continue
                b = RT.blended(stat, read)
                if b is not None:
                    row[stat] = (g[stat], b[0] * mins, b[1] * mins)
            out.append(row)
    return out


def measure(rows: list) -> dict:
    """``{season: {stat: {"n", "gain"}}}`` — the share of squared error the
    read takes off (positive = closer with it)."""
    out: dict = {}
    for r in rows:
        for stat in STATS:
            if stat not in r:
                continue
            y, a, b = r[stat]
            c = out.setdefault(r["season"], {}).setdefault(stat, {"n": 0, "e0": 0.0, "e1": 0.0})
            c["n"] += 1
            c["e0"] += (y - a) ** 2
            c["e1"] += (y - b) ** 2
    for by in out.values():
        for c in by.values():
            c["gain"] = (1 - c["e1"] / c["e0"]) if c["e0"] else 0.0
    return out


def verdict(res: dict) -> tuple[bool, list]:
    why, judged = [], 0
    for season, by in sorted(res.items()):
        for stat in STATS:
            c = by.get(stat) or {}
            if c.get("n", 0) < MIN_ROWS:
                continue
            judged += 1
            if not c["gain"] > 0:
                why.append(f"{stat} in {season}: {100 * c['gain']:+.2f}%")
    if not judged:
        return False, ["no season has enough games to judge"]
    return not why, why


def report(res: dict) -> list:
    lines = ["NBA RATES READ PAST THE LAST TWENTY ON THIS BOX'S OWN SEASONS — the board's constants",
             f"(every game of {MIN_MINUTES:.0f}+ minutes with {PRIOR_GAMES}+ earlier for his club; the rate times "
             "the minutes he played; squared error the read takes off)", ""]
    lines.append(f"{'season':<8}" + "".join(f"{s:>22}" for s in STATS))
    for season, by in sorted(res.items()):
        cells = []
        for stat in STATS:
            c = by.get(stat) or {}
            cells.append(f"n {c['n']:6d} {100 * c['gain']:+6.2f}%" if c.get("n") else "—")
        lines.append(f"{season!s:<8}" + "".join(f"{x:>22}" for x in cells))
    ok, why = verdict(res)
    lines += ["", f"THE BAR (every season with {MIN_ROWS}+ games of a stat: closer with the read, every stat): "
              + ("HOLDS — the board keeps it." if ok else
                 "DOES NOT HOLD: " + "; ".join(why[:6])
                 + " — set QB_NBA_RATES=0 in /etc/qellys/env to turn it off, and send this.")]
    lines.append("Read-only: nothing was changed.")
    return lines


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Measured with the read on, whatever the board's switch says: this is
    # the run that decides the switch.
    os.environ["QB_NBA_RATES"] = "1"
    from engine import db
    conn = _ro(db.DEFAULT_DB)
    try:
        players = load(conn)
    finally:
        conn.close()
    if not players:
        print("No NBA logs stored.")
        return 0
    res = measure(cases(players))
    for line in report(res):
        if "--save" in argv and line.startswith("Read-only"):
            continue                                  # it files a verdict below
        print(line)
    if "--save" in argv:
        ok, why = verdict(res)
        if why == ["no season has enough games to judge"]:
            print("rates verdict not filed: no season has enough games to judge")
        else:
            from engine.nba import switches
            print(f"rates verdict filed: {switches.record_check('rates', ok, '; '.join(why[:6]) or 'closer in every season judged', follow=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
