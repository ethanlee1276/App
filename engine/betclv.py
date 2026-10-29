"""Closing line value for a member's own bets: what their price was worth
against where the market closed.

Ethan's research (2026-10-29): "Live CLV: for each logged bet, current price
vs. your entry, then closing price vs. entry once the game starts. Pikkit
hides this behind Pro; you can make it free, because it's your
positioning" — and from the same paper, rank leaderboards "by CLV % ... not
profit" and a process badge for "Beat the close". CLV is the honest measure
of a bet before its result is known, the one the Record page already holds
our own picks to.

WHERE IT COMES FROM. The slip watch grades every saved slip each minute
(engine/slipwatch.sweep), each leg with what the books show at its own
number right now (sliplive.leg_prices: the best bettable price and the
market's chance with the margin taken out). Until a leg's game starts,
`note` keeps the latest of those; the last one kept before the start is the
leg's close. Nothing is fetched for this: it rides the sweep's own read.

THE NUMBER. A leg's CLV is what its entry price was worth at the close:

    entry decimal × closing no-vig chance − 1

the expected return of the bet if the closing market was right (the same
measure as the Record page's price CLV). Where the close had no two-sided
market to take the margin out, the best closing price's own implied chance
stands in, which understates the number (the margin is still in it). A
ticket's is its payout × the product of its legs' closing chances − 1,
when every leg has a close. Hand-logged bets have no legs to price and no
CLV.

KEPT per bet and leg: the entry price, the last pre-game best price and fair
chance, and when — deleted with the account (engine/accounts) and
KEEP_DAYS after. Standard library only.
"""
from __future__ import annotations

import math
import time

#: Rows older than this go.
KEEP_DAYS = 90
#: A leg whose game is under way or over has its close frozen.
STARTED = ("live", "final", "post", "in")


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS bet_clv (
        user_id INTEGER NOT NULL, bet_id TEXT NOT NULL, leg INTEGER NOT NULL,
        entry REAL, best REAL, fair REAL, at REAL NOT NULL,
        PRIMARY KEY (user_id, bet_id, leg))""")


def _american(o) -> float | None:
    try:
        v = float(str(o).replace("+", "").replace("−", "-"))
    except (TypeError, ValueError):
        return None
    return v if abs(v) >= 100 else None


def decimal(o) -> float | None:
    v = _american(o)
    if v is None:
        return None
    return 1 + v / 100 if v > 0 else 1 + 100 / abs(v)


def implied(o) -> float | None:
    d = decimal(o)
    return 1 / d if d else None


def leg_clv(entry, fair, best=None) -> float | None:
    """What the entry price was worth at the close: entry decimal × the
    closing chance − 1 (the no-vig chance; the best price's own, margin in,
    where there was none)."""
    d = decimal(entry)
    p = fair if isinstance(fair, (int, float)) and 0 < fair < 1 else implied(best)
    if not d or not p:
        return None
    return d * p - 1


def note(conn, user_id, bet_id: str, card: dict, now: float | None = None) -> int:
    """Keep each not-yet-started leg's latest prices from a graded card
    (engine/slipgrade.grade with a live reader). Returns legs kept."""
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    kept = 0
    for i, leg in enumerate((card or {}).get("legs") or []):
        if str(((leg or {}).get("live") or {}).get("state") or "") in STARTED:
            continue
        pr = leg.get("price") or {}
        best, fair = _american(pr.get("best")), pr.get("fair")
        if best is None and not isinstance(fair, (int, float)):
            continue
        conn.execute("INSERT INTO bet_clv (user_id, bet_id, leg, entry, best, fair, at) VALUES (?,?,?,?,?,?,?) "
                     "ON CONFLICT(user_id, bet_id, leg) DO UPDATE SET entry = excluded.entry, best = excluded.best, "
                     "fair = excluded.fair, at = excluded.at",
                     (int(user_id), str(bet_id)[:40], i, _american(leg.get("odds")), best,
                      float(fair) if isinstance(fair, (int, float)) else None, t))
        kept += 1
    return kept


def ticket(conn, user_id, bet_id: str, legs: int | None = None, payout=None) -> dict:
    """{"legs": [{leg, entry, close, clv}], "clv": the ticket's or None}.
    `legs` is how many the ticket has: the ticket's number needs every one."""
    ensure_tables(conn)
    rows = conn.execute("SELECT leg, entry, best, fair FROM bet_clv WHERE user_id = ? AND bet_id = ? ORDER BY leg",
                        (int(user_id), str(bet_id)[:40])).fetchall()
    out = [{"leg": r[0], "entry": r[1], "close": r[2], "fair": r[3], "clv": leg_clv(r[1], r[3], r[2])} for r in rows]
    whole = None
    n = len(out) if legs is None else int(legs)
    if out and len(out) == n and all(x["clv"] is not None for x in out):
        if n == 1:
            whole = out[0]["clv"]
        else:
            ps = [x["fair"] if x["fair"] else implied(x["close"]) for x in out]
            d = decimal(payout) or math.prod(decimal(x["entry"]) or 0 for x in out)
            whole = d * math.prod(ps) - 1 if d and all(ps) else None
    return {"legs": out, "clv": whole}


def words(clv) -> str:
    """"beat the close by 4.2%" / "3.1% worse than the close", or ""."""
    if clv is None:
        return ""
    pct = abs(clv) * 100
    if pct < 0.05:
        return "level with the close"
    return f"beat the close by {pct:.1f}%" if clv > 0 else f"{pct:.1f}% worse than the close"


def prune(conn, now: float | None = None) -> int:
    ensure_tables(conn)
    cur = conn.execute("DELETE FROM bet_clv WHERE at < ?", ((time.time() if now is None else now) - KEEP_DAYS * 86400,))
    return cur.rowcount
