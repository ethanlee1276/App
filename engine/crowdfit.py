"""Is the crowd right? Measured against the games that finished.

`engine/crowd` records, on every build while a game has not started, the
home club's win chance from Kalshi, Polymarket, the sportsbooks (de-
vigged) and our own model. This joins those rows to the final scores and
answers the three questions Ethan's plan rests on (2026-09-26: "crowd
betting is more accurate ... usually a market has swung a certain way
when a large group of people already know the answer"):

  1. WHO IS MOST ACCURATE? Brier score and log loss per source, on the
     last pregame price, and each source against the books head to head
     on the same games (a paired difference, with its standard error —
     the only fair comparison, since the sources price different games).

  2. DOES THE CROWD KNOW SOMETHING THE BOOKS DO NOT? One logistic fit per
     venue with the books' price as a fixed offset:

         P(home wins) = sigmoid( logit(books) + β · [logit(venue) − logit(books)] )

     β = 0: the gap is noise — the books already knew. β = 1: the venue
     is simply right and the books should be moved all the way to it.
     Anything between is how far to lean.

  3. DO LATE SWINGS KEEP GOING? For each source, the last price as the
     offset and the move over the prior hours as the feature:

         P(home wins) = sigmoid( logit(p_last) + β · [logit(p_last) − logit(p_earlier)] )

     β > 0: the market under-reacts, so a swing is informed money still
     arriving — the "people already know" read. β < 0: it over-reacts,
     and a late swing is worth fading. β = 0: the last price already
     has it all.

NOTHING IS ADOPTED BY THIS FILE. It writes its findings to a state file
and prints them; a finding counts as MEASURED only with `MIN_GAMES`
games behind it and a coefficient at least `MIN_Z` standard errors from
zero. Anything less says "not enough games yet", in those words.

Standard library only.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from . import feedstate as _feedstate
from .crowd import ensure_tables

STATE_PATH = Path(_feedstate.path("crowdfit.json"))

SOURCES = ("kalshi", "polymarket", "books", "model", "model_raw")
VENUES = ("kalshi", "polymarket")
#: Games before any finding is called measured.
MIN_GAMES = 200
#: …and how far from zero, in standard errors.
MIN_Z = 2.0
#: The swing window: the move from the price about this many hours before
#: the last pregame one. A shorter gap is not a swing, it is a tick.
SWING_HOURS = 6.0
SWING_MIN_HOURS = 2.0
EPS = 1e-4


def _logit(p: float) -> float:
    p = min(1 - EPS, max(EPS, float(p)))
    return math.log(p / (1 - p))


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def fit_offset(rows: list[tuple[float, float, int]]) -> dict:
    """One-coefficient logistic with an offset: rows are (offset, x, y).
    Newton's method; perfect separation or a flat feature is HELD."""
    n = len(rows)
    if n < 10 or not any(abs(x) > 1e-9 for _o, x, _y in rows):
        return {"n": n, "beta": None, "se": None}
    b = 0.0
    for _ in range(50):
        g = h = 0.0
        for o, x, y in rows:
            p = _sig(o + b * x)
            g += (y - p) * x
            h += p * (1 - p) * x * x
        if h <= 1e-12:
            return {"n": n, "beta": None, "se": None}
        step = g / h
        b += step
        if abs(b) > 20:
            return {"n": n, "beta": None, "se": None, "note": "separated — too few games to say"}
        if abs(step) < 1e-8:
            break
    return {"n": n, "beta": round(b, 4), "se": round(1 / math.sqrt(h), 4)}


def verdict(fit: dict, words: dict) -> str:
    b, se, n = fit.get("beta"), fit.get("se"), fit.get("n", 0)
    if b is None or se is None or n < MIN_GAMES:
        return f"not enough games yet ({n} of {MIN_GAMES})"
    z = b / se if se else 0.0
    if abs(z) < MIN_Z:
        return words["zero"]
    return words["pos"] if b > 0 else words["neg"]


def _games(conn) -> dict:
    """{(sport, date, away, home): home_won} from the finals we hold."""
    out = {}
    for sport, date, period, home, away, hs, as_ in conn.execute(
            "SELECT sport, date, period, home, away, home_score, away_score FROM games "
            "WHERE home_score IS NOT NULL AND away_score IS NOT NULL").fetchall():
        if hs == as_:
            continue
        day = str(date or period or "")[:10]
        out[(sport, day, away, home)] = 1 if hs > as_ else 0
    return out


def load(conn, crowd_conn=None) -> list[dict]:
    """One row per finished game: its last pregame prices, the prices
    about `SWING_HOURS` before them, and the result. ``conn`` holds the
    finals (the history DB); ``crowd_conn`` the recorded prices
    (`crowd.DB_PATH`), the same connection when both are in one."""
    snaps = crowd_conn or conn
    ensure_tables(snaps)
    finals = _games(conn)
    by: dict = {}
    for r in snaps.execute(
            "SELECT sport, date, away, home, bucket_ts, kalshi, polymarket, books, model, model_raw "
            "FROM crowd_snaps ORDER BY bucket_ts"):
        r = tuple(r)
        k = r[:4]
        if k in finals:
            by.setdefault(k, []).append(r)
    out = []
    for k, snaps in by.items():
        last = snaps[-1]
        cut = last[4] - SWING_HOURS * 3600
        early = [s for s in snaps if s[4] <= cut] or [s for s in snaps
                                                     if s[4] <= last[4] - SWING_MIN_HOURS * 3600]
        before = early[-1] if early else None
        row = {"game": k, "y": finals[k]}
        for i, src in enumerate(SOURCES):
            if last[5 + i] is not None:
                row[src] = float(last[5 + i])
            if before is not None and before[5 + i] is not None:
                row[f"{src}_before"] = float(before[5 + i])
        out.append(row)
    return out


def accuracy(rows: list[dict]) -> dict:
    out = {}
    for s in SOURCES:
        got = [(r[s], r["y"]) for r in rows if r.get(s) is not None]
        if not got:
            continue
        brier = sum((p - y) ** 2 for p, y in got) / len(got)
        ll = -sum(math.log(min(1 - EPS, max(EPS, p if y else 1 - p))) for p, y in got) / len(got)
        out[s] = {"games": len(got), "brier": round(brier, 5), "log_loss": round(ll, 5)}
        if s != "books":
            pair = [((r[s] - r["y"]) ** 2) - ((r["books"] - r["y"]) ** 2)
                    for r in rows if r.get(s) is not None and r.get("books") is not None]
            if len(pair) >= 2:
                m = sum(pair) / len(pair)
                sd = math.sqrt(sum((d - m) ** 2 for d in pair) / (len(pair) - 1))
                out[s]["vs_books"] = {"games": len(pair), "brier_diff": round(m, 5),
                                      "se": round(sd / math.sqrt(len(pair)), 5),
                                      "reads": "negative = more accurate than the books"}
    return out


def crowd_vs_books(rows: list[dict]) -> dict:
    out = {}
    for v in VENUES:
        fit = fit_offset([(_logit(r["books"]), _logit(r[v]) - _logit(r["books"]), r["y"])
                          for r in rows if r.get(v) is not None and r.get("books") is not None])
        fit["verdict"] = verdict(fit, {
            "zero": f"{v} disagreeing with the books predicts nothing — the books already knew",
            "pos": f"{v} knows something the books do not: lean toward it by β",
            "neg": f"when {v} disagrees with the books, the books are right — fade it"})
        out[v] = fit
    return out


def swings(rows: list[dict]) -> dict:
    out = {}
    for s in ("kalshi", "polymarket", "books"):
        fit = fit_offset([(_logit(r[s]), _logit(r[s]) - _logit(r[f"{s}_before"]), r["y"])
                          for r in rows if r.get(s) is not None and r.get(f"{s}_before") is not None])
        fit["verdict"] = verdict(fit, {
            "zero": "the last price already has the swing in it",
            "pos": "late swings keep going — informed money still arriving",
            "neg": "late swings overshoot — fade them"})
        out[s] = fit
    return out


def run(conn, write: bool = True, crowd_conn=None) -> dict:
    rows = load(conn, crowd_conn)
    by_sport: dict = {}
    for r in rows:
        by_sport[r["game"][0]] = by_sport.get(r["game"][0], 0) + 1
    state = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "games": len(rows), "by_sport": by_sport,
             "min_games": MIN_GAMES, "accuracy": accuracy(rows),
             "crowd_vs_books": crowd_vs_books(rows), "swings": swings(rows)}
    if write:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass
    return state


def _beta(f: dict) -> str:
    return "—" if f.get("beta") is None else f"β {f['beta']:+.3f} ± {f['se']:.3f}"


def report(state: dict) -> str:
    lines = [f"Crowd fit — {state['games']} finished game(s) with stored prices "
             f"({', '.join(f'{k} {v}' for k, v in sorted(state['by_sport'].items())) or 'none yet'})"]
    lines.append("\n1. Accuracy on the last pregame price (lower is better):")
    for s, a in state["accuracy"].items():
        vs = a.get("vs_books")
        lines.append(f"   {s:<11} {a['games']:>5} games  Brier {a['brier']:.4f}  log loss {a['log_loss']:.4f}"
                     + (f"  vs books {vs['brier_diff']:+.4f} ± {vs['se']:.4f}" if vs else ""))
    lines.append("\n2. Does the crowd know something the books do not?")
    for v, f in state["crowd_vs_books"].items():
        lines.append(f"   {v:<11} {_beta(f)} on {f['n']} games — {f['verdict']}")
    lines.append("\n3. Do late swings keep going?")
    for s, f in state["swings"].items():
        lines.append(f"   {s:<11} {_beta(f)} on {f['n']} games — {f['verdict']}")
    return "\n".join(lines)
