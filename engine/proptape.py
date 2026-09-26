"""Keep the prop prices around the news, which we have always thrown away.

Ethan, 2026-09-19: *"figure out what data we need to source and what we
can use to make all of our edge bets and all of our most likely bets
better."*

`engine.injurylag` asked, on this box's own data, whether we are ahead of
the market when a player's status changes. The answer for the NFL was
1,554 filings and **not one measurable**, split like this:

    737 never quoted by any book   — linemen and defenders; expected
    817 quoted, but never within 24h of the news   — THIS ONE

Eight hundred of them are men the books price every week. We simply hold
no number from the hours the news lands in. The measurement is not
impossible; the data was never written down.

THIS IS THE SAME BUG `engine/lineledger.py` WAS WRITTEN TO FIX, one table
over. Its header:

    The daily build asks the odds API for h2h, spreads, totals on every
    game, attaches all three to the slate, prices bets off them — and
    then throws two of the three away. […] Nothing here costs an API
    credit. The prices are already in memory when this runs; the only
    thing that was missing was writing them down.

Player props never got the same treatment. Only the PAID historical
harvest writes a prop row, and it snapshots near kickoff — while injury
news breaks midweek.

WHY THIS IS NOT JUST "STORE EVERYTHING". An NFL slate carries on the
order of sixteen games × twenty-five priced men × six markets × eight
books, which is tens of thousands of rows per build and hundreds of
thousands a day on a box with one core and a gigabyte. Two bounds keep
it honest, and each is the measurement's own shape rather than a
guess:

  * ONLY MEN ON AN INJURY REPORT. This tape exists to measure injury
    news, so a man nobody has filed anything about contributes nothing
    to it. `watchlist` reads `injury_events`, which is the same store
    the question is asked of.
  * ONLY WHEN THE NUMBER CHANGED. A line that has not moved since the
    last build is a row we already hold. Storing it again buys nothing
    and costs a row per build forever. This also means a quiet market is
    FREE, and a repricing — the event we are trying to catch — is what
    we pay for.

The second bound is why the "before" price survives: the last row stored
before a move is exactly the baseline `injurylag.classify` looks for.

NOTHING HERE BUYS ANYTHING. The prices are already in memory, parsed and
priced against, when this runs.
"""

from __future__ import annotations

import datetime as _dt

#: How far back a designation still counts as putting a man on the tape.
#:
#: Wide enough to hold a Wednesday filing through a Sunday kickoff — the
#: whole week the market reprices him over — and narrow enough that last
#: month's healed hamstring is not still buying rows.
WATCH_DAYS = 10

#: A ceiling on one build's writes.
#:
#: Not expected to bind: with both bounds above, a build should write
#: tens of rows, not thousands. It is here so that a bad watchlist or a
#: feed that re-prices everything at once costs a bounded write instead
#: of the disk.
MAX_ROWS = 4_000


def _stamp(now: _dt.datetime | None = None) -> str:
    """Minute resolution, UTC — the spelling `lineledger` and `newstape`
    both use. Three tables meant to be read against each other cannot
    each pick their own time format; that join is the one nobody makes."""
    n = now or _dt.datetime.now(_dt.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:00Z")


def _norm(name) -> str:
    """The books' spelling, which is what `odds_history` holds.

    Same function `injurylag` reads with and `parse_event_lines` writes
    with. A fourth spelling of a man is how the join that cost
    2026-09-19 gets recreated.
    """
    try:
        from .sources.oddsapi import normalize_name
        return normalize_name(str(name or ""))
    except Exception:                                         # noqa: BLE001
        return str(name or "").strip().lower()


def watchlist(conn, sport: str, now: _dt.datetime | None = None) -> set:
    """Men with a designation on file in the last `WATCH_DAYS`.

    Normalised to the books' spelling, so the caller can match a slate
    straight against it.

    RAISES rather than returning an empty set when the store cannot be
    read. Swallowing it here was the first thing I wrote, and it
    recreated the DOUBLE SILENCE `lineledger.record_note` was written
    against: an empty watchlist and an unreadable one both printed
    "nobody carries a designation", so a tape broken on the day it
    shipped looked exactly like a quiet Tuesday. `_write` catches this
    and the build says so — still writing nothing, but out loud.
    """
    n = now or _dt.datetime.now(_dt.timezone.utc)
    since = (n - _dt.timedelta(days=WATCH_DAYS)).strftime("%Y-%m-%dT%H:%M:00Z")
    rows = conn.execute(
        "SELECT DISTINCT player FROM injury_events "
        "WHERE sport=? AND COALESCE(first_seen, posted_at) >= ?",
        (sport, since)).fetchall()
    return {_norm(r[0]) for r in rows if r[0]}


def last_seen(conn, sport: str, players: set,
              now: _dt.datetime | None = None) -> dict:
    """``{(player, market, book): (line, over, under)}`` as last stored.

    One query, not one per prop. The whole point of the change bound is
    to write less; buying a read per prop to do it would trade disk for
    a worse problem.
    """
    if not players:
        return {}
    try:
        n = now or _dt.datetime.now(_dt.timezone.utc)
        since = (n - _dt.timedelta(days=WATCH_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:00Z")
        out: dict = {}
        for r in conn.execute(
                "SELECT player, market, book, line, over_odds, under_odds "
                "FROM odds_history WHERE sport=? AND taken_at >= ? "
                "ORDER BY taken_at", (sport, since)).fetchall():
            # Ordered by time, so the LAST row for a key wins — the most
            # recent number, which is the one a change is measured from.
            if r[0] in players:
                out[(r[0], r[1], r[2])] = (r[3], r[4], r[5])
        return out
    except Exception:                                         # noqa: BLE001
        return {}


def _games_by_team(games) -> dict:
    """``{team: (event_id, home, away)}`` for the slate's games."""
    from .lineledger import _f
    out: dict = {}
    for g in games or []:
        home, away = _f(g, "home", "") or "", _f(g, "away", "") or ""
        if not home or not away:
            continue
        date = str(_f(g, "date", "") or "")[:10]
        ev = (f"{date}-{away}@{home}", home, away)
        out[home] = ev
        out[away] = ev
    return out


def rows_for(sport: str, slate, watch: set, last: dict,
             now: _dt.datetime | None = None) -> list[dict]:
    """`odds_history` rows for the watched men whose number has moved."""
    taken = _stamp(now)
    by_team = _games_by_team(getattr(slate, "games", []))
    rows: list[dict] = []
    for prop in getattr(slate, "props", []) or []:
        player = _norm(getattr(prop, "player", ""))
        if not player or player not in watch:
            continue
        market = getattr(prop, "market", "") or ""
        game = by_team.get(getattr(prop, "team", "") or "")
        if not market or not game:
            continue
        event_id, home, away = game
        for ln in getattr(prop, "lines", []) or []:
            book = str(getattr(ln, "book", "") or "")
            line = getattr(ln, "line", None)
            if not book or line is None:
                continue
            over = getattr(ln, "over_odds", None)
            under = getattr(ln, "under_odds", None)
            now_at = (float(line), over, under)
            if last.get((player, market, book)) == now_at:
                # UNCHANGED SINCE THE LAST BUILD. We already hold this
                # number; storing it again would cost a row per build
                # forever and tell a reader nothing new.
                continue
            rows.append({
                "sport": sport, "taken_at": taken, "event_id": event_id,
                "home": home, "away": away, "player": player,
                "market": market, "book": book, "line": float(line),
                "over_odds": over, "under_odds": under,
            })
            if len(rows) >= MAX_ROWS:
                return rows
    return rows


def _write(conn, sport: str, slate, now=None) -> tuple:
    """``(stored, watched, error)`` — the whole truth once, so `record`
    and `record_note` can never disagree about what happened."""
    try:
        from . import db
        watch = watchlist(conn, sport, now)
        if not watch:
            return 0, 0, ""
        rows = rows_for(sport, slate, watch,
                        last_seen(conn, sport, watch, now), now)
        if not rows:
            return 0, len(watch), ""
        return db.upsert_odds_history(conn, rows), len(watch), ""
    except Exception as exc:                                  # noqa: BLE001
        return 0, 0, f"{type(exc).__name__}: {exc}"


def record(conn, sport: str, slate, now=None) -> int:
    """Rows written. PREFER `record_note` IN A BUILD — this returns 0
    both when there was nothing to write and when the write threw, and
    those are opposite facts."""
    return _write(conn, sport, slate, now)[0]


def record_note(conn, sport: str, slate, now=None) -> str:
    """`record`, plus the sentence the build prints. Never raises."""
    stored, watched, err = _write(conn, sport, slate, now)
    if err:
        return f"  ⚠️  prop tape skipped: {err}"
    league = sport.upper()
    if not watched:
        return (f"  {league} prop tape: nobody carries a designation in the "
                f"last {WATCH_DAYS} days — nothing to watch.")
    if not stored:
        return (f"  {league} prop tape: {watched} watched, no number moved "
                f"since the last build — a quiet market is free.")
    return (f"  {league} prop tape: {stored} moved price(s) stored free "
            f"for {watched} watched men.")
