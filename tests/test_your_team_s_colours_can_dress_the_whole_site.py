"""Your team's colours can dress the whole site, the way a live game's page wears its clubs' (MYCOLORS1).

Ethan, 2026-11-17: "And add how users can use there team colors too make the
whole websites colors change like how the background on live pages looks with
the team colors".

Settings → Team colours is three ways: off, the bar (the bar, the Live disc and
the lit tab, since 2026-10-24), or the whole site. On the whole site, app.js
applyTeamColors puts html.team-wash on with the team's two colours, deepened
until white type reads on them for the dark theme (--tw-1, --tw-2) and as they
are for paper (--tw-1-paper, --tw-2-paper); every page then sits on them, the
first from the left and the second from the right, falling to the page's own
ground further down (styles.css "YOUR TEAM'S COLOURS ON THE WHOLE SITE"). The
bar and the strip under the clock paint the same screen-sized picture pinned to
the screen's corner, so nothing rules the top. Whose: the team picked in
Settings or with a team page's "Wear these colours", any league's; else the one
you follow in the league in view, else the first you follow.

Run directly: `python3 tests/test_your_team_s_colours_can_dress_the_whole_site.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ACCT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
TEAMS = (ROOT / "web" / "js" / "teams.js").read_text(encoding="utf-8")
#: Adjacent rows of the top of the screen may differ by this much (0-255, any channel).
SEAM = 6


def _fn(src, name):
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}\n", at) + 3]


def _section():
    at = CSS.index("YOUR TEAM'S COLOURS ON THE WHOLE SITE (MYCOLORS1")
    return CSS[at:]


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", body], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


#: The colour arithmetic and the apply step, as the page runs them.
HELPERS = ("".join(_fn(APP, n) for n in ("teamColorsWho", "applyTeamColors", "twRgb", "twLab", "twHex", "twWash",
                                         "twSwatch", "twPin"))
           + APP[APP.index("const TW_DEEP_L"):APP.index("\n", APP.index("const TW_DEEP_L"))] + "\n"
           + 'const TW_SWATCH_KEY = "qb.teamSwatch";\nlet _twPinRO = null;\n')


def _apply(settings, sport, tables=None, swatch=None):
    """applyTeamColors with these settings on this league: which classes, which properties."""
    js = """
const classes = {}, props = {}, store = {}; let barX = null;
%s
global.localStorage = { getItem: (k) => store[k] == null ? null : store[k], setItem: (k, v) => { store[k] = String(v); } };
const bar = { getBoundingClientRect: () => ({ left: 0, width: 390 }), style: { setProperty: (k, v) => { barX = v; } } };
global.document = { querySelector: (q) => q === ".topbar" ? bar : null,
  documentElement: { classList: { toggle: (c, on) => { classes[c] = !!on; }, contains: (c) => !!classes[c] },
                     style: { setProperty: (k, v) => { props[k] = v; } } } };
global.window = { addEventListener: () => {} };
const S = %s; const settings = () => S; const state = { sport: %s };
const TABLES = %s;
const teamsForSport = (s) => TABLES[s] || {};
%s
applyTeamColors();
console.log(JSON.stringify({ classes, props, barX, store }));
""" % (f"store[{json.dumps('qb.teamSwatch')}] = {json.dumps(json.dumps(swatch))};" if swatch else "",
       json.dumps(settings), json.dumps(sport), json.dumps(tables or {
           "nfl": {"DET": {"primary": "#005a8b", "secondary": "#b0b7bc", "tertiary": "#000000"},
                   "PIT": {"primary": "#000000", "secondary": "#ffb612", "tertiary": "#c60c30"},
                   "LV": {"primary": "#000000"}},
           "nba": {"BOS": {"primary": "#007a33"}}}), HELPERS)
    return _node(js)


def test_settings_offer_three_ways_and_whose_colours():
    assert 'teamColors: "off",' in APP and 'teamColorsTeam: "",' in APP, "off, and nobody pinned, until chosen"
    rows = _fn(ACCT, "setListHTML")
    assert 'setSeg("teamColors", tc.mode, [["off", "Off"], ["on", "Bar"], ["site", "Whole site"]])' in rows
    assert 'data-set-open="teamcolors"' in rows, "a Whose colours row under it"
    tc = _fn(ACCT, "setTeamColours")
    assert "const who = teamColorsWho(s);" in tc, "the same rule the page wears"
    assert "Follow a team, or tap Wear these colours on a team’s page" in tc, "with no team, the way to get one"
    page = _fn(ACCT, "setPageHTML")
    sheet = page[page.index('if (page === "teamcolors") {'):page.index('if (page === "password") {')]
    assert 'data-set-key="teamColorsTeam" data-set-val=""' in sheet, "your team in each league, the default"
    assert 'data-set-key="teamColorsTeam" data-set-val="${escapeAttr(t)}"' in sheet and "s.teams" in sheet
    assert "teamMarkIn(sp, ab, 28)" in sheet, "each team with its mark"


def test_the_whole_site_wears_the_team_s_two_colours():
    lions = _apply({"teamColors": "site", "teams": ["nfl:DET"]}, "nfl")
    assert lions["classes"] == {"team-wash": True, "team-tint": True}, lions
    assert lions["props"]["--tw-1"] == "#005a8b", "the Lions' blue already reads under white type: kept"
    assert lions["props"]["--tw-2"] == "#6f757a", "their silver deepened until white reads on it"
    assert (lions["props"]["--tw-1-paper"], lions["props"]["--tw-2-paper"]) == ("#005a8b", "#b0b7bc"), "paper: as they are"
    assert lions["props"]["--team-1"] == "#005a8b", "and the bar's tint, as before"
    assert lions["barX"] == "0px", "the bar told where it starts across the screen"


def test_the_pin_beats_the_follows_and_the_pair_is_the_club_s_own():
    steelers = _apply({"teamColors": "site", "teams": ["nfl:DET"], "teamColorsTeam": "nfl:PIT"}, "nfl")
    assert (steelers["props"]["--tw-1"], steelers["props"]["--tw-2"]) == ("#a86300", "#000000"), \
        "their gold, deepened, into their black: not the red of their mark"
    other = _apply({"teamColors": "site", "teams": ["nfl:DET", "nba:BOS"]}, "nba")
    assert other["props"]["--tw-1"] == "#007a33", "on the NBA, the team you follow there"
    assert other["props"]["--tw-2"] != other["props"]["--tw-1"], "one colour: a deeper shade of it beside it"


def test_the_bar_alone_off_and_a_club_in_black_alone():
    bar = _apply({"teamColors": "on", "teams": ["nfl:DET"]}, "nfl")
    assert bar["classes"] == {"team-wash": False, "team-tint": True} and "--tw-1" not in bar["props"], bar
    off = _apply({"teamColors": "off", "teams": ["nfl:DET"]}, "nfl")
    assert off["classes"] == {"team-wash": False, "team-tint": False} and not off["props"], off
    black = _apply({"teamColors": "site", "teams": ["nfl:LV"]}, "nfl")
    assert black["classes"] == {"team-wash": False, "team-tint": True}, "no colour to wash with: the bar wears it"


def test_a_college_club_wears_its_colours_before_its_league_s_list_loads():
    kept = {"cbb:DUKE": {"primary": "#00539b", "secondary": "#ffffff"}}
    got = _apply({"teamColors": "site", "teams": [], "teamColorsTeam": "cbb:DUKE"}, "nfl", swatch=kept)
    assert got["classes"]["team-wash"] and got["props"]["--tw-1"] == "#00539b", got
    seen = _apply({"teamColors": "site", "teams": ["nfl:DET"]}, "nfl")
    assert json.loads(seen["store"]["qb.teamSwatch"]) == {"nfl:DET": {"primary": "#005a8b", "secondary": "#b0b7bc",
                                                                       "tertiary": "#000000"}}, "one club kept: the one worn"
    assert "if ((sport === \"cfb\" || sport === \"cbb\") && d.teams && settings().teamColors !== \"off\") applyTeamColors();" \
        in APP, "and again once college's list is in"


def test_white_type_reads_on_every_nfl_club_s_dark_wash():
    js = HELPERS + "\n" + TEAMS.replace("const TEAMS", "var TEAMS") + """
const out = {};
for (const [k, t] of Object.entries(TEAMS)) {
  const w = twWash(t);
  if (w) out[k] = w.deep.map((h) => twLab(twRgb(h))[0]);
}
console.log(JSON.stringify(out));
"""
    got = _node(js)
    assert len(got) >= 30, got
    worst = max(max(v) for v in got.values())
    assert worst <= 0.565, f"OKLab lightness {worst}: white type would not read"


def test_one_picture_from_the_bar_down():
    sec = _section()
    wash = sec[sec.index("html.team-wash {"):sec.index("}", sec.index("html.team-wash {"))]
    assert "--tw-wash: linear-gradient(100deg, var(--tw-1) 6%, color-mix(in oklab, var(--tw-1) 50%, var(--tw-2)) 50%, var(--tw-2) 94%);" \
        in wash, "the first from the left, the second from the right, as the game page's"
    assert "var(--bg) 820px);" in wash, "falling to the page's ground, as the game page's shade does"
    paper = sec[sec.index('html.team-wash[data-theme="light"] {'):]
    assert "color-mix(in oklab, var(--tw-1-paper) 34%, var(--bg))" in paper[:paper.index("}")], "paper: a tint"
    shared = ("html.team-wash .ambient, html.team-wash body:not(.gp-on) .topbar,\n"
              "html.store-ios.team-wash body:not(.gp-on)::before, html.ios-home.team-wash body:not(.gp-on)::before {\n"
              "  background: var(--tw-shade), var(--tw-wash), var(--bg);\n"
              "  background-size: 100vw 100vh;")
    assert shared in sec, "the page's layer, the bar and the strip under the clock paint one screen-sized picture"
    bar = sec[sec.index("html.team-wash body:not(.gp-on) .topbar {"):]
    assert "background-position: var(--tw-x) 0;" in bar[:bar.index("}")] and "animation: none" in bar[:bar.index("}")]
    assert "html.team-wash body:not(.gp-on) .topbar::before, html.team-wash body:not(.gp-on) .topbar::after { display: none; }" in sec
    assert "html.team-wash .amb-club { display: none; }" in sec, "one picture, page to page"
    assert "background-attachment: fixed;" in sec[sec.index("html.team-wash .shelf-head {"):], "a sticky heading's ground"
    # The light theme's own tokens stay as they were: the game page resets every one of them to night.
    light = CSS[CSS.index(':root[data-theme="light"] {'):]
    assert "--tw-" not in light[:light.index("\n}")]
    tabs = CSS[CSS.index(".tm-tabs {"):]
    assert "background: transparent;" in tabs[:tabs.index("}")], "no plain band across the colour"


def test_every_team_page_offers_wear_these_colours():
    head = _fn(MORE, "teamHeaderHTML")
    assert 'typeof wearBtn === "function" ? wearBtn(d.sport, p.team) : ""' in head
    btn = _fn(APP, "wearBtn")
    assert "if (!t || !twWash(t)) return \"\";" in btn, "only a club with a colour to wash with offers it"
    assert 'aria-pressed="${on}"' in btn and "Wearing these colours" in btn and "Wear these colours" in btn
    toggle = _fn(APP, "wearToggle")
    assert 'setSetting("teamColors", "site");' in toggle and 'setSetting("teamColorsTeam", key);' in toggle
    assert 'setSetting("teamColors", "off");' in toggle, "tapped again, the site's own gold"
    assert "teamColorsWho(s) === key" in _fn(APP, "wearingTeam"), "worn through your follows counts as worn"


def _seam(png, start=0):
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    pix, (w, h) = im.load(), im.size
    worst = (0, 0)
    for x in (2, w - 3):
        col = [pix[x, y] for y in range(h)]
        for y in range(start, h - 1):
            worst = max(worst, (max(abs(col[y + 1][c] - col[y][c]) for c in range(3)), y))
    return worst


def test_in_a_browser_the_site_wears_the_team_with_no_line_at_the_top():
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
    games = [{"home": "DET", "away": "GB", "date": "2099-01-01", "kickoff": "13:00", "spread": -3.5, "favorite": "DET",
              "total": 48.5, "home_ml": -180, "away_ml": 155}]
    body = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2099-01-01", "recommendations": [],
                       "most_likely": [], "games": games, "player_stats": {}})
    team = json.dumps({"sport": "nfl", "profile": {"team": "PIT", "name": "Pittsburgh Steelers",
                                                   "seasons": [{"season": 2026, "record": "6-4"}]}, "squad": []})
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
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                              has_touch=True, service_workers="block", color_scheme=theme)
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                         f" localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', '{theme}');"
                                         " localStorage.setItem('qb_settings_v1', JSON.stringify({ teamColors: 'site', teams: ['nfl:DET'] }));"
                                         " } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.route("**/api/team?*", lambda r: r.fulfill(status=200, content_type="application/json", body=team))
                    for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_function("() => document.querySelector('.sportbar .sport-btn')", timeout=20000)
                    page.wait_for_timeout(700)
                    look = page.evaluate("""() => { const css = (q) => getComputedStyle(document.querySelector(q)).backgroundImage;
                        return { wash: document.documentElement.classList.contains('team-wash'),
                                 same: css('.ambient') === css('.topbar'),
                                 lions: document.documentElement.style.getPropertyValue('--tw-1') === '#005a8b'
                                   && css('.ambient').includes('linear-gradient(100deg'),
                                 wide: document.documentElement.scrollWidth - innerWidth }; }""")
                    seam = _seam(page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": 320}))
                    # A team's page: Wear these colours, then back to the gold.
                    page.evaluate("openTeam('nfl', 'PIT')")
                    page.wait_for_function("() => document.querySelector('[data-wear]')", timeout=15000)
                    page.click("[data-wear]")
                    page.wait_for_timeout(200)
                    worn = page.evaluate("""() => ({ pressed: document.querySelector('[data-wear]').getAttribute('aria-pressed'),
                        tw1: document.documentElement.style.getPropertyValue('--tw-1'),
                        saved: JSON.parse(localStorage.getItem('qb_settings_v1')).teamColorsTeam })""")
                    page.click("[data-wear]")
                    page.wait_for_timeout(200)
                    back = page.evaluate("""() => ({ wash: document.documentElement.classList.contains('team-wash'),
                        mode: JSON.parse(localStorage.getItem('qb_settings_v1')).teamColors })""")
                    found[theme] = {"look": look, "seam": seam, "worn": worn, "back": back, "errors": errors}
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for theme, f in found.items():
        assert f["look"] == {"wash": True, "same": True, "lions": True, "wide": 0}, (theme, f["look"])
        assert f["seam"][0] <= SEAM, f"{theme}: a line of {f['seam'][0]} levels at {f['seam'][1] / 2:.0f}px"
        assert f["worn"] == {"pressed": "true", "tw1": "#a86300", "saved": "nfl:PIT"}, (theme, f["worn"])
        assert f["back"] == {"wash": False, "mode": "off"}, (theme, f["back"])
        assert not f["errors"], (theme, f["errors"])


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
