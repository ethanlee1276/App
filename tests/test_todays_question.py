"""Today's question (engine/trivia daily; Ethan, 2026-10-28: "keep building
… keep inventing … keep user retainment").

Wordle's lesson: one question a day, the same for everybody, is a reason
to come back on a day with no game you care about. It comes from the
trivia in the stoppages (the season logs the boards read), off one of the
day's games on the scoreboards. What this file pins:

  * one question a day (Eastern), asked the first time it is read and kept
    for the day whatever the scoreboards do after; a game whose teams have
    no logs is passed over; a day with no game has none;
  * one answer an account; the right name and how everybody answered show
    only after answering;
  * right pays +10 karma once, as itself: never twice through the catch-up,
    and it counts for the Trivia head badge and the day's trivia quest;
  * the server's route, the page's card and the policy.

Run directly: `python3 tests/test_todays_question.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from engine import accounts as A                             # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import socialfeed as SF                          # noqa: E402
from engine import trivia as TV                              # noqa: E402

DAY = "2026-10-28"


def _hist():
    """The stoppage trivia's season logs (tests/test_trivia_in_the_stoppages)."""
    from test_trivia_in_the_stoppages import _hist as logs
    return logs()


def _slate(*games):
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [{"home": h, "away": a, "event_id": str(i)}
                                                            for i, (a, h) in enumerate(games)]}))
    return d


def _db(n=2):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    TV._bank.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    TV.ensure_tables(conn)
    K.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", "correct-horse-battery", confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def test_one_question_a_day_the_same_for_everybody():
    conn, _ids = _db()
    hist = _hist()
    d = _slate(("BUF", "KC"), ("LAR", "CIN"))          # no logs for BUF or KC: passed over
    q = TV.daily(conn, hist, DAY, d, now=1000.0)
    assert q and q["league"] == "nfl" and q["game"] == "LAR @ CIN", q
    assert len(q["options"]) == 4 and 0 <= q["answer"] < 4 and q["text"].startswith("Who "), q
    # Kept for the day, whatever the scoreboards say after.
    assert TV.daily(conn, hist, DAY, _slate(), now=2000.0) == q
    assert TV.daily(conn, hist, "2026-10-29", _slate(), now=90000.0) is None, "no game, no question"
    st = TV.daily_state(conn, hist, None, DAY, d)
    assert st["q"]["text"] == q["text"] and "answer" not in st["q"] and "split" not in st["q"], st
    assert st["signed_in"] is False and st["day"] == DAY


def test_one_answer_an_account_and_the_split_after():
    conn, (me, sam) = _db()
    hist = _hist()
    d = _slate(("LAR", "CIN"))
    q = TV.daily(conn, hist, DAY, d)
    wrong = (q["answer"] + 1) % 4
    assert TV.daily_answer(conn, hist, me, DAY, 7, d)[0] == 400
    assert TV.daily_answer(conn, hist, me, DAY, "x", d)[0] == 400
    code, out = TV.daily_answer(conn, hist, me, DAY, q["answer"], d)
    assert code == 200 and out["mine"] == out["answer"] == q["answer"] and out["n"] == 1, out
    assert out["why"] and out["game"] == "LAR @ CIN"
    assert TV.daily_answer(conn, hist, me, DAY, wrong, d)[0] == 409, "once a day"
    code, out = TV.daily_answer(conn, hist, sam, DAY, wrong, d)
    assert code == 200 and out["n"] == 2 and out["split"][q["answer"]] == 1 and out["split"][wrong] == 1, out
    assert TV.daily_state(conn, hist, me, DAY, d)["q"]["mine"] == q["answer"]
    assert TV.daily_answer(conn, hist, me, "2026-11-01", 0, _slate())[0] == 404


def test_right_pays_ten_once_as_itself():
    conn, (me, sam) = _db()
    hist = _hist()
    d = _slate(("LAR", "CIN"))
    q = TV.daily(conn, hist, DAY, d)
    TV.daily_answer(conn, hist, me, DAY, q["answer"], d)
    TV.daily_answer(conn, hist, sam, DAY, (q["answer"] + 1) % 4, d)
    got = K.on_daily(conn, me, DAY, True)
    assert got and got["got"] == 10 and got["why"] == "Today's question right", got
    assert K.on_daily(conn, me, DAY, True) is None, "once a day"
    assert K.on_daily(conn, sam, DAY, False) is None
    K.sync_user(conn, me)
    K.sync_user(conn, sam)
    rows = conn.execute("SELECT user_id, kind, ref, pts FROM karma_events WHERE kind IN ('daily_q', 'trivia')").fetchall()
    assert [tuple(r) for r in rows] == [(me, "daily_q", DAY, 10)], rows
    assert K.badge_counts(conn, me)["trivia"] == 1, "it counts for Trivia head"
    assert K._quest_count(conn, me, "trivia", K.day_of(time.time())) == 1, "the day's trivia quest counts it"
    assert "daily_q" in K.RULES and K.RULES["daily_q"][0] == 10


def test_the_route_the_card_and_the_policy():
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert 'if path == "daily":\n            return self._trivia_daily(body)' in srv
    i = srv.index("def _trivia_daily(")
    body = srv[i:srv.index("\n    def ", i + 10)]
    assert 'K.on_daily(conn, who["id"], day, out.get("mine") == out.get("answer"))' in body
    assert 'b\'{"error":"Make a free account to answer."}\'' in body
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    for want in ("function krDailyHTML(d)", 'data-kr="daily"', 'fetch("/api/trivia/daily"',
                 "function krAskHTML(d)", 'data-kr="daily-open"', "${krAskHTML(d) || krPickemHTML(v.pickem)}", "${krDailyHTML(KR.daily)}",
                 '["day", "daily_q", "quest", "quests_all"]'):
        assert want in kjs, want
    policy = " ".join(Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8").split())
    assert "to today's question, one a day for everybody" in policy


def test_in_a_browser_the_live_tab_asks_in_its_card_and_answers_in_place():
    """The Live tab's karma card (Ethan, 2026-10-28: "fix how cluttered this
    is"): one line until tapped, the question in the card, the result in
    place, and on a later visit nothing (the Karma tab keeps the card)."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    conn, (me, _sam) = _db()
    v = K.me(conn, me)
    q = {"qkey": DAY, "text": "Who leads CIN in receiving yards this season?",
         "options": ["Tee Higgins", "Ja'Marr Chase", "Mike Gesicki", "Andrei Iosivas"], "mine": None, "open": True,
         "day": DAY, "league": "nfl", "game": "LAR @ CIN"}
    done = dict(q, mine=1, answer=1, why="Ja'Marr Chase: 600 receiving yards", split=[3, 9, 1, 0], n=13,
                karma={"got": 10, "why": "Today's question right", "total": v["points"] + 10, "level": v["level"], "up": False})
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    posted = []

    def daily(route):
        if route.request.method == "POST":
            posted.append(json.loads(route.request.post_data or "{}"))
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(done))
        return route.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"signed_in": True, "day": DAY, "q": q}))

    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/**", ful(json.dumps({"posts": []})))
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/trivia/daily*", daily)
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     f"localStorage.setItem('qb_kr_level','{v['level']}');}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(3500)
                got["ask"] = page.evaluate("(document.querySelector('.kr-live .kr-ask') || {}).textContent || ''")
                got["closed"] = page.evaluate("document.querySelectorAll('.kr-strip-host [data-kr=daily]').length")
                page.click(".kr-live .kr-ask")
                page.wait_for_timeout(300)
                got["q"] = page.evaluate("(document.querySelector('.kr-live .kr-daily-q') || {}).textContent || ''")
                got["opts"] = page.evaluate("document.querySelectorAll('.kr-live [data-kr=daily]').length")
                page.click('.kr-live [data-kr="daily"][data-v="1"]')
                page.wait_for_timeout(700)
                got["result"] = page.evaluate("(document.querySelector('.kr-live .kr-daily') || {}).textContent || ''")
                got["note"] = page.evaluate("[...document.querySelectorAll('.kr-note')].map((n) => n.textContent).join('|')")
                got["later"] = page.evaluate("""(() => { KR.dailyJust = 0; krStripDraw(document.querySelector('.kr-strip-host'));
                    return !!document.querySelector('.kr-strip-host .kr-daily, .kr-strip-host .kr-ask'); })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert "Today's question" in got["ask"] and "Answer" in got["ask"] and got["closed"] == 0, \
        "one line in the card until it is tapped"
    assert got["q"] == q["text"] and got["opts"] == 4, got
    assert posted == [{"pick": 1}], posted
    assert "Right · +10" in got["result"] and "69%" in got["result"] and "Ja'Marr Chase: 600 receiving yards" in got["result"], got
    assert "Today's question right" in got["note"], got
    assert got["later"] is False, "answered, a later visit leaves it to the Karma tab"


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
