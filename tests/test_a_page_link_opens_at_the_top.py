"""A link to a page opens it at its top, and Most Likely holds still while
its board lands.

2026-10-25, Lighthouse on Most Likely (Ethan: "continue on making the app
better"): the page's layout shifted 0.139, past Google's 0.1 "good" line.
Two causes, both fixed here:

  - FIVE PAGES SHARED THEIR NAME WITH AN ELEMENT. The router reads the
    address's #fragment as a page name, and the browser reads it as an
    element to scroll to: `#likely` opened Most Likely and then scrolled
    the reader past its hero to `<div id="likely">`, the board's host.
    Opening any of the five from a link, a push alert, the Home Screen app
    or a reload did the same. The hosts are `likely-board`,
    `longshots-board`, `trending-board`, `players-board` and the bankroll
    box `bankroll-amount` now, and no element may take a page's name.
  - MOST LIKELY DREW ITS PLAIN TITLE, THEN TOOK IT AWAY when the one board
    landed (the board brings its own hero). The layout is chosen before the
    board arrives now (the NFL build carries the one board), and the board
    settles it when it lands.

Run directly: `python3 tests/test_a_page_link_opens_at_the_top.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CLASHED = ("likely", "longshots", "trending", "players", "bankroll")


def _pages():
    return set(re.findall(r'<section class="view[^"]*" id="view-([a-z0-9-]+)"', HTML))


def _ids():
    ids = set(re.findall(r'\bid="([A-Za-z][\w-]*)"', HTML))
    for f in glob.glob(os.path.join(ROOT, "web", "js", "*.js")):
        ids |= set(re.findall(r'\bid="([A-Za-z][\w-]*)"', open(f, encoding="utf-8").read()))
    return ids


def test_no_element_takes_a_pages_name():
    pages = _pages()
    assert len(pages) > 40 and set(CLASHED) <= pages, sorted(pages)
    both = sorted(pages & _ids())
    assert not both, f"an element shares a page's name, so a link to the page scrolls to it: {both}"


def test_the_five_hosts_have_their_new_names():
    for old, new in (("likely", "likely-board"), ("longshots", "longshots-board"), ("trending", "trending-board"),
                     ("players", "players-board"), ("bankroll", "bankroll-amount")):
        assert f'id="{new}"' in HTML and f'id="{old}"' not in HTML, old
        assert f'document.getElementById("{new}")' in APP and f'document.getElementById("{old}")' not in APP, old


def test_most_likely_chooses_its_layout_before_the_board_lands():
    i = APP.index("function renderLikely(")
    body = APP[i:APP.index("\n}\n", i)]
    toggle = body.index('lv.classList.toggle("ob-on", state.data ? oneBoardOn() : state.sport === "nfl")')
    assert toggle < body.index("if (!state.data) return;"), "chosen before the cold landing returns"
    assert body.count('classList.toggle("ob-on"') == 1
    assert ".view.ob-on > .section-title { display: none; }" in open(os.path.join(ROOT, "web", "css", "styles.css"),
                                                                       encoding="utf-8").read()


def test_in_a_browser_a_cold_link_stays_at_the_top_and_most_likely_holds_still():
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
    from test_the_first_screen_holds_still import _board
    body = json.dumps(_board())
    srv, port = rendercheck._serve()
    shifts = """window.__cls = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__cls += e.value; })
      .observe({ type: 'layout-shift', buffered: true });
      try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}"""
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name in CLASHED:
                    ctx = browser.new_context(viewport={"width": 412, "height": 823}, is_mobile=True, has_touch=True,
                                              device_scale_factor=1.75, service_workers="block")
                    page = ctx.new_page()
                    page.add_init_script(shifts)
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#{name}", wait_until="load")
                    page.wait_for_timeout(2500)
                    got[name] = page.evaluate("() => ({ y: scrollY, cls: window.__cls, title: getComputedStyle(document.getElementById('likely-title')).display, hero: !!document.querySelector('#view-likely .ob-hero') })")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for name, g in got.items():
        assert g["y"] == 0, (f"#{name} scrolled the page", g)
    likely = got["likely"]
    assert likely["hero"] and likely["title"] == "none", likely
    assert likely["cls"] < 0.05, ("Most Likely still shifts as its board lands", likely)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
