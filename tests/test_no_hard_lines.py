"""No hard lines: every outline a fill or nothing, a selected chip a tint,
edges that fade (web/css/*.css; THE BLEND's "NO HARD LINES" in styles.css).

Ethan, 2026-10-27, a screenshot of his phone with the top bar and the league
row circled: "notice how sharp all the lines are on the whole site for
everything. I need you to fix that as well. Make everything smoother and more
blended and just like feel more professional." What these hold:

  * no rule in any sheet draws a full outline in the border tokens, nor a gold
    outline (a selected thing is tinted, not ringed);
  * the dividers that remain are a whisper: --border and --border-soft sit
    within a few points of lightness of the surfaces they cross;
  * the top of the page is one surface: the league row lets the page's light
    through, the bar casts a soft fade, a team's colour spills from the bar
    rather than drawing a stripe, and the iPhone app's glass bar has no rim;
  * a league button is a tint and its light, never a ring;
  * a game card's team colours are light from the photo, not a 2px rule;
  * every field is a filled well;
  * and in a browser, the phone's home draws no line wider than a hairline
    in a border colour anywhere on its first three screens.

Run directly: `python3 tests/test_no_hard_lines.py`
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

import palettefit as pf                                          # noqa: E402

CSS_DIR = ROOT / "web" / "css"
CSS = (CSS_DIR / "styles.css").read_text(encoding="utf-8")
BLEND = CSS[CSS.index("THE BLEND (2026-10-27). Ethan"):CSS.index("GLASS FOR WHAT FLOATS")]


def _root(selector: str) -> str:
    i = CSS.index(selector + " {\n")
    return CSS[i:CSS.index("\n}\n", i)]


def _hex(block: str, name: str) -> tuple:
    h = re.search(rf"^\s*--{name}: (#[0-9A-Fa-f]{{6}});", block, re.M).group(1)
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _rules():
    for f in sorted(CSS_DIR.glob("*.css")):
        code = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", code):
            yield f.name, m.group(1).strip(), m.group(2)


def test_no_outline_in_any_sheet():
    full = re.compile(r"(?<![-\w])border:\s*var\(--hairline\)\s+solid\s+var\(--border(-soft)?\)")
    gold = re.compile(r"(?<![-\w])border:\s*(?:var\(--hairline\)|1px|1\.5px|2px)\s+solid\s+var\(--(brand|brand-2|brand-solid|gold)\)")
    bad = [(f, sel[-60:]) for f, sel, body in _rules()
           if (full.search(body) or gold.search(body)) and "legend" not in sel and ".mk" not in sel]
    assert not bad, bad[:10]
    tinted = re.compile(r"border-color: color-mix\(in (?:oklab|srgb), var\(--[a-z0-9-]+\) \d+%, var\(--border")
    assert not [s for f, s, b in _rules() if tinted.search(b)], "a tinted outline is still an outline"
    mixed = re.compile(r"(?<![-\w])border:\s*(?:var\(--hairline\)|1px|1\.5px)\s+solid\s+color-mix\(")
    left = [(f, s[-60:]) for f, s, b in _rules() if mixed.search(b) and "legend" not in s]
    assert not left, left[:10]


def test_a_selected_thing_is_tinted_not_ringed():
    hot = re.compile(r"(?<![-\w])border-color:\s*var\(--(?:brand|brand-2|brand-solid|gold)\)")
    sel_re = re.compile(r"\.(active|on|sel|selected|ours|current)\b|\[aria-(pressed|selected|current)=")
    bad = [(f, s[-60:]) for f, s, b in _rules() if sel_re.search(s) and hot.search(b)]
    assert not bad, bad[:10]


def test_what_is_left_of_a_line_is_a_whisper():
    for theme in (_root(":root"), _root(':root[data-theme="light"]')):
        grounds = [pf.srgb_to_oklch(_hex(theme, g))[0] for g in ("bg", "panel", "panel-2")]
        for name, near, most in (("border-soft", .03, .08), ("border", .05, .115)):
            L = pf.srgb_to_oklch(_hex(theme, name))[0]
            assert min(abs(L - g) for g in grounds) < near, f"--{name} matches none of the surfaces"
            assert max(abs(L - g) for g in grounds) < most, f"--{name} stands out of a surface"


def test_the_top_of_the_page_is_one_surface():
    assert "@media (max-width: 1279px) { .sportbar { background: transparent; } }" in BLEND
    bar = BLEND[BLEND.index(".topbar::before {"):]
    bar = bar[:bar.index("}") + 1]
    assert "top: 100%;" in bar and "background: var(--grad-bar-fade);" in bar, "a soft edge, not a line"
    team = CSS[CSS.index(".team-tint .topbar::after {"):]
    team = team[:team.index("}") + 1]
    assert "top: 100%;" in team and "background: var(--grad-team-spill);" in team and "height: 2px" not in team
    glass = CSS[CSS.index("html.store-ios .topbar, html.ios-home .topbar {"):]
    assert "box-shadow: none;" in glass[:200], "the iPhone app's bar has no rim"
    for theme in (_root(":root"), _root(':root[data-theme="light"]')):
        rim = re.search(r"--glass-rim: ([^;]+);", theme).group(1)
        assert "0 -1px" not in rim, "no dark line under glass"


def test_a_league_button_is_a_tint_and_its_light():
    hue = re.search(r"--glow-hue: ([^;]+);", BLEND).group(1)
    assert "0 0 0" not in hue, "no ring"
    assert ".sportbar-in .sport-btn.active { color: var(--hue); border-bottom-color: transparent;" in BLEND


def test_a_games_colours_are_light_not_a_rule():
    rule = BLEND[BLEND.index(".game-card .game-info::before {"):]
    rule = rule[:rule.index("}") + 1]
    assert "height: 2px" not in rule and "mask-image: var(--mask-spill);" in rule


def test_every_field_is_a_filled_well():
    i = CSS.index(':where(input:not([type]), input[type="text"]')
    rule = CSS[i:CSS.index("}", i)]
    assert "background-color: var(--fill-tone);" in rule and "solid transparent;" in rule


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_the_home_draws_no_hard_line_in_a_browser():
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
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     "localStorage.setItem('qb_settings_v1', JSON.stringify({teams:['nfl:DET'], teamColors:'on'}));}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_timeout(1800)
                bad = page.evaluate("""() => {
                  const out = [], H = innerHeight * 3;
                  const alpha = (c) => { if (!c || c === 'transparent') return 0; const m = c.match(/rgba?\\(([^)]+)\\)/);
                    if (m) { const p = m[1].split(',').map(Number); return p.length > 3 ? p[3] : 1; }
                    const s = c.match(/\\/\\s*([0-9.]+)\\s*\\)\\s*$/); return s ? +s[1] : 1; };
                  for (const el of document.querySelectorAll('body *')) {
                    const r = el.getBoundingClientRect();
                    if (r.width < 6 || r.height < 6 || r.bottom < 0 || r.top > H) continue;
                    const cs = getComputedStyle(el);
                    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                    const sides = ['Top', 'Right', 'Bottom', 'Left'].filter((s) => cs['border' + s + 'Style'] !== 'none'
                      && parseFloat(cs['border' + s + 'Width']) > 0 && alpha(cs['border' + s + 'Color']) > .05);
                    if (sides.length === 4) out.push(el.tagName + '.' + String(el.className).slice(0, 60) + ' ' + cs.borderTopColor + ' in ' + (el.parentElement ? el.parentElement.className : '') + ' / ' + (el.textContent || '').trim().slice(0, 40));
                    for (const ps of ['::before', '::after']) {
                      const p = getComputedStyle(el, ps);
                      if (p.content !== 'none' && parseFloat(p.height) > 0 && parseFloat(p.height) <= 3
                          && parseFloat(p.width) > 40 && p.backgroundImage !== 'none') out.push(String(el.className).slice(0, 40) + ps);
                    }
                  }
                  return out; }""")
                assert not bad, f"hard lines on the home: {bad[:10]}"
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
