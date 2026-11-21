"""Share my level (js/karma.js; Ethan, 2026-10-28: "keep building … keep
inventing … keep user retainment").

Duolingo's streak card and Strava's share are how those apps get passed
around: a picture of the level, the karma, the days in a row and the best
badges, on the site's own card (app.js cardStage and exportCard, 1200x630,
the size every chat app crops to), from a "Share my level" button on the
Karma tab and "Share" on the level-up card. What this file pins:

  * the card is drawn with the site's card kit and exported by its one
    export path (the share sheet, or a download);
  * every tier has its colour on the card, the same tiers the page knows;
  * the badges on it are the earned ones, pinned first, four at most;
  * nothing about a bet, a pick or a price is drawn on it;
  * in a browser: the button draws a 1200x630 card and hands it over.

Run directly: `python3 tests/test_share_my_level.py`
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

KJS = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")


def _body(name):
    i = KJS.index(f"function {name}(")
    return KJS[i:KJS.index("\n}\n", i)]


def test_the_card_is_the_sites_own_and_leaves_by_its_one_door():
    draw = _body("krShareCanvas")
    assert "c.width = CARD_W;" in draw and "c.height = CARD_H;" in draw and "cardStage(x);" in draw
    share = _body("krShare")
    assert "exportCard(c, `qellys-level-${Number(v.level) || 1}.png`, done);" in share
    assert 'typeof cardStage !== "function" || typeof exportCard !== "function"' in share, \
        "karma.js loads after app.js; it must not throw if the card kit is missing"
    assert "await krLoad(true);" in share, "the card is drawn from the latest karma, not a stale copy"


def test_every_tier_has_its_colour_on_the_card():
    tiers = re.findall(r'\[\d+, "[^"]+", "(t\d)"\]', KJS[KJS.index("const KR_TIERS"):KJS.index("const KR_UNLOCK")])
    hexes = dict(re.findall(r'(t\d): "(#[0-9A-F]{6})"', KJS[KJS.index("const KR_TIER_HEX"):]
                            .split("\n", 1)[0]))
    assert tiers and sorted(hexes) == sorted(tiers), (tiers, hexes)


def test_the_buttons_are_on_the_tab_and_on_the_level_up():
    assert '<button type="button" class="kr-share" data-kr="share">Share my level</button>' in _body("krPanelHTML")
    assert 'data-kr="share">Share</button>' in _body("krLevelUp")
    assert 'if (act === "share") { krShare(b); return; }' in KJS
    css = Path(ROOT, "web", "css", "karma.css").read_text(encoding="utf-8")
    assert ".kr-share {" in css and ".kr-up-row {" in css


def test_nothing_about_a_bet_is_drawn():
    draw = _body("krShareCanvas").lower()
    for word in ("odds", "pick", "edge", "price", "parlay", "units", "stake"):
        assert word not in draw, word


def test_in_a_browser_the_button_draws_the_card_and_hands_it_over():
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
    from engine import accounts as A
    from engine import karma as K
    from engine import socialfeed as SF
    K._cache.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    K.ensure_tables(conn)
    _, out = A.create_user(conn, "ethan@example.com", "correct-horse-battery", confirmed=True)
    me = out["id"]
    SF.profile_set(conn, me, "ethan", "")
    for i in range(12):
        K.award(conn, me, "call_won", f"g{i}")
    K.award(conn, me, "recruit", "x", pts=600)
    v = K.me(conn, me)
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
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     f"localStorage.setItem('qb_kr_level','{v['level']}');}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(2500)
                page.evaluate("try { sessionStorage.setItem('qb_acct_tab', 'karma'); } catch (e) {}")
                page.goto(f"http://127.0.0.1:{port}/index.html#account", wait_until="load")
                page.wait_for_timeout(3500)
                page.evaluate("() => { window.exportCard = (c, name, done) => { window._shared = [c.width, c.height, name, "
                              "c.toDataURL('image/png').length]; done(); }; }")
                page.click('.kr-panel-host [data-kr="share"]')
                page.wait_for_timeout(800)
                got["shared"] = page.evaluate("window._shared || null")
                got["label"] = page.evaluate("document.querySelector('.kr-panel-host [data-kr=share]').textContent")
                got["order"] = page.evaluate("krShareBadges({pins: ['b'], badges: ["
                                             "{key: 'a', tier: 3, of: 5}, {key: 'b', tier: 1, of: 5}, {key: 'c', tier: 0, of: 5},"
                                             "{key: 'd', tier: 5, of: 5}, {key: 'e', tier: 2, of: 5}, {key: 'f', tier: 1, of: 6}]}"
                                             ").map((b) => b.key)")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert got["shared"] and got["shared"][:3] == [1200, 630, f"qellys-level-{v['level']}.png"], got
    assert got["shared"][3] > 20000, "a drawn card, not a blank one"
    assert got["label"] == "Share my level", "the button comes back once the card is handed over"
    assert got["order"] == ["b", "d", "a", "e"], got["order"]


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
