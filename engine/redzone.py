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

OPPONENT-ADJUSTED, like the unit ratings (gamescan._adjusted). Measured on
the box 2026-09-26: Pittsburgh read "allows 4.45 (-50%)" because its two
2026 games were against Atlanta (0 red-zone plays) and New England (1) —
the two lowest red-zone offences in the league. Each game's number is now
moved by how far that opponent sits from the league on the other side of
the ball, and the opponent's rate leaves THIS game out (its other games
this season, blended with its last season the same 55/45 way), so a
defence is not credited for an offence being bad only against it.

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


def _mean(xs):
    xs = list(xs)
    return (sum(xs) / len(xs)) if xs else None


def _season_games(conn, yr: int, upto: int | None) -> list:
    """[(week, offence, defence, red-zone plays)] for one season, weeks
    before ``upto``."""
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
    return [(wk, team, opp.get((team, wk)), v) for (team, wk), v in sorted(plays.items())]


def _by_side(games: list) -> dict:
    """{("off", team): {week: plays}, ("def", team): {week: plays allowed}}."""
    out: dict = {}
    for wk, team, o, v in games:
        out.setdefault(("off", team), {})[wk] = v
        if o:
            out.setdefault(("def", o), {})[wk] = v
    return out


def team_rates(conn, season: int, before_week: int | None = None) -> dict:
    """{team: {"off": plays per game, "def": plays allowed per game (both
    opponent-adjusted), "off_raw"/"def_raw": as counted, "off_rel"/"def_rel":
    adjusted vs the league, "games": n, "blend": w}}."""
    from .gamescan import season_share

    now_games = _season_games(conn, int(season), before_week)
    pri_games = _season_games(conn, int(season) - 1, None)
    now, pri = _by_side(now_games), _by_side(pri_games)

    def blended(side_now: dict, side_pri: dict, team: str, n_games: int | None = None,
                skip_now=None, skip_pri=None):
        a = _mean(v for w, v in (side_now.get(team) or {}).items() if w != skip_now)
        b = _mean(v for w, v in (side_pri.get(team) or {}).items() if w != skip_pri)
        g = n_games if n_games is not None else len([w for w in (side_now.get(team) or {}) if w != skip_now])
        if a is None:
            return b
        if b is None:
            return a
        w = season_share(g, True)
        return w * a + (1 - w) * b

    def split(by: dict, side: str) -> dict:
        return {t: wk for (s, t), wk in by.items() if s == side}

    off_now, def_now, off_pri, def_pri = split(now, "off"), split(now, "def"), split(pri, "off"), split(pri, "def")
    teams = set(off_now) | set(def_now) | set(off_pri) | set(def_pri)

    # League per-game means, this season and last, for the shift.
    league_now = _mean(v for _w, _t, _o, v in now_games)
    league_pri = _mean(v for _w, _t, _o, v in pri_games)

    def strength(side: str, team: str, current: bool, wk: int):
        """The opponent's rate on ``side`` from every game but this one."""
        if current:
            src_now, src_pri = (off_now, off_pri) if side == "off" else (def_now, def_pri)
            return blended(src_now, src_pri, team, skip_now=wk)
        src = off_pri if side == "off" else def_pri
        return _mean(v for w, v in (src.get(team) or {}).items() if w != wk)

    def league_for(current: bool):
        if not current:
            return league_pri
        if league_now is None or league_pri is None:
            return league_now if league_now is not None else league_pri
        return 0.55 * league_now + 0.45 * league_pri

    def adjusted(games: list, current: bool) -> tuple:
        off: dict = {}
        allowed: dict = {}
        league = league_for(current)
        for wk, team, o, v in games:
            if not o:
                off.setdefault(team, {})[wk] = v
                continue
            d_str = strength("def", o, current, wk)
            o_str = strength("off", team, current, wk)
            shift_off = (d_str - league) if (d_str is not None and league is not None) else 0.0
            shift_def = (o_str - league) if (o_str is not None and league is not None) else 0.0
            off.setdefault(team, {})[wk] = max(0.0, v - shift_off)
            allowed.setdefault(o, {})[wk] = max(0.0, v - shift_def)
        return off, allowed

    adj_off_now, adj_def_now = adjusted(now_games, True)
    adj_off_pri, adj_def_pri = adjusted(pri_games, False)

    out: dict = {}
    for team in teams:
        g = len(off_now.get(team) or {})
        row = {"games": g, "blend": round(season_share(g, True), 2)}
        for side, a_now, a_pri, r_now, r_pri in (("off", adj_off_now, adj_off_pri, off_now, off_pri),
                                                  ("def", adj_def_now, adj_def_pri, def_now, def_pri)):
            row[side] = blended(a_now, a_pri, team, n_games=g)
            row[f"{side}_raw"] = blended(r_now, r_pri, team, n_games=g)
        out[team] = row
    for side in ("off", "def"):
        league = _mean(r[side] for r in out.values() if r.get(side) is not None)
        for r in out.values():
            v = r.get(side)
            r[f"{side}_rel"] = (round(v / league - 1.0, 3) if v is not None and league else None)
            r[side] = round(v, 2) if v is not None else None
            if r.get(f"{side}_raw") is not None:
                r[f"{side}_raw"] = round(r[f"{side}_raw"], 2)
    return out
