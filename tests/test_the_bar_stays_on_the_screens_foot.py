"""The tab bar stays on the screen's foot as you scroll (web/js/boot.js and
web/css/styles.css, THE BAR STAYS ON THE SCREEN'S FOOT AS YOU SCROLL).

Ethan, 2026-11-17, two screenshots from their iPhone Duo, the tab bar
circled halfway up the screen over the picks, once beside DraftKings in
Split View and once on its own: "Also fix how this bar will move when I
scroll". The bar was not alone either time: the page's gold light ended in
a straight edge just under it, so every pinned layer stood a keyboard's
height up the screen. An iPhone can go on drawing the page above a keyboard
that has gone (another app's counts: iOS hands every app on the screen the
keyboard's place), and its pinned layers then hold to the foot of that short
screen as the page scrolls down and come back as it scrolls up: the bar
moving as you scroll. A nudge cannot clear a keyboard iOS still believes in.
What these hold:

  * with no field of the page's up and no pinch zoom, how far the screen
    stands from the viewport the layers are pinned to
    (visualViewport.offsetTop) goes to the page as --vv-y with html.vv-held,
    and every layer pinned to the screen (the bar, the pill, the chat's
    button, the toasts, the light, the top bar, the strip under the clock,
    the sheets and dialogs) moves back by it; read again every frame the
    page or the screen moves, and let go the moment it is 0 again;
  * a field that is up (the page's own keyboard) or a pinch zoom lets go at
    once; the installed app only (the Home Screen app, the iOS build), never
    a Safari tab, never an Android phone;
  * the nudge is kept for a screen that stands away on its own, and skipped
    while the screen is still short by a keyboard, where it would only move
    the page under the reader's thumb;
  * nothing a script places against the page under it moves (a chart's tip,
    the scrubber, the Ask room over the keyboard), nor the body.

Run directly: `python3 tests/test_the_bar_stays_on_the_screens_foot.py`
(the browser half: `QB_BROWSER_TESTS=1`, with Playwright).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
READ = lambda *p: (ROOT / Path(*p)).read_text(encoding="utf-8")  # noqa: E731
BOOT = READ("web", "js", "boot.js")
CSS = READ("web", "css", "styles.css")
DETAIL_CSS = READ("web", "css", "detail.css")
ACCOUNT_CSS = READ("web", "css", "account.css")


def _block():
    i = BOOT.index("THE PINNED LAYERS COME BACK TO THE SCREEN")
    return BOOT[i:BOOT.index("} catch (e) {}", i)]


def _rule():
    i = CSS.index("html.vv-held :is(")
    return CSS[i:CSS.index("}", i) + 1]


def test_the_hold_is_read_from_the_screen_and_only_in_the_installed_app():
    b = _block()
    assert "THE BAR STAYS ON THE SCREEN'S FOOT AS YOU SCROLL" in b
    assert 'var app = navigator.standalone === true || /QellysApp\\/[\\d.]+ \\(ios\\)/.test(ua);' in b, \
        "the Home Screen app and the iOS build: a Safari tab's own bars move its viewport on purpose"
    assert ("var dy = field(document.activeElement) || Math.abs(vv.scale - 1) > 0.01 ? 0 : "
            "Math.round(vv.offsetTop);") in b, "a field up or a pinch zoom lets go"
    assert "if (dy === held) return;" in b, "written only when it changes"
    assert "function soon() { if (app && !frame) frame = requestAnimationFrame(hold); }" in b, "once a frame at most"


def test_the_layers_move_inline_and_the_roots_copy_only_once_still():
    """A variable on the page's root restyles every element on the page: 23ms
    a frame on a 6,000-element board against 2 for the layers, measured. The
    layers take the distance inline, found once as the hold begins; the
    root's copy (for a layer drawn later, and the strip under the clock)
    follows 300ms after the screen last moved."""
    b = _block()
    i = b.index("function hold() {")
    h = b[i:b.index("\n    }\n", i)]
    assert "if (!held) layers = document.querySelectorAll(LAYERS);" in h
    assert "layers[i].style.translate = t;" in h and 't = dy ? "0 " + dy + "px" : ""' in h
    assert 'if (!held !== !dy) root.classList.toggle("vv-held", dy !== 0);' in h, "the class only as it starts and ends"
    assert "--vv-y" not in h, "never the root's variable a frame"
    assert "clearTimeout(rest);\n      rest = setTimeout(keep, 300);" in h
    j = b.index("function keep() {")
    k = b[j:b.index("\n    }\n", j)]
    assert "if (kept === held) return;" in k
    assert 'if (held) root.style.setProperty("--vv-y", held + "px");' in k
    assert 'else root.style.removeProperty("--vv-y");' in k


def test_the_script_and_the_stylesheet_move_the_same_layers():
    m = re.search(r'var LAYERS = ((?:"[^"]*"\s*\+?\s*)+);', _block())
    assert m, "LAYERS"
    js = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    js = {s.strip() for s in js.split(",") if s.strip()}
    r = _rule()
    inner = r[r.index(":is(") + 4:r.index("),")]
    css = {re.sub(r'\[id="([\w-]+)"\]', r"#\1", s.strip()) for s in inner.split(",") if s.strip()}
    assert js == css, f"script only: {sorted(js - css)}; stylesheet only: {sorted(css - js)}"


def test_it_is_read_again_whenever_the_page_or_the_screen_moves():
    b = _block()
    assert "function moved() { check(); soon(); }" in b
    for want in ('vv.addEventListener("resize", moved);', 'vv.addEventListener("scroll", moved);',
                 'addEventListener("scroll", moved, { passive: true });', 'addEventListener("pageshow", moved);',
                 'document.addEventListener("visibilitychange", function () { if (!document.hidden) moved(); });',
                 'document.addEventListener("focusin", soon, true);',
                 'document.addEventListener("focusout", soon, true);'):
        assert want in b, want
    # The field's own timer (the bar and the picker) is not the hold's to clear.
    assert 'document.addEventListener("focusin", moved' not in b


def test_no_nudge_while_the_screen_is_short_by_a_keyboard():
    assert "if (stale || (Math.abs(vv.offsetTop) >= 1 && innerHeight - vv.height < 40)) QB_SETTLE();" in _block()


def test_every_layer_pinned_to_the_screen_moves_back_by_it():
    r = _rule()
    assert r.rstrip().endswith("{ translate: 0 var(--vv-y); }"), \
        "the translate property: each layer keeps its own transform (the tuck, the pill's centring, a slide)"
    assert "html.vv-held body::before" in r, "the strip under the clock"
    for sel in (".tabbar", ".riding-tray", ".gch-fab", ".gch-sheet", ".kr-notes", ".tf-toast",
                ".crash-note", '[id="ptr"]', ".ambient", ".amb-club", ".topbar", ".sidebar",
                '[id="scrim"]', ".more-sheet", ".more-scrim", ".betit-sheet", '[id="ffd-overlay"]',
                '[id="pk-overlay"]', '[id="tour-overlay"]', '[id="cc-overlay"]', '[id="gl-overlay"]'):
        assert sel in r, sel
    for sel in (".graph-tip", ".scrub-rail", ".ask-room", ".shelf-head", ".gp-stick", ".rail"):
        assert sel not in r, f"{sel} is placed against the page under it"
    assert not re.search(r"(^|[\s,(])body(\s*[,{)]|\.)", r.replace("body::before", "")), "never the body"
    assert "--vv-y: 0px;" in CSS[:CSS.index("--strip-w: 84px;") + 400], "the root's own default, 0, with the Duo's strip"
    # A room's own layers are the room's to move (tests/test_a_rooms_styles_are_its_own.py):
    # nothing outside the room names them, so they take the root's copy.
    assert "html.vv-held .gp-wash, html.vv-held .pbp-big { translate: 0 var(--vv-y); }" in DETAIL_CSS
    assert "html.vv-held .pw-dock, html.vv-held .fsu-dock { translate: 0 var(--vv-y); }" in ACCOUNT_CSS
    for room in (".gp-wash", ".pbp-big", ".pw-dock", ".fsu-dock"):
        assert room not in r and room not in BOOT, room
    # Not a media query's: an iPad's installed app is held too.
    at = CSS.index(r)
    assert CSS.rfind("@media", 0, at) < CSS.rfind("}\n}", 0, at), "outside every media query"
    # Nothing else sets the property on these layers, so nothing fights it.
    others = [m.start() for m in re.finditer(r"(^|[\s;{])translate:", CSS) if not (at <= m.start() < at + len(r))]
    for o in others:
        head = CSS[CSS.rfind("}", 0, o) + 1:o]
        assert not any(s in head for s in (".tabbar", ".riding-tray", ".ambient", ".topbar")), head


# --- in a browser ----------------------------------------------------------------------
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 27_1 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/27.1 Mobile/15E148 Safari/604.1")
APP_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 27_1 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Mobile/15E148 QellysApp/1.4 (ios)")
ANDROID_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Mobile Safari/537.36")
#: The screen's viewport, held by the test: an EventTarget with an iPhone's
#: fields, and every scrollTo the page makes, written down.
FAKE_SCREEN = """(() => {
  const vv = new EventTarget();
  Object.assign(vv, { offsetTop: 0, offsetLeft: 0, scale: 1, width: innerWidth, height: innerHeight });
  Object.defineProperty(window, 'visualViewport', { configurable: true, get: () => vv });
  window.__vv = vv;
  window.__moves = [];
  const real = window.scrollTo.bind(window);
  window.scrollTo = function (a, b) { window.__moves.push(typeof a === 'object' ? a.top : b); return real(a, b); };
})();"""
TALL = """() => {
  const d = document.createElement('div'); d.style.height = '4000px';
  d.innerHTML = '<input id="t-txt" type="text">';
  document.body.append(d);
  window.scrollTo(0, 400);
}"""
READ_STATE = """() => {
  const cs = (s) => { const el = document.querySelector(s); return el ? getComputedStyle(el).translate : null; };
  const bar = document.querySelector('.tabbar').getBoundingClientRect();
  return { held: document.documentElement.classList.contains('vv-held'),
           y: getComputedStyle(document.documentElement).getPropertyValue('--vv-y').trim(),
           bar: cs('.tabbar'), light: cs('.ambient'), top: cs('.topbar'), body: getComputedStyle(document.body).translate,
           foot: Math.round(innerHeight - bar.bottom), up: document.documentElement.classList.contains('field-up'),
           moves: window.__moves.slice() };
}"""


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


def _screen(ua: str, standalone: bool) -> dict:
    from playwright.sync_api import sync_playwright
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
                ctx = browser.new_context(viewport={"width": 382, "height": 678}, screen={"width": 382, "height": 678},
                                          user_agent=ua, is_mobile=True, has_touch=True, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                                     "localStorage.setItem('qb.tour','done');localStorage.setItem('qb.a2hs','off');}catch(e){}")
                if standalone:
                    page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });")
                page.add_init_script(FAKE_SCREEN)
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                page.wait_for_selector(".tabbar", timeout=15000)
                page.wait_for_timeout(800)
                page.evaluate(TALL)
                page.wait_for_timeout(900)

                def step(js, wait=450):
                    page.evaluate("() => { window.__moves = []; }")
                    page.evaluate(js)
                    page.wait_for_timeout(wait)
                    return page.evaluate(READ_STATE) | {"at": page.evaluate("() => scrollY")}
                out["still"] = step("() => {}")
                # A keyboard gone but still believed in: the screen short by it
                # and standing 300 below the viewport the layers are pinned to.
                out["short"] = step("() => { __vv.offsetTop = 300; __vv.height = innerHeight - 300;"
                                    " __vv.dispatchEvent(new Event('scroll')); }")
                out["scrolled_up"] = step("() => { __vv.offsetTop = 120; __vv.dispatchEvent(new Event('scroll')); }", 120)
                out["still_again"] = step("() => {}", 400)
                out["typing"] = step("() => { document.getElementById('t-txt').focus({ preventScroll: true }); }", 120)
                out["let_go"] = step("() => { document.getElementById('t-txt').blur(); }", 700)
                page.wait_for_timeout(700)
                out["zoomed"] = step("() => { __vv.scale = 1.6; __vv.dispatchEvent(new Event('resize')); }", 120)
                out["back"] = step("() => { __vv.scale = 1; __vv.offsetTop = 0; __vv.height = innerHeight;"
                                   " __vv.dispatchEvent(new Event('scroll')); }")
                page.wait_for_timeout(700)
                # Standing away on its own, the screen the page's full height:
                # held, and the nudge still tried.
                out["away_alone"] = step("() => { __vv.offsetTop = 200; __vv.dispatchEvent(new Event('scroll')); }")
                out["front_again"] = step("() => { __vv.offsetTop = 0; window.dispatchEvent(new Event('pageshow')); }", 120)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    return out


def test_in_a_browser_the_installed_app_holds_its_layers_to_the_screen():
    if _skip():
        return
    got = _screen(IPHONE_UA, True)
    s = got["still"]
    assert not s["held"] and s["y"] == "0px" and s["bar"] == "none" and s["light"] == "none", f"nothing moved: {got}"
    k = got["short"]
    assert k["held"] and k["y"] == "300px", got
    for layer in ("bar", "light", "top"):
        assert k[layer] == "0px 300px", f"the {layer} back on the screen: {got}"
    assert k["body"] == "none", f"never the body: {got}"
    assert k["foot"] == s["foot"] - 300, f"the bar's foot down by the distance exactly: {got}"
    assert k["moves"] == [], f"no nudge while the screen is short by a keyboard: {got}"
    assert got["scrolled_up"]["bar"] == "0px 120px" and got["scrolled_up"]["light"] == "0px 120px", \
        f"the layers follow the screen at once: {got}"
    assert got["scrolled_up"]["y"] == "300px", f"the root's copy waits for the screen to be still: {got}"
    assert got["still_again"]["y"] == "120px" and got["still_again"]["bar"] == "0px 120px", f"then catches up: {got}"
    t = got["typing"]
    assert not t["held"] and t["bar"] == "none" and t["up"], f"the page's own keyboard: let go, the bar aside: {got}"
    g = got["let_go"]
    assert g["held"] and g["y"] == "120px" and not g["up"], f"the field gone: held again: {got}"
    assert not got["zoomed"]["held"], f"a pinch zoom is the reader's: {got}"
    b = got["back"]
    assert not b["held"] and b["y"] == "0px" and b["bar"] == "none" and b["foot"] == s["foot"], f"let go: {got}"
    a = got["away_alone"]
    assert a["held"] and a["y"] == "200px", got
    assert a["moves"] == [a["at"] - 1 if a["at"] else 1, a["at"]], f"the nudge kept for a screen standing away alone: {got}"
    assert not got["front_again"]["held"], got


def test_in_a_browser_the_ios_build_holds_and_a_safari_tab_and_android_do_not():
    if _skip():
        return
    built = _screen(APP_UA, False)
    assert built["short"]["held"] and built["short"]["bar"] == "0px 300px", f"the iOS build: {built}"
    tab = _screen(IPHONE_UA, False)
    assert not any(tab[k]["held"] for k in tab), f"a Safari tab's own bars move its viewport: {tab}"
    assert tab["short"]["bar"] == "none" and tab["short"]["moves"] == [], tab
    other = _screen(ANDROID_UA, True)
    assert not any(other[k]["held"] for k in other) and not other["away_alone"]["moves"], f"an Android phone: {other}"


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
