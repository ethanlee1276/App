"""Every fold and flip: each shape and posture laid out the way the phone's own apps do it.

Ethan, 2026-10-24: "make it for, like, any Galaxy Flip or Fold phones, all
form factors ... every single form factor", then "make it unique for that
phone ... look at how the iPhone Duo is, how other apps are doing it". The
Duo's apps run a list beside its item when open (Notes, Messages), put the
game above the stats when half folded (MLB), and lay out the cover screen
on its own; Galaxy and Pixel foldables do the same through the Viewport
Segments API, which Chrome ships and Safari 27.1 carries behind a flag.

What these hold: the near-square inner screen of a Fold, a Pixel Fold or an
OnePlus Open is an open shape in the stylesheet and the script alike, and a
tablet held upright is not; a wide open screen held by a finger (or folded
like a book) keeps the board beside the pick it opened, the board pane is
drawn while it shows, and the split goes when the screen folds; folded like
a book the panes meet at the hinge; folded like a laptop the page keeps to
the top half and the controls fill the bottom; a Flip's cover gets the slim
chrome and the narrowest covers a two-row pick; the section is last in the
stylesheet so the phone's rules cannot override it; and the installed app
is not locked to portrait (Android 16 ignores the lock on these screens).

Run directly: `python3 tests/test_every_fold_and_flip.py`
(the browser half: `QB_BROWSER_TESTS=1`, with Playwright).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
SECTION = CSS[CSS.index("EVERY FOLD AND FLIP (Ethan"):]


def test_the_section_is_last_so_nothing_overrides_it():
    tail = CSS[CSS.index("   EVERY FOLD AND FLIP (Ethan"):]
    assert "@media (vertical-viewport-segments: 2)" in tail and tail.rstrip().endswith("}")
    assert CSS.count("EVERY FOLD AND FLIP (Ethan") == 1


def test_a_folds_inner_screen_is_an_open_shape_in_both_places():
    inner = ("(pointer: coarse) and (min-width: 721px) and (max-width: 900px) and (min-height: 600px) "
             "and (min-aspect-ratio: 4/5)")
    assert inner in "".join(re.findall(r'"([^"]+)"', APP[APP.index("const UNFOLDED_MQ"):APP.index("function unfolded")]))
    assert inner in CSS and inner.replace("900px", "760px") in CSS


def test_the_list_stays_beside_the_pick_it_opened():
    at = APP.index("function paneSplit(")
    body = APP[at:APP.index("\n}\n", at)]
    assert 'const TWO_PANE_MQ = "(pointer: coarse) and (min-width: 900px) and (min-height: 480px), "' in APP
    assert '"(horizontal-viewport-segments: 2)"' in APP
    assert 'document.body.classList.toggle("two-pane", !!list)' in body
    assert "PANE_DETAILS.includes(leaving) ? _paneList" in body, "the next pick replaces the right pane only"
    assert "  paneSplit(name, leaving);\n" in APP, "every view switch decides it"
    assert 'view.classList.contains("pane-list")' in APP, "the board pane is drawn while it shows"
    assert 'if (_paneList && !split.matches) paneSplit(state.view, "");' in APP, "folding shut drops the split"
    for rule in ("body.two-pane main { display: grid;", "body.two-pane .view.pane-list { display: block;",
                 "body.two-pane .sidebar, body.two-pane .rail { display: none; }",
                 'grid-template-areas: "who odds ring" "checks checks checks"'):
        assert rule in SECTION, rule


def test_the_hinge_decides_the_postures():
    book = SECTION[SECTION.index("@media (horizontal-viewport-segments: 2)"):]
    assert "env(viewport-segment-width 0 0, 1fr) env(viewport-segment-width 1 0, 1fr)" in book
    assert "env(viewport-segment-left 1 0, 0px) - env(viewport-segment-right 0 0, 0px)" in book
    flex = SECTION[SECTION.index("@media (vertical-viewport-segments: 2)"):]
    assert "top: env(viewport-segment-bottom 0 0);" in flex, "the deck starts where the top half ends"
    assert "padding-bottom: calc(100vh - env(viewport-segment-bottom 0 0, 100vh));" in flex
    assert ".tb-item { display: flex;" in flex, "the deck carries the tab bar's look on a wide Fold too"


def test_the_covers():
    narrow = SECTION[SECTION.index("@media (max-width: 359px)"):]
    assert 'grid-template-areas: "who who" "odds ring" "checks checks";' in narrow[:400]
    glance = SECTION[SECTION.index("@media (max-width: 480px) and (max-height: 480px)"):]
    assert ".tb-item { font-size: 0;" in glance[:900] and ".ob-hero, .venue-band { display: none; }" in glance[:900]


def test_the_installed_app_turns_with_the_screen():
    web = json.load(open(os.path.join(ROOT, "web", "manifest.webmanifest"), encoding="utf-8"))
    twa = json.load(open(os.path.join(ROOT, "deploy", "twa", "twa-manifest.json"), encoding="utf-8"))
    assert web["orientation"] == "any" and twa["orientation"] == "any"


# --- in a browser, opt-in --------------------------------------------------------------
SHELLS = {
    # name: (w, h, shell)
    "Galaxy Fold cover": (280, 653, "drawer"),
    "Galaxy Z Fold7 inner": (750, 832, "sidebar"),
    "Pixel 9 Pro Fold inner": (791, 820, "sidebar"),
    "OnePlus Open inner": (813, 756, "sidebar"),
    "Pixel Fold inner": (841, 701, "sidebar"),
    "iPad Air upright": (820, 1180, "drawer"),
    "iPad mini": (744, 1133, "drawer"),
    "Galaxy Z Flip inner": (412, 1006, "drawer"),
}


def _board():
    rows = [{"player": f"Player Name {i}", "team": "CHI", "opponent": "NE", "market": "rec_yds",
             "market_label": "Receiving Yards", "side": "over", "line": 40.5 + i, "odds": -150,
             "book": "draftkings", "model_prob": 0.7 - i * 0.01, "hit_prob": 0.7, "implied_prob": 0.6,
             "kind": "prop", "lane": "prop", "tier": "top", "bettable": True, "confidence": 7.0,
             "grade": "B", "projection": 50.0, "reasons": ["because"]} for i in range(10)]
    return {"sport": "nfl", "date": "2099-01-01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 10}, "lanes": {"prop": 10}},
            "games": [], "player_stats": {}}


def test_in_a_browser_each_shape_and_posture():
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

    def open_page(browser, w, h, hinge=None):
        ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True,
                                  service_workers="block")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        if hinge:
            # Chromium's own foldable emulation: a display feature splits the
            # viewport into segments, as a Galaxy or Pixel foldable does.
            ctx.new_cdp_session(page).send("Emulation.setDeviceMetricsOverride", {
                "width": w, "height": h, "deviceScaleFactor": 2, "mobile": True,
                "displayFeature": {"orientation": hinge[0], "offset": hinge[1], "maskLength": hinge[2]}})
        page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
        for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
            page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
        page.goto(f"http://127.0.0.1:{port}/index.html#likely", wait_until="load")
        page.wait_for_timeout(1300)
        return ctx, page, errors

    rect = "(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }"
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, (w, h, shell) in SHELLS.items():
                    ctx, page, errors = open_page(browser, w, h)
                    got = page.evaluate("""() => { const s = document.getElementById('sidebar').getBoundingClientRect();
                        return { shell: s.right > 0 && s.width > 0 && s.left >= 0 ? 'sidebar' : 'drawer',
                                 scroll: document.scrollingElement.scrollWidth - innerWidth }; }""")
                    assert got["shell"] == shell and got["scroll"] <= 0, (name, got)
                    assert not errors, (name, errors)
                    ctx.close()
                # The narrowest cover: the name has the card's width, not a sliver.
                ctx, page, _e = open_page(browser, 280, 653)
                assert page.evaluate(rect, "#view-likely .ob-card .ob-what")[2] >= 150
                ctx.close()
                # A Flip's cover: icons only, a slim bar.
                ctx, page, _e = open_page(browser, 360, 374)
                bar = page.evaluate(rect, "#tabbar")
                assert bar[3] <= 64, bar
                assert page.evaluate("getComputedStyle(document.querySelector('.tb-item')).fontSize") == "0px"
                ctx.close()
                # The Duo on its side: the board stays beside the pick; folded, the pick is the page.
                ctx, page, errors = open_page(browser, 951, 543)
                page.click("#view-likely .ob-card .ob-who")
                page.wait_for_timeout(900)
                state = "() => ({two: document.body.classList.contains('two-pane'), active: document.querySelector('.view.active').id, list: (document.querySelector('.view.pane-list') || {}).id || ''})"
                assert page.evaluate(state) == {"two": True, "active": "view-prop", "list": "view-likely"}
                left, det = page.evaluate(rect, "#view-likely"), page.evaluate(rect, "#view-prop")
                assert left[2] >= 300 and det[0] >= left[0] + left[2] - 1, (left, det)
                page.click("#view-likely .ob-card:nth-of-type(2) .ob-who")
                page.wait_for_timeout(700)
                assert page.evaluate(state)["list"] == "view-likely", "the next pick replaces the right pane"
                page.set_viewport_size({"width": 382, "height": 580})
                page.wait_for_timeout(500)
                assert page.evaluate(state) == {"two": False, "active": "view-prop", "list": ""}
                assert not errors, errors
                ctx.close()
                # A Surface Duo folded like a book: the panes meet at the hinge.
                ctx, page, _e = open_page(browser, 1114, 720, ("vertical", 540, 34))
                page.click("#view-likely .ob-card .ob-who")
                page.wait_for_timeout(900)
                left, det = page.evaluate(rect, "#view-likely"), page.evaluate(rect, "#view-prop")
                assert (round(left[0]), round(left[2]), round(det[0]), round(det[2])) == (0, 540, 574, 540), (left, det)
                ctx.close()
                # A Flip on the table: the page above, the controls filling the bottom half.
                ctx, page, _e = open_page(browser, 412, 1006, ("horizontal", 492, 22))
                bar = page.evaluate(rect, "#tabbar")
                assert round(bar[1]) == 492 and round(bar[1] + bar[3]) == 1006, bar
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
