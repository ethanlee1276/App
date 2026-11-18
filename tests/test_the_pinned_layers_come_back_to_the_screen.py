"""The pinned layers come back to the screen on an iPhone (web/js/boot.js, THE
PINNED LAYERS COME BACK TO THE SCREEN; web/js/chat.js chatLetGo).

Ethan, 2026-11-15, their open iPhone Duo on NE @ DET's game page with the game
chat bar circled halfway up the screen, over "Where the money is going":
"fix how this game chat bar gets stuck on the middle of the screen". Every
pinned layer had moved as one: the top bar off the top, the sidebar's dots
and the chat bar about 500 points up. A minute later, further down the
page, all three were back. An iPhone draws its pinned layers against a
viewport it can leave behind when a keyboard goes, and a field taken out of
the page while it has the keyboard tells nobody (no focusout): the game chat
closed, or redrew its box after a send, with the box in focus, so nothing
put the layers back. What these hold:

  * the chat lets go of its box before it closes the sheet, resets the
    room or redraws the box after a send, so the focusout that settles the
    page comes;
  * the net under every such case: with no field up and no pinch zoom, a
    page still marked as typing, or a screen (window.visualViewport)
    standing away from the page, is settled: moved a pixel and back a frame
    later, at most once in 600ms;
  * a field that is up, or a pinch zoom, is left alone; nothing changes on
    an Android phone;
  * the chat bar steps aside while a field is up, as the tab bar does.

Run directly: `python3 tests/test_the_pinned_layers_come_back_to_the_screen.py`
(the browser half: `QB_BROWSER_TESTS=1`, with Playwright).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
READ = lambda *p: (ROOT / Path(*p)).read_text(encoding="utf-8")  # noqa: E731
BOOT = READ("web", "js", "boot.js")
CHAT = READ("web", "js", "chat.js")
CHAT_CSS = READ("web", "css", "chat.css")


def _block():
    i = BOOT.index("THE PINNED LAYERS COME BACK TO THE SCREEN")
    return BOOT[i:BOOT.index("} catch (e) {}", i)]


def test_the_page_is_settled_by_one_helper_a_frame_apart_and_never_chasing_itself():
    b = _block()
    assert "var QB_SETTLE = function () {};" in b, "a no-op anywhere it is not needed"
    assert "if (Date.now() - last < 600) return;" in b
    assert 'scrollTo({ top: y ? y - 1 : 1, behavior: "instant" });' in b
    assert 'requestAnimationFrame(function () { scrollTo({ top: y, behavior: "instant" }); });' in b
    # The field letting go goes through it, not a nudge of its own.
    assert b.count("scrollTo(") == 2 and "root.classList.remove(\"field-up\");\n        QB_SETTLE();" in b


def test_the_screens_own_viewport_is_the_net():
    b = _block()
    assert "if (!iphone && !/iPad/.test(ua) && !(/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return;" in b
    # Every move checks, and reads the hold (test_the_bar_stays_on_the_screens_foot).
    assert "function moved() { check(); soon(); }" in b
    for want in ('vv.addEventListener("resize", moved);', 'vv.addEventListener("scroll", moved);',
                 'addEventListener("scroll", moved, { passive: true });', 'addEventListener("pageshow", moved);',
                 'document.addEventListener("visibilitychange"'):
        assert want in b, want
    assert "if (field(document.activeElement) || Math.abs(vv.scale - 1) > 0.01) return;" in b, \
        "a field up, or a pinch zoom, moves the screen over the page on purpose"
    assert "if (stale || (Math.abs(vv.offsetTop) >= 1 && innerHeight - vv.height < 40)) QB_SETTLE();" in b, \
        "a screen still short by a keyboard is held to the screen, not nudged: the nudge cannot clear it"


def test_the_chat_lets_go_of_its_box_before_it_goes():
    i = CHAT.index("function chatLetGo(el) {")
    body = CHAT[i:CHAT.index("\n}\n", i)]
    assert "el.contains(a)" in body and "a.blur()" in body
    for fn in ("function chatReset() {", "function chatClose() {"):
        j = CHAT.index(fn)
        f = CHAT[j:CHAT.index("\n}\n", j)]
        assert f.index("chatLetGo(s);") < f.index("if (s) s.remove();"), fn
    j = CHAT.index("async function chatSend(form) {")
    f = CHAT[j:CHAT.index("\n}\n", j)]
    # A send keeps its box unless a chip above it has to go (2026-11-18, the keyboard stays up);
    # whenever the box is drawn again, it lets go first.
    assert f.count("chatLetGo(form);\n") == 2, "after a send that clears a chip, and after a failed one"
    for at in [k for k in range(len(f)) if f.startswith("chatLetGo(form);", k)]:
        assert f[at + len("chatLetGo(form);"):].lstrip().startswith("chatDrawFoot();"), "right before the redraw"


def test_the_chat_bar_steps_aside_while_a_field_is_up():
    assert "html.field-up .gch-fab { display: none; }" in CHAT_CSS


# --- in a browser ----------------------------------------------------------------------
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 27_1 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/27.1 Mobile/15E148 Safari/604.1")
ANDROID_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Mobile Safari/537.36")
#: The screen's viewport, held by the test: an EventTarget with the fields an
#: iPhone's has, and every scrollTo the page makes, written down. And an
#: iPhone's silence: Chromium fires focusout for a field taken out of the page
#: while it has focus, Safari fires none, so the one fired inside a remove()
#: is swallowed before the page hears it. A box that lets go first is heard.
FAKE_SCREEN = """(() => {
  const vv = new EventTarget();
  Object.assign(vv, { offsetTop: 0, offsetLeft: 0, scale: 1, width: innerWidth, height: innerHeight });
  Object.defineProperty(window, 'visualViewport', { configurable: true, get: () => vv });
  window.__vv = vv;
  window.__moves = [];
  const real = window.scrollTo.bind(window);
  window.scrollTo = function (a, b) { window.__moves.push(typeof a === 'object' ? a.top : b); return real(a, b); };
  window.__lets = 0;
  let removing = false;
  const remove = Element.prototype.remove;
  Element.prototype.remove = function () { removing = true; try { return remove.apply(this, arguments); } finally { removing = false; } };
  document.addEventListener('focusout', (e) => {
    if (removing) { e.stopImmediatePropagation(); return; }
    if (e.target.classList && e.target.classList.contains('gch-input')) window.__lets++;
  }, true);
})();"""
TALL = """() => {
  const d = document.createElement('div'); d.style.height = '4000px'; d.id = 't-tall';
  d.innerHTML = '<input id="t-txt" type="text">';
  document.body.append(d);
  window.scrollTo(0, 400);
}"""


def _ctx(pw, ua, w, h):
    kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists("/opt/pw-browsers/chromium"):
        kw["executable_path"] = "/opt/pw-browsers/chromium"
    browser = pw.chromium.launch(**kw)
    ctx = browser.new_context(viewport={"width": w, "height": h}, screen={"width": w, "height": h},
                              user_agent=ua, is_mobile=True, has_touch=True, service_workers="block")
    return browser, ctx


def _screen(ua: str) -> dict:
    from playwright.sync_api import sync_playwright
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "name": "Ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, out = [], {}
    try:
        with sync_playwright() as pw:
            browser, ctx = _ctx(pw, ua, 382, 678)
            try:
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                                     "localStorage.setItem('qb.tour','done');localStorage.setItem('qb.a2hs','off');}catch(e){}")
                page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });")
                page.add_init_script(FAKE_SCREEN)
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                page.wait_for_selector(".tabbar", timeout=15000)
                page.wait_for_timeout(800)
                page.evaluate(TALL)
                page.wait_for_timeout(900)
                out["y"] = page.evaluate("() => scrollY")

                def step(js, wait=450):
                    y0 = page.evaluate("() => { window.__moves = []; return scrollY; }")
                    page.evaluate(js)
                    page.wait_for_timeout(wait)
                    return page.evaluate("() => ({ moves: window.__moves.slice(), y: scrollY,"
                                         " up: document.documentElement.classList.contains('field-up') })") | {"y0": y0}
                stand = "() => { __vv.offsetTop = 500; __vv.dispatchEvent(new Event('scroll')); }"
                out["away"] = step(stand)
                out["again_at_once"] = step(stand, 300)
                page.wait_for_timeout(700)
                out["again_later"] = step(stand)
                page.wait_for_timeout(700)
                out["zoomed"] = step("() => { __vv.scale = 1.6; __vv.offsetTop = 300; __vv.dispatchEvent(new Event('scroll')); }")
                page.evaluate("() => { __vv.scale = 1; __vv.offsetTop = 0; }")
                page.wait_for_timeout(700)
                out["typing"] = step("() => { document.getElementById('t-txt').focus({ preventScroll: true }); __vv.offsetTop = 300;"
                                     " __vv.dispatchEvent(new Event('resize')); }")
                page.evaluate("() => { __vv.offsetTop = 0; }")
                page.wait_for_timeout(700)
                # The box taken out while it has the keyboard, then the keyboard
                # going: whichever way the browser tells it, the page settles.
                out["taken_out"] = step("() => { document.getElementById('t-txt').remove(); __vv.height += 300;"
                                        " __vv.dispatchEvent(new Event('resize')); }", 900)
                page.wait_for_timeout(700)
                out["front_again"] = step("() => { __vv.offsetTop = 220; window.dispatchEvent(new Event('pageshow')); }")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    return out


def _skip():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return True
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return True
    return False


def test_in_a_browser_the_screen_standing_away_is_settled_and_nothing_else_is():
    if _skip():
        return
    got = _screen(IPHONE_UA)
    assert got["y"] >= 300, got

    def settled(k):
        # A pixel and back to where it stood (from the very top, down a pixel).
        y = got[k]["y0"]
        return got[k]["moves"] == [y - 1 if y else 1, y]
    assert settled("away"), f"a pixel and back, a frame apart: {got}"
    assert got["again_at_once"]["moves"] == [], f"never twice inside 600ms: {got}"
    assert settled("again_later"), got
    assert got["zoomed"]["moves"] == [], f"a pinch zoom is the reader's: {got}"
    assert got["typing"]["moves"] == [] and got["typing"]["up"], f"a field up is the bar and the picker's: {got}"
    assert settled("taken_out") and not got["taken_out"]["up"], \
        f"the box gone with the keyboard: the page settles and stops being marked as typing: {got}"
    assert settled("front_again"), got
    other = _screen(ANDROID_UA)
    assert all(not other[k]["moves"] for k in ("away", "again_later", "front_again")), f"an Android phone: {other}"


def _game(eid):
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    plays = [{"kind": "football", "id": f"p{i}", "period": 3, "clock": f"{9 - i}:10", "team": "CIN" if i % 2 else "PIT",
              "event": "Rush", "yards": 4, "scoring": False, "away_score": 14, "home_score": 10,
              "players": ["Joe Burrow"], "rating": 2.1} for i in range(5)]
    return {"league": "nfl", "event_id": eid, "generated_at": iso, "home": "CIN", "away": "PIT",
            "home_name": "Cincinnati Bengals", "away_name": "Pittsburgh Steelers",
            "live": {"state": "live", "home_score": 10, "away_score": 14, "period": 3, "clock": "9:00",
                     "detail": "3rd 9:00"},
            "drives": [{"id": "d1", "team": "CIN", "result": "Touchdown", "plays": plays}], "plays": plays,
            "drive": {"team": "PIT", "plays": 1, "yards": 5}}


def test_in_a_browser_closing_the_chat_with_its_box_in_focus_settles_the_page():
    """The flow behind their screenshot: the chat open, its box in focus (the
    keyboard up), the chat closed. The box lets go first, so the page stops
    being marked as typing and is settled, and the chat bar is back."""
    if _skip():
        return
    from playwright.sync_api import sync_playwright
    import rendercheck
    eid = "990079"
    pbp = ROOT / "web" / "data" / "pbp"
    made = not pbp.is_dir()
    pbp.mkdir(parents=True, exist_ok=True)
    path = pbp / f"nfl_{eid}.json"
    path.write_text(json.dumps(_game(eid)))
    now = time.time()
    msgs = [{"id": 100 + i, "at": now - (4 - i) * 40, "body": f"message {i}", "by": {"handle": f"fan{i}", "color": i},
             "own": False, "reacts": {}, "mine": ""} for i in range(4)]
    room = json.dumps({"room": f"nfl_{eid}", "t": now, "messages": msgs, "older": False, "reacts": {}, "plays": {},
                       "threads": {}, "mine_plays": {}, "votes": {"home": 3, "away": 2, "mine": "", "open": True},
                       "here": 12, "me": {"signed_in": True, "handle": "fan0"}})
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": True, "plans": []}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            browser, ctx = _ctx(pw, IPHONE_UA, 390, 844)
            try:
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/chat/room*", ful(room))
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/chat/ticket*", ful(json.dumps({"legs": []})))
                page.route("**/api/callit/**", ful(json.dumps({"open": None, "kind": "football", "board": []})))
                page.route(f"**/data/pbp/nfl_{eid}*", ful(json.dumps(_game(eid))))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb_chat_rules_v1','1');}catch(e){}")
                page.add_init_script(FAKE_SCREEN)
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/{eid}", wait_until="load")
                page.wait_for_selector(".gch-entry", timeout=15000)
                page.wait_for_timeout(600)
                page.evaluate("(() => { const c = document.querySelector('.gch-entry'); c.scrollIntoView({block: 'center'}); c.click(); })()")
                page.wait_for_selector("#gch-sheet .gch-input", timeout=5000)
                page.focus("#gch-sheet .gch-input")
                page.wait_for_timeout(150)
                got["typing"] = page.evaluate("() => document.documentElement.classList.contains('field-up')")
                page.evaluate("() => { window.__moves = []; window.__lets = 0; }")
                page.evaluate("document.querySelector('[data-gch=close]').click()")
                page.wait_for_timeout(900)
                got["after"] = page.evaluate("""() => { const f = document.getElementById('gch-fab');
                  return { lets: window.__lets, moves: window.__moves.length,
                           up: document.documentElement.classList.contains('field-up'),
                           sheet: !!document.getElementById('gch-sheet'), bar: !!(f && f.isConnected && !f.hidden) }; }""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
        path.unlink()
        if made:
            try:
                pbp.rmdir()
            except OSError:
                pass
    assert not errs, errs[:3]
    assert got["typing"], f"the box in focus marks the page as typing: {got}"
    a = got["after"]
    assert a["lets"] == 1, f"the box let go before the sheet went: {got}"
    assert not a["up"] and a["moves"] == 2 and not a["sheet"] and a["bar"], got


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
