"""The blend: one face, a neutral ground, fills instead of outlines, light
that blends (web/css/styles.css THE BLEND and its tokens; web/index.html's
preload; app.js and the rooms' --tone).

Ethan, 2026-10-27: "We need the whole site to feel more blended with the
colors and everything you added. Everything feels so sharp ... realize what
apps actually look like ... The colors look weird. The textures look weird
... The skins of everything look weird." docs/VISUAL_AUDIT.md "The blend" has
the research and the before and after. What these hold: Inter is the one UI
face and numbers use its tabular figures; the dark ramp is graphite (low
chroma) with cards a clear step off the page, both themes; chips, buttons and
price boxes are fills; the corners are the softer three; the league colours
are one family; no glow draws a hard ring; the best pick wears a still gold
edge, not a rainbow; venue photographs share one grade; tracked caps are
half what they were; a coloured stripe is a tone, not a border.

Run directly: `python3 tests/test_the_site_blends.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import palettefit as pf                                          # noqa: E402

WEB = ROOT / "web"
CSS = (WEB / "css" / "styles.css").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
BLEND = CSS[CSS.index("THE BLEND (2026-10-27). Ethan"):CSS.index("GLASS FOR WHAT FLOATS")]


def _root(selector: str) -> str:
    i = CSS.index(selector + " {\n")
    return CSS[i:CSS.index("\n}\n", i)]


DARK, LIGHT = _root(":root"), _root(':root[data-theme="light"]')


def _hex(block: str, name: str) -> tuple:
    m = re.search(rf"^\s*--{name}: (#[0-9A-Fa-f]{{6}});", block, re.M)
    assert m, f"--{name} is not a hex in this block"
    h = m.group(1)
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def test_one_face_for_words_and_numbers():
    assert '@font-face {\n  font-family: "Inter";\n  src: url("../fonts/inter.woff2") format("woff2");' in CSS
    assert "font-weight: 100 900;" in CSS[CSS.index('font-family: "Inter";'):][:200], "one variable file, every weight"
    assert '--font-sans: "Inter",' in DARK
    assert "--font-mono: var(--font-sans);" in DARK and "--font-display: var(--font-sans);" in DARK
    assert "html { font-variant-numeric: tabular-nums; }" in BLEND, "a column of odds still lines up"
    assert '<link rel="preload" href="fonts/inter.woff2" as="font" type="font/woff2" crossorigin />' in HTML
    assert "archivo-narrow" not in HTML, "the old face is not fetched any more"
    font = WEB / "fonts" / "inter.woff2"
    assert font.read_bytes()[:4] == b"wOF2" and font.stat().st_size < 80_000
    assert '"Inter", system-ui' in (WEB / "js" / "app.js").read_text(encoding="utf-8"), "the share card too"


def test_the_ground_is_graphite_and_a_card_is_a_step_off_it():
    for block in (DARK, LIGHT):
        for name in ("bg", "panel-2", "panel-3"):
            _, c, _ = pf.srgb_to_oklch(_hex(block, name))
            assert c < .008, f"--{name} chroma {c:.4f}: brown is back"
    bg = pf.srgb_to_oklch(_hex(DARK, "bg"))[0]
    panel = pf.srgb_to_oklch(_hex(DARK, "panel"))[0]
    assert panel - bg >= .05, "a card is told from the page by its tone"
    for name in ("text-dim", "text-mute"):
        assert pf.srgb_to_oklch(_hex(DARK, name))[1] < .015, f"--{name} is grey, not beige"


def test_surfaces_are_fills_not_outlines():
    for block in (DARK, LIGHT):
        for tok in ("--fill-tone:", "--fill-tone-2:", "--glow-card:", "--venue-grade:"):
            assert tok in block, tok
    fills = BLEND[BLEND.index(".btn, .btn.ghost, .chip,"):]
    fills = fills[:fills.index("}") + 1]
    for cls in (".chip", ".subnav-btn", ".ob-pill", ".ob-tier-chip", ".ob-filter", ".hd-o", ".ob-odds", ".gc-mk"):
        assert cls in fills, cls
    assert "border-color: transparent; background-color: var(--fill-tone);" in fills
    assert ".card, .ob-card, .hd-card { box-shadow: var(--glow-card); }" in BLEND
    for tok, px in (("--radius-sm", 10), ("--radius", 14), ("--radius-lg", 18)):
        assert f"  {tok}: {px}px;" in DARK, tok


def test_the_league_colours_are_one_family():
    for block in (DARK, LIGHT):
        lch = [pf.srgb_to_oklch(_hex(block, f"lg-{lg}")) for lg in ("nfl", "cfb", "mlb", "nba", "wnba", "ufc")]
        ls = [l for l, _, _ in lch]
        assert max(ls) - min(ls) < .07, f"one lightness: {[round(x, 3) for x in ls]}"
        hues = sorted(h for _, _, h in lch)
        assert min(b - a for a, b in zip(hues, hues[1:])) > 15, "still told apart"


def test_light_blends_and_the_best_pick_is_gold_not_a_rainbow():
    for block in (DARK, LIGHT):
        for name in ("glow-gold", "glow-good", "glow-lift", "glow-league"):
            line = re.search(rf"--{name}: ([^;]+);", block).group(1)
            assert "0 0 0 1px" not in line, f"--{name} draws a hard ring"
        aurora = re.search(r"--grad-aurora: ([^;]+);", block).group(1)
        assert aurora.count("radial-gradient") == 1 and "at 50% -140px" in aurora, "one wash, centred, not a blob"
    code = re.sub(r"/\*.*?\*/", "", BLEND, flags=re.S)
    assert "conic-gradient" not in code and "lightSpin" not in code
    assert "background: var(--grad-rim-gold);" in code
    assert ".qt-row > .qt-chip:nth-child" not in code, "the four doors share the gold"
    assert ".venue-photo { filter: var(--venue-grade); }" in code


def test_tracked_caps_are_calmer():
    for f in sorted((WEB / "css").glob("*.css")):
        s = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        for m in re.finditer(r"([^{}]*)\{[^{}]*letter-spacing:\s*\.(\d+)em", s):
            if "brand-words" in m.group(1) or "brand-tag" in m.group(1):
                continue
            assert float("." + m.group(2)) <= .18, f"{f.name}: {m.group(1).strip()[:60]} at .{m.group(2)}em"


def test_a_coloured_stripe_is_a_tone():
    for js in (WEB / "js").glob("*.js"):
        assert "border-left:3px solid" not in js.read_text(encoding="utf-8"), f"{js.name} draws a stripe"
    rule = BLEND[BLEND.index('[style*="--tone:"] {'):]
    rule = rule[:rule.index("}") + 1]
    assert "--tone: var(--brand);" in rule and "background-image: var(--grad-tone);" in rule


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_the_blend_in_a_browser():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import json
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#likely", wait_until="load")
                page.wait_for_timeout(1500)
                got = page.evaluate("""async () => { await document.fonts.ready;
                  const chip = document.querySelector('.ob-filter, .ob-tier-chip');
                  const cs = chip ? getComputedStyle(chip) : null;
                  return { font: getComputedStyle(document.body).fontFamily,
                           loaded: document.fonts.check('600 14px Inter'),
                           nums: getComputedStyle(document.documentElement).fontVariantNumeric,
                           border: cs ? cs.borderTopColor : null }; }""")
                assert got["font"].startswith('Inter') or got["font"].startswith('"Inter"'), got
                assert got["loaded"], "the face arrived"
                assert got["nums"] == "tabular-nums", got
                assert got["border"] in ("rgba(0, 0, 0, 0)", "transparent"), f"a chip is a fill: {got}"
                assert not errors, errors
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
