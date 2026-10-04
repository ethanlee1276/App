"""What each college defence gives up to each position — from our own logs.

Ethan, 2026-09-23, after the NFL got its matchup model: "go do the same
work you just did for nfl but for CFB."

`engine/cfb/props._game_objects` gave every college defence a LEAGUE
AVERAGE profile, on the grounds that college "has no equivalent ingest".
It has: every stored player game (`player_game_logs`, sport 'cfb') names
its opponent and carries the player's roster position, which is exactly
what engine/defensevs rates the NFL from. This turns those rows into the
same per-game shape and hands them to the same code.

TWO COLLEGE RULES.

  * FBS AGAINST FBS ONLY. A Group-of-Five school's day against an FCS
    team is not a measurement of either defence, and an FCS team plays
    one or two stored games a year — enough to drag the league average
    and never enough to rate. A school counts as FBS when it has
    FBS_MIN_GAMES stored games in this season or either of the two
    before it.
  * NOTHING BEFORE THE FIRST GAME. In week one there is no current
    season to rate, and last season's defence has lost a quarter of its
    players to the portal; the card would claim a matchup it cannot see.
    From the first game on, the current season is shrunk toward last
    season's rating by defensevs.SHRINK_GAMES — the same shrink the NFL
    uses, and the college fit was flat across 6, 12 and 20 games.

How much of a rating reaches one player, per market and position, is
measured by `python3 cfbdefensefit.py` (engine/cfb/defensefit.py) and
lives in defensevs.TRANSFER_CFB.
"""
from __future__ import annotations

import datetime as _dt

from .. import defensevs as D

#: Stored games in a season for a school to count as FBS.
FBS_MIN_GAMES = 8

#: `player_game_logs` market -> the nflverse column defensevs reads.
COLUMN = {"rec_yds": "receiving_yards", "receptions": "receptions", "rush_yds": "rushing_yards",
          "pass_yds": "passing_yards", "pass_td": "passing_tds", "rec_td": "receiving_tds",
          "rush_td": "rushing_tds", "carries": "carries", "pass_att": "attempts"}


def fbs_teams(conn, season: int) -> set:
    """Schools with FBS_MIN_GAMES stored games in this season or the two before."""
    out: set = set()
    for s in (season, season - 1, season - 2):
        counts: dict = {}
        for r in conn.execute("SELECT home, away FROM games WHERE sport='cfb' AND season=?", (s,)):
            for t in (r[0], r[1]):
                counts[t] = counts.get(t, 0) + 1
        out |= {t for t, n in counts.items() if n >= FBS_MIN_GAMES}
    return out


def _week(first: str, period: str) -> int:
    try:
        return (_dt.date.fromisoformat(str(period)[:10]) - _dt.date.fromisoformat(str(first)[:10])).days // 7 + 1
    except ValueError:
        return 0


def wide_rows(conn, season: int, before: str | None = None, fbs: set | None = None) -> list[dict]:
    """One row per player-game in the nflverse shape defensevs reads, FBS
    against FBS, played before ``before`` (an ISO date) when it is given."""
    fbs = fbs_teams(conn, season) if fbs is None else fbs
    q = ("SELECT period, player, team, opponent, position, market, value FROM player_game_logs "
         "WHERE sport='cfb' AND season=? AND market IN (%s)" % ",".join("?" * len(COLUMN)))
    args: list = [int(season), *COLUMN]
    if before:
        q += " AND period < ?"
        args.append(str(before)[:10])
    rows: dict = {}
    for r in conn.execute(q, args):
        team, opp = r[2], r[3]
        if team not in fbs or opp not in fbs:
            continue
        row = rows.setdefault((r[0], r[1], team), {
            "player_id": f"{r[1]}|{team}", "player_display_name": r[1], "position": (r[4] or "").upper(),
            "opponent_team": opp, "team": team, "season_type": "REG", "period": r[0]})
        row[COLUMN[r[5]]] = float(r[6] or 0.0)
    if not rows:
        return []
    first = min(r["period"] for r in rows.values())
    out = []
    for row in rows.values():
        row["week"] = _week(first, row["period"])
        if row["week"] > 0:
            out.append(row)
    return out


def ratings(conn, season: int, before: str | None = None) -> dict:
    """{school: {stat: rating}} for tonight: this season's games before
    ``before``, shrunk toward last season's. Empty before the first game."""
    fbs = fbs_teams(conn, season)
    now = wide_rows(conn, season, before, fbs)
    if not now:
        return {}
    last = wide_rows(conn, season - 1, None, fbs)
    prior = D.ratings(last, 99) if last else None
    return D.ratings(now, 99, prior=prior)
