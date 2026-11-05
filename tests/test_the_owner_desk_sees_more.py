"""The owner's desk, second pass: what the box kept and the desk never showed.

Ethan, 2026-11-05: "figure out what other features we can add to the owners
desk". What these hold:

  * how people use the site is engine/analytics' counts as they are kept
    (Privacy Policy §2.5): visits a day, the pages, where visits came from
    and the plan taps from each, the page a plan button was tapped on,
    alerts that reached phones and the visits they opened, the research's
    events, and the month's flow — numbers, no identifier anywhere;
  * each sport's books: today's picks and those still open, the last 7 and
    30 days won-lost and units (settled bets only), its return, the most
    active sport first;
  * the way to paying: subscriptions started this month and how many pay,
    and of the trials that have ended how many turned paying;
  * the business day by day (`desk_days`): one row a site's day, written
    again through the day, by the push loop's owner pass with or without a
    phone to tell — totals, and no column that could hold an account;
  * the backups from the files' own dates and the note deploy/backup.sh
    leaves (`last_run.json`), and a late copy, a missed offsite leg or a
    stopped weekly zip under Needs you;
  * the security log as counts — never the network or the account — with
    a password-spraying hour and Stripe's failing signatures under Needs you;
  * each league's odds credits today and this billing month;
  * the page draws all of it, and the account list's filters show only the
    accounts each names, with their counts.

Run directly: `python3 tests/test_the_owner_desk_sees_more.py`
"""
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import analytics as AN                                # noqa: E402
from engine import billing as B                                   # noqa: E402
from engine import ledger                                         # noqa: E402
from engine import owneralerts as OA                              # noqa: E402
from engine import ownerdesk as OD                                # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"
NOW = OD.midnight(time.time()) + 15 * 3600                      # 3pm on the site's day
UTC_DAY = lambda k=0: (dt.datetime.fromtimestamp(NOW, dt.timezone.utc).date() - dt.timedelta(days=k)).isoformat()  # noqa: E731


def _user(conn, email, made=None, seen=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    conn.execute("UPDATE users SET created_at = ?, last_seen = ? WHERE id = ?",
                 (made if made is not None else NOW, seen, uid))
    conn.commit()
    return uid


# --- how people use the site ---------------------------------------------------------
def test_usage_is_the_counts_as_they_are_kept():
    d = Path(tempfile.mkdtemp())
    db = d / "analytics.db"
    c = sqlite3.connect(str(db))
    c.executescript(AN.SCHEMA)
    c.executemany("INSERT INTO counts VALUES (?,?,?,?,?,?)", [
        (UTC_DAY(), "visit", "", "search", "visitor", 40), (UTC_DAY(), "visit", "", "alert", "member", 12),
        (UTC_DAY(1), "visit", "", "direct", "subscriber", 8), (UTC_DAY(20), "visit", "", "direct", "visitor", 100),
        (UTC_DAY(), "view", "likely", "", "member", 30), (UTC_DAY(2), "view", "record", "", "visitor", 9),
        (UTC_DAY(), "checkout_click", "paywall", "search", "visitor", 4), (UTC_DAY(), "checkout_click", "record", "direct", "visitor", 1),
        (UTC_DAY(), "push_sent", "picks_up", "", "", 50), (UTC_DAY(3), "push_sent", "final", "", "", 10),
        (UTC_DAY(), "signup", "", "search", "visitor", 3), (UTC_DAY(), "bet_logged", "hand", "", "member", 6),
        (UTC_DAY(10), "trial_started", "", "", "", 2), (UTC_DAY(5), "trial_converted", "", "", "", 1),
        (UTC_DAY(40), "trial_started", "", "", "", 9)])                # older than the month: not in the flow
    c.commit()
    c.close()
    try:
        u = OD.usage(NOW, path=db)
        assert len(u["days"]) == OD.USAGE_DAYS and u["days"][-1]["day"] == UTC_DAY(), u["days"][-1]
        assert (u["days"][-1]["visits"], u["days"][-1]["members"], u["days"][-1]["views"]) == (52, 12, 30), u["days"][-1]
        assert u["days"][-2]["members"] == 8, "a subscriber's visit is a member's"
        assert u["pages"] == [["likely", 30], ["record", 9]] or u["pages"] == [("likely", 30), ("record", 9)], u["pages"]
        src = {x["source"]: x for x in u["sources"]}
        assert (src["search"]["visits"], src["search"]["checkout"]) == (40, 4), src
        assert "direct" in src and src["direct"]["visits"] == 8, "a week's sources: day 20 is not in them"
        assert [tuple(x) for x in u["checkout_from"]] == [("paywall", 4), ("record", 1)], u["checkout_from"]
        assert (u["alerts"]["sent"], u["alerts"]["opened"]) == (60, 12), u["alerts"]
        assert [x["event"] for x in u["did"]] == ["signup", "bet_logged"], u["did"]
        assert u["flow"]["visit"] == 160 and u["flow"]["trial_started"] == 2 and u["flow"]["trial_converted"] == 1, u["flow"]
        blob = json.dumps(u)
        for word in ("uid", "user", "email", "net", "ip"):
            assert f'"{word}"' not in blob, f"the usage card carries a {word}"
        none = OD.usage(NOW, path=d / "missing.db")
        assert none["first"] is None and none["days"] == [], "no counts kept: nothing to draw"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- each sport --------------------------------------------------------------------------
def _bet(L, sport, cat, days_ago, status, pnl, stake=1.0):
    gd = OD._day(NOW - days_ago * 86400)
    n = L.execute("SELECT COUNT(*) FROM bets").fetchone()[0]       # one player a pick: the journal's pick key
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, stake_dollars, "
              "status, category, pnl_units) VALUES (?, ?, ?, ?, ?, 'pts', 'OVER', 20.5, -110, ?, 10, ?, ?, ?)",
              (f"{gd}T12:00:00", sport, gd, gd, f"Player {n}", stake, status, cat, pnl))


def test_each_sport_by_book_over_seven_and_thirty_days():
    d = Path(tempfile.mkdtemp())
    L = ledger.connect(d / "l.db")
    try:
        for args in (("nba", "likely", 0, "open", 0), ("nba", "likely", 0, "won", 0.5), ("nba", "likely", 3, "lost", -1.0),
                     ("nba", "main", 2, "won", 0.91), ("nba", "main", 20, "lost", -1.0), ("nba", "main", 20, "push", 0),
                     ("nba", "longshot", 40, "won", 9.0),                      # older than the month
                     ("nfl", "main", 10, "won", 0.91), ("nfl", "unknown_cat", 1, "won", 5.0)):
            _bet(L, *args)
        L.commit()
        got = OD.sports(L, NOW)
        assert [s["sport"] for s in got] == ["nba", "nfl"], "the most active sport first"
        nba = {b["book"]: b for b in got[0]["books"]}
        assert list(nba) == ["Edge", "Most Likely", "All"], "the Record page's order, the totals last"
        ml, edge, tot = nba["Most Likely"], nba["Edge"], nba["All"]
        assert (ml["today"], ml["open"], ml["w7"], ml["l7"], ml["u7"]) == (2, 1, 1, 1, -0.5), ml
        assert (edge["w7"], edge["w30"], edge["l30"], edge["p30"], edge["u30"]) == (1, 1, 1, 1, -0.09), edge
        assert edge["roi30"] == round(-0.09 / 3, 4), "units over the settled stakes"
        assert (tot["n30"], tot["today"], tot["w30"], tot["l30"]) == (6, 2, 2, 2), tot
        nfl = got[1]["books"]
        assert [b["book"] for b in nfl] == ["Edge", "All"] and nfl[0]["w30"] == 1, "a category no book owns is left out"
        assert got[0]["last"], got[0]
        # "Plays today" is a game today (Eastern) on the league's scoreboard, not
        # a week's games on it: the NFL's carries Thursday to Monday.
        root = OD.ROOT
        try:
            OD.ROOT = d
            (d / "web" / "data").mkdir(parents=True)
            start = lambda days: dt.datetime.fromtimestamp(NOW + days * 86400, dt.timezone.utc).isoformat()  # noqa: E731
            (d / "web" / "data" / "live_nba.json").write_text(json.dumps({"games": [{"live": {"start_time": start(0)}}]}))
            (d / "web" / "data" / "live_nfl.json").write_text(json.dumps({"games": [{"live": {"start_time": start(3)}}]}))
            playing = {s["sport"]: s["playing"] for s in OD.sports(L, NOW)}
            assert playing == {"nba": True, "nfl": False}, playing
        finally:
            OD.ROOT = root
    finally:
        L.close()
        shutil.rmtree(d, ignore_errors=True)


# --- the way to paying, and the business day by day ------------------------------------------
def test_the_way_to_paying_and_the_trials_that_ended():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    try:
        B.init(conn)
        rows = [  # status, period_end, started: this month's and the ended trials' cohort
            ("active", NOW + 25 * 86400, NOW - 6 * 86400),      # started this month, trial over, paying
            ("trialing", NOW + 2 * 86400, NOW - 86400),         # started this month, still on its trial
            ("canceled", NOW - 3 * 86400, NOW - 10 * 86400),    # started this month, trial over, ended
            ("active", NOW + 5 * 86400, NOW - 33 * 86400),      # the cohort (4-34 days), not this month
            ("active", NOW + 5 * 86400, NOW - 90 * 86400)]      # neither
        for i, (st, end, started) in enumerate(rows):
            uid = _user(conn, f"p{i}@example.com")
            conn.execute("INSERT INTO subscriptions (user_id, status, period_end, updated_at, plan, cancel_at_end, started_at) "
                         "VALUES (?,?,?,?,?,?,?)", (uid, st, end, NOW, "monthly", 0, started))
        conn.commit()
        m = OD.money(conn, NOW)
        assert m["started_30d"] == {"n": 3, "paying": 1, "trialing": 1}, m["started_30d"]
        assert (m["ended_trials"]["n"], m["ended_trials"]["paying"]) == (3, 2), m["ended_trials"]
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_the_business_day_by_day_is_totals_and_nothing_about_an_account():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    try:
        B.init(conn)
        uid = _user(conn, "a@example.com", made=NOW - 3600, seen=NOW - 60)
        _user(conn, "b@example.com", made=NOW - 9 * 86400, seen=None)
        conn.execute("INSERT INTO subscriptions (user_id, status, period_end, updated_at, plan, cancel_at_end, started_at) "
                     "VALUES (?, 'active', ?, ?, 'monthly', 0, ?)", (uid, NOW + 20 * 86400, NOW, NOW - 10 * 86400))
        conn.commit()
        conn.execute("CREATE TABLE IF NOT EXISTS desk_days (day TEXT PRIMARY KEY, at REAL NOT NULL, accounts INTEGER, "
                     "new INTEGER, seen INTEGER, paying INTEGER, trialing INTEGER, mrr REAL, past_due INTEGER, cancelling INTEGER)")
        conn.execute("INSERT INTO desk_days VALUES (?, ?, 1, 0, 0, 0, 1, 0, 0, 0)", (OD._day(NOW - 3 * 86400), NOW - 3 * 86400))
        conn.commit()
        days = OD.trend(conn, NOW)
        assert [x["day"] for x in days] == [OD._day(NOW - 3 * 86400), OD._day(NOW)], "today's written on the first read"
        today = days[-1]
        assert (today["accounts"], today["new"], today["seen"], today["paying"]) == (2, 1, 1, 1), today
        assert today["mrr"] == B.PLANS["monthly"]["cents"] / 100, today
        # Written again through the day: one row a day, the latest numbers.
        _user(conn, "c@example.com", made=NOW - 60)
        OA.alerts_pass(conn, now=NOW + 60, health={})              # the push loop's pass, no phone to tell
        again = OD.trend(conn, NOW + 60)
        assert len(again) == 2 and again[-1]["accounts"] == 3, again
        cols = [r[1] for r in conn.execute("PRAGMA table_info(desk_days)")]
        assert not [c for c in cols if "user" in c or "email" in c or c == "id"], cols
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


# --- the backups ----------------------------------------------------------------------------------
def _aged(path: Path, hours: float, size: int = 2_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    t = NOW - hours * 3600
    os.utime(path, (t, t))


def test_the_backups_from_the_files_own_dates():
    d = Path(tempfile.mkdtemp())
    try:
        night, week = d / "backups", d / "data" / "backups"
        _aged(night / "accounts-20261104T040000Z.db.gz", 11)
        _aged(night / "accounts-20261103T040000Z.db.gz", 35)
        _aged(night / "ledger-20261104T040000Z.db.gz", 11, 9_000_000)
        (night / "last_run.json").write_text(json.dumps({"at": NOW - 11 * 3600, "offsite": "ok"}))
        _aged(week / "backup_2026-11-02.zip", 3 * 24)
        b = OD.backups(NOW, nightly=night, weekly=week)
        assert b["dbs"]["accounts"] == {"age_h": 11.0, "mb": 2.0, "kept": 2}, b["dbs"]
        assert b["dbs"]["ledger"]["mb"] == 9.0 and "history" not in b["dbs"], b["dbs"]
        assert b["run"] == {"age_h": 11.0, "offsite": "ok"} and b["weekly"]["age_d"] == 3.0, b
        assert not [p for p in OA.problems({"backups": b}, now=NOW) if p["key"] in ("backup", "offsite", "weekly-zip")]
        # Two nights missed, the offsite leg failing, the weekly zip stopped.
        _aged(night / "accounts-20261104T040000Z.db.gz", 50)
        _aged(night / "ledger-20261104T040000Z.db.gz", 50)
        (night / "last_run.json").write_text(json.dumps({"at": NOW - 5 * 3600, "offsite": "failed"}))
        _aged(week / "backup_2026-11-02.zip", 12 * 24)
        keys = [p["key"] for p in OA.problems({"backups": OD.backups(NOW, nightly=night, weekly=week)}, now=NOW)]
        assert keys[:3] == ["backup", "offsite", "weekly-zip"], keys
        gone = OD.backups(NOW, nightly=d / "nowhere", weekly=d / "nowhere")
        assert gone == {"dbs": {}, "run": None, "weekly": None, "found": False}, gone
        assert not OA.problems({"backups": gone}, now=NOW), "a folder this box cannot see is not an alarm"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_backup_script_leaves_its_note_and_still_ends_on_the_offsite_push():
    src = READ("deploy", "backup.sh")
    last = [ln.strip() for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#")][-1]
    assert last == "push_remote || true", last
    body = src[src.index("remote_kind() {"):src.index('if [[ "${1:-}" == "--test-remote" ]]')]
    assert body.count("note_run failed") == 3 and "note_run ok" in body and "note_run none" in body, \
        "every way out of the offsite push says how it went"
    d = Path(tempfile.mkdtemp())
    try:
        for remote, want in (("", "none"), (str(d / "no" / "such" / "place" / "x"), "failed")):
            env = {k: v for k, v in os.environ.items() if k != "QB_BACKUP_REMOTE"}
            if remote:
                env["QB_BACKUP_REMOTE"] = remote
            got = subprocess.run(["bash", "-c", body + '\npush_remote || true'], env={**env, "DEST": str(d)},
                                 capture_output=True, text=True, timeout=60)
            assert got.returncode == 0, got.stderr
            note = json.loads((d / "last_run.json").read_text())
            assert note["offsite"] == want and abs(note["at"] - time.time()) < 120, (remote, note, got.stdout)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- the security log -------------------------------------------------------------------------------
def _sec(ts, kind, outcome, net="198.51.100.0/24", who="aa11"):
    return json.dumps({"ts": dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds"),
                       "kind": kind, "outcome": outcome, "net": net, "who": who})


def test_the_security_log_as_counts_and_a_spraying_hour_needs_the_owner():
    d = Path(tempfile.mkdtemp())
    log = d / "security.jsonl"
    try:
        old = [_sec(NOW - 3 * 86400, "login", "ok"), _sec(NOW - 9 * 86400, "login", "fail")]   # the week's; and older
        (d / "security.jsonl.1").write_text("\n".join(old) + "\n")                              # the rotated file is read
        lines = [_sec(NOW - 600, "login", "ok"), _sec(NOW - 5 * 3600, "signup", "ok"), "not json",
                 _sec(NOW - 7200, "webhook", "bad_signature", net=None, who=None)]
        lines += [_sec(NOW - 60 - i, "login", "fail", net=f"203.0.113.{i % 2}/24", who=f"w{i % 3}") for i in range(55)]
        log.write_text("\n".join(lines) + "\n")
        s = OD.security(NOW, path=log)
        got = {(x["kind"], x["outcome"]): (x["day"], x["week"]) for x in s["lines"]}
        assert got[("login", "ok")] == (1, 2) and got[("login", "fail")] == (55, 55), got
        assert got[("signup", "ok")] == (1, 1) and got[("webhook", "bad_signature")] == (1, 1), got
        assert (s["fails_hour"], s["fails_worst_hour"], s["networks_failing"]) == (55, 55, 2), s
        assert (s["fails_one_network"], s["fails_one_account"], s["webhook_bad_day"]) == (28, 19, 1), s
        assert "203.0.113" not in json.dumps(s) and "w1" not in json.dumps(s), "counts, never the network or the account"
        keys = [p["key"] for p in OA.problems({"security": s}, now=NOW)]
        assert "signins" in keys and "webhook" not in keys, keys
        s["webhook_bad_day"] = OD.WEBHOOK_BAD
        assert "webhook" in [p["key"] for p in OA.problems({"security": s}, now=NOW)]
        assert OD.security(NOW, path=d / "none.jsonl")["lines"] == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- odds credits by league ---------------------------------------------------------------------------
def test_each_leagues_odds_credits_today_and_this_month():
    d = Path(tempfile.mkdtemp())
    spend = d / "odds_spend.jsonl"
    try:
        today = dt.date.fromtimestamp(NOW)
        first = today.replace(day=1)
        rows = [{"ts": NOW, "iso": f"{today.isoformat()}T10:00:00", "kind": "event_props", "sport": "nba", "credits": 120},
                {"ts": NOW, "iso": f"{today.isoformat()}T11:00:00", "kind": "game_lines", "sport": "nfl_lines", "credits": 3}]
        if first != today:
            rows.append({"ts": NOW, "iso": f"{first.isoformat()}T10:00:00", "kind": "event_props", "sport": "nba", "credits": 400})
        rows.append({"ts": NOW, "iso": "2001-01-01T10:00:00", "kind": "event_props", "sport": "nfl", "credits": 999})
        spend.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
        got = {r["lane"]: r for r in OD.odds_by_league(NOW, path=spend)}
        assert got["nba"]["today"] == 120 and got["nba"]["month"] == (120 if first == today else 520), got
        assert got["nfl"] == {"lane": "nfl", "today": 3, "month": 3}, "the lines tier spends its sport's money"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- the page ----------------------------------------------------------------------------------------------
def test_the_desk_page_draws_the_new_cards_and_filters_the_list():
    node = shutil.which("node")
    if not node:
        return
    sample = {"at": NOW, "now": {"members": 1, "visitors": 2, "pages": 1},
              "accounts": {"total": 6, "new_today": 1, "new_7d": 2, "new_30d": 5, "seen_today": 1, "seen_7d": 2, "seen_30d": 3,
                           "signups": [{"day": "2026-11-05", "n": 1}], "back_day1": {"of": 2, "back": 1}, "back_week1": {"of": 1, "back": 0},
                           "list": [{"id": 6, "joined": NOW, "seen": NOW, "suspended": False, "status": "active", "entitled": True},
                                    {"id": 5, "joined": NOW, "seen": None, "suspended": False, "status": "trialing", "entitled": True},
                                    {"id": 4, "joined": NOW, "seen": NOW, "suspended": False, "status": "past_due", "entitled": False},
                                    {"id": 3, "joined": NOW, "seen": NOW, "suspended": False, "status": "none", "entitled": True},
                                    {"id": 2, "joined": NOW, "seen": None, "suspended": True, "status": "none", "entitled": False},
                                    {"id": 1, "joined": NOW, "seen": NOW, "suspended": False, "status": "canceled", "entitled": False}]},
              "money": {"paying": 1, "trialing": 1, "cancelling": 0, "past_due": 1, "mrr": 25.0, "new_7d": 1, "lapsed_30d": 1,
                        "renewing_7d": 0, "by_plan": {"monthly": 1}, "plans": {"monthly": "Monthly"},
                        "started_30d": {"n": 3, "paying": 1, "trialing": 1}, "ended_trials": {"n": 4, "paying": 1, "days": 30}},
              "trend": {"days": [{"day": "2026-11-04", "accounts": 5, "new": 1, "seen": 2, "paying": 1, "trialing": 1, "mrr": 25.0,
                                  "past_due": 0, "cancelling": 0},
                                 {"day": "2026-11-05", "accounts": 6, "new": 1, "seen": 4, "paying": 3, "trialing": 0, "mrr": 75.0,
                                  "past_due": 1, "cancelling": 0}]},
              "usage": {"on": True, "first": "2026-10-01",
                        "days": [{"day": "2026-11-0%d" % (i % 9 + 1), "visits": 10 + i, "members": i, "views": 20} for i in range(14)],
                        "pages": [["likely", 30]], "sources": [{"source": "search", "visits": 40, "checkout": 4}],
                        "checkout_from": [["paywall", 4]], "alerts": {"sent": 60, "opened": 12, "kinds": [["picks_up", 50]]},
                        "did": [{"event": "signup", "k": "Accounts made", "n": 3}],
                        "flow": {"visit": 900, "checkout_click": 14, "trial_started": 6, "trial_converted": 2, "subscribed": 1,
                                 "renewed": 3, "canceled": 1}},
              "sports": {"sports": [{"sport": "nba", "playing": True, "last": "2026-11-05T13:02:11", "books": [
                  {"book": "Most Likely", "n30": 90, "today": 0, "open": 0, "w7": 30, "l7": 12, "u7": 4.25, "w30": 60, "l30": 30,
                   "p30": 1, "u30": -2.5, "roi30": -0.031},
                  {"book": "Edge", "n30": 9, "today": 0, "open": 0, "w7": 1, "l7": 2, "u7": -1.1, "w30": 4, "l30": 5, "p30": 0,
                   "u30": -1.2, "roi30": -0.13},
                  {"book": "All", "n30": 99, "today": 0, "open": 0, "w7": 31, "l7": 14, "u7": 3.15, "w30": 64, "l30": 35, "p30": 1,
                   "u30": -3.7, "roi30": -0.04}]}]},
              "picks": {"day": "2026-11-05", "open": 0, "books": []},
              "health": {"crashes": 0, "crash_kinds": 0, "crash_top": [], "builds_warned": [], "stale": {}, "commit": "abc",
                         "settled_ago_s": 60, "boards": {},
                         "odds_by": [{"lane": "nba", "today": 120, "month": 4300}, {"lane": "harvest", "today": 0, "month": 900}],
                         "backups": {"found": True, "dbs": {"accounts": {"age_h": 11.0, "mb": 2.0, "kept": 14},
                                                            "ledger": {"age_h": 40.0, "mb": 9.0, "kept": 14}},
                                     "run": {"age_h": 11.0, "offsite": "failed"}, "weekly": {"age_d": 3.0, "mb": 1.5, "kept": 6}},
                         "security": {"lines": [{"k": "Failed sign-ins", "day": 55, "week": 70, "kind": "login", "outcome": "fail"}],
                                      "fails_hour": 55, "fails_worst_hour": 55, "fails_one_network": 28, "networks_failing": 2,
                                      "fails_one_account": 19, "webhook_bad_day": 0}},
              "community": {"posts_today": 0, "comments_today": 0, "chat_today": 0, "reports_open": 0},
              "switches": [], "notice": {}, "reports": {"open": [], "open_n": 0, "hidden": [], "hidden_n": 0}}
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const document = { addEventListener() {} };
    """
    prog = (stubs + READ("web", "js", "owner.js") + f"\nconst D = {json.dumps(sample)};\n"
            "process.stdout.write(odHTML(D) + '\\n=====\\n');\n_odFilter = 'trial';\nprocess.stdout.write(odHTML(D));")
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html, trial = out.stdout.split("\n=====\n")
    for want in (
            # Each sport.
            "Each sport", "NBA", "plays today · nothing journaled yet", "30-12", "+4.25u", "60-30-1", "−2.50u", "-3.1%",
            "Last pick journaled 2026-11-05 13:02",
            # The way to paying and the trend.
            "From a visit to paying, last 30 days", "<b>900</b><span>visits</span>", "<b>5</b><span>accounts made</span>",
            "<b>14</b><span>plan buttons tapped</span>", "<b>3</b><span>subscriptions started</span>",
            "1 of 4 paying · 25%", "6 · 2", "Day by day, last 2 days", "1 → 3 (+2)", "$25 → $75",
            # How people use the site.
            "How people use the site", "Visits, 7 days", "A search engine", "40 · 4 plan taps (10%)", "paywall",
            "Reached phones", "12 · 20%", "picks_up", "Accounts made",
            # Health, backups, security.
            "The closing-price harvest", "120 today · 4,300 this month", "Backups", "The bet journal", "40 h old · 9 MB · 14 kept",
            "did NOT reach the offsite copy", "The weekly zip of the small files", "Sign-ins and security",
            "Failed sign-ins in the last hour", "28 (of 2)",
            # The list's filters, each with its count.
            'data-od-filter="paying"', "Paying <b>1</b>", "On a trial <b>1</b>", "Payment failed <b>1</b>",
            "Free access <b>1</b>", "Plan ended <b>1</b>", "Never back <b>2</b>", "Suspended <b>1</b>", "All <b>6</b>"):
        assert want in html, want
    assert html.index("Each sport") < html.index("Money") < html.index("How people use the site") < html.index("Backups")
    every = trial[trial.index("Every account, newest first"):]
    assert "Account #5" in every and "Account #6" not in every and "Account #4" not in every, "the filter shows only its own"
    assert 'class="od-chip on" data-od-filter="trial"' in every


def test_a_fresh_trend_says_when_it_starts():
    node = shutil.which("node")
    if not node:
        return
    prog = ("const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml; const toneOf = () => '';"
            "const document = { addEventListener() {} };\n" + READ("web", "js", "owner.js") +
            "\nprocess.stdout.write(odTrendHTML({days: [{day: 'x'}]}) + '|' + odUsageHTML({on: false, first: null}));")
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert "starts today" in out.stdout and "switched off (QB_ANALYTICS)" in out.stdout, out.stdout


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
