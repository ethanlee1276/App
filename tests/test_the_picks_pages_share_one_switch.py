"""The Picks pages share one switch: Most Likely, Report Picks, Best Parlays (step ABR, 22 November 2026).

Ethan, the Sunday afternoon: "We need to integrate the game report picks into the most likely picks page, like how
we have the picks button at the bottom in the tab. You can click it, it takes you to the most likely picks. It needs
to continue doing that, but it'll take you to the most likely picks page, and then there'll be an option in that
picks page to switch to the game report picks and parlays". What these hold:

  * the tab bar's Picks button still opens Most Likely;
  * Most Likely, Report Picks and Best Parlays each open on the same three-way switch, its own page filled;
  * a tap opens the page it names, and the tab bar's Picks stays lit on all three;
  * a league with no game reports (UFC) shows no switch; Report Picks' own door to Best Parlays is gone (the
    switch is that door, at the top of the page).

    python3 tests/test_the_picks_pages_share_one_switch.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
PAGES = ("likely", "reportpicks", "bestparlays")


def _section(view):
    s = HTML[HTML.index(f'<section class="view" id="view-{view}">'):]
    return s[:s.index("</section>")]


def test_the_picks_button_still_opens_most_likely():
    bar = HTML[HTML.index('<nav class="tabbar" id="tabbar"'):]
    bar = bar[:bar.index("</nav>")]
    assert re.search(r'<button class="tb-item nav-btn" data-view="likely"[^>]*>', bar)
    assert re.findall(r'data-view="(\w+)"', bar).count("likely") == 1


def test_each_picks_page_opens_on_the_same_switch_its_own_page_filled():
    for view in PAGES:
        sec = _section(view)
        nav = sec[sec.index('<nav class="picks-switch"'):sec.index("</nav>")]
        assert sec.index('<nav class="picks-switch"') < sec.index('class="section-title"'), f"{view}: at its top"
        assert re.findall(r'data-picks-go="(\w+)"', nav) == list(PAGES), view
        assert re.findall(r'class="ps-btn active" data-picks-go="(\w+)" aria-current="page"', nav) == [view], view
        assert ">Most Likely<" in nav and ">Report Picks<" in nav and ">Best Parlays<" in nav


def test_a_tap_opens_it_the_tab_stays_lit_and_a_league_without_reports_hides_it():
    assert 'const PICKS_PAGES = ["likely", "reportpicks", "bestparlays"];' in APP
    assert "switchView(b.dataset.picksGo, true);" in APP
    assert ("if (PICKS_PAGES.includes(lit)) {\n"
            "    document.querySelectorAll('.tabbar .nav-btn[data-view=\"likely\"]').forEach((b) => setSelected(b, true));") in APP
    assert "function markOffRows(hidden) {\n  markPicksSwitch(hidden);" in APP
    assert ".picks-switch {\n  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));" in CSS
    assert "ufc: [\"reportpicks\", \"bestparlays\"" in APP, "UFC has no game reports: one button left, no switch"


def test_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    from playwright.sync_api import sync_playwright
    import rendercheck
    board = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2026-W12", "recommendations": [],
                        "most_likely": [], "games": [], "player_stats": {}, "report_bets": [],
                        "game_parlays": {"games": []}})
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_function("() => typeof switchView === 'function' && state.data", timeout=20000)
                page.click('.tabbar .nav-btn[data-view="likely"]')
                page.wait_for_function("() => document.querySelector('#view-likely').classList.contains('active')",
                                       timeout=10000)
                page.click('#view-likely [data-picks-go="reportpicks"]')
                page.wait_for_function("() => document.querySelector('#view-reportpicks').classList.contains('active')",
                                       timeout=10000)
                lit = page.evaluate("""() => {
                    const b = document.querySelector('.tabbar .nav-btn[data-view="likely"]');
                    return b.classList.contains('active') || b.getAttribute('aria-current') === 'page'
                      || b.getAttribute('aria-selected') === 'true';
                }""")
                assert lit, "the Picks tab stays lit on Report Picks"
                page.click('#view-reportpicks [data-picks-go="bestparlays"]')
                page.wait_for_function("() => document.querySelector('#view-bestparlays').classList.contains('active')",
                                       timeout=10000)
                box = page.evaluate("""() => { const n = document.querySelector('#view-bestparlays .picks-switch');
                    const r = n.getBoundingClientRect(); return { w: r.width, wide: document.documentElement.scrollWidth - innerWidth,
                    rows: new Set([...n.querySelectorAll('.ps-btn')].map((b) => Math.round(b.getBoundingClientRect().top))).size }; }""")
                assert box["wide"] <= 0 and box["rows"] == 1, box
                assert not errors, errors
                ctx.close()
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                page.goto(f"http://127.0.0.1:{port}/index.html#likely", wait_until="load")
                page.wait_for_function("() => typeof applySport === 'function'", timeout=20000)
                # The league chip's own path: the sport set, then applied (applySport → markOffRows).
                page.evaluate("() => { state.sport = 'ufc'; applySport(); }")
                page.wait_for_timeout(300)
                hid = page.evaluate("() => [...document.querySelectorAll('.picks-switch')].every((n) => n.hidden)")
                assert hid, "UFC: no game reports, no switch"
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
