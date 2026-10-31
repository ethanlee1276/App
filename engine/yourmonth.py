"""Your month: one member's month here, for the Karma tab's "Your month" card,
its picture for the share sheet, and the Live tab's line in a month's first
week (js/karma.js krMonthHTML, krMonthCanvas).

Ethan, 2026-10-29: "keep building". A month's recap is a reason to come back
on the 1st the way a week's is on a Monday (Strava's month, Spotify's
Wrapped), and a picture worth sending a friend. It is built only from what
the site already keeps for the member and already shows them: the karma
they earned and the days they earned it on (karma_events), the live games
they watched here (karma_watch), their pick'em record (pickem_picks) and
their Call it record (callit_calls). Never a bet, a stake or a pick: karma
never pays for bets, and a picture of what someone won would be an ad for
betting. Nothing new is kept and nothing is sent: it is worked out when the
Karma tab asks, and a picture of it leaves the phone only by the member's
own share.

Which month: the one just ended, for the first GRACE days of the next (so
the recap read on the 1st is the whole month); after that, this one so far.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
#: Days of a new month the last one's recap stays up.
GRACE = 7
LEAGUE_WORD = {"nfl": "NFL", "cfb": "college football", "nba": "NBA", "wnba": "WNBA", "nhl": "NHL",
               "mlb": "MLB", "ufc": "UFC", "soccer": "soccer"}


def which(now: float | None = None) -> tuple:
    """('2026-10', whole): the month the card shows at ``now``, and whether
    it is over."""
    d = _dt.datetime.fromtimestamp(time.time() if now is None else float(now), ET).date()
    if d.day <= GRACE:
        last = d.replace(day=1) - _dt.timedelta(days=1)
        return f"{last.year}-{last.month:02d}", True
    return f"{d.year}-{d.month:02d}", False


def bounds(ym: str) -> tuple:
    """(first day, last day, start, end): the month's Eastern days as ISO
    dates, and its span as timestamps, the end exclusive."""
    y, m = (int(x) for x in ym.split("-"))
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    last = nxt - _dt.timedelta(days=1)
    start = _dt.datetime(first.year, first.month, 1, tzinfo=ET).timestamp()
    end = _dt.datetime(nxt.year, nxt.month, 1, tzinfo=ET).timestamp()
    return first.isoformat(), last.isoformat(), start, end


def _one(conn, sql: str, args: tuple):
    try:
        return conn.execute(sql, args).fetchone()
    except sqlite3.OperationalError:                       # a table no page has made yet
        return None


def summary(conn, user_id, ym: str | None = None, now: float | None = None) -> dict:
    """The month's numbers for one account; zeros where there is nothing."""
    whole = True
    if ym is None:
        ym, whole = which(now)
    first, last, start, end = bounds(ym)
    uid = int(user_id)
    k = _one(conn, "SELECT COALESCE(SUM(pts), 0), COUNT(DISTINCT CASE WHEN pts > 0 THEN day END) "
                   "FROM karma_events WHERE user_id = ? AND day BETWEEN ? AND ?", (uid, first, last))
    w = _one(conn, "SELECT COUNT(*) FROM karma_watch WHERE user_id = ? AND first_at >= ? AND first_at < ?",
             (uid, start, end))
    top = _one(conn, "SELECT league, COUNT(*) AS n FROM karma_watch WHERE user_id = ? AND first_at >= ? "
                     "AND first_at < ? GROUP BY league ORDER BY n DESC, league LIMIT 1", (uid, start, end))
    pk = _one(conn, "SELECT SUM(result = 'won'), SUM(result = 'lost'), SUM(result = 'push') FROM pickem_picks "
                    "WHERE user_id = ? AND game_date BETWEEN ? AND ? AND result IN ('won', 'lost', 'push')",
              (uid, first, last))
    ci = _one(conn, "SELECT COUNT(*), COALESCE(SUM(won), 0) FROM callit_calls WHERE user_id = ? "
                    "AND at >= ? AND at < ? AND won IS NOT NULL", (uid, start, end))
    name = _dt.date.fromisoformat(first).strftime("%B")
    out = {"month": ym, "name": name, "whole": whole, "from": first, "to": last,
           "karma": int(k[0] or 0) if k else 0, "days": int(k[1] or 0) if k else 0,
           "watched": int(w[0] or 0) if w else 0,
           "league": LEAGUE_WORD.get(str(top[0]), str(top[0]).upper()) if top else "",
           "league_games": int(top[1]) if top else 0,
           "pickem": None, "calls": None}
    if pk and any(pk):
        out["pickem"] = {"w": int(pk[0] or 0), "l": int(pk[1] or 0), "p": int(pk[2] or 0)}
    if ci and ci[0]:
        out["calls"] = {"n": int(ci[0]), "right": int(ci[1] or 0)}
    out["any"] = bool(out["karma"] or out["watched"] or out["pickem"] or out["calls"])
    return out
