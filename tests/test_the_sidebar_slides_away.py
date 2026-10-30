"""The sidebar slides away by its three dots, or by a finger (styles.css
"THE SIDEBAR SLIDES AWAY", app.js initSidebarGrip, boot.js).

Ethan, 2026-10-29, his open Duo upright with its sidebar circled: "put
like three dots on the right side of the menu. That gives you an option to
click the three dots and it'll just swipe the bar to the left, or you can
physically slide it yourself" (first asked as "an option to slide this menu
bar over too the side and make the Main screen bigger", then for "ipads and
computers too"). What these hold:

  * the dots are wherever the sidebar stands beside the page: the open
    shapes as app.js spells them (the open Duo either way up among them)
    and every wide window; nowhere else, and the hamburger is not there;
  * a tap on the dots, or a drag (the dots by any pointer, the bar itself
    by a finger), slides the bar away and the page takes its width; hidden,
    the dots wait at the left edge, and the same brings it back; a short
    drag springs back, a scroll is a scroll, a tap on a row still goes;
  * hidden, the column is nothing in every shell, the wall keeps its one
    column, nothing in the bar takes Tab, and it slides and fades by
    transform and opacity only (tests/test_design_tells.py);
  * remembered on this device, before the first paint;
  * no control in the top bar runs off the right edge at any width.

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
CSS, APP, BOOT, HTML = (READ("web", "css", "styles.css"), READ("web", "js", "app.js"), READ("web", "js", "boot.js"),
                        READ("web", "index.html"))


def _block():
    at = CSS.index("/* THE SIDEBAR SLIDES AWAY")
    return CSS[at:CSS.index("\n.mc-pick.active", at)]


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_dots_are_where_the_sidebar_stands_beside_the_page():
    block = _block()
    query = block[block.index("@media ") + len("@media "):block.index(" {\n", block.index("@media "))]
    m = re.search(r'const UNFOLDED_MQ = ((?:"[^"]+"\s*\+?\s*)+);', APP)
    side, upright, inner = "".join(re.findall(r'"([^"]+)"', m.group(1))).split(", ")
    assert [q.strip() for q in query.split(",\n")] == [
        "(min-width: 901px)", side.replace(" and (min-height", " and (max-width: 900px) and (min-height"), upright, inner], query
    assert ".sb-grip { display: none; }\n@media" in block, "nowhere else"
    assert ".menu-toggle" not in block, "the hamburger is the drawer's and the sheet's, not the docked sidebar's"
    assert "\n.menu-toggle { display: none; place-items: center;" in CSS


def test_the_dots_and_the_bar_hidden():
    block = _block()
    for want in (".sb-grip { display: grid; place-items: center; position: fixed; z-index: 39; width: 24px; height: 56px;",
                 "touch-action: none;", "body.two-pane .sb-grip, body.walled.on-wall .sb-grip { display: none; }",
                 "html.sb-hidden .shell {\n    --side-col: 0px; }",
                 "html.sb-hidden .sidebar { width: var(--sidebar-w); transform: translateX(-100%); opacity: 0; visibility: hidden;",
                 "visibility 0s linear var(--dur-base);",
                 "html.sb-hidden .sb-grip { transform: translateX(calc(14px - var(--sidebar-w))); }",
                 "html.sb-drag .sidebar { transform: translateX(var(--sb-drag)); opacity: 1; visibility: visible; }",
                 "html.sb-drag .sidebar, html.sb-drag .sb-grip { transition: none; }"):
        assert want in block, want
    assert "overflow" not in block, "the pane's scrolling is its own (tests/test_the_sidebar_holds_still.py)"
    # Every shell's first column reads it, the right rail's included; the wall's one column does not.
    assert CSS.count("grid-template-columns: var(--side-col, var(--sidebar-w)) minmax(0, 1fr)") == 3
    assert "body.walled.on-wall .shell { grid-template-columns: minmax(0, 1fr); }" in CSS


def test_the_dots_are_a_button_beside_the_bar():
    i = HTML.index('<aside class="sidebar" id="sidebar"')
    end = HTML.index("\n  </aside>", i)                  # the sidebar's own close (its comments name <main>)
    after = HTML[end:HTML.index("\n  <main>", end)]
    assert ('<button class="sb-grip" id="sb-grip" type="button" aria-label="Side menu"\n'
            '          aria-controls="sidebar" aria-expanded="true"></button>') in after
    assert 'id="menu-toggle" aria-label="Open menu"' in HTML


def test_a_tap_or_a_drag_slides_it():
    slide = _fn("sidebarSlide")
    assert 'classList.toggle("sb-hidden", hide)' in slide and 'grip.setAttribute("aria-expanded", String(!hide))' in slide
    assert 'localStorage.setItem(SB_HIDDEN_KEY, "1")' in slide and "localStorage.removeItem(SB_HIDDEN_KEY)" in slide
    grip = _fn("initSidebarGrip")
    for want in ('getComputedStyle(grip).display === "none"',
                 'grip.addEventListener("pointerdown", down);', 'sb.addEventListener("pointerdown", down);',
                 '(e.pointerType === "mouse" && e.currentTarget === sb)', "Math.abs(drag.dx) > drag.w / 4",
                 "(drag.dx < 0) !== drag.hidden", 'addEventListener("pointercancel", () => end(false));',
                 "performance.now() < quietUntil", 'grip.addEventListener("click", () => sidebarSlide());'):
        assert want in grip, want
    assert "\ninitMobileMenu();\ninitSidebarGrip();\n" in APP
    assert "sidebarDocked" not in _fn("initMobileMenu"), "the hamburger slides nothing"
    assert ".lb-table, table, .sidebar, .sb-grip, .more-sheet\")) return true;" in _fn("swipeOwned"), "no league swipe"
    assert 'n.matches(".sidebar, .sb-grip, .more-sheet, .rail")' in _fn("paneOwned"), "no pull to refresh"


def test_remembered_before_the_first_paint():
    assert 'if (localStorage.getItem("qb_sb_hidden") === "1") document.documentElement.classList.add("sb-hidden");' in BOOT
    assert '<script src="js/boot.js"></script>' in HTML[:HTML.index("</head>")], "a plain script in the head"


SEE = """() => { const s = document.getElementById('sidebar'), g = document.getElementById('sb-grip');
  const r = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.width)]; };
  return {hidden: document.documentElement.classList.contains('sb-hidden'), side: r(s), vis: getComputedStyle(s).visibility,
          grip: getComputedStyle(g).display === 'none' ? null : r(g), aria: g.getAttribute('aria-expanded'),
          menu: getComputedStyle(document.getElementById('menu-toggle')).display,
          tabbar: getComputedStyle(document.getElementById('tabbar')).display,
          main: Math.round(document.querySelector('main').getBoundingClientRect().width),
          key: localStorage.getItem('qb_sb_hidden'), atDom: window.__sbAtDom, wide: document.scrollingElement.scrollWidth,
          w: innerWidth}; }"""

#: A finger, as the page sees it: pointer events of the touch kind.
DRAG = """async ({sel, dx, dy}) => {
  const el = document.querySelector(sel), r = el.getBoundingClientRect();
  const x0 = r.left + r.width / 2, y0 = r.top + Math.min(r.height / 2, 200);
  const ev = (type, x, y, at) => (at || el).dispatchEvent(new PointerEvent(type, {bubbles: true, cancelable: true,
      pointerId: 7, pointerType: 'touch', isPrimary: true, button: 0, clientX: x, clientY: y}));
  ev('pointerdown', x0, y0);
  let mid = null;
  for (let i = 1; i <= 10; i++) {
    ev('pointermove', x0 + dx * i / 10, y0 + dy * i / 10, window);
    if (i === 5) mid = Math.round(document.getElementById('sidebar').getBoundingClientRect().left);
  }
  ev('pointerup', x0 + dx, y0 + dy, window);
  await new Promise((res) => setTimeout(res, 500));
  return {mid, hidden: document.documentElement.classList.contains('sb-hidden')};
}"""

OFF_EDGE = """() => [...document.querySelectorAll('.topbar .menu-toggle, .topbar .brand-home, .slate-meta > *')]
  .filter((e) => getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 1)
  .filter((e) => e.getBoundingClientRect().right > innerWidth + 1 || e.getBoundingClientRect().left < -1)
  .map((e) => e.id || e.className.toString().split(' ')[0])"""


def _open(browser, port, errs, w, h, touch):
    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block", is_mobile=touch, has_touch=touch)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}"
                         "document.addEventListener('DOMContentLoaded', () => {"
                         " window.__sbAtDom = document.documentElement.classList.contains('sb-hidden'); });")
    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
    page.wait_for_timeout(1500)
    return ctx, page


def _tab_stops_inside(page, presses):
    page.focus("#sb-grip")
    n = 0
    for _ in range(presses):
        page.keyboard.press("Shift+Tab")
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
                # Where the sidebar stands beside the page: tap the dots, reload, tap again.
                for name, w, h, touch in (("laptop", 1280, 800, False), ("duo upright", 703, 1000, True),
                                          ("duo on its side", 910, 703, True), ("ipad on its side", 1133, 744, True)):
                    ctx, page = _open(browser, port, errs, w, h, touch)
                    got[name] = [page.evaluate(SEE)]
                    page.click("#sb-grip")
                    page.wait_for_timeout(600)
                    got[name].append(page.evaluate(SEE))
                    if name == "laptop":
                        got["tab_hidden"] = _tab_stops_inside(page, 6)
                    page.reload(wait_until="load")
                    page.wait_for_timeout(1200)
                    got[name].append(page.evaluate(SEE))
                    page.click("#sb-grip")
                    page.wait_for_timeout(600)
                    got[name].append(page.evaluate(SEE))
                    if name == "laptop":
                        got["tab_shown"] = _tab_stops_inside(page, 6)
                        got["bar"] = {}
                        for bw in (901, 1024, 1100, 1180, 1280, 1366, 1440, 1520, 1600, 1920):
                            page.set_viewport_size({"width": bw, "height": 800})
                            page.wait_for_timeout(250)
                            got["bar"][bw] = page.evaluate(OFF_EDGE)
                        got["two_pane"] = page.evaluate("""() => { document.body.classList.add('two-pane');
                            const d = getComputedStyle(document.getElementById('sb-grip')).display;
                            document.body.classList.remove('two-pane'); return d; }""")
                        page.click("#sb-grip")
                        page.wait_for_timeout(600)
                        got["wall"] = page.evaluate("""() => { document.body.classList.add('walled', 'on-wall', 'has-rail');
                            return [getComputedStyle(document.querySelector('.shell')).gridTemplateColumns.split(' ').length,
                                    getComputedStyle(document.getElementById('sb-grip')).display]; }""")
                    if name == "duo upright":
                        got["drags"] = [page.evaluate(DRAG, {"sel": "#sidebar", "dx": -30, "dy": 0}),
                                        page.evaluate(DRAG, {"sel": "#sidebar", "dx": -6, "dy": -140}),
                                        page.evaluate(DRAG, {"sel": "#sidebar", "dx": -150, "dy": 6}),
                                        page.evaluate(DRAG, {"sel": "#sb-grip", "dx": 160, "dy": 0})]
                        page.click('#sidebar .nav-btn[data-view="longshots"]')
                        page.wait_for_timeout(500)
                        got["tap_after"] = page.evaluate("state.view")
                    ctx.close()
                # Where it is a drawer or a sheet: no dots, the hamburger.
                for name, w, h in (("phone", 390, 844), ("ipad upright", 820, 1180)):
                    ctx, page = _open(browser, port, errs, w, h, True)
                    got[name] = page.evaluate(SEE)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_the_dots_and_a_finger_slide_it():
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
    for name in ("laptop", "duo upright", "duo on its side", "ipad on its side"):
        shown, hidden, reloaded, back = got[name]
        edge = shown["side"][0] + shown["side"][1]
        assert shown["grip"] and abs(shown["grip"][0] + shown["grip"][1] / 2 - edge) <= 2, ("on the bar's right edge", name, shown)
        assert shown["grip"][1] >= 24 and shown["aria"] == "true", (name, shown)
        assert shown["menu"] == "none" and shown["tabbar"] == "none", ("no hamburger, no tab bar", name, shown)
        assert hidden["hidden"] and hidden["side"][0] + hidden["side"][1] <= 12 and hidden["vis"] == "hidden", (name, hidden)
        assert hidden["main"] >= shown["main"] + shown["side"][1], ("the page takes its width", name, shown, hidden)
        assert hidden["grip"][0] <= 8 and hidden["aria"] == "false" and hidden["key"] == "1", ("dots at the edge", name, hidden)
        assert hidden["wide"] == hidden["w"], ("nothing runs off the side", name, hidden)
        assert reloaded["hidden"] and reloaded["atDom"] is True, ("remembered before the first paint", name, reloaded)
        assert not back["hidden"] and back["key"] is None and back["side"] == shown["side"], (name, back)
    assert got["tab_hidden"] == 0 and got["tab_shown"] > 0, ("hidden, nothing in the bar takes Tab", got["tab_hidden"], got["tab_shown"])
    assert all(not off for off in got["bar"].values()), ("a control off the right edge", got["bar"])
    assert got["two_pane"] == "none", "a pick beside its board has no sidebar, so no dots"
    assert got["wall"] == [1, "none"], ("the wall keeps its one column, and no dots", got["wall"])
    short, scroll, away, back = got["drags"]
    assert short["mid"] < 0 and not short["hidden"], ("a short drag follows the finger and springs back", short)
    assert not scroll["hidden"] and scroll["mid"] > 0, ("a scroll is a scroll", scroll)
    assert away["hidden"], ("a finger slides the bar away", away)
    assert not back["hidden"], ("and drags the dots back", back)
    assert got["tap_after"] == "longshots", "a tap on a row still goes there"
    for name in ("phone", "ipad upright"):
        assert got[name]["grip"] is None and got[name]["menu"] == "grid", ("the drawer's or the sheet's: no dots", name, got[name])


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
