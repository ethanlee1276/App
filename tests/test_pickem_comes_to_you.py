"""The pick'em comes to you (engine/pickem, js/social.js, js/karma.js;
Ethan, 2026-10-28: "keep building and adding more features").

The weekly pick'em was a tab on Social nobody was reminded of. Now:

  * a winner pays karma (+5, once a pick), and a perfect week (five or more
    winners, no loss, nothing open) +25 once the week is over;
  * the standings have a friends table (you and your friends, both sides
    of the friendship) beside everyone's;
  * a phone hears about three hours before a football week's picks lock:
    before the week's first kickoff and a day's first kickoff of four games
    or more, for an account that played in the last four weeks and still
    has a game there to pick, unless it turned the push off; one a day at
    most (a college Saturday has four or five kickoffs that big);
  * the Live tab's karma card carries one line while the NFL week has games
    still to pick, after today's question and never beside it, with the next
    lock in the phone's own time (the push says "in 3 hours": the server does
    not know the phone's time zone).

Run directly: `python3 tests/test_pickem_comes_to_you.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import karma as K                                    # noqa: E402
from engine import pickem as PK                                  # noqa: E402
from engine import pushalerts as PA                              # noqa: E402
from engine import pushmine as PM                                # noqa: E402
from engine import social as SOC                                 # noqa: E402

# Week of Tuesday Oct 27, 2026: Thursday night (EDT), then Sunday Nov 1 (EST
# from 2 a.m. that day): four games at 1 p.m. and two at 4:25.
THU = "2026-10-30T00:15:00Z"
SUN1 = [("NYJ", "BUF"), ("DAL", "PHI"), ("SEA", "SF"), ("KC", "LV")]
SUN4 = [("DEN", "LAC"), ("ARI", "LAR")]
GAMES = ([{"home": "GB", "away": "CAR", "date": "2026-10-29", "kickoff": THU}]
         + [{"home": h, "away": a, "date": "2026-11-01", "kickoff": "2026-11-01T18:00:00Z"} for h, a in SUN1]
         + [{"home": h, "away": a, "date": "2026-11-01", "kickoff": "2026-11-01T21:25:00Z"} for h, a in SUN4])


def _db(*handles):
    from test_the_weekly_pickem import _conn       # a sibling test's fixtures, imported where used (test_doctor)
    c = _conn(*handles)
    PK.ensure_tables(c)
    return c


def _pts(c, uid, kind):
    return c.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=? AND kind=?",
                     (uid, kind)).fetchone()[0]


def test_a_winner_pays_once_and_a_perfect_week_once_it_is_over():
    from test_the_weekly_pickem import _hist, _seed, _t
    c = _db("amy", "bob")
    sun = _t(2026, 10, 18, 17)                        # Sunday Oct 18, 1 p.m. Eastern
    finals = []
    for i, (h, a) in enumerate(SUN1 + [("CHI", "GB")]):
        gid = f"2026-10-18|{a}@{h}"
        _seed(c, 1, gid, h, a, "2026-10-18", sun, h)                 # amy: every home side
        _seed(c, 2, gid, h, a, "2026-10-18", sun, a if i == 0 else h)  # bob misses the first
        finals.append(("nfl", 2026, "2026-10-18", "2026-10-18", h, a, 24, 17))
    opener = lambda: _hist(finals)                                  # noqa: E731
    assert PK.grade(c, opener, now=_t(2026, 10, 19, 12)) == 10
    assert _pts(c, 1, "pickem_won") == 25 and _pts(c, 2, "pickem_won") == 20, "+5 a winner, a loser nothing"
    assert _pts(c, 1, "pickem_week") == 0, "not while the week is still on: a later pick could lose"
    PK.grade(c, opener, now=_t(2026, 10, 21, 15))                   # the Wednesday after
    assert _pts(c, 1, "pickem_week") == 25 and _pts(c, 2, "pickem_week") == 0, "five winners and no loss: amy's"
    PK.grade(c, opener, now=_t(2026, 10, 22, 15))
    assert _pts(c, 1, "pickem_won") == 25 and _pts(c, 1, "pickem_week") == 25, "each pays once"
    assert K.RULES["pickem_won"][0] == 5 and K.RULES["pickem_week"][0] == 25
    # Four winners is a good week, not a perfect one.
    c2 = _db("cal")
    rows = []
    for h, a in SUN1:
        _seed(c2, 1, f"2026-10-18|{a}@{h}", h, a, "2026-10-18", sun, h)
        rows.append(("nfl", 2026, "2026-10-18", "2026-10-18", h, a, 24, 17))
    PK.grade(c2, lambda: _hist(rows), now=_t(2026, 10, 19, 12))
    PK.grade(c2, lambda: _hist(rows), now=_t(2026, 10, 21, 15))
    assert _pts(c2, 1, "pickem_won") == 20 and _pts(c2, 1, "pickem_week") == 0


def test_the_friends_table_is_you_and_your_friends():
    from test_the_weekly_pickem import _board, _t
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp, GAMES)
        c = _db("amy", "bob", "cal")
        SOC.ensure_tables(c)
        for a, b in ((1, 2), (2, 1), (3, 1)):                       # amy and bob are friends; cal only asked
            c.execute("INSERT INTO friendships (user_id, friend_id, created_at) VALUES (?,?,?)", (a, b, 0))
        now = _t(2026, 10, 28, 18)
        for uid in (1, 2, 3):
            assert PK.pick(c, uid, "nfl", f"2026-10-29|CAR@GB", "GB", now=now, data_dir=d)[0] == 200
        v = PK.view(c, "nfl", 1, now=now, data_dir=d)
        hs = lambda t: sorted(r["handle"] for r in t["rows"])     # noqa: E731
        assert hs(v["week_table"]) == ["amy", "bob", "cal"] and hs(v["week_friends"]) == ["amy", "bob"], v["week_friends"]
        assert v["friends"] == 1 and hs(v["season_friends"]) == ["amy", "bob"]
        out = PK.view(c, "nfl", None, now=now, data_dir=d)
        assert out["week_friends"] is None and out["friends"] == 0, "nobody signed in has friends here"


def test_the_push_before_picks_lock_reaches_players_with_a_game_left():
    from test_the_weekly_pickem import _board, _seed, _t
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp, GAMES)
        c = _db("amy", "bob", "cal", "dee")
        PM.ensure_tables(c)
        last_sun = _t(2026, 10, 25, 17)
        for uid in (1, 2, 3):                                       # three played last week; dee never has
            _seed(c, uid, "2026-10-25|NE@MIA", "MIA", "NE", "2026-10-25", last_sun, "MIA")
        thu_gid = "2026-10-29|CAR@GB"
        assert PK.pick(c, 2, "nfl", thu_gid, "GB", now=_t(2026, 10, 29, 16), data_dir=d)[0] == 200   # bob has Thursday
        assert PK.set_remind(c, 3, False)[1]["remind"] is False                                        # cal said no
        for uid in (1, 2, 3, 4):
            code, out = PA.subscribe(c, f"{uid:064x}", "apns", user_id=uid, topics=("posted", "pickem"))
            assert code == 200, out
        topics = {uid: PM.asked(c, uid, "pickem") for uid in (1, 2, 3, 4)}
        assert topics == {1: True, 2: True, 3: False, 4: False}, ("a player's phone carries it, unless off", topics)
        assert PK.reminds(c, 1) and not PK.reminds(c, 3) and not PK.reminds(c, 4)
        assert PK.reminds(c, 4, switch_only=True), "the page's switch reads on until turned off"

        thu = _t(2026, 10, 29, 21, 30)                               # 5:30 p.m. EDT, 2h45 before kickoff
        assert PK.alerts_pass(c, now=thu, data_dir=d) == 1
        got = c.execute("SELECT user_id, id, title, body, url FROM push_mine").fetchall()
        assert [(r[0], r[1]) for r in got] == [(1, f"pickem:nfl:{int(PK._ts(THU))}")], got
        assert got[0][2] == "NFL Pick'em locks in 3 hours", "relative: the server does not know the phone's time zone"
        assert got[0][3] == "CAR at GB kicks off then, and you have 7 picks left this week." and got[0][4] == "/#feed/pickem/nfl"
        assert PK.alerts_pass(c, now=thu + 600, data_dir=d) == 0, "once a kickoff"
        assert PK.alerts_pass(c, now=_t(2026, 10, 29, 20), data_dir=d) == 0, "four hours out is too early"

        sun = _t(2026, 11, 1, 15, 15)                               # 10:15 a.m. EST before the four 1 p.m. games
        assert PK.alerts_pass(c, now=sun, data_dir=d) == 2, "amy and bob both have Sunday to pick"
        assert c.execute("SELECT body FROM push_mine WHERE user_id=2 AND id LIKE 'pickem:nfl:%' ORDER BY rowid DESC").fetchone()[0] \
            == "4 games kick off then, and you have 6 picks left this week."
        assert PK.alerts_pass(c, now=_t(2026, 11, 1, 19), data_dir=d) == 0, "two games at 4:25: not worth a push"

        # dee plays this week: her phone learns the topic at the next push it is owed.
        c.execute("DELETE FROM push_mine")
        assert PK.pick(c, 4, "nfl", "2026-11-01|LAC@DEN", "DEN", now=_t(2026, 10, 29, 16), data_dir=d)[0] == 200
        assert PK.alerts_pass(c, now=sun + 60, data_dir=d) >= 1
        assert PM.asked(c, 4, "pickem") and c.execute("SELECT 1 FROM push_mine WHERE user_id=4").fetchone()


def test_a_college_saturday_is_one_push_not_five():
    from test_the_weekly_pickem import _board, _seed, _t
    # Week of Tuesday Nov 3 (EST): a Tuesday night MAC game, then Saturday's
    # noon, 3:30 and 7:30 windows, each big enough on its own.
    sat = lambda hh, mm, n, tag: [{"home": f"H{tag}{i}", "away": f"A{tag}{i}", "date": "2026-11-07",   # noqa: E731
                                   "kickoff": f"2026-11-{'08' if hh >= 24 else '07'}T{hh % 24:02d}:{mm:02d}:00Z"}
                                  for i in range(n)]
    games = ([{"home": "Ohio", "away": "Ball State", "date": "2026-11-03", "kickoff": "2026-11-04T00:00:00Z"}]
             + sat(17, 0, 5, "n") + sat(20, 30, 5, "t") + sat(24, 30, 4, "e"))
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp, games, name="cfb.json")
        c = _db("amy")
        PM.ensure_tables(c)
        _seed(c, 1, "2026-10-31|Army@Navy", "Navy", "Army", "2026-10-31", _t(2026, 10, 31, 17), "Navy", sport="cfb")
        assert PA.subscribe(c, f"{1:064x}", "apns", user_id=1, topics=("posted", "pickem"))[0] == 200
        assert PK.alerts_pass(c, now=_t(2026, 11, 3, 21, 15), data_dir=d) == 1, "the week's first game"
        title = tuple(c.execute("SELECT title, body FROM push_mine").fetchone())
        assert title == ("College football Pick'em locks in 3 hours",
                         "Ball State at Ohio kicks off then, and you have 15 picks left this week."), title
        assert PK.alerts_pass(c, now=_t(2026, 11, 7, 14, 15), data_dir=d) == 1, "Saturday noon"
        assert PK.alerts_pass(c, now=_t(2026, 11, 7, 17, 45), data_dir=d) == 0, "3:30: the day had its push"
        assert PK.alerts_pass(c, now=_t(2026, 11, 7, 21, 45), data_dir=d) == 0, "7:30 Eastern is still Saturday"
        assert c.execute("SELECT COUNT(*) FROM push_mine WHERE user_id=1").fetchone()[0] == 2


def test_the_live_card_line_says_what_is_left_and_when_it_locks():
    from test_the_weekly_pickem import _board, _t
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp, GAMES)
        c = _db("amy")
        now = _t(2026, 10, 28, 18)                                 # Wednesday afternoon
        assert PK.next_up(c, 1, "nfl", now=now, data_dir=d) == {"sport": "nfl", "picked": 0, "games": 7, "lock": THU}
        PK.pick(c, 1, "nfl", "2026-10-29|CAR@GB", "GB", now=now, data_dir=d)
        n = PK.next_up(c, 1, "nfl", now=now, data_dir=d)
        assert n["picked"] == 1 and n["lock"] == "2026-11-01T18:00:00Z", n
        for g in GAMES[1:]:
            PK.pick(c, 1, "nfl", f"{g['date']}|{g['away']}@{g['home']}", g["home"], now=now, data_dir=d)
        assert PK.next_up(c, 1, "nfl", now=now, data_dir=d) is None, "all picked: nothing to say"
        assert PK.next_up(c, None, "nfl", now=now, data_dir=d) is None
        assert K._pickem_next(c, 1, now, d) is None and K._pickem_next(c, 99, now, Path(tmp) / "nowhere") is None


def test_the_pages_draw_it_and_the_policy_names_it():
    social = (ROOT / "web" / "js" / "social.js").read_text(encoding="utf-8")
    for want in ("function pickemScopeHTML(P)", "function pickemRemindHTML(P)", 'data-fd="pk-scope"', 'data-fd="pk-remind"',
                 'api("pickem-remind", { on })', "fr ? P.week_friends : P.week_table", '<a href="#feed/search">Find people</a> to add'):
        assert want in social, want
    kjs = (ROOT / "web" / "js" / "karma.js").read_text(encoding="utf-8")
    assert "function krPickemHTML(p)" in kjs and "${krAskHTML(d) || krPickemHTML(v.pickem)}" in kjs, \
        "after today's question, never beside it"
    assert '"trivia", "pickem_won", "pickem_week"]]' in kjs, "How karma works lists both"
    assert "a.kr-ask { text-decoration: none; }" in (ROOT / "web" / "css" / "karma.css").read_text(encoding="utf-8")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"pin", "pickem", "pickem-remind"):' in srv and "PK.set_remind(conn, uid, body.get(\"on\") is True)" in srv
    assert "pickem" in PA.PERSONAL and PM.TTL_S["pickem"] == 3 * 3600
    pm = (ROOT / "engine" / "pushmine.py").read_text(encoding="utf-8")
    assert "told += _pk.alerts_pass(conn, now=t)" in pm
    policy = " ".join((ROOT / "web" / "privacy.html").read_text(encoding="utf-8").split())
    for want in ("<code>pickem_picks</code>", "<code>pickem_prefs</code>", "Remind me before picks lock",
                 "a pick'em winner or a perfect pick'em week"):
        assert want in policy, want


# --- in a phone browser ----------------------------------------------------------
def test_in_a_phone_browser_friends_the_switch_and_the_live_line():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    import test_todays_question as TQ
    conn, (me, _sam) = TQ._db()
    v = dict(K.me(conn, me), camp=None, pickem={"sport": "nfl", "picked": 1, "games": 7, "lock": "2026-11-01T18:00:00Z"})
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    row = lambda h, w, me=False: {"handle": h, "name": h.title(), "color": 2, "w": w, "l": 0, "p": 0,   # noqa: E731
                                  "open": 0, "rank": 1, "me": me}
    view = {"sport": "nfl", "week": "2026-10-27", "label": "Oct 27 – Nov 2", "current": True, "prev": "2026-10-20",
            "next": None, "games": [], "season_days": 200, "signed_in": True, "has_handle": True, "remind": True,
            "week_table": {"rows": [row("zed", 3), row("ethan", 2, True)], "me": None, "players": 2},
            "season_table": {"rows": [row("zed", 9)], "me": None, "players": 1},
            "week_friends": {"rows": [row("ethan", 2, True), row("sam", 1)], "me": None, "players": 2},
            "season_friends": {"rows": [row("sam", 4)], "me": None, "players": 1}, "friends": 1}
    old_q = {"qkey": TQ.DAY, "text": "Who?", "options": ["A", "B", "C", "D"], "mine": 1, "answer": 1, "open": True,
             "day": TQ.DAY, "split": [0, 1, 0, 0], "n": 1, "why": "B"}
    posted = []
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731

    def remind(route):
        posted.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "remind": False}))

    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block", timezone_id="America/Los_Angeles", locale="en-US")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/feed/rail*", ful(json.dumps({"trending": {"picks": [], "active": 0}, "leaders": [],
                                                                "stats": {}, "suggest": [], "tags": []})))
                page.route("**/api/feed/pickem?*", ful(json.dumps(view)))
                page.route("**/api/feed/pickem-remind", remind)
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/trivia/daily*", ful(json.dumps({"signed_in": True, "day": TQ.DAY, "q": old_q})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                     f"localStorage.setItem('qb_new_2026_10_28b','1');localStorage.setItem('qb_kr_level','{v['level']}');}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html#feed/pickem/nfl", wait_until="load")
                page.wait_for_selector(".fd-pk-scope", timeout=15000)
                lead = "[...document.querySelectorAll('.fd-pk-tables .fd-lead .fd-person span span')].map((s) => s.textContent)"
                got["everyone"] = page.evaluate(lead)
                page.click('.fd-pk-scope [data-fd="pk-scope"][data-v="friends"]')
                page.wait_for_timeout(600)
                got["friends"] = page.evaluate(lead)
                got["tab"] = page.evaluate("(document.querySelector('.fd-pk-scope button.on') || {}).textContent || ''")
                page.click('[data-fd="pk-remind"]')
                page.wait_for_timeout(500)
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(3500)
                got["line"] = page.evaluate("(document.querySelector('.kr-live .kr-pk') || {}).textContent || ''")
                got["href"] = page.evaluate("(document.querySelector('.kr-live .kr-pk') || {}).getAttribute?.('href') || ''")
                got["now"] = page.evaluate("typeof krLockWhen === 'function' ? krLockWhen(new Date().toISOString()) : 'none'")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert got["everyone"] == ["@zed", "@ethan", "@zed"], got
    assert got["friends"] == ["@ethan", "@sam", "@sam"] and got["tab"].startswith("Friends · 1"), got
    assert posted == [{"on": False}], posted
    line = " ".join(got["line"].split())
    # 1 p.m. Eastern on Sunday Nov 1 is 10 a.m. on a phone in Los Angeles ("today" on the day itself).
    assert ("Pick'em · 1 of 7 picked · locks Sun 10:00 AM" in line or "locks today 10:00 AM" in line) \
        and got["href"] == "#feed/pickem/nfl", got
    assert got["now"].startswith("today "), got


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
