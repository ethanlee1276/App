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

SHOT QUALITY (engine/nhl/xg.py, our own expected goals from the league's
play-by-play). Where the model has a player's shots, his shooting % regresses
toward what his shots were worth rather than a flat position rate; a goal
market reads the 5-on-5 chances the opponent allows a game times how its
starter does against chances (goals allowed ÷ expected); team strength
mixes expected goals for and against into goals for and against
(XG_TEAM_BLEND); and THE POWER PLAY is its own step — a skater on a unit
(PP1/PP2, read from who scores and shoots on it) has the power-play share
of his output moved by the power-play chances tonight's opponent concedes
(pp_factor). With no shot data everything reads as before.

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

# --- Scalpy NHL 1.0 (Ethan, 2026-10-03) -------------------------------------
#: "Volume over finishing": a goal is a SHOT times a shooting percentage, and
#: the percentage is regressed toward his position's league rate by this
#: many shots — 5 goals on 14 shots is not a 35% shooter.
SH_PRIOR_SHOTS = 200.0
#: How far the opposing starter can move a goal-driven market, either way.
#: Goals against = shots against × (1 − save%), so the goalie REPLACES the
#: team goals-against tilt (which already carried him) rather than stacking.
GOALIE_CAP = 0.20
#: Early-season mode: the share of a team's strength taken from THIS season
#: by games played, the rest from last season — "we absolutely cannot look
#: at five games and say Team A is massively better".
SEASON_BLEND = ((6, 0.25), (12, 0.35), (25, 0.50), (29, 0.60))
SEASON_BLEND_LATE = 0.70
#: Second night of a back-to-back: the tired side's expected goals.
B2B_FACTOR = 0.97
#: A role is "unstable" when his last 5 games' ice time is this far off the
#: 10 before them, or he dressed in fewer than ROLE_MIN_GAMES of his last 10
#: team games — Scalpy passes the prop.
ROLE_SWING = 0.25
ROLE_MIN_GAMES = 6
#: A probable starter must hold at least this share of his team's last
#: STARTER_WINDOW starts before a saves (or goalie-driven) bet stands.
STARTER_SHARE = 0.60
#: Scalpy's win-first grades, by modeled hit probability. C (2026-10-03)
#: is the band between the board's shared 55% bar and Scalpy's 65% B line —
#: on the board since the NHL floor came down to the other leagues', and
#: graded so a reader can see it is not a B.
GRADES = ((0.75, "A+"), (0.70, "A"), (0.65, "B"), (0.55, "C"))
# --- Shot quality (engine/nhl/xg.py, 2026-10-03) ----------------------------
#: Every number below is a plain prior, written down before any backtest —
#: the walk-forward ranking (engine.rankfit) judges whether they help.
#: A goal-market shooting % is regressed toward the percentage HIS SHOTS
#: WERE WORTH (his expected goals ÷ his shots on goal) instead of his
#: position's flat rate — a net-front tipper and a point shooter do not
#: share a prior. That expected rate is itself shrunk toward the position
#: rate by this many shots on goal.
XSH_PRIOR_SHOTS = 60.0
#: A team's strength reads its goals AND its expected goals: this share of
#: each side's for/against ratio comes from xG (chances are steadier than
#: finishing over a month of games), the rest from goals.
XG_TEAM_BLEND = 0.5
#: A goalie's skill is goals allowed ÷ expected goals faced (below 1 =
#: he stops more than the shots were worth), shrunk toward 1 by this many
#: expected goals of league-average goaltending — about ten games' worth.
GSAX_PRIOR_XGA = 30.0
#: Finishing luck worth naming: goals this far above or below expected.
LUCK_GOALS = 2.5

# --- The power-play role (engine/nhl/xg.power_play, 2026-10-03) ------------
#: Only the power-play share of a skater's output moves with how many
#: power-play chances tonight's opponent concedes (its PP expected goals
#: against a game — penalties taken and penalty kill in one number). The
#: share is his PP points ÷ points (PP attempts ÷ attempts for shots),
#: shrunk toward PP_SHARE_PRIOR by PP_SHARE_PRIOR_N; the opponent's ratio
#: is shrunk toward 1 by PP_OPP_PRIOR_GAMES; the move is capped at PP_CAP.
#: A skater on neither unit is not moved.
PP_SHARE_PRIOR = 0.20
PP_SHARE_PRIOR_N = 5.0
PP_OPP_PRIOR_GAMES = 20.0
PP_CAP = 0.08

#: The prop hierarchy — the most stable market first.
PROP_TIER = {"sog": 1, "saves": 2, "points": 3, "assists": 4, "blocks": 4, "goals": 5, "anytime_goal": 5}

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
        out[grp]["sh"] = (t.get("goals", 0.0) / t["sog"]) if t.get("sog") else 0.09
    g = tot.get("G") or {}
    out["sv"] = (g.get("saves", 0) / g["shots_against"]) if g.get("shots_against") else LEAGUE_SV
    return out


def season_weight(gp: int) -> float:
    """This season's share of a team's strength after ``gp`` games — the
    Scalpy early-season schedule (75/25 the first two weeks, 30/70 by game
    30). The rest is last season."""
    for upto, w in SEASON_BLEND:
        if gp <= upto:
            return w
    return SEASON_BLEND_LATE


def _profile(games: list) -> dict:
    acc = {"gf": [0.0, 0.0], "ga": [0.0, 0.0], "sog_for": [0.0, 0.0], "sog_against": [0.0, 0.0]}
    for i, (gf, ga, sf, sa) in enumerate(games):
        w = _w(i, TEAM_HALF_LIFE)
        for k, v in (("gf", gf), ("ga", ga), ("sog_for", sf), ("sog_against", sa)):
            if v is not None:
                acc[k][0] += w * float(v)
                acc[k][1] += w
    out = {k: (s / wt if wt else None) for k, (s, wt) in acc.items()}
    out["n"] = len(games)
    return out


def team_profiles(conn, seasons=None) -> dict:
    """{team: {"gf", "ga", "sog_for", "sog_against", "n", "gp_season"}} per
    game, decay weighted, from the games table (goals) and the box-score
    shots carried in each game's extra.

    EARLY-SEASON MODE (Scalpy NHL 1.0): the newest season and the one before
    are profiled SEPARATELY and blended by how many games the newest has —
    `season_weight` — so five October games cannot overrule a full season."""
    import json as _json
    q = "SELECT home, away, home_score, away_score, extra, period, season FROM games WHERE sport='nhl' " \
        "AND home_score IS NOT NULL"
    args: list = []
    if seasons:
        q += f" AND season IN ({','.join('?' * len(seasons))})"
        args += list(seasons)
    by: dict = {}
    for home, away, hs, as_, extra, _day, season in conn.execute(q + " ORDER BY period DESC", args):
        try:
            ex = _json.loads(extra or "{}")
        except ValueError:
            ex = {}
        for team, gf, ga, sf, sa in ((home, hs, as_, ex.get("home_sog"), ex.get("away_sog")),
                                    (away, as_, hs, ex.get("away_sog"), ex.get("home_sog"))):
            by.setdefault(team, {}).setdefault(int(season or 0), []).append((float(gf), float(ga), sf, sa))
    newest = max((s for t in by.values() for s in t), default=0)
    out = {}
    for team, per in by.items():
        cur, prior = per.get(newest, []), [g for s in sorted(per, reverse=True) if s != newest for g in per[s]]
        if not prior or not cur:
            prof = _profile(cur or prior)
            prof["gp_season"] = len(cur)
            out[team] = prof
            continue
        a, b, w = _profile(cur), _profile(prior), season_weight(len(cur))
        prof = {k: (w * a[k] + (1 - w) * b[k]) if a[k] is not None and b[k] is not None else (a[k] if a[k] is not None else b[k])
                for k in ("gf", "ga", "sog_for", "sog_against")}
        prof["n"], prof["gp_season"], prof["season_weight"] = a["n"] + b["n"], len(cur), w
        out[team] = prof
    return out


def regressed_sv(p: dict, league: dict) -> float | None:
    """A goalie's save rate over his recent games, shrunk toward the league
    by PRIOR_SHOTS — "never let a three-game hot streak overpower a
    multi-season baseline"."""
    games = [g for g in (p or {}).get("games") or [] if g.get("shots_against", 0) > 0]
    if not games:
        return None
    lsv = league.get("sv", LEAGUE_SV)
    saves = sum(g.get("saves", 0) for g in games)
    shots = sum(g.get("shots_against", 0) for g in games)
    return (saves + lsv * PRIOR_SHOTS) / (shots + PRIOR_SHOTS)


def raw_sv(p: dict, last: int = 15) -> float | None:
    """His plain save rate over his newest ``last`` games in net — the hot
    or cold run Edge Hunter sets against the regressed baseline above."""
    games = [g for g in (p or {}).get("games") or [] if g.get("shots_against", 0) > 0][:last]
    shots = sum(g.get("shots_against", 0) for g in games)
    return sum(g.get("saves", 0) for g in games) / shots if shots else None


def team_sv(players: dict, team: str, league: dict) -> float | None:
    """Every goalie of this team pooled — what the team's goals-against
    already carries, so tonight's starter is measured against it."""
    pool = {"position": "G", "games": [g for p in players.values() if p["position"] == "G"
                                       and p["team"] == team for g in p["games"]]}
    return regressed_sv(pool, league)


def goalie_factor(opp_sv: float | None, league: dict) -> float:
    """How many more (or fewer) goals the opposing starter lets in than a
    league-average one: (1 − his save%) ÷ (1 − league save%), capped."""
    if opp_sv is None:
        return 1.0
    lsv = league.get("sv", LEAGUE_SV)
    f = (1.0 - opp_sv) / max(1.0 - lsv, 1e-6)
    return max(1 - GOALIE_CAP, min(1 + GOALIE_CAP, f))


def _league_avg(teams: dict, key: str) -> float | None:
    vals = [t[key] for t in teams.values() if t.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def attach_xg(teams: dict, xg_teams: dict | None) -> dict:
    """Each team's expected goals for and against a game (all strengths and
    5-on-5) from engine.nhl.xg.summaries, beside its goals. In place."""
    for team, s in (xg_teams or {}).items():
        t, n = teams.get(team), s.get("games") or 0
        if t is None or not n:
            continue
        t.update(xgf=s["xgf"] / n, xga=s["xga"] / n, xgf_ev=s["xgf_ev"] / n, xga_ev=s["xga_ev"] / n,
                 xg_games=n)
        if s.get("xga_pp") is not None:
            t.update(xgf_pp=s["xgf_pp"] / n, xga_pp=s["xga_pp"] / n)
    return teams


def pp_share(pp: dict | None, market: str) -> float | None:
    """The share of his output that comes on the power play, shrunk."""
    if not pp or market == "blocks":
        return None
    num, den = (pp["pp_iff"], pp["iff"]) if market == "sog" else (pp["pp_points"], pp["points"])
    return (num + PP_SHARE_PRIOR * PP_SHARE_PRIOR_N) / (den + PP_SHARE_PRIOR_N)


def opp_pp_ratio(teams: dict, opponent: str) -> float | None:
    """The power-play chances this opponent concedes a game against the
    league (shrunk toward 1), or None without shot data."""
    t, avg = teams.get(opponent) or {}, _league_avg(teams, "xga_pp")
    if t.get("xga_pp") is None or not avg:
        return None
    n = t.get("xg_games", 0)
    return 1.0 + (t["xga_pp"] / avg - 1.0) * n / (n + PP_OPP_PRIOR_GAMES)


def pp_factor(pp: dict | None, market: str, teams: dict, opponent: str) -> float:
    """1 + (his PP share) × (the opponent's PP ratio − 1), capped; 1 for a
    skater on neither unit or without shot data."""
    share, ratio = pp_share(pp, market), opp_pp_ratio(teams, opponent)
    if share is None or ratio is None or not (pp or {}).get("unit"):
        return 1.0
    return max(1 - PP_CAP, min(1 + PP_CAP, 1.0 + share * (ratio - 1.0)))


def _blend_xg(teams: dict, t: dict, key: str, raw: float) -> float:
    """``raw`` (this side's goals ratio to the league) with XG_TEAM_BLEND of
    its expected-goals ratio mixed in, when both the team and the league
    carry xG — each ratio against its own league average, so the scales
    never mix."""
    xkey = "x" + key
    xavg = _league_avg(teams, xkey)
    if t.get(xkey) is None or not xavg:
        return raw
    return (1 - XG_TEAM_BLEND) * raw + XG_TEAM_BLEND * t[xkey] / xavg


def goalie_skill(g: dict | None) -> float | None:
    """Goals he allowed ÷ the expected goals he faced, shrunk toward 1 by
    GSAX_PRIOR_XGA (None without a record). Below 1 stops more than
    the shots were worth."""
    if not g or not g.get("xga"):
        return None
    return (g["ga"] + GSAX_PRIOR_XGA) / (g["xga"] + GSAX_PRIOR_XGA)


def expected_sh(xp: dict | None, league_sh: float) -> float | None:
    """The shooting percentage his shots on goal were worth (ixG ÷ shots
    on goal), shrunk toward his position's rate by XSH_PRIOR_SHOTS."""
    if not xp or not xp.get("sog"):
        return None
    return (xp["ixg"] + league_sh * XSH_PRIOR_SHOTS) / (xp["sog"] + XSH_PRIOR_SHOTS)


def opp_factor(teams: dict, opponent: str, kind: str) -> float:
    """How much more (or less) of a stat this opponent gives up than the
    league, shrunk toward 1 and capped at ±OPP_CAP."""
    key = {"sog": "sog_against", "goals": "ga", "sog_for": "sog_for", "xga": "xga_ev"}[kind]
    t, avg = teams.get(opponent) or {}, _league_avg(teams, key)
    if not t or t.get(key) is None or not avg:
        return 1.0
    n = t.get("n", 0) if kind != "xga" else t.get("xg_games", 0)
    raw = t[key] / avg
    if kind == "goals":
        raw = _blend_xg(teams, t, "ga", raw)
    shrunk = 1.0 + (raw - 1.0) * n / (n + OPP_PRIOR_GAMES)
    return max(1 - OPP_CAP, min(1 + OPP_CAP, shrunk))


# --- skaters ------------------------------------------------------------------
def skater_projection(p: dict, market: str, league: dict, teams: dict, opponent: str,
                      opp_sv: float | None = None, xp: dict | None = None,
                      opp_skill: float | None = None, pp: dict | None = None) -> dict | None:
    """{"mean", "disp", "toi", "rate60", "opp", "n", ...} for one skater and
    market. ``opp_sv`` is the opposing probable starter's regressed save%:
    when given, a goal-driven market reads shots allowed × that goalie in
    place of the team's raw goals-against.

    SHOT QUALITY, when the xG model has his shots: ``xp`` is his
    engine.nhl.xg player summary (his finishing regresses toward what his
    shots were worth), and ``opp_skill`` the opposing starter's
    goalie_skill — then a goal-driven market reads the chances that team
    allows (its xG against a game) × how that goalie does against them,
    which replaces both the shots-allowed tilt and the save rate. The
    chances read are 5-on-5; the power play is its own step: ``pp`` is his
    engine.nhl.xg.power_play row, and pp_factor moves only the power-play
    share of his output by the chances the opponent concedes shorthanded."""
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
    goal_market = market in ("goals", "anytime_goal", "points", "assists")
    if goal_market and opp_skill is not None and (teams.get(opponent) or {}).get("xga_ev") is not None:
        opp = opp_factor(teams, opponent, "xga") * max(1 - GOALIE_CAP, min(1 + GOALIE_CAP, opp_skill))
    elif goal_market and opp_sv is not None:
        opp = opp_factor(teams, opponent, "sog") * goalie_factor(opp_sv, league)
    else:
        opp = opp_factor(teams, opponent, _OPP_KIND[market])
    ppf = pp_factor(pp, market, teams, opponent)
    opp *= ppf
    mean = rate60 * toi / 60.0 * opp
    sh = xsh = None
    if market in ("goals", "anytime_goal"):
        # VOLUME OVER FINISHING: shots per 60 × ice time × a shooting % that
        # is regressed hard toward his position's league rate.
        sog_prior = (league.get(grp) or {}).get("sog", 0.0)
        sn = sd = 0.0
        g_n = s_n = 0.0
        for i, g in enumerate(games):
            w = _w(i, RATE_HALF_LIFE)
            sn += w * g.get("sog", 0.0)
            sd += w * g["toi"]
            g_n += g.get("goals", 0.0)
            s_n += g.get("sog", 0.0)
        sog60 = (sn + sog_prior * PRIOR_MINUTES / 60.0) / (sd + PRIOR_MINUTES) * 60.0
        lsh = (league.get(grp) or {}).get("sh", 0.09)
        xsh = expected_sh(xp, lsh)
        sh = (g_n + (xsh if xsh is not None else lsh) * SH_PRIOR_SHOTS) / (s_n + SH_PRIOR_SHOTS)
        mean = sog60 * toi / 60.0 * sh * opp
        rate60 = sog60 * sh
    vals = [g.get(stat, 0.0) for g in games]
    disp = 1.0
    if market in ("sog", "blocks") and len(vals) >= 5:
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
        own = (v / m) if m > 0 else SOG_DISPERSION
        k = len(vals) / (len(vals) + 20.0)
        disp = max(1.0, k * own + (1 - k) * SOG_DISPERSION)
    t5 = [g["toi"] for g in games[:5]]
    t10 = [g["toi"] for g in games[5:15]]
    swing = (abs(sum(t5) / len(t5) / (sum(t10) / len(t10)) - 1.0)
             if len(t5) == 5 and len(t10) >= 5 and sum(t10) else 0.0)
    return {"mean": round(mean, 4), "disp": round(disp, 3), "toi": round(toi, 2), "rate60": round(rate60, 3),
            "opp": round(opp, 3), "n": len(games), "recent": vals[:12],
            "sh": round(sh, 4) if sh is not None else None, "toi_swing": round(swing, 3),
            "xsh": round(xsh, 4) if xsh is not None else None,
            "shot_model": "xg" if goal_market and opp_skill is not None
            and (teams.get(opponent) or {}).get("xga_ev") is not None else "shots",
            "pp_unit": (pp or {}).get("unit"), "pp_factor": round(ppf, 3)}


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


def starter_share(players: dict, team: str, name: str) -> float:
    """``name``'s share of his team's last STARTER_WINDOW starts."""
    dates = []
    for n, p in players.items():
        if p["position"] != "G" or p["team"] != team:
            continue
        dates += [(g["date"], n) for g in p["games"] if g.get("started")]
    recent = sorted(dates, reverse=True)[:STARTER_WINDOW]
    return (sum(1 for _d, n in recent if n == name) / len(recent)) if recent else 0.0


def scalpy_grade(prob: float, flags=()) -> str:
    """A+ / A / B / C / Pass by modeled hit probability; any risk flag keeps a
    row out of A+ ("requires stable role ... no major goalie uncertainty")."""
    for bar, label in GRADES:
        if prob >= bar:
            return "A" if (label == "A+" and flags) else label
    return "Pass"


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
def team_lambdas(teams: dict, home: str, away: str, rested: dict | None = None) -> tuple[float, float] | None:
    """Expected regulation goals (home, away). ``rested`` = {team: False}
    marks the second night of a back-to-back (B2B_FACTOR) — an adjustment,
    never a thesis on its own."""
    avg = _league_avg(teams, "gf")
    h, a = teams.get(home), teams.get(away)
    if not avg or not h or not a:
        return None

    ga_avg = _league_avg(teams, "ga") or avg

    def strength(t, key):
        n = t.get("n", 0)
        raw = _blend_xg(teams, t, key, t[key] / (avg if key == "gf" else ga_avg))
        return 1.0 + (raw - 1.0) * n / (n + TEAM_PRIOR_GAMES)
    # Regulation goals: the per-game figures include overtime and shootout
    # goals, about 0.1 a game — taken back out here.
    reg = avg * 0.97
    lh = reg * strength(h, "gf") * strength(a, "ga") * HOME_EDGE
    la = reg * strength(a, "gf") * strength(h, "ga") / HOME_EDGE
    rested = rested or {}
    if rested.get(home) is False and rested.get(away) is not False:
        lh *= B2B_FACTOR
    if rested.get(away) is False and rested.get(home) is not False:
        la *= B2B_FACTOR
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
