"""What if he sits? The on/off record behind a basketball teammate's absence.

Ethan, 2026-10-15, from the brainstorm he asked to have built: an NBA
"what if he sits" toggle. THE RULE IT KEEPS: a number on the board moves
only through a measured rule. Your O run met the vacancy bar (a held-out
test is earned), but no rule has been adopted, so this moves nothing: it
shows the evidence — in the games he missed for this club, how each
teammate's share of the team's minutes, points, rebounds and assists
changed against the games he played — beside the counts, and says when the
missed games are too few to be evidence at all (`onoff.MIN_OUT_GAMES`).

Share, not volume (pace cancels); absence read from the box scores, not
an injury report; his games before he joined this club are not "sat".
All of it is `engine/nba/onoff`'s, which the board's teammate card already
uses for a man who IS out; this asks the same question of any man in the
rotation, before anyone knows.
"""

from __future__ import annotations

from engine.nba import onoff

#: The stats asked of each absence, in the order the page shows them.
STATS = ("min", "pts", "reb", "ast")
#: Teammates shown per stat, most helped first.
TOP = 8
#: The rotation offered: the men with the most minutes in his club's recent games.
ROTATION = 10
LEAGUES = ("nba", "wnba")


def _rows(conn, league: str, team: str, seasons: list[int]) -> list[dict]:
    q = ("SELECT player, team, period, market, value FROM player_game_logs WHERE sport=? AND team=? "
         "AND market IN (%s)" % ",".join("?" * len(onoff.STATS)))
    args = [league, team, *onoff.STATS]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    return [dict(r) for r in conn.execute(q, args).fetchall()]


def rotation(rows: list[dict], limit: int = ROTATION, last: int = 15) -> list[dict]:
    """[{player, minutes}] — average minutes over the club's last ``last`` games."""
    dates = sorted({r["period"] for r in rows if r["market"] == "min"}, reverse=True)[:last]
    keep = set(dates)
    tot: dict = {}
    for r in rows:
        if r["market"] == "min" and r["period"] in keep:
            tot[r["player"]] = tot.get(r["player"], 0.0) + float(r["value"] or 0)
    n = len(dates) or 1
    out = [{"player": p, "minutes": round(m / n, 1)} for p, m in tot.items() if m > 0]
    return sorted(out, key=lambda x: -x["minutes"])[:limit]


def whatif(conn, league: str, team: str, player: str = "", seasons: list[int] | None = None) -> dict:
    """The rotation, and — with ``player`` — each stat's on/off shares."""
    league = (league or "").lower()
    if league not in LEAGUES or not team:
        return {"error": "league and team"}
    if seasons is None:
        from engine.seasons import recent_seasons
        import datetime
        seasons = recent_seasons(league, datetime.date.today().isoformat())
    rows = _rows(conn, league, team, seasons)
    out = {"league": league, "team": team, "rotation": rotation(rows), "floor": onoff.MIN_OUT_GAMES}
    if not player:
        return out
    mine = [r["period"] for r in rows if r["player"] == player]
    if not mine:
        out["error"] = "no games for this club"
        return out
    first = min(mine)
    since = [r for r in rows if r["period"] >= first]
    out["player"] = player
    out["since"] = first
    out["stats"] = {}
    for stat in STATS:
        res = onoff.inheritance(since, team, player, stat)
        top = list(res["beneficiaries"].items())[:TOP]
        out["stats"][stat] = {"n_played": res["n_played"], "n_out": res["n_out"], "enough": res["enough"],
                              "rows": [{"player": n, **v} for n, v in top]}
    return out
