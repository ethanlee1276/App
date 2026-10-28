"""What's new (js/karma.js; Ethan, 2026-10-28: "we don't want the site to
feel overwhelmed with a bunch of random-ass features, but we just want it
to feel complete").

A feature nobody finds is clutter. Every app's release notes, inside the
app: once, on the Live tab under the karma strip, to an account past its
getting-started list (a new one has that list instead), what the last
round added, a line each; "Got it" puts it away on this device. What this
file pins:

  * the card is the strip's, after it, and only without the getting-started
    list; a device that cannot remember the "Got it" is never shown it;
  * every line names something on the site, briefly;
  * in a browser: shown, put away, and still away after a reload.

Run directly: `python3 tests/test_whats_new.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

KJS = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")


def _body(name):
    i = KJS.index(f"function {name}(")
    return KJS[i:KJS.index("\n}\n", i)]


def test_the_card_rides_the_strip_once_and_never_for_a_new_account():
    assert "krStripHTML(v) + krNewHTML(v) + krDailyHTML(KR.daily, true)" in KJS
    body = _body("krNewHTML")
    assert 'if (!v || v.camp) return "";' in body, "a new account has its getting-started list instead"
    assert 'try { if (localStorage.getItem(KR_NEW_KEY)) return ""; } catch (e) { return ""; }' in body, \
        "a device that cannot remember the Got it is never shown a card it cannot put away"
    assert 'data-kr="new-ok"' in body and 'if (act === "new-ok") {' in KJS


def test_every_line_is_short_and_names_something_real():
    block = KJS[KJS.index("const KR_NEW = ["):KJS.index("]];", KJS.index("const KR_NEW = ["))]
    rows = re.findall(r'\["([^"]+)", "([^"]+)", "([^"]+)"\]?', block)
    assert 3 <= len(rows) <= 6, rows
    for icon, title, words in rows:
        assert len(title) <= 24 and len(words) <= 100, (title, words)
    titles = [t for _i, t, _w in rows]
    assert "Today's question" in titles and "Player of the game" in titles and "Remind me" in titles


def test_in_a_browser_it_shows_goes_away_and_stays_away():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    v = {"level": 6, "tier": "Starter", "cls": "t2", "points": 1108, "to": 1350, "progress": .4, "streak": {"now": 3},
         "quests": [], "badges": [], "camp": None, "friends": [], "pins": [], "week": {"rows": []}}
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
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/**", ful(json.dumps({"posts": []})))
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     "localStorage.setItem('qb_kr_level','6');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(3500)
                got["shown"] = page.evaluate("(document.querySelector('.kr-strip-host .kr-new') || {}).textContent || ''")
                page.click('.kr-strip-host [data-kr="new-ok"]')
                page.wait_for_timeout(300)
                got["gone"] = page.evaluate("!document.querySelector('.kr-new')")
                page.reload(wait_until="load")
                page.wait_for_timeout(3500)
                got["strip"] = page.evaluate("!!document.querySelector('.kr-strip-host .kr-strip')")
                got["still_gone"] = page.evaluate("!document.querySelector('.kr-new')")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert "What's new" in got["shown"] and "Today's question" in got["shown"], got
    assert got["gone"] and got["strip"] and got["still_gone"], got


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
