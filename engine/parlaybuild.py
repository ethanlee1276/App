"""The parlay builder: tonight's legs put together, priced with the correlation between them.

Ethan, 2026-10-15, from the brainstorm he asked to have built: a correlated
parlay builder. The site already holds every piece: our chance on each leg
(the board), how two legs relate (engine/parlays.relate — the clash
taxonomy and its measured priors, the rules the model's own tickets obey)
and the Gaussian copula that turns the legs and their correlation into one
chance they all hit (parlays.joint_two / joint_three). This puts them in
the reader's hands: pick legs, see the chance with the correlation beside
the chance as if the legs were independent, the fair price, what the
legs pay at their own prices multiplied, and which legs on the board stack
best with the ones chosen.

THE RULES ARE THE MODEL'S OWN. A pair the taxonomy kills (or a duplicate)
is refused with its reason (parlays.check_ticket); the reader's slip cap
is the sport's (RULES[sport].slip_legs). A book prices a same-game parlay
with its own correlation, so "pays" is what independent legs would pay,
and the page says so.

CONTEXT. The chances are the board's own published numbers and the
correlations are the engine's priors; nothing here is a pick and nothing
on the board moves for it. The legs and their chances come from the page
(what the reader already holds); nothing is read here but them.
"""

from __future__ import annotations

import math
import random

from . import parlays as P

#: Candidates read for "stacks well with".
MAX_POOL = 40
#: Shown as stacks.
TOP = 5
#: A stack worth naming: the average correlation with the legs chosen.
STACK_RHO = 0.15
#: Draws for a joint of more than three legs, or three with a negative pair.
DRAWS = 40_000

KEEP = ("player", "market", "side", "line", "team", "opponent", "home", "away", "game_date", "position", "odds", "p")


def clean(leg) -> dict | None:
    """A leg as the page sends it, or None: a named pick with a chance."""
    if not isinstance(leg, dict):
        return None
    out = {k: (str(leg[k])[:60] if isinstance(leg.get(k), str) else leg.get(k)) for k in KEEP if k in leg}
    try:
        out["p"] = float(out.get("p"))
    except (TypeError, ValueError):
        return None
    if not (0.0 < out["p"] < 1.0) or not isinstance(out.get("market"), str) or not out.get("market"):
        return None
    if not out.get("player") and not (out.get("home") and out.get("away")):
        return None
    return out


def _dec(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0 or -100 < o < 100:
        return None
    return 1 + (o / 100.0 if o > 0 else 100.0 / -o)


def _chol(m: list[list[float]]) -> list[list[float]] | None:
    n = len(m)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = m[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
            if i == j:
                if s <= 1e-9:
                    return None
                low[i][j] = math.sqrt(s)
            else:
                low[i][j] = s / low[j][j]
    return low


def joint_n(ps: list[float], rho: dict, draws: int = DRAWS, seed: int = 7) -> float:
    """P(every leg wins) under a Gaussian copula with these pairwise
    correlations, by simulation (a fixed seed, so a page reads the same
    number twice). A correlation matrix that is not positive definite is
    shrunk toward independence until it is."""
    n = len(ps)
    zs = [P._phi_inv(1 - p) for p in ps]
    shrink = 1.0
    low = None
    while low is None and shrink > 0:
        m = [[1.0 if i == j else shrink * rho.get((min(i, j), max(i, j)), 0.0) for j in range(n)] for i in range(n)]
        low = _chol(m)
        shrink = round(shrink - 0.1, 2)
    if low is None:
        return math.prod(ps)
    rng = random.Random(seed)
    hit = 0
    for _ in range(draws):
        e = [rng.gauss(0.0, 1.0) for _ in range(n)]
        if all(sum(low[i][k] * e[k] for k in range(i + 1)) > zs[i] for i in range(n)):
            hit += 1
    return hit / draws


def _block(ps: list[float], rho: dict) -> float:
    if len(ps) == 1:
        return ps[0]
    if len(ps) == 2:
        return P.joint_two(ps[0], ps[1], rho.get((0, 1), 0.0))
    if len(ps) == 3 and all(rho.get(k, 0.0) > 0 for k in ((0, 1), (0, 2), (1, 2))):
        return P.joint_three(tuple(ps), (rho.get((0, 1), 0.0), rho.get((0, 2), 0.0), rho.get((1, 2), 0.0)))
    return joint_n(ps, rho)


def joint(ps: list[float], rho: dict) -> float:
    """P(every leg wins). Legs with no correlation path between them (two
    games) are independent, so the joint is the product over the linked
    groups — priced whole, a cross-game leg's zero would make the
    one-factor copula (joint_three) shrink every loading to nothing and
    lose the pair that is correlated. A linked group of three with every
    pair positive is joint_three, the model's own; anything else is
    simulated (joint_n)."""
    n = len(ps)
    root = list(range(n))

    def find(i):
        while root[i] != i:
            i = root[i]
        return i
    for (i, j), r in rho.items():
        if abs(r) > 1e-9:
            root[find(i)] = find(j)
    out = 1.0
    for g in sorted({find(i) for i in range(n)}):
        idx = [i for i in range(n) if find(i) == g]
        at = {v: k for k, v in enumerate(idx)}
        sub = {(at[i], at[j]): r for (i, j), r in rho.items() if i in at and j in at}
        out *= _block([ps[i] for i in idx], sub)
    return out


def build(sport: str, legs: list, pool: list | None = None) -> dict:
    """The ticket: ``{"ok", "legs", "pairs", "joint", "independent",
    "fair", "pays", "ev", "stacks", "cap"}``, or ``{"ok": False, "reason",
    "pair"}`` when the engine refuses it."""
    sport = (sport or "").lower()
    cap = P.RULES[sport].slip_legs if sport in P.RULES else P.MAX_LEGS
    ls = [x for x in (clean(l) for l in (legs or [])[:12]) if x]
    if not ls:
        return {"ok": False, "reason": "add a leg", "pair": None, "cap": cap}
    chk = P.check_ticket(sport, ls)
    if not chk.get("ok"):
        return {"ok": False, "reason": chk.get("reason") or "the engine refuses this ticket", "pair": chk.get("pair"), "cap": cap}
    rho: dict = {}
    pairs = []
    for i in range(len(ls)):
        for j in range(i + 1, len(ls)):
            try:
                r = P.relate(sport, ls[i], ls[j])
            except Exception:                                 # noqa: BLE001
                continue
            rho[(i, j)] = float(r.rho)
            if abs(r.rho) >= 0.01:
                pairs.append({"pair": [i, j], "rho": round(r.rho, 2), "why": r.mechanism or "", "measured": bool(r.measured)})
    ps = [l["p"] for l in ls]
    j = joint(ps, rho)
    decs = [_dec(l.get("odds")) for l in ls]
    pays = math.prod(decs) if all(decs) else None
    # A SAME-GAME TICKET IS PRICED BY THE BOOK'S OWN CORRELATION, never as
    # independent legs multiplied, so no edge is claimed against that
    # product: the page compares the book's own price with our fair one.
    same = any(P.game_key(ls[a]) == P.game_key(ls[b]) for a in range(len(ls)) for b in range(a + 1, len(ls)))
    out = {"ok": True, "cap": cap, "legs": len(ls), "pairs": pairs, "joint": round(j, 4),
           "independent": round(math.prod(ps), 4), "same_game": same,
           "fair": P.decimal_to_american(1 / j) if j > 0 else None,
           "pays": P.decimal_to_american(pays) if pays else None,
           "ev": round(j * pays - 1, 4) if pays and j > 0 and not same else None, "stacks": []}
    if len(ls) < cap:
        out["stacks"] = stacks(sport, ls, pool or [])
    return out


def stacks(sport: str, legs: list[dict], pool: list) -> list[dict]:
    """The board's legs that move with the ones chosen: each candidate's
    average correlation with them, the refused left out, the best first."""
    seen = {(l.get("player"), l.get("market"), str(l.get("side") or "").upper()) for l in legs}
    found = []
    for raw in (pool or [])[:MAX_POOL]:
        c = clean(raw)
        if not c or (c.get("player"), c.get("market"), str(c.get("side") or "").upper()) in seen:
            continue
        if P.check_ticket(sport, legs + [c]).get("ok") is not True:
            continue
        rs = []
        for l in legs:
            try:
                rs.append(float(P.relate(sport, l, c).rho))
            except Exception:                                 # noqa: BLE001
                rs = []
                break
        if not rs:
            continue
        avg = sum(rs) / len(rs)
        if avg >= STACK_RHO:
            found.append({**{k: c.get(k) for k in ("player", "market", "side", "line", "p", "odds")},
                          "rho": round(avg, 2)})
    found.sort(key=lambda x: (-x["rho"], -(x.get("p") or 0)))
    return found[:TOP]
