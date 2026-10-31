"""The smart paywall: what members' alerts caught on a free account's own
teams last week.

Ethan's second research paper (2026-10-29): "Smart paywall: shows a free
user what paid alerts caught on their teams last week" — in place of a
generic "upgrade" line, the plans page says, for a signed-in free account
that follows teams, how many picks the board posted on those teams in the
last WEEK_DAYS and how the graded ones went, win or lose.

ONLY WHAT IS ALREADY PUBLIC. A pick whose game is over is on the Record
page for anybody to read (and in its receipts file); this counts those, on
the reader's teams, and never names one: no player, no market, no price,
and never a pick still open (free accounts never learn which of their
players have picks). Picks still open are counted only as a number.
Read from the journal the Record page reads (engine/ledger, the pooled
books: each pick once). Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WEEK_DAYS = 7
#: A week worth saying: at least this many picks on their teams.
MIN_PICKS = 2
MAX_TEAMS = 12


def _teams(settings) -> list:
    """[(sport, ABBR)] from a member's synced settings ("nfl:KC")."""
    out = []
    for t in (settings or {}).get("teams") or []:
        sport, _, abbr = str(t).partition(":")
        if sport and abbr.strip():
            out.append((sport.lower(), abbr.strip().upper()))
    return out[:MAX_TEAMS]


def caught(lconn, teams: list, now: float | None = None) -> dict | None:
    """{"n", "w", "l", "p", "open", "teams"} for the pooled books' staked
    picks on these teams in the last WEEK_DAYS; None under MIN_PICKS."""
    from engine import ledger as L
    if not teams:
        return None
    t = time.time() if now is None else float(now)
    since = (_dt.datetime.fromtimestamp(t, ET).date() - _dt.timedelta(days=WEEK_DAYS)).isoformat()
    books, bargs = L.books_sql(L.POOLED_BOOKS)
    w = l = p = op = 0
    hit: set = set()
    for sport, abbr in teams:
        rows = lconn.execute(
            f"SELECT status FROM bets WHERE {books} AND date >= ? AND LOWER(sport) = ? AND UPPER(team) = ? "
            "AND stake_units > 0", [*bargs, since, sport, abbr]).fetchall()
        for (status,) in rows:
            s = str(status or "")
            w += s == "won"
            l += s == "lost"
            p += s == "push"
            op += s not in ("won", "lost", "push")
            hit.add(abbr)
    n = w + l + p + op
    if n < MIN_PICKS:
        return None
    return {"n": n, "w": w, "l": l, "p": p, "open": op, "teams": sorted(hit)}
