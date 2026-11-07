"""The lights on: every league its own colour, glow where something is on,
motion on arrival (web/css/styles.css THE LIGHTS ON; app.js markSportRow,
_switchViewNow, obCardHTML).

Ethan, 2026-10-27: "i feel like we can use more colors and shit throughout
the site too to be more exciting and shit like that. animations and glowing
shit." Gold stays the brand (his call, 2026-08-23); around it, each league
has a colour, the page glows in the league in view, the open league's
button and the night's best pick are lit, and a page rises in as it opens.

What these hold: each league's colour is a token in both themes and the page
names the league in view so the light follows it; every league button wears
its own; the glows are all tokens (tests/test_design_tells keeps the
family); a page rises in once, as it opens, never on a redraw, holds no
transform once landed, and the screens of their own are left alone; the
night's best pick wears a moving rim drawn behind it, not a heavier border;
nothing blurs; and in a browser the basketball tab paints basketball's
colour and the best pick wears its edge.

Run directly: `python3 tests/test_the_lights_on.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
#: The section's rules; its tokens live in the sheet's one :root and one
#: light block (tests/test_one_root_and_shared_percents). The same night
#: Ethan asked for it all to blend ("Everything feels so sharp"), and the
#: section became THE BLEND: the light stayed, softer (tests/test_the_site_blends).
LIGHTS = CSS[CSS.index("THE BLEND (2026-10-27). Ethan"):CSS.index("GLASS FOR WHAT FLOATS")]
LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc")


def _block(selector: str, text: str = LIGHTS) -> str:
    i = text.index(selector + " {")
    return text[i:text.index("}", i) + 1]


def _root(selector: str) -> str:
    i = CSS.index(selector + " {\n")
    return CSS[i:CSS.index("\n}\n", i)]


def _fn(name: str) -> str:
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_every_league_has_a_colour_in_both_themes():
    dark, light = _root(":root"), _root(':root[data-theme="light"]')
    for lg in LEAGUES:
        assert re.search(rf"--lg-{lg}: #[0-9A-F]{{6}};", dark), lg
        assert re.search(rf"--lg-{lg}: #[0-9A-F]{{6}};", light), f"{lg}: a darker shade for a light page"
    assert "--league: var(--lg-nfl);" in dark, "football's gold until the page says otherwise"
    for lg in LEAGUES[1:]:
        assert f':root[data-league="{lg}"] {{ --league: var(--lg-{lg}); }}' in LIGHTS, lg


def test_the_page_names_the_league_in_view():
    mark = _fn("markSportRow")
    assert 'document.documentElement.dataset.league = lit || "";' in mark, \
        "the game page's own league too: markSportRow lights what sportRowLeague says"
    assert "background-image: var(--grad-aurora); background-repeat: no-repeat; }" in LIGHTS
    aurora = [l for l in (_root(":root") + _root(':root[data-theme="light"]')).splitlines()
              if l.strip().startswith("--grad-aurora:")]
    assert len(aurora) == 2 and all("var(--league)" in l for l in aurora), "the league's light, in both themes"


def test_every_league_button_wears_its_own_colour():
    for lg in LEAGUES:
        assert f'.sportbar-in .sport-btn[data-sport="{lg}"] {{ --hue: var(--lg-{lg}); }}' in LIGHTS, lg
    btn = _block(".sportbar-in .sport-btn")
    assert "--glow-hue:" in btn and "var(--hue)" in btn
    phone = LIGHTS[LIGHTS.index("@media (max-width: 760px)"):]
    assert ".sportbar-in .sport-btn.active .crest { outline-color: transparent; color: var(--hue); box-shadow: var(--glow-hue);" \
        in phone, "a tinted crest with a thin ring of its light, not a hard outline"
    assert ".topbar .sportbar-in .sport-btn.active { border-color: transparent; color: var(--hue); box-shadow: var(--glow-hue);" \
        in LIGHTS, "the desktop's pill too"


def test_the_glows_are_tokens_and_nothing_blurs():
    shadows = re.findall(r"box-shadow:\s*([^;]+);", re.sub(r"/\*.*?\*/", "", LIGHTS, flags=re.S))
    glow = r"var\(--glow(?:-[a-z]+)*\)"
    assert shadows and all(re.fullmatch(rf"{glow}(?:, {glow})*|none", v.strip()) for v in shadows), shadows
    for name in ("--glow-gold", "--glow-good", "--glow-lift", "--glow-league"):
        assert f"{name}:" in _root(":root") and f"{name}:" in _root(':root[data-theme="light"]'), \
            f"{name} in both themes"
    code = re.sub(r"/\*.*?\*/", "", LIGHTS, flags=re.S)
    assert "backdrop-filter" not in code and "will-change" not in code, "no blur and no layer per card on a phone"
    assert "@media (hover: hover) and (pointer: fine)" in LIGHTS, "a card lifts to a mouse, never under a thumb"


def test_a_page_rises_in_once_as_it_opens():
    sw = APP[APP.index("function _switchViewNow("):]
    sw = sw[:sw.index('if (name === "prop") {')]
    assert 'if (name !== leaving && !RISE_SKIPS.has(name)) {' in sw
    assert 'target.classList.add("enter");' in sw
    assert 'target._enterT = setTimeout(() => target.classList.remove("enter"), 900);' in sw, \
        "off again before any redraw: a live page redrawing every five seconds never flickers"
    assert 'const RISE_SKIPS = new Set(["ask", "pbp", "messages"]);' in APP, "the screens of their own"
    rise = LIGHTS[LIGHTS.index("@keyframes lightRise"):]
    assert "animation: lightRise var(--dur-slow) var(--ease-out) backwards;" in rise, \
        "filled backwards only: a landed section holds no transform, so nothing fixed in it moves"
    assert ".view.enter > :nth-child(-n+8)" in rise


def test_the_best_pick_wears_an_edge_drawn_behind_it():
    """A moving rainbow until the blend (2026-10-27): a still gold edge now,
    still a layer 1px proud of the card so the card keeps its hairline."""
    assert '${rank === 1 ? " is-first" : ""}' in _fn("obCardHTML")
    rim = LIGHTS[LIGHTS.index(".ob-card.is-first::before {"):]
    rim = rim[:rim.index("}") + 1]
    assert "inset: -1px; z-index: -1;" in rim and "background: var(--grad-rim-gold);" in rim
    assert "animation" not in rim
    first = _block(".ob-card.is-first")
    assert "border:" not in first, "the card keeps its hairline (tests/test_hairlines)"

def test_the_brand_and_the_ai_catch_the_light():
    assert ".qt-brand-t b { background: var(--grad-shine) 0 0 / 250% 100%;" in LIGHTS
    assert "animation: lightShine 7s var(--ease-out) infinite;" in LIGHTS
    assert ".tb-ask { position: relative; overflow: hidden; box-shadow: var(--glow-gold); }" in LIGHTS
    assert "animation: sheen 6s var(--ease-out) infinite;" in LIGHTS, "the shared sheen, a transform only"

def test_colour_that_means_something():
    assert ".ob-ring.tier-look .ob-ring-fg { stroke: var(--sky); }" in LIGHTS, "the third tier is a colour too"
    assert ".chip.up { background-color: color-mix(in oklab, var(--good) 14%, transparent); }" in LIGHTS
    assert ".section-title .st-ico { color: var(--league); }" in LIGHTS

def test_the_gold_buttons_ink_reads_on_their_sheen_in_both_themes():
    """2026-10-28, the sweep after "No hard lines": the gold buttons' sheen
    was the dark theme's bright gold in both themes, under the light theme's
    white ink, so "See the plans" and "Log bet" read at 1.8:1 on paper. Each
    theme names its own sheen, and both its stops hold its ink at 4.5:1."""
    def lum(h):
        def f(c):
            return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)
    for theme in (_root(":root"), _root(':root[data-theme="light"]')):
        sheen = re.search(r"--grad-gold-btn: linear-gradient\(180deg, (#[0-9A-Fa-f]{6}), (#[0-9A-Fa-f]{6})\);", theme)
        assert sheen, "each theme names its own sheen"
        ink = re.search(r"--brand-ink: (#[0-9A-Fa-f]{6});", theme).group(1)
        for stop in sheen.groups():
            lo, hi = sorted((lum(stop), lum(ink)))
            assert (hi + .05) / (lo + .05) >= 4.5, (stop, ink)


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_the_lights_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    from test_every_page_opens_clean import _board

    body = json.dumps(_board())
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nba#recommended", wait_until="load")
                page.wait_for_timeout(1500)
                assert page.evaluate("document.documentElement.dataset.league") == "nba"
                lg = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--league').trim()")
                nba = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--lg-nba').trim()")
                assert lg == nba and lg, (lg, nba)
                crest = page.evaluate("""(() => { const c = document.querySelector('.sportbar-in .sport-btn.active .crest');
                                                  return c ? getComputedStyle(c).boxShadow : ''; })()""")
                assert crest and crest != "none", "the open league's crest is lit"
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_timeout(1200)
                page.evaluate("switchView('likely')")
                page.wait_for_timeout(150)
                assert page.evaluate("document.getElementById('view-likely').classList.contains('enter')"), \
                    "the page rises in as it opens"
                page.wait_for_timeout(1100)
                assert not page.evaluate("document.getElementById('view-likely').classList.contains('enter')"), \
                    "and is done before any redraw"
                rim = page.evaluate("""(() => { const c = document.querySelector('.ob-card.is-first');
                                                return c ? getComputedStyle(c, '::before').backgroundImage : null; })()""")
                assert rim and "linear-gradient" in rim, f"the best pick's edge: {rim}"
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
