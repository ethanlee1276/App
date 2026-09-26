"""Red-zone trips: how often an offence gets inside the 20, and how often a
defence lets its opponents in.

Ethan, 2026-09-25/26, on touchdown picks: "we need to be looking at how
good the offense is and the red zone, how often they get to the red zone
and players' red zone usages and how the defenses guards the offense in
the red zone."

Built from what the play-by-play ingest already stores: every red-zone
target and carry (``rz_tgt``, ``rz_car``) per player per week. Summed per
team-week that is the offence's red-zone plays; the schedule says whom it
played, so the same number is the OPPONENT'S red-zone plays allowed. Each
side is a per-game rate over the weeks before the game, this season
leading last season 55/45 from two games on (gamescan.season_share), and
centred on the league so +20% reads "gets there a fifth more than an
average offence".

Plays, not drives: the feed carries plays inside the 20, not possessions.
A team that gets in once and runs six plays reads like one that got in
twice and scored fast — which is why this is one reading of five on a
touchdown scenario, not a number that moves a probability.

Standard library only.
"""
from __future__ import annotations


def _week(p) -> int | None:
    try:
        return int(str(p).lstrip("0") or 0)
    except ValueError:
        return None


def team_rates(conn, season: int, before_week: int | None = None) -> dict:
    """{team: {"off": plays per game, "def": plays allowed per game,
    "off_rel": vs league, "def_rel": vs league, "games": n, "blend": w}}."""
    from .gamescan import season_share

    def season_weeks(yr: int, upto: int | None):
        plays: dict = {}
        for r in conn.execute(
                "SELECT team, period, SUM(value) v FROM player_game_logs "
                "WHERE sport='nfl' AND season=? AND market IN ('rz_tgt','rz_car') "
                "GROUP BY team, period", (yr,)):
            wk = _week(r["period"])
            if wk is None or (upto is not None and wk >= upto):
                continue
            plays[(r["team"], wk)] = float(r["v"] or 0.0)
        opp: dict = {}
        for g in conn.execute("SELECT period, home, away FROM games WHERE sport='nfl' AND season=?", (yr,)):
            wk = _week(g["period"])
            if wk is None or (upto is not None and wk >= upto):
                continue
            opp[(g["home"], wk)] = g["away"]
            opp[(g["away"], wk)] = g["home"]
        off: dict = {}
        allowed: dict = {}
        for (team, wk), v in plays.items():
            off.setdefault(team, []).append(v)
            o = opp.get((team, wk))
            if o:
                allowed.setdefault(o, []).append(v)
        return off, allowed

    off_now, def_now = season_weeks(int(season), before_week)
    off_pri, def_pri = season_weeks(int(season) - 1, None)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None      # noqa: E731
    out: dict = {}
    for team in set(off_now) | set(def_now) | set(off_pri) | set(def_pri):
        row = {}
        g = len(off_now.get(team, []))
        for side, now, pri in (("off", off_now, off_pri), ("def", def_now, def_pri)):
            a, b = mean(now.get(team, [])), mean(pri.get(team, []))
            w = season_share(g, b is not None)
            row[side] = (a if b is None else b if a is None else w * a + (1 - w) * b)
        row["games"], row["blend"] = g, round(season_share(g, True), 2)
        out[team] = row
    for side in ("off", "def"):
        vals = [r[side] for r in out.values() if r.get(side) is not None]
        league = mean(vals)
        for r in out.values():
            v = r.get(side)
            r[f"{side}_rel"] = (round(v / league - 1.0, 3) if v is not None and league else None)
            r[side] = round(v, 2) if v is not None else None
    return out
