"""Alerts on the phone: tonight's picks are up, and last night is graded.

    python3 -m engine.pushalerts            # what it would say now, sending nothing
    python3 -m engine.pushalerts --send     # and knock every phone that asked

Ethan, 2026-10-24: the native feature for the stores — "push alerts when a
pick posts or settles" (docs/APP_STORES.md). Two kinds, each once:

  posted    a league's board has its picks up for the day: "Tonight's NFL
            picks are up — 6 on the board." Once per league per board date.
  settled   last night is graded: "Last night: 7–3, +3.1u." Once per night,
            off the feed's settle_recap — the same line the site's anchor
            moment and the nightly email read (engine/digest.last_night), so
            the alert cannot disagree with the page it opens.

WHAT TRAVELS. Counts and the public record, never a pick: the record is free
by design, and a pick's name stays behind the wall (gate.PAID_KEYS) — an
alert on a lock screen is the most public copy of the product there is.

HOW IT REACHES A PHONE (engine/webpush): an empty, signed knock; the phone's
service worker then asks POST /api/push/latest what to say and shows it.
The iOS shell's phones get the words directly from Apple (APNs), once the
Apple key is set.

QUIET HOURS. Nothing is sent from 23:00 to 08:59 Eastern; what came due in
the night goes at nine, once.

Called every cycle from engine/maintenance.run_if_due (throttled here to one
look per SCAN_EVERY_S); costs nothing when nobody has subscribed.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path

from engine import digest, gate, webpush

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
STATE = ROOT / "data" / "push" / "state.json"
LATEST = ROOT / "data" / "push" / "latest.json"
KINDS = ("posted", "settled")
#: The boards, as the site names them, plus hockey (digest predates it).
LEAGUES = tuple((s, f, label) for s, f, label in digest.BOARDS) + (("nhl", "nhl.json", "NHL"),)
SCAN_EVERY_S = 300
QUIET = (23, 9)                      # Eastern: from 23:00, until 09:00
KEEP_MESSAGES = 30
#: A message older than this is not "the latest" for a knock that arrives late.
FRESH_S = 12 * 3600
MAX_SUBS = 50_000
#: A subscription the push service has refused this many times running goes.
MAX_FAILS = 5


# --- the subscriptions (accounts DB) ------------------------------------------
def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS push_subs (
        endpoint TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'web',
        user_id INTEGER, topics TEXT NOT NULL DEFAULT 'posted,settled',
        leagues TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
        last_ok TEXT, fails INTEGER NOT NULL DEFAULT 0)""")
    conn.commit()


def _clean_list(raw, allowed) -> str:
    items = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    return ",".join(x for x in allowed if x in {str(i).strip().lower() for i in items})


def subscribe(conn, endpoint: str, kind: str = "web", user_id=None, topics=KINDS, leagues=()) -> tuple[int, dict]:
    """Store (or update) a subscription. ``endpoint`` is the push service's
    URL for a browser, or the device token for the iOS shell."""
    ensure_tables(conn)
    kind = "apns" if kind == "apns" else "web"
    endpoint = str(endpoint or "").strip()
    if kind == "web" and not webpush.endpoint_ok(endpoint):
        return 400, {"error": "that is not a push service address"}
    if kind == "apns" and not (8 <= len(endpoint) <= 200 and all(c in "0123456789abcdefABCDEF" for c in endpoint)):
        return 400, {"error": "that is not a device token"}
    t = _clean_list(topics, KINDS)
    if not t:
        return 400, {"error": "choose at least one alert"}
    lg = _clean_list(leagues, [s for s, _, _ in LEAGUES])
    n = conn.execute("SELECT COUNT(*) FROM push_subs").fetchone()[0]
    have = conn.execute("SELECT 1 FROM push_subs WHERE endpoint = ?", (endpoint,)).fetchone()
    if not have and n >= MAX_SUBS:
        return 503, {"error": "alerts are full right now"}
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("""INSERT INTO push_subs (endpoint, kind, user_id, topics, leagues, created, fails)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(endpoint) DO UPDATE SET kind = excluded.kind, topics = excluded.topics,
                      leagues = excluded.leagues, user_id = COALESCE(excluded.user_id, push_subs.user_id), fails = 0""",
                 (endpoint, kind, user_id, t, lg, now))
    conn.commit()
    return 200, {"ok": True, "topics": t.split(","), "leagues": [x for x in lg.split(",") if x]}


def unsubscribe(conn, endpoint: str) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (str(endpoint or ""),))
    conn.commit()
    return 200, {"ok": True}


def subscription(conn, endpoint: str) -> dict | None:
    ensure_tables(conn)
    row = conn.execute("SELECT topics, leagues FROM push_subs WHERE endpoint = ?", (str(endpoint or ""),)).fetchone()
    if not row:
        return None
    return {"topics": [x for x in row[0].split(",") if x], "leagues": [x for x in row[1].split(",") if x]}


def wants(sub_topics: str, sub_leagues: str, msg: dict) -> bool:
    if msg.get("kind") not in str(sub_topics).split(","):
        return False
    lg = [x for x in str(sub_leagues or "").split(",") if x]
    return not lg or not msg.get("league") or msg["league"] in lg


# --- what to say ----------------------------------------------------------------
def _load(path: Path) -> dict:
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _picks(board: dict) -> int:
    return sum(1 for r in board.get("recommendations") or [] if isinstance(r, dict) and r.get("recommended"))


def due(state: dict, web: Path = WEB, today: _dt.date | None = None) -> list[dict]:
    """The messages owed now and never sent: [{id, kind, league, title, body, url}]."""
    today = today or _dt.date.today()
    sent = set(state.get("sent") or [])
    out = []
    for sport, file, label in LEAGUES:
        board = _load(gate.board_source(Path(web) / "data" / file))
        n = _picks(board)
        date = str(board.get("date") or "")
        # Today's board only: a stale file's picks were announced the day it was new.
        if not n or not date or (len(date) == 10 and date < today.isoformat()):
            continue
        key = f"posted:{sport}:{date}"
        if key in sent:
            continue
        when = "This week’s" if sport == "nfl" else "Saturday’s" if sport == "cfb" else "Tonight’s"
        out.append({"id": key, "kind": "posted", "league": sport,
                    "title": f"{when} {label} picks are up",
                    "body": f"{n} pick{'s' if n != 1 else ''} on the board — see them before the lines move.",
                    "url": f"/?sport={sport}#recommended"})
    night = digest.last_night(web)
    if night and night.get("date") and (night["w"] or night["l"]):
        key = f"settled:{night['date']}"
        if key not in sent:
            u = night["net_u"]
            push = f"–{night['p']}" if night.get("p") else ""
            out.append({"id": key, "kind": "settled", "league": "",
                        "title": f"Last night: {night['w']}–{night['l']}{push}, {'+' if u >= 0 else '−'}{abs(u):.1f}u",
                        "body": "Every pick graded at the price we took it. The record is free to read.",
                        "url": "/#record"})
    return out


def quiet_now(now: _dt.datetime | None = None) -> bool:
    try:
        from zoneinfo import ZoneInfo
        h = (now or _dt.datetime.now(ZoneInfo("America/New_York"))).hour
    except Exception:                                         # noqa: BLE001
        h = ((now or _dt.datetime.utcnow()).hour - 4) % 24
    return h >= QUIET[0] or h < QUIET[1]


def latest_for(sub: dict | None, path: Path | None = None, now: float | None = None) -> dict:
    """What a knocked phone shows: its newest wanted message, fresh; the
    newest of all when it is not subscribed here; a plain line otherwise."""
    msgs = (_load(path or LATEST).get("messages") or [])[::-1]
    now = now or time.time()
    fresh = [m for m in msgs if now - float(m.get("at") or 0) < FRESH_S]
    for m in fresh:
        if not sub or wants(",".join(sub.get("topics") or []), ",".join(sub.get("leagues") or []), m):
            return {k: m[k] for k in ("title", "body", "url", "kind") if k in m} | {"tag": m.get("id", "")}
    return {"title": "Qellys Book", "body": "The board has moved — open it for the latest.", "url": "/", "tag": "qb"}


def _record(msg: dict, path: Path | None = None) -> None:
    path = path or LATEST
    got = _load(path)
    msgs = [m for m in got.get("messages") or [] if m.get("id") != msg["id"]]
    msgs.append(dict(msg, at=int(time.time())))
    _save(path, {"messages": msgs[-KEEP_MESSAGES:]})


# --- sending ---------------------------------------------------------------------
def send(conn, msgs: list, knock=webpush.knock, apns=webpush.apns_send, log=print,
         vapid: dict | None = None, apns_cfg=None) -> dict:
    """Knock every subscription that wants each message. Returns counts."""
    ensure_tables(conn)
    rows = conn.execute("SELECT endpoint, kind, topics, leagues, fails FROM push_subs").fetchall()
    stats = {"sent": 0, "gone": 0, "failed": 0, "skipped_apns": 0}
    if not rows or not msgs:
        return stats
    k = vapid or webpush.keys()
    cfg = webpush.apns_config() if apns_cfg is None else apns_cfg
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    for endpoint, kind, topics, leagues, fails in rows:
        mine = [m for m in msgs if wants(topics, leagues, m)]
        if not mine:
            continue
        if kind == "apns":
            if not cfg:
                stats["skipped_apns"] += 1
                continue
            codes = [apns(endpoint, m, cfg) for m in mine]
        else:
            # One knock is enough: the worker shows the newest message it wants.
            codes = [knock(endpoint, k, topic=mine[-1]["id"].replace(":", "-"))]
        if all(c in (200, 201) for c in codes):
            stats["sent"] += 1
            conn.execute("UPDATE push_subs SET last_ok = ?, fails = 0 WHERE endpoint = ?", (now, endpoint))
        elif any(c in (404, 410) for c in codes) or (kind == "apns" and 400 in codes):
            stats["gone"] += 1
            conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        else:
            stats["failed"] += 1
            if fails + 1 >= MAX_FAILS:
                conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
            else:
                conn.execute("UPDATE push_subs SET fails = fails + 1 WHERE endpoint = ?", (endpoint,))
    conn.commit()
    return stats


def scan_and_send(log=print, connect=None, state_path: Path | None = None, web: Path = WEB,
                  now: float | None = None, force: bool = False, **send_kw) -> dict | None:
    """The cycle's look: what is owed, recorded and sent once. None when it
    was not time to look (throttle, quiet hours)."""
    state_path = Path(state_path or STATE)
    state = _load(state_path)
    now = now or time.time()
    if not force and now - float(state.get("looked") or 0) < SCAN_EVERY_S:
        return None
    state["looked"] = now
    if not force and quiet_now():
        _save(state_path, state)
        return None
    msgs = due(state, web)
    stats = {"messages": len(msgs)}
    if msgs:
        if connect is None:
            from engine import accounts
            connect = accounts.connect
        conn = connect()
        try:
            for m in msgs:
                _record(m, state_path.parent / LATEST.name)
            stats.update(send(conn, msgs, log=log, **send_kw))
        finally:
            conn.close()
        state["sent"] = (list(state.get("sent") or []) + [m["id"] for m in msgs])[-400:]
        log(f"  push: {len(msgs)} alert(s) — " + "; ".join(m["title"] for m in msgs)
            + f" · {stats.get('sent', 0)} phone(s), {stats.get('gone', 0)} gone, {stats.get('failed', 0)} failed")
    _save(state_path, state)
    return stats


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--send", action="store_true", help="record and send what is owed (ignores quiet hours)")
    a = ap.parse_args(argv)
    if a.send:
        print(json.dumps(scan_and_send(force=True), indent=1))
        return 0
    msgs = due(_load(STATE))
    print(f"{len(msgs)} alert(s) owed now:" if msgs else "Nothing owed: every board and night is announced.")
    for m in msgs:
        print(f"  [{m['kind']}] {m['title']} — {m['body']}  ({m['url']})")
    # Read-only: a box where nobody has subscribed has no table yet, and
    # looking must not make one (the catch-up script runs this).
    import sqlite3
    from engine import accounts
    try:
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
        try:
            n = dict(conn.execute("SELECT kind, COUNT(*) FROM push_subs GROUP BY kind").fetchall())
        finally:
            conn.close()
    except sqlite3.Error:
        n = {}
    print(f"Subscribed: {n.get('web', 0)} browser(s), {n.get('apns', 0)} iPhone app(s). "
          f"Apple key: {'set' if webpush.apns_config() else 'not set (docs/APP_STORES.md)'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
