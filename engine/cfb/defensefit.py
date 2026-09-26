"""How much of a college defence's rating reaches one player: measured.

The college twin of engine/defensefit.py, reading our own college logs
(engine/cfb/defense.wide_rows, FBS against FBS) instead of nflverse, and
asking one more question the NFL fit did not: does the rating add anything
BEYOND the book's implied team total? College touchdowns are priced from
that total (engine/cfb/tds), and a defence's overall scoring record adds
nothing once it is in (tds.defense_multiplier) — so for touchdowns the
number that counts is the gain on top of the total.

For every player-game from week 4 on with three earlier games that season:

    e = his own average in those games (touchdowns: blended with his
        position's rate, as defensefit does)
    d = the opponent's rating for the stat, from games BEFORE this one,
        shrunk toward last season's, minus 1
    t = his team's implied points / the season's average, minus 1

and y ≈ e·(1 + b·d), or y ≈ e·(1 + c·t + b·d), by least squares, fitted on
the other seasons and scored on the held-out one. THE RULE (defensevs
MODEL_STAT_CFB / TRANSFER_CFB): a rating is used where its held-out gain is
positive on average and in at least three of the four seasons; where two
ratings qualify, the larger average wins. Standard library only.
"""
from __future__ import annotations

from .. import defensefit as F
from .. import defensevs as D
from . import defense as CD

#: market -> (groups, the player's columns, form floor); QB rushing is college's own.
MARKETS = {
    "pass_yds": (("QB",), ("passing_yards",), 100.0),
    "rush_yds": (("RB", "QB"), ("rushing_yards",), 15.0),
    "rec_yds": (("WR", "TE", "RB"), ("receiving_yards",), 15.0),
    "receptions": (("WR", "TE", "RB"), ("receptions",), 1.5),
    "anytime_td": (("WR", "TE", "RB"), ("receiving_tds", "rushing_tds"), 0.0),
}
#: The ratings tried for each group, beside his own position's.
OPTIONS = ("own", "pass")


def own_stat(group: str, market: str) -> str | None:
    if market == "rush_yds" and group == "QB":
        return "rb_rush_yds"
    return D.stat_for(group, market)


def implied_by_team(conn, season: int) -> dict:
    """{(period, team): (implied points, his team's spread, the total)} from the stored closing lines."""
    out = {}
    for r in conn.execute("SELECT period, home, away, spread, total FROM games WHERE sport='cfb' AND season=? "
                          "AND spread IS NOT NULL AND total IS NOT NULL", (season,)):
        sp, tot = float(r[3]), float(r[4])
        out[(r[0], r[1])] = ((tot - sp) / 2.0, sp, tot)
        out[(r[0], r[2])] = ((tot + sp) / 2.0, -sp, tot)
    return out


def samples(conn, season: int, shrink: float = D.SHRINK_GAMES) -> list[dict]:
    fbs = CD.fbs_teams(conn, season)
    rows = CD.wide_rows(conn, season, None, fbs)
    if not rows:
        return []
    last = CD.wide_rows(conn, season - 1, None, fbs)
    prior = F._ratings_upto(D.allowed_by_game(last, 99), 99, shrink, None) if last else None
    games = D.allowed_by_game(rows, 99)
    pos_td = F._position_td_rates(rows)
    lines = implied_by_team(conn, season)
    avg = sum(v[0] for v in lines.values()) / len(lines) if lines else 0.0
    by_p: dict = {}
    for r in rows:
        g = D.GROUP_OF.get(r["position"])
        if g:
            by_p.setdefault(r["player_id"], []).append((r["week"], g, r))
    cache: dict = {}
    out = []
    for logs in by_p.values():
        logs.sort(key=lambda x: x[0])
        for i, (wk, g, r) in enumerate(logs):
            if wk < F.FIRST_WEEK or i < F.MIN_PRIOR_GAMES:
                continue
            if wk not in cache:
                cache[wk] = F._ratings_upto(games, wk, shrink, prior)
            rating = cache[wk].get(r["opponent_team"])
            line = lines.get((r["period"], r["team"]))
            if not rating or line is None or not avg:
                continue
            prev = [x[2] for x in logs[:i]]
            for m, (groups, cols, floor) in MARKETS.items():
                if g not in groups:
                    continue
                vals = [sum(D._f(p, c) for c in cols) for p in prev]
                if m == "anytime_td":
                    touches = sum(D._f(p, "receptions") + D._f(p, "carries") for p in prev) / len(prev)
                    if touches < F.TD_MIN_TOUCHES:
                        continue
                    e = (sum(vals) + F.TD_PRIOR_GAMES * pos_td.get(g, 0.0)) / (len(vals) + F.TD_PRIOR_GAMES)
                else:
                    e = sum(vals) / len(vals)
                    if e < floor:
                        continue
                so = own_stat(g, m)
                if not so or so not in rating:
                    continue
                out.append({"m": m, "g": g, "e": e, "y": sum(D._f(r, c) for c in cols),
                            "own": rating[so] - 1.0, "pass": rating.get("qb_pass_yds", 1.0) - 1.0,
                            "t": line[0] / avg - 1.0, "spread": line[1], "total": line[2]})
    return out


def fit(pts: list[dict], keys: list[str]) -> list[float]:
    """Least squares of (y − e) on e·x for each key, no intercept."""
    n = len(keys)
    a = [[0.0] * (n + 1) for _ in range(n)]
    for p in pts:
        xs = [p["e"] * p[k] for k in keys]
        for i in range(n):
            a[i][n] += xs[i] * (p["y"] - p["e"])
            for j in range(n):
                a[i][j] += xs[i] * xs[j]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            return [0.0] * n
        a[c], a[piv] = a[piv], a[c]
        for r in range(n):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def gain(pts: list[dict], keys: list[str], coef: list[float]) -> float:
    base = sum((p["y"] - p["e"]) ** 2 for p in pts)
    got = sum((p["y"] - p["e"] * (1 + sum(c * p[k] for c, k in zip(coef, keys)))) ** 2 for p in pts)
    return (base - got) / base if base > 0 else 0.0


def study(by_season: dict) -> dict:
    """{(market, group): {option: {"per": [held-out gain by season], "mean", "b"}}} plus the rule's choice.

    For touchdowns each option is scored as what it adds on top of the
    implied total (``t`` fitted beside it)."""
    years = sorted(by_season)
    out: dict = {}
    pairs = sorted({(p["m"], p["g"]) for s in years for p in by_season[s]})
    for m, g in pairs:
        res = {}
        for opt in OPTIONS:
            keys = ["t", opt] if m == "anytime_td" else [opt]
            per = []
            for test in years:
                tr = [p for s in years if s != test for p in by_season[s] if p["m"] == m and p["g"] == g]
                te = [p for p in by_season[test] if p["m"] == m and p["g"] == g]
                if len(tr) < 100 or len(te) < 30:
                    continue
                c = fit(tr, keys)
                x = gain(te, keys, c)
                if m == "anytime_td":
                    x -= gain(te, ["t"], fit(tr, ["t"]))
                per.append(x)
            whole = [p for s in years for p in by_season[s] if p["m"] == m and p["g"] == g]
            res[opt] = {"per": per, "mean": sum(per) / len(per) if per else 0.0,
                        "b": fit(whole, keys)[-1] if whole else 0.0, "n": len(whole)}
        ok = [o for o in OPTIONS if res[o]["per"] and res[o]["mean"] > 0
              and sum(1 for x in res[o]["per"] if x > 0) >= min(3, len(res[o]["per"]))]
        res["choice"] = max(ok, key=lambda o: res[o]["mean"]) if ok else None
        out[(m, g)] = res
    return out


def in_use(market: str, group: str) -> tuple:
    """(the stat the college model reads, its transfer) as shipped."""
    return D.model_stat(group, market, "cfb"), D.transfer(group, market, "cfb")


def nfl_rules(by_season: dict) -> dict:
    """What engine/matchup's spread and total rules — fitted on the NFL —
    do to college numbers, per market and position and held-out season:
    {(market, group): [gain by season]}. Negative is worse. They stand down
    for college (matchup.evaluate_matchup, sport "cfb") on this."""
    from ..matchup import SCRIPT_COEF_PASS, SCRIPT_CLAMP, TOTAL_COEF, TOTAL_BASELINE, TOTAL_CLAMP
    from ..statmath import clamp

    def rule(p):
        if p["m"] in ("pass_yds", "rec_yds", "receptions"):
            return clamp(1.0 + SCRIPT_COEF_PASS * p["spread"], *SCRIPT_CLAMP)
        if p["m"] == "rush_yds":
            return clamp(1.0 + TOTAL_COEF.get("rush_yds", 0.0) * (p["total"] - TOTAL_BASELINE), *TOTAL_CLAMP)
        return 1.0
    out: dict = {}
    for s in sorted(by_season):
        for key in sorted({(p["m"], p["g"]) for p in by_season[s]}):
            pts = [p for p in by_season[s] if (p["m"], p["g"]) == key]
            base = sum((p["y"] - p["e"]) ** 2 for p in pts)
            got = sum((p["y"] - p["e"] * rule(p)) ** 2 for p in pts)
            out.setdefault(key, []).append((base - got) / base if base > 0 else 0.0)
    return out
