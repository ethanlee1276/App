"""The open Duo wears the app: the tab bar on the right edge on its side, at
the bottom upright, and the menu sheet in place of the sidebar
(styles.css "THE DUO OPEN ON ITS SIDE WEARS THE APP", boot.js, app.js
DUO_SIDE_MQ, duoSide, isPhone).

Ethan, 2026-10-29, the open Duo on its side with the desktop sidebar: "I
kind of prefer it to have the tab bar that we have on the regular mobile
app with the live button ... on the side like how we do in the folded
view". He chose Apple's layout for the Duo, whose design guide says "The
controls remain on the side when the device opens in landscape to ensure a
consistent experience as people move between displays" and keeps standard
horizontal bars on the inner display upright. What these hold:

  * on its side (a finger on a wide, short screen: 951 by 543, 890 by 626),
    the page keeps its width and its way around is the phone's: the five
    tabs on the right edge, the hamburger opening the menu sheet, the
    sidebar and the header's Ask button gone (Ask is a tab);
  * upright (669 by 825) it is a phone, with the bar at the bottom;
  * a tablet on its side, a laptop and a phone on its side keep theirs
    (the sidebar, with the button that slides it away since 2026-10-29);
  * the bar's and the sheet's rules are the phone's own, copied out of its
    width blocks, and held to them here; the button's look is one rule at
    every width; the shape is one query in boot.js, app.js and the side
    strip's block.

Run directly: `python3 tests/test_the_open_duo_wears_the_app.py`
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
CSS, APP, BOOT = READ("web", "css", "styles.css"), READ("web", "js", "app.js"), READ("web", "js", "boot.js")
DUO_SIDE = ("(pointer: coarse) and (min-width: 761px) and (max-width: 1060px) and (min-height: 500px) "
            "and (max-height: 760px) and (min-aspect-ratio: 5/4)")


def _block(start):
    i = CSS.index(start)
    j = CSS.index("{", i) + 1
    depth, k = 1, j
    while depth:
        depth += {"{": 1, "}": -1}.get(CSS[k], 0)
        k += 1
    return CSS[i:k]


PHONE = _block("@media (max-width: 760px) {\n  /* SIX CRESTS")
DRAWER = _block("@media (max-width: 900px) {\n  .shell, body.has-rail .shell { display: block; }")


def _duo_block():
    at = CSS.index("/* THE DUO OPEN ON ITS SIDE WEARS THE APP")
    end = CSS.index("\n\n", CSS.index("html.duo-side .more-pill b {", at))
    return CSS[at:end]


def _bodies(block, sel):
    return [" ".join(m.group(1).split()) for m in re.finditer(r"(?m)^\s*" + re.escape(sel) + r" \{([^}]*)\}", block)]


TAB = [".tabbar", ".tb-item", ".tb-item svg", ".tb-item.active", ".tb-center", ".tb-center-disc",
       ".tb-center-disc svg", ".tb-center.active", ".tb-badge", ".tb-badge[hidden]",
       '.tb-item[aria-expanded="true"]', ".tb-item > svg", ".tb-item.active > svg", ".tb-item::after",
       '.tb-item.active::after, .tb-item[aria-expanded="true"]::after', ".tb-center::after"]
SHEET = [".more-scrim", ".more-sheet", ".more-scrim[hidden], .more-sheet[hidden]", "body.more-open",
         "body.more-open .more-scrim", "body.more-open .more-sheet", ".more-handle", ".more-search",
         ".more-search svg", ".more-group", ".more-foot", ".more-foot .more-pills:empty", ".more-switch i",
         '.more-switch[aria-checked="true"] i', '.more-switch[aria-checked="true"] svg', ".more-group h3",
         ".more-pills", ".more-pill", ".more-pill svg", ".more-pill.active", ".more-pill.active svg", ".more-pill b"]
BUTTON = [".menu-toggle", ".mt-bars", ".mt-bars::before, .mt-bars::after", ".mt-bars::before", ".mt-bars::after",
          ".mt-label"]


def _prefix(sel):
    return ", ".join("html.duo-side " + s.strip() for s in sel.split(","))


def test_the_bar_the_sheet_and_the_button_are_the_phones_own():
    duo = _duo_block()
    for originals, sels in ((PHONE, TAB), (PHONE, SHEET)):
        for sel in sels:
            want, got = _bodies(originals, sel), _bodies(duo, _prefix(sel))
            assert want and got == want, (sel, want, got)
    # The button shows at every width now (tests/test_the_sidebar_slides_away.py):
    # its look is the base rule's, and no width block carries a copy.
    assert "\n.menu-toggle { display: grid; place-items: center; width: 42px; height: 42px;" in CSS
    for sel in BUTTON:
        assert not _bodies(duo, _prefix(sel)) and not _bodies(DRAWER, sel), sel
    for want in ("html.duo-side .shell, html.duo-side body.has-rail .shell { display: block; }",
                 "html.duo-side .sidebar, html.duo-side .tb-ask { display: none; }"):
        assert want in duo, want
    # Before the stylesheet's tokens-only tail (its #fff are the phone's own).
    assert CSS.index("/* THE DUO OPEN ON ITS SIDE WEARS THE APP") < CSS.index("A Most Likely pick, explained")
    # The side strip's rules turn the bar on end, after the copies.
    assert CSS.index("/* THE DUO OPEN ON ITS SIDE WEARS THE APP") < CSS.index("/* THE IPHONE DUO'S SIDE STRIP")
    assert "html.duo-side #qb-slip { right: var(--strip-w); }" in CSS
    assert "html.duo-side.side-rail:not(.side-rail-inset) .tabbar { padding-top: calc(var(--topbar-h) + 8px); }" in CSS


def test_one_shape_in_three_places():
    assert f'var DUO_SIDE = "{DUO_SIDE}";' in BOOT
    assert f'const DUO_SIDE_MQ = "{DUO_SIDE}";' in APP
    strip = CSS[CSS.index("/* THE IPHONE DUO'S SIDE STRIP"):]
    assert strip[strip.index("@media"):strip.index("{", strip.index("@media"))].strip() == \
        "@media (max-width: 760px),\n       " + DUO_SIDE
    # Defined before anything that runs reads it (initFoldSeams).
    assert APP.index("const DUO_SIDE_MQ") < APP.index("\ninitFoldSeams();\n")


def test_the_script_takes_the_sheet_for_the_menu_there():
    assert 'matchMedia("(max-width: 760px)").matches) && !unfolded() || duoSide();' in APP
    assert "return !!(window.matchMedia && matchMedia(DUO_SIDE_MQ).matches);" in APP
    assert "[narrow, phone, open, split, side].forEach(" in APP, "the sheet closes on leaving the shape"
    assert 'root.classList.toggle("duo-side", duo);' in BOOT
    assert 'root.classList.toggle("side-rail-inset", !!side && (side === "left" ? l : r) >= 60);' in BOOT
    assert "var w = side === \"left\" ? l : r >= 60 ? r : 84;" in BOOT


SHAPES = {
    # name: (width, height, touch, the Duo on its side, the bar's place)
    "on its side": (951, 543, True, True, "right"),
    "on its side, by Apple's pixels": (890, 626, True, True, "right"),
    # Ethan's own Duo, as a Home Screen app (his screenshots, two pixels a point).
    "on its side, his Home Screen app": (910, 703, True, True, "right"),
    "upright": (669, 825, True, False, "bottom"),
    "upright, his Home Screen app": (703, 1000, True, False, "bottom"),
    # A Fold's near-square inner screen keeps its desktop shell.
    "a Pixel Fold's inner screen": (841, 701, True, False, None),
    "a tablet on its side": (1133, 744, True, False, None),
    "a laptop": (951, 543, False, False, None),
    "a phone on its side": (874, 402, True, False, None),
}

PROBE = """() => { const h = document.documentElement, t = document.getElementById('tabbar'),
    s = document.getElementById('sidebar'), m = document.getElementById('menu-toggle'),
    box = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
    const sb = s.getBoundingClientRect();
    return { duo: h.classList.contains('duo-side'),
             bar: getComputedStyle(t).display !== 'none' ? box(t) : null,
             tabs: [...t.querySelectorAll('.tb-item')].map((b) => b.textContent.trim()),
             sidebar: getComputedStyle(s).display !== 'none' && sb.width > 0 && sb.right > 0,
             menu: getComputedStyle(m).display !== 'none',
             ask: getComputedStyle(document.getElementById('nav-ask')).display !== 'none',
             main: Math.round(document.querySelector('main').getBoundingClientRect().right),
             sw: document.scrollingElement.scrollWidth, w: innerWidth, h: innerHeight }; }"""


def test_in_a_browser_each_shape_and_the_menu_on_its_side():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, (w, h, touch, _duo, _bar) in SHAPES.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block",
                                              is_mobile=touch, has_touch=touch)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                         "localStorage.setItem('qb_new_2026_10_29','1');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_timeout(1800)
                    got[name] = page.evaluate(PROBE)
                    if name == "on its side":
                        page.click("#menu-toggle")
                        page.wait_for_timeout(500)
                        got["sheet"] = page.evaluate("""() => ({ open: document.body.classList.contains('more-open'),
                            pills: [...document.querySelectorAll('#more-groups .more-pill')].map((p) => p.textContent.trim()) })""")
                        page.click('#more-groups .more-pill[data-ref="view:longshots"]')
                        page.wait_for_timeout(600)
                        got["via_sheet"] = page.evaluate("[state.view, document.body.classList.contains('more-open')]")
                        page.click('#tabbar .tb-item[data-view="likely"]')
                        page.wait_for_timeout(600)
                        got["via_bar"] = page.evaluate("state.view")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    for name, (w, h, _touch, duo, bar) in SHAPES.items():
        g = got[name]
        assert g["duo"] == duo and g["sw"] <= w, (name, g)
        if bar == "right":
            assert g["bar"] == [w - 84, 0, 84, h], (name, "on end, the right edge, top to bottom", g)
            assert g["tabs"] == ["Home", "Picks", "Live", "Record", "Ask"], g["tabs"]
            assert not g["sidebar"] and g["menu"] and not g["ask"], (name, g)
            assert g["main"] <= w - 84, (name, "the page keeps clear of the bar", g)
        elif bar == "bottom":
            assert g["bar"] and g["bar"][1] + g["bar"][3] >= h - 2 and g["bar"][2] > w / 2, (name, "at the foot", g)
            assert not g["sidebar"] and g["menu"], (name, g)
        else:
            assert g["bar"] is None or name == "a phone on its side", (name, g)
    for name in ("a tablet on its side", "a laptop", "a Pixel Fold's inner screen"):
        assert got[name]["sidebar"] and got[name]["menu"], (name, "the sidebar stays theirs, and slides", got[name])
    sheet = got["sheet"]
    assert sheet["open"] and len(sheet["pills"]) >= 20, sheet
    for want in ("Most Likely", "Long Shots", "Over / Under", "Game Lines", "Injuries & News"):
        assert want in sheet["pills"], (want, sheet["pills"])
    assert got["via_sheet"] == ["longshots", False], ("a pill goes there and the sheet closes", got["via_sheet"])
    assert got["via_bar"] == "likely", got["via_bar"]


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
