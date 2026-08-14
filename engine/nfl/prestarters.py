"""Who is actually going to play in a preseason game.

Ethan, 2026-08-14: "i wanna show props for the pre season … make sure to
implement scanning to see which teams will be playing starters and which
ones wont along with any other information like that that would be
useful."

He is right that this is the question. A preseason game is not a contest
between two teams, it is a contest between two COACHING DECISIONS, and
the decision is how long the first string is on the field. Everything
else — who wins, how many points, whether a name you know does anything
at all — falls out of that one call.

WHAT IS MEASURABLE HERE, AND WHAT IS NOT.

The regular-season logs carry `snap_pct`, which says exactly who a team's
starters are. The preseason logs do not: ESPN's box score gives passing,
rushing and receiving, so a player only appears if he touched the ball.
That has two consequences worth stating rather than papering over.

  * Only SKILL starters are visible. A starting guard who played the
    whole first half leaves no trace, so "starters seen" is a count of
    quarterbacks, backs and receivers and is described as such.
  * Appearance is binary, and a quarterback who hands off twice appears
    identically to one who threw twenty times — which is why the headline
    number here is his ATTEMPTS, not his presence.

THE STARTING QUARTERBACK'S ATTEMPTS ARE THE MEASUREMENT. He is on the
field for exactly as long as the staff wants the first team out there,
and he is the one player guaranteed to leave a mark in the box score
when he is. Zero is a rest. A handful is a series. Twenty is a dress
rehearsal.

NO THRESHOLD HERE IS INVENTED. "Rested", "limited" and "extended" are
cuts taken from the league's own distribution of those attempt counts
across the seasons on hand — `bands()` computes them, and they move when
the league's habits move. A hard-coded "10 attempts means extended"
would be a claim about football written by someone who did not check.

Read-only. The queries are ordinary SQL; everything else is arithmetic.
"""

from __future__ import annotations

#: Snap share at or above which a player counted as a starter that season.
#: `snap_pct` is stored as a FRACTION (Jared Goff, 2025: 1.0), which is
#: worth stating because a 55 here instead of 0.55 silently selects nobody
#: and every team reads as resting everyone.
STARTER_SNAP = 0.55
#: Games a player must have to be judged a starter at all — one 100% game
#: is an injury fill-in, not a role.
MIN_GAMES = 4
#: Box scores only see players who touched the ball.
SKILL = ("QB", "RB", "WR", "TE", "FB")


def starters(conn, team: str, season: int, min_snap: float = STARTER_SNAP,
             min_games: int = MIN_GAMES) -> dict:
    """``{player: mean snap share}`` for one team's regular-season starters.

    ``season`` is the season that DEFINES the role — for a preseason in
    August that is the season just gone, because the one about to start
    has no snaps yet.
    """
    rows = conn.execute(
        "SELECT player, position, AVG(value) a, COUNT(*) g "
        "FROM player_game_logs WHERE sport='nfl' AND season=? AND team=? "
        "AND market='snap_pct' GROUP BY player, position "
        "HAVING g >= ? AND a >= ?",
        (int(season), team, int(min_games), float(min_snap))).fetchall()
    return {r["player"]: float(r["a"]) for r in rows
            if not r["position"] or str(r["position"]).upper() in SKILL}


def starting_qb(conn, team: str, season: int) -> str | None:
    """The quarterback who took the snaps, by pass attempts.

    Attempts rather than snap share because a team that changed starters
    mid-season has two men near the top on snaps and only one of them
    threw the ball most.
    """
    row = conn.execute(
        "SELECT player, SUM(value) t FROM player_game_logs "
        "WHERE sport='nfl' AND season=? AND team=? AND market='pass_att' "
        "GROUP BY player ORDER BY t DESC LIMIT 1",
        (int(season), team)).fetchone()
    return row["player"] if row and (row["t"] or 0) > 0 else None


def _pre_rows(conn, season: int, team: str, week=None):
    q = ("SELECT player, week, market, value FROM preseason_player_logs "
         "WHERE sport='nfl' AND season=? AND team=?")
    args: list = [int(season), team]
    if week is not None:
        q += " AND week=?"
        args.append(int(week))
    try:
        return conn.execute(q, args).fetchall()
    except Exception:                                         # noqa: BLE001
        return []                       # table absent = nothing ingested yet


def usage(conn, team: str, season: int, week: int,
          role_season: int | None = None) -> dict | None:
    """What one team actually did in one preseason game.

    ``{qb, qb_att, seen, roster, share, played}`` or None when the game
    has not been ingested. ``role_season`` defaults to the season before
    ``season`` — the one that says who the starters are.
    """
    role_season = int(role_season if role_season is not None else season - 1)
    rows = _pre_rows(conn, season, team, week)
    if not rows:
        return None
    core = starters(conn, team, role_season)
    qb = starting_qb(conn, team, role_season)
    att = 0.0
    seen = set()
    for r in rows:
        if r["player"] in core and float(r["value"] or 0) > 0:
            seen.add(r["player"])
        if qb and r["player"] == qb and r["market"] == "pass_att":
            att += float(r["value"] or 0)
    return {
        "team": team, "season": int(season), "week": int(week),
        "qb": qb, "qb_att": att,
        "seen": len(seen), "roster": len(core),
        "share": (len(seen) / len(core)) if core else None,
        # Named so a caller cannot mistake it for a snap count.
        "played": sorted(seen),
    }


def bands(conn, seasons=None) -> dict:
    """League-wide cuts for "rested / limited / extended", from the data.

    Terciles of every starting quarterback's preseason attempt count
    across the seasons on hand. Returned as ``{"lo", "hi", "n"}``: below
    ``lo`` is a rest, above ``hi`` is a dress rehearsal, between is a
    series or two.

    ``None`` when there is not enough ingested preseason to cut anything,
    which is the honest answer — a verdict from four games is a guess
    wearing a percentile.
    """
    try:
        rows = conn.execute(
            "SELECT DISTINCT season, week, team FROM preseason_player_logs "
            "WHERE sport='nfl'" + (
                " AND season IN (%s)" % ",".join("?" * len(seasons))
                if seasons else ""),
            [int(s) for s in (seasons or [])]).fetchall()
    except Exception:                                         # noqa: BLE001
        return {}
    atts = []
    for r in rows:
        u = usage(conn, r["team"], r["season"], r["week"])
        if u and u["qb"]:
            atts.append(u["qb_att"])
    if len(atts) < 30:
        return {}
    atts.sort()
    return {"lo": atts[len(atts) // 3], "hi": atts[2 * len(atts) // 3],
            "n": len(atts)}


def verdict(qb_att: float | None, cuts: dict) -> str:
    """"rested" / "limited" / "extended" / "unknown"."""
    if qb_att is None or not cuts:
        return "unknown"
    if qb_att <= cuts.get("lo", 0):
        return "rested"
    return "extended" if qb_att >= cuts.get("hi", 1e9) else "limited"


def tendency(conn, team: str, seasons, week: int | None = None) -> dict:
    """How this team has handled preseason before.

    ``{"n", "mean_att", "by_week": {week: mean}}``. A coach's habit is the
    only forward-looking signal available before a game is played — no
    free feed announces who is sitting — so this is what the board leans
    on for a fixture that has not happened.

    IT IS A TEAM RECORD, NOT A COACH RECORD, and that is a real weakness:
    a new head coach inherits his predecessor's history here. The staff
    is not in any table we hold, so the alternative is no signal at all.
    """
    out: dict = {"n": 0, "mean_att": None, "by_week": {}}
    tot: list = []
    per: dict = {}
    for season in seasons or []:
        weeks = conn.execute(
            "SELECT DISTINCT week FROM preseason_player_logs "
            "WHERE sport='nfl' AND season=? AND team=?",
            (int(season), team)).fetchall() if _has_table(conn) else []
        for w in weeks:
            if week is not None and int(w["week"]) != int(week):
                continue
            u = usage(conn, team, season, w["week"])
            if u and u["qb"]:
                tot.append(u["qb_att"])
                per.setdefault(int(w["week"]), []).append(u["qb_att"])
    if tot:
        out["n"] = len(tot)
        out["mean_att"] = round(sum(tot) / len(tot), 1)
        out["by_week"] = {w: round(sum(v) / len(v), 1) for w, v in sorted(per.items())}
    return out


def _has_table(conn) -> bool:
    try:
        conn.execute("SELECT 1 FROM preseason_player_logs LIMIT 1")
        return True
    except Exception:                                         # noqa: BLE001
        return False


def scan(conn, games: list[dict], season: int, seasons=None) -> list[dict]:
    """One read per upcoming fixture: what each side is likely to do.

    ``games`` are board rows carrying ``home``/``away``/``week``. The
    answer for a game that has NOT been played is a tendency, and it is
    labelled as one — the board must never print a habit as though it
    were a team sheet.
    """
    seasons = list(seasons or range(season - 5, season))
    cuts = bands(conn, seasons)
    out = []
    for g in games or []:
        row = {"home": g.get("home"), "away": g.get("away"),
               "week": g.get("week"), "date": g.get("date"), "sides": {}}
        for side in ("home", "away"):
            team = g.get(side)
            if not team:
                continue
            t = tendency(conn, team, seasons, week=g.get("week"))
            att = t.get("by_week", {}).get(int(g.get("week") or 0))
            if att is None:
                att = t.get("mean_att")
            row["sides"][side] = {
                "team": team, "qb": starting_qb(conn, team, season - 1),
                "expect_att": att, "verdict": verdict(att, cuts),
                "games_seen": t.get("n", 0),
            }
        out.append(row)
    return {"games": out, "bands": cuts, "seasons": seasons}
