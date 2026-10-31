"""The iPhone Duo: the phone on its front screen, the desktop on the big one, and nothing lost between them.

Ethan, 2026-10-23: "Make app work seamlessly with iPhone duo. We need to
make it work with the front screen and the phone being open and big
screen. The big screen we can do a desktop sort of view. Also make it
work when the duo is half open."

Safari tells a page nothing about the fold (no Viewport Segments, no
Device Posture), so the Duo is three screen shapes and a resize. What
Safari gives the page, measured in the iOS 27.1 simulator: folded
382 x 580, open on its side 951 x 543 to 589, open upright 669 x 825;
Apple's pixels over three say 466 x 678 and 890 x 626. Half-folding has
been measured moving Safari to the front screen.

What these hold: the open shapes get the desktop shell (the sidebar, no
drawer, no tab bar, the header kept in place) through overrides an old
Safari can still parse, with the same two shapes in the stylesheet and in
app.js; a phone, a phone on its side and an iPad mini keep their layouts;
an open drawer or phone sheet closes when the screen opens; the block at
the top of the reading column is put back where it was after a fold, by
a jump rather than a glide; the header's date range steps aside where it
would run off the screen; and the short front screen sheds its
decoration so a pick shows on arrival.

Run directly: `python3 tests/test_the_iphone_duo_screens.py`
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

SIDE = "(min-width: 700px) and (min-height: 480px) and (min-aspect-ratio: 5/4)"
UPRIGHT = "(pointer: coarse) and (min-width: 600px) and (max-width: 720px) and (min-height: 700px)"
#: The third open shape (tests/test_every_fold_and_flip.py): a Fold's inner screen.
FOLD_INNER = "(pointer: coarse) and (min-width: 721px) and (max-width: 900px) and (min-height: 600px) and (min-aspect-ratio: 4/5)"


def _blocks(query_start):
    """[(index, body)] of every top-level @media block whose query starts so."""
    out = []
    for m in re.finditer(re.escape("@media " + query_start), CSS):
        i = CSS.index("{", m.start()) + 1
        depth = 1
        j = i
        while depth:
            depth += {"{": 1, "}": -1}.get(CSS[j], 0)
            j += 1
        out.append((m.start(), CSS[m.start():j]))
    return out


#: The two layout blocks among the open shapes' blocks, told by what they do.
#: Others may use the same shapes (the Liquid Glass look, 2026-10-24); every
#: one of them must spell the shapes exactly as UNFOLDED_MQ does.
LAYOUT_MARKS = (".shell, body.has-rail .shell { display: grid; }", ".tabbar, .riding-tray { display: none; }")


def _open_shape_blocks():
    return sorted(_blocks("(min-width: 700px) and (max-width: 9") + _blocks("(min-width: 700px) and (max-width: 7"))


def _duo_blocks():
    got = [(i, b) for i, b in _open_shape_blocks() if any(m in b for m in LAYOUT_MARKS)]
    assert len(got) == 2, [b[:90] for _i, b in got]
    return got


def test_the_open_shapes_are_the_same_in_the_stylesheet_and_the_script():
    m = re.search(r'const UNFOLDED_MQ = ((?:"[^"]+"\s*\+?\s*)+);', APP)
    assert m, "UNFOLDED_MQ is defined in app.js"
    js = "".join(re.findall(r'"([^"]+)"', m.group(1))).split(", ")
    assert js == [SIDE, UPRIGHT, FOLD_INNER], js
    for _i, block in _open_shape_blocks():
        query = block[:block.index("{")]
        side, upright, inner = [q.strip() for q in query[len("@media "):].split(",\n")]
        assert side.replace(" and (max-width: 900px)", "").replace(" and (max-width: 760px)", "") == SIDE, side
        assert upright == UPRIGHT, upright
        assert inner.replace("(max-width: 760px)", "(max-width: 900px)") == FOLD_INNER, inner


def test_the_overrides_are_plain_ands_an_old_safari_can_read():
    for _i, block in _open_shape_blocks():
        query = block[:block.index("{")]
        assert " not " not in query and "<" not in query and ">" not in query, query


def test_the_open_shell_comes_after_what_it_overrides():
    drawer = CSS.index("@media (max-width: 900px) {\n  .shell, body.has-rail .shell { display: block; }")
    phone = CSS.index("  body { padding-bottom: 84px; }        /* room for the bar */")
    (shell_at, shell), (chrome_at, chrome) = _duo_blocks()
    assert drawer < shell_at and phone < chrome_at, "a later rule of the same weight wins"
    assert ".shell, body.has-rail .shell { display: grid; }" in shell
    assert ".menu-toggle { display: none; }" in shell
    assert "position: sticky;" in shell and "transform: none;" in shell
    assert "body.menu-open #scrim { display: none; }" in shell
    assert ".tabbar, .riding-tray { display: none; }" in chrome
    assert "body, body.has-tray { padding-bottom: 0; }" in chrome
    assert "#nav-search, #nav-bell, #theme-toggle { display: grid; }" in chrome, \
        "the tab bar's More sheet held these; with the bar gone they come back"


def test_the_script_treats_the_open_screen_as_the_desktop():
    assert "if (!touch.matches || open.matches ||" in APP, "the header stays put on the open screen"
    assert 'matchMedia("(max-width: 760px)").matches) && !unfolded();' in APP, "not a phone when open"
    assert "\ninitFoldSeams();\n" in APP
    at = APP.index("function initFoldSeams()")
    body = APP[at:APP.index("\n}\n", at)]
    assert 'closeMobileMenu("the screen opened")' in body
    assert "moreSheetOpen(false)" in body
    assert 'root.style.scrollBehavior = "auto";' in body, "a jump: the page scrolls smoothly by its stylesheet"
    assert "Math.abs(width - was) / was < 0.2" in body, "a toolbar sliding is not a fold"


def test_the_header_date_steps_aside_where_it_would_run_off():
    assert "@media (max-width: 999px) {\n  #slate-date { display: none; }\n}" in CSS


def test_the_short_front_screen_sheds_its_decoration():
    got = _blocks("(max-width: 760px) and (max-height: 700px)")
    assert len(got) == 1, len(got)
    block = got[0][1]
    assert ".venue-band { display: none; }" in block
    assert ".sportbar-in .sport-btn .crest { width: 34px; height: 34px; }" in block


# --- in a browser, opt-in --------------------------------------------------------------
SHAPES = {
    # name: (width, height, touch, shell expected, tab bar expected)
    "folded": (382, 580, True, "drawer", True),
    "folded, by Apple's pixels": (466, 678, True, "drawer", True),
    "open on its side": (951, 543, True, "sidebar", False),
    "open on its side, by Apple's pixels": (890, 626, True, "sidebar", False),
    "open upright": (669, 825, True, "sidebar", False),
    "open upright, by Apple's pixels": (626, 890, True, "sidebar", False),
    "a phone": (390, 844, True, "drawer", True),
    "a phone on its side": (874, 402, True, "drawer", False),
    "an iPad mini": (744, 1133, True, "drawer", True),
    "a laptop": (1280, 800, False, "sidebar", False),
}


def _board():
    rows = [{"player": f"Player {i}", "team": "CHI", "opponent": "NE", "market": "rec_yds",
             "market_label": "Receiving Yards", "side": "over", "line": 40.5 + i, "odds": -150,
             "book": "draftkings", "model_prob": 0.7 - i * 0.01, "hit_prob": 0.7, "implied_prob": 0.6,
             "kind": "prop", "lane": "prop", "tier": "top", "bettable": True, "confidence": 7.0,
             "grade": "B", "projection": 50.0, "reasons": ["because"]} for i in range(14)]
    return {"sport": "nfl", "date": "2099-01-01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 14}, "lanes": {"prop": 14}},
            "games": [], "player_stats": {}}


def test_in_a_browser_every_shape_gets_its_layout_and_a_fold_keeps_your_place():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    body = json.dumps(_board())
    srv, port = rendercheck._serve()

    def open_page(browser, w, h, touch):
        ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=touch, has_touch=touch,
                                  service_workers="block")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
        for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
            page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
        page.goto(f"http://127.0.0.1:{port}/index.html#likely", wait_until="load")
        page.wait_for_timeout(1500)
        return ctx, page, errors

    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for name, (w, h, touch, shell, tabbar) in SHAPES.items():
                    ctx, page, errors = open_page(browser, w, h, touch)
                    got = page.evaluate("""() => {
                        const s = document.getElementById('sidebar').getBoundingClientRect();
                        const t = getComputedStyle(document.getElementById('tabbar')).display !== 'none';
                        let over = 0;
                        document.querySelector('.topbar').querySelectorAll('*').forEach((n) => {
                            const r = n.getBoundingClientRect(); if (r.width && r.right > innerWidth + 1) over++; });
                        return { shell: s.right > 0 && s.width > 0 ? 'sidebar' : 'drawer', tabbar: t, over,
                                 scroll: document.scrollingElement.scrollWidth };
                    }""")
                    assert got["shell"] == shell and got["tabbar"] == tabbar, (name, got)
                    assert got["over"] == 0, (name, "the header runs off the screen", got)
                    assert got["scroll"] <= w, (name, "the page scrolls sideways", got)
                    assert not errors, (name, errors)
                    ctx.close()
                # folded, scrolled to a pick, then open, folded, open upright, folded
                ctx, page, errors = open_page(browser, 382, 580, True)
                page.evaluate("document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 1400)")
                page.wait_for_timeout(300)
                probe = """() => { const main = document.querySelector('main').getBoundingClientRect();
                    const x = Math.min(innerWidth - 4, Math.max(0, main.left) + Math.max(24, main.width / 2));
                    let y = Math.max(0, document.querySelector('.topbar').getBoundingClientRect().bottom) + 8, b = null, big = null;
                    for (let i = 0; i < 6 && !b; i += 1, y += 32) { const g = foldAnchorAt(x, y);
                        if (g && g.big) { big = big || g.big; continue; } b = g; }
                    window.__held = b || big; return Math.round(window.__held.getBoundingClientRect().top); }"""
                for w, h in ((951, 543), (382, 580), (669, 825), (382, 580)):
                    was = page.evaluate(probe)
                    page.set_viewport_size({"width": w, "height": h})
                    page.wait_for_timeout(600)
                    now = page.evaluate("Math.round(window.__held.getBoundingClientRect().top)")
                    assert abs(now - was) <= 2, (w, h, was, now)
                # the phone's sheet, open on the front screen, closes when the screen opens
                page.click("#menu-toggle")
                page.wait_for_timeout(300)
                assert page.evaluate("document.body.classList.contains('more-open')")
                page.set_viewport_size({"width": 951, "height": 543})
                page.wait_for_timeout(300)
                assert not page.evaluate("document.body.classList.contains('more-open')")
                assert not errors, errors
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
