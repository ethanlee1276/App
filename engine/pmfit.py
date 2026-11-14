"""Fit the informed-flow weights against the markets that resolved.

`engine.predmarket` scores a trade out of 100 by adding up whichever
signals fired — 40/30/15/8 across the size tiers, 20 for order-book
impact, 15 for a niche market, 25 for a fresh wallet, then ×1.3 when
three of them stack. Every one of those numbers is a professional
estimate, and the module has always said so.

`flag_report` grades the composite honestly: hit rate against the entry
price's implied rate, flat-stake ROI, a calibration z-score, split by
score band. What it could never do is grade a COMPONENT, because the
only thing `pm_flags` recorded was the total. A year of resolutions
would still not have said which signal earned it — the same shape as
the game-line model, which shipped a "shrink halfway to the market"
guess for its whole life because no closing number was ever stored.

`predmarket.store_flags` now writes the breakdown. This fits it.

THE ESTIMATOR. Each resolved flag is one observation: did this trade's
side win, given that the market was charging its entry price for it?
The price is carried as a fixed offset in log-odds, so the coefficients
answer exactly one question — how much does each signal move the odds
BEYOND what the market already knew. A signal that only fires on trades
the market had already priced correctly gets a coefficient of zero,
which is the honest reading and is invisible to any hit-rate table.

    P(this side wins) = sigmoid( logit(implied) + Σ β_k · fired_k )

WHAT IT IS ALLOWED TO DO. Nothing, until the record is thick enough:
`MIN_FLAGS` resolved flags overall, `MIN_PER_SIGNAL` for any individual
signal, and a standard error tight enough that the number means
something. Perfect separation — every flag carrying a signal won —
returns nan and is HELD, because that is what a small lucky sample
looks like and adopting it would hand the feed an infinite weight.

Adoption rescales rather than replaces: the fitted coefficients are
normalised onto the same 0–100 scale the card already speaks, so a
board that has always shown "84" does not start showing "3.2". And a
signal that measures at zero drops to zero points rather than being
deleted — it keeps firing, keeps showing on the receipts, and stops
contributing to the number. The card should say "we looked and this one
does not predict anything", not quietly omit it.

Standard library only.
"""

from __future__ import annotations

import json
import math
import time

from . import feedstate as _feedstate
from .predmarket import SIGNAL_KEYS, ensure_tables

STATE_PATH = _feedstate.path("pmfit.json")

#: Resolved flags in total before any coefficient may be adopted.
MIN_FLAGS = 400
#: …and per signal, so a weight is never fitted on a handful of firings.
MIN_PER_SIGNAL = 60
#: A coefficient looser than this is a shrug with a decimal point.
MAX_SE = 0.6
#: The scale the card speaks. The fitted coefficients are log-odds; this
#: is what they are rescaled onto so the displayed score keeps meaning
#: what it has always meant.
SCORE_CEIL = 100.0
#: A single signal may not be worth more than this share of the ceiling,
#: however hard the fit leans. One coefficient running away with the
#: whole score is the failure mode of a thin sample, not a discovery.
MAX_SHARE = 0.5

_cache: dict = {}


class Coefficient:
    """One signal's fitted weight, with everything needed to judge it."""

    __slots__ = ("key", "beta", "se", "n", "wins", "held")

    def __init__(self, key, beta=float("nan"), se=float("nan"), n=0,
                 wins=0, held=""):
        self.key, self.beta, self.se = key, beta, se
        self.n, self.wins, self.held = n, wins, held

    def __repr__(self):                                # pragma: no cover
        if self.held:
            return f"<{self.key}: held — {self.held}>"
        return (f"<{self.key}: {self.beta:+.3f} ± {self.se:.3f} "
                f"on {self.n} flags>")


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def observations(conn) -> list[dict]:
    """One row per resolved flag that recorded which signals fired.

    A SELL is a bet on the other side, so its implied probability is
    ``1 - price`` and its win condition is already stored inverted by
    `predmarket.resolve_flags`. Flags written before the breakdown
    column existed carry NULL and are skipped rather than having a
    breakdown guessed backwards out of their total.
    """
    ensure_tables(conn)
    out = []
    for r in conn.execute(
            "SELECT price, side, won, signals FROM pm_flags "
            "WHERE status='settled' AND won IS NOT NULL "
            "AND signals IS NOT NULL AND signals <> ''"):
        try:
            price = float(r["price"])
            won = 1.0 if int(r["won"]) else 0.0
        except (TypeError, ValueError):
            continue
        implied = (1.0 - price) if r["side"] == "SELL" else price
        if not (0.0 < implied < 1.0):
            continue
        fired = {k for k in str(r["signals"]).split(",") if k in SIGNAL_KEYS}
        if not fired:
            continue
        out.append({"offset": _logit(implied), "won": won, "fired": fired})
    return out


def _fit(rows: list[dict], keys: list[str]) -> tuple[dict, dict]:
    """Newton on the multi-signal logistic with the price as an offset.

    Returns ``({key: beta}, {key: se})``, or ``({}, {})`` when the fit
    did not converge — which is what perfect separation looks like from
    in here, and is a refusal rather than an answer.
    """
    beta = {k: 0.0 for k in keys}
    for _ in range(80):
        grad = {k: 0.0 for k in keys}
        hess = [[0.0] * len(keys) for _ in keys]
        for r in rows:
            z = r["offset"] + sum(beta[k] for k in keys if k in r["fired"])
            p = 1.0 / (1.0 + math.exp(-max(min(z, 40.0), -40.0)))
            w = p * (1.0 - p)
            for i, ki in enumerate(keys):
                if ki not in r["fired"]:
                    continue
                grad[ki] += r["won"] - p
                for j, kj in enumerate(keys):
                    if kj in r["fired"]:
                        hess[i][j] += w
        step = _solve(hess, [grad[k] for k in keys])
        if step is None:
            return {}, {}
        for i, k in enumerate(keys):
            beta[k] += step[i]
        if max(abs(x) for x in step) < 1e-8:
            break
    else:
        return {}, {}
    inv = _invert(hess)
    if inv is None:
        return {}, {}
    se = {}
    for i, k in enumerate(keys):
        v = inv[i][i]
        se[k] = math.sqrt(v) if v > 0 else float("nan")
    return beta, se


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gauss-Jordan with partial pivoting. None when singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        d = m[col][col]
        m[col] = [x / d for x in m[col]]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            if f:
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def _invert(a: list[list[float]]) -> list[list[float]] | None:
    n = len(a)
    cols = []
    for i in range(n):
        e = [1.0 if j == i else 0.0 for j in range(n)]
        c = _solve(a, e)
        if c is None:
            return None
        cols.append(c)
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def fit_signals(conn) -> dict:
    """``{"coefficients": [...], "n": int, "held": [...]}``."""
    rows = observations(conn)
    counts = {k: sum(1 for r in rows if k in r["fired"]) for k in SIGNAL_KEYS}
    wins = {k: sum(r["won"] for r in rows if k in r["fired"])
            for k in SIGNAL_KEYS}
    held, keys = [], []
    for k in SIGNAL_KEYS:
        if counts[k] < MIN_PER_SIGNAL:
            held.append(Coefficient(k, n=counts[k],
                                    held=f"{counts[k]} flags, "
                                         f"needs {MIN_PER_SIGNAL}"))
        else:
            keys.append(k)
    if len(rows) < MIN_FLAGS or not keys:
        return {"n": len(rows), "coefficients": [],
                "held": held + ([Coefficient("*", n=len(rows),
                                             held=f"{len(rows)} resolved "
                                                  f"flags, needs {MIN_FLAGS}")]
                                if len(rows) < MIN_FLAGS else [])}
    beta, se = _fit(rows, keys)
    if not beta:
        return {"n": len(rows), "coefficients": [],
                "held": held + [Coefficient(
                    "*", n=len(rows),
                    held="the fit did not converge — with this record every "
                         "flagged trade on some signal went the same way, "
                         "which is what a lucky sample looks like")]}
    good = []
    for k in keys:
        if se[k] != se[k] or se[k] > MAX_SE:
            held.append(Coefficient(k, beta=beta[k], se=se[k], n=counts[k],
                                    wins=wins[k],
                                    held=f"±{se[k]:.2f} is looser than the "
                                         f"±{MAX_SE} needed to act on"))
            continue
        good.append(Coefficient(k, beta=beta[k], se=se[k], n=counts[k],
                                wins=wins[k]))
    return {"n": len(rows), "coefficients": good, "held": held}


def points_from(coefficients: list[Coefficient]) -> dict:
    """Fitted coefficients rescaled onto the card's own 0–100 scale.

    A negative or zero coefficient becomes ZERO POINTS, not a negative
    score and not a deleted signal: it keeps firing and keeps showing on
    the receipts, and stops moving the number. "We looked and this one
    does not predict anything" is a thing the card should be able to say.
    """
    positive = {c.key: max(0.0, c.beta) for c in coefficients}
    total = sum(positive.values())
    if total <= 0:
        return {k: 0 for k in positive}
    # int throughout: these are POINTS on a card, and a "50.0" that
    # round-trips through JSON as a float is a display bug waiting to
    # happen in a place nobody would look for one.
    cap = int(SCORE_CEIL * MAX_SHARE)
    return {k: int(min(cap, round(SCORE_CEIL * v / total)))
            for k, v in positive.items()}


def refresh(conn) -> dict:
    """Fit and persist. Returns ``{"adopted": {...}, "held": [...], "n": n}``."""
    result = fit_signals(conn)
    held = [{"key": c.key, "why": c.held} for c in result["held"]]
    points = points_from(result["coefficients"])
    if not points:
        return {"adopted": {}, "held": held, "n": result["n"]}
    state = {"points": points, "n": result["n"], "fit_at": time.time(),
             "detail": {c.key: {"beta": round(c.beta, 4),
                                "se": round(c.se, 4), "n": c.n,
                                "wins": int(c.wins)}
                        for c in result["coefficients"]}}
    _write_state(state)
    _cache.clear()
    return {"adopted": points, "held": held, "n": result["n"]}


def _read_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    import os
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def measured() -> dict | None:
    """The persisted fit, or None. Never raises — this is read on the
    scoring path for every trade in the feed."""
    if "state" in _cache:
        return _cache["state"]
    entry = _read_state()
    ok = False
    if entry:
        try:
            pts = entry["points"]
            ok = (int(entry["n"]) >= MIN_FLAGS and isinstance(pts, dict)
                  and pts and all(0 <= float(v) <= SCORE_CEIL
                                  for v in pts.values()))
        except (KeyError, TypeError, ValueError):
            ok = False
    _cache["state"] = entry if ok else None
    return _cache["state"]


def points_for(key: str) -> int | None:
    """The measured points for one signal, or None if never fitted."""
    state = measured()
    if not state:
        return None
    try:
        return int(state["points"][key])
    except (KeyError, TypeError, ValueError):
        return None


def note() -> str | None:
    """One line for the desk explaining what the record has changed."""
    state = measured()
    if not state:
        return None
    try:
        n = int(state["n"])
        pts = state["points"]
    except (KeyError, TypeError, ValueError):
        return None
    dead = sorted(k for k, v in pts.items() if not v)
    line = (f"Signal weights measured on {n} resolved flags rather than "
            f"assigned")
    if dead:
        line += (f" — {', '.join(dead)} moved no odds the price had not "
                 f"already moved, and now scores nothing")
    return line + "."


if __name__ == "__main__":                       # pragma: no cover
    import sqlite3
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "data/predmarket.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    out = refresh(conn)
    print(f"{out['n']} resolved flags with a recorded breakdown")
    for k, v in sorted(out["adopted"].items()):
        print(f"  adopted {k:14} {v:3} pts")
    for h in out["held"]:
        print(f"  held    {h['key']:14} {h['why']}")
    conn.close()
