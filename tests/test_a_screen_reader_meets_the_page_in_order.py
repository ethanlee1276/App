"""What a keyboard or a screen reader meets: the closed drawer out of reach,
the headings in order, a game card's name carrying what a glance gets.

2026-10-25, Lighthouse across the front screen, the Record, About, the
account and Most Likely (Ethan: "continue on making the app better"):
accessibility 96-98, now 100. What it found, and what holds it:

  - THE CLOSED DRAWER WAS ONLY SLID AWAY. Under 901px the sidebar is a
    drawer pushed off screen with a transform, and a keyboard's Tab and a
    screen reader's swipe walked into it while it sat there (Lighthouse
    read its Record link as a skip link with nowhere to land). Closed, it
    is hidden now: the visibility flips after the slide out ends and before
    the slide in starts, and the open Duo's sidebar beside the page stays
    visible.
  - MOST LIKELY JUMPED FROM ITS h1 TO h3: its tier titles are h2.
  - A GAME CARD IS ONE BUTTON whose name stands in for everything on it, so
    the name now says when it starts and how many picks it holds, as the
    card shows them ("Open picks for Patriots at Bears, Sun, Oct 25, 1:00 PM,
    3 picks").

Run directly: `python3 tests/test_a_screen_reader_meets_the_page_in_order.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_closed_drawer_is_hidden_and_the_open_one_shown():
    i = CSS.index("CLOSED IS HIDDEN, not only slid away")
    block = CSS[i:CSS.index("THUMB TARGETS IN THE DRAWER", i)]
    assert "transform: translateX(-102%); visibility: hidden;" in block
    assert "visibility 0s linear var(--dur-base)" in block, "hidden only once the slide out has ended"
    assert re.search(r"body\.menu-open \.sidebar \{[^}]*visibility: visible; transition-delay: 0s;", block), \
        "shown before the slide in starts"
    # A tablet's sidebar on its side sits beside the page, never closed.
    assert "will-change: auto; transform: none; transition: none; visibility: visible;" in CSS
    # The rescue for a drawer that does not arrive forces it visible too.
    assert '["visibility", "visible"]' in APP


def test_most_likely_goes_from_its_h1_to_h2():
    assert '<h1 class="ob-h1">' in _fn("obHeroHTML")
    tiers = _fn("obTierSections")
    assert '<h2 class="ob-sec-title">' in tiers and "</h2>" in tiers and "<h3" not in tiers


def test_a_game_cards_name_says_when_and_how_many_picks():
    card = _fn("gameCard")
    assert 'at ${escapeHtml(teamName(g.home))}${doorFacts}">' in card
    i = card.index("const doorFacts")
    facts = card[card.index("const when", i - 300):card.index(";", i) + 1]
    assert "!isLive && !isFinal ? whenLabel(g.date, g.kickoff)" in facts, "a start time only before the start"
    assert 'replace(/\\s*·\\s*/g, ", ")' in facts, "read as a pause, not a middle dot"
    assert "${n} pick${n === 1 ? \"\" : \"s\"}" in facts and facts.startswith("const when") and "escapeHtml(" in facts


def test_in_a_browser_the_drawer_is_out_of_reach_until_it_opens():
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
    from test_every_page_opens_clean import _board
    import json
    body = json.dumps(_board())
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, (w, h, touch) in {"phone": (390, 844, True), "tablet": (820, 1180, True),
                                             "tablet on its side": (1133, 744, True), "desktop": (1280, 900, False)}.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=touch, has_touch=touch,
                                              service_workers="block", reduced_motion="reduce")
                    page = ctx.new_page()
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_timeout(1200)
                    probe = "() => { const s = document.getElementById('sidebar'); const r = s.getBoundingClientRect(); return { vis: getComputedStyle(s).visibility, onscreen: r.right > 8 && r.left < innerWidth }; }"
                    g = {"closed": page.evaluate(probe)}
                    # Tab through the page: does focus ever land inside the drawer?
                    inside = False
                    for _ in range(40):
                        page.keyboard.press("Tab")
                        if page.evaluate("() => !!(document.activeElement && document.activeElement.closest('#sidebar'))"):
                            inside = True
                            break
                    g["tab_reaches_it"] = inside
                    if name == "tablet":
                        page.evaluate("document.getElementById('menu-toggle').click()")
                        page.wait_for_timeout(500)
                        g["open"] = page.evaluate(probe)
                        page.evaluate("document.getElementById('menu-toggle').click()")
                        page.wait_for_timeout(900)
                        g["reclosed"] = page.evaluate(probe)
                    if name == "phone":
                        page.evaluate("switchView('likely')")
                        page.wait_for_timeout(1200)
                        g["levels"] = page.evaluate("() => [...document.querySelectorAll('#view-likely h1, #view-likely h2, #view-likely h3, #view-likely h4')].filter((e) => e.offsetParent).map((e) => +e.tagName[1])")
                        g["card"] = page.evaluate("() => { const c = document.querySelector('#view-recommended .game-card'); return c && c.getAttribute('aria-label'); }")
                    got[name] = g
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for name in ("phone", "tablet"):
        assert got[name]["closed"]["vis"] == "hidden" and not got[name]["tab_reaches_it"], (name, got[name])
    assert got["tablet"]["open"] == {"vis": "visible", "onscreen": True}, got["tablet"]
    assert got["tablet"]["reclosed"]["vis"] == "hidden", got["tablet"]
    # The sidebar beside the page, never closed: a tablet on its side and a
    # desktop (the open Duo wears the app since 2026-10-29: its menu is the sheet).
    for name in ("tablet on its side", "desktop"):
        assert got[name]["closed"] == {"vis": "visible", "onscreen": True} and got[name]["tab_reaches_it"], (name, got[name])
    levels = got["phone"]["levels"]
    assert levels and all(b - a <= 1 for a, b in zip(levels, levels[1:])), ("a heading skips a level", levels)
    card = got["phone"]["card"]
    assert card and card.startswith("Open ") and " at " in card, card


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
