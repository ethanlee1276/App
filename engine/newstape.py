"""When we learned it — the other half of an injury report.

Ethan, 2026-09-07, on the data a winning model needs: "News timing.
Injuries, inactives, quarterback changes, weather, each timestamped. The
value is not knowing, it is knowing before the soft books move."

That last sentence is the whole design. Knowing a receiver is out is
worth nothing on its own: the closing line knows it too, and this
repository's own information tests say no input on disk beats the close.
What is worth something is the INTERVAL — the minutes between a filing
landing and a soft book repricing — because that interval is the same
shape as the one measured edge here already has. A book a point under
the field's consensus beat the close 64.8% of the time on 30,448
quotes, and a book that has not yet moved on a filing is the same
animal seen earlier.

WHAT WAS MISSING, and it was not the feed. The injuries page has read
ESPN's keyless league endpoint since 2026-08-10, and
`espninjuries.current_rows` keeps the NEWEST filing per player and drops
the rest on the next pull. That is right for a page, which answers "who
is hurt now", and useless for timing: a designation that landed four
minutes ago and one that has stood since Tuesday are the same row.

So this writes an EVENT ROW the first time it sees a designation, and
never touches it again. Two clocks are kept apart on purpose:

    posted_at   the feed's own stamp for the filing (may be absent)
    first_seen  when THIS box saw it

Their difference is the feed's lag. The difference between `first_seen`
and a price moving in `odds_history` — which since 2026-09-07 carries
the sharp book's number beside the shopped best — is the one an edge
could live in. Nothing here measures that yet, and this module claims
nothing about it; a measurement needs a sample, and a sample needs
somebody to have written the timestamps down first. This is that.

Standard library only. Never raises into a build: a page that fails
because its telemetry could not write is a page down for the least
important reason available.
"""

from __future__ import annotations

import datetime as _dt

#: Designations worth an event row. A filing that says a player is
#: available is not news a book reprices on, and ESPN emits plenty of
#: them ("Active"); storing those would bury the ones that matter in a
#: table whose whole purpose is to be read chronologically.
WATCHED = {"OUT", "DOUBTFUL", "QUESTIONABLE", "SUSPENSION", "SUSPENDED",
           "INJURED RESERVE", "IR", "DAY-TO-DAY", "GTD",
           "PUP", "NON FOOTBALL INJURY", "NFI"}


def _stamp(now: _dt.datetime | None = None) -> str:
    """Minute resolution, UTC, matching `engine.lineledger`'s stamp — the
    two tables are meant to be read against each other and a join across
    two time formats is a join nobody makes."""
    n = now or _dt.datetime.now(_dt.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:00Z")


def is_watched(status) -> bool:
    """Is this designation one a book would reprice on?"""
    return str(status or "").strip().upper().replace("-", "-") in WATCHED


def rows_for(sport: str, rows: list, now: _dt.datetime | None = None) -> list[dict]:
    """`injury_events` rows for one league's parsed injury board.

    ``rows`` is `espninjuries.parse_injuries` output. A row with no
    player or no watched status contributes nothing — the same "drop
    rather than guess" rule the parser itself runs on.
    """
    seen = _stamp(now)
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        player = (r.get("player") or "").strip()
        status = (r.get("status") or "").strip()
        if not player or not is_watched(status):
            continue
        out.append({
            "sport": sport, "player": player,
            "team": (r.get("team") or "").strip(),
            "status": status,
            # Empty rather than None: it is half a primary key, and NULL
            # does not compare equal to NULL in SQLite, so a feed with no
            # stamp would write a new row on every single pull.
            "posted_at": (r.get("date") or "").strip(),
            "first_seen": seen,
            "injury": (r.get("injury") or "") or "",
            "pos": (r.get("pos") or "") or "",
        })
    return out


def record(conn, sport: str, rows: list, now: _dt.datetime | None = None) -> int:
    """Write the designations we have not seen before. Returns how many."""
    try:
        from . import db
        return db.insert_injury_events(conn, rows_for(sport, rows, now))
    except Exception:                                        # noqa: BLE001
        return 0
