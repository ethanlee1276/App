"""The top of the Live tab, uncluttered (web/js/app.js renderLiveBoard,
web/js/karma.js krStripHTML; Ethan, 2026-10-28, the top of Live circled:
"And fix how cluttered this is").

It stacked the page's name and a second line under it, the karma card with
three quest chips, today's question as its own row run straight into the
"No games live" card, that card's one long sentence, and two doors that
repeat the tab bar. Now:

  * the page's name alone, then "No games live" over one line of what is
    next (the next start, the bets queued), said first;
  * one karma card under it: the level and the way to the next, the day's
    quests as a dot each (a new account's first days: its next first and
    how many of six), and today's question as one line in the card until
    it is tapped (tests/test_todays_question.py has the rest of its life);
  * no doors to Picks and the Record (the tab bar and the sidebar are
    those), and the cards 12px apart, never touching.

Run directly: `python3 tests/test_the_live_tab_is_one_calm_block.py`
"""
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))


def READ(*parts):
    return Path(ROOT, *parts).read_text(encoding="utf-8")


KJS, KCSS = READ("web", "js", "karma.js"), READ("web", "css", "karma.css")


def test_one_card_the_quests_as_dots_and_the_question_as_a_line():
    fn = KJS[KJS.index("function krStripHTML(v, d)"):KJS.index("function krStripDraw(host)")]
    for want in ('<div class="kr-live"><button type="button" class="kr-strip" data-kr="open"',
                 '<span class="kr-dots" role="img" aria-label="Today\'s quests: ${qs.filter((x) => x.done).length} of ${qs.length} done"',
                 "qs.map((x) => `<i${x.done ? ' class=\"on\"' : \"\"}></i>`)",
                 '<span class="kr-of">${Number(camp.done)}/${Number(camp.of)}</span>',
                 '<span class="kr-strip-sub kr-next">Getting started: ${krEsc(next.text)} · +${Number(camp.pts)}</span>',
                 "${krAskHTML(d)}</div>${krFriendsHTML(v)}"):
        assert want in fn, want
    for gone in ('<span class="kr-q${', '<span class="kr-qs">', "kr-camp-h"):
        assert gone not in KJS, ("the chips and the shouted header are gone", gone)
    ask = KJS[KJS.index("function krAskHTML(d)"):KJS.index("function krStripHTML(v, d)")]
    assert "Date.now() - KR.dailyJust < KR_JUST_MS ? krDailyHTML(d) : \"\"" in ask, "answered: in place this visit, then gone"
    assert "if (KR.dailyOpen) return krDailyHTML(d);" in ask and 'data-kr="daily-open"' in ask
    assert 'if (act === "daily-open") { KR.dailyOpen = true; krStripDraw(b.closest(".kr-strip-host")); return; }' in KJS
    for rule in (".kr-live { margin: 0 0 12px;", ".kr-dots i.on {", ".kr-ask {", ".kr-live .kr-daily {",
                 "#live-board:has(.lb-grid, .pf-host) .kr-ask { display: none; }"):   # with games on, the games lead
        assert rule in KCSS, rule
    for gone in (".kr-qs {", ".kr-q {", ".kr-camp-h {", ".kr-daily.folded {", ".kr-daily-n {"):
        assert gone not in KCSS, gone


# --- in a phone browser ----------------------------------------------------------
LAYOUT = """(() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null;
                     const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, text: e.textContent.trim() }; };
  const title = document.querySelector('#live-board .section-title');
  return { title: title ? title.textContent.trim() : '', sub: !!document.querySelector('#live-board .section-title .sub'),
           doors: !!document.querySelector('#live-board .es-doors'), rest: r('#live-board .lv-rest'),
           card: r('#live-board .kr-live'), dots: [...document.querySelectorAll('.kr-dots i')].map((i) => i.className),
           label: (document.querySelector('.kr-dots') || { getAttribute: () => '' }).getAttribute('aria-label'),
           of: r('.kr-of'), next: r('.kr-next'), ask: r('.kr-live .kr-ask') };
})()"""


def test_in_a_phone_browser_the_live_tab_says_it_once():
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
    from engine import karma as K
    conn, (me, _sam) = TQ._db()
    v = dict(K.me(conn, me), camp=None, quests=[
        {"key": "watch", "text": "Watch 10 minutes of two live games", "n": 0, "goal": 2, "done": False},
        {"key": "call", "text": "Call one play", "n": 1, "goal": 1, "done": True},
        {"key": "react", "text": "React to a message", "n": 0, "goal": 1, "done": False}])
    camp = dict(v, camp={"of": 6, "done": 2, "pts": 20, "bonus": 50,
                         "steps": [{"key": "name", "text": "Pick a username", "done": True},
                                   {"key": "team", "text": "Follow a team", "done": True},
                                   {"key": "watch", "text": "Watch a live game", "done": False}]})
    q = {"qkey": TQ.DAY, "text": "Who leads CIN in receiving yards this season?",
         "options": ["Tee Higgins", "Ja'Marr Chase", "Mike Gesicki", "Andrei Iosivas"], "mine": None, "open": True,
         "day": TQ.DAY, "league": "nfl", "game": "LAR @ CIN"}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for key, me_v in (("quests", v), ("camp", camp)):
                    ctx = browser.new_context(viewport={"width": 440, "height": 956}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                    page.route("**/api/account/me*", ful(json.dumps(who)))
                    page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                    page.route("**/api/karma/me*", ful(json.dumps(me_v)))
                    page.route("**/api/trivia/daily*", ful(json.dumps({"signed_in": True, "day": TQ.DAY, "q": q})))
                    page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                         "localStorage.setItem('qb_new_2026_10_28b','1');"
                                         f"localStorage.setItem('qb_kr_level','{me_v['level']}');}}catch(e){{}}")
                    page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                    page.wait_for_timeout(3500)
                    got[key] = page.evaluate(LAYOUT)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    g = got["quests"]
    assert g["title"] == "Live now" and not g["sub"] and not g["doors"], g
    assert g["rest"] and g["rest"]["text"].startswith("No games live"), g
    assert g["card"] and g["card"]["top"] >= g["rest"]["bottom"] + 12, "said first, the card under it, never touching"
    assert g["dots"] == ["", "on", ""] and g["label"] == "Today's quests: 1 of 3 done", g
    assert g["ask"] and "Today's question" in g["ask"]["text"] and g["ask"]["top"] < g["card"]["bottom"], "in the card"
    c = got["camp"]
    assert c["of"] and c["of"]["text"] == "2/6" and not c["dots"], c
    assert c["next"] and c["next"]["text"] == "Getting started: Watch a live game · +20", c


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
