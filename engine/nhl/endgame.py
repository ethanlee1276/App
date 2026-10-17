"""The NHL endgame: score effects, the pulled goalie and the empty net, priced.

Ethan, 2026-10-17: "create models and features that don't exist ... new
equations and methods ... make the NFL and every sport elite."

WHAT THE GAME MODEL ASSUMED. `engine/nhl/model.game_probs` scores regulation
as two independent Poissons: each side's goals arrive at one steady rate
from the opening faceoff to the final horn, whatever the score and whatever
the clock. Hockey does not work that way, and the last three minutes do not
work that way at all:

  * a side that trails pushes, and a side that leads sits back — the score
    effect, all game long;
  * a side down one late pulls its goalie for a sixth skater: it scores more
    often than it did, and the side in front scores into an empty net far
    more often than it did.

Both change the SHAPE of the final score, not just its average. A one-goal
lead with ninety seconds left ends as a two-goal win (an empty-netter) or
a tie (the extra attacker scores) far more often than a steady-rate model
says, so it misprices exactly the two markets built on that shape: the
puck line (−1.5 needs a two-goal win) and the total (an empty-netter is a
goal nobody's season rate expected that night).

THE EQUATION. Regulation is a Markov chain over the score (h, a), stepped
every DT seconds. In each step the home side scores with probability

    λ_h · k_h · m(phase(t), h − a) · DT / 3600

and the away side with the same expression on its own lambda and its own
score difference (a − h). m is a multiplier per (phase of the game, score
difference from the scoring side's view), FITTED from every regulation goal
of three NHL seasons (`fit`): "early" covers the first 55 minutes, and
each of the last five minutes is its own phase, because that is where the
goalie comes out. k_h and k_a rescale each side so its expected regulation
goals still equal the lambda it was given — the lambdas are season goal
rates that already contain the empty-netters, so the chain moves WHEN the
goals come and what the final score looks like, never how many a team
scores on average. A regulation tie goes to overtime exactly as the old
model sends it (OT_HOME), and the total counts the decider as one goal.

THE FIT. Each game's goals are walked in clock order. Between goals, each
side's exposure — its base rate times the seconds spent in each (phase,
score difference) cell — is added to that cell; each goal is counted in
the scorer's cell at the moment it went in. A cell's multiplier is its
goals over its exposure, shrunk toward 1 by PRIOR_GOALS. The base rate is
the side's season goals for and the opponent's goals against (its own game
left out), with home ice, so a weak side's trailing minutes are not read as
a trailing effect.

THE SEAT IS EARNED. `heldout` replays every game of each season the fit did
not see (trained on the seasons BEFORE it only) and scores the old model
and this one on the same lambdas: the puck line, the full total-goals
distribution, and the regulation margin. The bar is written before any run
— better pooled on all three, and no held-out season worse on the puck line
or the total — and the build prices with this only when the saved verdict
says it holds (`priced`). Until then every number is the old model's.

Standard library only; reads the history database the NHL ingest fills
(nhl_shots with its goal clock, and the games table's finals).
"""
from __future__ import annotations

import json
import math
import os
import time

from . import model as M

STORE = "nhl_endgame.json"
#: Regulation, in seconds.
REG_S = 3600
#: The chain's step. Ten seconds: two goals in one step are rare enough to ignore.
DT = 10
#: The phases a multiplier is fitted for: (label, start second, end second).
PHASES = (("early", 0, 3300), ("m56", 3300, 3360), ("m57", 3360, 3420),
          ("m58", 3420, 3480), ("m59", 3480, 3540), ("m60", 3540, 3600))
#: Score difference from the scoring side's view, clamped to ±MAX_DIFF.
MAX_DIFF = 3
#: A cell's multiplier is shrunk toward 1 by this many expected goals. The
#: last-minute cells are thin by nature — a one-goal game spends about a
#: minute there — so the prior is a few goals, not dozens: on three seasons
#: a cell of the last minute expects some sixty goals at the base rate.
PRIOR_GOALS = 5.0
#: Team rates are shrunk toward the league by this many games.
TEAM_PRIOR = 10.0
#: The score grid the chain carries (goals per side).
MAX_G = 12
#: A game must have at least this many seasons behind it to be scored held out.
MIN_TRAIN_GAMES = 400


def _phase(t: float) -> str:
    for label, lo, hi in PHASES:
        if lo <= t < hi:
            return label
    return PHASES[-1][0]


def _clamp(d: int) -> int:
    return max(-MAX_DIFF, min(MAX_DIFF, d))


# ---- the games ---------------------------------------------------------------------------------

def load_games(conn, seasons=None) -> list[dict]:
    """Every NHL final with its regulation goals on the clock:
    ``[{gid, season, date, home, away, goals: [(t, is_home)], final: (hs, as)}]``.

    A game is kept only when its play file carries the clock (some row of it
    has ``t``) and its regulation goals agree with the final — a tie after
    sixty minutes is a final one goal apart, anything else the same score —
    so a half-read play file never trains or scores anything."""
    finals: dict = {}
    q = ("SELECT season, date, home, away, home_score, away_score, extra FROM games "
         "WHERE sport='nhl' AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = []
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    for season, date, home, away, hs, as_, extra in conn.execute(q, args):
        try:
            gid = int((json.loads(extra or "{}")).get("nhl_id") or 0)
        except (ValueError, TypeError):
            gid = 0
        if gid:
            finals[gid] = {"gid": gid, "season": int(season), "date": str(date)[:10],
                           "home": str(home), "away": str(away), "final": (int(hs), int(as_)),
                           "goals": []}
    if not finals:
        return []
    clocked = {r[0] for r in conn.execute(
        "SELECT game_id FROM nhl_shots GROUP BY game_id HAVING COUNT(t) > 0")}
    for gid, team, period, t in conn.execute(
            "SELECT game_id, team, period, t FROM nhl_shots WHERE is_goal = 1 AND period <= 3"):
        g = finals.get(gid)
        if g is None or t is None:
            continue
        if team == g["home"]:
            g["goals"].append((int(t), True))
        elif team == g["away"]:
            g["goals"].append((int(t), False))
    out = []
    for gid, g in finals.items():
        if gid not in clocked:
            continue
        g["goals"].sort()
        rh = sum(1 for _, h in g["goals"] if h)
        ra = len(g["goals"]) - rh
        hs, as_ = g["final"]
        if rh == ra:
            if abs(hs - as_) != 1 or min(hs, as_) != rh:
                continue
        elif (rh, ra) != (hs, as_):
            continue
        g["reg"] = (rh, ra)
        out.append(g)
    out.sort(key=lambda g: (g["date"], g["gid"]))
    return out


def team_rates(games: list[dict]) -> dict:
    """``{(season, team): {"gf", "ga", "n"}}`` — regulation goals, summed."""
    out: dict = {}
    for g in games:
        rh, ra = g["reg"]
        for team, gf, ga in ((g["home"], rh, ra), (g["away"], ra, rh)):
            c = out.setdefault((g["season"], team), {"gf": 0, "ga": 0, "n": 0})
            c["gf"] += gf
            c["ga"] += ga
            c["n"] += 1
    return out


def league_shape(games: list[dict]) -> tuple:
    """(regulation goals per side per game, home-ice factor) across ``games``."""
    if not games:
        return 2.9, M.HOME_EDGE
    hg = sum(g["reg"][0] for g in games)
    ag = sum(g["reg"][1] for g in games)
    per_side = (hg + ag) / (2.0 * len(games))
    edge = math.sqrt(hg / ag) if hg and ag else M.HOME_EDGE
    return per_side, edge


def game_lambdas(g: dict, rates: dict, avg: float, edge: float) -> tuple:
    """(home, away) regulation lambdas for one game from its sides' season
    rates with the game's own goals taken out, shrunk toward the league."""
    rh, ra = g["reg"]

    def strength(team, mine, against):
        c = rates.get((g["season"], team)) or {"gf": 0, "ga": 0, "n": 0}
        n = c["n"] - 1
        if n <= 0:
            return 1.0, 1.0
        gf, ga = (c["gf"] - mine) / n, (c["ga"] - against) / n
        w = n / (n + TEAM_PRIOR)
        return 1.0 + w * (gf / avg - 1.0), 1.0 + w * (ga / avg - 1.0)

    h_att, h_def = strength(g["home"], rh, ra)
    a_att, a_def = strength(g["away"], ra, rh)
    return avg * h_att * a_def * edge, avg * a_att * h_def / edge


# ---- the fit -------------------------------------------------------------------------------------

def _cells() -> dict:
    return {p: {d: [0.0, 0.0] for d in range(-MAX_DIFF, MAX_DIFF + 1)} for p, _, _ in PHASES}


def _expose(cells, rate_s: float, diff: int, t0: float, t1: float) -> None:
    """Add a side's expected goals between t0 and t1 at one score difference."""
    for label, lo, hi in PHASES:
        a, b = max(t0, lo), min(t1, hi)
        if b > a:
            cells[label][_clamp(diff)][1] += rate_s * (b - a)


def fit(games: list[dict]) -> dict:
    """The multipliers, fitted on ``games``:
    ``{"m": {phase: {diff: m}}, "games", "goals", "cells": {phase: {diff: [goals, expected]}}}``."""
    rates = team_rates(games)
    avg, edge = league_shape(games)
    cells = _cells()
    goals = 0
    for g in games:
        lh, la = game_lambdas(g, rates, avg, edge)
        sh, sa = lh / REG_S, la / REG_S
        h = a = 0
        last = 0.0
        for t, is_home in g["goals"] + [(REG_S, None)]:
            t = min(float(t), REG_S)
            _expose(cells, sh, h - a, last, t)
            _expose(cells, sa, a - h, last, t)
            last = t
            if is_home is None:
                break
            if is_home:
                cells[_phase(t)][_clamp(h - a)][0] += 1
                h += 1
            else:
                cells[_phase(t)][_clamp(a - h)][0] += 1
                a += 1
            goals += 1
    m = {p: {d: round((c[0] + PRIOR_GOALS) / (c[1] + PRIOR_GOALS), 4) for d, c in row.items()}
         for p, row in cells.items()}
    return {"m": m, "games": len(games), "goals": goals,
            "cells": {p: {d: [c[0], round(c[1], 2)] for d, c in row.items()} for p, row in cells.items()}}


def _m(fitted: dict, phase: str, diff: int) -> float:
    row = (fitted.get("m") or {}).get(phase) or {}
    v = row.get(_clamp(diff))
    if v is None:
        v = row.get(str(_clamp(diff)))       # a fit read back from JSON keys its diffs as text
    return float(v) if v else 1.0


# ---- the chain -----------------------------------------------------------------------------------

def _run(lh: float, la: float, fitted: dict, kh: float, ka: float, dt: int) -> list:
    """The regulation score distribution, ``P[h][a]``."""
    n = MAX_G + 1
    P = [[0.0] * n for _ in range(n)]
    P[0][0] = 1.0
    rh, ra = lh * kh / REG_S * dt, la * ka / REG_S * dt
    mcache: dict = {}
    t = 0
    while t < REG_S:
        phase = _phase(t + dt / 2.0)
        Q = [[0.0] * n for _ in range(n)]
        for h in range(n):
            row = P[h]
            for a in range(n):
                p = row[a]
                if p < 1e-13:
                    continue
                d = h - a
                key = (phase, d)
                if key not in mcache:
                    mcache[key] = (_m(fitted, phase, d), _m(fitted, phase, -d))
                mh, ma = mcache[key]
                ph, pa = rh * mh, ra * ma
                s = ph + pa
                if s > 0.95:                      # never on any real lambda; kept a probability
                    ph, pa = ph * 0.95 / s, pa * 0.95 / s
                    s = 0.95
                Q[h][a] += p * (1.0 - s)
                Q[min(h + 1, MAX_G)][a] += p * ph
                Q[h][min(a + 1, MAX_G)] += p * pa
        P = Q
        t += dt
    return P


def _means(P) -> tuple:
    eh = sum(h * P[h][a] for h in range(len(P)) for a in range(len(P)))
    ea = sum(a * P[h][a] for h in range(len(P)) for a in range(len(P)))
    return eh, ea


def game_probs(lh: float, la: float, fitted: dict, dt: int = DT) -> dict:
    """`model.game_probs`'s answer, priced through the endgame chain: the
    same keys, so the build reads it unchanged. Each side keeps its own
    expected regulation goals (one rescaling pass)."""
    P = _run(lh, la, fitted, 1.0, 1.0, dt)
    eh, ea = _means(P)
    kh = lh / eh if eh > 0 else 1.0
    ka = la / ea if ea > 0 else 1.0
    P = _run(lh, la, fitted, kh, ka, dt)
    home_reg = away_reg = tie = home_by2 = away_by2 = 0.0
    totals: dict = {}
    for h in range(len(P)):
        for a in range(len(P)):
            pr = P[h][a]
            if pr <= 0:
                continue
            if h > a:
                home_reg += pr
                if h - a >= 2:
                    home_by2 += pr
            elif a > h:
                away_reg += pr
                if a - h >= 2:
                    away_by2 += pr
            else:
                tie += pr
            tt = h + a + (1 if h == a else 0)
            totals[tt] = totals.get(tt, 0.0) + pr
    return {"home_ml": home_reg + tie * M.OT_HOME, "away_ml": away_reg + tie * (1 - M.OT_HOME),
            "home_-1.5": home_by2, "away_-1.5": away_by2,
            "home_+1.5": 1.0 - away_by2, "away_+1.5": 1.0 - home_by2,
            "tie": tie, "totals": totals, "lh": lh, "la": la, "endgame": True}


# ---- held out ------------------------------------------------------------------------------------

def _ll(p: float) -> float:
    return -math.log(min(1.0 - 1e-9, max(1e-9, p)))


def _outcomes(g: dict) -> dict:
    rh, ra = g["reg"]
    total = rh + ra + (1 if rh == ra else 0)
    if rh - ra >= 2:
        margin = "home2"
    elif rh - ra == 1:
        margin = "home1"
    elif rh == ra:
        margin = "tie"
    elif ra - rh == 1:
        margin = "away1"
    else:
        margin = "away2"
    return {"total": total, "home_cover": rh - ra >= 2, "margin": margin}


def _margin_p(probs: dict, which: str) -> float:
    by2h, by2a, tie = probs["home_-1.5"], probs["away_-1.5"], probs["tie"]
    reg_h = probs["home_ml"] - tie * M.OT_HOME
    reg_a = probs["away_ml"] - tie * (1 - M.OT_HOME)
    return {"home2": by2h, "home1": reg_h - by2h, "tie": tie,
            "away1": reg_a - by2a, "away2": by2a}[which]


def score(games: list[dict], fitted: dict, dt: int = DT) -> dict:
    """Both models on ``games``, on the same lambdas (each game's sides'
    season rates with its own goals left out): mean log loss on the puck
    line, the total-goals distribution and the regulation margin, and the
    two-goal finish rate each claims beside the one that happened."""
    rates = team_rates(games)
    avg, edge = league_shape(games)
    acc = {k: [0.0, 0.0] for k in ("puck", "total", "margin")}
    by2 = {"plain": 0.0, "endgame": 0.0, "actual": 0}
    n = 0
    for g in games:
        lh, la = game_lambdas(g, rates, avg, edge)
        plain = M.game_probs(lh, la)
        end = game_probs(lh, la, fitted, dt)
        o = _outcomes(g)
        for i, pr in enumerate((plain, end)):
            pc = pr["home_-1.5"]
            acc["puck"][i] += _ll(pc if o["home_cover"] else 1.0 - pc)
            acc["total"][i] += _ll(pr["totals"].get(o["total"], 0.0))
            acc["margin"][i] += _ll(_margin_p(pr, o["margin"]))
        by2["plain"] += plain["home_-1.5"] + plain["away_-1.5"]
        by2["endgame"] += end["home_-1.5"] + end["away_-1.5"]
        by2["actual"] += o["margin"] in ("home2", "away2")
        n += 1
    if not n:
        return {"games": 0}
    out = {"games": n}
    for k, (a, b) in acc.items():
        out[k] = {"plain": round(a / n, 5), "endgame": round(b / n, 5)}
    out["two_goal_finish"] = {"plain": round(by2["plain"] / n, 4), "endgame": round(by2["endgame"] / n, 4),
                              "actual": round(by2["actual"] / n, 4)}
    return out


#: Written before any run. Pooled over the held-out seasons the endgame
#: chain must beat the steady-rate model on all three scores, and no single
#: held-out season may be worse on the puck line or the total.
BAR = ("held out by season (each scored on a fit of the seasons before it only): better pooled log loss "
       "on the puck line, the total-goals distribution and the regulation margin, and no held-out "
       "season worse on the puck line or the total")


def heldout(games: list[dict], dt: int = DT) -> dict:
    """The verdict: each season scored on a fit of the seasons before it."""
    seasons = sorted({g["season"] for g in games})
    folds = []
    for s in seasons:
        train = [g for g in games if g["season"] < s]
        test = [g for g in games if g["season"] == s]
        if len(train) < MIN_TRAIN_GAMES or not test:
            continue
        r = score(test, fit(train), dt)
        r["season"] = s
        r["trained_on"] = len(train)
        folds.append(r)
    if not folds:
        return {"holds": False, "why": f"no season has {MIN_TRAIN_GAMES}+ clocked games before it yet",
                "folds": [], "bar": BAR}
    tot = sum(f["games"] for f in folds)
    pooled = {k: {m: round(sum(f[k][m] * f["games"] for f in folds) / tot, 5) for m in ("plain", "endgame")}
              for k in ("puck", "total", "margin")}
    better = all(pooled[k]["endgame"] < pooled[k]["plain"] for k in pooled)
    no_worse = all(f[k]["endgame"] <= f[k]["plain"] for f in folds for k in ("puck", "total"))
    holds = better and no_worse
    if holds:
        why = "beats the steady-rate model pooled on all three scores and in every held-out season"
    elif not better:
        why = "not better pooled on " + ", ".join(k for k in pooled if pooled[k]["endgame"] >= pooled[k]["plain"])
    else:
        why = "worse in a held-out season on " + ", ".join(
            f"{f['season']} {k}" for f in folds for k in ("puck", "total") if f[k]["endgame"] > f[k]["plain"])
    return {"holds": holds, "why": why, "games": tot, "folds": folds, "pooled": pooled, "bar": BAR}


# ---- the store and the gate ----------------------------------------------------------------------

def save(res: dict) -> str:
    from .. import modelstate
    p = modelstate.path(STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    return p


_CACHE: dict = {}


def load() -> dict:
    """The saved fit and verdict, re-read when the file changes on disk."""
    from .. import modelstate
    p = modelstate.path(STORE)
    try:
        stamp = os.path.getmtime(p)
    except OSError:
        return {}
    if _CACHE.get("stamp") == stamp:
        return _CACHE["data"]
    try:
        with open(p) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    _CACHE.update(stamp=stamp, data=data)
    return data


def verdict() -> dict:
    return load().get("verdict") or {}


def priced(lh: float, la: float) -> dict:
    """The game's probabilities: the endgame chain's when its saved verdict
    holds, the steady-rate model's otherwise (the same keys either way)."""
    store = load()
    if (store.get("verdict") or {}).get("holds") and (store.get("fit") or {}).get("m"):
        try:
            return game_probs(lh, la, store["fit"])
        except Exception:                                        # noqa: BLE001
            pass
    return M.game_probs(lh, la)


def note(probs: dict, lh: float, la: float) -> str | None:
    """One line for a game card when the endgame priced it: how much more
    often than a steady-rate game this one ends by two or more."""
    if not probs.get("endgame"):
        return None
    plain = M.game_probs(lh, la)
    a = probs["home_-1.5"] + probs["away_-1.5"]
    b = plain["home_-1.5"] + plain["away_-1.5"]
    return (f"Late-game math: a side down one late pulls its goalie, so this game ends by two or more "
            f"{a:.0%} of the time ({b:.0%} if every minute played the same)")


# ---- the command ---------------------------------------------------------------------------------

def run(conn, dt: int = DT, say=print) -> dict:
    """Load, measure held out, fit on everything, save. Returns what was saved."""
    t0 = time.time()
    games = load_games(conn)
    say(f"  {len(games):,} NHL finals with their goals on the clock")
    v = heldout(games, dt)
    for f in v.get("folds", []):
        say(f"  {f['season']} (fit on {f['trained_on']:,} earlier games, {f['games']:,} scored): "
            f"puck line {f['puck']['plain']:.4f} → {f['puck']['endgame']:.4f} · "
            f"total {f['total']['plain']:.4f} → {f['total']['endgame']:.4f} · "
            f"margin {f['margin']['plain']:.4f} → {f['margin']['endgame']:.4f} · "
            f"two-goal finishes claimed {f['two_goal_finish']['plain']:.1%} → "
            f"{f['two_goal_finish']['endgame']:.1%}, happened {f['two_goal_finish']['actual']:.1%}")
    full = fit(games) if games else {"m": {}}
    res = {"fit": full, "verdict": v, "fitted_at": time.strftime("%Y-%m-%d %H:%M"),
           "seconds": round(time.time() - t0, 1)}
    if games:
        late = full["m"].get("m60", {})
        say(f"  last minute: a side down one scores ×{late.get(-1, 1):.2f} its usual rate, "
            f"the side up one ×{late.get(1, 1):.2f} (the empty net)")
    say(f"  verdict: {'HOLDS' if v.get('holds') else 'does not hold'} — {v.get('why')}")
    return res


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="The NHL endgame chain: fit, held-out test, save")
    ap.add_argument("--backfill", type=int, default=0,
                    help="first re-read up to N stored finals whose goals lack the clock (cached play files)")
    ap.add_argument("--save", action="store_true", help="write the fit and verdict to the models dir")
    ap.add_argument("--dt", type=int, default=DT, help=f"the chain's step in seconds (default {DT})")
    a = ap.parse_args(argv)
    from .. import db
    conn = db.connect()
    if a.backfill:
        from ..sources import nhlpbp
        r = nhlpbp.backfill(conn, limit=a.backfill)
        print(f"  backfill: {r['games']:,} games re-read, {r['failed']} failed, {r['todo']:,} were waiting")
    res = run(conn, a.dt)
    if a.save:
        print(f"  saved {save(res)}")
    else:
        print("  not saved (add --save)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
