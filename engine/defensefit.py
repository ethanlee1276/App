"""How much of a defence's rating reaches one player: measured, walk-forward.

engine/defensevs.py rates what each defence gives up to each position.
This measures, from nflverse weekly box scores, how much of that rating
shows up in an individual player's line — the number the projection
multiplies by — and how many games a rating needs before it is trusted.

For every regular-season player-game from week 4 on, with at least three
earlier games that season:

    expected  = his own average in those earlier games (touchdowns: his
                rate blended with his position's, since three games of
                touchdowns is mostly luck)
    d         = the opponent's rating for his position, from games BEFORE
                this one only, minus 1
    actual    = what he did

and the transfer b is the least-squares answer to
``actual ≈ expected · (1 + b·d)``:

    b = Σ e·d·(y − e) / Σ (e·d)²

b = 0 means the matchup tells you nothing beyond the player's own form;
b = 1 means a defence rated 20% generous moves him 20%. Fitted on the
earlier seasons, then scored on the last one it has never seen: the
share of squared error it removes there is the honest measure.
"""
from __future__ import annotations

import math

from engine import defensevs as D
from engine import passtd as _passtd

#: Markets measured: (market, groups it applies to, stat column(s) of the player, form floor)
MARKETS = {
    "rec_yds": (("WR", "TE", "RB"), ("receiving_yards",), 15.0),
    "receptions": (("WR", "TE", "RB"), ("receptions",), 1.5),
    "rush_yds": (("RB",), ("rushing_yards",), 15.0),
    "pass_yds": (("QB",), ("passing_yards",), 150.0),
    "anytime_td": (("WR", "TE", "RB"), ("receiving_tds", "rushing_tds"), 0.0),
    # Added 2026-09-23: the passing-touchdown prop had no matchup at all
    # (its rows came out of the chain untouched by any defence).
    "pass_td": (("QB",), ("passing_tds",), 0.5),
}
#: A quarterback must be the one throwing: this many attempts a game in
#: his earlier games to be measured on passing touchdowns.
PASS_TD_MIN_ATTEMPTS = 20.0
MIN_PRIOR_GAMES = 3
FIRST_WEEK = 4
#: A touchdown rate this many games' worth of the position's own rate.
TD_PRIOR_GAMES = 6
#: A player must see real work to be measured on touchdowns: this many
#: catches or carries a game in his earlier games.
TD_MIN_TOUCHES = 2.0
SHRINK_GRID = (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)


def _f(r, k):
    return D._f(r, k)


def samples(rows: list[dict], shrink: float, prior: dict | None = None, legacy: bool = False,
            model: bool = False) -> dict:
    """{market: [(expected, d, actual)]} for one season's weekly rows."""
    reg = [r for r in rows if D._regular(r)]
    by_player: dict = {}
    for r in reg:
        g = D.GROUP_OF.get(str(r.get("position") or "").upper())
        if g:
            by_player.setdefault(str(r.get("player_id") or r.get("player_display_name")), []).append((D._week(r), g, r))
    games = D.allowed_by_game(reg, 99)
    pos_td = _position_td_rates(reg)
    cache: dict = {}
    out: dict = {m: [] for m in MARKETS}
    for logs in by_player.values():
        logs.sort(key=lambda x: x[0])
        for i, (wk, g, r) in enumerate(logs):
            if wk < FIRST_WEEK or i < MIN_PRIOR_GAMES:
                continue
            opp = str(r.get("opponent_team") or "")
            if wk not in cache:
                cache[wk] = _legacy(reg, wk) if legacy else _ratings_upto(games, wk, shrink, prior)
            rating = cache[wk].get(opp)
            if not rating:
                continue
            prev = [x[2] for x in logs[:i]]
            for market, (groups, cols, floor) in MARKETS.items():
                if g not in groups:
                    continue
                stat = D.model_stat(g, market) if model else D.stat_for(g, market)
                if not stat or stat not in rating:
                    continue
                vals = [sum(_f(p, c) for c in cols) for p in prev]
                y = sum(_f(r, c) for c in cols)
                if market == "anytime_td":
                    touches = sum(_f(p, "receptions") + _f(p, "carries") for p in prev) / len(prev)
                    if touches < TD_MIN_TOUCHES:
                        continue
                    e = (sum(vals) + TD_PRIOR_GAMES * pos_td[g]) / (len(vals) + TD_PRIOR_GAMES)
                elif market == "pass_td":
                    # The expectation is the board's own passing-TD
                    # projection (engine/passtd), most recent game first.
                    if sum(_f(p, "attempts") for p in prev) / len(prev) < PASS_TD_MIN_ATTEMPTS:
                        continue
                    e = _passtd.projection(vals[::-1])
                    if e < floor:
                        continue
                else:
                    e = sum(vals) / len(vals)
                    if e < floor:
                        continue
                out[market].append((e, rating[stat] - 1.0, y, g))
    return out


def _position_td_rates(reg: list[dict]) -> dict:
    tot, n = {}, {}
    for r in reg:
        g = D.GROUP_OF.get(str(r.get("position") or "").upper())
        if g in ("WR", "TE", "RB") and (_f(r, "receptions") + _f(r, "carries")) >= 1:
            tot[g] = tot.get(g, 0.0) + _f(r, "receiving_tds") + _f(r, "rushing_tds")
            n[g] = n.get(g, 0) + 1
    return {g: tot[g] / n[g] for g in tot}


def _ratings_upto(games: dict, wk: int, shrink: float, prior: dict | None) -> dict:
    """ratings() over the precomputed game totals, restricted to weeks before ``wk``: {team: {stat: factor}}."""
    cut = {t: {w: v for w, v in g.items() if w < wk} for t, g in games.items()}
    cut = {t: g for t, g in cut.items() if g}
    if not cut:
        return {}
    per = {t: {s: sum(v[s] for v in g.values()) / len(g) for s in D.STATS} for t, g in cut.items()}
    league = {s: sum(p[s] for p in per.values()) / len(per) for s in D.STATS}
    out = {}
    for t, p in per.items():
        n = len(cut[t])
        w = n / (n + shrink) if (n + shrink) > 0 else 1.0
        row = {}
        for s in D.STATS:
            raw = p[s] / league[s] if league[s] > 0 else 1.0
            c = (prior or {}).get(t, {}).get(s, 1.0)
            row[s] = c + (raw - c) * w
        out[t] = row
    return out


def _legacy(reg: list[dict], wk: int) -> dict:
    """The ratings the model used before 2026-09-23 (the old
    engine/sources/nflverse.build_defense_profiles, kept here so the
    comparison can be re-run): each defence's mean conceded per player
    appearance, against the league's, WR1/WR2/slot one number, no shrink,
    and touchdowns rated by the yards number."""
    rows = [r for r in reg if 0 < D._week(r) < wk]
    buckets = ("qb_pass", "wr_rec", "te_rec", "rb_rush", "rb_recv")
    allowed: dict = {}
    for r in rows:
        deff = str(r.get("opponent_team") or "")
        if not deff:
            continue
        pos = str(r.get("position") or "").upper()
        d = allowed.setdefault(deff, {b: [] for b in buckets})
        if pos == "QB":
            d["qb_pass"].append(_f(r, "passing_yards"))
        if pos == "WR":
            d["wr_rec"].append(_f(r, "receiving_yards"))
        if pos == "TE":
            d["te_rec"].append(_f(r, "receiving_yards"))
        if pos == "RB":
            d["rb_rush"].append(_f(r, "rushing_yards"))
            d["rb_recv"].append(_f(r, "receiving_yards"))
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0          # noqa: E731
    tm = {t: {b: mean(v[b]) for b in buckets} for t, v in allowed.items()}
    league = {b: mean([x[b] for x in tm.values()]) for b in buckets}
    fac = lambda t, b: tm[t][b] / league[b] if league[b] > 0 else 1.0    # noqa: E731
    out = {}
    for t in tm:
        wr, te, qb = fac(t, "wr_rec"), fac(t, "te_rec"), fac(t, "qb_pass")
        out[t] = {"wr_rec_yds": wr, "wr_rec": wr, "wr_td": wr, "te_rec_yds": te, "te_rec": te, "te_td": te,
                  "rb_rush_yds": fac(t, "rb_rush"), "rb_rec_yds": fac(t, "rb_recv"),
                  "rb_rec": fac(t, "rb_recv"), "rb_td": fac(t, "rb_rush"), "qb_pass_yds": qb, "qb_pass_td": qb}
    return out


def fit(pts: list[tuple]) -> dict:
    """b, its standard error, and the sample."""
    num = sum(e * d * (y - e) for e, d, y, *_g in pts)
    den = sum((e * d) ** 2 for e, d, _y, *_g in pts)
    if den <= 0 or len(pts) < 30:
        return {"b": 0.0, "se": None, "n": len(pts)}
    b = num / den
    resid = sum((y - e * (1 + b * d)) ** 2 for e, d, y, *_g in pts) / max(1, len(pts) - 1)
    return {"b": round(b, 4), "se": round(math.sqrt(resid / den), 4), "n": len(pts)}


def gain(pts: list[tuple], b: float) -> float:
    """Share of squared error removed by applying transfer b, against b = 0."""
    base = sum((y - e) ** 2 for e, _d, y, *_g in pts)
    with_b = sum((y - e * (1 + b * d)) ** 2 for e, d, y, *_g in pts)
    return (base - with_b) / base if base > 0 else 0.0


def study(seasons: dict, test_season: int | None, legacy: bool = False, with_prior: bool = False,
          model: bool = False) -> dict:
    """Fit on every season but ``test_season``, score on it, over the shrink grid.

    ``seasons`` is {season: weekly rows}. Returns the best shrink and, per
    market, the fitted b, its SE and n, and the held-out gain."""
    grid = (0.0,) if legacy else SHRINK_GRID
    best = None
    for k in grid:
        train, test = {m: [] for m in MARKETS}, {m: [] for m in MARKETS}
        for season, rows in sorted(seasons.items()):
            prior = None
            if with_prior and (season - 1) in seasons:
                prev = _ratings_upto(D.allowed_by_game(seasons[season - 1], 99), 99, k, None)
                prior = prev
            got = samples(rows, k, prior, legacy, model)
            for m in MARKETS:
                (test if season == test_season else train)[m].extend(got[m])
        res = {}
        for m in MARKETS:
            f = fit(train[m])
            res[m] = {**f, "held_out_gain": round(gain(test[m], f["b"]), 5), "held_out_n": len(test[m])}
            groups = sorted({p[3] for p in train[m]})
            if groups:
                res[m]["by_group"] = {}
                for g in groups:
                    fg = fit([p for p in train[m] if p[3] == g])
                    res[m]["by_group"][g] = {**fg, "held_out_gain": round(gain([p for p in test[m] if p[3] == g], fg["b"]), 5)}
        score = sum(r["held_out_gain"] * r["held_out_n"] for r in res.values())
        if best is None or score > best[0]:
            best = (score, k, res)
    return {"shrink": best[1], "markets": best[2]}


def report(result: dict, title: str) -> str:
    out = [title, f"  shrink {result['shrink']:g} games"]
    for m, r in result["markets"].items():
        se = f" ± {r['se']:.3f}" if r.get("se") is not None else ""
        out.append(f"  {m:<11} b = {r['b']:+.3f}{se}  (n {r['n']:>6})   held-out gain {100 * r['held_out_gain']:+.2f}% "
                   f"(n {r['held_out_n']})")
        for g, rg in (r.get("by_group") or {}).items():
            sg = f" ± {rg['se']:.3f}" if rg.get("se") is not None else ""
            out.append(f"      {g:<6} b = {rg['b']:+.3f}{sg}  (n {rg['n']:>6})   held-out gain {100 * rg['held_out_gain']:+.2f}%")
    return "\n".join(out)
