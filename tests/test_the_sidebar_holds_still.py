"""The sidebar holds still and scrolls up and down only (styles.css .sidebar,
app.js paneOwned, swipeOwned, the touch listeners).

Ethan, 2026-10-29, his open iPhone Duo with the sidebar circled: "I'm able
to move this bar around and it's weird so make it solid and only able to
scroll up and down". The pane scrolled in both directions (overflow-y: auto
makes the other axis auto too), its content rubber-banded past either end
and sideways, and a pull down inside it was the page's pull to refresh
("Release to refresh" on his screen). What these hold:

  * nothing in the sidebar scrolls sideways, there is no rubber band, and a
    finger can pan it up and down only (a pinch still zooms);
  * a pull or a sideways swipe that begins inside the sidebar, the menu
    sheet or any pane that scrolls on its own is that pane's: never the
    page's pull to refresh, never a jump to the next league;
  * a pull on the page itself still refreshes it.

Run directly: `python3 tests/test_the_sidebar_holds_still.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
CSS, APP = READ("web", "css", "styles.css"), READ("web", "js", "app.js")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_pane_scrolls_up_and_down_only():
    base = CSS[CSS.index(".sidebar { position: sticky;"):]
    base = base[:base.index("}")]
    assert "overflow-x: hidden; overflow-y: auto; overscroll-behavior: none; touch-action: pan-y pinch-zoom;" in base
    # No later rule for the sidebar at any width gives either back.
    for m in re.finditer(r"(?m)^\s*(?:body[.\w-]* )?\.sidebar(?:\.[\w-]+)? \{([^}]*)\}", CSS):
        at = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
        if at == CSS.index(".sidebar { position: sticky;"):
            continue
        for prop in ("overflow", "overscroll", "touch-action"):
            assert prop not in m.group(1), (prop, m.group(0)[:120])


def test_a_gesture_that_starts_in_a_pane_is_the_panes():
    owned = _fn("paneOwned")
    assert 'n.matches(".sidebar, .sb-grip, .more-sheet, .rail")' in owned
    assert 'o === "auto" || o === "scroll"' in owned and "n.scrollHeight > n.clientHeight + 4" in owned
    assert "atTop: window.scrollY <= 0 && !paneOwned(e.target)" in APP, "no pull to refresh from inside a pane"
    assert ".lb-table, table, .sidebar, .sb-grip, .more-sheet\")) return true;" in _fn("swipeOwned"), "nor a league swipe"


TOUCH = """async ({x0, y0, x1, y1}) => {
  const t = (x, y) => new Touch({identifier: 1, target: document.elementFromPoint(x0, y0), clientX: x, clientY: y});
  const el = document.elementFromPoint(x0, y0);
  const fire = (type, x, y) => el.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true,
      touches: type === 'touchend' ? [] : [t(x, y)], changedTouches: [t(x, y)]}));
  fire('touchstart', x0, y0);
  for (let i = 1; i <= 6; i++) fire('touchmove', x0 + (x1 - x0) * i / 6, y0 + (y1 - y0) * i / 6);
  const p = document.getElementById('ptr');
  const mid = p && !p.hidden ? p.textContent : '';
  fire('touchend', x1, y1);
  return {mid, inSidebar: !!el.closest('.sidebar')};
}"""


def test_on_the_open_duo_the_pane_holds_and_the_page_still_refreshes():
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
                # The open Duo: a finger, 703 by 1000 (styles.css "The open Duo").
                ctx = browser.new_context(viewport={"width": 703, "height": 1000}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_timeout(2500)
                got["style"] = page.evaluate("""() => { const s = getComputedStyle(document.getElementById('sidebar'));
                    return [s.position, s.overflowX, s.overflowY, s.overscrollBehaviorY, s.touchAction]; }""")
                got["sideways"] = page.evaluate("""() => { const s = document.getElementById('sidebar');
                    s.scrollLeft = 60; return s.scrollLeft; }""")
                r = page.evaluate("""() => { const b = document.getElementById('sidebar').getBoundingClientRect();
                    return [b.left, b.right, b.top, b.bottom]; }""")
                mid = (r[0] + r[1]) / 2
                got["sport0"] = page.evaluate("state.sport")
                got["pull_in_pane"] = page.evaluate(TOUCH, {"x0": mid, "y0": r[2] + 120, "x1": mid, "y1": r[2] + 260})
                got["swipe_in_pane"] = page.evaluate(TOUCH, {"x0": r[1] - 20, "y0": r[2] + 300, "x1": r[0] + 20, "y1": r[2] + 302})
                page.wait_for_timeout(400)
                got["sport1"] = page.evaluate("state.sport")
                got["pull_on_page"] = page.evaluate(TOUCH, {"x0": 520, "y0": 420, "x1": 520, "y1": 560})
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    # Fixed, not sticky, since it comes down the page with you (tests/test_the_sidebar_follows_the_page.py).
    assert got["style"] == ["fixed", "hidden", "auto", "none", "pan-y pinch-zoom"], got["style"]
    assert got["sideways"] == 0, "nothing to scroll sideways"
    assert got["pull_in_pane"]["inSidebar"] and got["pull_in_pane"]["mid"] == "", ("the pane's own pull", got)
    assert got["swipe_in_pane"]["inSidebar"] and got["sport1"] == got["sport0"], ("no league jump from the pane", got)
    assert not got["pull_on_page"]["inSidebar"] and got["pull_on_page"]["mid"] == "Release to refresh", got


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
