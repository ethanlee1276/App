"""First-party product analytics: counts, never people. OFF until Ethan says yes.

Ethan's product audit, 2026-09-23, item 14: "for a company trying to grow,
you need to know: where did the subscriber come from? Which page converted
them? … Where did the trial user stop? … How many open the Record?" He
answered "Ok keep going" to building it next.

THE PROMISE THIS HAS TO KEEP. The Privacy Policy says, in bold, "We run no
analytics, no advertising, no tracking pixels and no third-party scripts."
So this ships SWITCHED OFF, the way the paywall did: `QB_ANALYTICS=1` turns
it on, and until then the page is told it is off (via /api/billing/status)
and sends nothing at all, the endpoint stores nothing, and a subscription
change counts nothing. The policy wording that goes with turning it on is
drafted in docs/AUDIT_2026-09-23.md, item 14, for Ethan to sign off; the
switch and the new wording go live together.

WHAT IS KEPT, when on: one row per (day, event, page, source, who) and a
count. No user id, no IP address, no cookie, no URL or referrer, no device,
no time finer than the day. `source` is a coarse bucket the page works out
from where the visit came from (direct · search · social · referral ·
campaign); `who` is the server's own reading of the request (visitor ·
member · subscriber). Nothing here can say what one person did.

The one per-person write is `users.last_seen`, which the Privacy Policy
already lists: a signed-in visit refreshes it, at most once a day, so the
report can say what share of accounts came back after their first day and
after their first week. Before the switch it only moved at sign-in.

    python3 -m engine.analytics report        # last 7 days
    python3 -m engine.analytics report 30
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("QB_ANALYTICS_DB", "").strip() or (ROOT / "data" / "analytics.db"))
ENV = "QB_ANALYTICS"

#: What the page may send. `view` carries the page's own name; `ask` is a
#: question put to Ask; `checkout_click` is the plan button, with the page
#: the reader came from before the plans.
CLIENT_EVENTS = ("visit", "view", "ask", "checkout_click")
#: What only the server knows: a Stripe status change (see transition()).
SERVER_EVENTS = ("trial_started", "subscribed", "trial_converted", "canceled", "renewed")
EVENTS = CLIENT_EVENTS + SERVER_EVENTS
SOURCES = ("direct", "search", "social", "referral", "campaign")
WHO = ("visitor", "member", "subscriber")
PAGE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
#: A signed-in visit refreshes last_seen at most this often.
SEEN_EVERY_S = 20 * 3600
DAY_S = 86400

_LOCK = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS counts (
    day    TEXT NOT NULL,
    event  TEXT NOT NULL,
    page   TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    who    TEXT NOT NULL DEFAULT '',
    n      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, event, page, source, who)
);
"""


def enabled() -> bool:
    return os.environ.get(ENV, "").strip() == "1"


def today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def _connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH), timeout=5)
    conn.executescript(SCHEMA)
    return conn


def clean(event: str, page: str = "", source: str = "", who: str = "") -> tuple | None:
    """The row's key, every part checked against its list, or None for an unknown event."""
    if event not in EVENTS:
        return None
    page = str(page or "").strip().lower()
    return (event, page if PAGE.match(page) else "", source if source in SOURCES else "",
            who if who in WHO else "")


def record(event: str, page: str = "", source: str = "", who: str = "", day: str | None = None,
           path=None) -> bool:
    """Add one to a count. False, and nothing written, while switched off or for an unknown event."""
    key = clean(event, page, source, who) if enabled() else None
    if key is None:
        return False
    try:
        with _LOCK:
            conn = _connect(path)
            try:
                conn.execute("INSERT INTO counts (day, event, page, source, who, n) VALUES (?,?,?,?,?,1) "
                             "ON CONFLICT(day, event, page, source, who) DO UPDATE SET n = n + 1",
                             (day or today(), *key))
                conn.commit()
            finally:
                conn.close()
    except (sqlite3.Error, OSError):
        return False                  # a lost count is never worth a failed page or payment
    return True


def transition(prev_status: str | None, prev_end, status: str | None, period_end) -> str | None:
    """The business event a subscription change is, if it is one."""
    p, s = str(prev_status or "none"), str(status or "none")
    if s == p:
        try:
            later = float(period_end) > float(prev_end) + DAY_S
        except (TypeError, ValueError):
            later = False
        return "renewed" if s == "active" and later else None
    if s == "trialing":
        return "trial_started"
    if s == "active":
        return "trial_converted" if p == "trialing" else None if p == "past_due" else "subscribed"
    if s == "canceled":
        return "canceled"
    return None


def seen(conn, user_id: int, now: float | None = None) -> bool:
    """Refresh a signed-in account's last_seen, at most once a day, while switched on."""
    if not enabled():
        return False
    t = now or time.time()
    cur = conn.execute("UPDATE users SET last_seen=? WHERE id=? AND (last_seen IS NULL OR last_seen < ?)",
                       (t, int(user_id), t - SEEN_EVERY_S))
    conn.commit()
    return cur.rowcount > 0


# ---- the report --------------------------------------------------------------------
def _rows(days: int, path=None) -> list[tuple]:
    if not Path(path or DB_PATH).exists():
        return []
    since = (_dt.datetime.now(_dt.timezone.utc).date() - _dt.timedelta(days=days - 1)).isoformat()
    conn = _connect(path)
    try:
        return conn.execute("SELECT day, event, page, source, who, n FROM counts WHERE day >= ?",
                            (since,)).fetchall()
    finally:
        conn.close()


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "—"


def accounts_summary(accounts_path=None, days: int = 7, now: float | None = None) -> list[str]:
    """Signups, subscriptions and who came back, from the accounts database: nothing new collected."""
    from engine import accounts as A
    p = Path(accounts_path or A.DB_PATH)
    if not p.exists():
        return ["  no accounts database here"]
    t = now or time.time()
    conn = sqlite3.connect(str(p))
    try:
        new = conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (t - days * DAY_S,)).fetchone()[0]
        out = [f"  new accounts, last {days} days: {new}"]
        try:
            subs = conn.execute("SELECT status, COUNT(*) FROM subscriptions GROUP BY status "
                                "ORDER BY COUNT(*) DESC").fetchall()
        except sqlite3.Error:
            subs = []
        if subs:
            out.append("  subscriptions now: " + ", ".join(f"{s} {n}" for s, n in subs))
        for after in (1, 7):
            old, back = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN last_seen >= created_at + ? THEN 1 ELSE 0 END) "
                "FROM users WHERE created_at <= ?", (after * DAY_S, t - (after + 1) * DAY_S)).fetchone()
            out.append(f"  came back after day {after}: {back or 0} of {old} accounts at least "
                       f"{after + 1} days old ({_pct(back or 0, old)})")
    finally:
        conn.close()
    return out


def report(days: int = 7, path=None, accounts_path=None) -> str:
    rows = _rows(days, path)
    head = [f"Qellys analytics, last {days} days (UTC days). Switched "
            f"{'ON' if enabled() else 'OFF: nothing is being counted'} ({ENV})."]
    by_day: dict = {}
    pages: dict = {}
    src: dict = {}
    conv: dict = {}
    for day, event, page, source, _who, n in rows:
        d = by_day.setdefault(day, {})
        key = "paywall" if event == "view" and page == "paywall" else event
        d[key] = d.get(key, 0) + n
        if event == "view":
            pages[page or "?"] = pages.get(page or "?", 0) + n
        if event in ("visit", "checkout_click"):
            s = src.setdefault(source or "unknown", {"visit": 0, "checkout_click": 0})
            s[event] += n
        if event == "checkout_click":
            conv[page or "?"] = conv.get(page or "?", 0) + n
    cols = ("visit", "view", "ask", "paywall", "checkout_click", "trial_started", "subscribed",
            "trial_converted", "canceled", "renewed")
    out = head + ["", "day         " + "  ".join(f"{c[:9]:>9}" for c in cols)]
    for day in sorted(by_day):
        out.append(f"{day}  " + "  ".join(f"{by_day[day].get(c, 0):>9}" for c in cols))
    if not by_day:
        out.append("  (no counts in this window)")
    if pages:
        out += ["", "most viewed pages:"] + [f"  {p:<16}{n:>7}" for p, n in
                                            sorted(pages.items(), key=lambda kv: -kv[1])[:12]]
    if src:
        out += ["", "where visits came from:  visits  checkout clicks"]
        out += [f"  {s:<22}{v['visit']:>7}  {v['checkout_click']:>7}  ({_pct(v['checkout_click'], v['visit'])})"
                for s, v in sorted(src.items(), key=lambda kv: -kv[1]["visit"])]
    if conv:
        out += ["", "the page a checkout click came from:"]
        out += [f"  {p:<16}{n:>7}" for p, n in sorted(conv.items(), key=lambda kv: -kv[1])[:8]]
    out += ["", "accounts (from the accounts database):"] + accounts_summary(accounts_path, days)
    return "\n".join(out)


if __name__ == "__main__":                              # python3 -m engine.analytics report [days]
    import sys
    if sys.argv[1:2] == ["report"]:
        print(report(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
    else:
        print("usage: python3 -m engine.analytics report [days]")
