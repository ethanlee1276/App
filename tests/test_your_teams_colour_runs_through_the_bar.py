"""Your team's colour runs through the top bar and out of it, with no rule
where the bar ends (Ethan, 2026-10-28, an iPhone screenshot of the MLB Home
with the top bar and the league row circled: "the colors up here could be
blended better too. Still have sharp lines").

With "Your team's colours" on, the colour spilled from the bar's foot at 22%,
under a bar that wore none of it: a dark band, then a blue one, ruled where
they met (28 levels from one row of pixels to the next, measured on the
iPhone app's bar with the Lions followed; 54 in the light theme).

What these hold:

  * the bar wears the colour (12% of it, under its own words), the strip
    under the clock in the iPhone app wears it too, and the same colour runs
    on past the bar's foot and thins out over the league row;
  * the bar's soft edge starts from the bar's tinted ground, not the plain one;
  * the strip under the clock ends in an 8px soft foot, so with the bar slid
    away it meets the page without a rule;
  * in a browser, the iPhone app at rest, with the bar slid away, in both
    themes, with the setting on and off: no row of the top of the page
    differs from the next by more than a whisper.

Run directly: `python3 tests/test_your_teams_colour_runs_through_the_bar.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
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
#: Adjacent rows of the top of the page may differ by this much (0-255, any
#: channel). The old foot of the bar moved 28 (dark) and 54 (light).
SEAM = 6


def _rule(selector: str) -> str:
    i = CSS.index(selector + " {")
    return CSS[i:CSS.index("}", i) + 1]


def test_the_bar_wears_the_colour_and_the_spill_runs_on_from_it():
    root = CSS[CSS.index(":root {"):CSS.index("}", CSS.index(":root {"))]
    assert "--team-ground: color-mix(in oklab, var(--team-1) 12%, transparent);" in root
    assert "--grad-team-ground: linear-gradient(var(--team-ground), var(--team-ground));" in root
    spill = re.search(r"--grad-team-spill: (linear-gradient\(.*\));", CSS).group(1)
    assert spill.startswith("linear-gradient(180deg, var(--team-ground) calc(100% - 48px),"), \
        "flat through the bar, the same 12% at its foot"
    assert spill.endswith(", transparent)"), "and nothing at the end of the run"
    edge = _rule(".team-tint .topbar::after")
    assert "top: 0; z-index: -1; height: calc(100% + 48px);" in edge, "the bar and the run below it, under the bar's words"
    assert "background: var(--grad-team-spill);" in edge
    fade = _rule(".team-tint")
    assert "--grad-bar-fade: linear-gradient(180deg, color-mix(in oklab, var(--team-1) 12%, var(--topbar-bg)), transparent);" in fade, \
        "the bar's soft edge starts from its tinted ground"


def test_the_strip_under_the_clock_wears_it_and_ends_softly():
    strip = _rule("  html.store-ios body::before, html.ios-home body::before")
    assert "height: calc(env(safe-area-inset-top, 0px) + 8px);" in strip and "background: var(--bg);" in strip, strip
    assert "-webkit-mask-image: var(--mask-strip-foot); mask-image: var(--mask-strip-foot);" in strip
    assert "--mask-strip-foot: linear-gradient(to bottom, #000 calc(100% - 8px), transparent);" in CSS
    assert ("html.store-ios.team-tint body::before, html.ios-home.team-tint body::before "
            "{ background: var(--grad-team-ground), var(--bg); }") in CSS


def _seam(png: bytes, start: int = 0) -> tuple:
    """The biggest row-to-row change down the page's two outer edges (left
    and right of every button and crest), from `start` device rows down,
    and where."""
    try:
        from PIL import Image
    except ImportError:                  # the browser test asks for Pillow first
        return (0, 0)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    pix, (w, h) = im.load(), im.size
    worst = (0, 0)
    for x in (2, w - 3):
        col = [pix[x, y] for y in range(h)]
        for y in range(start, h - 1):
            d = max(abs(col[y + 1][c] - col[y][c]) for c in range(3))
            worst = max(worst, (d, y))
    return worst


def test_in_a_browser_the_top_of_the_page_has_no_rule():
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
    games = [{"home": "TB", "away": "MIL", "date": "2099-01-01", "kickoff": "19:10", "spread": -1.5, "favorite": "TB",
              "total": 7.0, "home_ml": -114, "away_ml": 113}]
    body = json.dumps({"sport": "mlb", "generated_from": "live", "date": "2099-01-01", "recommendations": [],
                       "most_likely": [], "games": games, "player_stats": {}})
    srv, port = rendercheck._serve()
    found = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for theme, team in (("dark", "nfl:DET"), ("light", "nfl:DET"), ("dark", "")):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                              has_touch=True, service_workers="block", color_scheme=theme)
                    page = ctx.new_page()
                    cdp = ctx.new_cdp_session(page)
                    try:
                        cdp.send("Emulation.setSafeAreaInsetsOverride", {"insets": {"top": 47, "bottom": 34, "left": 0, "right": 0}})
                    except Exception:                               # noqa: BLE001
                        print("      (the safe area unchecked: this Chromium cannot emulate one)")
                        ctx.close()
                        return
                    teams = (f"localStorage.setItem('qb_settings_v1', JSON.stringify({{ teamColors: 'on', teams: ['{team}'] }}));"
                             if team else "")
                    page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true });"
                                         "try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                         f" localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', '{theme}'); {teams} }}"
                                         " catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=mlb#recommended", wait_until="load")
                    page.wait_for_function("() => document.querySelector('.sportbar .sport-btn')", timeout=20000)
                    page.wait_for_timeout(600)
                    key = f"{theme} {team or 'no team'}"
                    found[key] = {
                        "tint": page.evaluate("document.documentElement.classList.contains('team-tint')"),
                        "rest": _seam(page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": 200})),
                    }
                    # The bar slid away under the clock's strip: what is left
                    # is the strip, over the page.
                    page.evaluate("window.scrollTo(0, 900)")
                    page.wait_for_timeout(300)
                    page.evaluate("document.querySelector('.topbar').style.transform = 'translateY(-120px)'")
                    page.wait_for_timeout(200)
                    # From 8px down: the strip's foot is the question, and
                    # an emulated viewport can draw a fixed layer a pixel or
                    # two low just after a jump of the scroll (a phone draws
                    # its clock over that row anyway).
                    found[key]["away"] = _seam(page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": 120}), start=16)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert found["dark nfl:DET"]["tint"] and found["light nfl:DET"]["tint"] and not found["dark no team"]["tint"], found
    for key, f in found.items():
        for state in ("rest", "away"):
            assert f[state][0] <= SEAM, f"{key}, bar {state}: a rule of {f[state][0]} levels at {f[state][1] / 2:.0f}px"


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
