"""The NHL model: skater and goalie props, and the three game lines.

Ethan, 2026-10-03: "start working on the most likely bet model and the
edge model for NHL. Look into all data and tools we can use for most likely
bets when it comes to goal scorers ... look at all the markets, add in all
that shit."

THE MARKETS (the ones a US book hangs on an NHL game, The Odds API's keys):
  skaters  shots on goal (sog), points, goals, assists, blocked shots
           (blocks), and the anytime goal scorer (anytime_goal — "he
           scores", the same yes/no shape as the anytime touchdown)
  goalies  saves
  games    moneyline (overtime and shootout included), puck line (±1.5),
           total goals (the shootout winner counts as one goal, as books
           grade it)

HOW A SKATER IS PROJECTED. Hockey is a rate game: a player's shots come
from his ice time, so every stat is a per-60 RATE times the minutes he will
play. The rate is his recent games, decay-weighted (RATE_HALF_LIFE games),
shrunk toward his position's league rate by PRIOR_MINUTES of ice time — a
fourth-liner with three hot games does not become a sniper. Minutes are his
recent ice time (TOI_HALF_LIFE). The opponent moves it: how many shots (or
goals) that team allows a game against the league, from its own games,
shrunk toward average and capped at ±OPP_CAP.

THE COUNTS. Goals, assists and points are Poisson in their rate; shots and
blocks are over-dispersed (a negative binomial whose spread comes from the
player's own game-to-game variance, shrunk toward SOG_DISPERSION). The
anytime goal is P(goals ≥ 1) = 1 − e^−λ.

A GOALIE'S SAVES. The probable starter only (the goalie who started most
of his team's last STARTER_WINDOW games — nobody confirms starters this
early, and the card says so). Shots against are his team's recent shots
allowed times the opponent's shot rate; his save rate is shrunk toward the
league by PRIOR_SHOTS. Saves are shots × save rate, with the spread of both.

THE GAMES. Each team's goals for and against a game, decay-weighted over
its recent games and shrunk toward the league, give each side an expected
goal count; home ice is HOME_EDGE. Regulation is two Poissons; a tie goes
to overtime/shootout, won by the home side OT_HOME of the time, and adds
one goal to the total. The puck line can only be covered in regulation.

Nothing here is fitted to a backtest: every constant below is a plain
prior, written down, and the record and the walk-forward ranking measure
(engine.rankfit, which turns each market's Most Likely shelf on by itself)
are what judge it. Standard library only.
"""
from __future__ import annotations

import math

RATE_HALF_LIFE = 12.0
TOI_HALF_LIFE = 6.0
RECENT_GAMES = 40
PRIOR_MINUTES = 120.0
OPP_PRIOR_GAMES = 20.0
OPP_CAP = 0.15
SOG_DISPERSION = 1.25
STARTER_WINDOW = 10
PRIOR_SHOTS = 600.0
LEAGUE_SV = 0.900
HOME_EDGE = 1.04
OT_HOME = 0.52
TEAM_HALF_LIFE = 25.0
TEAM_PRIOR_GAMES = 15.0
MAX_GOALS = 14

SKATER_MARKETS = ("sog", "points", "goals", "assists", "blocks", "anytime_goal")
GOALIE_MARKETS = ("saves",)
MARKET_LABELS = {"sog": "Shots on Goal", "points": "Points", "goals": "Goals", "assists": "Assists",
                 "blocks": "Blocked Shots", "anytime_goal": "Anytime Goal", "saves": "Saves",
                 "toi": "Time on Ice", "hits": "Hits", "ppg": "Power-Play Goals",
                 "shots_against": "Shots Against", "goals_against": "Goals Against", "started": "Started"}
#: The stat each market's rate is built from (anytime_goal rides goals).
_STAT = {"sog": "sog", "points": "points", "goals": "goals", "assists": "assists",
         "blocks": "blocks", "anytime_goal": "goals"}
#: Which opponent number moves each market: shots allowed, or goals allowed.
_OPP_KIND = {"sog": "sog", "blocks": "sog_for", "points": "goals", "goals": "goals",
             "assists": "goals", "anytime_goal": "goals"}


# --- small maths ----------------------------------------------------------
def _w(i: int, half_life: float) -> float:
    return 0.5 ** (i / half_life)


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def nbinom_pmf(k: int, mean: float, disp: float) -> float:
    """Negative binomial by mean and variance/mean ratio (disp > 1); falls
    back to Poisson at disp ≤ 1."""
    if disp <= 1.0001 or mean <= 0:
        return poisson_pmf(k, mean)
    p = 1.0 / disp
    r = mean * p / (1 - p)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1 - p))


def p_over(line: float, mean: float, disp: float = 1.0) -> float:
    """P(count > line) for a half-point (or whole) line; a whole-number
    line's push is excluded from both sides, as books grade it."""
    k_max = int(math.floor(line))
    under = sum(nbinom_pmf(k, mean, disp) for k in range(0, k_max + 1))
    push = nbinom_pmf(k_max, mean, disp) if float(line).is_integer() else 0.0
    over = 1.0 - under
    return over / (1.0 - push) if push < 1 else 0.0


def normal_over(line: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return 1.0 if mean > line else 0.0
    z = (line + (0.5 if float(line).is_integer() else 0.0) - mean) / sd
    return 0.5 * math.erfc(z / math.sqrt(2))


# --- history ----------------------------------------------------------------
def player_games(conn, teams: set | None = None, seasons=None) -> dict:
    """{player: {"team", "position", "games": [per-game dicts, newest first]}}
    from player_game_logs (sport nhl). A traded player's team is his newest."""
    q = ("SELECT player, team, opponent, position, home, period, market, value FROM player_game_logs "
         "WHERE sport='nhl'")
    args: list = []
    if seasons:
        q += f" AND season IN ({','.join('?' * len(seasons))})"
        args += list(seasons)
    out: dict = {}
    for r in conn.execute(q + " ORDER BY period DESC", args):
        p = out.setdefault(r[0], {"team": r[1], "position": r[3], "games": {}})
        g = p["games"].setdefault(r[5], {"date": r[5], "team": r[1], "opponent": r[2], "home": r[4]})
        g[r[6]] = float(r[7] or 0)
    for _name, p in out.items():
        games = sorted(p["games"].values(), key=lambda g: g["date"], reverse=True)[:RECENT_GAMES]
        p["games"] = games
        if games:
            p["team"] = games[0]["team"]
    if teams:
        out = {k: v for k, v in out.items() if v["team"] in teams}
    return out


def league_rates(players: dict) -> dict:
    """Per-60 rates by position group (F, D) for each skater stat, and the
    league save rate — the priors every player is shrunk toward."""
    tot: dict = {}
    for p in players.values():
        grp = "G" if p["position"] == "G" else ("D" if p["position"] == "D" else "F")
        for g in p["games"]:
            t = tot.setdefault(grp, {"toi": 0.0})
            t["toi"] += g.get("toi", 0.0)
            for s in ("sog", "points", "goals", "assists", "blocks", "saves", "shots_against"):
                t[s] = t.get(s, 0.0) + g.get(s, 0.0)
    out = {}
    for grp, t in tot.items():
        mins = max(t["toi"], 1.0)
        out[grp] = {s: t.get(s, 0.0) / mins * 60.0 for s in ("sog", "points", "goals", "assists", "blocks")}
    g = tot.get("G") or {}
    out["sv"] = (g.get("saves", 0) / g["shots_against"]) if g.get("shots_against") else LEAGUE_SV
    return out


def team_profiles(conn, seasons=None) -> dict:
    """{team: {"gf", "ga", "sog_for", "sog_against", "n"}} per game, decay
    weighted, from the games table (goals) and the box-score shots carried
    in each game's extra."""
    import json as _json
    q = "SELECT home, away, home_score, away_score, extra, period FROM games WHERE sport='nhl' " \
        "AND home_score IS NOT NULL"
    args: list = []
    if seasons:
        q += f" AND season IN ({','.join('?' * len(seasons))})"
        args += list(seasons)
    by: dict = {}
    for home, away, hs, as_, extra, _day in conn.execute(q + " ORDER BY period DESC", args):
        try:
            ex = _json.loads(extra or "{}")
        except ValueError:
            ex = {}
        for team, gf, ga, sf, sa in ((home, hs, as_, ex.get("home_sog"), ex.get("away_sog")),
                                    (away, as_, hs, ex.get("away_sog"), ex.get("home_sog"))):
            by.setdefault(team, []).append((float(gf), float(ga), sf, sa))
    out = {}
    for team, games in by.items():
        acc = {"gf": [0.0, 0.0], "ga": [0.0, 0.0], "sog_for": [0.0, 0.0], "sog_against": [0.0, 0.0]}
        for i, (gf, ga, sf, sa) in enumerate(games):
            w = _w(i, TEAM_HALF_LIFE)
            for k, v in (("gf", gf), ("ga", ga), ("sog_for", sf), ("sog_against", sa)):
                if v is not None:
                    acc[k][0] += w * float(v)
                    acc[k][1] += w
        out[team] = {k: (s / wt if wt else None) for k, (s, wt) in acc.items()}
        out[team]["n"] = len(games)
    return out


def _league_avg(teams: dict, key: str) -> float | None:
    vals = [t[key] for t in teams.values() if t.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def opp_factor(teams: dict, opponent: str, kind: str) -> float:
    """How much more (or less) of a stat this opponent gives up than the
    league, shrunk toward 1 and capped at ±OPP_CAP."""
    key = {"sog": "sog_against", "goals": "ga", "sog_for": "sog_for"}[kind]
    t, avg = teams.get(opponent) or {}, _league_avg(teams, key)
    if not t or t.get(key) is None or not avg:
        return 1.0
    n = t.get("n", 0)
    raw = t[key] / avg
    shrunk = 1.0 + (raw - 1.0) * n / (n + OPP_PRIOR_GAMES)
    return max(1 - OPP_CAP, min(1 + OPP_CAP, shrunk))


# --- skaters ------------------------------------------------------------------
def skater_projection(p: dict, market: str, league: dict, teams: dict, opponent: str) -> dict | None:
    """{"mean", "disp", "toi", "rate60", "opp", "n"} for one skater and market."""
    games = [g for g in p["games"] if g.get("toi", 0) > 0]
    if len(games) < 3:
        return None
    stat = _STAT[market]
    grp = "D" if p["position"] == "D" else "F"
    prior = (league.get(grp) or {}).get(stat, 0.0)
    num = den = 0.0
    for i, g in enumerate(games):
        w = _w(i, RATE_HALF_LIFE)
        num += w * g.get(stat, 0.0)
        den += w * g["toi"]
    rate60 = (num + prior * PRIOR_MINUTES / 60.0) / (den + PRIOR_MINUTES) * 60.0
    tn = td = 0.0
    for i, g in enumerate(games[:15]):
        w = _w(i, TOI_HALF_LIFE)
        tn += w * g["toi"]
        td += w
    toi = tn / td
    opp = opp_factor(teams, opponent, _OPP_KIND[market])
    mean = rate60 * toi / 60.0 * opp
    vals = [g.get(stat, 0.0) for g in games]
    disp = 1.0
    if market in ("sog", "blocks") and len(vals) >= 5:
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
        own = (v / m) if m > 0 else SOG_DISPERSION
        k = len(vals) / (len(vals) + 20.0)
        disp = max(1.0, k * own + (1 - k) * SOG_DISPERSION)
    return {"mean": round(mean, 4), "disp": round(disp, 3), "toi": round(toi, 2), "rate60": round(rate60, 3),
            "opp": round(opp, 3), "n": len(games), "recent": vals[:12]}


def skater_prob(proj: dict, market: str, line: float, side: str) -> float:
    """Our chance of this side, from the projection."""
    if market == "anytime_goal":
        p = 1.0 - math.exp(-proj["mean"])
        return p if str(side).upper() in ("OVER", "YES") else 1.0 - p
    over = p_over(line, proj["mean"], proj["disp"])
    return over if str(side).upper() in ("OVER", "YES") else 1.0 - over


# --- goalies ------------------------------------------------------------------
def probable_starter(players: dict, team: str) -> str | None:
    """The goalie who started most of his team's recent games."""
    starts: dict = {}
    dates: list = []
    for name, p in players.items():
        if p["position"] != "G" or p["team"] != team:
            continue
        for g in p["games"]:
            if g.get("started"):
                dates.append((g["date"], name))
    for _d, name in sorted(dates, reverse=True)[:STARTER_WINDOW]:
        starts[name] = starts.get(name, 0) + 1
    return max(starts, key=starts.get) if starts else None


def goalie_projection(p: dict, league: dict, teams: dict, team: str, opponent: str) -> dict | None:
    games = [g for g in p["games"] if g.get("shots_against", 0) > 0]
    if len(games) < 3:
        return None
    sv_saves = sum(g.get("saves", 0) for g in games)
    sv_shots = sum(g.get("shots_against", 0) for g in games)
    lsv = league.get("sv", LEAGUE_SV)
    sv = (sv_saves + lsv * PRIOR_SHOTS) / (sv_shots + PRIOR_SHOTS)
    own = (teams.get(team) or {}).get("sog_against")
    avg = _league_avg(teams, "sog_against") or 30.0
    shots = (own if own is not None else avg) * opp_factor(teams, opponent, "sog_for")
    mean = shots * sv
    var = shots * SOG_DISPERSION * sv * sv + shots * sv * (1 - sv)
    return {"mean": round(mean, 3), "sd": round(math.sqrt(var), 3), "shots": round(shots, 2), "sv": round(sv, 4),
            "n": len(games), "recent": [g.get("saves", 0.0) for g in games[:12]]}


def goalie_prob(proj: dict, line: float, side: str) -> float:
    over = normal_over(line, proj["mean"], proj["sd"])
    return over if str(side).upper() == "OVER" else 1.0 - over


# --- games ------------------------------------------------------------------
def team_lambdas(teams: dict, home: str, away: str) -> tuple[float, float] | None:
    """Expected regulation goals (home, away)."""
    avg = _league_avg(teams, "gf")
    h, a = teams.get(home), teams.get(away)
    if not avg or not h or not a:
        return None

    def strength(t, key):
        n = t.get("n", 0)
        return 1.0 + ((t[key] / avg) - 1.0) * n / (n + TEAM_PRIOR_GAMES)
    # Regulation goals: the per-game figures include overtime and shootout
    # goals, about 0.1 a game — taken back out here.
    reg = avg * 0.97
    lh = reg * strength(h, "gf") * strength(a, "ga") * HOME_EDGE
    la = reg * strength(a, "gf") * strength(h, "ga") / HOME_EDGE
    return lh, la


def game_probs(lh: float, la: float) -> dict:
    """Moneyline, puck line and total-goals distribution from the two means."""
    ph = [poisson_pmf(k, lh) for k in range(MAX_GOALS + 1)]
    pa = [poisson_pmf(k, la) for k in range(MAX_GOALS + 1)]
    home_reg = away_reg = tie = 0.0
    home_by2 = away_by2 = 0.0
    totals: dict = {}
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            pr = x * y
            if i > j:
                home_reg += pr
                if i - j >= 2:
                    home_by2 += pr
            elif j > i:
                away_reg += pr
                if j - i >= 2:
                    away_by2 += pr
            else:
                tie += pr
            t = i + j + (1 if i == j else 0)
            totals[t] = totals.get(t, 0.0) + pr
    return {"home_ml": home_reg + tie * OT_HOME, "away_ml": away_reg + tie * (1 - OT_HOME),
            "home_-1.5": home_by2, "away_-1.5": away_by2,
            "home_+1.5": 1.0 - away_by2, "away_+1.5": 1.0 - home_by2,
            "tie": tie, "totals": totals, "lh": lh, "la": la}


def total_over(probs: dict, line: float) -> float:
    over = sum(p for t, p in probs["totals"].items() if t > line)
    push = probs["totals"].get(int(line), 0.0) if float(line).is_integer() else 0.0
    return over / (1.0 - push) if push < 1 else 0.0
