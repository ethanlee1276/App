"""The week in one card: how the published books did over the last seven days.

Ethan, 2026-10-04: "do all of it" — a weekly recap, built by itself. The
Record page leads with it: each published book's W-L-P, units and hit rate
against what we claimed and what the prices said, the best hit and the
toughest miss. Every number is the journal's own; nothing here is new
arithmetic the Record page does not already trust.

Settled picks only (won, lost, push; voids out), by their game's calendar
day, the last DAYS days ending today (Eastern). The books are the ones the
site publishes, each on its own, never pooled. Standard library only.
"""
from __future__ import annotations

import datetime as _dt

DAYS = 7
BOOKS = (("Most Likely", ("likely_live",)), ("The one board", ("board",)), ("Edge picks", ("main",)))
ET_OFFSET_H = -4


def _implied(o) -> float | None:
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def _today(now=None) -> _dt.date:
    now = now or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    return (now + _dt.timedelta(hours=ET_OFFSET_H)).date()


def recap(conn, now=None, days: int = DAYS) -> dict:
    end = _today(now)
    start = end - _dt.timedelta(days=days - 1)
    out = {"from": start.isoformat(), "to": end.isoformat(), "books": []}
    for label, cats in BOOKS:
        marks = ",".join("?" * len(cats))
        rows = conn.execute(
            f"SELECT sport, player, market, side, line, odds, hit_prob, status, pnl_units, "
            f"COALESCE(game_day, date) AS day FROM bets WHERE category IN ({marks}) "
            f"AND status IN ('won','lost','push') AND COALESCE(game_day, date) BETWEEN ? AND ?",
            (*cats, start.isoformat(), end.isoformat())).fetchall()
        if not rows:
            continue
        w = sum(1 for r in rows if r[7] == "won")
        lo = sum(1 for r in rows if r[7] == "lost")
        p = sum(1 for r in rows if r[7] == "push")
        decided = [r for r in rows if r[7] in ("won", "lost")]
        claims = [float(r[6]) for r in decided if r[6] is not None]
        prices = [_implied(r[5]) for r in decided if _implied(r[5]) is not None]
        won = [r for r in rows if r[7] == "won" and r[5] is not None]
        lost = [r for r in rows if r[7] == "lost" and r[6] is not None]

        def pick(r):
            return {"sport": r[0], "player": r[1], "market": r[2], "side": r[3], "line": r[4],
                    "odds": r[5], "claim": None if r[6] is None else round(float(r[6]), 3)}
        best = max(won, key=lambda r: float(r[5])) if won else None
        worst = max(lost, key=lambda r: float(r[6])) if lost else None
        out["books"].append({
            "book": label, "w": w, "l": lo, "p": p,
            "units": round(sum(float(r[8] or 0) for r in rows), 2),
            "hit": round(w / len(decided), 3) if decided else None,
            "claimed": round(sum(claims) / len(claims), 3) if claims else None,
            "price": round(sum(prices) / len(prices), 3) if prices else None,
            "best": pick(best) if best else None,
            "worst": pick(worst) if worst else None,
            "by_sport": {s: {"w": sum(1 for r in rows if r[0] == s and r[7] == "won"),
                             "l": sum(1 for r in rows if r[0] == s and r[7] == "lost")}
                         for s in sorted({r[0] for r in rows})},
        })
    return out
