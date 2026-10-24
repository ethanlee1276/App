"""Alerts that are yours: a watch that fired, and your ticket — on, one leg
left, settled.

    python3 -m engine.pushmine          # what is queued and who asked, sending nothing

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 9 and 10, the two features the betting apps lead with (Action's
Line Watcher, a game-on alert for your own bet). engine/pushalerts sends
everybody the same two lines; this sends one member the lines about them.

WATCHES (topic "watches"). The Alerts page already matches a member's
player, team and edge watches against the feed (engine/alerts). A watch
that catches something new now knocks their phones too: "3 new on your
watches — on Ja'Marr Chase and any edge at or above 6%." The feed is a paid
file, so only a member the site's own gate lets read it is told; the words
are the member's own watches and a count, never the pick — the Alerts page
says what moved. A member's first look starts from now, not from the whole
feed window. Quiet hours (pushalerts.QUIET) hold these; what fired in the
night is one alert at nine.

YOUR BETS (topic "bets"). A saved slip is a My Bets entry the box already
grades every minute (engine/slipwatch), so it says:
  on        the first of its games is live
  last      it is down to the leg that decides it (the moment the hedge is
            worth opening)
  settled   the box score settled it: won, lost or pushed
Each once per slip, from slipwatch's own pass. These are the member's own
ticket, so they go at any hour: a game that ends at one in the morning is
the game they are watching. A bet logged by hand has no games to follow and
is not one of them.

WHAT TRAVELS AND WHERE IT WAITS. A message is queued here (`push_mine`,
beside the accounts) and sent by `flush`; a phone's service worker then asks
POST /api/push/latest what to say, and `pushalerts.latest_for` reads the
member's own queue with the shared one, newest first. The iPhone app's
alerts carry the words themselves (APNs). Only a phone signed in when it
subscribed carries the member's alerts — signing out on it detaches it
(server._push_post), so a shared phone stops showing the last person's
tickets.

Run from launch._slip_watcher's minute, after the slip watch, with the
server's own gate. Standard library only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from engine import alerts as AL
from engine import pushalerts as PA
from engine import webpush

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TOPICS = PA.PERSONAL
#: The watches look at most this often (the feed changes on a build, minutes apart).
WATCH_EVERY_S = 120
#: How long each kind stays worth showing. A "your game is on" an hour late
#: is noise; a settled ticket is still news the next morning.
TTL_S = {"watches": 12 * 3600, "on": 30 * 60, "last": 3 * 3600, "settled": 12 * 3600}
KEEP_PER_USER = 12
KEEP_S = 24 * 3600
_looked = {"watches": 0.0}


def ensure_tables(conn) -> None:
    PA.ensure_tables(conn)
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS push_mine (
        user_id INTEGER NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL,
        at REAL NOT NULL, until REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, id));
      CREATE TABLE IF NOT EXISTS push_watch_seen (
        user_id INTEGER PRIMARY KEY, ts TEXT NOT NULL);
    """)
    conn.commit()


def asked(conn, user_id, topic: str) -> bool:
    """Does any phone signed in as this member want this topic?"""
    ensure_tables(conn)
    for (topics,) in conn.execute("SELECT topics FROM push_subs WHERE user_id = ?", (int(user_id),)):
        if topic in str(topics).split(","):
            return True
    return False


def tell(conn, user_id, msg_id: str, topic: str, title: str, body: str, url: str,
         ttl: str = "", now: float | None = None) -> bool:
    """Queue one message for a member, once ever (its id). False when it was
    queued before or nobody of theirs asked for the topic."""
    if topic not in TOPICS or not asked(conn, user_id, topic):
        return False
    t = time.time() if now is None else now
    cur = conn.execute("INSERT OR IGNORE INTO push_mine (user_id, id, kind, title, body, url, at, until) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (int(user_id), str(msg_id)[:120], topic, str(title)[:120], str(body)[:240],
                        url if str(url).startswith("/") else "/", t, t + TTL_S.get(ttl or topic, 3600)))
    if cur.rowcount:
        conn.execute("DELETE FROM push_mine WHERE user_id = ? AND id NOT IN (SELECT id FROM push_mine "
                     "WHERE user_id = ? ORDER BY at DESC LIMIT ?)", (int(user_id), int(user_id), KEEP_PER_USER))
    conn.commit()
    return bool(cur.rowcount)


def mine(conn, user_id, now: float | None = None) -> list[dict]:
    """A member's messages still worth showing, oldest first, in
    pushalerts' shape (each with its `at`) — what latest_for reads."""
    if not user_id:
        return []
    t = time.time() if now is None else now
    try:
        rows = conn.execute("SELECT id, kind, title, body, url, at FROM push_mine WHERE user_id = ? "
                            "AND until > ? ORDER BY at", (int(user_id), t)).fetchall()
    except sqlite3.Error:
        return []
    return [{"id": r[0], "kind": r[1], "league": "", "title": r[2], "body": r[3], "url": r[4], "at": r[5]}
            for r in rows]


# --- watches -----------------------------------------------------------------
def _feed(web: Path = WEB) -> list:
    """The feed the Alerts page filters (server._alerts_feed): the paid copy
    when the wall is up. Only read for members the gate lets through."""
    from engine import gate
    path = Path(web) / "data" / "feed.json"
    if gate.enabled():
        path = gate.board_source(path)
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("events") or []
    except (OSError, ValueError):
        return []


def watch_line(hits: list) -> tuple[str, str]:
    """``(title, body)`` from the member's own watches: a count and their
    words, never the pick (the Alerts page shows what moved)."""
    why = []
    for h in hits:
        for w in h.get("why") or []:
            if w not in why:
                why.append(w)
    n = len(hits)
    title = f"{n} new on your watches" if n != 1 else "Your watch caught something"
    said = ", ".join(why[:2]) + (f" and {len(why) - 2} more" if len(why) > 2 else "")
    return title, (f"On {said}. " if said else "") + "Open Alerts to see what moved."


def watch_pass(conn, events: list, entitled=None, now: float | None = None) -> int:
    """Queue one alert per member whose watches caught something since
    their last look. Returns how many members were told."""
    from engine import gate
    ensure_tables(conn)
    newest = AL.newest_ts(events)
    told = 0
    users = conn.execute("SELECT DISTINCT s.user_id, u.email FROM push_subs s JOIN users u ON u.id = s.user_id "
                         "WHERE s.user_id IS NOT NULL AND (',' || s.topics || ',') LIKE '%,watches,%'").fetchall()
    for uid, email in users:
        if gate.enabled():
            try:
                ok = bool(entitled and entitled(conn, {"id": uid, "email": email}))
            except Exception:                                    # noqa: BLE001
                ok = False
            if not ok:
                continue
        watches = AL.list_watches(conn, uid)
        row = conn.execute("SELECT ts FROM push_watch_seen WHERE user_id = ?", (uid,)).fetchone()
        since = row[0] if row else ""
        if newest and newest > since:
            conn.execute("INSERT INTO push_watch_seen (user_id, ts) VALUES (?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET ts = excluded.ts", (uid, newest))
            conn.commit()
        if not since or not watches:
            continue                              # the first look starts from now
        hits = AL.fired(events, watches, since=since)
        if hits:
            title, body = watch_line(hits)
            told += tell(conn, uid, f"watches:{newest}", "watches", title, body, "/#alerts", now=now)
    return told


# --- your bets (called from engine/slipwatch's pass) -------------------------
def _money(x) -> str:
    try:
        return f"${float(x or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def bet_on(conn, user_id, bet_id: str, where: str, now: float | None = None) -> bool:
    return tell(conn, user_id, f"bets:on:{bet_id}", "bets", "Your parlay is on",
                (f"{where[:150]} — " if where else "") + "follow it on the Live tab.", "/#live", ttl="on", now=now)


def bet_last(conn, user_id, bet_id: str, leg: str, now: float | None = None) -> bool:
    return tell(conn, user_id, f"bets:last:{bet_id}", "bets", "Down to the last leg",
                f"{leg[:100] or 'One leg'} decides your parlay — the hedge and the cash-out check are on the Live tab.",
                "/#live", ttl="last", now=now)


def bet_settled(conn, user_id, bet: dict, done: dict, now: float | None = None) -> bool:
    """Won (and what it pays back), lost, or pushed — the result slipwatch
    just wrote to the member's My Bets."""
    res = done.get("result")
    stake = bet.get("stake")
    if res == "win":
        try:
            o = float(done.get("paid_odds") or bet.get("odds"))
            dec = 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
            body = f"{_money(float(stake) * dec)} back on {_money(stake)}. My Bets has it graded."
        except (TypeError, ValueError, ZeroDivisionError):
            body = "My Bets has it graded."
        title = "Your parlay won"
    elif res == "loss":
        title, body = "Your parlay lost", "Graded off the box score. My Bets has it."
    elif res == "push":
        title, body = "Your parlay pushed", f"Your {_money(stake)} comes back. My Bets has it."
    else:
        return False
    return tell(conn, user_id, f"bets:settled:{bet.get('id')}", "bets", title, body, "/#mybets",
                ttl="settled", now=now)


# --- sending -----------------------------------------------------------------
def flush(conn, knock=webpush.knock, apns=webpush.apns_send, vapid: dict | None = None, apns_cfg=None,
          now: float | None = None, quiet: bool | None = None) -> dict:
    """Send what is queued: each member's phones that want each message.
    Watches wait out quiet hours; a member's bets do not. Every message is
    tried once (a phone that misses it reads it from latest_for)."""
    ensure_tables(conn)
    t = time.time() if now is None else now
    quiet = PA.quiet_now() if quiet is None else quiet
    conn.execute("UPDATE push_mine SET sent = 1 WHERE sent = 0 AND until <= ?", (t,))
    # Kept a day at most (the privacy policy, 2.7): long enough for a late
    # knock to read it, no longer.
    conn.execute("DELETE FROM push_mine WHERE at < ?", (t - KEEP_S,))
    held = " AND kind != 'watches'" if quiet else ""
    rows = conn.execute("SELECT user_id, id, kind, title, body, url FROM push_mine WHERE sent = 0" + held +
                        " ORDER BY at").fetchall()
    stats = {"messages": len(rows), "sent": 0, "gone": 0, "failed": 0, "skipped_apns": 0}
    if not rows:
        conn.commit()
        return stats
    by_user: dict = {}
    for uid, mid, kind, title, body, url in rows:
        by_user.setdefault(uid, []).append({"id": mid, "kind": kind, "league": "", "title": title,
                                            "body": body, "url": url})
    k = vapid or webpush.keys()
    cfg = webpush.apns_config() if apns_cfg is None else apns_cfg
    for uid, msgs in by_user.items():
        for endpoint, kind, topics, fails in conn.execute(
                "SELECT endpoint, kind, topics, fails FROM push_subs WHERE user_id = ?", (uid,)).fetchall():
            want = [m for m in msgs if PA.wants(topics, "", m)]
            if not want:
                continue
            if kind == "apns":
                if not cfg:
                    stats["skipped_apns"] += 1
                    continue
                codes = [apns(endpoint, m, cfg) for m in want]
            else:
                codes = [knock(endpoint, k, topic=want[-1]["id"].replace(":", "-")[:32])]
            if all(c in (200, 201) for c in codes):
                stats["sent"] += 1
            elif any(c in (404, 410) for c in codes) or (kind == "apns" and 400 in codes):
                stats["gone"] += 1
                conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
            else:
                stats["failed"] += 1
                conn.execute("UPDATE push_subs SET fails = fails + 1 WHERE endpoint = ?", (endpoint,))
                if fails + 1 >= PA.MAX_FAILS:
                    conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        conn.executemany("UPDATE push_mine SET sent = 1 WHERE user_id = ? AND id = ?",
                         [(uid, m["id"]) for m in msgs])
    conn.commit()
    return stats


def run_once(entitled=None, log=print, connect=None, now: float | None = None, web: Path = WEB,
             **flush_kw) -> dict:
    """The minute's pass: the watches (every WATCH_EVERY_S), then send what
    is queued — the slip watch's tickets included. Costs one small query
    when nobody has asked for either."""
    from engine import modelstate
    import os
    t = time.time() if now is None else now
    if connect is None:
        if os.environ.get(modelstate.ENV_VAR):
            return {}
        from engine import accounts
        connect = accounts.connect
    conn = connect()
    try:
        ensure_tables(conn)
        if not conn.execute("SELECT 1 FROM push_subs WHERE user_id IS NOT NULL LIMIT 1").fetchone():
            return {"messages": 0}
        told = 0
        if t - _looked["watches"] >= WATCH_EVERY_S:
            _looked["watches"] = t
            told = watch_pass(conn, _feed(web), entitled=entitled, now=t)
        stats = flush(conn, now=t, **flush_kw)
        if stats["messages"]:
            log(f"  push (yours): {stats['messages']} alert(s), {told} from watches · {stats['sent']} phone(s), "
                f"{stats['gone']} gone, {stats['failed']} failed")
        return dict(stats, watches=told)
    finally:
        conn.close()


def main(argv=None) -> int:
    """Read-only: what is queued and how many phones asked, by topic."""
    from engine import accounts
    try:
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"No accounts database to read ({exc}).")
        return 0
    try:
        try:
            subs = conn.execute("SELECT topics FROM push_subs WHERE user_id IS NOT NULL").fetchall()
        except sqlite3.Error:
            subs = []
        n = {tp: sum(1 for (s,) in subs if tp in str(s).split(",")) for tp in TOPICS}
        try:
            q = conn.execute("SELECT kind, SUM(sent = 0), COUNT(*) FROM push_mine GROUP BY kind").fetchall()
        except sqlite3.Error:
            q = []
    finally:
        conn.close()
    print(f"Signed-in phones asking: {n['watches']} for watches, {n['bets']} for their bets.")
    print("Queued (unsent / kept): " + (", ".join(f"{k} {u}/{c}" for k, u, c in q) if q else "nothing yet."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
