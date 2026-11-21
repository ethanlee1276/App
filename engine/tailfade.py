"""Tail or fade: put yourself on the record against the model.

Roadmap #5 (Ethan): "Every recommendation gets two buttons: tail /
fade. Track each user's record against the model's. 'You're 12-9 fading
Qellys this month; the model is 61-52.' People who think they're
smarter than the model will grind the site to prove it — and the ones
who aren't learn to tail, which is your product's whole pitch."

THE RULES, in one place because the page states them and the fold
enforces them:

  * A signed-in account may tail or fade any RECOMMENDED pick before
    its game starts. One stance per pick; changing or clearing it is
    free until the game goes live. No money moves — this is a public
    argument with the model, scored honestly.
  * SETTLEMENT FOLLOWS THE JOURNAL. The pick's own graded row (the same
    one the Results page shows) decides: a tail wins when the pick wins,
    a fade wins when it loses, a push settles the call void. The join is
    (sport, date, player, market, side) — the line rides along for
    display, but a moved line is still the same pick, and settling a
    fade against a line its bettor never saw would invent a different
    bet than the one they made.
  * THE SAME SOURCE SCORES BOTH SIDES. Your record and the model's are
    both read from the journal, so the strip can never tell a story the
    Results page contradicts.
  * "This month" is the month the CALL was made (the user's own clock of
    engagement), not the slate label — NFL slates are week labels with
    no month to group by.

The server half only: no build-side artifact exists, because calls are
per-account state and the model's record is already published. Tables
ride in accounts.db beside the streak game's, deleted with the account
and included in its export (engine/accounts.py names them).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import time

#: Stances. Anything else is a 400.
STANCES = ("tail", "fade")

#: How many recent calls /me returns for the page's list.
RECENT_CALLS = 12


def call_id(sport: str, date: str, player: str, market: str,
            side: str) -> str:
    raw = f"{sport}|{date}|{player}|{market}|{side}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def ensure_tables(conn) -> None:
    """Additive, safe on every call — same posture as the streak game."""
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS tf_calls (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        call_id    TEXT NOT NULL,
        sport      TEXT NOT NULL,
        date       TEXT NOT NULL,
        player     TEXT NOT NULL,
        market     TEXT NOT NULL,
        side       TEXT NOT NULL,
        line       REAL,
        stance     TEXT NOT NULL CHECK (stance IN ('tail','fade')),
        status     TEXT NOT NULL DEFAULT 'open',
        result     TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, call_id)
      );
      CREATE INDEX IF NOT EXISTS tf_calls_open
        ON tf_calls(user_id, status);
    """)
    conn.commit()


def _row_started(r: dict) -> bool:
    return bool(r.get("live")) or any(
        "already started" in w for w in (r.get("warnings") or []))


def record_call(conn, user_id: int, board: dict, sport: str,
                player: str, market: str, stance: str) -> tuple[int, dict]:
    """Make, change or clear one call, validated against the SERVED board.

    The browser names a player and a market; the board decides what those
    mean — its side, its line, whether it is recommended, whether the
    game has started. Client-supplied sides would let a caller invent a
    pick the model never made and then beat it.
    """
    r = next((x for x in board.get("recommendations") or []
              if x.get("player") == player and x.get("market") == market
              and x.get("recommended")), None)
    if r is None:
        return 404, {"error": "That isn’t a recommended pick on the "
                              "current board."}
    if _row_started(r):
        return 409, {"error": "That game has started — calls are locked."}
    date = str(board.get("date") or "")
    cid = call_id(sport, date, player, market, str(r.get("side") or ""))
    ensure_tables(conn)
    if stance == "clear":
        conn.execute("DELETE FROM tf_calls WHERE user_id=? AND call_id=? "
                     "AND status='open'", (int(user_id), cid))
        conn.commit()
        return 200, {"cleared": True, "call_id": cid}
    if stance not in STANCES:
        return 400, {"error": "Pick tail or fade."}
    conn.execute(
        "INSERT INTO tf_calls (user_id, call_id, sport, date, player, "
        "market, side, line, stance, created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id, call_id) DO UPDATE SET stance=excluded.stance "
        "WHERE tf_calls.status='open'",
        (int(user_id), cid, sport, date, player, market,
         str(r.get("side") or ""), r.get("line"), stance, time.time()))
    conn.commit()
    return 200, {"call_id": cid, "stance": stance,
                 "side": r.get("side"), "line": r.get("line")}


def settle(conn, user_id: int, ledger_conn) -> int:
    """Fold graded journal rows into this account's open calls.

    Lazy, on read, like the streak's fold — no cron, no cross-process
    writer. A call whose pick is still open stays open; one whose pick
    the journal graded settles the moment its owner looks.
    """
    ensure_tables(conn)
    n = 0
    for c in conn.execute("SELECT * FROM tf_calls WHERE user_id=? AND "
                          "status='open'", (int(user_id),)).fetchall():
        row = ledger_conn.execute(
            "SELECT status FROM bets WHERE sport=? AND date=? AND player=? "
            "AND market=? AND side=? AND category='main' "
            "AND status IN ('won','lost','void') LIMIT 1",
            (c["sport"], c["date"], c["player"], c["market"],
             c["side"])).fetchone()
        if row is None:
            continue
        pick = row["status"]
        if pick == "void":
            result = "void"
        elif c["stance"] == "tail":
            result = "won" if pick == "won" else "lost"
        else:
            result = "won" if pick == "lost" else "lost"
        conn.execute("UPDATE tf_calls SET status='settled', result=? "
                     "WHERE user_id=? AND call_id=?",
                     (result, int(user_id), c["call_id"]))
        n += 1
    if n:
        conn.commit()
    return n


def _agg(conn, user_id: int, since_ts: float | None = None) -> dict:
    win = " AND created_at >= ?" if since_ts is not None else ""
    args = [int(user_id)] + ([since_ts] if since_ts is not None else [])
    out = {"tail": {"w": 0, "l": 0}, "fade": {"w": 0, "l": 0}}
    for r in conn.execute(
            f"SELECT stance, result, COUNT(*) AS n FROM tf_calls "
            f"WHERE user_id=? AND status='settled' AND result IN "
            f"('won','lost'){win} GROUP BY stance, result", args):
        out[r["stance"]]["w" if r["result"] == "won" else "l"] += int(r["n"])
    return out


def model_month(ledger_conn, month_start_iso: str) -> dict:
    """The model's own graded W-L since the month began — the number the
    user's record is read against, from the same journal."""
    row = ledger_conn.execute(
        "SELECT SUM(status='won') AS w, SUM(status='lost') AS l FROM bets "
        "WHERE category='main' AND status IN ('won','lost') AND ts >= ?",
        (month_start_iso,)).fetchone()
    return {"w": int(row["w"] or 0), "l": int(row["l"] or 0)}


def me(conn, user_id: int, ledger_conn) -> dict:
    """Everything the page needs: records, the model's month, recent calls."""
    settle(conn, user_id, ledger_conn)
    now = _dt.datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0,
                              microsecond=0)
    calls = [dict(r) for r in conn.execute(
        "SELECT call_id, sport, date, player, market, side, line, stance, "
        "status, result, created_at FROM tf_calls WHERE user_id=? "
        "ORDER BY created_at DESC LIMIT ?",
        (int(user_id), RECENT_CALLS))]
    open_calls = {r["call_id"]: r["stance"] for r in conn.execute(
        "SELECT call_id, stance FROM tf_calls WHERE user_id=? AND "
        "status='open'", (int(user_id),))}
    return {
        "month": _agg(conn, user_id, month_start.timestamp()),
        "all": _agg(conn, user_id),
        "model_month": model_month(ledger_conn,
                                   month_start.isoformat(timespec="seconds")),
        "open": open_calls,
        "calls": calls,
    }
