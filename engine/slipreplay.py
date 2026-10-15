"""The bet replay: a saved slip's live chance, kept as the box watches it, played back once it settles.

Ethan, 2026-10-15, from the brainstorm he asked to have built: a live
sweat meter and a bet replay. The box already grades every member's open
saved slips once a minute (engine/slipwatch.sweep, slipgrade.grade brief)
for the last-leg alert and the settle; that grade carries the ticket's
chance for the rest (`now.chance`) and, before anything starts, our chance
it all hits (`ours`). This keeps those numbers, thinned, so My Bets can
draw the whole night back: where it stood before kickoff, every swing
while the games ran, and how it ended.

THINNED, LIKE THE SWEAT TAPE (engine/sweat): a point is kept when
GAP_S has passed since the last one or the chance moved by JUMP, and a
slip keeps at most CAP points; the night's last word (won or lost) is
always kept. Rows older than KEEP_DAYS go, so the table never grows with
the season. Our own number, context: nothing here grades or moves a bet.
"""

from __future__ import annotations

import time

GAP_S = 120
JUMP = 0.02
CAP = 400
KEEP_DAYS = 30


def ensure_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS slip_chance (
        user_id INTEGER NOT NULL,
        bet_id  TEXT NOT NULL,
        at      REAL NOT NULL,
        p       REAL NOT NULL,
        kind    TEXT NOT NULL,
        PRIMARY KEY (user_id, bet_id, at)
    )""")


def point(card: dict) -> tuple | None:
    """``(p, kind)`` the grade says now: ``pre`` before anything starts
    (our chance it all hits), ``live`` while it runs (the chance for the
    rest), ``won``/``lost`` once it is decided; None when it has no
    number."""
    n = (card or {}).get("now") or {}
    status = n.get("status")
    if status == "won":
        return 1.0, "won"
    if status == "lost":
        return 0.0, "lost"
    if status == "open":
        return (float(n["chance"]), "live") if n.get("chance") is not None else None
    ours = (card or {}).get("ours")
    return (float(ours), "pre") if ours is not None and not n else None


def bank(conn, user_id: int, bet_id: str, card: dict, now: float | None = None) -> bool:
    """Keep this grade's number for the slip when it earns a place.
    Returns whether a point was written."""
    got = point(card)
    if got is None:
        return False
    p, kind = round(max(0.0, min(1.0, got[0])), 4), got[1]
    t = time.time() if now is None else float(now)
    bid = str(bet_id)[:40]
    last = conn.execute("SELECT at, p, kind FROM slip_chance WHERE user_id=? AND bet_id=? ORDER BY at DESC LIMIT 1",
                        (int(user_id), bid)).fetchone()
    if last is not None:
        l_at, l_p, l_kind = last
        if l_kind in ("won", "lost"):
            return False                     # decided: nothing after the last word
        if kind == l_kind and t - l_at < GAP_S and abs(p - l_p) < JUMP:
            return False
        if kind == "pre" and l_kind == "pre" and abs(p - l_p) < JUMP:
            return False
    n = conn.execute("SELECT COUNT(*) FROM slip_chance WHERE user_id=? AND bet_id=?", (int(user_id), bid)).fetchone()[0]
    if n >= CAP and kind not in ("won", "lost"):
        return False
    conn.execute("INSERT OR REPLACE INTO slip_chance (user_id, bet_id, at, p, kind) VALUES (?,?,?,?,?)",
                 (int(user_id), bid, t, p, kind))
    return True


def history(conn, user_id: int, bet_id: str) -> list[list]:
    """``[[at, p, kind]]``, oldest first — one member's slip only."""
    ensure_table(conn)
    return [[r[0], r[1], r[2]] for r in conn.execute(
        "SELECT at, p, kind FROM slip_chance WHERE user_id=? AND bet_id=? ORDER BY at",
        (int(user_id), str(bet_id)[:40])).fetchall()]


def prune(conn, now: float | None = None) -> int:
    t = time.time() if now is None else float(now)
    cur = conn.execute("DELETE FROM slip_chance WHERE at < ?", (t - KEEP_DAYS * 86400,))
    return cur.rowcount or 0
