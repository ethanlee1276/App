"""What a stranger sees of the paid side before making an account.

    python3 -m engine.firstlook         # the JSON, as the box would serve it

Ethan, 2026-10-25: "we need to go deeper on the free paid wall for when u
sign into the site or first get onto the site. look at other apps ... we
can show our paid features on the sign up site". The sign-up screen and
the plans show the members' side the way a store app's paywall does — the
picks waiting tonight, how last night went, and one real graded pick as
the sample (the Financial Times' "view a sample" before you register) —
and every number comes from here.

PUBLIC BY DESIGN, and nothing in it is new to the public: the record, last
night and tonight's per-league counts are the iPhone widget's own feed
(engine/widgetfeed, GET /api/widget — a count, as the "picks are up" alert
says it, never a pick), and the sample is the newest row of the Record's
settled list (/api/record/bets serves the same row to anyone). Whatever
that row did — won or lost — is what shows: a first screen that picked
its own best result would be the one claim on the page nobody could check.

AND HOW MANY ARE HERE (`proof`, 2026-10-26, the ideas list's "true social
proof"): accounts made in the last seven days, from the accounts table,
and pages in a game's chat room right now, from the room's own "here"
count (engine/gamechat). Counts only, never a name. Real or not shown: a
number under its floor is left out rather than dressed up, and nothing is
ever rounded up, padded or invented.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: What the screen keeps of the newest graded pick.
LAST_FIELDS = ("date", "sport", "player", "market", "side", "line", "odds", "book",
               "status", "pnl_units", "hit_prob")


#: The floors under which a count is not shown: "3 accounts made this
#: week" tells a stranger nothing they should act on.
WEEK_MIN = 25
ROOMS_MIN = 10
WEEK_S = 7 * 86400


def proof(now: float | None = None, conn=None) -> dict | None:
    """``{"week": accounts made in seven days, "rooms": pages in game rooms
    now}``, each only when it clears its floor; None when neither does."""
    now = time.time() if now is None else float(now)
    out: dict = {}
    own = conn is None
    try:
        if own:
            # A read never makes the accounts file: no file, no count.
            from engine import accounts as A
            conn = A.connect() if Path(A.DB_PATH).exists() else None
        if conn is not None:
            week = int(conn.execute("SELECT COUNT(*) FROM users WHERE created_at > ?",
                                    (now - WEEK_S,)).fetchone()[0])
            if week >= WEEK_MIN:
                out["week"] = week
    except Exception:                    # noqa: BLE001 — the first screen draws without it
        pass
    finally:
        if own and conn is not None:
            conn.close()
    from engine import gamechat as GC
    rooms = GC.here_total(now)
    if rooms >= ROOMS_MIN:
        out["rooms"] = rooms
    return out or None


def last_graded(conn) -> dict | None:
    """The newest settled pick of the headline record, or None."""
    from engine import ledger as L
    try:
        rows = L.settled_page(conn)["rows"]
    except sqlite3.Error:
        return None
    return {k: rows[0].get(k) for k in LAST_FIELDS} if rows else None


def build(web: Path = WEB, today: _dt.date | None = None, conn=None) -> dict:
    from engine import widgetfeed
    out = widgetfeed.build(web, today)
    out.pop("url", None)
    own = conn is None
    if own:
        from engine import ledger as L
        try:
            conn = L.connect()
        except sqlite3.Error:
            conn = None
    try:
        out["last"] = last_graded(conn) if conn is not None else None
    finally:
        if own and conn is not None:
            conn.close()
    out["proof"] = proof()
    return out


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=2)
    print()
