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
  * a game card's team colours are one layer over the whole card, rising
    out of the photograph and running to its foot: no band where they start
    or stop (2026-10-28), and the strip's bar is no grey dash on a phone;
  * a pick's rank is a pill that fits its number, placed by the card alone;
  * every field is a filled well;
  * (the sweep after, 2026-10-28) a badge, a note or a frame is a tint; a
    stripe is light from the left edge; an open tab is a tinted pill; what
    still draws a line or a coloured border is named in GLYPHS, EDGES and
    COLOURED, each a picture, a focus or a border that is its own fill;
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


#: What may still draw a full border: pictures, not boxes. A chart's legend
#: marks and miss dots, a pitch zone's ball, a puck, a ring chart, an avatar's
#: ring (team-coloured on the hero card, the panel's own colour round a
#: profile picture on its cover), a step's progress circle, and the social
#: room's --fd-line, which is transparent wherever those rules apply.
GLYPHS = {
    ("ask.css", ".ask-steps li::before"),
    ("carrychart.css", ".cc-legend .mk"), ("carrychart.css", ".cc-legend .dt.m"),
    ("carrychart.css", ".cc-row .dot.miss"), ("carrychart.css", ".cc-legend .dt.mp-b"),
    ("carrychart.css", ".mb-hero-face .cc-face"), ("carrychart.css", ".cc-legend .dt.kk-x"),
    ("extras.css", ".xt-ring"),
    ("gamecast.css", ".gc-pz-n.b"), ("gamecast.css", ".gc-pz-key .b::before"),
    ("hoopscast.css", ".hc-key i.miss"),
    ("rinkcast.css", ".rc-puckmark"), ("rinkcast.css", ".rc-key-note i.miss"), ("rinkcast.css", ".rc-key-note i.block"),
    ("social.css", ".fd-card"), ("social.css", ".fd-tab"), ("social.css", ".fd-hero"),
    ("social.css", ".fd-comp-in, .fd-comp-fake"), ("social.css", ".fd-seg"), ("social.css", ".fd-mtrend-c"),
    ("social.css", ".fd-av-xl"), ("social.css", ".fd-av-xl.fd-av-site"), ("social.css", ".fd-search"),
    ("social.css", ".fd-days"), ("social.css", ".fd-pstats"),
}


def test_badges_notes_and_frames_are_tints_not_outlines():
    """2026-10-28, the sweep after: a grade, a status pill, a slip note, a
    poll button, an invite code and a photo frame still drew their outline
    in their own colour (currentColor, --good, --warn, --bad) or a dash,
    which the outline checks above did not read. Each is a tint now; only
    the pictures in GLYPHS still draw a full border."""
    drawn = set()
    for f, sel, body in _rules():
        for d in re.finditer(r"(?<![-\w])border:\s*([^;]+);", body):
            v = d.group(1)
            if re.search(r"\b(solid|dashed|dotted|double)\b", v) and "transparent" not in v:
                drawn.add((f, " ".join(sel.split())))
    assert drawn <= GLYPHS, sorted(drawn - GLYPHS)
    assert "var(--fd-line)" in (CSS_DIR / "social.css").read_text(encoding="utf-8")
    for host in (".fd-wrap {", ".acct-prof {"):
        rule = (CSS_DIR / "social.css").read_text(encoding="utf-8")
        rule = rule[rule.index(host):]
        assert "--fd-line: transparent;" in rule[:rule.index("}")], host


#: One-sided lines that keep a colour: chart marks (Ask's line, a legend's
#: dashed mark, the fantasy bars' threshold), two chevrons drawn with borders,
#: and the Record ledger's stripe for a browser without color-mix (the wash
#: that replaced it needs color-mix). Every other one-sided line is a divider
#: in --border, --border-soft or --fd-line, or nothing.
EDGES = {
    ("ask.css", ".ask-line"), ("carrychart.css", ".cc-legend .dt.rl-m"), ("fantasy.css", ".mk-bars::after"),
    ("record.css", ".rl-row.won"), ("record.css", ".rl-row.lost"),
    ("styles.css", ".pz-runner > summary::after"), ("styles.css", ".row-fold-chev"),
}

#: A border colour that still shows: a field or a calculator in focus, a
#: spinner, a ring chart, a legend mark, an avatar's ring or cut-out, and
#: buttons and badges whose border is their own fill.
COLOURED = {
    ("ask.css", ".ask-steps li.now::before"), ("ask.css", ".ask-track .ask-act.primary"),
    ("carrychart.css", ".uf-ring.me"), ("carrychart.css", ".cc-legend .mk.fum"),
    ("extras.css", ".xt-f input:focus, .xt-f select:focus"), ("extras.css", ".xt-ring.good"), ("extras.css", ".xt-ring.bad"),
    ("hoopscast.css", ".hc-play.k-made .hc-pkind, .hc-play.k-ft .hc-pkind"), ("rinkcast.css", ".rc-play.k-goal .rc-pkind"),
    ("social.css", ".fd-comp-in:focus"), ("social.css", ".fd-input:focus"), ("social.css", ".fd-editp-prev .fd-av-xl"),
    ("styles.css", ".search-wrap input:focus"), ("styles.css", ".calc-in:focus"), ("styles.css", "#ptr.ready, #ptr.busy"),
    ("styles.css", ".card.longshot.lk-top .grade.lk-pct"), ("styles.css", ".card.longshot.lk-mid .grade.lk-pct"),
    ("styles.css", ".stub-cta"), ("styles.css", ".pw-buy, .co-go"),
    ("styles.css", ':where(input:not([type="checkbox"]):not([type="radio"]), select, textarea):focus'),
}


def test_no_coloured_stripe_underline_or_ring_is_left():
    """2026-10-28, the sweep after: a bet's stripe, a pick's, a verdict's and
    a notice's became light from the left edge (the --tone wash); an open
    tab's underline became a tinted pill like the league row's; a chip's,
    a tag's or a card's coloured border, at rest, hovered or chosen, became
    a tint. What is left is in EDGES and COLOURED, each a picture, a focus
    or a border that is its own fill."""
    edges, coloured = set(), set()
    for f, sel, body in _rules():
        key = (f, " ".join(sel.split()))
        for d in re.finditer(r"(?<![-\w])border-(?:left|right|top|bottom)(-color)?:\s*([^;]+);", body):
            v = d.group(2).strip()
            if "transparent" in v or re.fullmatch(r"0|none", v):
                continue
            if d.group(1) is None and not re.search(r"\b(solid|dashed|dotted|double)\b", v):
                continue
            if not re.search(r"var\(--(border|border-soft|fd-line)\)$", v):
                edges.add(key)
        for d in re.finditer(r"(?<![-\w])border-color:\s*([^;]+);", body):
            if d.group(1).strip() != "transparent":
                coloured.add(key)
    assert edges <= EDGES, sorted(edges - EDGES)
    assert coloured <= COLOURED, sorted(coloured - COLOURED)
    rec = (CSS_DIR / "record.css").read_text(encoding="utf-8")
    fall = rec[rec.index("@supports not (background: color-mix(in srgb, red 10%, transparent)) {", rec.index(".rl-row.push")):]
    assert ".rl-row.won { border-left-color" in fall[:fall.index("\n}")], "the stripe is only the old browsers' fallback"


def test_a_state_is_a_wash_or_a_pill():
    styles = CSS
    assert ".mbc.open { --tone: var(--warn); }" in styles and ".mbc.win { --tone: var(--good); }" in styles
    group = styles[styles.index(".mbc.open, .mbc.win, .mbc.loss, .mbc.push {"):]
    group = group[:group.index("}")]
    assert "--grad-tone:" in group and "background-image: var(--grad-tone);" in group
    for f, sel in (("more.css", ".tm-tab.on {"), ("chat.css", ".gch-tab.on {"), ("detail.css", ".pbp-tab.active {"),
                   ("carrychart.css", ".cc-tab.on {"), ("hoopscast.css", ".hc-tab.on {"), ("rinkcast.css", ".rc-tab.on {")):
        s = (CSS_DIR / f).read_text(encoding="utf-8")
        rule = s[s.index(sel):]
        rule = rule[:rule.index("}")]
        assert "border-bottom-color: transparent; border-radius: 999px;" in rule, (f, sel)


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
    # Lit glass along its top (under the status bar), and no ring: the full
    # rim's 1px ring was the line along the bar's foot Ethan circled.
    assert "box-shadow: var(--glass-rim-soft);" in glass[:200], "the iPhone app's bar has no ring"
    for theme in (_root(":root"), _root(':root[data-theme="light"]')):
        soft = re.search(r"--glass-rim-soft: ([^;]+);", theme).group(1)
        assert soft.startswith("inset 0 1px 0 ") and soft.count("inset") == 1 and "0 0 0" not in soft, soft
    for theme in (_root(":root"), _root(':root[data-theme="light"]')):
        rim = re.search(r"--glass-rim: ([^;]+);", theme).group(1)
        assert "0 -1px" not in rim, "no dark line under glass"


def test_a_league_button_is_a_tint_and_its_light():
    hue = re.search(r"--glow-hue: ([^;]+);", BLEND).group(1)
    assert "0 0 0" not in hue, "no ring"
    assert ".sportbar-in .sport-btn.active { color: var(--hue); border-bottom-color: transparent;" in BLEND


def test_a_games_colours_are_light_not_a_rule():
    """Ethan, 2026-10-28, circling a Home tile: "The stadium thing has these
    hard lines that look gross." The teams' wash was painted on the facts'
    own box, with a band of colour along its top: it began in a line across
    the photograph and ended in another over the weather. It is one layer
    over the whole card now, rising through a mask and running to the foot,
    with the chips and the words above it."""
    wash = BLEND[BLEND.index(".game-card::after {"):]
    wash = wash[:wash.index("}") + 1]
    assert "inset: 0;" in wash and "background-image: var(--grad-teams-wash);" in wash, wash
    assert "mask-image: var(--mask-teams-rise);" in wash and "z-index: 2;" in wash, wash
    assert re.search(r"--mask-teams-rise: linear-gradient\(to bottom, transparent \d+%, #000 \d+%\);", CSS)
    assert ".game-card .game-info::before" not in CSS, "no band along the top of the facts"
    assert not re.search(r"\.game-card \.game-info \{[^}]*background", CSS), "the facts' box paints nothing of its own"
    assert ".game-card .game-info, .game-card .wind-wrap { position: relative; z-index: 3; }" in BLEND
    # The strip scrolls under a finger with no bar; a mouse gets a round one.
    assert "@media (pointer: coarse) {\n  .games-scroller { scrollbar-width: none; }\n" \
           "  .games-scroller::-webkit-scrollbar { display: none; }" in CSS
    assert ".games-scroller::-webkit-scrollbar-thumb { background: var(--fill-tone-2); border-radius: 999px; }" in CSS


def test_a_picks_rank_is_a_pill_that_fits_its_number():
    """Ethan, 2026-10-28, circling "#3": "the numbers ... doesn't fit the
    box". On a phone the rank was a tab cut into the card's corner, so the
    corner's curve ate the number, and it still named the desktop's rank
    column, which Safari answered by drawing it above the card."""
    look = CSS[CSS.index(".ob-rank { grid-area: rank;"):]
    look = look[:look.index("}") + 1]
    for want in ("border-radius: 999px;", "min-width: 24px;", "box-shadow: var(--glow-cutout);", "line-height: 1;"):
        assert want in look, want
    assert ".ob-rank { background: color-mix(in oklab, var(--brand) 18%, var(--panel)); }" in CSS, "opaque on a picture"
    for pre in ("  .ob-card .ob-rank {", "body.two-pane .pane-list .ob-card .ob-rank {"):
        rule = CSS[CSS.index(pre):]
        rule = rule[:rule.index("}") + 1]
        for want in ("grid-area: auto;", "position: absolute;", "top: 7px; left: 7px;", "height: 20px;"):
            assert want in rule, (pre, want)
        assert "border-radius" not in rule, "not a tab cut into the corner"


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


def test_the_pages_with_the_last_outlines_draw_none_in_a_browser():
    """The sweep's pages, on a computer: the plans and sign-up pages' chosen
    plan, Edge's chips, the method page's tags, My Bets and the memes page.
    An element boxed on all four sides in a colour that shows is an outline,
    whatever drew it; an avatar's ring is a picture."""
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
    found = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for theme in ("dark", "light"):
                    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
                    page = ctx.new_page()
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                         f"localStorage.setItem('ge-theme','{theme}');}}catch(e){{}}")
                    for view in ("paywall", "signup", "edge", "methodology", "mybets", "memes", "recommended", "record"):
                        page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#{view}", wait_until="load")
                        page.wait_for_timeout(1500)
                        bad = page.evaluate("""() => {
                          const out = [];
                          const alpha = (c) => { if (!c || c === 'transparent') return 0; const m = c.match(/rgba?\\(([^)]+)\\)/);
                            if (m) { const p = m[1].split(',').map(Number); return p.length > 3 ? p[3] : 1; }
                            const s = c.match(/\\/\\s*([0-9.]+)\\s*\\)\\s*$/); return s ? +s[1] : 1; };
                          for (const el of document.querySelectorAll('body *')) {
                            const r = el.getBoundingClientRect();
                            if (r.width < 6 || r.height < 6 || r.bottom < 0 || r.top > innerHeight * 3) continue;
                            if (el === document.activeElement || /\\b(uf-ring|cc-face|fd-av-xl|crest)\\b/.test(String(el.className))) continue;
                            const cs = getComputedStyle(el);
                            if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                            const sides = ['Top', 'Right', 'Bottom', 'Left'].filter((s) => cs['border' + s + 'Style'] !== 'none'
                              && parseFloat(cs['border' + s + 'Width']) > 0 && alpha(cs['border' + s + 'Color']) > .05);
                            if (sides.length === 4) out.push(el.tagName + '.' + String(el.className).slice(0, 50) + ' ' + cs.borderTopColor);
                          }
                          return out; }""")
                        if bad:
                            found[f"{view}/{theme}"] = bad[:5]
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not found, found


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
