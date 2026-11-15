"""Every page a link opens has a way back to where you were (2026-11-15).

Ethan, on a player's page opened from a name in a game report: "There's no
button to take me back to the previous page I was on. … I feel like there's a
lot of pages that we lead to, but there's never a back button to go back to
where you were previously." The game, pick and play-by-play pages had their
own Back; a player, a team, the injuries or the standings opened from a card
had none. Now (js/app.js, THE WAY BACK):

  * a tap inside a page (a DOOR) opens its page as a new history entry that
    carries where it came from; a tap on the site's own navigation (a TAB:
    the top bar, sidebar, tab bar, menu, league row, footer, a Back) does not;
  * the page wears one bar, "← Back to …", naming the page it goes back to,
    and pressing it is the browser's own back: the page comes back as it was
    left, scroll and search words included;
  * a player to a teammate, a team to its opponent's page, the search to a
    player, is a new page of the same view; an opponent chip is still a
    filter on its team's page;
  * coming back to a game page keeps where ITS Back goes.

    python3 tests/test_every_page_a_link_opens_has_a_way_back.py
    QB_BROWSER_TESTS=1 python3 tests/test_every_page_a_link_opens_has_a_way_back.py
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from _app import app_js  # noqa: E402
from _windows import block  # noqa: E402

APP = app_js()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def test_a_tap_is_read_before_any_handler_moves_the_page():
    i = APP.index('window.addEventListener("click", (e) => {\n    const t = e.target;\n    const nav')
    assert APP[i:i + 400].rstrip().endswith("}, true);\n}") or "}, true);" in APP[i:i + 400], \
        "the capture phase, on the window: before the page's own handlers"
    nav = APP[APP.index("const WAY_NAV = "):APP.index("const WAY_SESSION")]
    for chrome in (".topbar", ".sidebar", ".tabbar", ".more-sheet", ".sportbar", ".footer",
                   ".way-back", ".gp-back", "[data-gp-back]", "#wall-back"):
        assert chrome in nav, chrome
    assert ".rail" not in nav, "the rail's games and picks are doors"


def test_a_door_writes_an_entry_that_knows_where_it_came_from():
    body = block(APP, "function _switchViewNow(")
    assert ("const door = !booting && !!_lastTap.from && !_lastTap.nav && Date.now() - _lastTap.at < 1500\n"
            "    && _lastTap.at > _routerNavAt;") in body
    assert "const fresh = openedByTap || (door && wayKey(url) !== wayKey(fromHash));" in body
    assert "if (door) { wayStampLeaving(); history.pushState(wayPushState({ view: name }), \"\", `#${name}`); }" in body
    assert "history.replaceState(wayKeepState({ view: name }), \"\", `#${name}`);" in body
    # The bar is drawn on every switch, the team page's early return included.
    assert body.count("paintWayBack();") >= 2
    team = body[body.index('if (name === "team") {'):body.index('if (name === "game") {')]
    assert "paintWayBack();" in team


def test_the_pages_with_their_own_back_and_the_wall_wear_no_bar():
    skips = APP[APP.index("const WAY_SKIPS = "):APP.index("const WAY_NAMES")]
    for v in ("prop", "game", "pbp", "ask", "messages", "paywall", "checkout", "signup", "reset"):
        assert f'"{v}"' in skips, v
    assert ".way-back { display: flex;" in CSS
    rule = CSS[CSS.index(".way-back {"):CSS.index("}", CSS.index(".way-back .way-back-btn")) + 1]
    assert "border" not in rule and "outline" not in rule, "the site draws no hard lines"


def test_the_bar_is_the_browsers_back_and_never_a_dead_button():
    fn = block(APP, "function wayBack(")
    assert "history.back();" in fn and "location.hash = f.hash;" in fn
    assert "if ((history.state || {}).w === WAY_SESSION) {" in fn
    # A step between two paths fires no hashchange: the bar tells the router.
    assert 'if (_hashSeenAt < t0) window.dispatchEvent(new HashChangeEvent("hashchange"));' in fn
    land = block(APP, "function _landScroll(")
    assert "} else if (back && wayLanded() != null) {\n    y = wayLanded();" in land


def test_the_names_and_the_keys():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no Node)")
        return
    i = APP.index("const WAY_NAMES = ")
    prog = ("const state = {view: '', playerSlug: '', search: ''}; let _teamState = {};"
            "let _profRows = new Map();"
            "const teamNameIn = (s, t) => ({DET: 'Lions', NE: 'Patriots'})[t] || t;"
            "const deslug = (s) => String(s || '').replace(/-+/g, ' ').trim();"
            "const document = {querySelector: (q) => q.includes('likely') ? {textContent: ' Most Likely '} : null};\n"
            + APP[i:APP.index("};", i) + 2] + "\n" + block(APP, "function wayKey(") + "\n"
            + block(APP, "function wayName(") + """
const out = [];
out.push(wayKey('#team/nfl/DET/GB'), wayKey('#team/nfl/DET'), wayKey('#player/drake-maye'), wayKey('#likely'));
_teamState = {sport: 'nfl', team: 'DET'}; out.push(wayName('team'));
state.playerSlug = 'amon-ra-st-brown'; out.push(wayName('players'));
_profRows = new Map([['Amon-Ra St. Brown', []]]); out.push(wayName('players'));
state.playerSlug = ''; out.push(wayName('players'));
out.push(wayName('game'), wayName('pbp'), wayName('prop'), wayName('recommended'), wayName('likely'), wayName('zzz'));
console.log(JSON.stringify(out));
""")
    got = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-600:]
    assert json.loads(got.stdout) == [
        "team/nfl/DET", "team/nfl/DET", "player/drake-maye", "likely",
        "the Lions", "Amon Ra St Brown", "Amon-Ra St. Brown", "the search",
        "the game", "the game", "the pick", "the board", "Most Likely", "the last page"], got.stdout


def test_back_to_the_search_brings_its_words_back():
    router = APP[APP.index('window.addEventListener("hashchange", () => {\n    _routerNavAt'):]
    router = router[:router.index("// An IN-PAGE ANCHOR")]
    assert 'if (h === "players" && state.playerSlug) waySearchBack();' in router
    fn = block(APP, "function waySearchBack(")
    assert "state.search = here.q || \"\";" in fn and "_landScroll(\"players\", \"players\");" in fn


def _board():
    names = [("Drake Maye", "NE", "DET"), ("Amon-Ra St. Brown", "DET", "NE")]
    rows = []
    for i in range(30):
        player, team, opp = names[i % 2] if i < 2 else (f"Player Name {i}", "NE", "DET")
        rows.append({"player": player, "team": team, "opponent": opp, "market": "rec_yds",
                     "market_label": "Receiving Yards", "side": "over", "line": 40.5 + i, "odds": -150,
                     "book": "draftkings", "model_prob": 0.7 - i * 0.005, "hit_prob": 0.7,
                     "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": "top",
                     "bettable": True, "confidence": 7.0, "grade": "B", "projection": 50.0,
                     "reasons": ["because"], "recommended": True})
    return {"sport": "nfl", "date": "2099-W01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 30}, "lanes": {"prop": 30}},
            "games": [{"home": "DET", "away": "NE", "date": "2099-01-01", "kickoff": "13:00",
                       "spread": -3.5, "total": 44.5}], "player_stats": {}}


def test_in_a_browser_a_link_opens_a_page_with_a_way_back():
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
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                # bypass_csp: the waits below poll an expression, which the
                # site's own policy (script-src 'self') would refuse to eval.
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                          has_touch=True, service_workers="block", bypass_csp=True)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                # At the root, as the site is served (the manifest starts at
                # /#recommended and <base href="/"> resolves every hash there).
                page.goto(f"http://127.0.0.1:{port}/#likely", wait_until="load")
                page.wait_for_function("state.view === 'likely' && document.querySelectorAll('#view-likely [data-open]').length > 5",
                                       timeout=20000)
                page.wait_for_timeout(600)
                view = lambda: page.evaluate("state.view")  # noqa: E731
                bar = lambda: page.evaluate(  # noqa: E731
                    "(() => { const b = document.querySelector(`#view-${state.view} > .way-back`);"
                    " return b && b.offsetParent !== null ? b.textContent.trim() : ''; })()")
                assert bar() == "", "a page opened from the tab bar wears no bar"

                # A door, scrolled down the page: a player's name.
                page.evaluate("""() => {
                  const host = document.getElementById('view-likely');
                  const rows = host.querySelectorAll('[data-open]');
                  rows[Math.min(6, rows.length - 1)].insertAdjacentHTML('afterend',
                    '<p><button type="button" id="t-door" data-player-page="drake-maye">Drake Maye</button></p>');
                  document.getElementById('t-door').scrollIntoView({ block: 'center', behavior: 'instant' });
                }""")
                page.wait_for_timeout(300)
                y0 = page.evaluate("Math.round(window.scrollY)")
                assert y0 > 300, f"the fixture board is too short to scroll ({y0})"
                page.click("#t-door")
                page.wait_for_function("state.view === 'players'", timeout=5000)
                page.wait_for_timeout(500)
                assert page.evaluate("location.hash") == "#player/drake-maye"
                assert bar() == "← Back to Most Likely", bar()

                # The bar goes back, to the place on the page.
                page.click("#view-players > .way-back [data-way-back]")
                page.wait_for_function("state.view === 'likely'", timeout=5000)
                page.wait_for_timeout(900)
                assert page.evaluate("location.hash") == "#likely"
                y1 = page.evaluate("Math.round(window.scrollY)")
                assert abs(y1 - y0) < 40, (y0, y1)
                assert bar() == ""

                # Player → his team → back → the player → back → the board.
                # (The board redrew on the way back, so the door goes in again.)
                page.evaluate("""() => {
                  document.getElementById('view-likely').insertAdjacentHTML('afterbegin',
                    '<p><button type="button" id="t-door" data-player-page="drake-maye">Drake Maye</button></p>');
                }""")
                page.click("#t-door")
                page.wait_for_function("state.view === 'players' && location.hash === '#player/drake-maye'", timeout=5000)
                page.wait_for_timeout(400)
                page.evaluate("""() => {
                  document.getElementById('players-board').insertAdjacentHTML('afterbegin',
                    '<button type="button" id="t-team" data-team-sport="nfl" data-team-open="NE">Patriots</button>');
                }""")
                page.click("#t-team")
                page.wait_for_function("state.view === 'team'", timeout=5000)
                page.wait_for_timeout(500)
                assert page.evaluate("location.hash").startswith("#team/nfl/NE"), page.evaluate("location.hash")
                assert bar() == "← Back to Drake Maye", bar()
                page.click("#view-team > .way-back [data-way-back]")
                page.wait_for_function("state.view === 'players' && location.hash === '#player/drake-maye'", timeout=5000)
                page.wait_for_timeout(400)
                assert bar() == "← Back to Most Likely", bar()
                page.go_back()
                page.wait_for_function("state.view === 'likely'", timeout=5000)

                # The search to a player and back: the words come back.
                page.click(".tabbar [data-view='recommended']")
                page.wait_for_function("state.view === 'recommended'", timeout=5000)
                page.evaluate("switchView('players', true)")
                page.wait_for_function("state.view === 'players'", timeout=5000)
                page.fill("#player-search", "player name")
                page.wait_for_timeout(600)
                assert bar() == "", "the search opened by the site's own control wears no bar"
                page.evaluate("""() => {
                  document.getElementById('players-board').insertAdjacentHTML('afterbegin',
                    '<button type="button" id="t-p3" data-player-page="player-name-3">Player Name 3</button>');
                }""")
                page.click("#t-p3")
                page.wait_for_function("location.hash === '#player/player-name-3'", timeout=5000)
                page.wait_for_timeout(400)
                assert bar() == "← Back to the search", bar()
                page.click("#view-players > .way-back [data-way-back]")
                page.wait_for_function("location.hash === '#players'", timeout=5000)
                page.wait_for_timeout(500)
                assert page.evaluate("state.playerSlug") == ""
                assert page.input_value("#player-search") == "player name"
                assert bar() == ""

                # A tab tap from a page with a bar: the tab's page has none.
                page.evaluate("""() => {
                  document.getElementById('players-board').insertAdjacentHTML('afterbegin',
                    '<button type="button" id="t-p4" data-player-page="player-name-4">Player Name 4</button>');
                }""")
                page.click("#t-p4")
                page.wait_for_function("location.hash === '#player/player-name-4'", timeout=5000)
                page.wait_for_timeout(300)
                assert bar() == "← Back to the search"
                page.click(".tabbar [data-view='live']")
                page.wait_for_function("state.view === 'live'", timeout=5000)
                page.wait_for_timeout(400)
                assert bar() == ""
                assert page.evaluate("document.querySelectorAll('.way-back').length") == 0
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_a_report_name_and_back_keeps_the_game_pages_own_back():
    """The screenshot's case: a game page, a name in its report, the
    player's page, back — and the game page's own Back still names the
    page the game was opened from. Then once more from /index.html, where
    the hash resolves to another path and the browser fires no hashchange
    on the way back."""
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
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for path in ("/#likely", "/index.html#likely"):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                              has_touch=True, service_workers="block", bypass_csp=True)
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}{path}", wait_until="load")
                    page.wait_for_function("state.view === 'likely' && document.querySelectorAll('#view-likely [data-open]').length > 5",
                                           timeout=20000)
                    page.wait_for_timeout(600)
                    bar = lambda: page.evaluate(  # noqa: E731
                        "(() => { const b = document.querySelector(`#view-${state.view} > .way-back`);"
                        " return b && b.offsetParent !== null ? b.textContent.trim() : ''; })()")
                    if path == "/#likely":
                        page.evaluate("""() => {
                          document.getElementById('view-likely').insertAdjacentHTML('afterbegin',
                            '<p><button type="button" id="t-game">NE @ DET</button></p>');
                          document.getElementById('t-game').addEventListener('click', () => openGame('ne-det-0101'));
                        }""")
                        page.click("#t-game")
                        page.wait_for_function("state.view === 'game'", timeout=5000)
                        page.wait_for_timeout(700)
                        assert page.evaluate("(document.getElementById('gp-back') || {}).textContent") == "← Back to Most Likely"
                        assert bar() == "", "the game page keeps its own Back"
                        # A name in the report.
                        page.evaluate("""() => {
                          document.getElementById('view-game').insertAdjacentHTML('beforeend',
                            '<p><button type="button" id="t-name" data-player-page="amon-ra-st-brown">Amon-Ra St. Brown</button></p>');
                        }""")
                        page.click("#t-name")
                        page.wait_for_function("location.hash === '#player/amon-ra-st-brown'", timeout=5000)
                        page.wait_for_timeout(500)
                        assert bar() == "← Back to the game", bar()
                        page.click("#view-players > .way-back [data-way-back]")
                        page.wait_for_function("state.view === 'game'", timeout=5000)
                        page.wait_for_timeout(700)
                        assert page.evaluate("location.hash").startswith("#game/")
                        assert page.evaluate("(document.getElementById('gp-back') || {}).textContent") == "← Back to Most Likely", \
                            "coming back to the game kept where its Back goes"
                        page.click("#gp-back")
                        page.wait_for_function("state.view === 'likely'", timeout=5000)
                    else:
                        page.evaluate("""() => {
                          document.getElementById('view-likely').insertAdjacentHTML('afterbegin',
                            '<p><button type="button" id="t-door" data-player-page="drake-maye">Drake Maye</button></p>');
                        }""")
                        page.click("#t-door")
                        page.wait_for_function("location.hash === '#player/drake-maye'", timeout=5000)
                        page.wait_for_timeout(400)
                        assert bar() == "← Back to Most Likely", bar()
                        page.click("#view-players > .way-back [data-way-back]")
                        page.wait_for_function("state.view === 'likely'", timeout=5000)
                    assert not errors, (path, errors)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
