"""What the sportsbook line did between our bet and now.

Ethan, 2026-08-20: "Line-movement as a first-class visual. You already
store odds_history and the price tape machinery now exists and is
verified. Applying the same tape to sportsbook lines — open → now, with
our pick's entry marked — turns CLV from a number on a page into
something you can see. The data is already collected."

He is right that it is collected. `lineledger.record()` runs inside both
live builds and writes one row per distinct MINUTE a number was observed,
keyed by (sport, taken_at, event_id, player, market, book) — props,
moneylines, spreads and totals through one table shape. Nothing here
costs an API credit; the prices were already in memory.

This is the read-back, and it is the same shape as
`engine/predmarket.price_series` on purpose: the front end already knows
how to draw that, and a second series format would mean a second chart.

WHY CLV DESERVES A PICTURE. The Record page prints "avg CLV +0.34 pts"
and that number is doing more work than any other on the site — it is the
only evidence about the PROCESS that arrives before the results do. As a
number it is inert. As a line that starts where we bet and ends where the
market closed, with our entry marked, it is the argument.

TWO HONESTY RULES, both inherited from the prediction-market tape and
both load-bearing:

  * fewer than two observed minutes gets NO tape. One point is not a
    line, and a chart drawn through a single dot invites "it has been
    flat", which is the one reading the data cannot support.
  * the series is what we SAW. The build runs on a timer and the odds
    budget paces the paid pulls, so gaps are real and are not
    interpolated across. A smooth line through hours nobody sampled is a
    picture of a market that did not exist.

Read-only. Every function here takes a connection and returns plain data.
"""

from __future__ import annotations

import datetime as _dt

#: How far back a tape reaches by default. A bet is placed the same day it
#: is graded, so a day of movement covers the whole life of the position
#: while keeping the payload small enough to embed.
TAPE_HOURS = 24

#: Below this the line is not a line. Same bar the prediction-market tape
#: uses, for the same reason.
MIN_POINTS = 2


def _iso(ts: _dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:00Z")


def line_tape(conn, sport: str, player: str, market: str,
              book: str | None = None, hours: int = TAPE_HOURS,
              now: _dt.datetime | None = None) -> list[dict]:
    """Every minute we recorded this market, oldest first.

    `book` narrows to one sportsbook's quote. Left out, the tape is the
    BEST available number at each minute — which is the number a reader
    could actually have taken, and the one the pick was priced against.
    Mixing books without that rule would draw a line that jumps between
    venues and means nothing.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    since = _iso(now - _dt.timedelta(hours=hours))
    args: list = [sport, player, market, since]
    where = "sport=? AND player=? AND market=? AND taken_at >= ?"
    if book:
        where += " AND book=?"
        args.append(book)
    rows = conn.execute(
        f"SELECT taken_at, book, line, over_odds, under_odds "
        f"FROM odds_history WHERE {where} ORDER BY taken_at ASC", args
    ).fetchall()

    # One point per minute. With no book named, keep the best price a
    # bettor could have taken at that minute rather than an average of
    # venues nobody could bet at once.
    best: dict = {}
    for r in rows:
        at = r["taken_at"]
        cur = best.get(at)
        if cur is None or _better(r["over_odds"], cur["over_odds"]):
            best[at] = {"at": at, "book": r["book"], "line": r["line"],
                        "over_odds": r["over_odds"],
                        "under_odds": r["under_odds"]}
    return [best[k] for k in sorted(best)]


def _better(a, b) -> bool:
    """Is american price `a` better for the bettor than `b`?

    +150 beats +120 beats -110 beats -140. Straight numeric comparison
    gets this right for two positives or two negatives and wrong across
    the boundary, where -101 would beat +101 — which is backwards, and is
    the kind of thing that silently picks the worst quote on the board.
    """
    if a is None:
        return False
    if b is None:
        return True
    return _payout(a) > _payout(b)


def _payout(odds) -> float:
    """Profit per unit staked, so the two sign conventions compare."""
    o = float(odds)
    return o / 100.0 if o > 0 else 100.0 / abs(o)


def attach_tapes(conn, rows, sport: str, hours: int = TAPE_HOURS,
                 now: _dt.datetime | None = None) -> int:
    """Hang the recorded line history on each recommendation.

    Embedded in the payload rather than served from an endpoint, for the
    reason the prediction-market tape records: this whole site is "the
    build writes JSON, the page reads it", and a chart that needs a live
    API is a chart that is blank whenever the API is not.

    Returns how many rows got one, so a build can say so rather than the
    absence being invisible.
    """
    n = 0
    for r in rows:
        player = r.get("player") or r.get("team")
        market = r.get("market")
        if not player or not market:
            continue
        pts = line_tape(conn, sport, player, market, hours=hours, now=now)
        if len(pts) < MIN_POINTS:
            continue
        r["line_tape"] = pts
        # WHERE WE GOT IN, so the chart can mark it. Carried explicitly
        # rather than inferred from the first point: the tape starts when
        # recording started, which is not the same instant as the bet.
        entry = r.get("odds")
        if entry is not None:
            r["tape_entry"] = {"odds": entry, "line": r.get("line")}
        n += 1
    return n


def move_summary(pts: list[dict], entry_odds=None) -> dict:
    """What the line did, as numbers a sentence can be built from.

    `drift` is in american points and signed the way a bettor reads it:
    positive means the price got BETTER than where we came in, which is
    the market moving toward us.
    """
    if len(pts) < MIN_POINTS:
        return {"n": len(pts), "open": None, "last": None, "drift": None}
    first, last = pts[0], pts[-1]
    out = {"n": len(pts), "open": first.get("over_odds"),
           "last": last.get("over_odds"),
           "open_line": first.get("line"), "last_line": last.get("line"),
           "from": first.get("at"), "to": last.get("at"), "drift": None}
    ref = entry_odds if entry_odds is not None else first.get("over_odds")
    if ref is not None and last.get("over_odds") is not None:
        # Payout-space, not raw american points: -110 to +110 is a far
        # bigger move than +110 to +330, and subtracting the labels would
        # say the opposite.
        out["drift"] = round(_payout(last["over_odds"]) - _payout(ref), 4)
    return out
