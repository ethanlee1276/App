"""The tab bar on the iPhone Duo's side strip (js/boot.js, styles.css).

Ethan, 2026-10-29, his closed iPhone Duo, the tab bar circled and an arrow
to the black strip beside the clock: "move this bar ... to the right side
... only for the iPhone Duo". On the closed Duo, an app built with the iOS
27.1 SDK reaches the screen's edge, and the strip beside the clock and the
camera comes to the page as a safe-area inset on one side only, where the
system stands its own bars on end under the clock. An app built with an
older SDK, and a Home Screen web app on iOS so far, never gets the strip:
there the inset is nothing and nothing here moves. What these hold:

  * a strip on one side only (60px or more, the other side 16 or less) puts
    the bar in it, on end, under the clock; the page keeps clear of it and
    saves no room at its foot; on the left side as well (Split View);
  * an iPhone on its side insets both sides alike and keeps its bar, and an
    iPhone in the hand has no side inset at all;
  * the strip's width is its own variable (--strip-w), not the desktop
    layout's --rail-w.

Run directly: `python3 tests/test_the_iphone_duo_side_strip.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


def test_boot_measures_a_strip_on_one_side_only():
    boot = READ("web", "js", "boot.js")
    for want in ('padding-left:env(safe-area-inset-left,0px);padding-right:env(safe-area-inset-right,0px)',
                 'var side = r >= 60 && l <= 16 ? "right" : l >= 60 && r <= 16 ? "left" : duo ? "right" : "";',
                 'root.classList.toggle("duo-side", duo);',
                 'root.classList.toggle("side-rail", !!side);', 'root.classList.toggle("side-rail-left", side === "left");',
                 'root.style.setProperty("--strip-w"', 'addEventListener("resize", rail);'):
        assert want in boot, want
    css = READ("web", "css", "styles.css")
    at = css.index("/* THE IPHONE DUO'S SIDE STRIP")
    block = css[at:css.index("/* YOUR TEAM'S COLOURS", at)]
    for want in ("flex-direction: column", "width: var(--strip-w);", "padding-right: var(--strip-w);",
                 "html.side-rail-left .tabbar", "html.side-rail body.menu-open .topbar",
                 # What floated above the bar comes down to the foot, out of the strip.
                 "html.side-rail .riding-tray", "html.side-rail .gch-fab", "html.side-rail .kr-notes",
                 "html.side-rail .pw-dock", "html.side-rail .tf-toast", "html.side-rail .crash-note",
                 "html.side-rail-left .riding-tray", "html.side-rail-left .gch-fab", "html.side-rail-left .tf-toast"):
        assert want in block, want
    assert "html.side-rail #qb-slip { right: var(--strip-w);" in css, "the slip's, with the slip's own rules"
    assert "--rail-w" not in block, "the desktop layout's --rail-w is another thing"
    assert css.count("--rail-w: 280px;") == 1, "and it stays the desktop's right column"
    assert "--tb-drop:" not in block, "the iPhone capsule's drop is its own (tests/test_the_iphone_tab_bar_sits_low.py)"
    root = css[css.index(":root {"):]
    assert "--strip-w: 84px;" in root[:root.index("\n}\n")], "a token like the layout's others; boot.js writes the measured one"


def _shapes():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    out, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, insets, size in (
                        ("duo", {"top": 0, "left": 0, "bottom": 21, "right": 84}, (458, 932)),
                        ("duo_left", {"top": 0, "left": 84, "bottom": 21, "right": 0}, (458, 932)),
                        ("on_its_side", {"top": 0, "left": 59, "bottom": 21, "right": 59}, (932, 430)),
                        ("in_the_hand", {"top": 59, "left": 0, "bottom": 34, "right": 0}, (390, 844))):
                    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    ctx.new_cdp_session(page).send("Emulation.setSafeAreaInsetsOverride", {"insets": insets})
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?app=ios#home", wait_until="load")
                    page.wait_for_timeout(1500)
                    out[name] = page.evaluate("""() => { const h = document.documentElement,
                        t = document.getElementById('tabbar').getBoundingClientRect(), b = getComputedStyle(document.body);
                        // A toast, and the slip as it docks: where they land.
                        if (typeof tfToast === 'function') tfToast('Saved');
                        const slip = document.getElementById('qb-slip');
                        slip.hidden = false; slip.style.height = '60px';
                        const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect();
                                             return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; };
                        return {rail: h.classList.contains('side-rail'), left: h.classList.contains('side-rail-left'),
                                bar: [Math.round(t.left), Math.round(t.width), Math.round(t.height)],
                                pad: [parseFloat(b.paddingLeft), parseFloat(b.paddingRight), parseFloat(b.paddingBottom)],
                                toast: box(document.querySelector('.tf-toast')), slip: box(slip),
                                w: innerWidth, h: innerHeight}; }""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return out, errs


def test_in_a_browser_the_bar_moves_into_the_strip_and_nowhere_else():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got, errs = _shapes()
    assert not errs, errs
    duo = got["duo"]
    assert duo["rail"] and not duo["left"], duo
    assert duo["bar"] == [duo["w"] - 84, 84, duo["h"]], ("on end, in the strip, top to bottom", duo)
    assert duo["pad"][1] == 84 and duo["pad"][2] < 60, ("the page clear of the strip, no room kept at its foot", duo)
    assert duo["toast"] and duo["toast"][1] <= duo["w"] - 84, ("a toast keeps out of the strip", duo)
    assert duo["slip"][1] == duo["w"] - 84 and duo["slip"][2] >= duo["h"] - 40, ("the slip at the foot, beside it", duo)
    left = got["duo_left"]
    assert left["rail"] and left["left"] and left["bar"][:2] == [0, 84] and left["pad"][0] == 84, left
    assert left["toast"] and left["toast"][0] >= 84 and left["slip"][0] == 84, left
    side = got["on_its_side"]
    assert not side["rail"], ("both sides inset alike: no strip", side)
    hand = got["in_the_hand"]
    assert not hand["rail"] and hand["bar"][1] > 300 and hand["pad"][2] > 80, ("the bar at the foot", hand)


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
