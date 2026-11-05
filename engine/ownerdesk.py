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

THE SECOND PASS (Ethan, 2026-11-05: "figure out what other features we can
add to the owners desk"). What the box already kept and only printed over
ssh, or kept and never showed: how people use the site (engine/analytics'
counts: visits a day, the pages, where visits come from, which page a
checkout click came from, alerts sent and opened), the way from a visit to
paying (the month's flow, and how many of the trials that have ended are
paying), the business day by day (`desk_days`: the day's totals, written
by the push loop's owner pass), each sport's books over 7 and 30 days, the
odds credits each league spent, the backups (deploy/backup.sh's nightly
copies and its offsite leg, the weekly zip), and the security log
(engine/seclog: sign-ins, failures, the rate limit, Stripe's signatures) —
counts, and the business's own numbers, like the rest. `desk_days` holds
the day's totals and nothing about any account.
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
    # Every account by its number (Ethan, 2026-11-05: "a list of all accounts
    # on the website in this section"); who each is shows when it is opened.
    # Its own guard: a list that cannot be read never takes the counts down.
    try:
        from . import owneraccounts as OA
        out["list"] = OA.listed(conn)
    except Exception as exc:                                 # noqa: BLE001
        out["list"], out["list_error"] = [], f"{type(exc).__name__}: {exc}"
    return out


# --- money --------------------------------------------------------------------
#: A subscription started this many days ago has had its trial (three days)
#: and a day's grace; the desk asks how many of a month of those are paying.
TRIAL_DONE_DAYS = 4
COHORT_DAYS = 30


def money(conn, now: float | None = None) -> dict:
    """Who is paying, on which plan, and what that is worth a month."""
    from . import billing as B
    t = time.time() if now is None else float(now)
    if not _has(conn, "subscriptions"):
        return {"paying": 0, "trialing": 0, "cancelling": 0, "past_due": 0, "by_plan": {}, "mrr": 0.0,
                "new_7d": 0, "lapsed_30d": 0, "renewing_7d": 0, "statuses": {},
                "started_30d": {"n": 0, "paying": 0, "trialing": 0},
                "ended_trials": {"n": 0, "paying": 0, "days": COHORT_DAYS}}
    have = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    col = lambda c: c if c in have else "NULL"  # noqa: E731
    rows = conn.execute(f"SELECT status, period_end, {col('plan')} AS plan, {col('cancel_at_end')} AS cae, "
                        f"{col('started_at')} AS started, updated_at FROM subscriptions").fetchall()
    out = {"paying": 0, "trialing": 0, "cancelling": 0, "past_due": 0, "by_plan": {}, "mrr": 0.0,
           "new_7d": 0, "lapsed_30d": 0, "renewing_7d": 0, "statuses": {}}
    # The way to paying: subscriptions started this month and where they
    # stand, and of those started TRIAL_DONE_DAYS or more ago (their trial
    # over, a day's grace past it), how many are paying now.
    out["started_30d"] = {"n": 0, "paying": 0, "trialing": 0}
    out["ended_trials"] = {"n": 0, "paying": 0, "days": COHORT_DAYS}
    for st, end, plan, cae, started, updated in rows:
        status = str(st or "none").lower()
        out["statuses"][status] = out["statuses"].get(status, 0) + 1
        # A trial its member cancelled is walled at once (billing.trial_cancel_walls):
        # not a trial on the desk any more, and not a member.
        live = B.entitled(status, end, t, bool(cae), started)
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
        try:
            began = float(started) if started else None
        except (TypeError, ValueError):
            began = None
        paying_now = bool(live) and status != "trialing"
        if began is not None and began >= t - 30 * DAY_S:
            out["started_30d"]["n"] += 1
            out["started_30d"]["paying"] += paying_now
            out["started_30d"]["trialing"] += bool(live) and status == "trialing"
        if began is not None and t - (COHORT_DAYS + TRIAL_DONE_DAYS) * DAY_S <= began <= t - TRIAL_DONE_DAYS * DAY_S:
            out["ended_trials"]["n"] += 1
            out["ended_trials"]["paying"] += paying_now
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
def _league_playing(league: str, unknown: bool = True) -> bool:
    """Has the league games on its scoreboard (web/data/live_<league>.json)?"""
    try:
        got = json.loads((ROOT / "web" / "data" / f"live_{league}.json").read_text(encoding="utf-8"))
        return bool(got.get("games"))
    except (OSError, ValueError, AttributeError):
        return unknown                                       # unknown: judged by its age alone


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
    playing = _league_playing
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
    out["odds_by"] = _section(odds_by_league, t)
    out["backups"] = _section(backups, t)
    out["security"] = _section(security, t)
    return out


# --- files read again only when they change ---------------------------------------
_LINES: dict = {}


def _parsed_lines(f: Path, parse) -> list:
    """Each line of ``f`` through ``parse`` (None drops it), read again only
    when the file's size or date changes: the desk is redrawn every minute
    and these logs grow all month."""
    try:
        st = f.stat()
    except OSError:
        return []
    key = (st.st_size, st.st_mtime, parse)
    hit = _LINES.get(str(f))
    if hit and hit[0] == key:
        return hit[1]
    rows = []
    try:
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    got = parse(json.loads(line))
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if got is not None:
                    rows.append(got)
    except OSError:
        return []
    _LINES[str(f)] = (key, rows)
    return rows


# --- odds credits by league -----------------------------------------------------------
def odds_by_league(now: float | None = None, path: Path | None = None) -> list:
    """Credits each league spent today and this billing month (engine/oddsplan's
    lanes: a league, the harvest, the slips), the most first."""
    from . import oddsbudget as OB
    from . import oddsplan as OP
    t = time.time() if now is None else float(now)
    rows = _parsed_lines(Path(path or OB.SPEND_LOG), _spend_row)
    today = _dt.date.fromtimestamp(t)                        # the pacer's own day (the box's clock)
    try:
        start = OP.renewal(today, OB.load())[0]
    except Exception:                                        # noqa: BLE001 — the 1st, as the plan assumes
        start = today.replace(day=1)
    month = OP.month_spend(rows, start)
    day = OP.month_spend(rows, today)
    return sorted(({"lane": k, "today": int(day.get(k, 0)), "month": int(v)} for k, v in month.items() if v),
                  key=lambda r: -r["month"])


def _spend_row(r: dict):
    return {"iso": str(r["iso"]), "kind": r.get("kind"), "sport": r.get("sport"), "credits": int(r.get("credits") or 0)}


# --- the backups ---------------------------------------------------------------------
#: The databases deploy/backup.sh copies every night, the two that cannot be
#: rebuilt first.
NIGHTLY_DBS = ("accounts", "ledger", "zeno", "history")
#: A nightly copy of the accounts or the journal older than this needs the owner.
NIGHTLY_LATE_H = 36
#: And a weekly zip (engine/maintenance) older than this.
WEEKLY_LATE_D = 9


def backups(now: float | None = None, nightly: Path | None = None, weekly: Path | None = None) -> dict:
    """How old the newest nightly copy of each database is, whether the last
    run reached the offsite copy (the note deploy/backup.sh leaves beside
    them, `last_run.json`), and the weekly zip of the small files."""
    t = time.time() if now is None else float(now)
    d = Path(nightly or os.environ.get("QB_BACKUP_DIR", "").strip() or ROOT / "backups")
    out = {"dbs": {}, "run": None, "weekly": None, "found": d.is_dir()}
    if out["found"]:
        for name in NIGHTLY_DBS:
            got = []
            for f in d.glob(f"{name}-*.db.gz"):
                try:
                    st = f.stat()
                except OSError:
                    continue
                got.append((st.st_mtime, st.st_size))
            if got:
                m, size = max(got)
                out["dbs"][name] = {"age_h": round((t - m) / 3600, 1), "mb": round(size / 1e6, 1), "kept": len(got)}
        try:
            run = json.loads((d / "last_run.json").read_text(encoding="utf-8"))
            out["run"] = {"age_h": round((t - float(run["at"])) / 3600, 1), "offsite": str(run.get("offsite") or "")}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        from . import maintenance as M
        zips = []
        for f in Path(weekly or M.BACKUP_DIR).glob("backup_*.zip"):
            st = f.stat()
            zips.append((st.st_mtime, st.st_size))
        if zips:
            m, size = max(zips)
            out["weekly"] = {"age_d": round((t - m) / DAY_S, 1), "mb": round(size / 1e6, 1), "kept": len(zips)}
    except Exception:                                        # noqa: BLE001 — the nightly half still reads
        pass
    return out


# --- sign-ins and the security log -----------------------------------------------------
#: (kind, outcome, words), in the order the desk lists them: engine/seclog's lines.
SEC_LINES = (("login", "ok", "Sign-ins"), ("login", "fail", "Failed sign-ins"),
             ("passkey_login", "ok", "Passkey sign-ins"), ("passkey_login", "fail", "Failed passkey sign-ins"),
             ("phone_verify", "ok", "Phone codes accepted"), ("phone_verify", "fail", "Phone codes refused"),
             ("signup", "ok", "Accounts made"), ("signup", "fail", "Sign-ups refused"),
             ("password_reset_request", "asked", "Password resets asked for"),
             ("password_reset", "ok", "Passwords reset"),
             ("rate_limit", "blocked", "Requests slowed by the rate limit"),
             ("owner_token", "refused", "Owner doors refused"), ("founder", "refused", "Founder doors refused"),
             ("webhook", "bad_signature", "Stripe messages failing their signature"),
             ("redeem", "refused", "Codes refused"),
             ("account_delete", "wrong_password", "Deletes with a wrong password"))
#: Failed sign-ins in the last hour that need the owner: somebody trying passwords.
SPRAY_HOUR = 50
#: Stripe messages failing their signature in a day: the webhook's secret may
#: have changed, and payments stop reaching the site until it matches.
WEBHOOK_BAD = 3


def _sec_row(j: dict):
    return (_dt.datetime.fromisoformat(str(j["ts"])).timestamp(), str(j.get("kind") or ""),
            str(j.get("outcome") or ""), j.get("net"), j.get("who"))


def security(now: float | None = None, path: Path | None = None) -> dict:
    """The security log's day and week as counts (engine/seclog), and what
    a password-spraying run would look like: failed sign-ins this hour and
    in the day's worst hour, and the most from one network or on one
    account — counts, never the network or the account."""
    from . import seclog as SL
    t = time.time() if now is None else float(now)
    p = Path(path or SL.path())
    rows = [r for f in (p.with_suffix(p.suffix + ".1"), p) for r in _parsed_lines(f, _sec_row) if r[0] >= t - 7 * DAY_S]
    counts: dict = {}
    for ts, kind, outcome, _net, _who in rows:
        c = counts.setdefault((kind, outcome), [0, 0])
        c[1] += 1
        if ts >= t - DAY_S:
            c[0] += 1
    hours: dict = {}
    nets: dict = {}
    whos: dict = {}
    for ts, kind, outcome, net, who in rows:
        if ts < t - DAY_S or outcome != "fail" or kind not in ("login", "passkey_login"):
            continue
        h = int((t - ts) // 3600)
        hours[h] = hours.get(h, 0) + 1
        if net:
            nets[net] = nets.get(net, 0) + 1
        if who:
            whos[who] = whos.get(who, 0) + 1
    return {"lines": [{"k": words, "day": counts[(k, o)][0], "week": counts[(k, o)][1], "kind": k, "outcome": o}
                      for k, o, words in SEC_LINES if (k, o) in counts],
            "fails_hour": hours.get(0, 0), "fails_worst_hour": max(hours.values(), default=0),
            "fails_one_network": max(nets.values(), default=0), "networks_failing": len(nets),
            "fails_one_account": max(whos.values(), default=0),
            "webhook_bad_day": counts.get(("webhook", "bad_signature"), [0, 0])[0]}


# --- how people use the site ----------------------------------------------------------
#: Visits a day for this many days; the pages, sources and events for a week;
#: the way from a visit to paying for a month.
USAGE_DAYS = 14
USAGE_WEEK = 7
FLOW_DAYS = 30
#: The month's flow, in order: engine/analytics' client and server events.
FLOW = ("visit", "signup", "checkout_click", "trial_started", "subscribed", "trial_converted", "canceled", "renewed")
#: The research's events (docs/RETENTION.md §7) the desk counts, with their words.
DID = (("signup", "Accounts made"), ("bet_logged", "Bets put in My Bets"), ("game_view", "Game pages opened"),
       ("sweat", "Game pages showing the reader's own bets"), ("push_on", "Alerts turned on"),
       ("push_prompt", "Alerts asked for"), ("installed", "Added to a home screen"), ("ask", "Questions to Ask"),
       ("kelly", "Kelly calculator used"), ("billing_portal", "Billing page opened"),
       ("discord", "Discord invite tapped"), ("onboarding", "“Make it yours” answered"),
       ("limit_set", "Limits or breaks set"), ("second_screen", "Second-screen mode"))


def usage(now: float | None = None, path: Path | None = None) -> dict:
    """engine/analytics' counts (Privacy Policy §2.5: a day, an event, a page,
    a broad source, signed in or not — no identifier) as the desk reads them.
    Its days are the server's (UTC), as the counts are kept."""
    from . import analytics as AN
    t = time.time() if now is None else float(now)
    p = Path(path or AN.DB_PATH)
    today = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).date()
    ago = lambda k: (today - _dt.timedelta(days=k)).isoformat()  # noqa: E731
    out = {"on": bool(AN.enabled()), "first": None, "days": [], "pages": [], "sources": [], "checkout_from": [],
           "alerts": {"sent": 0, "opened": 0, "kinds": []}, "did": [], "flow": {}}
    if not p.is_file():
        return out
    conn = sqlite3.connect(str(p), timeout=5)
    try:
        rows = conn.execute("SELECT day, event, page, source, who, n FROM counts WHERE day >= ?",
                            (ago(FLOW_DAYS - 1),)).fetchall()
        out["first"] = conn.execute("SELECT MIN(day) FROM counts").fetchone()[0]
    finally:
        conn.close()
    by_day = {ago(k): {"day": ago(k), "visits": 0, "members": 0, "views": 0} for k in range(USAGE_DAYS - 1, -1, -1)}
    week = ago(USAGE_WEEK - 1)
    pages: dict = {}
    src: dict = {}
    conv: dict = {}
    kinds: dict = {}
    did: dict = {}
    flow: dict = {}
    did_keys = {e for e, _w in DID}
    for day, event, page, source, who, n in rows:
        n = int(n or 0)
        if event in FLOW:
            flow[event] = flow.get(event, 0) + n
        b = by_day.get(day)
        if b is not None and event == "visit":
            b["visits"] += n
            b["members"] += n if who in ("member", "subscriber") else 0
        elif b is not None and event == "view":
            b["views"] += n
        if day < week:
            continue
        if event == "view":
            pages[page or "?"] = pages.get(page or "?", 0) + n
        if event in ("visit", "checkout_click"):
            s = src.setdefault(source or "unknown", [0, 0])
            s[event == "checkout_click"] += n
        if event == "checkout_click":
            conv[page or "?"] = conv.get(page or "?", 0) + n
        if event == "push_sent":
            kinds[page or "?"] = kinds.get(page or "?", 0) + n
        if event in did_keys:
            did[event] = did.get(event, 0) + n
    top = lambda d, k: sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]  # noqa: E731
    out.update({"days": list(by_day.values()), "pages": top(pages, 10),
                "sources": [{"source": k, "visits": v[0], "checkout": v[1]}
                            for k, v in sorted(src.items(), key=lambda kv: (-kv[1][0], kv[0]))],
                "checkout_from": top(conv, 6),
                "alerts": {"sent": sum(kinds.values()), "opened": (src.get("alert") or [0, 0])[0], "kinds": top(kinds, 8)},
                "did": [{"event": e, "k": w, "n": did[e]} for e, w in DID if did.get(e)], "flow": flow})
    return out


# --- each sport --------------------------------------------------------------------------
SPORT_DAYS = 30


def sports(lconn, now: float | None = None) -> list:
    """Each sport's books: picks journaled today and still open, the last 7
    and 30 days won-lost and units (settled bets, each book's own stakes),
    and when its board last journaled one — the most active sport first."""
    t = time.time() if now is None else float(now)
    today, d7, d30 = _day(t), _day(t - 6 * DAY_S), _day(t - (SPORT_DAYS - 1) * DAY_S)
    book_of = {c: name for name, cats in BOOKS for c in cats}
    settled = "status IN ('won','lost','push')"
    q = (f"SELECT sport, category, game_day, COUNT(*), SUM(status='won'), SUM(status='lost'), SUM(status='push'), "
         f"SUM(status='open'), COALESCE(SUM(CASE WHEN {settled} THEN pnl_units END), 0), "
         f"COALESCE(SUM(CASE WHEN {settled} THEN stake_units END), 0) FROM bets WHERE game_day >= ? "
         f"GROUP BY sport, category, game_day")
    acc: dict = {}
    for sport, cat, gd, n, w, lo, pu, op, u, st in lconn.execute(q, (d30,)).fetchall():
        book = book_of.get(cat)
        if not book:
            continue
        for key in (book, "All"):
            c = acc.setdefault(str(sport or "?").lower(), {}).setdefault(key, {
                "book": key, "n30": 0, "today": 0, "open": 0, "w7": 0, "l7": 0, "u7": 0.0,
                "w30": 0, "l30": 0, "p30": 0, "u30": 0.0, "s30": 0.0})
            c["n30"] += n
            if gd == today:
                c["today"] += n
                c["open"] += op or 0
            if gd >= d7:
                c["w7"] += w or 0
                c["l7"] += lo or 0
                c["u7"] += float(u or 0)
            c["w30"] += w or 0
            c["l30"] += lo or 0
            c["p30"] += pu or 0
            c["u30"] += float(u or 0)
            c["s30"] += float(st or 0)
    last = {str(s or "?").lower(): ts for s, ts in lconn.execute(
        "SELECT sport, MAX(ts) FROM bets WHERE game_day >= ? GROUP BY sport", (d30,)).fetchall()}
    out = []
    for sp, books in acc.items():
        rows = []
        for name in [b for b, _c in BOOKS] + ["All"]:
            c = books.get(name)
            if not c:
                continue
            c["roi30"] = round(c["u30"] / c["s30"], 4) if c["s30"] else None
            c["u7"], c["u30"] = round(c["u7"], 2), round(c["u30"], 2)
            del c["s30"]
            rows.append(c)
        out.append({"sport": sp, "playing": _league_playing(sp, unknown=False), "last": last.get(sp), "books": rows})
    out.sort(key=lambda s: (-s["books"][-1]["n30"], s["sport"]))
    return out


# --- the business, day by day ----------------------------------------------------------------
#: How many of the site's days the trend carries.
TREND_DAYS = 90
_DAY_COLS = ("accounts", "new", "seen", "paying", "trialing", "mrr", "past_due", "cancelling")


def _days_table(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS desk_days (day TEXT PRIMARY KEY, at REAL NOT NULL, accounts INTEGER, "
                 "new INTEGER, seen INTEGER, paying INTEGER, trialing INTEGER, mrr REAL, past_due INTEGER, "
                 "cancelling INTEGER)")


def snapshot(conn, now: float | None = None) -> dict:
    """Write the site's day's totals (written again through the day, so the
    day's last write is its close): accounts, new, signed in, and the money
    card's numbers. The business's own numbers; no account in them."""
    t = time.time() if now is None else float(now)
    m = midnight(t)
    one = lambda q, *a: conn.execute(q, a).fetchone()[0] or 0  # noqa: E731
    mon = money(conn, t)
    row = {"day": _day(t), "at": t, "accounts": one("SELECT COUNT(*) FROM users"),
           "new": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", m),
           "seen": one("SELECT COUNT(*) FROM users WHERE last_seen >= ?", m),
           **{k: mon.get(k) or 0 for k in ("paying", "trialing", "mrr", "past_due", "cancelling")}}
    _days_table(conn)
    conn.execute(f"INSERT OR REPLACE INTO desk_days (day, at, {', '.join(_DAY_COLS)}) VALUES (?, ?{', ?' * len(_DAY_COLS)})",
                 (row["day"], row["at"], *[row[k] for k in _DAY_COLS]))
    conn.commit()
    return row


def trend(conn, now: float | None = None, days: int = TREND_DAYS) -> list:
    """The kept days, oldest first; today's is written if the push loop has
    not yet (a fresh box, or the first read of the day)."""
    t = time.time() if now is None else float(now)
    if not _has(conn, "desk_days") or not conn.execute("SELECT 1 FROM desk_days WHERE day=?", (_day(t),)).fetchone():
        snapshot(conn, t)
    cols = ("day",) + _DAY_COLS
    return [dict(zip(cols, r)) for r in conn.execute(
        f"SELECT {', '.join(cols)} FROM desk_days WHERE day >= ? ORDER BY day", (_day(t - (days - 1) * DAY_S),)).fetchall()]


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
                "switches": _section(switches), "notice": _section(_notice),
                "usage": _section(usage, t), "trend": _section(_trend, conn, t),
                "sports": (_section(_sports, lconn, t) if lconn is not None
                           else {"error": "the ledger is not readable"})}
    finally:
        if own and lconn is not None:
            try:
                lconn.close()
            except sqlite3.Error:
                pass


def _trend(conn, t: float) -> dict:
    return {"days": trend(conn, t)}


def _sports(lconn, t: float) -> dict:
    return {"sports": sports(lconn, t)}


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
