"""Every page opens without a script error, on every kind of screen — the crash check a store app needs.

Ethan, 2026-10-24: "more professional and more bug checks and all that". The
bug scan (engine/bugscan) hears of a crash after someone hits it; this finds
it first. Each page the navigation can open, plus the Record, My Bets,
Fantasy, Prediction Market and Account pages, is opened on a phone, a Flip's
cover, a Fold's inner screen, the open Duo on its side, a desktop and the Play app, on a
board with picks on it, and must raise nothing: no uncaught error, no
rejected promise. Network refusals (the test serves only the site itself)
are not errors of the page's own.

Opt-in, like the other browser checks: `QB_BROWSER_TESTS=1`, with
Playwright. The nightly code-health run includes it.

Run directly: `QB_BROWSER_TESTS=1 python3 tests/test_every_page_opens_clean.py`
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
#: Pages reached other than through a nav button's data-view.
EXTRA = ["record", "mybets", "fantasy", "intel", "account", "memes", "ufc", "methodology", "about"]
SCREENS = {"phone": (390, 844, True), "flip cover": (360, 374, True), "fold inner": (750, 832, True),
           "duo open": (951, 543, True), "desktop": (1280, 800, False),
           # The Play build (web/js/boot.js QB_STORE_APP): no sportsbook, no league art.
           "play app": (390, 844, True)}


def pages() -> list:
    views = sorted(set(re.findall(r'data-view="([a-z-]+)"', HTML)))
    return views + [p for p in EXTRA if p not in views]


def test_the_page_list_covers_the_navigation():
    got = pages()
    assert {"recommended", "likely", "live", "edge", "props", "tools", "ask", "standings"} <= set(got), got
    for p in got:
        assert f'id="view-{p}"' in HTML or p in EXTRA, p


def _board():
    rows = [{"player": f"Player Name {i}", "team": "CHI", "opponent": "NE", "market": "rec_yds",
             "market_label": "Receiving Yards", "side": "over", "line": 40.5 + i, "odds": -150,
             "book": "draftkings", "model_prob": 0.7 - i * 0.01, "hit_prob": 0.7, "implied_prob": 0.6,
             "kind": "prop", "lane": "prop", "tier": "top", "bettable": True, "confidence": 7.0,
             "grade": "B", "projection": 50.0, "reasons": ["because"], "recommended": True}
            for i in range(8)]
    return {"sport": "nfl", "date": "2099-W01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 8}, "lanes": {"prop": 8}},
            "games": [{"home": "CHI", "away": "NE", "date": "2099-01-01", "kickoff": "13:00",
                       "spread": -3.5, "total": 44.5}], "player_stats": {}}


def test_in_a_browser_every_page_opens_clean_on_every_screen():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    body = json.dumps(_board())
    srv, port = rendercheck._serve()
    failures = []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for screen, (w, h, touch) in SCREENS.items():
                    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=touch,
                                              has_touch=touch, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    app = "?app=play" if screen == "play app" else ""
                    page.goto(f"http://127.0.0.1:{port}/index.html{app}", wait_until="load")
                    page.wait_for_timeout(1000)
                    for name in pages():
                        errors.clear()
                        page.evaluate(f"location.hash = '#{name}'")
                        page.wait_for_timeout(500)
                        if errors:
                            failures.append((screen, name, errors[:2]))
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not failures, failures


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
