"""Each member's own time here, a row a day: when they look, what they read,
and whether an alert brought them. OFF until Ethan says yes, and until the
Privacy Policy says it.

Ethan, 2026-10-29: "we can be recording what users do on the app, how long
they spend on it, and we can base notifications off that." The apps that
are good at bringing people back all start here, with first-party usage
(docs/RETENTION.md §6): Braze's per-person send time is each user's "most
engaged hour" from their own session starts and alert opens; Airship's
churn model leans on how recently and how often a person opens the app;
the RFM churn studies find long-run frequency the strongest single sign.

WHAT IS KEPT, per member and Eastern day, while it is on:
  seconds   time with a page of the site in front of them: counted only
            while the tab is visible and somebody touched it in the last
            two minutes (half an hour on a live game, which people watch
            rather than touch), at most DAY_MAX_S a day
  visits    a tab opened, or one come back to after half an hour away
  taps      of those visits, how many one of our alerts opened
  views     seconds by page (the page's own view name: "recommended",
            "pbp" ...), the top MAX_KEYS
  sports    seconds by league ("nba", "nfl" ...)
  hours     seconds by hour of the day, Eastern
No address, no device, no location, no clicks, nothing typed, nothing about
any other app or site — this site's own pages only (§2: reading how people
use other apps is neither possible on an iPhone nor something we would do).

FOR WHAT (engine/engagement): each member's usual hour for the alerts that
are not tied to a game, fewer of the shared alerts to a phone that never
opens them, and a "while you were away" alert built from the member's own
teams when they have been gone longer than their own rhythm. And the
owner's report, as totals. Never sold, shared, or used for an advert.

TWO LOCKS. QB_ACTIVITY=1 (deploy/setenv.sh) AND the Privacy Policy's own
section on it (web/privacy.html, id="your-activity"): the switch does
nothing until the policy says what it does, so the switch and the wording
go live together, the way the paywall and the usage counts did. Then each
member's own switch in Settings → Your activity: on once the site's is,
and turning it off deletes every row kept and stops the next.

Kept KEEP_DAYS days, then deleted; deleted with the account
(engine/accounts.delete_user); in the account's export.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = "QB_ACTIVITY"
#: The Privacy Policy's section on this; without it the switch stays off.
POLICY = ROOT / "web" / "privacy.html"
POLICY_ID = "your-activity"
#: Rows older than this are deleted.
KEEP_DAYS = 120
#: What one beat may carry (the page sends every five minutes and on leaving).
BEAT_MAX_S = 900
#: What one day may hold.
DAY_MAX_S = 20 * 3600
#: Pages and leagues kept per day row; the rest are folded into "other".
MAX_KEYS = 24
VIEW = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SPORT = re.compile(r"^[a-z0-9]{2,8}$")
SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_days (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    seconds INTEGER NOT NULL DEFAULT 0,
    visits  INTEGER NOT NULL DEFAULT 0,
    taps    INTEGER NOT NULL DEFAULT 0,
    views   TEXT NOT NULL DEFAULT '{}',
    sports  TEXT NOT NULL DEFAULT '{}',
    hours   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS activity_prefs (
    user_id INTEGER PRIMARY KEY,
    off     INTEGER NOT NULL DEFAULT 0,
    at      REAL NOT NULL
);
"""
_policy: dict = {"key": None, "ok": False}
_pruned = {"day": ""}


def policy_ready(path: Path | None = None) -> bool:
    """Does the Privacy Policy have its section on this? Read again whenever
    the file (or which file) changes."""
    p = Path(path or POLICY)
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return False
    if _policy["key"] != key:
        _policy.update(key=key, ok=f'id="{POLICY_ID}"' in p.read_text(encoding="utf-8"))
    return bool(_policy["ok"])


def switched() -> bool:
    return os.environ.get(ENV, "").strip() == "1"


def enabled() -> bool:
    """Both locks open: the switch, and the policy that describes it."""
    return switched() and policy_ready()


def why_off() -> str:
    if not switched():
        return f"switched off ({ENV} is not 1)"
    if not policy_ready():
        return (f"{ENV}=1, but the Privacy Policy has no section id=\"{POLICY_ID}\" yet, "
                "so nothing is kept (docs/RETENTION.md §6 has the wording to approve)")
    return ""


def eastern(t: float | None = None) -> _dt.datetime:
    when = _dt.datetime.fromtimestamp(time.time() if t is None else float(t), _dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return when.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                         # noqa: BLE001 — no tz database: EDT
        return (when - _dt.timedelta(hours=4)).replace(tzinfo=None)


def day_of(t: float | None = None) -> str:
    return eastern(t).date().isoformat()


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)


# ---- the member's own switch ------------------------------------------------------
def opted_out(conn, user_id) -> bool:
    ensure_tables(conn)
    row = conn.execute("SELECT off FROM activity_prefs WHERE user_id = ?", (int(user_id),)).fetchone()
    return bool(row and row[0])


def set_off(conn, user_id, off: bool, now: float | None = None) -> None:
    """Turn it off (deleting every row kept) or back on."""
    ensure_tables(conn)
    conn.execute("INSERT INTO activity_prefs (user_id, off, at) VALUES (?, ?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET off = excluded.off, at = excluded.at",
                 (int(user_id), 1 if off else 0, time.time() if now is None else float(now)))
    if off:
        conn.execute("DELETE FROM activity_days WHERE user_id = ?", (int(user_id),))
    conn.commit()


def on_for(conn, user_id) -> bool:
    """Is anything being kept for this member right now?"""
    return bool(user_id) and enabled() and not opted_out(conn, user_id)


# ---- a beat from the page -----------------------------------------------------------
def _secs(raw, pattern) -> dict:
    """{name: seconds} from what the page sent, every name and number checked."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, v in list(raw.items())[:MAX_KEYS]:
        k = str(k).strip().lower()
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if pattern.match(k) and n > 0:
            out[k] = min(n, BEAT_MAX_S)
    return out


def _fold(have: dict, add: dict) -> dict:
    """Add `add` into `have`, keeping the MAX_KEYS largest and folding the rest into "other"."""
    merged = dict(have)
    for k, v in add.items():
        merged[k] = int(merged.get(k, 0)) + int(v)
    if len(merged) <= MAX_KEYS:
        return merged
    keep = sorted((k for k in merged if k != "other"), key=lambda k: -merged[k])[:MAX_KEYS - 1]
    other = sum(v for k, v in merged.items() if k not in keep)
    return {**{k: merged[k] for k in keep}, "other": other}


def _hours(raw: str) -> list:
    try:
        got = [int(x) for x in str(raw or "").split(",")]
    except ValueError:
        got = []
    return got if len(got) == 24 else [0] * 24


def _load(raw: str) -> dict:
    try:
        got = json.loads(raw or "{}")
    except ValueError:
        return {}
    return {str(k): int(v) for k, v in got.items() if isinstance(v, (int, float))} if isinstance(got, dict) else {}


def beat(conn, user_id, got: dict, now: float | None = None) -> bool:
    """Add one beat from the page to today's row. False, and nothing kept,
    while either lock is shut, for a member who turned it off, or for a
    beat that carries nothing."""
    if not isinstance(got, dict) or not on_for(conn, user_id):
        return False
    t = time.time() if now is None else float(now)
    try:
        s = max(0, min(int(got.get("s") or 0), BEAT_MAX_S))
    except (TypeError, ValueError):
        s = 0
    visit = 1 if got.get("n") else 0
    tap = 1 if visit and got.get("a") else 0
    views, sports = _secs(got.get("v"), VIEW), _secs(got.get("sp"), SPORT)
    if not (s or visit):
        return False
    when = eastern(t)
    day, hour = when.date().isoformat(), when.hour
    row = conn.execute("SELECT seconds, views, sports, hours FROM activity_days WHERE user_id = ? AND day = ?",
                       (int(user_id), day)).fetchone()
    seconds, v0, s0, h0 = (row[0], _load(row[1]), _load(row[2]), _hours(row[3])) if row else (0, {}, {}, [0] * 24)
    kept = min(s, max(0, DAY_MAX_S - int(seconds)))
    # The pages and leagues share out the seconds kept, never more: a
    # beat's own split is scaled to it (a day at its cap keeps none).
    share = lambda d: {k: round(v * kept / s) for k, v in d.items() if round(v * kept / s)} if s else {}  # noqa: E731
    h0[hour] += kept
    conn.execute("""INSERT INTO activity_days (user_id, day, seconds, visits, taps, views, sports, hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, day) DO UPDATE SET seconds = excluded.seconds,
                      visits = activity_days.visits + ?, taps = activity_days.taps + ?,
                      views = excluded.views, sports = excluded.sports, hours = excluded.hours""",
                 (int(user_id), day, int(seconds) + kept, visit, tap,
                  json.dumps(_fold(v0, share(views)), sort_keys=True),
                  json.dumps(_fold(s0, share(sports)), sort_keys=True),
                  ",".join(str(x) for x in h0), visit, tap))
    if tap:
        # An alert they opened: their phones are not ignoring us
        # (engine/pushalerts.IGNORED_N).
        try:
            conn.execute("UPDATE push_subs SET unopened = 0 WHERE user_id = ?", (int(user_id),))
        except sqlite3.OperationalError:
            pass                                              # no alerts table yet on this database
    if _pruned["day"] != day:
        _pruned["day"] = day
        prune(conn, t)
    conn.commit()
    return True


def prune(conn, now: float | None = None) -> int:
    """Delete rows older than KEEP_DAYS."""
    ensure_tables(conn)
    cut = (eastern(now).date() - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    cur = conn.execute("DELETE FROM activity_days WHERE day < ?", (cut,))
    conn.commit()
    return cur.rowcount


# ---- reading it back ----------------------------------------------------------------
def rows(conn, user_id=None, days: int = KEEP_DAYS, now: float | None = None) -> list[dict]:
    """The kept rows, oldest first: one member's, or everyone's when user_id is None."""
    ensure_tables(conn)
    since = (eastern(now).date() - _dt.timedelta(days=days - 1)).isoformat()
    sql = "SELECT user_id, day, seconds, visits, taps, views, sports, hours FROM activity_days WHERE day >= ?"
    args: tuple = (since,)
    if user_id is not None:
        sql += " AND user_id = ?"
        args += (int(user_id),)
    return [{"user_id": r[0], "day": r[1], "seconds": int(r[2]), "visits": int(r[3]), "taps": int(r[4]),
             "views": _load(r[5]), "sports": _load(r[6]), "hours": _hours(r[7])}
            for r in conn.execute(sql + " ORDER BY day", args)]


def _top(d: dict, n: int = 3) -> list:
    return [k for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if k != "other" and v > 0][:n]


def summary(conn, user_id, now: float | None = None, days: int = 28) -> dict:
    """What the member's own Settings screen shows them: everything this
    knows about their last `days`, in their words."""
    mine = rows(conn, user_id, days, now)
    active = [r for r in mine if r["seconds"] or r["visits"]]
    secs = sum(r["seconds"] for r in active)
    views: dict = {}
    sports: dict = {}
    hours = [0] * 24
    for r in active:
        views = _fold(views, r["views"])
        sports = _fold(sports, r["sports"])
        hours = [a + b for a, b in zip(hours, r["hours"])]
    best = max(range(24), key=lambda h: hours[h]) if any(hours) else None
    return {"days": days, "days_active": len(active),
            "minutes_a_day": round(secs / 60 / len(active)) if active else 0,
            "visits": sum(r["visits"] for r in active), "from_alerts": sum(r["taps"] for r in active),
            "sports": _top(sports), "pages": _top(views), "hour_et": best, "kept_days": KEEP_DAYS}


def export_user(conn, user_id) -> dict:
    """For the account's export (engine/accounts.export_user)."""
    ensure_tables(conn)
    out: dict = {}
    if opted_out(conn, user_id):
        out["activity"] = "turned off in Settings"
    kept = rows(conn, user_id)
    if kept:
        out["activity_by_day"] = [{k: v for k, v in r.items() if k != "user_id"} for r in kept]
    return out
