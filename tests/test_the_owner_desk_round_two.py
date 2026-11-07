"""The owner's desk, round two: who stays, the emails, the morning summary,
the spreadsheets.

Ethan, 2026-11-05, "Yes keep going", to: a morning summary on the owner's
phone; retention and lifetime value on the desk; the emails sent and failed;
a one-tap spreadsheet export. What these hold:

  * every email the site tries is counted by the part of the site that sent
    it (engine/mailer reads the calling module) and whether it went, and a
    refusal's reason never keeps an address; a phone account's placeholder
    is not a send; the desk reads the counts and a day of failures that
    outnumber the sends goes under Needs you;
  * who stays is read from what every account already has: each signup
    week's accounts, how many came back after their first day, how many
    were here this past week and how many pay; a plan cancelled on its free
    trial is not a lost member; the monthly cancel rate waits for enough
    paying months, and what a paying member is worth is a month's revenue
    over it;
  * the morning summary is yesterday in a line (accounts made, subscriptions
    started, paying and the day's change, the month's revenue, the picks'
    record, reports waiting), queued once an Eastern day from 8am to the
    site's owners' phones while the desk's switch is on; the push loop runs
    it beside the problem alerts, apart from them;
  * the switch and the four spreadsheets answer the site's owners and
    nobody else, and a spreadsheet holds counts and the business's own
    numbers only;
  * the page draws all of it.

Run directly: `python3 tests/test_the_owner_desk_round_two.py`
"""
import datetime as dt
import json
import os
import shutil
import smtplib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
_TMP = Path(tempfile.mkdtemp())
os.environ["QB_MAILLOG"] = str(_TMP / "mail.jsonl")

from engine import accounts as A                                  # noqa: E402
from engine import billing as B                                   # noqa: E402
from engine import ledger                                         # noqa: E402
from engine import mailer                                         # noqa: E402
from engine import owneralerts as OA                              # noqa: E402
from engine import ownerdesk as OD                                # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
OD.PREFS_PATH = _TMP / "owner_desk.json"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"
NOW = OD.midnight(time.time()) + 15 * 3600                      # 3pm on the site's day


def _user(conn, email, made=None, seen=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    conn.execute("UPDATE users SET created_at = ?, last_seen = ? WHERE id = ?",
                 (made if made is not None else NOW, seen, uid))
    conn.commit()
    return uid


def _sub(conn, uid, status, end, started, updated=None, plan="monthly"):
    conn.execute("INSERT INTO subscriptions (user_id, status, period_end, updated_at, plan, cancel_at_end, started_at) "
                 "VALUES (?,?,?,?,?,0,?)", (uid, status, end, updated or NOW, plan, started))
    conn.commit()


# --- the emails ---------------------------------------------------------------------------------
def _send_from(module: str, *args):
    """Call engine.mailer.send as though from `module` (the log reads the caller's own name)."""
    ns: dict = {}
    exec("def go(*a):\n    return MA.send(*a)\n", {"__name__": module, "MA": mailer}, ns)
    return ns["go"](*args)


def test_every_email_is_counted_by_who_sent_it_and_never_the_address():
    log = Path(os.environ["QB_MAILLOG"])
    log.unlink(missing_ok=True)
    real = mailer._deliver
    try:
        mailer._deliver = lambda *a, **k: None
        _send_from("engine.lifecycle", "member@example.com", "Your week", "text")
        _send_from("engine.trialnote", "member@example.com", "Your trial", "text")

        def refuse(*a, **k):
            raise smtplib.SMTPRecipientsRefused({"bounce.me@example.com": (550, b"5.1.1 <bounce.me@example.com> unknown")})
        mailer._deliver = refuse
        try:
            _send_from("server", "bounce.me@example.com", "Reset your password", "text")
        except smtplib.SMTPRecipientsRefused:
            pass
        else:
            raise AssertionError("a refusal still reaches the caller")
        try:
            mailer.send("14155552671@phone.invalid", "hi", "body")
        except Exception:                                        # noqa: BLE001
            pass
    finally:
        mailer._deliver = real
    text = log.read_text(encoding="utf-8")
    assert "example.com" not in text and "Reset your password" not in text and "Your week" not in text, text
    lines = [json.loads(x) for x in text.splitlines()]
    assert [(x["kind"], x["ok"]) for x in lines] == [("Membership emails", True), ("Trial notes", True),
                                                     ("Password resets", False)], lines
    assert "<address>" in lines[-1]["why"] and "SMTPRecipientsRefused" in lines[-1]["why"]
    m = OD.mail(time.time() + 1, path=log)
    assert (m["sent_day"], m["failed_day"], m["sent_week"], m["failed_week"]) == (2, 1, 2, 1), m
    assert m["last_fail"]["kind"] == "Password resets" and m["kinds"][0]["kind"] in ("Membership emails", "Trial notes")
    assert not [p for p in OA.problems({"mail": m}) if p["key"] == "mail"], "one failure among sends is not an alarm"
    sick = {**m, "failed_day": OD.MAIL_FAILS, "sent_day": 1}
    got = [p for p in OA.problems({"mail": sick}) if p["key"] == "mail"]
    assert got and "Password resets" in got[0]["body"], got


# --- who stays ------------------------------------------------------------------------------------
def test_who_stays_by_signup_week_and_what_a_paying_member_is_worth():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    et = lambda m, day, h: dt.datetime(2026, m, day, h, tzinfo=OD.ET).timestamp()  # noqa: E731
    now = et(11, 5, 15)                                         # a Thursday: this week from 2 November, the last from 26 October
    try:
        B.init(conn)
        _user(conn, "a@example.com", made=et(11, 5, 14), seen=now - 60)          # this week, not back yet, here
        b = _user(conn, "b@example.com", made=et(10, 26, 1), seen=et(11, 4, 12))  # last week, back, here
        _user(conn, "c@example.com", made=et(10, 26, 2), seen=et(10, 27, 10))     # last week, back, gone since
        _user(conn, "e@example.com", made=now - 140 * 86400, seen=None)           # too old for the table
        _sub(conn, b, "active", now + 20 * 86400, now - 10 * 86400)
        trial = _user(conn, "t@example.com", made=now - 30 * 86400, seen=now - 29 * 86400)
        _sub(conn, trial, "canceled", now - 26 * 86400, now - 29 * 86400, updated=now - 26 * 86400)  # its trial only
        gone = _user(conn, "g@example.com", made=now - 80 * 86400, seen=now - 30 * 86400)
        _sub(conn, gone, "canceled", now - 20 * 86400, now - 80 * 86400, updated=now - 20 * 86400)    # paid, then left
        r = OD.retention(conn, now)
        assert len(r["weeks"]) == OD.RETENTION_WEEKS
        this, last = r["weeks"][-1], r["weeks"][-2]
        assert (this["week"], last["week"]) == ("2026-11-02", "2026-10-26"), (this, last)
        assert (this["joined"], this["back"], this["recent"], this["paying"]) == (1, 0, 1, 0), this
        assert (last["joined"], last["back"], last["recent"], last["paying"]) == (2, 2, 1, 1), last
        assert r["cancels_90d"] == 1, "the trial that ended unpaid is the trials' number, not a lost member"
        assert r["arpu"] == B.PLANS["monthly"]["cents"] / 100 and r["monthly_cancel_rate"] is None, \
            "1 paying member and 1 cancel is too few member-months to say"
        for i in range(4):                                       # enough paying months to read a rate
            _sub(conn, _user(conn, f"p{i}@example.com", made=now - 70 * 86400, seen=now - 3600),
                 "active", now + 15 * 86400, now - 50 * 86400)
        r = OD.retention(conn, now)
        assert r["paying"] == 5 and r["member_months"] == 5 * 3 + 1.5
        assert r["monthly_cancel_rate"] == round(1 / 16.5, 4)
        assert r["lifetime_value"] == round(r["arpu"] / r["monthly_cancel_rate"], 2)
        assert "example.com" not in json.dumps(r), "counts, never people"
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


# --- the morning summary -----------------------------------------------------------------------------
def _eastern(y, m, d, h, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=OD.ET).timestamp()


def _owner_with_phone(conn):
    site = _user(conn, "mornowner@example.com")
    assert SF.claim(conn, "mornowner@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    PA.ensure_tables(conn)
    conn.execute("INSERT INTO push_subs (endpoint, kind, user_id, topics, leagues, created) VALUES (?,?,?,?,?,?)",
                 (f"https://fcm.googleapis.com/fcm/send/morning-{site}", "web", site, "posted", "", "2026-11-01T00:00:00"))
    conn.commit()
    return site


def test_the_morning_summary_goes_once_a_day_after_eight_while_it_is_switched_on():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    saved_db = ledger.DEFAULT_DB
    try:
        B.init(conn)
        PM.ensure_tables(conn)
        OD.set_prefs({"morning": True})
        OA._MORNING_DONE.clear()
        site = _owner_with_phone(conn)
        seven, eight = _eastern(2026, 11, 4, 7, 10), _eastern(2026, 11, 4, 8, 5)
        yday = OD._day(_eastern(2026, 11, 3, 12))
        _user(conn, "new1@example.com", made=_eastern(2026, 11, 3, 10))
        _user(conn, "new2@example.com", made=_eastern(2026, 11, 3, 21))
        payer = _user(conn, "payer@example.com", made=_eastern(2026, 10, 1, 12))
        _sub(conn, payer, "active", eight + 20 * 86400, _eastern(2026, 11, 3, 9))
        OD._days_table(conn)
        conn.execute("INSERT INTO desk_days (day, at, paying) VALUES (?, ?, 1), (?, ?, 0)",
                     (yday, eight - 86400, OD._day(_eastern(2026, 11, 2, 12)), eight - 2 * 86400))
        conn.commit()
        ledger.DEFAULT_DB = str(d / "ledger.db")
        L = ledger.connect(d / "ledger.db")
        for i, (status, pnl) in enumerate((("won", 0.91), ("won", 0.5), ("lost", -1.0))):
            L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
                      "stake_dollars, status, category, pnl_units) VALUES (?, 'nba', ?, ?, ?, 'pts', 'OVER', 20.5, -110, 1, 10, "
                      "?, 'likely', ?)", (f"{yday}T12:00:00", yday, yday, f"P{i}", status, pnl))
        L.commit()
        L.close()
        assert OA.morning_pass(conn, now=seven) == 0, "not before eight, Eastern"
        assert OA.morning_pass(conn, now=eight) == 1
        row = conn.execute("SELECT user_id, id, kind, title, body, url FROM push_mine WHERE id LIKE 'owner:morning:%'").fetchone()
        assert (row[0], row[1], row[2], row[5]) == (site, "owner:morning:2026-11-04", PA.ACCOUNT, "/#owner"), tuple(row)
        body = row[4]
        for want in ("2 new accounts", "1 subscription started", "1 paying (+1)", "$25 a month", "picks 2-1, +0.41u"):
            assert want in body, (want, body)
        assert "example.com" not in body
        assert OA.morning_pass(conn, now=eight + 900) == 0, "once a day"
        OA._MORNING_DONE.clear()
        assert OA.morning_pass(conn, now=eight + 1800) == 0, "a restart asks again; the queue never takes one id twice"
        OD.set_prefs({"morning": False})
        OA._MORNING_DONE.clear()
        assert OA.morning_pass(conn, now=eight + 86400) == 0, "switched off on the desk: nothing in the morning"
    finally:
        ledger.DEFAULT_DB = saved_db
        OD.set_prefs({"morning": True})
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_the_push_loop_runs_the_morning_summary_beside_the_problems_and_apart_from_them():
    pm = READ("engine", "pushmine.py")
    i = pm.index("_oa.alerts_pass(conn, now=t, data_dir=Path(web) / \"data\")")
    j = pm.index("_oa.morning_pass(conn, now=t)")
    assert i < j < i + 900, "after the problems, in its own try"
    assert pm.count("_oa.morning_pass(") == 1


# --- the switch and the spreadsheets, behind the desk's door -----------------------------------------------
def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _http(base, path, body=None, cookie=""):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_the_switch_and_the_spreadsheets_answer_the_owner_and_nobody_else():
    conn = A.connect()
    SF.ensure_tables(conn)
    r = conn.execute("SELECT user_id FROM feed_profiles WHERE handle = ?", ("Qellys_Book",)).fetchone()
    if r:
        site = int(r[0])
    else:
        site = _user(conn, "roundtwo@example.com")
        assert SF.claim(conn, "roundtwo@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    fan = _user(conn, "roundtwofan@example.com")
    site_c = f"qb_session={A.start_session(conn, site)}"
    fan_c = f"qb_session={A.start_session(conn, fan)}"
    conn.close()
    OD.set_prefs({"morning": True})
    httpd, base = _serve()
    try:
        for who in ("", fan_c):
            assert _http(base, "/api/owner/prefs", {"morning": False}, who)[0] == 404
            assert _http(base, "/api/owner/export?what=days", cookie=who)[0] == 404
        assert OD.prefs()["morning"] is True, "nobody else switched it"
        code, _h, raw = _http(base, "/api/owner/prefs", {"morning": False}, site_c)
        assert code == 200 and json.loads(raw)["prefs"] == {"morning": False}
        assert OD.prefs()["morning"] is False
        assert _http(base, "/api/owner/prefs", {"nothing": 1}, site_c)[0] == 400
        for what, head in (("days", "day,accounts,new,seen,paying"), ("usage", "day (UTC),visits"),
                           ("retention", "week from,accounts made"), ("sports", "sport,book,picks today")):
            code, headers, raw = _http(base, f"/api/owner/export?what={what}", cookie=site_c)
            assert code == 200, (what, code, raw[:200])
            assert headers["Content-Type"].startswith("text/csv")
            assert f'filename="qellys-{what}-' in headers["Content-Disposition"]
            text = raw.decode("utf-8")
            assert text.startswith(head), (what, text[:120])
            assert "@" not in text, "counts and the business's own numbers, never an address"
        assert _http(base, "/api/owner/export?what=accounts", cookie=site_c)[0] == 400, "only the four tables"
    finally:
        httpd.shutdown()
        OD.set_prefs({"morning": True})


# --- the page --------------------------------------------------------------------------------------------
def test_the_desk_page_draws_round_two():
    node = shutil.which("node")
    if not node:
        return
    sample = {"at": NOW, "now": {"members": 1, "visitors": 0, "pages": 1},
              "retention": {"weeks": [{"week": "2026-10-26", "joined": 4, "back": 3, "recent": 2, "paying": 1},
                                      {"week": "2026-11-02", "joined": 0, "back": 0, "recent": 0, "paying": 0}],
                            "paying": 5, "arpu": 25.0, "cancels_90d": 1, "member_months": 16.5,
                            "monthly_cancel_rate": 0.0606, "lifetime_value": 412.54},
              "health": {"crashes": 0, "crash_kinds": 0, "crash_top": [], "builds_warned": [], "stale": {}, "boards": {},
                         "mail": {"configured": True, "transport": "resend", "sent_day": 2, "failed_day": 1, "sent_week": 9,
                                  "failed_week": 1, "kinds": [{"kind": "Password resets", "sent_day": 0, "failed_day": 1,
                                                               "sent_week": 3, "failed_week": 1}],
                                  "last_fail": {"ago_h": 2.0, "kind": "Password resets",
                                                "why": "SMTPRecipientsRefused: <address> <b>x</b>"}}},
              "morning": {"day": "2026-11-04", "title": "Yesterday on Qellys Book",
                          "body": "3 new accounts · 1 paying (+1) · $25 a month · picks 2-1, +0.41u", "on": True, "hour": 8},
              "prefs": {"morning": True}, "switches": [], "notice": {}, "community": {},
              "reports": {"open": [], "open_n": 0, "hidden": [], "hidden_n": 0}}
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const document = { addEventListener() {} };
    """
    prog = (stubs + READ("web", "js", "owner.js") + f"\nconst D = {json.dumps(sample)};\n"
            "process.stdout.write(odHTML(D) + '\\n=====\\n');\nD.prefs = {morning: false};\nprocess.stdout.write(odHTML(D));")
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html, off = out.stdout.split("\n=====\n")
    for want in ("Who stays", "Came back", "3<br><span class=\"od-mute\">75%</span>", "$25.00", "about 6.1%", "about $413",
                 "Emails", "Sent, 24 h", "Password resets", "Sent through Resend", "&lt;b&gt;x&lt;/b&gt;",
                 "Morning summary", "Yesterday on Qellys Book", "picks 2-1, +0.41u", "Turn the morning summary off",
                 'id="od-morning" data-on="1"', "Download the numbers", 'href="/api/owner/export?what=days" download',
                 'href="/api/owner/export?what=retention" download'):
        assert want in html, want
    assert "<b>x</b>" not in html, "a failure's reason is text"
    assert "Turn the morning summary on" in off and 'data-on="0"' in off and "nothing goes out in the morning" in off


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
