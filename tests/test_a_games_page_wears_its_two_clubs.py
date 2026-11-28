"""A game's page wears its two clubs' colours (GAMEWASH1).

Ethan, 2026-11-19: "go through the visuals of the site and continue on the
color work". A live game's page sat on its two clubs' colours, a team's page
and a player's on their club's; the page a game has before it starts and
after it ends sat on the site's gold. What these hold:

  * the game's page names both clubs (detail.js renderGamePage →
    pageClubOn("sport:AWAY+sport:HOME")) and the screen wears the away club
    from the left and the home club from the right, with the colour setting
    off too, and over your own colours if you wear some;
  * each club by its real colours; where the two firsts read as one colour
    the away side wears its second (the live page's rule); one club with no
    colours on file leaves the screen to the other, and a fight card (no
    clubs at all) leaves it to you, or the site;
  * the bar's tint stays yours: a game has two clubs, and neither is you;
  * leaving the page hands the screen back (the router names no club);
  * in a browser: the page opens on the two clubs and the board gets its
    own look back.

    python3 tests/test_a_games_page_wears_its_two_clubs.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TW = __import__("test_a_team_page_wears_its_club_and_the_colours_fade")   # the colour harness (a sibling test)

APP = TW.APP
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
TABLES = {"nfl": {"TB": {"primary": "#d50a0a", "secondary": "#34302b"},
                  "DET": {"primary": "#005a8b", "secondary": "#b0b7bc", "tertiary": "#000000"},
                  "IND": {"primary": "#00508f", "secondary": "#c8102e"},
                  "PIT": {"primary": "#000000", "secondary": "#ffb612", "tertiary": "#c60c30"}},
          "ufc": {}}
OFF = {"teamColors": "off", "teams": []}


def test_the_away_club_from_the_left_and_the_home_club_from_the_right_with_the_setting_off():
    on, gone = TW._run(OFF, ["pageClubOn('nfl:TB+nfl:DET')", "pageClubOn('')"], TABLES)
    assert on["classes"] == {"team-wash": True, "club-page": True, "team-tint": False}, on["classes"]
    assert (on["props"]["--tw-1"], on["props"]["--tw-2"]) == ("#d50a0a", "#005a8b"), on["props"]
    assert (on["props"]["--tw-1-paper"], on["props"]["--tw-2-paper"]) == ("#d50a0a", "#005a8b")
    assert gone["classes"] == {"team-wash": False, "club-page": False, "team-tint": False}, "the screen is handed back"


def test_two_clubs_in_one_colour_and_the_away_side_wears_its_second():
    # The Colts' blue beside the Lions' reads as one colour: the Colts' red, then.
    same, = TW._run(OFF, ["pageClubOn('nfl:IND+nfl:DET')"], TABLES)
    assert (same["props"]["--tw-1"], same["props"]["--tw-2"]) == ("#c8102e", "#005a8b"), same["props"]
    rule = TW._fn(APP, "pairWash")
    assert "away.deep.findIndex((c) => apart(c, home.deep[0]))" in rule and ">= TW_APART" in rule
    assert "const home = homes[0] || GP_GREY;" in TW._fn(DETAIL, "gpWashColours"), "the live page's rule: home keeps its first"


def test_one_club_without_colours_leaves_the_screen_to_the_other_and_a_fight_card_to_you():
    lone, other, fight = TW._run(OFF, ["pageClubOn('nfl:NOPE+nfl:DET')", "pageClubOn('nfl:TB+nfl:NOPE')",
                                       "pageClubOn('ufc:A+ufc:B')"], TABLES)
    assert lone["classes"]["team-wash"] and lone["props"]["--tw-2"] == "#005a8b" and lone["props"]["--tw-1"] != "#005a8b"
    assert other["classes"]["team-wash"] and other["props"]["--tw-2"] == "#d50a0a"
    assert fight["classes"] == {"team-wash": False, "club-page": False, "team-tint": False}, "no clubs: the site's own"
    # Wearing your own colours across the site, a fight card keeps them; they are not the page's clubs.
    mine = {"teamColors": "site", "teams": ["nfl:PIT"]}
    home, card = TW._run(mine, ["applyTeamColors()", "pageClubOn('ufc:A+ufc:B')"], TABLES)
    assert card["classes"] == {"team-wash": True, "club-page": False, "team-tint": True}, card["classes"]
    assert card["props"]["--tw-1"] == home["props"]["--tw-1"] == "#a56400"


def test_the_bars_tint_stays_yours_over_a_games_two_clubs():
    mine = {"teamColors": "site", "teams": ["nfl:PIT"]}
    home, game, team = TW._run(mine, ["applyTeamColors()", "pageClubOn('nfl:TB+nfl:DET')", "pageClubOn('nfl:DET')"], TABLES)
    assert (game["props"]["--tw-1"], game["props"]["--tw-2"]) == ("#d50a0a", "#005a8b"), "the game's clubs, over your own"
    assert game["props"]["--team-1"] == home["props"]["--team-1"] == "#000000", "a game has two clubs, and neither is you"
    assert game["classes"] == {"team-wash": True, "club-page": True, "team-tint": True}
    # One club's page does take the tint: it is that club's page.
    assert team["props"]["--team-1"] == "#005a8b"


def test_the_page_names_its_clubs_and_the_router_hands_the_screen_back():
    draw = TW._fn(DETAIL, "renderGamePage")
    named = 'pageClubOn(g && g.away && g.home ? `${state.sport}:${g.away}+${state.sport}:${g.home}` : "");'
    assert named in draw and 'if (state.view === "game" && typeof pageClubOn === "function") {' in draw
    assert draw.index(named) < draw.index("That game isn’t on the current slate"), "a game not on the slate names none"
    assert 'if (name !== "team" && name !== "game") pageClubOn("");' in TW._fn(APP, "_switchViewNow")
    assert 'const pair = _pageClub.includes("+");' in TW._fn(APP, "applyTeamColors")


def test_in_a_browser_the_page_opens_on_its_two_clubs_and_the_board_gets_its_look_back():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    games = [{"home": "DET", "away": "TB", "date": "2099-01-01", "kickoff": "13:00", "spread": -3.5, "favorite": "DET",
              "total": 48.5, "home_ml": -180, "away_ml": 155}]
    body = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2099-01-01", "recommendations": [],
                       "most_likely": [], "games": games, "player_stats": {}})
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block", color_scheme="dark", bypass_csp=True)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', 'dark'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_function("typeof state !== 'undefined' && (state.data && state.data.games || []).length > 0", timeout=20000)
                look = """() => ({ wash: document.documentElement.classList.contains('team-wash'),
                    club: document.documentElement.classList.contains('club-page'),
                    tw: [document.documentElement.style.getPropertyValue('--tw-1'), document.documentElement.style.getPropertyValue('--tw-2')],
                    back: getComputedStyle(document.querySelector('.ambient')).backgroundImage,
                    view: state.view, wide: document.documentElement.scrollWidth - innerWidth })"""
                before = page.evaluate(look)
                page.evaluate("openGame('2099-01-01_TB@DET')")
                page.wait_for_function("state.view === 'game' && document.documentElement.classList.contains('club-page')", timeout=10000)
                on = page.evaluate(look)
                want = page.evaluate("pairWash('nfl:TB+nfl:DET').deep")
                page.evaluate("switchView('recommended')")
                page.wait_for_function("!document.documentElement.classList.contains('club-page')", timeout=10000)
                page.wait_for_timeout(700)                       # the cross-fade's copy has gone
                after = page.evaluate(look)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors[:2]
    assert not before["wash"] and not before["club"], before
    assert on["wash"] and on["club"] and on["tw"] == want and want[0] != want[1], (on, want)
    assert "linear-gradient(100deg" in on["back"] and on["back"] != before["back"], on["back"][:160]
    assert on["wide"] <= 0, "nothing wider than the screen"
    assert not after["wash"] and after["back"] == before["back"], "the board's own look, as it was"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
