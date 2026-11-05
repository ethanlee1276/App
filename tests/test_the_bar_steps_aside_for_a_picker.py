"""The tab bar steps aside while a picker or a keyboard is up, on an iPhone
(web/js/boot.js and web/css/styles.css, "THE BAR AND THE PICKER").

Ethan, 2026-11-05, his iPhone Duo at 7:11 with the tab bar circled halfway up
the Home page, right under "Sort: Start Time": "the menu bar is moving around
fix that". The sort is a <select>; an iPhone opens its wheel, like its
keyboard, from the foot of the screen without shrinking the page, and the
fixed bar rode up over the page with it and could stay there after. What
these hold:

  * on an iPhone, a select, a text box or a text area taking focus takes the
    bar and the pill above it away (html.field-up), in every way the bar is
    drawn on a phone;
  * when the field lets go and no other field has taken it, they come back,
    at the screen's foot, after the wheel or the keyboard has gone;
  * moving from one field to the next keeps them away;
  * a button or a checkbox is no field, and nothing changes on any phone but
    an iPhone.

Run directly: `python3 tests/test_the_bar_steps_aside_for_a_picker.py`
(the browser half: `QB_BROWSER_TESTS=1`, with Playwright).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
READ = lambda *p: (ROOT / Path(*p)).read_text(encoding="utf-8")  # noqa: E731
BOOT = READ("web", "js", "boot.js")
CSS = READ("web", "css", "styles.css")


def test_the_iphone_alone_listens_for_a_field():
    i = BOOT.index("THE BAR AND THE PICKER")
    block = BOOT[i:BOOT.index("} catch (e) {}", i)]
    assert 'if (!/iPhone|iPod/.test(navigator.userAgent || "")) return;' in block
    assert 'document.addEventListener("focusin"' in block and 'document.addEventListener("focusout"' in block
    assert 'root.classList.add("field-up")' in block and 'root.classList.remove("field-up")' in block
    assert "if (field(document.activeElement)) return;" in block, "a field taking over keeps the bar away"
    assert 'behavior: "instant"' in block, "the page's smooth scrolling never glides the nudge"


def test_the_bar_and_the_pill_step_aside_on_a_phone_alone():
    rule = "html.field-up .tabbar, html.field-up .riding-tray { display: none !important; }"
    assert rule in CSS
    at = CSS.index(rule)
    assert CSS.rfind("@media (max-width: 760px) {", 0, at) > CSS.rfind("}\n}", 0, at), "inside a phone's width"
    assert at > CSS.index("html.side-rail .tabbar, html.side-rail.store-ios .tabbar"), \
        "after the strip's own rules, so the bar beside the clock steps aside too"


# --- in a browser ----------------------------------------------------------------------
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 27_1 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/27.1 Mobile/15E148 Safari/604.1")
ANDROID_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Mobile Safari/537.36")
W, H = 382, 678
STATE = """() => {
  const tab = document.querySelector('.tabbar');
  const r = tab.getBoundingClientRect();
  return { up: document.documentElement.classList.contains('field-up'),
           shown: getComputedStyle(tab).display !== 'none',
           foot: Math.round(innerHeight - r.bottom) };
}"""
FIELDS = """() => {
  const box = document.createElement('div');
  box.style.cssText = 'position: relative; padding: 12px;';
  box.innerHTML = '<select id="t-sel"><option>Sort: Start Time</option><option>Sort: Most Picks</option></select>'
    + '<input id="t-txt" type="text"><input id="t-chk" type="checkbox"><button id="t-btn">x</button>';
  document.querySelector('main').prepend(box);
}"""


def _run(ua: str) -> dict:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "name": "Ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, out = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": W, "height": H}, screen={"width": W, "height": H},
                                          user_agent=ua, is_mobile=True, has_touch=True, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                                     "localStorage.setItem('qb.tour','done');localStorage.setItem('qb.a2hs','off');}catch(e){}")
                page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });")
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                page.wait_for_selector(".tabbar", timeout=15000)
                page.wait_for_timeout(800)
                page.evaluate(FIELDS)
                out["before"] = page.evaluate(STATE)
                page.focus("#t-sel")
                page.wait_for_timeout(50)
                out["picker"] = page.evaluate(STATE)
                page.focus("#t-txt")
                page.wait_for_timeout(500)
                out["next_field"] = page.evaluate(STATE)
                page.evaluate("document.activeElement.blur()")
                page.wait_for_timeout(100)
                out["just_after"] = page.evaluate(STATE)
                page.wait_for_function("!document.documentElement.classList.contains('field-up')", timeout=3000)
                out["after"] = page.evaluate(STATE)
                for sel in ("#t-chk", "#t-btn"):
                    page.focus(sel)
                    page.wait_for_timeout(50)
                    out[sel] = page.evaluate(STATE)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    return out


def test_on_an_iphone_the_bar_steps_aside_and_comes_back_at_the_foot():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got = _run(IPHONE_UA)
    assert got["before"]["shown"] and not got["before"]["up"], got
    assert got["picker"]["up"] and not got["picker"]["shown"], f"the wheel is up: the bar steps aside: {got}"
    assert got["next_field"]["up"] and not got["next_field"]["shown"], f"one field to the next keeps it away: {got}"
    assert got["just_after"]["up"], f"it waits for the wheel or the keyboard to go: {got}"
    assert got["after"]["shown"] and not got["after"]["up"], got
    assert 0 <= got["after"]["foot"] <= 30, f"back at the screen's foot: {got}"
    assert got["after"]["foot"] == got["before"]["foot"], got
    for sel in ("#t-chk", "#t-btn"):
        assert got[sel]["shown"] and not got[sel]["up"], f"{sel} is no field: {got}"
    other = _run(ANDROID_UA)
    assert other["picker"]["shown"] and not other["picker"]["up"], f"an Android phone keeps its bar: {other}"


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
