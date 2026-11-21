"""A team's page wears its club's colours, and every change of the screen's
colours fades (TEAMWASH1, WASHFADE1).

Ethan, 2026-11-17: "team pages should wear their club's colors", and then:
"make transitions smooth. Like when the colors switch from somebody's
personal team colors they have set from the website to when they go to a
team page and it switches to the team's colors, make that transition smooth
and not some like quick, like glitchy switch". What these hold:

  * while a team's page is open it names its club (app.js pageClubOn) and
    the whole screen sits on that club's two colours: over your own colours
    if you wear some, and with the setting off too; the pair is the club's
    real colours (clubWash: a kit's white or silver trim steps aside), the
    one a player's page wears; a club in black alone keeps the site's light;
  * leaving the page gives the screen back (the router names no club),
    and one club's page goes straight to the next club's;
  * every change of what the layer under the pages, the bar or the strip
    under the clock paints is cross-faded: a copy of the old look laid over
    the new and faded out by opacity alone; never for a reader who asked for
    less motion;
  * in a browser: your colours fade to the club's on its page and back, the
    site's gold does the same with the setting off, and nothing is left on
    the screen afterwards.

    python3 tests/test_a_team_page_wears_its_club_and_the_colours_fade.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text(encoding="utf-8")
MORE = (WEB / "js" / "more.js").read_text(encoding="utf-8")
FADE = (WEB / "js" / "washfade.js").read_text(encoding="utf-8")
PLAYER = (WEB / "js" / "playerpage.js").read_text(encoding="utf-8")
CSS = (WEB / "css" / "washfade.css").read_text(encoding="utf-8")
MORE_CSS = (WEB / "css" / "more.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _line(src, start):
    at = src.index(start)
    return src[at:src.index("\n", at) + 1]


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", body], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


HELPERS = ("".join(_fn(APP, n) for n in ("teamColorsWho", "pageClubOn", "pairWash", "applyTeamColors", "okLab", "okRgb",
                                         "twWash", "clubWash", "twSwatch", "twPin"))
           + "".join(_line(APP, s) for s in ("const rgbHex = ", "const TW_DEEP_L", "const twHex6 = ", "const TW_SWATCH_KEY",
                                             "let _pageClub = "))
           + "let _twPinRO = null;\n")
TABLES = {"nfl": {"DET": {"primary": "#005a8b", "secondary": "#b0b7bc", "tertiary": "#000000"},
                  "PIT": {"primary": "#000000", "secondary": "#ffb612", "tertiary": "#c60c30"},
                  "LV": {"primary": "#000000"}},
          "nhl": {"TOR": {"primary": "#00205b", "secondary": "#ffffff"}}}


def _run(settings, steps, tables=None):
    """applyTeamColors after each step (a line of JS): the classes and properties then."""
    js = """
const classes = {}, props = {}, store = {}; let barX = null;
global.localStorage = { getItem: (k) => store[k] == null ? null : store[k], setItem: (k, v) => { store[k] = String(v); } };
const bar = { getBoundingClientRect: () => ({ left: 0, width: 390 }), style: { setProperty: (k, v) => { barX = v; } } };
global.document = { querySelector: (q) => q === ".topbar" ? bar : null,
  documentElement: { classList: { toggle: (c, on) => { classes[c] = !!on; }, contains: (c) => !!classes[c] },
                     style: { setProperty: (k, v) => { props[k] = v; } } } };
global.window = { addEventListener: () => {} };
const S = %s; const settings = () => S; const state = { sport: "nfl" };
const TABLES = %s;
const teamsForSport = (s) => TABLES[s] || {};
%s
const out = [];
for (const step of %s) { eval(step); out.push({ classes: { ...classes }, props: { ...props } }); }
console.log(JSON.stringify(out));
""" % (json.dumps(settings), json.dumps(tables or TABLES), HELPERS, json.dumps(steps))
    return _node(js)


def test_a_teams_page_wears_its_club_over_your_colours_and_with_the_setting_off():
    mine = {"teamColors": "site", "teams": ["nfl:DET"]}
    home, steelers, leafs, back = _run(mine, ["applyTeamColors()", "pageClubOn('nfl:PIT')", "pageClubOn('nhl:TOR')",
                                              "pageClubOn('')"])
    assert home["classes"] == {"team-wash": True, "club-page": False, "team-tint": True}
    assert home["props"]["--tw-1"] == "#005a8b"
    # The Steelers' page: their gold and black, over the Lions' blue, and the bar's tint theirs too.
    assert steelers["classes"] == {"team-wash": True, "club-page": True, "team-tint": True}
    assert steelers["props"]["--tw-1"] == "#a56400" and steelers["props"]["--team-1"] == "#000000"
    # Straight on to the Leafs' page: blue, and a deeper blue where the white of the kit would turn fog grey.
    assert leafs["classes"]["club-page"] and leafs["props"]["--tw-1"] == "#00205b"
    assert leafs["props"]["--tw-2"] != "#ffffff" and leafs["props"]["--tw-2-paper"] != "#ffffff", leafs["props"]
    # Left: your own colours again.
    assert back["classes"] == {"team-wash": True, "club-page": False, "team-tint": True}
    assert back["props"]["--tw-1"] == "#005a8b" and back["props"]["--team-1"] == "#005a8b"
    off = {"teamColors": "off", "teams": []}
    plain, on, gone, raiders = _run(off, ["applyTeamColors()", "pageClubOn('nfl:DET')", "pageClubOn('')",
                                          "pageClubOn('nfl:LV')"])
    assert plain["classes"] == {"team-wash": False, "club-page": False, "team-tint": False}
    assert on["classes"] == {"team-wash": True, "club-page": True, "team-tint": True}, "with the setting off too"
    assert gone["classes"] == {"team-wash": False, "club-page": False, "team-tint": False}
    # Black alone has no colour to wash with: the site's light, and the bar's tint.
    assert raiders["classes"] == {"team-wash": False, "club-page": False, "team-tint": True}


def test_a_club_never_seen_names_nothing_and_the_same_club_is_not_applied_twice():
    odd, = _run({"teamColors": "off", "teams": []}, ["pageClubOn('nfl:NOPE')"])
    assert odd["classes"] == {"team-wash": False, "club-page": False, "team-tint": False}
    assert "if (key === _pageClub) return;" in _fn(APP, "pageClubOn")


def test_the_page_names_its_club_once_drawn_and_the_router_hands_the_screen_back():
    draw = _fn(MORE, "renderTeamPage")
    assert 'if (state.view === "team") pageClubOn(`${d.sport}:${p.team}`);' in draw
    assert draw.index("host.innerHTML = `") < draw.index("pageClubOn("), "once the page is drawn"
    sw = _fn(APP, "_switchViewNow")
    assert 'if (name !== "team" && name !== "game") pageClubOn("");' in sw, "a game's page names its two (GAMEWASH1)"
    # One pair for every page that is one club's: the player's page asks the same function.
    assert "function plrWashPair(t) { return clubWash(t); }" in PLAYER
    assert "html.club-page:not([data-theme=\"light\"]) .tm-head.tm-band { background: none;" in MORE_CSS


def test_every_change_of_the_colours_is_cross_faded_by_opacity_alone():
    fade = _fn(FADE, "wfFade")
    assert 'el.style.transition = `opacity ${WF_MS}ms ease`; el.style.opacity = "0";' in fade
    assert "transform" not in fade and "filter" not in fade, "opacity alone: the compositor's work"
    watch = _fn(FADE, "wfWatch")
    assert 'attributeFilter: ["class", "style", "data-theme"]' in watch
    assert '[document.documentElement, document.body, document.getElementById("view-pbp")]' in watch
    assert "requestAnimationFrame(wfCheck)" in watch, "read once a frame at most, before the frame is painted"
    assert "if (_wfLook && !wfStill()) wfFade(_wfLook, now);" in _fn(FADE, "wfCheck")
    still = FADE[FADE.index("const wfStill = "):FADE.index("//: The copy of one surface")]
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)").matches' in still and "visibilityState" in still
    assert "const WF_MS = 420;" in FADE and FADE.rstrip().endswith("wfWatch();"), "the room starts its own watch"
    for rule in (".wf-copy { position: fixed; inset: 0; z-index: -1; pointer-events: none;",
                 ".wf-copy[hidden] { display: none; }", ".wf-copy.wf-bar { position: absolute; }",
                 "@media (prefers-reduced-motion: reduce) { .wf-copy { display: none; } }"):
        assert rule in CSS, rule


def test_no_first_visit_waits_on_it_and_no_rooms_class_is_named_outside_its_room():
    """Fetched once the page has loaded (the first paint's byte budget is not spent on it), cached with
    the installed app's other pages, and trimmed like them; and it finds a game page's own wash by a
    mark the game page puts on it (data-wash), never by that room's class names."""
    assert 'window.addEventListener("load", () => setTimeout(() => window.QB_STALE || loadRoom("js/washfade.js", "css/washfade.css"), 900));' in APP
    assert "function wfFade(" not in APP and "function wfWatch(" not in APP
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    lazy = sw[sw.index("const LAZY = ["):sw.index("];", sw.index("const LAZY = ["))]
    assert '"/js/washfade.js"' in lazy and '"/css/washfade.css"' in lazy
    assert '"js/washfade.js", "css/washfade.css"' in (ROOT / "engine" / "shrink.py").read_text(encoding="utf-8")
    assert "gp-on" not in FADE and "gp-wash" not in FADE and "plr-on" not in FADE
    assert 'document.querySelector("[data-wash]")' in _fn(FADE, "wfBackdrop")
    assert '<div class="gp-wash" data-wash aria-hidden="true"></div>' in (WEB / "js" / "detail.js").read_text(encoding="utf-8")


def _browser(reduced=False):
    from playwright.sync_api import sync_playwright
    import rendercheck
    games = [{"home": "DET", "away": "GB", "date": "2099-01-01", "kickoff": "13:00", "spread": -3.5, "favorite": "DET",
              "total": 48.5, "home_ml": -180, "away_ml": 155}]
    body = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2099-01-01", "recommendations": [],
                       "most_likely": [], "games": games, "player_stats": {}})

    def team(route):
        abbr = "GB" if "team=GB" in route.request.url else "PIT"
        name = {"GB": "Green Bay Packers", "PIT": "Pittsburgh Steelers"}[abbr]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"sport": "nfl", "profile": {"team": abbr, "name": name, "seasons": [{"season": 2026, "record": "6-4"}]},
             "squad": []}))
    sampler = """(go) => new Promise((res) => { const out = [], t0 = performance.now();
        (0, eval)(go);
        const tick = () => { const c = document.querySelector('.wf-copy.wf-back'), b = document.querySelector('.wf-copy.wf-bar');
          out.push([c && !c.hidden ? +getComputedStyle(c).opacity : null, b && !b.hidden ? +getComputedStyle(b).opacity : null,
                    c ? c.style.backgroundImage : '']);
          if (performance.now() - t0 < 1500) requestAnimationFrame(tick); else res(out); };
        requestAnimationFrame(tick); })"""
    srv, port = rendercheck._serve()
    found = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for mode in ("site", "off"):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block", color_scheme="dark", bypass_csp=True,
                                              reduced_motion="reduce" if reduced else "no-preference")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                         " localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', 'dark');"
                                         " localStorage.setItem('qb_settings_v1', JSON.stringify({ teamColors: '%s', teams: ['nfl:DET'] }));"
                                         " } catch (e) {}" % mode)
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    page.route("**/api/team?*", team)
                    for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    for _ in range(60):                       # the watcher starts once the app has drawn itself
                        if page.evaluate("typeof _wfLook !== 'undefined' && !!_wfLook"):
                            break
                        page.wait_for_timeout(100)
                    css = "getComputedStyle(document.querySelector('.ambient')).backgroundImage"
                    before = page.evaluate(css)
                    to_club = page.evaluate(sampler, "openTeam('nfl', 'PIT')")
                    on = page.evaluate("""() => ({ club: document.documentElement.classList.contains('club-page'),
                        tw1: document.documentElement.style.getPropertyValue('--tw-1'),
                        head: getComputedStyle(document.querySelector('.tm-head')).backgroundImage,
                        left: [...document.querySelectorAll('.wf-copy')].filter((c) => !c.hidden).length,
                        wide: document.documentElement.scrollWidth - innerWidth })""")
                    during = page.evaluate(css)
                    to_next = page.evaluate(sampler, "openTeam('nfl', 'GB')")
                    nxt = page.evaluate("document.documentElement.style.getPropertyValue('--tw-1')")
                    to_home = page.evaluate(sampler, "switchView('recommended')")
                    after = page.evaluate(css)
                    off = page.evaluate("document.documentElement.classList.contains('club-page')")
                    found[mode] = {"before": before, "during": during, "after": after, "on": on, "next": nxt, "off": off,
                                   "to_club": to_club, "to_next": to_next, "to_home": to_home, "errors": errors}
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return found


def _faded(samples):
    """Did the copy of the layer under the pages show, part-faded, and go?"""
    back = [s[0] for s in samples if s[0] is not None]
    return bool(back) and any(0.03 < v < 0.97 for v in back) and (samples[-1][0] in (None, 0))


def test_in_a_browser_your_colours_fade_to_the_clubs_on_its_page_and_back():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got = _browser()
    for mode, f in got.items():
        assert not f["errors"], (mode, f["errors"][:2])
        assert f["on"]["club"] and f["on"]["tw1"] == "#a56400", (mode, f["on"])
        assert f["on"]["head"] == "none", "at night the header lies on the colours themselves"
        assert f["on"]["left"] == 0 and f["on"]["wide"] <= 0, (mode, f["on"])
        assert f["before"] != f["during"] and f["after"] == f["before"], (mode, "the screen is handed back as it was")
        assert not f["off"] and f["next"] not in ("", "#a56400"), (mode, f["next"])
        for leg in ("to_club", "to_next", "to_home"):
            assert _faded(f[leg]), (mode, leg, [s[:2] for s in f[leg]][:40])
        # The copy laid over the club's page is the look before it: your Lions' blue, or the site's gold light.
        first = next(s[2] for s in f["to_club"] if s[0] is not None)
        assert ("linear-gradient(100deg" in first) == (mode == "site"), (mode, first[:120])
        assert any(s[1] is not None for s in f["to_club"]), "the bar fades with it"
    assert "linear-gradient(100deg" in got["site"]["before"] and "radial-gradient" in got["off"]["before"]


def test_in_a_browser_nothing_fades_for_a_reader_who_asked_for_less_motion():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got = _browser(reduced=True)
    for mode, f in got.items():
        assert not f["errors"], (mode, f["errors"][:2])
        assert f["on"]["club"] and f["on"]["tw1"] == "#a56400", "the colours still change"
        for leg in ("to_club", "to_next", "to_home"):
            assert all(s[0] is None and s[1] is None for s in f[leg]), (mode, leg, "no copy is ever shown")


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
