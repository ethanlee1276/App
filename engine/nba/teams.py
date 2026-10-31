"""What every basketball team does with the ball and allows without it — the
offence-against-defence half of the NBA matchup scan (engine/nba/scan).

Ethan, 2026-10-20: "We need offense vs defense or however that works and all
other shit we have ... look at what we use for nfl data and tool wise and
make sure NBA has the same shit." The NFL's scan ranks every unit off the
play-by-play (engine/gamescan); basketball's equivalent is a team's offence
and defence per possession — the two numbers every NBA preview reads first —
and the four things that decide a possession (Dean Oliver's four factors):
shooting, turnovers, the offensive glass and free throws.

WHAT IS COUNTED, from the box scores we store (`player_game_logs`, summed per
team-game; the opponent's rows that night are the defence's): points,
rebounds, assists, threes, steals, blocks, turnovers and minutes — and, from
2026-10-20, field goals and free throws made and tried, threes tried and
offensive rebounds (`espnhoops.STAT_MAP`). With those a game's possessions
are counted the standard way, each side's and averaged,

    possessions = FGA − OREB + TOV + 0.44 × FTA

and with possessions come pace and the per-100 ratings. A season whose box
scores were stored before those columns has the per-game numbers only, and
the page says so (`per100`): `python3 ingest.py nba --seasons 2025 --refresh`
reads last season's again with them.

THIS SEASON AND LAST. On opening night a team has no games; its numbers are
last season's whole, and as this season's come in they take over at
games / (games + PRIOR_GAMES) — the shape the NHL board uses. A summer's
trades are not in last season's numbers, so every tape says how much of each
team is still last season.

Ranks run 1 = best: the most for, the fewest against (pace runs 1 = the
fastest, which is not "best", and is drawn without a colour). Standard
library only.
"""
from __future__ import annotations

#: The box-score columns a team's night is summed from.
BOX = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min",
       "fgm", "fga", "fg3a", "ftm", "fta", "oreb")
#: The share of free-throw attempts that end a possession (the standard 0.44).
FT_WEIGHT = 0.44
#: This season's games worth as much as last season's whole (the blend).
PRIOR_GAMES = 10
#: A team needs this many games in a season before that season counts.
MIN_GAMES = 3
#: The share of a team's games that must carry the shooting columns before
#: its per-100 numbers are trusted (a few refreshed nights are not a season).
PER100_COVER = 0.8
#: A regulation game in team minutes (five men × 48).
TEAM_MINUTES = 240.0

#: Each rated stat and which way is better: True when more is better.
#: Pace is listed so it is ranked; it is drawn without a colour (PLAIN).
BETTER = {
    "pts": True, "opp_pts": False, "margin": True,
    "ortg": True, "drtg": False, "net": True, "pace": True,
    "efg": True, "opp_efg": False, "tov_pct": False, "opp_tov_pct": True,
    "oreb_pct": True, "dreb_pct": True, "ftr": True, "opp_ftr": False,
    "fg3a_rate": True, "opp_fg3a_rate": False, "fg3_pct": True, "opp_fg3_pct": False,
    "reb": True, "opp_reb": False, "ast": True, "opp_ast": False,
    "fg3m": True, "opp_fg3m": False, "stl": True, "blk": True,
    "tov": False, "opp_tov": True,
}
#: Rated, but neither end is "good".
PLAIN = ("pace",)
#: The per-game stats summed both ways (for and allowed).
PER_GAME = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _canon(sport: str):
    """The league's own club codes for the NBA (ESPN filed six of them its
    own way before 2026-10-14 — GS, NY, NO, SA, UTAH, WSH); the WNBA's rows
    are read as stored, as its board reads them."""
    if sport != "nba":
        return lambda t: str(t or "")
    from .. import divisions
    return lambda t: divisions.canonical("nba", str(t or ""))


def load_rows(conn, sport: str, season: int) -> list:
    """``(period, team, opponent, market, value)`` for every stored box-score
    column a team's night is summed from."""
    qs = ",".join("?" * len(BOX))
    return [tuple(r) for r in conn.execute(
        "SELECT period, team, opponent, market, value FROM player_game_logs "
        f"WHERE sport=? AND season=? AND market IN ({qs})", (sport, season, *BOX)).fetchall()]


def team_games(rows, sport: str = "nba") -> dict:
    """``{(team, date): {"opp": code, stat: total}}`` — every team-night, its
    players' box scores added up."""
    canon = _canon(sport)
    out: dict = {}
    for period, team, opp, market, value in rows:
        if value is None or not team or market not in BOX:
            continue
        g = out.setdefault((canon(team), str(period)[:10]), {"opp": canon(opp)})
        if not g.get("opp") and opp:
            g["opp"] = canon(opp)
        g[market] = g.get(market, 0.0) + float(value)
    return out


def possessions(g: dict) -> float | None:
    """One side's possessions in a night, or None when its box lacks a column."""
    if any(g.get(k) is None for k in ("fga", "fta", "oreb", "tov")):
        return None
    return g["fga"] - g["oreb"] + g["tov"] + FT_WEIGHT * g["fta"]


def _ratio(a: float, b: float):
    return a / b if b else None


def season_profiles(games: dict, before: str | None = None) -> dict:
    """``{team: profile}`` for one season's team-nights (only nights before
    ``before`` when given). Sums first, ratios after — a team's shooting is
    its makes over its tries, never the average of nightly percentages."""
    pairs: dict = {}
    for (team, day), g in games.items():
        if before and day >= before:
            continue
        opp = games.get((g.get("opp") or "", day))
        if opp is None:
            continue
        pairs.setdefault(team, []).append((g, opp))
    out: dict = {}
    for team, nights in pairs.items():
        n = len(nights)
        if n < MIN_GAMES:
            out[team] = {"games": n}          # counted, too few to rate
            continue
        prof: dict = {"games": n}
        for k in PER_GAME:
            prof[k] = sum(a.get(k) or 0.0 for a, _b in nights) / n
            prof["opp_" + k] = sum(b.get(k) or 0.0 for _a, b in nights) / n
        prof["margin"] = prof["pts"] - prof["opp_pts"]
        full = [(a, b) for a, b in nights if possessions(a) is not None and possessions(b) is not None]
        if len(full) >= MIN_GAMES and len(full) >= PER100_COVER * n:
            poss = sum((possessions(a) + possessions(b)) / 2 for a, b in full)
            mins = sum((a.get("min") or TEAM_MINUTES) for a, _b in full)
            s = {k: sum(a.get(k) or 0.0 for a, _b in full) for k in BOX}
            o = {k: sum(b.get(k) or 0.0 for _a, b in full) for k in BOX}
            prof["per100_games"] = len(full)
            prof["poss"] = poss / len(full)
            prof["pace"] = 48.0 * poss / (mins / 5.0) if mins else None
            prof["ortg"] = 100.0 * s["pts"] / poss if poss else None
            prof["drtg"] = 100.0 * o["pts"] / poss if poss else None
            if prof["ortg"] is not None and prof["drtg"] is not None:
                prof["net"] = prof["ortg"] - prof["drtg"]
            for side, x in (("", s), ("opp_", o)):
                prof[side + "efg"] = _ratio(x["fgm"] + 0.5 * x["fg3m"], x["fga"])
                prof[side + "tov_pct"] = _ratio(x["tov"], x["fga"] + FT_WEIGHT * x["fta"] + x["tov"])
                prof[side + "ftr"] = _ratio(x["fta"], x["fga"])
                prof[side + "fg3a_rate"] = _ratio(x["fg3a"], x["fga"])
                prof[side + "fg3_pct"] = _ratio(x["fg3m"], x["fg3a"])
            dreb, opp_dreb = s["reb"] - s["oreb"], o["reb"] - o["oreb"]
            prof["oreb_pct"] = _ratio(s["oreb"], s["oreb"] + opp_dreb)
            prof["dreb_pct"] = _ratio(dreb, dreb + o["oreb"])
        out[team] = {k: v for k, v in prof.items() if v is not None}
    return out


def blend(now: dict, last: dict) -> dict:
    """``{team: profile}`` — this season's numbers at games / (games +
    PRIOR_GAMES) against last season's whole. A stat only one season has is
    that season's alone, and ``per100_from`` says which (``"now"``,
    ``"last"``, ``"both"``)."""
    out: dict = {}
    for team in set(now) | set(last):
        a, b = now.get(team) or {}, last.get(team) or {}
        n = int(a.get("games") or 0)
        rated_now = any(k in a for k in BETTER)
        rated_last = any(k in b for k in BETTER)
        if not rated_now and not rated_last:
            continue
        w = 1.0 if not rated_last else 0.0 if not rated_now else n / (n + PRIOR_GAMES)
        prof: dict = {"games_season": n, "games_last": int(b.get("games") or 0), "season_weight": round(w, 3)}
        for k in BETTER:
            va, vb = a.get(k), b.get(k)
            if va is not None and vb is not None:
                prof[k] = w * va + (1 - w) * vb
            elif va is not None:
                prof[k] = va
            elif vb is not None:
                prof[k] = vb
        if "ortg" in prof:
            prof["per100_from"] = ("both" if "ortg" in a and "ortg" in b else "now" if "ortg" in a else "last")
        out[team] = prof
    return out


def ranks(profiles: dict) -> dict:
    """``{team: {stat: rank}}``, 1 = the best end (the most for, the fewest
    against; for pace, the fastest). Ties share the better rank's order by
    team code, so a refresh never shuffles them."""
    out: dict = {t: {} for t in profiles}
    for k, more in BETTER.items():
        have = [(t, p[k]) for t, p in profiles.items() if p.get(k) is not None]
        have.sort(key=lambda tv: ((-tv[1]) if more else tv[1], tv[0]))
        for i, (t, _v) in enumerate(have):
            out[t][k] = i + 1
    return out


def league_means(profiles: dict) -> dict:
    """``{stat: the average team's value}`` over the rated teams."""
    out: dict = {}
    for k in BETTER:
        vs = [p[k] for p in profiles.values() if p.get(k) is not None]
        if vs:
            out[k] = sum(vs) / len(vs)
    return out


def build(now_rows, last_rows, sport: str = "nba", before: str | None = None) -> dict:
    """``{"teams": {team: profile + ranks}, "league": means, "n", "per100",
    "nights"}`` from this season's and last season's log rows. ``nights`` is
    every team-night of both (`team_games`) — the scan's usage rates read
    it; it is the build's, never the page's."""
    now_g, last_g = team_games(now_rows, sport), team_games(last_rows, sport)
    prof = blend(season_profiles(now_g, before=before), season_profiles(last_g))
    rk = ranks(prof)
    for t, p in prof.items():
        p["ranks"] = rk.get(t, {})
    return {"teams": prof, "league": league_means(prof), "n": len(prof),
            "per100": any("ortg" in p for p in prof.values()), "nights": {**last_g, **now_g}}


def board_profiles(conn, sport: str, date: str) -> dict:
    """`build` for a board on ``date``: this season walk-forward, last season
    whole."""
    from ..seasons import season_of
    season = season_of(sport, date)
    return build(load_rows(conn, sport, season), load_rows(conn, sport, season - 1), sport, before=date)
