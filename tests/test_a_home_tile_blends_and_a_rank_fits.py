"""Three things on Ethan's two iPhone screenshots of the Home page
(2026-10-28, 7:57 PM), the first two circled: "the things I circled look
ugly. The stadium thing has these hard lines that look gross and the numbers
in the other one doesn't fit the box".

What these hold:

  * a game tile on the Home strip blends from the photograph to its foot:
    with the photograph hidden, no row of its edge differs from the next by
    more than a whisper. The teams' colour wash used to start in a line
    across the photo and stop in another over the weather (jumps of 52 and
    21 levels, dark theme; 74 and 29 light, measured on the old sheet);
  * a pick's rank is a pill that holds its number, inside its card's corner
    and placed by the card alone (it was a tab cut into the rounded corner,
    still naming the desktop's rank column, which Safari drew above the
    card);
  * in the iPhone app the bar is solid, and the strip under the clock holds
    still while the bar retracts beneath it: the page's words no longer run
    behind the logo, and the logo no longer slides up under the time.

The rules themselves are pinned in tests/test_no_hard_lines.py and
tests/test_what_floats_wears_glass.py; these are the pictures.

Run directly: `python3 tests/test_a_home_tile_blends_and_a_rank_fits.py`
(the browser checks with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
#: Adjacent rows of a tile's edge may differ by this much (0-255, any
#: channel). A smooth gradient moves about one level a row; the old seams
#: moved 20 to 74.
SEAM = 6


def test_the_clock_keeps_a_solid_strip_in_the_iphone_app():
    i = CSS.index("html.store-ios body::before, html.ios-home body::before {")
    rule = CSS[i:CSS.index("}", i)]
    # Its foot thins out over 8px since 2026-10-28, so with the bar away it
    # meets the page softly (tests/test_your_teams_colour_runs_through_the_bar.py).
    assert "position: fixed; top: 0;" in rule and "height: calc(env(safe-area-inset-top, 0px) + 8px);" in rule, rule
    assert "mask-image: var(--mask-strip-foot);" in rule, rule
    assert "background: var(--bg);" in rule and "pointer-events: none;" in rule, rule
    z = int(re.search(r"z-index: (\d+);", rule).group(1))
    bar = CSS[CSS.index(".topbar {\n  position: sticky; top: 0; z-index: "):]
    assert z == int(re.search(r"z-index: (\d+);", bar).group(1)) + 1, "just over the bar, under every sheet"
    app_bar = CSS[CSS.index("html.store-ios .topbar, html.ios-home .topbar {"):]
    assert app_bar[:app_bar.index("}")].split("{", 1)[1].strip().startswith("background: var(--bg);"), \
        "the bar is the strip's own colour, so the two meet without a seam"


def _board():
    def row(player, team, opp, market, label, line, odds, tier, prob):
        return {"player": player, "team": team, "opponent": opp, "market": market, "market_label": label,
                "side": "over", "line": line, "odds": odds, "book": "DraftKings", "model_prob": prob,
                "hit_prob": prob, "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": tier,
                "bettable": True, "confidence": 7.0, "grade": "B", "projection": line + 2, "reasons": ["because"],
                "recommended": True, "since": "2026-10-28T11:08:00Z", "game_date": "2099-01-03",
                "checks": {"model": True, "matchup": True, "market": True, "record": None}}
    rows = [row("Mark Andrews", "BAL", "BUF", "rec", "Receptions", 3.5, -205, "top", 0.6),
            row("T.J. Hockenson", "MIN", "DET", "rec", "Receptions", 3.5, -219, "top", 0.65),
            row("Jordan Addison", "MIN", "DET", "rec_yds", "Receiving Yards", 29.5, -190, "top", 0.59),
            row("Kyler Murray", "ARI", "DAL", "pass_cmp", "Completions", 17.5, -208, "strong", 0.65)]
    wx = lambda t: {"temp_f": t, "wind_mph": 8, "wind_dir": "W", "measured": True}  # noqa: E731
    games = [{"home": "GB", "away": "CAR", "date": "2099-01-01", "kickoff": "20:15", "spread": -3.5,
              "favorite": "GB", "total": 48.0, "home_ml": -184, "away_ml": 180, "weather": wx(50),
              "weather_checked": True},
             {"home": "BUF", "away": "BAL", "date": "2099-01-03", "kickoff": "13:00", "spread": -3.5,
              "favorite": "BUF", "total": 51.5, "home_ml": -180, "away_ml": 150, "weather": wx(65),
              "weather_checked": True}]
    return {"sport": "nfl", "date": "2099-W01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 3, "strong": 1}, "lanes": {"prop": 4}},
            "board_shelves": [{"key": "likely", "title": "Most likely", "rows": rows}],
            "games": games, "player_stats": {}}


def _page(browser, port, theme, standalone=False):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True, service_workers="block", color_scheme=theme)
    page = ctx.new_page()
    body = json.dumps(_board())
    page.add_init_script(("Object.defineProperty(navigator, 'standalone', { get: () => true });" if standalone else "")
                         + "try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                         f" localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', '{theme}'); }} catch (e) {{}}")
    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
    return ctx, page


def _seams(png: bytes, dpr: int = 2) -> list:
    """The biggest row-to-row changes down a strip 3-9px in from a tile's
    left edge (left of every chip and word), its rounded corners left out."""
    try:
        from PIL import Image
    except ImportError:                  # the browser test asks for Pillow first
        return []
    im = Image.open(io.BytesIO(png)).convert("RGB")
    pix, (w, h) = im.load(), im.size
    rows = []
    for y in range(h):
        px = [pix[x, y] for x in range(3 * dpr, 9 * dpr)]
        rows.append([sum(p[c] for p in px) / len(px) for c in range(3)])
    jumps = [(max(abs(rows[y + 1][c] - rows[y][c]) for c in range(3)), y // dpr)
             for y in range(20 * dpr, h - 20 * dpr)]
    return sorted(jumps, reverse=True)[:3]


def test_in_a_browser_the_tile_blends_the_rank_fits_and_the_clock_holds_still():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
        import PIL  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright or no Pillow)")
        return
    import rendercheck
    srv, port = rendercheck._serve()
    found = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for theme in ("dark", "light"):
                    ctx, page = _page(browser, port, theme)
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_function("() => document.querySelector('#games .game-card')"
                                           " && document.querySelector('#likely-top .ob-rank')", timeout=20000)
                    # The photograph hidden, the layers over it are what is left to blend.
                    page.add_style_tag(content=".venue-photo, .stadium-wrap svg { visibility: hidden !important; }")
                    page.evaluate("""() => { const c = document.querySelector('#games .game-card');
                      window.scrollTo(0, window.scrollY + c.getBoundingClientRect().top - 140); }""")
                    page.wait_for_timeout(400)
                    found[f"tile {theme}"] = _seams(page.locator("#games .game-card").first.screenshot())
                    found[f"ranks {theme}"] = page.evaluate("""() => [...document.querySelectorAll('#likely-top .ob-rank')].map((r) => {
                      const c = r.closest('.ob-card').getBoundingClientRect(), b = r.getBoundingClientRect();
                      return { n: r.textContent.trim(), top: b.top - c.top, left: b.left - c.left, inside: b.right < c.right && b.bottom < c.bottom,
                               fits: r.scrollWidth <= r.clientWidth + 1 && r.scrollHeight <= r.clientHeight + 1, h: b.height,
                               radius: getComputedStyle(r).borderTopLeftRadius }; })""")
                    ctx.close()
                # The iPhone app, a 47px status bar, the bar half retracted.
                ctx, page = _page(browser, port, "dark", standalone=True)
                cdp = ctx.new_cdp_session(page)
                try:
                    cdp.send("Emulation.setSafeAreaInsetsOverride", {"insets": {"top": 47, "bottom": 34, "left": 0, "right": 0}})
                    inset = True
                except Exception:                                   # noqa: BLE001
                    inset = False
                if inset:
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_function("() => document.querySelector('#games .game-card')", timeout=20000)
                    page.evaluate("window.scrollTo(0, 900)")
                    page.wait_for_timeout(400)
                    # Half retracted, set outright: how the bar follows the finger
                    # is tests/test_headertuck.py's; what shows under the clock
                    # while it does is this one's.
                    page.evaluate("document.querySelector('.topbar').style.transform = 'translateY(-60px)'")
                    page.wait_for_timeout(150)
                    found["bar moved"] = page.evaluate("document.querySelector('.topbar').style.transform")
                    from PIL import Image
                    im = Image.open(io.BytesIO(page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": 46}))).convert("RGB")
                    pix, (w, h) = im.load(), im.size
                    px = [pix[x, y] for y in range(h) for x in range(w)]
                    found["under the clock"] = max(max(abs(p[c] - px[0][c]) for c in range(3)) for p in px)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for theme in ("dark", "light"):
        worst = found[f"tile {theme}"][0]
        assert worst[0] <= SEAM, f"a {theme} tile changes by {worst[0]:.0f} levels at {worst[1]}px: a line"
        ranks = found[f"ranks {theme}"]
        assert [r["n"] for r in ranks] == ["#1", "#2", "#3", "#4"], ranks
        for r in ranks:
            assert r["fits"] and r["inside"] and r["h"] >= 18, r
            assert 4 <= r["top"] <= 12 and 4 <= r["left"] <= 12, ("in the corner's room, off its curve", r)
            assert r["radius"] != "0px", r
    if "under the clock" in found:
        assert found["bar moved"].startswith("translateY(-"), found["bar moved"]
        assert found["under the clock"] <= 3, ("the bar or the page shows under the clock", found["under the clock"])
    else:
        print("      (the status-bar strip unchecked: this Chromium cannot emulate a safe area)")


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
