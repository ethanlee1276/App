"""Round prices for every fight the model prices, off the finish times we store.

Ethan, 2026-10-14: "Do 1-7 and the ones we download but don't use" — and
on that list, UFC finish times: "They'd allow 'goes the distance' and
round reads; the odds feed only prices the moneyline, so these would be
our own fair prices to shop by hand."

WHAT WAS MISSING. Whether a fight goes the distance was already priced,
off the method model (`markets.implied_markets`, the "distance" rows).
Rounds were not: a round price needs WHEN a finish lands, the dossiers
hold no finish times, and the script's front-loaded hazard is a written
prior (`triangle.HAZARD_SHAPE`) that is never to price a round market.
Since 2026-10-14 `ufc_fights` holds how and when every recent bout of
every fighter on the card ended (engine/ufc/history).

THE SHAPE. When a finish lands, given that the fight is finished: the
spread of finish times over every stored bout scheduled for the same
number of rounds, each bout once by its ESPN id (the league's shape),
leaned toward the two fighters' own fights that ended inside the distance
(won or lost), each worth one fight against PRIOR fights' worth of the
league:

    F(t) = (n_own · F_own(t) + PRIOR · F_league(t)) / (n_own + PRIOR)

and the chance the fight ends inside the distance is the method model's,
so the round prices agree with the distance price by construction:

    under X.5 rounds = P(inside) · F(before X·5:00 + 2:30)
    ends in round r  = P(inside) · (F(r·5:00) − F((r − 1)·5:00))

NOT MEASURED. Nothing here has been scored against a result: PRIOR is a
written weight and a fighter's own finishes are few. These are fair
numbers to shop by hand — the odds feed carries the moneyline only, so no
book price ever sits beside them, nothing is staked and nothing journals.
Fewer than MIN_LEAGUE stored finishes at the fight's length, and there is
no round price at all, never the written prior. Three rounds is assumed
where the feed names none, as the card's own duration read says.

Standard library only.
"""

from __future__ import annotations

import bisect

#: Seconds in a round.
ROUND_S = 300.0
#: Stored finishes at a scheduled length before the league's shape is read
#: at all; below it the card carries no round price.
MIN_LEAGUE = 120
#: The league's weight, in fights, against the pair's own finishes.
PRIOR = 10
#: The over/under lines a book hangs, by scheduled rounds.
LINES = {3: (1.5, 2.5), 5: (1.5, 2.5, 3.5, 4.5)}
FINISHES = ("KO/TKO", "SUB")


def _clock_s(clock) -> float | None:
    try:
        m, s = str(clock or "").strip().split(":")
        return int(m) * 60 + int(s)
    except (TypeError, ValueError):
        return None


def finish_secs(method: str, rnd, clock) -> float | None:
    """When a finish landed, in seconds from the opening bell; None for a
    decision, a draw or no contest, or a finish whose round or clock the
    record does not carry (the stored duration reads a full fight then)."""
    if method not in FINISHES or not rnd:
        return None
    c = _clock_s(clock)
    if c is None:
        return None
    return (int(rnd) - 1) * ROUND_S + min(c, ROUND_S)


def _finishes(rows, rounds: int) -> list[float]:
    """Sorted finish times inside ``rounds``, each bout once."""
    seen: set = set()
    out = []
    for comp, method, rnd, clock in rows:
        if not comp or comp in seen:
            continue
        seen.add(comp)
        t = finish_secs(method, rnd, clock)
        if t is not None and 0 < t <= rounds * ROUND_S:
            out.append(t)
    return sorted(out)


def league(conn, rounds: int) -> list[float]:
    """Every stored bout scheduled for ``rounds`` that ended inside it."""
    return _finishes(conn.execute(
        "SELECT comp_id, method, rnd, clock FROM ufc_fights WHERE rounds=?", (int(rounds),)), rounds)


def own(conn, names, rounds: int) -> list[float]:
    """The two fighters' own finishes inside ``rounds`` minutes' worth of
    fighting, whatever the bout was scheduled for, each bout once."""
    from .history import resolve
    stored = [s for s in (resolve(conn, n) for n in names or []) if s]
    if not stored:
        return []
    marks = ",".join("?" * len(stored))
    return _finishes(conn.execute(
        f"SELECT comp_id, method, rnd, clock FROM ufc_fights WHERE fighter IN ({marks})", stored), rounds)


def _before(xs: list[float], t: float) -> float:
    """Share of ``xs`` strictly before ``t``."""
    return bisect.bisect_left(xs, t) / len(xs) if xs else 0.0


def _by(xs: list[float], t: float) -> float:
    """Share of ``xs`` at or before ``t``."""
    return bisect.bisect_right(xs, t) / len(xs) if xs else 0.0


def board(p_inside: float, rounds: int, league_xs: list[float], own_xs: list[float]) -> dict | None:
    """``{"rows": [{market, selection, p}], "n_league", "n_own", "rounds",
    "note"}``, or None without enough stored finishes at this length."""
    rounds = 5 if int(rounds or 3) == 5 else 3
    if len(league_xs) < MIN_LEAGUE:
        return None
    n = len(own_xs)
    wl, wo = PRIOR / (n + PRIOR), n / (n + PRIOR)

    def blend(f, t):
        return wl * f(league_xs, t) + wo * (f(own_xs, t) if n else 0.0)

    p = max(0.0, min(1.0, float(p_inside or 0.0)))
    rows = []
    for x in LINES[rounds]:
        under = round(p * blend(_before, (int(x) * ROUND_S) + ROUND_S / 2), 4)
        rows.append({"market": "round", "selection": f"Under {x:g} rounds", "p": under})
        rows.append({"market": "round", "selection": f"Over {x:g} rounds", "p": round(1.0 - under, 4)})
    for r in range(1, rounds + 1):
        rows.append({"market": "exact_round", "selection": f"Ends in round {r}",
                     "p": round(p * (blend(_by, r * ROUND_S) - blend(_by, (r - 1) * ROUND_S)), 4)})
    return {"rows": rows, "n_league": len(league_xs), "n_own": n, "rounds": rounds,
            "note": (f"When a finish lands: {len(league_xs)} stored {rounds}-round finishes, leaned "
                     f"toward these two fighters' own {n} — not measured against results; a fair "
                     f"number to shop, never a bet.")}


def attach(result: dict, conn) -> int:
    """Hang the round prices on every fight the model priced (picks and
    near misses): unpriced rows on its ``market_board``, the fair number
    to shop, and the read itself as ``round_read``. Returns how many
    fights carry them; a fight with no stored shape carries none."""
    from . import markets
    shapes: dict = {}
    n = 0
    for row in list(result.get("picks") or []) + list(result.get("pass_list") or []):
        if not isinstance(row, dict) or row.get("p_distance") is None or "market_board" not in row:
            continue
        rounds = 5 if int(row.get("scheduled_rounds") or 3) == 5 else 3
        if rounds not in shapes:
            shapes[rounds] = league(conn, rounds)
        names = [f.get("name") for f in row.get("fighters") or [] if isinstance(f, dict)]
        got = board(1.0 - float(row["p_distance"]), rounds, shapes[rounds], own(conn, names, rounds))
        if not got:
            continue
        # A number no book hangs (under 1% or over 99%) is not one to shop.
        row["market_board"] = [c for c in row["market_board"]
                               if c.get("market") not in ("round", "exact_round")] + [
            markets.price_market(r, None, None, thin_data=bool(row.get("thin_data")))
            for r in got["rows"] if 0.01 <= r["p"] <= 0.99]
        row["round_read"] = {k: got[k] for k in ("n_league", "n_own", "rounds", "note")}
        n += 1
    return n
