"""The screen's last strip (web/js/boot.js, web/css/styles.css; Ethan,
2026-10-28, a screenshot from his iPhone with the strip circled: "Fix this
black bar").

The menu and the shade behind it stopped 62pt short of the bottom of his
screen, over a bare strip of page: exactly his status bar's height. iOS 26
can open a Home Screen app with the page that much shorter than the screen
until it settles (innerHeight = the screen less the status bar), and
everything pinned to the bottom stops there: the menu, its shade, the tab
bar, every sheet.

  * boot.js measures the shortfall on an iPhone app (Safari's Home Screen
    app or the iOS build), up to 100px, and hands it to the page as --vgap;
    a resize measures it again, so it is gone once iOS catches up. Nowhere
    else is it ever set.
  * styles.css (and the chat room's, the level-up's and the carry chart's
    sheets) reach the bottom edge by it; the floating tab bar, the riding
    pill and the slip are measured from the real edge.

Run directly: `python3 tests/test_the_screens_last_strip.py`
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def READ(*parts):
    return Path(ROOT, *parts).read_text(encoding="utf-8")


BOOT, CSS = READ("web", "js", "boot.js"), READ("web", "css", "styles.css")


def test_boot_measures_it_only_on_an_iphone_app():
    gate = ('if (!/iPhone/.test(ua) || !(navigator.standalone === true || /QellysApp\\/[\\d.]+ \\(ios\\)/.test(ua))) '
            'return;')
    assert gate in BOOT, "an iPhone Home Screen app or the iOS build (its own user agent), and nothing else"
    body = BOOT[BOOT.index("THE SCREEN'S LAST STRIP"):]
    assert "QB_STORE_APP ===" not in body[:body.index("} catch (e) {}")], \
        "not the remembered store app: a Safari tab that once opened ?app=ios keeps that too"
    for want in ("Math.max(s.width, s.height) : Math.min(s.width, s.height)",
                 "var gap = Math.round(full - innerHeight);",
                 "if (!(gap > 0 && gap <= 100)) gap = 0;",
                 'if (gap) root.style.setProperty("--vgap", gap + "px");',
                 'else root.style.removeProperty("--vgap");',
                 "if (gap) poll = setInterval(vgap, 1000);",          # a settle with no event still clears it
                 'addEventListener("resize", vgap);', 'addEventListener("pageshow", vgap);',
                 'visualViewport.addEventListener("resize", vgap);'):
        assert want in BOOT, want


def test_the_layers_pinned_to_the_bottom_reach_down_by_it():
    assert re.search(r"--vgap:\s*0px;", CSS), "0 unless boot.js measured a shortfall"
    sheet = ".more-sheet { display: block; position: fixed; top: 0; left: 0; bottom: 0;"
    reach = ".more-scrim, .more-sheet { bottom: calc(-1 * var(--vgap)); }"
    assert sheet in CSS and reach in CSS and CSS.index(sheet) < CSS.index(reach), "after the sheet's own rule"
    # Less the capsule's own drop (tests/test_the_iphone_tab_bar_sits_low.py).
    capsule = "left: 12px; right: 12px; bottom: calc(8px + env(safe-area-inset-bottom) - var(--tb-drop));"
    floats = ("html.store-ios .tabbar, html.ios-home .tabbar {\n"
              "    bottom: calc(8px + env(safe-area-inset-bottom) - var(--tb-drop) - var(--vgap)); }")
    assert capsule in CSS and floats in CSS and CSS.index(capsule) < CSS.index(floats)
    assert "bottom: calc(98px + env(safe-area-inset-bottom, 0px) - var(--tb-drop) - var(--vgap)); }" in CSS, \
        "the riding pill rides with it"
    # The ids sit after their own rules and before the sheet's tokens-only
    # tail (tests/test_most_likely_opens_its_own_page.py: no "#" past it).
    tail = CSS.index("A Most Likely pick, explained")
    for own, reach in (("#qb-slip { bottom: calc(58px + env(safe-area-inset-bottom) - var(--tb-drop)); }",
                        "#qb-slip { bottom: calc(58px + env(safe-area-inset-bottom) - var(--tb-drop) - var(--vgap)); }"),
                       ("#tour-overlay { position: fixed; inset: 0;",
                        "#ffd-overlay, #pk-overlay, #tour-overlay { bottom: calc(-1 * var(--vgap)); }"),
                       (".betit-sheet { position: fixed; inset: 0;", ".betit-sheet { bottom: calc(-1 * var(--vgap)); }")):
        assert own in CSS and reach in CSS and CSS.index(own) < CSS.index(reach), reach
        assert reach.startswith(".") or CSS.index(reach) < tail, reach
    # Only the carry chart carries its own 0: it is also drawn without the
    # site's sheet (its own browser test), where an unset token would undo
    # the inset and let the overlay grow past the screen. The rooms that
    # load only with the site's sheet read the token as it is, since a 0
    # there could never be reached (tests/test_design_tells.py).
    for path, reach in ((("web", "css", "chat.css"), ".gch-sheet { bottom: calc(-1 * var(--vgap)); }"),
                        (("web", "css", "carrychart.css"), "#cc-overlay { bottom: calc(-1 * var(--vgap, 0px)); }")):
        css = READ(*path)
        sel = reach.split(" {")[0]
        assert reach in css, path
        assert css.index(f"{sel} {{ position: fixed; inset: 0;") < css.index(reach)
    assert "animation: krIn .25s ease-out both;\n  bottom: calc(-1 * var(--vgap)); }" in READ("web", "css", "karma.css")


# --- in a phone browser ----------------------------------------------------------
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1")
MEASURE = """(() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null;
                     const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom }; };
  return { vgap: getComputedStyle(document.documentElement).getPropertyValue('--vgap').trim(),
           ih: innerHeight, home: document.documentElement.classList.contains('ios-home'),
           sheet: r('#more-sheet'), scrim: r('#more-scrim'), tab: r('.tabbar') };
})()"""


def _until(page, js: str, timeout: float = 8.0) -> None:
    """Poll ``js`` until it is true: the site's CSP refuses the string
    eval that Playwright's own wait_for_function runs on the page."""
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(js):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"never true: {js}")


def test_in_a_phone_browser_the_menu_reaches_the_bottom_of_a_short_screen():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    me = {"handle": "ethan", "name": "Ethan", "color": 1}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}

    def phone(browser, height, standalone, ua=IPHONE_UA, remembered=""):
        ctx = browser.new_context(viewport={"width": 440, "height": height}, screen={"width": 440, "height": 956},
                                  user_agent=ua, is_mobile=True, has_touch=True, service_workers="block")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
        page.route("**/api/**", ful("{}"))
        page.route("**/api/account/me*", ful(json.dumps({"signed_in": True, "email": "you@example.com", "profile": me})))
        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb-seen-intro','1');"
                             "localStorage.setItem('qb.tour','done');localStorage.setItem('qb.a2hs','off');}catch(e){}")
        if standalone:
            page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });")
        if remembered:
            page.add_init_script(f"try{{localStorage.setItem('qb-store-app','{remembered}');}}catch(e){{}}")
        page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
        page.wait_for_selector("#menu-toggle", timeout=15000)
        page.wait_for_timeout(400)
        page.click("#menu-toggle")
        _until(page, "document.body.classList.contains('more-open')")
        page.wait_for_timeout(500)
        return ctx, page

    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx, page = phone(browser, 894, True)            # Ethan's: a status bar short
                got["short"] = page.evaluate(MEASURE)
                page.set_viewport_size({"width": 440, "height": 956})   # iOS settles
                _until(page, "innerHeight === 956")
                page.wait_for_timeout(300)
                got["settled"] = page.evaluate(MEASURE)
                ctx.close()
                ctx, page = phone(browser, 956, True)            # opened right
                got["full"] = page.evaluate(MEASURE)
                ctx.close()
                ctx, page = phone(browser, 800, False)           # a Safari tab: its bars are not a shortfall
                got["tab"] = page.evaluate(MEASURE)
                ctx.close()
                ctx, page = phone(browser, 894, False, IPHONE_UA + " QellysApp/1.0 (ios)")   # the iOS build
                got["build"] = page.evaluate(MEASURE)
                ctx.close()
                ctx, page = phone(browser, 894, False, remembered="ios")   # a tab that once opened ?app=ios
                got["kept"] = page.evaluate(MEASURE)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    s = got["short"]
    assert s["home"] and s["vgap"] == "62px" and s["ih"] == 894, s
    assert s["sheet"]["top"] == 0 and s["sheet"]["bottom"] == 956, "the menu to the foot of the screen"
    assert s["scrim"]["bottom"] == 956, "and its shade"
    assert s["tab"]["bottom"] == 956 - 8, "the tab bar floats 8px off the real edge, not the short one"
    for key, h in (("settled", 956), ("full", 956), ("tab", 800), ("kept", 894)):
        g = got[key]
        assert g["vgap"] == "0px" and g["sheet"]["bottom"] == h and g["scrim"]["bottom"] == h, (key, g)
    assert got["tab"]["home"] is False and got["tab"]["tab"]["bottom"] == 800, got["tab"]
    b = got["build"]
    assert b["vgap"] == "62px" and b["sheet"]["bottom"] == 956 and b["tab"]["bottom"] == 956 - 8, b
    assert got["kept"]["tab"]["bottom"] == 894 - 8, "the store app's capsule, measured from the tab's own edge"


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
