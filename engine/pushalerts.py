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
import sqlite3
import time
from pathlib import Path

from engine import digest, gate, webpush

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
STATE = ROOT / "data" / "push" / "state.json"
LATEST = ROOT / "data" / "push" / "latest.json"
KINDS = ("posted", "settled")
#: A member's own alerts (engine/pushmine): a phone signed in when it
#: subscribed may ask for these too.
PERSONAL = ("watches", "bets", "clutch", "finals", "lineup", "karma", "mentions", "reminders", "pickem", "kickoff",
            # "While you were away" (engine/engagement.away_pass).
            "away")
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
#: FEWER, BETTER (2026-10-29, docs/RETENTION.md: how often alerts come is
#: what turns them off). A phone gets at most one picks-are-up alert in this
#: long; a board that comes due sooner is said with the next one, and when
#: several boards are up the alert names them all in one line
#: (`merge_posted`) instead of one alert a league.
POSTED_GAP_S = 3 * 3600
#: FEWER STILL FOR A PHONE THAT NEVER OPENS THEM (2026-10-29). While a
#: member's own activity is kept (engine/activity), a phone of theirs that
#: has had IGNORED_N of these two kinds in a row without the member opening
#: any of our alerts gets them at most once in IGNORED_GAP_S, until they
#: open one again. The point of both is the tap; a phone that never taps
#: is a phone about to turn alerts off (docs/RETENTION.md §1). Scores and
#: the member's own alerts are a glance and are left alone.
IGNORED_N = 15
IGNORED_GAP_S = 24 * 3600
#: ON THE MEMBER'S OWN TERMS (Ethan's research, 2026-10-29: "a hard cap of
#: 5 pushes a day for free users and 8 for paid ... quiet hours ... local
#: ... a one-tap 'pause alerts for 24h/7d'"). A phone gets at most this many
#: alerts an Eastern day, every kind counted (a lock-screen game or parlay
#: updating is not an alert); the member's own quiet hours are QUIET read
#: in the time zone their Settings name (Eastern when they named none); and
#: Alerts → Pause stops every alert to this phone for a day or a week.
DAY_CAP = {"free": 5, "paid": 8}
PAUSE_HOURS = (24, 168)


# --- the subscriptions (accounts DB) ------------------------------------------
def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS push_subs (
        endpoint TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'web',
        user_id INTEGER, topics TEXT NOT NULL DEFAULT 'posted,settled',
        leagues TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
        last_ok TEXT, fails INTEGER NOT NULL DEFAULT 0)""")
    # When this phone was last sent a picks-are-up alert (POSTED_GAP_S).
    # Added rather than declared: the table shipped first.
    have = {r[1] for r in conn.execute("PRAGMA table_info(push_subs)")}
    # And how many of the shared kinds it has had since its member last
    # opened one of our alerts (IGNORED_N; engine/activity resets it).
    for col, decl in (("posted_at", "REAL"), ("unopened", "INTEGER NOT NULL DEFAULT 0"),
                      # The pause (PAUSE_HOURS) and the day's count (DAY_CAP).
                      ("paused_until", "REAL"), ("day", "TEXT"), ("day_n", "INTEGER NOT NULL DEFAULT 0")):
        if col not in have:
            from engine.db import column_exists_or_raise
            try:
                conn.execute(f"ALTER TABLE push_subs ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError as exc:
                column_exists_or_raise(exc)
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
    # A member's own alerts need the member: a phone subscribed signed out
    # carries the shared two only, and its link to an account is whatever
    # its latest subscribe said (signing out re-subscribes, detaching it).
    t = _clean_list(topics, KINDS + (PERSONAL if user_id else ()))
    # Karma alerts (the Karma tab, engine/karma) and a game chat's mentions
    # and replies (Activity, engine/socialfeed) are the account's choices,
    # not this phone's list: a phone signed in to an account that wants
    # them carries them, whatever the Alerts page sent.
    if user_id:
        for topic, want in _account_topics(conn, user_id):
            keep = [x for x in t.split(",") if x and x != topic]
            t = ",".join(keep + ([topic] if want else []))
    if not t and not user_id and _clean_list(topics, PERSONAL):
        # Signed out with only their own alerts chosen: nothing left for
        # this phone, and it must not keep the last member's.
        unsubscribe(conn, endpoint)
        return 200, {"ok": True, "topics": [], "leagues": [], "detached": True}
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
                      leagues = excluded.leagues, user_id = excluded.user_id, fails = 0""",
                 (endpoint, kind, user_id, t, lg, now))
    conn.commit()
    return 200, {"ok": True, "topics": t.split(","), "leagues": [x for x in lg.split(",") if x]}


def _account_topics(conn, user_id) -> list:
    from engine import gamechat as _gc
    from engine import karma as _karma
    from engine import pickem as _pk
    from engine import socialfeed as _sf
    return [(_karma.ALERT_TOPIC, _karma.reminds(conn, user_id)),
            (_sf.MENTION_TOPIC, _sf.mention_alerts(conn, user_id)),
            (_gc.REMIND_TOPIC, _gc.reminds(conn, user_id)),
            (_pk.ALERT_TOPIC, _pk.reminds(conn, user_id))]


def phones(conn, user_id) -> int:
    """How many phones signed in to this account take alerts at all."""
    try:
        return int(conn.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=?",
                                (int(user_id),)).fetchone()[0] or 0)
    except sqlite3.OperationalError:
        return 0


def relink(conn, user_id, topic: str, on: bool) -> None:
    """Put one of the account's own topics on (or take it off) every phone
    signed in to it, the way a subscribe from the Alerts page would."""
    try:
        rows = conn.execute("SELECT endpoint, topics FROM push_subs WHERE user_id=?", (int(user_id),)).fetchall()
    except sqlite3.OperationalError:
        return
    for endpoint, topics in rows:
        have = [x for x in str(topics or "").split(",") if x and x != topic]
        conn.execute("UPDATE push_subs SET topics=? WHERE endpoint=?",
                     (",".join(have + ([topic] if on else [])), endpoint))


def pause(conn, endpoint: str, hours, now: float | None = None) -> tuple[int, dict]:
    """Stop every alert to this phone for `hours` (one of PAUSE_HOURS), or
    start them again (0)."""
    ensure_tables(conn)
    try:
        h = int(hours)
    except (TypeError, ValueError):
        h = -1
    if h not in PAUSE_HOURS + (0,):
        return 400, {"error": "pause for a day or a week"}
    if not conn.execute("SELECT 1 FROM push_subs WHERE endpoint = ?", (str(endpoint or ""),)).fetchone():
        return 404, {"error": "alerts are not on for this phone"}
    until = (time.time() if now is None else float(now)) + h * 3600 if h else None
    conn.execute("UPDATE push_subs SET paused_until = ? WHERE endpoint = ?", (until, str(endpoint)))
    conn.commit()
    return 200, {"ok": True, "paused_until": until}


def eastern_day(t: float) -> str:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromtimestamp(t, ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                         # noqa: BLE001
        return (_dt.datetime.utcfromtimestamp(t) - _dt.timedelta(hours=4)).date().isoformat()


def member_tz(conn, user_id) -> str:
    """The time zone a member chose in Settings (their synced settings),
    or "" when they left it to the device."""
    if not user_id:
        return ""
    try:
        row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'settings'",
                           (int(user_id),)).fetchone()
        tz = (json.loads(row[0]) or {}).get("tz") if row else ""
    except (sqlite3.Error, ValueError, TypeError, AttributeError):
        return ""
    return tz if isinstance(tz, str) and len(tz) < 40 else ""


def quiet_for(conn, user_id, t: float) -> bool:
    """Is it quiet hours where this member is? QUIET in their own zone,
    Eastern when they named none."""
    tz = member_tz(conn, user_id) or "America/New_York"
    try:
        from zoneinfo import ZoneInfo
        h = _dt.datetime.fromtimestamp(t, ZoneInfo(tz)).hour
    except Exception:                                         # noqa: BLE001 — an unknown zone: Eastern
        return quiet_now(_dt.datetime.utcfromtimestamp(t) - _dt.timedelta(hours=4))
    return h >= QUIET[0] or h < QUIET[1]


def paid_ids(conn) -> set:
    """Members on a plan (DAY_CAP["paid"])."""
    try:
        return {u for (u,) in conn.execute("SELECT user_id FROM subscriptions WHERE status IN ('active', 'trialing')")}
    except sqlite3.Error:
        return set()


def room_today(day, day_n, today: str, uid, paid: set) -> int:
    """How many more alerts this phone may get today."""
    cap = DAY_CAP["paid" if uid and uid in paid else "free"]
    return cap - (int(day_n or 0) if day == today else 0)


def spend(conn, endpoint: str, n: int, today: str) -> None:
    """Count `n` alerts delivered to this phone today."""
    conn.execute("UPDATE push_subs SET day_n = CASE WHEN day = ? THEN day_n + ? ELSE ? END, day = ? "
                 "WHERE endpoint = ?", (today, n, n, today, endpoint))


def paused(paused_until, t: float) -> bool:
    try:
        return bool(paused_until) and float(paused_until) > t
    except (TypeError, ValueError):
        return False


def unsubscribe(conn, endpoint: str) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (str(endpoint or ""),))
    conn.commit()
    return 200, {"ok": True}


def subscription(conn, endpoint: str) -> dict | None:
    ensure_tables(conn)
    row = conn.execute("SELECT topics, leagues, user_id FROM push_subs WHERE endpoint = ?",
                       (str(endpoint or ""),)).fetchone()
    if not row:
        return None
    return {"topics": [x for x in row[0].split(",") if x], "leagues": [x for x in row[1].split(",") if x],
            "user_id": row[2]}


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
        out.append({"id": key, "kind": "posted", "league": sport, "label": label, "n": n,
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


def merge_posted(posted: list) -> dict:
    """Several boards' picks-are-up alerts as one line, newest board first:
    "Picks are up: NBA, NHL and NFL" / "NBA 6 · NHL 4 · NFL 8 on the board".
    One alert is itself."""
    posted = list(posted or [])
    if len(posted) <= 1:
        return posted[0] if posted else {}
    labels = [str(m.get("label") or m.get("league") or "").upper() or "?" for m in posted]
    named = ", ".join(labels[:-1]) + f" and {labels[-1]}"
    counts = " · ".join(f"{lb} {m['n']}" if m.get("n") else lb for lb, m in zip(labels, posted))
    return {"id": "posted:" + "+".join(str(m.get("league") or "") for m in posted), "kind": "posted", "league": "",
            "title": f"Picks are up: {named}",
            "body": f"{counts} on the board — see them before the lines move.",
            "url": posted[0].get("url") or "/#recommended"}


def quiet_now(now: _dt.datetime | None = None) -> bool:
    try:
        from zoneinfo import ZoneInfo
        h = (now or _dt.datetime.now(ZoneInfo("America/New_York"))).hour
    except Exception:                                         # noqa: BLE001
        h = ((now or _dt.datetime.utcnow()).hour - 4) % 24
    return h >= QUIET[0] or h < QUIET[1]


def latest_for(sub: dict | None, path: Path | None = None, now: float | None = None,
               mine: list | None = None) -> dict:
    """What a knocked phone shows: its newest wanted message, fresh; the
    newest of all when it is not subscribed here; a plain line otherwise.
    ``mine`` is the member's own queue (engine/pushmine.mine), read with
    the shared one, newest first."""
    msgs = sorted((_load(path or LATEST).get("messages") or []) + list(mine or []),
                  key=lambda m: float(m.get("at") or 0))[::-1]
    now = now or time.time()
    fresh = [m for m in msgs if now - float(m.get("at") or 0) < FRESH_S]
    def mine_(m):
        return not sub or wants(",".join(sub.get("topics") or []), ",".join(sub.get("leagues") or []), m)
    for m in fresh:
        if mine_(m):
            if m.get("kind") == "posted":
                # Every board up today that this phone wants, in one line.
                today = [x for x in fresh if x.get("kind") == "posted" and mine_(x)
                         and now - float(x.get("at") or 0) < POSTED_GAP_S + SCAN_EVERY_S]
                m = merge_posted(today) if len(today) > 1 else m
            return {k: m[k] for k in ("title", "body", "url", "kind") if k in m} | {"tag": m.get("id", "")}
    return {"title": "Qellys Book", "body": "The board has moved — open it for the latest.", "url": "/", "tag": "qb"}


def _record(msg: dict, path: Path | None = None) -> None:
    path = path or LATEST
    got = _load(path)
    msgs = [m for m in got.get("messages") or [] if m.get("id") != msg["id"]]
    msgs.append(dict(msg, at=int(time.time())))
    _save(path, {"messages": msgs[-KEEP_MESSAGES:]})


# --- sending ---------------------------------------------------------------------
def counted(msgs: list) -> None:
    """One alert that reached a phone, by kind, as a daily total
    (engine/analytics: nothing while it is switched off, never a person)."""
    try:
        from engine import analytics
        for kind in {str(m.get("kind") or "") for m in msgs or []}:
            analytics.record("push_sent", page=kind)
    except Exception:                                         # noqa: BLE001 — a count is never worth an alert
        pass


def send(conn, msgs: list, knock=webpush.knock, apns=webpush.apns_send, log=print,
         vapid: dict | None = None, apns_cfg=None, now_s: float | None = None) -> dict:
    """Knock every subscription that wants each message. Returns counts."""
    ensure_tables(conn)
    rows = conn.execute("SELECT endpoint, kind, topics, leagues, fails, posted_at, user_id, unopened, last_ok, "
                        "paused_until, day, day_n FROM push_subs").fetchall()
    stats = {"sent": 0, "gone": 0, "failed": 0, "skipped_apns": 0}
    if not rows or not msgs:
        return stats
    k = vapid or webpush.keys()
    cfg = webpush.apns_config() if apns_cfg is None else apns_cfg
    now_ts = time.time() if now_s is None else float(now_s)
    now = _dt.datetime.fromtimestamp(now_ts, _dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    tracked = _tracked(conn)
    today, paid = eastern_day(now_ts), paid_ids(conn)
    capped = quieted = held = full = 0
    for endpoint, kind, topics, leagues, fails, posted_at, uid, unopened, last_ok, until, day, day_n in rows:
        mine = [m for m in msgs if wants(topics, leagues, m)]
        # Paused from the Alerts page: nothing at all until it runs out.
        if mine and paused(until, now_ts):
            held += 1
            continue
        # At most one picks-are-up alert in POSTED_GAP_S: a board due sooner
        # is said with the next one.
        if posted_at and now_ts - float(posted_at) < POSTED_GAP_S and any(m.get("kind") == "posted" for m in mine):
            mine = [m for m in mine if m.get("kind") != "posted"]
            capped += 1
        # A phone that never opens them: once in IGNORED_GAP_S at most.
        if mine and tracked(uid) and int(unopened or 0) >= IGNORED_N and _age_s(last_ok, now_ts) < IGNORED_GAP_S:
            mine = []
            quieted += 1
        if not mine:
            continue
        posted = [m for m in mine if m.get("kind") == "posted"]
        # The day's cap (DAY_CAP): what is left of it, said in alerts.
        left = room_today(day, day_n, today, uid, paid)
        if left <= 0:
            full += 1
            continue
        if kind == "apns":
            if not cfg:
                stats["skipped_apns"] += 1
                continue
            out = ([m for m in mine if m.get("kind") != "posted"] + ([merge_posted(posted)] if posted else []))[:left]
            codes = [apns(endpoint, m, cfg) for m in out]
        else:
            # One knock is enough: the worker shows the newest message it wants.
            out = mine[-1:]
            codes = [knock(endpoint, k, topic=mine[-1]["id"].replace(":", "-"))]
        if all(c in (200, 201) for c in codes):
            stats["sent"] += 1
            conn.execute("UPDATE push_subs SET last_ok = ?, fails = 0 WHERE endpoint = ?", (now, endpoint))
            spend(conn, endpoint, len(out), today)
            if posted:
                conn.execute("UPDATE push_subs SET posted_at = ? WHERE endpoint = ?", (now_ts, endpoint))
            if tracked(uid):
                conn.execute("UPDATE push_subs SET unopened = unopened + 1 WHERE endpoint = ?", (endpoint,))
            counted(out if kind == "apns" else mine)
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
    if capped:
        stats["capped"] = capped
    if quieted:
        stats["quieted"] = quieted
    if held:
        stats["paused"] = held
    if full:
        stats["day_capped"] = full
    return stats


def _tracked(conn):
    """Is this subscription's member one whose opening an alert is known
    (engine/activity on for them)? Nobody, while it is off."""
    from engine import activity as ACT
    if not ACT.enabled():
        return lambda uid: False
    ACT.ensure_tables(conn)
    off = {u for (u,) in conn.execute("SELECT user_id FROM activity_prefs WHERE off = 1")}
    return lambda uid: bool(uid) and uid not in off


def _age_s(iso, now_ts: float) -> float:
    """Seconds since a last_ok stamp (UTC, as send writes it); forever when there is none."""
    try:
        then = _dt.datetime.fromisoformat(str(iso)).replace(tzinfo=_dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return float("inf")
    return now_ts - then


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
