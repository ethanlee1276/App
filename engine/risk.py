"""One risk view of every open bet — how the tickets move together, the bad night, and the hedge that cuts the most.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 13. My Bets lists
open tickets one at a time, each with its own chance. Nobody's night is
one ticket: three slips that all lean on the same quarterback are one bet
three times, and a reader who sees three 30% tickets thinks he has three
chances when he may have one.

THE NIGHT, SIMULATED. Every open leg once (the same leg on two slips is
one event), each with our chance where a board prices it
(`slipgrade.price_leg`) and its own price's chance otherwise, joined by the
parlay engine's correlation for legs in one game (`parlays.relate`), drawn
together NIGHTS times through a Gaussian copula. A ticket wins when all its
legs do. From that: what the night is worth on average, how widely it
swings, the bad night (the worst one in twenty), the chance every ticket
loses, and how much of the money rides on each player and each game.

THE HEDGE. For each open leg, a bet on its other side at a fair-ish price
(its own price's chance with a book's margin put back), at stakes from a
tenth of the money at risk to all of it; the one that lifts the bad night
most is named with its stake, what it costs on average, and the swing
before and after — or none, when no single hedge lifts the bad night by
MIN_LIFT of the money at risk. (The stake that only shrinks the swing can
make the bad night worse: it loses exactly when the leg it hedges wins
and the rest of the book does not.) A reading: it places nothing and the board
reads none of it.

Standard library only.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

NIGHTS = 5000
MAX_BETS = 60
MAX_LEGS = 12
#: A hedge's other side: its own price's chance plus a book's margin.
HEDGE_MARGIN = 0.045
BAD_NIGHT = 0.05
#: A hedge is named only if it lifts the bad night by this share of the money at risk.
MIN_LIFT = 0.05
_N = NormalDist()


def _dec(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o >= 100:
        return 1.0 + o / 100.0
    if o <= -100:
        return 1.0 + 100.0 / -o
    return None


def implied(odds) -> float | None:
    d = _dec(odds)
    return 1.0 / d if d else None


def leg_key(leg: dict) -> str:
    who = leg.get("player") or leg.get("team") or leg.get("game") or ""
    return f"{leg.get('sport', '')}|{who}|{leg.get('market', '')}|{leg.get('side', '')}|{leg.get('line', '')}".lower()


def clean_bets(raw) -> list:
    """Open tickets as the page sends them: a stake, a price, and legs in
    the slip reader's shape (a hand-logged bet with no legs is one leg of
    its own, priced by its odds)."""
    from . import slipgrade as SG
    out = []
    for b in (raw if isinstance(raw, list) else [])[:MAX_BETS]:
        if not isinstance(b, dict):
            continue
        stake = SG._num(b.get("stake"))
        dec = _dec(b.get("odds"))
        if stake <= 0 or not dec:
            continue
        legs = []
        if isinstance(b.get("legs"), list) and b["legs"]:
            raw_legs = [{**l, "sport": str(l.get("sport") or "other").lower()} for l in b["legs"][:MAX_LEGS]
                        if isinstance(l, dict)]
            legs = SG.clean_slip({"legs": raw_legs})["legs"]
        if not legs:
            legs = [{"sport": str(b.get("sport") or "other").lower(), "player": "", "team": "", "game": "",
                     "market": "other", "side": "", "line": 0.0, "odds": SG._odds(b.get("odds")),
                     "text": SG._text(b.get("desc"), 120), "solo": str(b.get("id") or len(out))}]
        out.append({"id": str(b.get("id") or len(out))[:40], "stake": stake, "dec": dec,
                    "desc": SG._text(b.get("desc"), 160), "legs": legs})
    return out


def price_legs(bets: list, boards: dict | None) -> dict:
    """``{leg key: {"leg", "prob", "source"}}`` — our chance where a board
    prices it, else its own price's (a ticket's legs without their own
    price share the ticket's)."""
    from . import slipgrade as SG
    out = {}
    for b in bets:
        n = len(b["legs"])
        for leg in b["legs"]:
            k = leg_key(leg) + (f"|{leg['solo']}" if leg.get("solo") else "")
            if k in out:
                continue
            prob, source = None, "price"
            if boards and leg["market"] != "other":
                got = SG.price_leg(boards, leg, read=False)
                if got.get("prob") is not None:
                    prob, source, leg = float(got["prob"]), "ours", {**leg, **{f: got.get(f) for f in
                                                                                ("team", "opponent", "league", "row")}}
            if prob is None:
                prob = implied(leg.get("odds")) or (implied_from_ticket(b["dec"], n))
                prob = None if prob is None else prob / (1.0 + HEDGE_MARGIN)
            out[k] = {"leg": leg, "prob": min(0.995, max(0.005, prob or 0.5)), "source": source}
    return out


def implied_from_ticket(dec: float, n: int) -> float | None:
    return (1.0 / dec) ** (1.0 / n) if dec and n else None


def correlations(keys: list, priced: dict) -> list:
    """The matrix the copula draws with: the parlay engine's number for two
    legs in one game, zero across games."""
    from . import parlays as P
    from . import slipgrade as SG
    n = len(keys)
    rho = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = priced[keys[i]]["leg"], priced[keys[j]]["leg"]
            if a.get("market") == "other" or b.get("market") == "other":
                continue
            la, lb = SG._relation_leg({**a, "row": a.get("row")}), SG._relation_leg({**b, "row": b.get("row")})
            if P.game_key(la) != P.game_key(lb) or not any(P.game_key(la)[0]):
                continue
            rel = P.relate(a.get("league") or a.get("sport") or "nfl", la, lb)
            r = rel.rho if rel.measured else rel.rho * P.RHO_SHRINK
            rho[i][j] = rho[j][i] = max(-0.9, min(0.9, float(r)))
    return rho


def cholesky(m: list) -> list:
    """Lower-triangular L with L·Lᵀ = m, shrinking the off-diagonal until
    the matrix is one a copula can draw from."""
    n = len(m)
    shrink = 1.0
    for _ in range(30):
        a = [[m[i][j] * (1.0 if i == j else shrink) for j in range(n)] for i in range(n)]
        low = [[0.0] * n for _ in range(n)]
        ok = True
        for i in range(n):
            for j in range(i + 1):
                s = a[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
                if i == j:
                    if s <= 1e-9:
                        ok = False
                        break
                    low[i][j] = math.sqrt(s)
                else:
                    low[i][j] = s / low[j][j]
            if not ok:
                break
        if ok:
            return low
        shrink *= 0.85
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def simulate(bets: list, priced: dict, nights: int = NIGHTS, seed: int = 5) -> dict:
    """Each night's result for the whole book, and each leg's wins."""
    keys = list(priced)
    low = cholesky(correlations(keys, priced))
    cut = [_N.inv_cdf(priced[k]["prob"]) for k in keys]
    index = {k: i for i, k in enumerate(keys)}
    rng = random.Random(seed)
    n = len(keys)
    pnl, wins = [0.0] * nights, [[False] * nights for _ in range(n)]
    ticket_legs = [[index[leg_key(l) + (f"|{l['solo']}" if l.get("solo") else "")] for l in b["legs"]] for b in bets]
    for t in range(nights):
        e = [rng.gauss(0.0, 1.0) for _ in range(n)]
        for i in range(n):
            z = sum(low[i][k] * e[k] for k in range(i + 1))
            wins[i][t] = z < cut[i]
        total = 0.0
        for b, legs in zip(bets, ticket_legs):
            total += b["stake"] * (b["dec"] - 1.0) if all(wins[i][t] for i in legs) else -b["stake"]
        pnl[t] = total
    return {"keys": keys, "pnl": pnl, "wins": wins}


def _sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _quantile(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(p * len(s))))]


def best_hedge(bets: list, priced: dict, sim: dict) -> dict | None:
    """The one bet on a leg's other side that lifts the bad night most:
    every open leg, at stakes from a tenth of the money at risk to all of
    it. Named only when it lifts the bad night by MIN_LIFT of the money at
    risk; its average cost and the swing before and after come with it."""
    pnl = sim["pnl"]
    at_risk = sum(b["stake"] for b in bets)
    base_bad, base_sd = _quantile(pnl, BAD_NIGHT), _sd(pnl)
    best = None
    for i, k in enumerate(sim["keys"]):
        p = priced[k]
        own = implied(p["leg"].get("odds"))
        if own is None or p["leg"].get("market") == "other":
            continue
        d = 1.0 / min(0.97, max(0.03, 1.0 - own + HEDGE_MARGIN))
        h = [(d - 1.0) if not w else -1.0 for w in sim["wins"][i]]
        mh = sum(h) / len(h)
        for step in range(1, 11):
            stake = at_risk * step / 10.0
            new = [a + stake * b for a, b in zip(pnl, h)]
            bad = _quantile(new, BAD_NIGHT)
            if best is None or bad > best["bad_night_after"]:
                leg = p["leg"]
                best = {"leg": leg.get("text") or f"{leg.get('player') or leg.get('team')} {leg.get('side')} {leg.get('line')}",
                        "other_side_price": round(d, 3), "stake": round(stake, 2), "cost": round(stake * mh, 2),
                        "bad_night_before": round(base_bad, 2), "bad_night_after": round(bad, 2),
                        "sd_before": round(base_sd, 2), "sd_after": round(_sd(new), 2)}
    return best if best and best["bad_night_after"] - base_bad >= MIN_LIFT * at_risk else None


def exposure(bets: list, priced: dict) -> dict:
    """How much of the money at risk rides on each player and each game."""
    total = sum(b["stake"] for b in bets) or 1.0
    players, games = {}, {}
    for b in bets:
        seen_p, seen_g = set(), set()
        for l in b["legs"]:
            k = leg_key(l) + (f"|{l['solo']}" if l.get("solo") else "")
            leg = priced.get(k, {}).get("leg", l)
            if leg.get("player"):
                seen_p.add(leg["player"])
            g = leg.get("game") or (" @ ".join(x for x in (leg.get("opponent"), leg.get("team")) if x))
            if g:
                seen_g.add(g)
        for p in seen_p:
            players[p] = players.get(p, 0.0) + b["stake"]
        for g in seen_g:
            games[g] = games.get(g, 0.0) + b["stake"]
    top = lambda d: [{"name": k, "stake": round(v, 2), "share": round(v / total, 3)}   # noqa: E731
                     for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:5]]
    return {"players": top(players), "games": top(games)}


def analyze(raw_bets, boards: dict | None = None, nights: int = NIGHTS) -> dict:
    bets = clean_bets(raw_bets)
    if not bets:
        return {"bets": 0}
    priced = price_legs(bets, boards)
    sim = simulate(bets, priced, nights)
    pnl = sim["pnl"]
    stake = sum(b["stake"] for b in bets)
    all_lose = sum(1 for x in pnl if abs(x + stake) < 1e-9) / len(pnl)
    return {"bets": len(bets), "legs": len(priced), "at_risk": round(stake, 2),
            "ours": sum(1 for p in priced.values() if p["source"] == "ours"),
            "expected": round(sum(pnl) / len(pnl), 2), "swing": round(_sd(pnl), 2),
            "profit_chance": round(sum(1 for x in pnl if x > 0) / len(pnl), 3),
            "bad_night": round(_quantile(pnl, BAD_NIGHT), 2), "all_lose": round(all_lose, 3),
            "independent_all_lose": round(math.prod(1.0 - _ticket_chance(b, priced) for b in bets), 3),
            "exposure": exposure(bets, priced), "hedge": best_hedge(bets, priced, sim), "nights": len(pnl)}


def _ticket_chance(b: dict, priced: dict) -> float:
    return math.prod(priced[leg_key(l) + (f"|{l['solo']}" if l.get("solo") else "")]["prob"] for l in b["legs"])
