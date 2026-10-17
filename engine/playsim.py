"""Players inside the simulated game — every prop on a team out of the same simulated games.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 9. `engine/drivesim`
replays a game drive by drive, but only as two scores: no player lives in
it. So every same-game ticket on the site is priced with one correlation
per KIND of pair (a quarterback and any receiver: one number; two
receivers: another), whoever the players are. A quarterback with one
receiver who sees a third of the targets and a quarterback who spreads it
six ways get the same number.

THE SIMULATION. Each team's game is played pass by pass and run by run:
the number of passes and runs, each throw's target (by his share of the
team's attempts over its last LOOKBACK games), whether it is caught (his
catch rate), how far (his yards a catch, a gamma draw), and each carry's
ball carrier and yards. Three game-wide shocks touch every player at once:
VOLUME (more plays for everyone), SCRIPT (passes up, runs down — a team
behind throws), and EFFICIENCY (the quarterback's day: every catch more
likely and longer). The quarterback's attempts, completions and yards are
the sum of his receivers', so the board's numbers can never disagree with
each other inside one simulated game.

Nothing in it is a guess that could be measured instead: the three shocks'
sizes and the two gamma shapes are fitted on the training seasons' team
games (`fit_shocks`, `fit_shapes`), and the shares are each team's own.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. For every pair of different
players on one team in the two newest seasons whose props both closed
(either side, any market the sim plays), the four outcomes (both over,
only one, neither) are priced with the closes' own fair chances, joined
two ways: the sim's correlation for those two players, and the one the
parlay pricer uses for that kind of pair (`engine/parlays.relate`, shrunk
as it shrinks). Scored by log loss, averaged within each team-game first
(pairs in one game are not independent), the sim earns a reading only if
it beats the pricer's number with t ≥ MIN_T over MIN_GAMES team-games and
MIN_PAIRS pairs, and in each test season. Until then the pick page shows
which legs move with his in the simulated games and nothing on a ticket
reads it.

Standard library only.
"""

from __future__ import annotations

import bisect
import json
import math
import random
import time

MARKETS = ("pass_att", "pass_cmp", "pass_yds", "targets", "receptions", "rec_yds", "rush_att", "rush_yds")
#: The NFL logs kept carries as `carries` before the carries prop gave them
#: their market's name too (2026-09-27, engine/ingest NFL_USAGE_MARKETS);
#: older seasons have only the first.
CARRIES = "carries"
#: The markets a board prop can be read from.
PROP_MARKETS = ("pass_att", "pass_cmp", "pass_yds", "receptions", "rec_yds", "rush_att", "rush_yds")
LOOKBACK = 8
MIN_GAMES_PROFILE = 3
#: Shrinkage toward league norms, in his own attempts: catch rate, yards a
#: catch, yards a carry. A receiver with 6 targets is mostly the league.
CATCH_PRIOR = (0.64, 20)
YPC_PRIOR = (11.0, 15)
YPR_PRIOR = (4.3, 40)
#: The pseudo-receiver for throws to anyone outside the profile, and the
#: throws with no target at all (spikes, throwaways).
OTHER_CATCH, OTHER_YPC = 0.55, 9.5
#: Carries can lose yards: a carry's yards are a gamma draw shifted down by this.
RUSH_SHIFT = 3.0
DEFAULT_SHOCKS = {"vol_sd": 0.10, "script_sd": 0.12, "eff_sd": 0.14, "k_rec": 1.6, "k_rush": 1.1}
TRIALS_BUILD = 1000
TRIALS_MEASURE = 400
#: Seasons the box measurement reads: two to fit the shocks, the newest two
#: held out. Six seasons of every team's logs would not fit a gigabyte.
MEASURE_SEASONS = 4
BUILD_SECONDS = 10.0
#: The bar.
MIN_T = 2.0
MIN_GAMES = 300
MIN_PAIRS = 1000
STORE = "playsim.json"


def _norm(name):
    from .backtest import _norm as n
    return n(name)


# ---- profiles ----------------------------------------------------------------------------

def team_games(rows) -> dict:
    """rows: (season, week, team, player, market, value) → ``{team:
    [(season, week, {player: {market: value}})]}`` in order."""
    acc: dict = {}
    for season, week, team, player, market, value in rows:
        if value is None:
            continue
        acc.setdefault(team, {}).setdefault((int(season), int(week)), {}).setdefault(player, {})[market] = float(value)
    for g in acc.values():
        for players in g.values():
            for st in players.values():
                if CARRIES in st:
                    st.setdefault("rush_att", st.pop(CARRIES))
    return {t: [(s, w, g[(s, w)]) for (s, w) in sorted(g)] for t, g in acc.items()}


def _shrink(num, den, prior):
    mean, weight = prior
    return (num + mean * weight) / (den + weight)


def profile(games: list) -> dict | None:
    """One team's shares and rates over the games given (its last
    LOOKBACK before the one simulated). A man's share is his targets (or
    carries) over the team's attempts in the games he played."""
    games = games[-LOOKBACK:]
    if len(games) < MIN_GAMES_PROFILE:
        return None
    pa = [sum(p.get("pass_att", 0.0) for p in g.values()) for _s, _w, g in games]
    ra = [sum(p.get("rush_att", 0.0) for p in g.values()) for _s, _w, g in games]
    if not sum(pa) or not sum(ra):
        return None
    last = games[-1][2]
    qb = max(last, key=lambda p: last[p].get("pass_att", 0.0))
    if not last[qb].get("pass_att"):
        return None
    rec, rush = {}, {}
    for i, (_s, _w, g) in enumerate(games):
        for player, st in g.items():
            if st.get("targets"):
                r = rec.setdefault(player, [0.0, 0.0, 0.0, 0.0])
                r[0] += st["targets"]
                r[1] += st.get("receptions", 0.0)
                r[2] += st.get("rec_yds", 0.0)
                r[3] += pa[i]
            if st.get("rush_att"):
                r = rush.setdefault(player, [0.0, 0.0, 0.0])
                r[0] += st["rush_att"]
                r[1] += st.get("rush_yds", 0.0)
                r[2] += ra[i]
    receivers = {p: {"share": t / team, "catch": _shrink(c, t, CATCH_PRIOR), "ypc": _shrink(y, c, YPC_PRIOR)}
                 for p, (t, c, y, team) in rec.items() if team}
    rushers = {p: {"share": n / team, "ypr": _shrink(y, n, YPR_PRIOR)} for p, (n, y, team) in rush.items() if team}
    for group in (receivers, rushers):
        total = sum(v["share"] for v in group.values())
        if total > 1.0:
            for v in group.values():
                v["share"] /= total
    return {"qb": qb, "pass_att": sum(pa) / len(pa), "rush_att": sum(ra) / len(ra),
            "receivers": receivers, "rushers": rushers}


# ---- the simulation -----------------------------------------------------------------------

def _count(rng, lam):
    if lam <= 0:
        return 0
    if lam > 25:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _picker(group: dict, other: bool):
    names = list(group)
    cum, c = [], 0.0
    for n in names:
        c += group[n]["share"]
        cum.append(c)
    if other:
        names.append(None)
        cum.append(max(c, 1.0))
    return names, cum


def simulate(prof: dict, trials: int, rng: random.Random, shocks: dict | None = None) -> dict:
    """``{player: {market: [value per trial]}}`` — the quarterback's
    passing lines are the sum of every throw, his receivers' and the
    pseudo-receiver's."""
    sh = {**DEFAULT_SHOCKS, **(shocks or {})}
    qb = prof["qb"]
    rnames, rcum = _picker(prof["receivers"], True)
    cnames, ccum = _picker(prof["rushers"], False)
    out: dict = {}

    def slot(p, m):
        return out.setdefault(p, {}).setdefault(m, [0.0] * trials)
    for p in prof["receivers"]:
        for m in ("targets", "receptions", "rec_yds"):
            slot(p, m)
    for p in prof["rushers"]:
        for m in ("rush_att", "rush_yds"):
            slot(p, m)
    for m in ("pass_att", "pass_cmp", "pass_yds"):
        slot(qb, m)
    kr, kq = sh["k_rec"], sh["k_rush"]
    rtop, ctop = rcum[-1], (ccum[-1] if ccum else 0.0)
    for t in range(trials):
        v, s, e = rng.gauss(0, sh["vol_sd"]), rng.gauss(0, sh["script_sd"]), rng.gauss(0, sh["eff_sd"])
        n_pass = _count(rng, prof["pass_att"] * math.exp(v + s))
        n_rush = _count(rng, prof["rush_att"] * math.exp(v - s))
        cmp_ = yds = 0.0
        boost = math.exp(e)
        for _ in range(n_pass):
            who = rnames[min(bisect.bisect_right(rcum, rng.random() * rtop), len(rnames) - 1)]
            if who is None:
                c, ypc = OTHER_CATCH, OTHER_YPC
            else:
                st = prof["receivers"][who]
                c, ypc = st["catch"], st["ypc"]
                out[who]["targets"][t] += 1
            c = 1.0 / (1.0 + (1.0 / c - 1.0) * math.exp(-e))
            if rng.random() < c:
                y = rng.gammavariate(kr, ypc * boost / kr)
                cmp_ += 1
                yds += y
                if who is not None:
                    out[who]["receptions"][t] += 1
                    out[who]["rec_yds"][t] += y
        out[qb]["pass_att"][t] = n_pass
        out[qb]["pass_cmp"][t] = cmp_
        out[qb]["pass_yds"][t] = yds
        if not ctop:
            continue
        for _ in range(n_rush):
            i = bisect.bisect_right(ccum, rng.random() * ctop)
            if i >= len(cnames):
                continue
            who = cnames[i]
            ypr = prof["rushers"][who]["ypr"]
            out[who]["rush_att"][t] += 1
            out[who]["rush_yds"][t] += rng.gammavariate(kq, (ypr + RUSH_SHIFT) / kq) - RUSH_SHIFT
    return out


def over_chance(values: list, line: float) -> float | None:
    """Over, with a push counted as half — a whole-number line on a count."""
    if not values:
        return None
    over = sum(1 for x in values if x > line)
    push = sum(1 for x in values if x == line)
    return (over + 0.5 * push) / len(values)


def _ranks(xs):
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def normal_scores(xs: list) -> list:
    """Each value's rank through the normal quantile."""
    from statistics import NormalDist
    q = NormalDist().inv_cdf
    n = len(xs)
    return [q(r / (n + 1)) for r in _ranks(xs)]


def scores_corr(a: list, b: list) -> float | None:
    if len(a) < 20 or len(a) != len(b):
        return None
    sa = math.sqrt(sum(x * x for x in a))
    sb = math.sqrt(sum(y * y for y in b))
    if not sa or not sb:
        return None
    return max(-0.95, min(0.95, sum(x * y for x, y in zip(a, b)) / (sa * sb)))


def normal_scores_corr(xs: list, ys: list) -> float | None:
    """The Gaussian copula's own parameter: the correlation of the two
    series' normal scores (ranks through the normal quantile)."""
    if len(xs) < 20:
        return None
    return scores_corr(normal_scores(xs), normal_scores(ys))


# ---- the pricer's number, and the four outcomes ----------------------------------------------

def prior_rho(sport: str, a: dict, b: dict) -> float:
    """What the parlay pricer joins these two overs with, shrunk the way it
    shrinks an unmeasured number."""
    from . import parlays as P
    rel = P.relate(sport, {**a, "side": "over"}, {**b, "side": "over"})
    return rel.rho if rel.measured else rel.rho * P.RHO_SHRINK


def cells(pa: float, pb: float, rho: float) -> tuple:
    """(both over, a only, b only, neither) under a Gaussian copula."""
    from .parlays import joint_two
    eps = 1e-6
    j = joint_two(pa, pb, rho)
    j = min(max(j, max(0.0, pa + pb - 1.0) + eps), min(pa, pb) - eps)
    return (j, pa - j, pb - j, 1.0 - pa - pb + j)


def log_loss(c: tuple, a_over: bool, b_over: bool) -> float:
    i = (0 if b_over else 1) if a_over else (2 if b_over else 3)
    return -math.log(max(c[i], 1e-9))


# ---- the fits the simulation reads ------------------------------------------------------------

def fit_shocks(tg: dict, seasons) -> dict:
    """Volume and script from each team's passes and runs against its own
    season mean (Poisson noise taken out, since the simulation adds its
    own): passes = exp(v + s), runs = exp(v - s), so their covariance is
    v² − s². Efficiency from yards an attempt beyond what the throws'
    own sampling explains."""
    lp, lr, le, noise = [], [], [], []
    for games in tg.values():
        by: dict = {}
        for s, _w, g in games:
            if s in seasons:
                pa = sum(p.get("pass_att", 0.0) for p in g.values())
                ra = sum(p.get("rush_att", 0.0) for p in g.values())
                py = sum(p.get("pass_yds", 0.0) for p in g.values() if p.get("pass_att"))
                pc = sum(p.get("pass_cmp", 0.0) for p in g.values())
                if pa >= 10 and ra >= 5 and py > 0:
                    by.setdefault(s, []).append((pa, ra, py / pa, pc / pa))
        for rows in by.values():
            if len(rows) < 4:
                continue
            mp = sum(r[0] for r in rows) / len(rows)
            mr = sum(r[1] for r in rows) / len(rows)
            my = sum(r[2] for r in rows) / len(rows)
            for pa, ra, ypa, cr in rows:
                lp.append((math.log(pa / mp), 1.0 / mp))
                lr.append((math.log(ra / mr), 1.0 / mr))
                le.append(math.log(ypa / my))
                k = DEFAULT_SHOCKS["k_rec"]
                noise.append(((1.0 + 1.0 / k) / max(cr, 0.3) - 1.0) / pa)
    if len(lp) < 50:
        return dict(DEFAULT_SHOCKS)
    n = len(lp)
    vp = sum(x * x for x, _ in lp) / n - sum(w for _, w in lp) / n
    vr = sum(x * x for x, _ in lr) / n - sum(w for _, w in lr) / n
    cov = sum(a[0] * b[0] for a, b in zip(lp, lr)) / n
    avg = (vp + vr) / 2.0
    ve = sum(x * x for x in le) / n - sum(noise) / n
    return {**DEFAULT_SHOCKS, "vol_sd": round(math.sqrt(max(0.0, (avg + cov) / 2.0)), 4),
            "script_sd": round(math.sqrt(max(0.0, (avg - cov) / 2.0)), 4),
            "eff_sd": round(math.sqrt(max(0.0, ve)) / 1.37, 4), "n": n}


def fit_shapes(tg: dict, seasons) -> dict:
    """The gamma shapes: given a man's catches in a game, his yards vary by
    n·ypc²/k around n·ypc; carries the same, shifted. k by moments over
    every player-game, ypc his own season's."""
    rec: dict = {}
    rush: dict = {}
    for games in tg.values():
        for s, _w, g in games:
            if s not in seasons:
                continue
            for p, st in g.items():
                if st.get("receptions"):
                    rec.setdefault((p, s), []).append((st["receptions"], st.get("rec_yds", 0.0)))
                if st.get("rush_att"):
                    rush.setdefault((p, s), []).append((st["rush_att"], st.get("rush_yds", 0.0) + RUSH_SHIFT * st["rush_att"]))

    def k_of(groups):
        num = den = 0.0
        for rows in groups.values():
            n_tot = sum(n for n, _ in rows)
            if len(rows) < 4 or n_tot < 10:
                continue
            m = sum(y for _, y in rows) / n_tot
            for n, y in rows:
                num += n * m * m
                den += (y - n * m) ** 2
        return round(num / den, 3) if den else None
    out = {}
    kr, kq = k_of(rec), k_of(rush)
    if kr:
        out["k_rec"] = max(0.5, min(5.0, kr))
    if kq:
        out["k_rush"] = max(0.3, min(5.0, kq))
    return out


# ---- the held-out test ------------------------------------------------------------------------

def reduce_closes(closes: dict) -> dict:
    """``{(norm player, date): (line, fair over)}`` — the line most books
    hung, and the median of their fair over chances at it."""
    from statistics import median
    from .bookrecipe import _fair_over
    out = {}
    for (player, date), books in closes.items():
        lines: dict = {}
        for line, over, under in books.values():
            f = _fair_over({"over_odds": over, "under_odds": under})
            if f is not None:
                lines.setdefault(line, []).append(f)
        if lines:
            line = max(lines, key=lambda x: (len(lines[x]), -x))
            out[(_norm(player), date)] = (line, median(lines[line]))
    return out


def pair_cases(tg: dict, closes: dict, dates: dict, seasons, sport="nfl", trials=TRIALS_MEASURE,
               shocks=None, seed=7) -> list:
    """Every pair of two different players' closes on one team-game in
    `seasons`: [(season, game key, ll_sim, ll_prior, ll_independent)]."""
    rng = random.Random(seed)
    out = []
    for team, games in tg.items():
        for i, (season, week, g) in enumerate(games):
            if season not in seasons:
                continue
            date = dates.get((season, week, team))
            if not date:
                continue
            props = []
            for player, st in g.items():
                for m in PROP_MARKETS:
                    c = closes.get(m, {}).get((_norm(player), date))
                    if c and m in st and st[m] != c[0]:
                        props.append((player, m, c[0], c[1], st[m] > c[0]))
            if len(props) < 2:
                continue
            prof = profile(games[:i])
            if not prof:
                continue
            sim = simulate(prof, trials, rng, shocks)
            key = f"{team}|{season}|{week}"
            for x in range(len(props)):
                for y in range(x + 1, len(props)):
                    a, b = props[x], props[y]
                    if a[0] == b[0]:
                        continue
                    sa, sb = (sim.get(a[0]) or {}).get(a[1]), (sim.get(b[0]) or {}).get(b[1])
                    if not sa or not sb:
                        continue
                    r_sim = normal_scores_corr(sa, sb)
                    if r_sim is None:
                        continue
                    r_pri = prior_rho(sport, {"player": a[0], "team": team, "market": a[1]},
                                      {"player": b[0], "team": team, "market": b[1]})
                    pa, pb = min(max(a[3], 0.02), 0.98), min(max(b[3], 0.02), 0.98)
                    out.append((season, key, log_loss(cells(pa, pb, r_sim), a[4], b[4]),
                                log_loss(cells(pa, pb, r_pri), a[4], b[4]),
                                log_loss(cells(pa, pb, 0.0), a[4], b[4])))
    return out


def verdict(cases: list) -> dict:
    """Clustered by team-game: each game's mean gain, then the t over games."""
    def stat(idx):
        by: dict = {}
        for c in cases:
            by.setdefault(c[1], []).append(c[idx] - c[2])
        g = [sum(v) / len(v) for v in by.values()]
        n = len(g)
        if n < 2:
            return {"games": n, "gain": None, "t": None}
        m = sum(g) / n
        var = sum((x - m) ** 2 for x in g) / (n - 1)
        return {"games": n, "gain": round(m, 5), "t": round(m / math.sqrt(var / n), 2) if var > 0 else None}
    seasons = sorted({c[0] for c in cases})
    vs_prior, vs_indep = stat(3), stat(4)
    by_season = {}
    for s in seasons:
        sub = [c for c in cases if c[0] == s]
        by_season[str(s)] = round(sum(c[3] - c[2] for c in sub) / len(sub), 5) if sub else None
    holds = (len(cases) >= MIN_PAIRS and vs_prior["games"] >= MIN_GAMES and (vs_prior["gain"] or 0) > 0
             and (vs_prior["t"] or 0) >= MIN_T and len(seasons) >= 2 and all((v or 0) > 0 for v in by_season.values()))
    return {"pairs": len(cases), "vs_pricer": vs_prior, "vs_independent": vs_indep, "by_season": by_season,
            "test": seasons, "holds": bool(holds)}


# ---- storage, the box, the ideas file -----------------------------------------------------------

def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1)
    return p


def load() -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def load_rows(conn, sport: str, seasons=None, teams=None) -> list:
    q = ("SELECT season, period, team, player, market, value FROM player_game_logs WHERE sport=? AND market IN (%s)"
         % ",".join("?" * (len(MARKETS) + 1)))
    args = [sport, *MARKETS, CARRIES]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    if teams:
        q += " AND team IN (%s)" % ",".join("?" * len(teams))
        args += list(teams)
    out = []
    for r in conn.execute(q, args):
        try:
            out.append((int(r[0]), int(r[1]), r[2], r[3], r[4], r[5]))
        except (TypeError, ValueError):
            continue
    return out


def measure(conn, sport: str = "nfl") -> dict:
    from .bookmenu import closes_compact
    from .formbook import game_dates
    have = sorted(int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND market='targets'", (sport,)) if r[0] is not None)
    tg = team_games(load_rows(conn, sport, have[-MEASURE_SEASONS:]))
    seasons = sorted({s for games in tg.values() for s, _w, _g in games})
    if len(seasons) < 3:
        return {"note": "fewer than three seasons of logs", "holds": False}
    test, train = set(seasons[-2:]), set(seasons[:-2])
    shocks = {**fit_shocks(tg, train), **fit_shapes(tg, train)}
    closes = {}
    for m in PROP_MARKETS:
        closes[m] = reduce_closes(closes_compact(conn, sport, m))
    cases = pair_cases(tg, closes, game_dates(), test, sport, shocks=shocks)
    return {"shocks": shocks, "verdict": verdict(cases), "train": sorted(train)}


def ideas_section(props, games, board, sport, conn=None):
    if sport not in ("nfl", "cfb"):
        return None
    rows = [r for r in (board or {}).get("recommendations") or []
            if r.get("team") and r.get("market") in PROP_MARKETS and r.get("line") is not None]
    if not rows:
        return {"players": {}, "games": {}}
    saved = load()
    shocks = saved.get("shocks") or {}
    by_team: dict = {}
    for r in rows:
        by_team.setdefault(r["team"], {})[(r["player"], r["market"])] = r
    own = conn is None
    if own:
        from . import db as _db
        conn = _db.connect()
    import sqlite3
    try:
        try:
            latest = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()[0]
        except sqlite3.OperationalError:
            latest = None                                     # a database with no logs table reads empty
        if latest is None:
            return {"players": {}, "games": {}}
        tg = team_games(load_rows(conn, sport, (int(latest) - 1, int(latest)), sorted(by_team)))
    finally:
        if own:
            conn.close()
    rng = random.Random(11)
    start = time.monotonic()
    players, pairs_by_game = {}, {}
    for team in sorted(by_team, key=lambda t: -len(by_team[t])):
        if time.monotonic() - start > BUILD_SECONDS:
            break
        prof = profile(tg.get(team) or [])
        if not prof:
            continue
        sim = simulate(prof, TRIALS_BUILD, rng, shocks)
        legs = [(p, m, r) for (p, m), r in by_team[team].items() if (sim.get(p) or {}).get(m)]
        ns = {(p, m): normal_scores(sim[p][m]) for p, m, _r in legs}
        for p, m, r in legs:
            vals = sim[p][m]
            links = []
            for q, n, s in legs:
                if q == p:
                    continue
                rho = scores_corr(ns[(p, m)], ns[(q, n)])
                if rho is None:
                    continue
                o_a = [x > r["line"] for x in vals]
                o_b = [y > s["line"] for y in sim[q][n]]
                both = sum(1 for x, y in zip(o_a, o_b) if x and y)
                given = both / sum(o_a) if sum(o_a) else None
                links.append({"player": q, "market": n, "line": s["line"], "rho": round(rho, 3),
                              "pricer_rho": round(prior_rho(sport, {"player": p, "team": team, "market": m},
                                                            {"player": q, "team": team, "market": n}), 3),
                              "their_over": round(sum(o_b) / len(o_b), 3),
                              "their_over_given_his": None if given is None else round(given, 3)})
            links.sort(key=lambda x: -abs(x["rho"]))
            players[f"{p}|{m}"] = {"team": team, "line": r["line"], "sim_over": round(over_chance(vals, r["line"]), 3),
                                   "links": links[:4], "trials": TRIALS_BUILD}
            for link in links:
                key = "|".join(sorted((team, r.get("opponent") or "")))
                pair = tuple(sorted(((p, m), (link["player"], link["market"]))))
                pairs_by_game.setdefault(key, {})[pair] = {
                    "a": f"{pair[0][0]} {pair[0][1]}", "b": f"{pair[1][0]} {pair[1][1]}",
                    "rho": link["rho"], "pricer_rho": link["pricer_rho"]}
    games_out = {k: sorted(v.values(), key=lambda x: -abs(x["rho"] - x["pricer_rho"]))[:6] for k, v in pairs_by_game.items()}
    return {"players": players, "games": games_out, "verdict": saved.get("verdict") or {}}


def pick_view(sec, player, market, side="", line=None):
    p = (sec.get("players") or {}).get(f"{player}|{market}")
    return {**p, "verdict": sec.get("verdict") or {}} if p else None


def game_view(sec, home, away):
    rows = (sec.get("games") or {}).get("|".join(sorted((home, away))))
    return {"pairs": rows, "verdict": sec.get("verdict") or {}} if rows else None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Players inside the simulated game, against the parlay pricer's correlations")
    ap.add_argument("--sport", default="nfl", help="nfl or cfb (default nfl)")
    ap.add_argument("--save", action="store_true", help="keep the fitted shocks and the verdict for the pick page")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, a.sport)
    finally:
        conn.close()
    print(f"Players inside the simulated game — {a.sport}")
    if res.get("note"):
        print(f"  {res['note']}")
        return 0
    sh = res["shocks"]
    print(f"  fitted on {res['train']}: volume ±{sh['vol_sd']}, script ±{sh['script_sd']}, the passer's day "
          f"±{sh['eff_sd']}, yards-a-catch shape {sh['k_rec']}, yards-a-carry shape {sh['k_rush']}")
    v = res["verdict"]
    p, i = v["vs_pricer"], v["vs_independent"]
    print(f"  held out {v['test']}: {v['pairs']} pairs over {p['games']} team-games")
    print(f"    against the parlay pricer's number: log loss better by {p['gain']} a pair (t {p['t']}), "
          f"by season {v['by_season']}")
    print(f"    against no correlation at all:      better by {i['gain']} (t {i['t']})")
    print(f"  THE BAR: beats the pricer's number, t ≥ {MIN_T}, ≥ {MIN_GAMES} team-games and {MIN_PAIRS} pairs, "
          f"each test season above zero — {'HOLDS' if v['holds'] else 'does not hold'}")
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
