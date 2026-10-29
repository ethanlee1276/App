"""The sidebar slides away on iPads and computers (styles.css "THE SIDEBAR
SLIDES AWAY", app.js sidebarSlide, boot.js).

Ethan, 2026-10-29: "an option to slide this menu bar over too the side and
make the Main screen bigger", then "add the slide button for ipads and
computers too". Wherever the sidebar stands beside the page, the menu button
at the top left slides it away and the page takes its width; again, and it
comes back. What these hold:

  * it is the open shapes' own list: a wide window (901px and up), any window
    on its side, a Fold's inner screen, spelt as app.js spells them;
  * hidden, the sidebar's column is nothing, the right rail keeps its own,
    the wall keeps its one column, and nothing in the sidebar takes Tab;
    it slides and fades out over the page by transform and opacity only
    (tests/test_design_tells.py: no layout property animates);
  * the button is one rule at every width, and with it in the bar no control
    runs off the right edge at any width: the date and the source pill step
    aside below the wide bar, and from 1280px the search field gives way first;
  * a pick open beside its board has put the sidebar aside: no button there;
  * the choice is remembered on this device, before the first paint;
  * a phone's button opens its sheet, the open Duo's its sheet, a narrow
    window's its drawer, as before, and says so again when a window narrows;
  * the open Duo's bar beside the clock wears the strip's black (dark look):
    a Home Screen app cannot draw under the clock, so the two read as one.

Run directly: `python3 tests/test_the_sidebar_slides_away.py`
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


def _block():
    at = CSS.index("/* THE SIDEBAR SLIDES AWAY")
    return CSS[at:CSS.index("\n.mc-pick.active", at)]


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_it_is_where_the_sidebar_stands_beside_the_page():
    block = _block()
    query = block[block.index("@media ") + len("@media "):block.index(" {\n")]
    m = re.search(r'const UNFOLDED_MQ = ((?:"[^"]+"\s*\+?\s*)+);', APP)
    side, inner = "".join(re.findall(r'"([^"]+)"', m.group(1))).split(", ")
    assert [q.strip() for q in query.split(",\n")] == [
        "(min-width: 901px)", side.replace(" and (min-height", " and (max-width: 900px) and (min-height"), inner], query
    shell = CSS[CSS.index("@media (min-width: 700px) and (max-width: 900px) and (min-height: 480px)"):]
    shell = shell[:shell.index("\n}\n")]
    assert ".menu-toggle { display: none; }" not in shell, "the open shapes show the button now"
    look = ".menu-toggle { display: grid; place-items: center; width: 42px; height: 42px;"
    assert CSS.count(look) == 1 and "\n" + look in CSS, "one rule, at every width"
    assert "\n.mt-label { display: none; }" in CSS, "the bars alone, as at 900px"
    assert "html:not(.duo-side) body.two-pane .menu-toggle { display: none; }" in block


def test_hidden_the_page_takes_the_width():
    block = _block()
    for want in ("html.sb-hidden .shell {\n    --side-col: 0px; }",
                 "html.sb-hidden .sidebar { width: var(--sidebar-w); transform: translateX(-100%); opacity: 0; "
                 "visibility: hidden;", "visibility 0s linear var(--dur-base);"):
        assert want in block, want
    # Every shell's first column reads it, the right rail's included; the wall's one column does not.
    assert CSS.count("grid-template-columns: var(--side-col, var(--sidebar-w)) minmax(0, 1fr)") == 3
    assert "body.walled.on-wall .shell { grid-template-columns: minmax(0, 1fr); }" in CSS
    assert "overflow" not in block, "the pane's scrolling is its own (tests/test_the_sidebar_holds_still.py)"
    wide = CSS[CSS.index("/* THE TOP BAR, TO ETHAN'S DASHBOARD RENDER"):]
    wide = wide[:wide.index("\n}\n")]
    for want in (".slate-meta { flex: 0 1 auto; }", ".slate-meta > * { flex-shrink: 0; }",
                 ".ns-field { flex-shrink: 1; min-width: 72px; }"):
        assert want in wide, want
    # Below the wide bar the date and the source pill step aside (at 900px and under they always had).
    for want in ("@media (max-width: 1520px) {\n  .topbar #slate-date { display: none; }",
                 "@media (max-width: 1439px) {\n  .topbar #data-source { display: none; }"):
        assert want in CSS, want


def test_the_button_slides_where_it_stands_and_opens_the_rest():
    click = _fn("initMobileMenu")
    phone, slide, drawer = (click.index("if (isPhone()) {"), click.index("if (sidebarDocked()) {"),
                            click.index('document.body.classList.toggle("menu-open")'))
    assert phone < slide < drawer, "the sheet first, then the slide, then the drawer"
    assert 'getComputedStyle(sb).position === "sticky"' in _fn("sidebarDocked")
    slide_fn = _fn("sidebarSlide")
    assert 'localStorage.setItem(SB_HIDDEN_KEY, "1")' in slide_fn and "localStorage.removeItem(SB_HIDDEN_KEY)" in slide_fn
    assert 'const SB_HIDDEN_KEY = "qb_sb_hidden";' in APP
    sync = _fn("sidebarSlideSync")
    for want in ('btn.setAttribute("aria-controls", phone ? "more-sheet" : "sidebar");',
                 '!document.documentElement.classList.contains("sb-hidden")',
                 'body.contains("menu-open") || body.contains("more-open")'):
        assert want in sync, want
    assert 'id="menu-toggle" aria-label="Menu"' in READ("web", "index.html"), "one name; aria-expanded says the rest"
    assert 'addEventListener("resize", sidebarSlideSync);' in click


def test_remembered_before_the_first_paint():
    assert 'if (localStorage.getItem("qb_sb_hidden") === "1") document.documentElement.classList.add("sb-hidden");' in BOOT
    html = READ("web", "index.html")
    assert '<script src="js/boot.js"></script>' in html[:html.index("</head>")], "a plain script in the head"


def test_the_open_duos_bar_wears_the_strips_black():
    root = CSS[CSS.index(":root {"):]
    assert "--strip-black: #000;" in root[:root.index("\n}\n")]
    assert ('html.duo-side.side-rail:not(.side-rail-inset):not([data-theme="light"]) .tabbar '
            '{ background: var(--strip-black); }') in CSS
    assert 'root.classList.toggle("side-rail-inset"' in BOOT, \
        "an app given the strip draws under the clock itself (tests/test_the_iphone_duo_side_strip.py)"


SEE = """() => { const s = document.getElementById('sidebar'), b = document.getElementById('menu-toggle');
  const r = s.getBoundingClientRect();
  return {hidden: document.documentElement.classList.contains('sb-hidden'), duo: document.documentElement.classList.contains('duo-side'),
          sheet: document.body.classList.contains('more-open'), drawer: document.body.classList.contains('menu-open'),
          side: [Math.round(r.left), Math.round(r.width)], vis: getComputedStyle(s).visibility,
          main: Math.round(document.querySelector('main').getBoundingClientRect().width),
          aria: b.getAttribute('aria-expanded'), label: b.getAttribute('aria-label'),
          key: localStorage.getItem('qb_sb_hidden'), atDom: window.__sbAtDom, wide: document.scrollingElement.scrollWidth,
          w: innerWidth}; }"""


OFF_EDGE = """() => [...document.querySelectorAll('.topbar .menu-toggle, .topbar .brand-home, .slate-meta > *')]
  .filter((e) => getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 1)
  .filter((e) => e.getBoundingClientRect().right > innerWidth + 1 || e.getBoundingClientRect().left < -1)
  .map((e) => e.id || e.className.toString().split(' ')[0])"""


def _open(browser, port, errs, w, h, touch, hidden=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block", is_mobile=touch, has_touch=touch)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                         + ("localStorage.setItem('qb_sb_hidden','1');" if hidden else "") + "}catch(e){}"
                         "document.addEventListener('DOMContentLoaded', () => {"
                         " window.__sbAtDom = document.documentElement.classList.contains('sb-hidden'); });")
    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
    page.wait_for_timeout(1500)
    return ctx, page


def _tab_stops_inside(page, presses):
    page.focus("#menu-toggle")
    n = 0
    for _ in range(presses):
        page.keyboard.press("Tab")
        n += page.evaluate("() => !!document.activeElement.closest('#sidebar')")
    return n


def _run():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                # A laptop: hide, the page takes the width; reload, still hidden; Tab skips it.
                ctx, page = _open(browser, port, errs, 1280, 800, False)
                got["bar"] = {}
                for bw in (901, 1024, 1100, 1180, 1280, 1366, 1440, 1520, 1600, 1920):
                    page.set_viewport_size({"width": bw, "height": 800})
                    page.wait_for_timeout(250)
                    got["bar"][bw] = page.evaluate(OFF_EDGE)
                page.set_viewport_size({"width": 1280, "height": 800})
                page.wait_for_timeout(300)
                got["laptop"] = [page.evaluate(SEE)]
                page.click("#menu-toggle")
                page.wait_for_timeout(700)
                got["laptop"].append(page.evaluate(SEE))
                got["laptop_tab_hidden"] = _tab_stops_inside(page, 40)
                page.reload(wait_until="load")
                page.wait_for_timeout(1200)
                got["laptop"].append(page.evaluate(SEE))
                # Narrowed to a drawer: the drawer's button again, and the drawer opens.
                page.set_viewport_size({"width": 800, "height": 900})
                page.wait_for_timeout(500)
                got["narrow"] = [page.evaluate(SEE)]
                page.click("#menu-toggle")
                page.wait_for_timeout(600)
                got["narrow"].append(page.evaluate(SEE))
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                page.set_viewport_size({"width": 1280, "height": 800})
                page.wait_for_timeout(500)
                got["narrow"].append(page.evaluate(SEE))
                page.click("#menu-toggle")
                page.wait_for_timeout(700)
                got["laptop"].append(page.evaluate(SEE))
                got["laptop_tab_shown"] = _tab_stops_inside(page, 20)
                page.click("#menu-toggle")
                page.wait_for_timeout(700)
                got["wall"] = page.evaluate("""() => { document.body.classList.add('walled', 'on-wall', 'has-rail');
                    return getComputedStyle(document.querySelector('.shell')).gridTemplateColumns.split(' ').length; }""")
                ctx.close()
                # An iPad on its side, finger and all: it slides.
                ctx, page = _open(browser, port, errs, 1133, 744, True)
                got["ipad"] = [page.evaluate(SEE)]
                page.click("#menu-toggle")
                page.wait_for_timeout(700)
                got["ipad"].append(page.evaluate(SEE))
                ctx.close()
                # Ethan's open Duo on its side, his phone, an iPad upright, all with it hidden on this device.
                for name, w, h in (("duo", 910, 703), ("phone", 390, 844), ("ipad_upright", 820, 1180)):
                    ctx, page = _open(browser, port, errs, w, h, True, hidden=True)
                    page.click("#menu-toggle")
                    page.wait_for_timeout(700)
                    got[name] = page.evaluate(SEE)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_it_slides_where_it_stands_and_nowhere_else():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got, errs = _run()
    assert not errs, errs
    shown, hidden, reloaded, back = got["laptop"]
    assert not shown["hidden"] and shown["side"][1] > 180 and shown["aria"] == "true", shown
    assert shown["label"] == "Menu", shown
    assert all(not off for off in got["bar"].values()), ("a control off the right edge", got["bar"])
    assert hidden["hidden"] and hidden["side"][0] + hidden["side"][1] <= 0 and hidden["vis"] == "hidden", hidden
    assert hidden["main"] >= shown["main"] + shown["side"][1], ("the page takes the sidebar's width", shown, hidden)
    assert hidden["aria"] == "false" and hidden["key"] == "1", hidden
    assert hidden["wide"] == hidden["w"], "nothing runs off the side"
    assert got["laptop_tab_hidden"] == 0, "nothing in the hidden sidebar takes Tab"
    assert reloaded["hidden"] and reloaded["atDom"] is True and reloaded["main"] == hidden["main"], ("remembered", reloaded)
    assert not back["hidden"] and back["key"] is None and back["side"][1] == shown["side"][1], back
    assert got["laptop_tab_shown"] > 0, "shown, it is in the Tab order again"
    assert got["wall"] == 1, "the wall keeps its one column"
    narrow, drawer, wide = got["narrow"]
    assert narrow["aria"] == "false", ("the drawer's button again: its drawer is shut", narrow)
    assert drawer["drawer"] and drawer["side"][0] == 0 and drawer["vis"] == "visible" and drawer["aria"] == "true", \
        ("the drawer opens", drawer)
    assert wide["hidden"] and wide["aria"] == "false", ("and back beside the page, still hidden", wide)
    ipad, ipad_hidden = got["ipad"]
    assert ipad_hidden["hidden"] and ipad_hidden["main"] == ipad_hidden["w"], ("an iPad on its side slides", ipad_hidden)
    assert ipad_hidden["main"] > ipad["main"], ipad
    duo = got["duo"]
    assert duo["duo"] and duo["sheet"] and not duo["drawer"] and duo["aria"] == "true", ("the open Duo's sheet", duo)
    phone = got["phone"]
    assert phone["sheet"] and not phone["drawer"], ("the phone's sheet", phone)
    up = got["ipad_upright"]
    assert up["drawer"] and up["side"][0] == 0 and up["vis"] == "visible", ("an iPad upright opens its drawer", up)


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
