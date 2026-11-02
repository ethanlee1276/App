"""The owner's desk — the business at a glance, for the site's own account.

Ethan, 2026-11-02: "deep dive and add more features and tools the Qellys book
owners account should have". Everything here was already known to the box
and printed only over ssh (engine.analytics report, engine.bugscan, the odds
plan, the record export); this gathers what an owner checks first onto one
page the Qellys_Book account can open on a phone (js/owner.js), and nobody
else can (server.py `/api/owner/desk`, the same door as Who's on now).

COUNTS AND THE BUSINESS'S OWN NUMBERS, NEVER A PERSON. Accounts are counts;
money is counts by plan and an estimate of the month's recurring revenue;
picks are the books' own record; health is the box's. Nothing names a member
(Who's on now is the one page that does, under its own policy section).

Each section is read on its own and fails on its own: a missing table, an
unreadable file or a module that raises leaves that section `{"error": ...}`
and the rest of the desk drawn.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAY_S = 86400
#: The site's day, as everything else here counts it.
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                            # noqa: BLE001 — a box without tzdata
    ET = _dt.timezone(_dt.timedelta(hours=-5))
#: The books, by journal category, in the order the Record page reads them.
BOOKS = (("Edge", ("main", "paper")), ("Most Likely", ("likely", "likely_live")),
         ("Long Shots", ("longshot",)), ("Pick of the Day", ("potd",)), ("Parlays", ("two_leg", "parlay")))
#: The boards whose freshness the desk reports (engine.bugscan's own list).
SIGNUP_DAYS = 14


def midnight(now: float | None = None) -> float:
    """The start of the site's day (Eastern), as epoch seconds."""
    t = _dt.datetime.fromtimestamp(time.time() if now is None else now, ET)
    return t.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _day(now: float | None = None) -> str:
    return _dt.datetime.fromtimestamp(time.time() if now is None else now, ET).date().isoformat()


def _has(conn, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _section(fn, *a, **k) -> dict:
    try:
        return fn(*a, **k)
    except Exception as exc:                                 # noqa: BLE001 — one section, not the desk
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


# --- right now ----------------------------------------------------------------
def right_now(now: float | None = None) -> dict:
    """Tabs open this minute (engine/whoson): members, visitors, pages."""
    from . import whoson as W
    tabs = W.live(now)
    members = {v["uid"] for v in tabs if v["uid"]}
    return {"members": len(members), "visitors": sum(1 for v in tabs if not v["uid"]),
            "pages": len({(v["view"], v["detail"]) for v in tabs})}


# --- accounts -----------------------------------------------------------------
def accounts(conn, now: float | None = None) -> dict:
    t = time.time() if now is None else float(now)
    m = midnight(t)
    one = lambda q, *a: conn.execute(q, a).fetchone()[0] or 0  # noqa: E731
    out = {"total": one("SELECT COUNT(*) FROM users"),
           "new_today": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", m),
           "new_7d": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", t - 7 * DAY_S),
           "new_30d": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", t - 30 * DAY_S),
           "seen_today": one("SELECT COUNT(*) FROM users WHERE last_seen >= ?", m),
           "seen_7d": one("SELECT COUNT(*) FROM users WHERE last_seen >= ?", t - 7 * DAY_S),
           "seen_30d": one("SELECT COUNT(*) FROM users WHERE last_seen >= ?", t - 30 * DAY_S)}
    # A day a bar, oldest first: the site's own days.
    days = []
    for k in range(SIGNUP_DAYS - 1, -1, -1):
        a = m - k * DAY_S
        days.append({"day": _day(a + 3600), "n": one("SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?",
                                                      a, a + DAY_S)})
    out["signups"] = days
    # Came back: of the accounts old enough to have, how many were seen after their first day / week.
    for after, key in ((1, "back_day1"), (7, "back_week1")):
        row = conn.execute("SELECT COUNT(*), SUM(CASE WHEN last_seen >= created_at + ? THEN 1 ELSE 0 END) "
                           "FROM users WHERE created_at <= ?", (after * DAY_S, t - (after + 1) * DAY_S)).fetchone()
        out[key] = {"of": row[0] or 0, "back": row[1] or 0}
    return out


# --- money --------------------------------------------------------------------
def money(conn, now: float | None = None) -> dict:
    """Who is paying, on which plan, and what that is worth a month."""
    from . import billing as B
    t = time.time() if now is None else float(now)
    if not _has(conn, "subscriptions"):
        return {"paying": 0, "trialing": 0, "cancelling": 0, "past_due": 0, "by_plan": {}, "mrr": 0.0,
                "new_7d": 0, "lapsed_30d": 0, "renewing_7d": 0, "statuses": {}}
    have = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    col = lambda c: c if c in have else "NULL"  # noqa: E731
    rows = conn.execute(f"SELECT status, period_end, {col('plan')} AS plan, {col('cancel_at_end')} AS cae, "
                        f"{col('started_at')} AS started, updated_at FROM subscriptions").fetchall()
    out = {"paying": 0, "trialing": 0, "cancelling": 0, "past_due": 0, "by_plan": {}, "mrr": 0.0,
           "new_7d": 0, "lapsed_30d": 0, "renewing_7d": 0, "statuses": {}}
    for st, end, plan, cae, started, updated in rows:
        status = str(st or "none").lower()
        out["statuses"][status] = out["statuses"].get(status, 0) + 1
        live = B.entitled(status, end, t, bool(cae))
        if status == "past_due":
            out["past_due"] += 1
        if live:
            if status == "trialing":
                out["trialing"] += 1
            else:
                out["paying"] += 1
                p = B.PLANS.get(str(plan or B.DEFAULT_PLAN)) or B.PLANS[B.DEFAULT_PLAN]
                out["mrr"] += p["cents"] / 100.0 / max(1, int(p.get("months") or 1))
                key = str(plan or B.DEFAULT_PLAN)
                out["by_plan"][key] = out["by_plan"].get(key, 0) + 1
                if end and not cae and t <= float(end) <= t + 7 * DAY_S:
                    out["renewing_7d"] += 1
            if cae:
                out["cancelling"] += 1
            if started and float(started) >= t - 7 * DAY_S:
                out["new_7d"] += 1
        elif status in ("canceled", "cancelled", "unpaid", "incomplete_expired") and updated and float(updated) >= t - 30 * DAY_S:
            out["lapsed_30d"] += 1
    out["mrr"] = round(out["mrr"], 2)
    out["plans"] = {pid: B.PLANS[pid]["name"] for pid in B.PLAN_ORDER}
    return out


# --- the picks ----------------------------------------------------------------
def picks(lconn, now: float | None = None, record_path: Path | None = None) -> dict:
    """Today's board by book (journaled, settled, units) and the record's headline."""
    day = _day(now)
    books = []
    for name, cats in BOOKS:
        marks = ",".join("?" * len(cats))
        r = lconn.execute(f"SELECT COUNT(*), SUM(status='won'), SUM(status='lost'), SUM(status='push'), "
                          f"SUM(status='open'), COALESCE(SUM(pnl_units), 0) FROM bets "
                          f"WHERE game_day=? AND category IN ({marks})", (day, *cats)).fetchone()
        if r[0]:
            books.append({"book": name, "n": r[0], "won": r[1] or 0, "lost": r[2] or 0, "push": r[3] or 0,
                          "open": r[4] or 0, "units": round(r[5] or 0.0, 2)})
    open_all = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0]
    out = {"day": day, "books": books, "open": open_all}
    try:
        rec = json.loads((record_path or ROOT / "web" / "data" / "record.json").read_text(encoding="utf-8"))
        o = rec.get("overall") or {}
        ls = rec.get("longshots") or {}
        out["record"] = {"wins": o.get("wins"), "losses": o.get("losses"), "units": o.get("net_units"),
                         "roi": o.get("roi"), "since": rec.get("record_epoch"), "built": rec.get("generated_at"),
                         "longshots": {"wins": ls.get("wins"), "losses": ls.get("losses"), "units": ls.get("net_units")}}
    except (OSError, ValueError):
        out["record"] = None
    return out


# --- the box ------------------------------------------------------------------
def health(now: float | None = None) -> dict:
    """The box's own state: crashes, builds, stale boards, the updater, the
    settle pass, odds credits, disk. The service journal is not read from a
    web request (journalctl can take seconds); `engine.bugscan` prints it."""
    from . import bugscan as BS
    t = time.time() if now is None else float(now)
    scan = BS.scan(24, now=t, journal=lambda hours: None)
    crashes = scan.get("crashes") or []
    # A board is stale only while its league is playing: one with no game on
    # its scoreboard (MLB in November) is resting, not broken.
    def playing(league: str) -> bool:
        try:
            got = json.loads((ROOT / "web" / "data" / f"live_{league}.json").read_text(encoding="utf-8"))
            return bool(got.get("games"))
        except (OSError, ValueError, AttributeError):
            return True                                      # unknown: judged by its age alone
    old_boards = scan.get("stale") or {}
    out = {"crashes": sum(g.get("n", 0) for g in crashes), "crash_kinds": len(crashes),
           "crash_top": [{"m": str(g.get("m") or "")[:120], "n": g.get("n", 0)} for g in crashes[:3]],
           "builds_warned": sorted((scan.get("builds") or {}).keys()),
           "stale": {k: v for k, v in old_boards.items() if playing(k)},
           "resting": sorted(k for k in old_boards if not playing(k)), "commit": BS.running_commit()}
    upd = scan.get("update") or {}
    out["update"] = {"ok": upd.get("ok"), "at": upd.get("at"), "commit": upd.get("commit"),
                     "note": str(upd.get("note") or "")[:200]} if upd else None
    # The settle pass (engine/maintenance), every five minutes while there is something to grade.
    try:
        from . import maintenance as M
        st = json.loads(Path(M.STATE_PATH).read_text(encoding="utf-8"))
        last = st.get("last_settle_ts")
        out["settled_ago_s"] = int(t - float(last)) if last else None
    except (OSError, ValueError, TypeError):
        out["settled_ago_s"] = None
    # Odds credits this month (engine/oddsbudget's pool).
    try:
        from . import oddsbudget as OB
        s = OB.load()
        out["odds"] = {"remaining": int(s.remaining), "used": int(s.used),
                       "days_left": OB.days_left_in_month(), "per_day": int(OB.daily_allowance(s))}
    except Exception:                                        # noqa: BLE001
        out["odds"] = None
    try:
        du = shutil.disk_usage(str(ROOT))
        out["disk"] = {"free_gb": round(du.free / 1e9, 1), "used_pct": round(100 * du.used / du.total, 1)}
    except OSError:
        out["disk"] = None
    # The boards, how old each is.
    ages = {}
    for league, rel in BS.BOARDS.items():
        try:
            ages[league] = round((t - os.path.getmtime(ROOT / rel)) / 3600, 1)
        except OSError:
            continue
    out["boards"] = ages
    return out


# --- the room -----------------------------------------------------------------
def community(conn, now: float | None = None) -> dict:
    t = time.time() if now is None else float(now)
    m = midnight(t)
    out = {"posts_today": 0, "comments_today": 0, "chat_today": 0, "reports_open": 0}
    if _has(conn, "feed_posts"):
        out["posts_today"] = conn.execute("SELECT COUNT(*) FROM feed_posts WHERE created_at >= ?", (m,)).fetchone()[0]
    if _has(conn, "feed_comments"):
        out["comments_today"] = conn.execute("SELECT COUNT(*) FROM feed_comments WHERE created_at >= ?", (m,)).fetchone()[0]
    if _has(conn, "chat_msgs"):
        out["chat_today"] = conn.execute("SELECT COUNT(*) FROM chat_msgs WHERE created_at >= ?", (m,)).fetchone()[0]
    if _has(conn, "feed_reports"):
        # A reported post or comment that is still there and still up for
        # everybody: what the Reports card below asks the owner to look at.
        q = ("SELECT COUNT(*) FROM (SELECT DISTINCT r.kind, r.item_id FROM feed_reports r "
             "LEFT JOIN feed_posts p ON r.kind='post' AND p.id=r.item_id "
             "LEFT JOIN feed_comments c ON r.kind='comment' AND c.id=r.item_id "
             "WHERE COALESCE(p.id, c.id) IS NOT NULL AND COALESCE(p.hidden, c.hidden, 0)=0)")
        out["reports_open"] += conn.execute(q).fetchone()[0]
    if _has(conn, "chat_reports") and _has(conn, "chat_msgs"):
        # And a reported game-chat message still showing in its room.
        out["reports_open"] += conn.execute(
            "SELECT COUNT(DISTINCT r.msg_id) FROM chat_reports r JOIN chat_msgs m ON m.id=r.msg_id "
            "WHERE m.hidden=0").fetchone()[0]
    if _has(conn, "push_subs"):
        out["push_phones"] = conn.execute("SELECT COUNT(*) FROM push_subs").fetchone()[0]
    return out


# --- reports to review -------------------------------------------------------------
#: How many of each list the desk carries (it is redrawn every minute).
REPORTS_SHOWN = 25
REPORT_TEXT = 240
#: The two kinds of thing the owner can hide, by where they live.
WHERES = ("feed", "chat")


def reports(conn) -> dict:
    """What readers flagged, the feed and the game chat in one queue, for the
    desk's Hide / Keep it up / Restore (server.py `/api/owner/hide`).

    Still up first, the most-reported first; then what is hidden (three
    reports hide a thing on their own until somebody looks — engine/socialfeed
    and engine/gamechat REPORTS_TO_HIDE — and the founder's menu hides some
    by hand). The words and the reasons, never who wrote or who reported:
    the decision is about what was said. Until now the game chat's queue had
    no screen at all; only the feed's showed, on the founder's Account tab."""
    from . import gamechat as GC
    from . import socialfeed as SF
    items = []
    for it in SF.reported(conn):
        items.append({"where": "feed", "kind": it["kind"], "id": it["id"], "reports": it["reports"],
                      "reasons": it["reasons"], "hidden": it["hidden"], "text": it["text"][:REPORT_TEXT]})
    for it in GC.reported(conn):
        league, _, event = str(it.get("room") or "").partition("_")
        items.append({"where": "chat", "kind": "message", "id": it["id"], "reports": it["reports"],
                      "reasons": it["reasons"], "hidden": it["hidden"], "text": str(it["text"])[:REPORT_TEXT],
                      "game": f"{league}/{event}" if league and event else ""})
    up = sorted((x for x in items if not x["hidden"]), key=lambda x: (-x["reports"], -x["id"]))
    down = [x for x in items if x["hidden"]]
    return {"open": up[:REPORTS_SHOWN], "open_n": len(up), "hidden": down[:REPORTS_SHOWN], "hidden_n": len(down)}


def moderate(conn, where, kind, item_id, hidden) -> tuple[int, dict]:
    """Hide a reported thing for everybody, or keep it up / put it back (which
    clears its reports), through the same switches the founder's tools use."""
    from . import gamechat as GC
    from . import socialfeed as SF
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return 400, {"error": "Which one?"}
    if where == "chat":
        return GC.set_hidden(conn, item_id, bool(hidden))
    if where == "feed" and kind in ("post", "comment"):
        return SF.set_hidden(conn, kind, item_id, bool(hidden))
    return 400, {"error": "Unknown kind."}


# --- the switches ---------------------------------------------------------------
def switches() -> list:
    """The site's optional features and the letters the policy promises, on or off."""
    out = []
    try:
        from . import analytics as AN
        out.append({"name": "Page counts (analytics)", "on": bool(AN.enabled())})
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from . import activity as ACT
        out.append({"name": "Members' own time (activity)", "on": bool(ACT.enabled())})
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from . import whoson as W
        out.append({"name": "Who's on now", "on": bool(W.policy_ready())})
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from . import policynotice as PN
        armed = [n for n in PN.ORDER if PN.armed(n)]
        out.append({"name": "Privacy Policy notice emails", "on": bool(armed),
                    "note": ", ".join(f"the {n} change" for n in armed)})
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from . import billing as B
        on = B.configured()
        live = on and B.live_mode(B.keys()[0])
        out.append({"name": "Payments (Stripe)", "on": bool(on), "note": "live" if live else ("test mode" if on else "")})
    except Exception:                                        # noqa: BLE001
        pass
    return out


def desk(conn, lconn=None, now: float | None = None) -> dict:
    """The whole desk; ``lconn`` is the ledger's connection (None: opened here)."""
    from . import ledger as L
    t = time.time() if now is None else float(now)
    own = lconn is None
    if own:
        try:
            lconn = L.connect()
        except Exception:                                    # noqa: BLE001
            lconn = None
    try:
        h = _section(health, t)
        return {"at": t, "day": _day(t), "now": _section(right_now, t), "accounts": _section(accounts, conn, t),
                "money": _section(money, conn, t),
                "picks": _section(picks, lconn, t) if lconn is not None else {"error": "the ledger is not readable"},
                "health": h, "needs": _section(_needs, h, t), "alerts": _section(_alerts, conn),
                "community": _section(community, conn, t), "reports": _section(reports, conn),
                "switches": _section(switches), "notice": _section(_notice)}
    finally:
        if own and lconn is not None:
            try:
                lconn.close()
            except sqlite3.Error:
                pass


def _needs(h: dict, t: float) -> list:
    """What needs the owner now: the same list engine/owneralerts pushes."""
    from . import owneralerts as OA
    return OA.problems(h, now=t)


def _alerts(conn) -> dict:
    """How many phones signed in to the site's account would hear those."""
    from . import owneralerts as OA
    from . import pushalerts as PA
    uid = OA.site_account(conn)
    if not uid or not _has(conn, "push_subs"):
        return {"phones": 0}
    return {"phones": int(PA.phones(conn, uid))}


def _notice() -> dict:
    from . import sitenotice as SN
    return SN.current() or {}
