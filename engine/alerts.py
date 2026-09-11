"""Alerts that fire on a condition, not a schedule (IDEAS #6).

The Alerts page has always been a DIGEST: everything that changed on
everything, newest first, and the page says so rather than pretending to
be a push service. That is the right default and it is not what somebody
means when they say "tell me when Chase's line moves". They mean: out of
all of that, these are mine.

THREE SHAPES, AND THE BRIEF INSISTED ON THREE — "keep it to three shapes
rather than building a query builder nobody uses." The three are not
chosen for tidiness; they are the three the feed can actually answer
without re-deriving anything:

    player   a name        every event names its player
    team     a club        both sides of it, because "the Bengals game"
                           includes the receiver playing against them
    edge     a number      "anything at or above 6%" — the shape the
                           roadmap asked for as "moves past X"

MATCHING IS STATELESS AND HAPPENS ON READ. A watch is not a subscription
that has to be delivered; it is a filter over the feed the site already
publishes. Nothing is copied into a per-user table, so a watch added at
noon immediately applies to the whole feed window, a watch deleted stops
mattering instantly, and the alert list can never drift from the feed it
came from. `engine/feed.py`'s own rule — an event is a change the board
already believes, never a re-derivation — survives intact, because this
module derives nothing at all.

THE EDGE SHAPE ONLY LOOKS AT EVENTS THAT CARRY A LIVE EDGE, and that is
a real distinction rather than an implementation detail: an `edge_died`
event is the moment an edge STOPPED existing, and firing "6% edge" on it
would be a notification about the opposite of what was asked for.

NOT PUSH, AND THE PAGE SAYS SO. Web Push needs P-256 ECDH and AES-GCM,
which the standard library does not have, and that refusal is written up
in docs/IDEAS.md. What this gives you is the count on the bell and your
own strip at the top of the page — which is the difference between
reading two hundred rows and reading four.

Standard library, no I/O, no clock: the caller hands in the feed and the
watches.
"""

from __future__ import annotations

import re

#: The three shapes. Anything else is refused at the door rather than
#: stored and silently never matched.
KINDS = ("player", "team", "edge")

#: Per account. A list longer than this stops being a filter.
MAX_WATCHES = 20

#: A name or a club abbreviation; anything longer is a paste accident.
MAX_VALUE = 40

#: Percent, and the rails are the honest range of this board's edges.
#: Below the floor the filter matches everything, which is the digest
#: again; above the ceiling it matches nothing, forever, silently.
EDGE_MIN, EDGE_MAX = 0.5, 25.0

#: Events whose `edge` (or `gap`) describes an edge that EXISTS NOW.
_EDGE_FIELDS = {"edge_appeared": "edge", "line_move": "edge",
                "price_move": "edge", "stale_line": "gap"}


def _fold(text) -> str:
    """Compare names the way people type them: case, punctuation and
    spacing all removed. "Ja'Marr Chase", "jamarr chase" and "JaMarr
    Chase" are one watch."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def normalize(kind, value):
    """``(kind, stored value)`` for a watch, or None if it is not one.

    Stored in the reader's own spelling for the player and team shapes —
    the card shows it back to them, and folding it here would print
    "jamarrchase" on their own screen. Matching folds at compare time.
    """
    kind = str(kind or "").strip().lower()
    if kind not in KINDS:
        return None
    raw = str(value or "").strip()
    if kind == "edge":
        try:
            pct = round(float(raw.rstrip("% ")), 2)
        except (TypeError, ValueError):
            return None
        if not EDGE_MIN <= pct <= EDGE_MAX:
            return None
        return ("edge", f"{pct:g}")
    if not raw or len(raw) > MAX_VALUE or not _fold(raw):
        return None
    if kind == "team":
        return ("team", raw.upper())
    return ("player", raw)


def describe(kind: str, value: str) -> str:
    """The watch as a sentence, for the chip and for an email subject."""
    if kind == "edge":
        return f"any edge at or above {value}%"
    if kind == "team":
        return f"anything in a {value} game"
    return f"anything on {value}"


def _players_in(event: dict) -> list:
    """Every name an event is about.

    The `released` event is one row summarising a whole lineup drop and
    names its players in a list of "Name (Market)" strings — a watch on
    one of those players has to catch it, or the single most useful
    alert of the day (his prop finally got a price) is the one that does
    not fire.
    """
    out = [event.get("player") or ""]
    for s in event.get("players") or []:
        out.append(str(s).split(" (")[0])
    return [p for p in out if p]


def matches(event: dict, kind: str, value: str) -> bool:
    """Does this one event satisfy this one watch? Pure."""
    if not event or kind not in KINDS:
        return False
    if kind == "player":
        want = _fold(value)
        return any(_fold(p) == want for p in _players_in(event))
    if kind == "team":
        want = str(value or "").strip().upper()
        if not want:
            return False
        return want in {str(event.get("team") or "").upper(),
                        str(event.get("opponent") or "").upper()}
    field = _EDGE_FIELDS.get(str(event.get("kind") or ""))
    if not field:
        return False
    try:
        have = float(event.get(field))
        want = float(value)
    except (TypeError, ValueError):
        return False
    # Board edges are fractions (0.062); the watch is in percent, which
    # is what the page shows and what a person says out loud.
    return have * 100.0 >= want


def fired(events, watches, since: str = "", limit: int = 60) -> list[dict]:
    """The reader's own events, newest first, each saying which watch caught it.

    ``since`` is the last stamp they were shown; events at or before it
    are old news. Passing nothing means the whole window, which is what
    a first visit should see.
    """
    seen, out = set(), []
    for e in sorted(events or [], key=lambda x: str(x.get("ts") or ""),
                    reverse=True):
        if since and str(e.get("ts") or "") <= since:
            continue
        hits = [w for w in watches or []
                if matches(e, w.get("kind"), w.get("value"))]
        if not hits:
            continue
        eid = e.get("id") or f"{e.get('ts')}|{e.get('player')}|{e.get('kind')}"
        if eid in seen:
            continue
        seen.add(eid)
        out.append({**e, "why": [describe(w["kind"], w["value"]) for w in hits]})
        if len(out) >= limit:
            break
    return out


def newest_ts(events) -> str:
    """The stamp to store as "seen" once a reader has been shown these.

    Taken from the EVENTS rather than from a clock: a server whose time
    is a second ahead of the build's would mark an event seen that
    nobody was ever shown.
    """
    return max((str(e.get("ts") or "") for e in events or []), default="")


# --- where a watch lives ----------------------------------------------------
#
# Beside the accounts, because a watch is a fact about a PERSON rather
# than about a board — same posture as the friends tables. Nothing that
# has FIRED is stored: matching is stateless (see the header), so the
# only per-user state is the list itself and one stamp saying how far
# they have read.

def ensure_tables(conn) -> None:
    """Additive, safe on every call — same posture as the social layer."""
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS alert_watches (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind       TEXT NOT NULL,
        value      TEXT NOT NULL,
        created_at REAL NOT NULL,
        UNIQUE (user_id, kind, value)
      );
      CREATE INDEX IF NOT EXISTS alert_watches_user
        ON alert_watches (user_id);
      CREATE TABLE IF NOT EXISTS alert_seen (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        ts      TEXT NOT NULL
      );
    """)
    conn.commit()


def list_watches(conn, user_id) -> list[dict]:
    ensure_tables(conn)
    return [{"id": r["id"], "kind": r["kind"], "value": r["value"],
             "label": describe(r["kind"], r["value"])}
            for r in conn.execute(
                "SELECT id, kind, value FROM alert_watches WHERE user_id=? "
                "ORDER BY created_at", (int(user_id),))]


def add_watch(conn, user_id, kind, value) -> tuple[int, dict]:
    """(status, body). Refuses at the door rather than storing a watch
    that could never match — a filter that silently never fires is
    indistinguishable from a broken one."""
    import time
    ensure_tables(conn)
    norm = normalize(kind, value)
    if not norm:
        return 400, {"error": "that is not one of the three shapes",
                     "kinds": list(KINDS),
                     "edge_range": [EDGE_MIN, EDGE_MAX]}
    n = conn.execute("SELECT COUNT(*) FROM alert_watches WHERE user_id=?",
                     (int(user_id),)).fetchone()[0]
    if n >= MAX_WATCHES:
        return 400, {"error": f"{MAX_WATCHES} watches is the limit — a list "
                              "longer than that stops being a filter"}
    conn.execute("INSERT OR IGNORE INTO alert_watches (user_id, kind, value, "
                 "created_at) VALUES (?,?,?,?)",
                 (int(user_id), norm[0], norm[1], time.time()))
    conn.commit()
    return 200, {"watches": list_watches(conn, user_id)}


def remove_watch(conn, user_id, watch_id) -> tuple[int, dict]:
    ensure_tables(conn)
    try:
        wid = int(watch_id)
    except (TypeError, ValueError):
        return 400, {"error": "bad watch id"}
    conn.execute("DELETE FROM alert_watches WHERE id=? AND user_id=?",
                 (wid, int(user_id)))
    conn.commit()
    return 200, {"watches": list_watches(conn, user_id)}


def seen_ts(conn, user_id) -> str:
    ensure_tables(conn)
    row = conn.execute("SELECT ts FROM alert_seen WHERE user_id=?",
                       (int(user_id),)).fetchone()
    return str(row["ts"]) if row else ""


def mark_seen(conn, user_id, ts: str) -> None:
    """Only ever moves FORWARD. A stale tab posting an old stamp would
    otherwise un-read everything that arrived while it sat there."""
    ensure_tables(conn)
    if not ts:
        return
    if ts <= seen_ts(conn, user_id):
        return
    conn.execute("INSERT INTO alert_seen (user_id, ts) VALUES (?,?) "
                 "ON CONFLICT(user_id) DO UPDATE SET ts=excluded.ts",
                 (int(user_id), str(ts)))
    conn.commit()
