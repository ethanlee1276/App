"""The player's page in the club's colours (PLRWASH1, 2026-11-17).

Ethan, with the Panthers @ Saints live page, the top of it circled: "Also the
player page should be colorful with there team colors like how the live page
looks".

So the page wears its club's two colours as a live game's page wears its two
clubs' (web/js/playerpage.js plrFrameOn, web/css/playerpage.css):

  - the pair is the whole-site wash's own (app.js twWash), save that white,
    silver and grey are a kit's trim beside a club's real colours: they step
    aside for the club's next colour, else a deeper shade of the first (the
    Leafs and Duke are blue on blue, not blue into fog); a club whose colours
    are all trim and black keeps them, and a club in black alone keeps the
    site's own light;
  - the colours go on <body> deepened (white type reads on them) and as they
    are (paper thins them into the page), and the bar, the screen behind the
    page and the strip under a phone's clock paint one picture, the bar told
    how far across the screen it starts;
  - the page is the player's: the search's head waits behind the way back;
  - off when the board stops showing a player's page, when another page
    opens, and handed back to the whole-site wash where one is worn;
  - and in a browser (QB_BROWSER_TESTS=1), at a phone's width: the Bills'
    blue and red on Josh Allen's page over a reader's own Dolphins wash, one
    picture with no rule at the top of the screen, nothing sideways, the
    Dolphins back on the way back to the search and on leaving for another
    page; on paper the header keeps its band over the thinned colours.

    python3 tests/test_the_player_page_wears_the_team_colours.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_player_page_wears_the_team_colours.py
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
PAGE = open(os.path.join(ROOT, "web", "js", "playerpage.js"), encoding="utf-8").read()
SHEET = open(os.path.join(ROOT, "web", "css", "playerpage.css"), encoding="utf-8").read()

#: Adjacent rows at the top of the screen may differ by this much (0-255, any channel), as the
#: whole-site wash's own test allows.
SEAM = 6

#: The clubs as the site's team tables hold them (web/js/teams.js, teams_nba.js, teams_nhl.js; Duke
#: as college's board names it), and a club in black alone.
CLUBS = {
    "BUF": {"primary": "#00338d", "secondary": "#c60c30", "tertiary": "#0c2e82"},
    "NYK": {"primary": "#006bb6", "secondary": "#f58426", "tertiary": "#bec0c2"},
    "TOR": {"primary": "#00205b", "secondary": "#ffffff", "tertiary": "#000000"},
    "DUKE": {"primary": "#003087", "secondary": "#FFFFFF"},
    "LV": {"primary": "#a5acaf", "secondary": "#000000", "tertiary": "#a6aeb0"},
    "BKN": {"primary": "#1a1a1a", "secondary": "#ffffff", "tertiary": "#707271"},
    "INK": {"primary": "#000000"},
}


def _fn(src, name):
    at = src.index(f"function {name}(")
    return src[at:src.index("\n}\n", at) + 3]


def _line(src, start):
    at = src.index(start)
    return src[at:src.index("\n", at) + 1]


def _section():
    at = SHEET.index("THE PLAYER'S PAGE IN THE CLUB'S COLOURS (PLRWASH1")
    return SHEET[at:SHEET.index("@media (max-width: 640px)", at)]


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", body], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


#: The colour arithmetic as the page runs it (app.js), and the page's own wash (playerpage.js).
COLOUR = ("".join(_fn(APP, n) for n in ("okLab", "okRgb", "twWash"))
          + "".join(_line(APP, s) for s in ("const rgbHex = ", "const TW_DEEP_L", "const twHex6 = ")))
WASH = ("".join(_line(PAGE, s) for s in ("const PLR_WASH_VARS = ", "let _plrWatch = "))
        + "".join(_fn(PAGE, n) for n in ("plrFrameOn", "plrWashPair", "plrWashOff", "plrFrameOff", "plrPin")))


def test_the_pair_is_the_clubs_colours_and_not_its_trim():
    got = _node("""%s%s
const CLUBS = %s;
const chroma = (c) => { const [, a, b] = okLab(c); return Math.hypot(a, b); };
const out = {};
for (const [k, t] of Object.entries(CLUBS)) {
  const w = plrWashPair(t), raw = twWash(t);
  out[k] = w && { deep: w.deep, paper: w.paper, hued: w.deep.map((c) => chroma(c) >= TW_HUED),
                  light: w.deep.map((c) => okLab(c)[0] <= TW_DEEP_L + 0.005), raw: raw && raw.deep };
}
console.log(JSON.stringify(out));
""" % (COLOUR, WASH, json.dumps(CLUBS)))
    # A club with no trim in its pair wears the whole-site wash's own pair.
    assert got["BUF"]["deep"] == ["#00338d", "#c60c30"] == got["BUF"]["raw"], got["BUF"]
    assert got["NYK"]["deep"] == ["#006bb6", "#ba5100"] == got["NYK"]["raw"], got["NYK"]
    assert got["NYK"]["paper"] == ["#006bb6", "#f58426"], "paper wears them as they are"
    # White beside a real colour is trim: blue on blue, not blue into fog.
    for club, deep in (("TOR", ["#00205b", "#00003f"]), ("DUKE", ["#003087", "#00005e"])):
        assert got[club]["deep"] == deep and all(got[club]["hued"]), (club, got[club])
        assert got[club]["raw"][1] != deep[1], (club, "twWash alone washes into grey", got[club]["raw"])
        assert got[club]["paper"][1] != "#ffffff", (club, got[club]["paper"])
    # Every colour is deep enough for white type.
    assert all(all(v["light"]) for v in got.values() if v), {k: v["deep"] for k, v in got.items() if v}
    # All trim and black: those are the club.
    assert got["LV"]["deep"] == got["LV"]["raw"] and got["LV"]["paper"][0] == "#a5acaf", got["LV"]
    assert got["BKN"]["deep"] == got["BKN"]["raw"], got["BKN"]
    assert got["INK"] is None, "a club in black alone keeps the site's own light"


def test_the_colours_go_on_the_page_and_come_off_it():
    got = _node("""%s
const set = () => { const s = new Set(); return { s, add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c) }; };
const bodyCls = set(), viewCls = set(), props = {}, barProps = {};
const view = { classList: viewCls }, board = { querySelector: () => null };
const bar = { getBoundingClientRect: () => ({ left: 240, width: 1040 }), style: { setProperty: (k, v) => { barProps[k] = v; } } };
global.document = {
  getElementById: (id) => ({ "view-players": view, "players-board": board })[id] || null,
  querySelector: (q) => (q === ".topbar" ? bar : null),
  body: { classList: bodyCls, style: { setProperty: (k, v) => { props[k] = v; }, removeProperty: (k) => { delete props[k]; } } } };
%s
const CLUBS = %s;
const teamsIn = (sport) => (sport === "nfl" ? CLUBS : {});
const look = () => ({ body: [...bodyCls.s], view: [...viewCls.s], props: { ...props }, bar: { ...barProps } });
const out = {};
plrFrameOn("nfl", "BUF"); out.bills = look();
plrFrameOn("nfl", "INK"); out.ink = look();
plrFrameOn("nfl", "TOR"); plrFrameOn("nfl", ""); out.nobody = look();
plrFrameOn("nfl", "BUF"); plrFrameOff(); out.off = look();
console.log(JSON.stringify(out));
""" % (COLOUR, WASH, json.dumps(CLUBS)))
    assert got["bills"] == {"body": ["plr-on"], "view": ["plr-view"], "bar": {"--pw-x": "-240px"},
                            "props": {"--pw-1": "#00338d", "--pw-2": "#c60c30",
                                      "--pw-1-paper": "#00338d", "--pw-2-paper": "#c60c30"}}, got["bills"]
    # No colour to wear: the page is still the player's, on the site's own light.
    for k in ("ink", "nobody"):
        assert got[k]["body"] == [] and got[k]["props"] == {} and got[k]["view"] == ["plr-view"], (k, got[k])
    assert got["off"]["body"] == [] and got["off"]["view"] == [] and got["off"]["props"] == {}, got["off"]


def test_every_way_onto_the_page_and_off_it_is_covered():
    draw = _fn(PAGE, "renderPlayerPage")
    assert draw.count("plrFrameOn(") == 2, "the same player's page put back on a redraw, and a new page"
    assert "host.replaceChildren(same);\n    plrFrameOn(sport, same._plr.team);" in draw
    assert "plrMarkets(page, kept);\n  plrFrameOn(sport, team);" in draw
    fill = _fn(PAGE, "plrFill")
    assert "d.team !== page._plr.team && page.isConnected && _plrLive && _plrLive.page === page" in fill, \
        "the page's own answer names the club the search did not"
    on = _fn(PAGE, "plrFrameOn")
    assert 'board.querySelector(":scope > .plr")' in on and "_plrWatch.observe(board, { childList: true });" in on, \
        "any drawing of the Players page that is not a player's takes the colours with it"
    switch = _fn(APP, "_switchViewNow")
    assert 'if (name !== "players" && typeof plrFrameOff === "function") plrFrameOff();' in switch, "another page opens"


def test_the_sheet_paints_one_picture_like_the_live_page():
    css = _section()
    # Both colours, each a gradient on its own property, as every gradient on the page is.
    assert "  --pw-wash: linear-gradient(100deg, var(--pw-1) 6%" in css and "var(--pw-2) 94%)" in css
    # Each colour defined in the sheet too (the night's own), the club's put on inline over it.
    assert all(f"  --pw-{k}: var(--night-" in css for k in ("1", "2", "1-paper", "2-paper"))
    assert "--pw-shade: linear-gradient(180deg," in css and "var(--bg) 820px)" in css
    assert '[data-theme="light"] body.plr-on {\n  --pw-wash: linear-gradient(100deg, color-mix(in oklab, var(--pw-1-paper) 34%, var(--bg))' in css
    # One picture: the screen behind the page, the bar and the strip under a phone's clock.
    assert ("html body.plr-on .ambient, html body.plr-on:not(.gp-on) .topbar,\n"
            "html.store-ios body.plr-on:not(.gp-on)::before, html.ios-home body.plr-on:not(.gp-on)::before {\n"
            "  background: var(--pw-shade), var(--pw-wash), var(--bg);\n"
            "  background-size: 100vw 100vh; background-repeat: no-repeat; background-position: 0 0; }") in css
    assert ("html body.plr-on:not(.gp-on) .topbar {\n  --pw-x: 0px;\n"
            "  background-position: var(--pw-x) 0; border-bottom-color: transparent; animation: none; }") in css
    assert "html body.plr-on:not(.gp-on) .topbar::before, html body.plr-on:not(.gp-on) .topbar::after { display: none; }" in css
    assert "html body.plr-on:not(.gp-on) .sportbar { background: transparent; }" in css
    # At night the name lies on the colours and the cards are glass with no blur.
    assert 'html:not([data-theme="light"]) body.plr-on .plr-hero { background: none;' in css
    assert "--panel: rgba(12, 11, 14, .34);" in css and "blur(" not in css
    # Less transparency or more contrast asked for: the theme's own solid panels come back.
    assert ("@media (prefers-reduced-transparency: reduce), (prefers-contrast: more) {\n"
            "  html:not([data-theme=\"light\"]) body.plr-on #view-players {\n"
            "    --panel: inherit; --panel-2: inherit; --panel-3: inherit; --bg-2: inherit;") in css
    # The page is the player's.
    assert ("#view-players.plr-view > .section-title, #view-players.plr-view > .search-scope, #view-players.plr-view > .search-recent,\n"
            "#view-players.plr-view > .search-wrap, #view-players.plr-view > #team-hits { display: none; }") in css
    # As specific as the whole-site wash and later, so the player's club wins over the reader's.
    styles = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    assert "html.team-wash .ambient, html.team-wash body:not(.gp-on) .topbar," in styles


def _seam(png, start=0):
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
            worst = max(worst, (max(abs(col[y + 1][c] - col[y][c]) for c in range(3)), y))
    return worst


def _settled(page, clip, tries=12):
    """The strip once two shots in a row are the same (bounded)."""
    last = page.screenshot(clip=clip)
    for _ in range(tries):
        page.wait_for_timeout(120)
        now = page.screenshot(clip=clip)
        if now == last:
            return now
        last = now
    return last


def _rec(player, team, market, label, line):
    logs = [{"value": line + d, "week": w, "opponent": "MIA", "home": w % 2 == 0} for w, d in ((11, 6), (10, -9), (9, 14))]
    return {"player": player, "team": team, "opponent": "MIA", "position": "QB", "market": market, "market_label": label,
            "side": "OVER", "line": line, "odds": -110, "book": "DraftKings", "book_name": "DraftKings",
            "projection": line + 10, "hit_prob": 0.58, "raw_prob": 0.6, "edge": 0.05, "grade": "A", "recommended": True,
            "logs": logs, "headshot": "", "sport": "nfl", "reasons": ["Volume up"],
            "form": {"last1": line + 6, "last3": line + 3, "last5": line + 1, "last10": line, "season": line},
            "bet_links": [["DraftKings", "https://sportsbook.draftkings.test/x", -110]]}


def test_in_a_browser_the_page_wears_its_club_and_hands_the_screen_back():
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
    board = {"sport": "nfl", "player_stats": {}, "recommendations": [_rec("Josh Allen", "BUF", "pass_yds", "Passing Yards", 245.5)]}
    shell = {"sport": "nfl", "player": "Josh Allen", "team": "BUF", "position": "QB", "seasons": [2026], "season": 2026,
             "bio": {"number": "17", "position": "QB"}, "notes": {}, "headline": [], "splits": {"rows": [], "groups": []},
             "career": {"rows": [], "groups": [], "total": {}}}
    looks = """() => { const css = (q) => getComputedStyle(document.querySelector(q)), body = getComputedStyle(document.body);
        const view = document.getElementById('view-players');
        return { on: document.body.classList.contains('plr-on'), page: view.classList.contains('plr-view'),
                 pw: [body.getPropertyValue('--pw-1').trim(), body.getPropertyValue('--pw-2').trim()],
                 bar: css('.topbar').backgroundImage, same: css('.topbar').backgroundImage === css('.ambient').backgroundImage,
                 site: document.documentElement.classList.contains('team-wash'),
                 shown: [...view.children].filter((e) => getComputedStyle(e).display !== 'none').map((e) => e.id || e.className),
                 band: document.querySelector('.plr-hero') ? css('.plr-hero').backgroundImage.startsWith('linear-gradient') : null,
                 wide: document.documentElement.scrollWidth - innerWidth }; }"""
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
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True,
                                              has_touch=True, service_workers="block", color_scheme=theme)
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    local = f"http://127.0.0.1:{port}/"
                    page.route(lambda u: not u.startswith(local), lambda r: r.abort())

                    def answer(obj):
                        return lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(obj))
                    for pattern, obj in (("**/api/players/gamelog*", {}), ("**/api/players/logs*", {"player": "x", "stats": {}}),
                                         ("**/api/players/search*", {"players": []}), ("**/api/players/page*", shell),
                                         ("**/data/news.json*", {"sports": {"nfl": []}}),
                                         ("**/api/recommendations*", board), ("**/data/recommendations*", board)):
                        page.route(pattern, answer(obj))
                    # At night the reader wears the Dolphins across the site (MYCOLORS1); on paper, nothing.
                    mine = "localStorage.setItem('qb_settings_v1', JSON.stringify({ teamColors: 'site', teams: ['nfl:MIA'] }));" \
                        if theme == "dark" else ""
                    page.add_init_script("try { localStorage.setItem('qb_intro_v1', '1'); localStorage.setItem('qb.tour', 'done');"
                                         f" localStorage.setItem('ge-theme', '{theme}'); {mine} }} catch (e) {{}}")
                    page.goto(f"{local}index.html?sport=nfl#players", wait_until="load")
                    page.wait_for_selector(".psr-row[data-player-page='josh-allen']", timeout=30000)
                    page.wait_for_timeout(300)
                    f = {"list": page.evaluate(looks)}
                    page.click(".psr-row[data-player-page='josh-allen']")
                    page.wait_for_selector(".plr .plr-tonight .profile", timeout=30000)
                    page.wait_for_function("() => document.body.classList.contains('plr-on')", timeout=8000)
                    page.wait_for_timeout(300)
                    f["page"] = page.evaluate(looks)
                    f["seam"] = _seam(_settled(page, {"x": 0, "y": 0, "width": 390, "height": 320}))
                    page.click("#view-players > .way-back [data-way-back]")
                    page.wait_for_function("() => location.hash === '#players' && !state.playerSlug", timeout=8000)
                    page.wait_for_selector("#players-board .psr-row", timeout=8000)
                    f["back"] = page.evaluate(looks)
                    page.evaluate("() => openPlayer('Josh Allen')")
                    page.wait_for_function("() => document.body.classList.contains('plr-on')", timeout=30000)
                    page.evaluate("() => switchView('recommended')")
                    page.wait_for_function("() => state.view === 'recommended'", timeout=8000)
                    page.wait_for_timeout(200)
                    f["left"] = page.evaluate(looks)
                    f["errors"] = errors
                    found[theme] = f
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    bills = "rgb(0, 51, 141)"
    for theme, f in found.items():
        pg = f["page"]
        assert pg["on"] and pg["page"] and pg["pw"] == ["#00338d", "#c60c30"], (theme, pg)
        assert pg["same"], (theme, "the bar and the screen behind the page are one picture", pg["bar"])
        # (Paper thins the colours into the page, so its picture holds mixes, not the Bills' blue itself.)
        assert bills in pg["bar"] or theme == "light", (theme, "the Bills' picture", pg["bar"])
        assert pg["shown"] == ["way-back", "players-board"], (theme, "the search's head waits behind the way back", pg["shown"])
        assert pg["wide"] <= 0, (theme, pg["wide"])
        assert f["seam"][0] <= SEAM, f"{theme}: a line of {f['seam'][0]} levels at {f['seam'][1]}px"
        for k in ("back", "left"):
            assert not f[k]["on"] and not f[k]["page"] and f[k]["pw"] == ["", ""], (theme, k, f[k])
        assert "search-wrap" in f["back"]["shown"], (theme, f["back"]["shown"])
        assert not f["errors"], (theme, f["errors"])
    night, paper = found["dark"], found["light"]
    # Over the reader's own Dolphins: the player's club while the page is open, the Dolphins either side of it.
    assert night["list"]["site"] and night["page"]["site"] and night["back"]["site"], night["list"]
    assert night["list"]["bar"] != night["page"]["bar"] and bills not in night["list"]["bar"], night["list"]["bar"]
    assert night["back"]["bar"] == night["list"]["bar"] == night["left"]["bar"], "the reader's wash, handed back"
    assert night["page"]["band"] is False, "at night the name lies on the colours"
    # Paper: the colours thinned into the page, the header keeping its band.
    assert paper["page"]["band"] is True and not paper["list"]["site"], paper["page"]
    assert paper["page"]["bar"] != paper["list"]["bar"], paper["page"]["bar"]


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
