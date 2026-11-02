"""The owner's desk and the notice to everybody, for the site's own account.

Ethan, 2026-11-02: "deep dive and add more features and tools the Qellys book
owners account should have".

What these hold:

  * engine/ownerdesk counts accounts (new, seen, came back, signups a day),
    money (paying, trials, cancelling, failing, lapsed, the month's recurring
    revenue by plan), today's picks by book, the room (posts, chat, reports
    still up) — counts only, nobody named — and one section that cannot be
    read never takes the desk down;
  * engine/sitenotice stands one plain-text notice for its hours, replaces it
    on a new post, clears it, and refuses an empty one;
  * /api/owner/desk and /api/owner/notice answer the verified Qellys_Book
    account and nobody else (a 404 to everyone else, members included), and
    the notice rides on /api/billing/status for every page;
  * the desk page draws what it is sent, the notice draws as text, and both
    load only when they are wanted (rooms; the notice only when there is one);
  * the reports queue puts the feed's and the game chat's reports in one list
    (still up first, most reported first; the words, never who), and its
    Hide / Keep it up / Restore answer the site's account and nobody else.

Run directly: `python3 tests/test_the_owner_desk.py`
"""
import json
import os
import shutil
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
_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import billing as B                                   # noqa: E402
from engine import ownerdesk as OD                                # noqa: E402
from engine import sitenotice as SN                               # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
SN.PATH = _TMP / "site_notice.json"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"
NOW = OD.midnight(time.time()) + 15 * 3600                      # 3pm on the site's day


def _user(conn, email, made=None, seen=None, handle=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    conn.execute("UPDATE users SET created_at = ?, last_seen = ? WHERE id = ?",
                 (made if made is not None else NOW, seen, uid))
    conn.commit()
    if handle:
        assert SF.profile_set(conn, uid, handle, "", name=handle.title())[0] == 200
    return uid


# --- the engine ------------------------------------------------------------------
def test_accounts_are_counts_by_the_sites_day():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    try:
        _user(conn, "a@example.com", made=NOW - 3600, seen=NOW - 60)               # today, seen today
        _user(conn, "b@example.com", made=NOW - 3 * 86400, seen=NOW - 86400)       # this week, back after day 1
        _user(conn, "c@example.com", made=NOW - 20 * 86400, seen=NOW - 20 * 86400) # never came back
        _user(conn, "e@example.com", made=NOW - 40 * 86400, seen=NOW - 2 * 86400)  # old, came back
        a = OD.accounts(conn, NOW)
        assert (a["total"], a["new_today"], a["new_7d"], a["new_30d"]) == (4, 1, 2, 3), a
        assert (a["seen_today"], a["seen_7d"]) == (1, 3), a
        assert len(a["signups"]) == OD.SIGNUP_DAYS and a["signups"][-1]["n"] == 1, a["signups"][-3:]
        assert a["back_day1"] == {"of": 3, "back": 2}, a["back_day1"]
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_money_counts_who_pays_and_what_a_month_brings():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    try:
        B.init(conn)
        rows = [  # status, plan, period_end, cancel_at_end, started, updated
            ("active", "monthly", NOW + 5 * 86400, 0, NOW - 2 * 86400, NOW),      # paying, renews this week, new
            ("active", "yearly", NOW + 200 * 86400, 0, NOW - 90 * 86400, NOW),
            ("active", "monthly", NOW + 20 * 86400, 1, NOW - 40 * 86400, NOW),    # cancelling, still paid up
            ("trialing", "monthly", NOW + 3 * 86400, 0, NOW - 86400, NOW),
            ("past_due", "monthly", NOW + 86400, 0, NOW - 60 * 86400, NOW),
            ("canceled", "monthly", NOW - 5 * 86400, 0, NOW - 70 * 86400, NOW - 5 * 86400),
        ]
        for i, (st, plan, end, cae, started, upd) in enumerate(rows):
            uid = _user(conn, f"m{i}@example.com")
            conn.execute("INSERT INTO subscriptions (user_id, status, period_end, updated_at, plan, cancel_at_end, started_at) "
                         "VALUES (?,?,?,?,?,?,?)", (uid, st, end, upd, plan, cae, started))
        conn.commit()
        m = OD.money(conn, NOW)
        assert m["paying"] == 3 + (1 if B.entitled("past_due", NOW + 86400, NOW) else 0), m
        assert (m["trialing"], m["cancelling"], m["past_due"], m["lapsed_30d"]) == (1, 1, 1, 1), m
        assert m["by_plan"]["monthly"] >= 2 and m["by_plan"]["yearly"] == 1, m
        monthly, yearly = B.PLANS["monthly"], B.PLANS["yearly"]
        want = 2 * monthly["cents"] / 100 + yearly["cents"] / 100 / 12
        if B.entitled("past_due", NOW + 86400, NOW):
            want += monthly["cents"] / 100
        assert abs(m["mrr"] - round(want, 2)) < 0.02, (m["mrr"], want)
        assert m["renewing_7d"] >= 1 and m["new_7d"] >= 2, m
        assert "email" not in json.dumps(m), "counts, never people"
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_todays_picks_by_book_and_the_room():
    from engine import ledger as L
    d = Path(tempfile.mkdtemp())
    lc = L.connect(d / "ledger.db")
    conn = A.connect(str(d / "a.db"))
    try:
        day = OD._day(NOW)
        for i, (cat, st, pnl) in enumerate([("main", "won", 0.9), ("main", "lost", -1.0), ("likely", "open", None),
                                            ("longshot", "won", 1.8), ("likely", "won", 0.5)]):
            lc.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, stake_units, status, pnl_units, "
                       "category, game_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("t", "nfl", "2026-W08", f"P{i}", "rec_yds", "OVER", 50.5, -110, 1.0, st, pnl, cat, day))
        lc.commit()
        p = OD.picks(lc, NOW, record_path=d / "missing.json")
        books = {b["book"]: b for b in p["books"]}
        assert books["Edge"]["n"] == 2 and books["Edge"]["won"] == 1 and books["Edge"]["units"] == -0.1, books["Edge"]
        assert books["Most Likely"]["open"] == 1 and books["Long Shots"]["units"] == 1.8, books
        assert p["record"] is None and p["open"] == 1
        # The room: today's posts, comments, chat, and reports on things still up.
        SF.ensure_tables(conn)
        u = _user(conn, "poster@example.com", handle="Poster")
        conn.execute("INSERT INTO feed_posts (user_id, sport, legs, created_at) VALUES (?,?,?,?)", (u, "nfl", "[]", NOW - 60))
        conn.execute("INSERT INTO feed_posts (user_id, sport, legs, created_at, hidden) VALUES (?,?,?,?,1)", (u, "nfl", "[]", NOW - 90))
        conn.execute("INSERT INTO feed_reports (kind, item_id, user_id, created_at) VALUES ('post', 1, ?, ?)", (u, NOW - 30))
        conn.execute("INSERT INTO feed_reports (kind, item_id, user_id, created_at) VALUES ('post', 2, ?, ?)", (u, NOW - 30))
        conn.commit()
        c = OD.community(conn, NOW)
        assert c["posts_today"] == 2 and c["reports_open"] == 1, c
    finally:
        conn.close()
        lc.close()
        shutil.rmtree(d, ignore_errors=True)


def _reported_room(conn):
    """A feed post with one report, a comment hidden by hand, and two chat
    messages: one with two reports, one taken down by three."""
    from engine import gamechat as GC
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    poster = _user(conn, "rposter@example.com", handle="RPoster")
    readers = [_user(conn, f"reader{i}@example.com") for i in range(3)]
    conn.execute("INSERT INTO feed_posts (user_id, sport, legs, caption, created_at) VALUES (?,?,?,?,?)",
                 (poster, "nfl", "[]", "Lock of the <b>century</b>", NOW - 600))
    post = conn.execute("SELECT MAX(id) FROM feed_posts").fetchone()[0]
    conn.execute("INSERT INTO feed_comments (post_id, user_id, body, created_at, hidden) VALUES (?,?,?,?,1)",
                 (post, poster, "a comment the founder hid", NOW - 500))
    assert SF.report(conn, readers[0], "post", post, "spam")[0] == 200
    for body in ("you all stink", "buy my picks at a link"):
        conn.execute("INSERT INTO chat_msgs (room, user_id, body, created_at) VALUES (?,?,?,?)",
                     ("nfl_401873033", poster, body, NOW - 300))
    m1, m2 = [r[0] for r in conn.execute("SELECT id FROM chat_msgs ORDER BY id")]
    for i, who in enumerate(readers):
        if i < 2:
            assert GC.report(conn, who, m1, "abuse", now=NOW)[0] == 200
        assert GC.report(conn, who, m2, "spam", now=NOW)[0] == 200
    conn.commit()
    return {"post": post, "m1": m1, "m2": m2}


def test_reports_from_the_feed_and_the_game_chat_in_one_queue():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "a.db"))
    try:
        ids = _reported_room(conn)
        r = OD.reports(conn)
        up = [(x["where"], x["kind"], x["id"], x["reports"]) for x in r["open"]]
        assert up == [("chat", "message", ids["m1"], 2), ("feed", "post", ids["post"], 1)], up
        assert r["open_n"] == 2 and r["hidden_n"] == 2, r
        down = {(x["where"], x["kind"]) for x in r["hidden"]}
        assert down == {("chat", "message"), ("feed", "comment")}, "three reports took one down; the founder hid the other"
        chat = r["open"][0]
        assert chat["game"] == "nfl/401873033" and chat["reasons"] == ["abuse"] and chat["text"] == "you all stink"
        flat = json.dumps(r)
        assert "rposter" not in flat.lower() and "example.com" not in flat, "the words, never who wrote or reported"
        assert OD.community(conn, NOW)["reports_open"] == 2, "the room's count is the queue's"
        # Hide the chat message; keep the post up, which clears its reports.
        assert OD.moderate(conn, "chat", "message", ids["m1"], True)[0] == 200
        assert OD.moderate(conn, "feed", "post", ids["post"], False)[0] == 200
        r = OD.reports(conn)
        assert r["open_n"] == 0 and OD.community(conn, NOW)["reports_open"] == 0, r["open"]
        assert ids["post"] not in [x["id"] for x in r["hidden"] if x["kind"] == "post"], "kept up, off the queue"
        # Restore the one three reports took down: back in its room, its reports gone.
        assert OD.moderate(conn, "chat", "message", ids["m2"], False)[0] == 200
        assert conn.execute("SELECT hidden FROM chat_msgs WHERE id=?", (ids["m2"],)).fetchone()[0] == 0
        assert not conn.execute("SELECT 1 FROM chat_reports WHERE msg_id=?", (ids["m2"],)).fetchone()
        assert OD.moderate(conn, "feed", "story", 1, True)[0] == 400
        assert OD.moderate(conn, "chat", "message", "x", True)[0] == 400
        assert OD.moderate(conn, "chat", "message", 99999, True)[0] == 404
    finally:
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_a_league_with_no_games_is_resting_not_stale():
    from engine import bugscan as BS
    d = Path(tempfile.mkdtemp())
    real_root, real_scan = OD.ROOT, BS.scan
    try:
        (d / "web" / "data").mkdir(parents=True)
        (d / "web" / "data" / "live_mlb.json").write_text(json.dumps({"games": []}))
        (d / "web" / "data" / "live_nba.json").write_text(json.dumps({"games": [{"event_id": "1"}]}))
        OD.ROOT = d
        BS.scan = lambda hours, now=None, journal=None: {"crashes": [], "builds": {}, "stale": {"mlb": 30.5, "nba": 5.0},
                                                          "update": {}}
        h = OD.health(NOW)
        assert h["stale"] == {"nba": 5.0} and h["resting"] == ["mlb"], (h["stale"], h["resting"])
    finally:
        OD.ROOT, BS.scan = real_root, real_scan
        shutil.rmtree(d, ignore_errors=True)


def test_one_section_that_cannot_be_read_never_takes_the_desk_down():
    conn = sqlite3.connect(":memory:")                 # no tables at all
    try:
        got = OD.desk(conn, lconn=sqlite3.connect(":memory:"), now=NOW)
        assert "error" in got["accounts"] and "error" in got["picks"], got
        assert isinstance(got["switches"], list) and "now" in got and "health" in got
        json.dumps(got)
    finally:
        conn.close()


# --- the notice -------------------------------------------------------------------
def test_one_notice_plain_text_for_its_hours():
    p = _TMP / "notice_a.json"
    assert SN.current(path=p) is None
    assert SN.post("   ", path=p)[0] == 400, "an empty notice is refused"
    code, out = SN.post("Picks are late tonight:\n the odds feed is down.\x07", hours=2, tone="warn", now=1000, path=p)
    assert code == 200 and out["notice"]["text"] == "Picks are late tonight: the odds feed is down."
    cur = SN.current(now=1000 + 3600, path=p)
    assert cur["tone"] == "warn" and cur["until"] == 1000 + 7200
    assert SN.current(now=1000 + 7201, path=p) is None, "its hours run out"
    first = cur["id"]
    SN.post("x" * 500, hours=999, tone="loud", now=2000, path=p)
    cur = SN.current(now=2001, path=p)
    assert len(cur["text"]) == SN.MAX_LEN and cur["tone"] == "info" and cur["until"] == 2000 + SN.MAX_HOURS * 3600
    assert cur["id"] != first, "a new notice is a new id, so closing one never hides the next"
    SN.clear(path=p)
    assert SN.current(now=2001, path=p) is None


# --- the server -------------------------------------------------------------------
def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _site(conn):
    """The verified Qellys_Book account: made by whichever server test runs
    first and shared after (the handle is one of a kind)."""
    SF.ensure_tables(conn)
    r = conn.execute("SELECT user_id FROM feed_profiles WHERE handle = ?", ("Qellys_Book",)).fetchone()
    if r:
        return int(r[0])
    uid = _user(conn, "deskowner@example.com")
    assert SF.claim(conn, "deskowner@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    return uid


def _call(base, path, body=None, cookie=""):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def test_the_desk_and_the_notice_answer_the_site_account_and_nobody_else():
    conn = A.connect()
    site = _site(conn)
    fan = _user(conn, "deskfan@example.com", handle="DeskFan")
    site_c = f"qb_session={A.start_session(conn, site)}"
    fan_c = f"qb_session={A.start_session(conn, fan)}"
    conn.close()
    SN.clear()
    httpd, base = _serve()
    try:
        for who in ("", fan_c):
            assert _call(base, "/api/owner/desk", cookie=who)[0] == 404, "no such page for anybody else"
            assert _call(base, "/api/owner/notice", {"text": "hello"}, who)[0] == 404
        assert SN.current() is None, "nobody else put anything up"
        code, desk = _call(base, "/api/owner/desk", cookie=site_c)
        assert code == 200 and desk["accounts"]["total"] >= 2, desk.get("accounts")
        for key in ("now", "money", "picks", "health", "community", "switches", "notice"):
            assert key in desk, key
        assert "deskfan@example.com" not in json.dumps(desk), "counts, never people"
        # The notice: up from the desk, on every page's status call, then down.
        code, out = _call(base, "/api/owner/notice", {"text": "New: the play-by-play.", "hours": 3, "tone": "good"}, site_c)
        assert code == 200 and out["notice"]["text"] == "New: the play-by-play."
        st = _call(base, "/api/billing/status")[1]
        assert st["notice"]["text"] == "New: the play-by-play." and st["notice"]["tone"] == "good"
        assert _call(base, "/api/owner/notice", {"text": ""}, site_c)[0] == 400
        assert _call(base, "/api/owner/notice", {"clear": True}, site_c)[0] == 200
        assert _call(base, "/api/billing/status")[1]["notice"] is None
    finally:
        httpd.shutdown()
        SN.clear()


def test_the_reports_queue_answers_the_site_account_and_nobody_else():
    conn = A.connect()
    site = _site(conn)
    ids = _reported_room(conn)
    fan = _user(conn, "repfan@example.com", handle="RepFan")
    site_c = f"qb_session={A.start_session(conn, site)}"
    fan_c = f"qb_session={A.start_session(conn, fan)}"
    conn.close()
    httpd, base = _serve()
    try:
        hide = {"where": "chat", "kind": "message", "id": ids["m1"], "hidden": True}
        for who in ("", fan_c):
            assert _call(base, "/api/owner/hide", hide, who)[0] == 404, "no such door for anybody else"
        code, desk = _call(base, "/api/owner/desk", cookie=site_c)
        assert code == 200 and ids["m1"] in [x["id"] for x in desk["reports"]["open"] if x["where"] == "chat"]
        assert _call(base, "/api/owner/hide", hide, site_c)[0] == 200
        assert _call(base, "/api/owner/hide", {"where": "feed", "kind": "post", "id": ids["post"], "hidden": False},
                     site_c)[0] == 200
        desk = _call(base, "/api/owner/desk", cookie=site_c)[1]
        still = [(x["where"], x["id"]) for x in desk["reports"]["open"]]
        assert ("chat", ids["m1"]) not in still and ("feed", ids["post"]) not in still, still
        conn = A.connect()
        try:
            assert conn.execute("SELECT hidden FROM chat_msgs WHERE id=?", (ids["m1"],)).fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        httpd.shutdown()


# --- the page ---------------------------------------------------------------------
def test_the_desk_page_draws_what_it_is_sent():
    node = shutil.which("node")
    if not node:
        return
    sample = {"at": NOW, "now": {"members": 3, "visitors": 7, "pages": 4},
              "accounts": {"total": 120, "new_today": 4, "new_7d": 19, "new_30d": 61, "seen_today": 22, "seen_7d": 70,
                           "seen_30d": 95, "signups": [{"day": "2026-11-0%d" % (i % 9 + 1), "n": i % 5} for i in range(14)],
                           "back_day1": {"of": 100, "back": 41}, "back_week1": {"of": 80, "back": 22}},
              "money": {"paying": 31, "trialing": 6, "cancelling": 2, "past_due": 1, "mrr": 742.5, "new_7d": 4,
                        "lapsed_30d": 3, "renewing_7d": 9, "by_plan": {"monthly": 25, "yearly": 6},
                        "plans": {"monthly": "Monthly", "yearly": "Yearly"}},
              "picks": {"day": "2026-11-02", "open": 14, "books": [{"book": "Edge", "n": 5, "won": 2, "lost": 1, "push": 0,
                                                                    "open": 2, "units": 0.85}],
                        "record": {"wins": 2779, "losses": 1961, "units": 13.25, "roi": 0.0082, "since": "2026-08-06",
                                   "longshots": {"wins": 75, "losses": 383, "units": -4.31}}},
              "health": {"crashes": 2, "crash_kinds": 1, "crash_top": [{"m": "TypeError: x is undefined", "n": 2}],
                         "builds_warned": [], "stale": {}, "commit": "abc1234", "settled_ago_s": 140,
                         "update": {"ok": True, "at": "2026-11-02T10:31:00", "commit": "abc1234", "note": "pulled"},
                         "odds": {"remaining": 41000, "used": 59000, "days_left": 28, "per_day": 1460},
                         "disk": {"free_gb": 31.2, "used_pct": 58.0}, "boards": {"nfl": 0.4, "nba": 5.0}},
              "community": {"posts_today": 9, "comments_today": 30, "chat_today": 210, "reports_open": 1, "push_phones": 44},
              "switches": [{"name": "Who's on now", "on": True}], "notice": {"error": "x"},
              "reports": {"open": [{"where": "chat", "kind": "message", "id": 7, "reports": 2, "reasons": ["abuse"],
                                    "hidden": False, "text": "you <b>all</b> stink", "game": "nfl/401873033"}],
                          "open_n": 1, "hidden_n": 1,
                          "hidden": [{"where": "feed", "kind": "comment", "id": 3, "reports": 0, "reasons": [],
                                      "hidden": True, "text": "hid by hand"}]}}
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const document = { addEventListener() {} };
    """
    prog = stubs + READ("web", "js", "owner.js") + f"\nprocess.stdout.write(odHTML({json.dumps(sample)}));"
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html = out.stdout
    for want in ("Members on", ">7<", "Paying", "$743", "A month, recurring", "Edge", "+0.85u", "2,779-1,961",
                 "Long Shots (their own record)", "Crashes, 24 h", "TypeError: x is undefined", "41,000 · 1,460 a day for 28 days",
                 "31.2 GB free", "Reports waiting", "Who's on now", "Put it up", 'maxlength="200"', "NBA 5 h",
                 # The reports queue: words escaped, a way to the game, the three buttons.
                 "Reports to review", "Game-chat message", "2 reports · abuse", "you &lt;b&gt;all&lt;/b&gt; stink",
                 'href="#pbp/nfl/401873033"', 'data-od-mod="1" data-where="chat" data-kind="message" data-id="7"',
                 "Keep it up", "Restore", "hidden by hand", "Hidden from everybody · 1"):
        assert want in html, want
    assert html.index("Reports to review") < html.index("Today's picks"), "reports waiting go near the top"


def test_the_notice_draws_as_text_and_loads_only_when_there_is_one():
    js = READ("web", "js", "notice.js")
    assert 'bar.querySelector(".sn-text").textContent = n.text;' in js, "text, never markup"
    assert 'localStorage.setItem(KEY, String(n.id || ""))' in js and 'const KEY = "qb.notice.closed";' in js
    app = READ("web", "js", "app.js")
    assert ('if (_pwStatus.notice || window.qbNotice) loadRoom("js/notice.js", "css/notice.css")'
            '.then(() => window.qbNotice && qbNotice(_pwStatus.notice));') in app
    assert 'function renderOwner(...a) { return roomCall(renderOwner, "renderOwner", "js/owner.js", "css/owner.css", a); }' in app
    assert 'if (name === "owner") renderOwner();' in app and '"whoson", "owner", "discord"' in app
    acct = READ("web", "js", "account.js")
    assert 'title: "Owner desk"' in acct and 'href: "#owner"' in acct
    assert acct.index('title: "Owner desk"') > acct.index("_acctUser.whoson"), "inside the site account's own group"
    html = READ("web", "index.html")
    assert '<section class="view" id="view-owner">' in html and 'id="owner-body"' in html


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
