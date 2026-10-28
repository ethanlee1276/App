"""The iPhone app's tab bar floats, the riding tray is a pill, your team's colours.

Ethan, 2026-10-24: "build everything ... including all the ideas" — the Look
items of docs/IDEAS.md (styles.css "THE iPHONE APP'S GLASS, THE RIDING PILL,
YOUR TEAM'S COLOURS"):

  - the iOS build and an iPhone Home Screen app float the tab bar as a glass
    capsule above the home indicator, as iOS 26's own apps do; a browser tab
    and the Play build keep the full-width bar, and the page keeps room for
    the capsule (and for the pill above it);
  - the More and Bet sheets are glass panes on touch screens;
  - the riding tray is a centred dark pill whatever the theme, its live dot
    breathing only for readers who allow motion;
  - with the Team colours setting on, the bar's edge, the Live disc and the
    lit tab wear the colours of the team you follow in this league (else the
    first one you follow); off, or nobody followed, the site's own gold.

Run directly: `python3 tests/test_the_iphone_app_wears_its_own_glass.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import re
import subprocess
import sys
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
CSS, APP, BOOT = READ("web", "css", "styles.css"), app_js(), READ("web", "js", "boot.js")
LOOK = CSS[CSS.index("THE iPHONE APP'S GLASS, THE RIDING PILL"):]
SHOTS = os.environ.get("QB_SHOTS_DIR", "")


def test_only_the_iphone_app_floats_the_bar():
    assert 'if (navigator.standalone === true) document.documentElement.classList.add("ios-home");' in BOOT
    at = LOOK.index("html.store-ios .tabbar, html.ios-home .tabbar {")
    assert LOOK.rfind("@media (max-width: 760px) {", 0, at) > -1
    rule = LOOK[at:LOOK.index("}", at)]
    assert "border-radius: 999px" in rule and "env(safe-area-inset-bottom)" in rule and "var(--glass-rim)" in rule
    assert "html.store-ios body.has-tray, html.ios-home body.has-tray" in LOOK, "room for the pill above the capsule"
    assert "backdrop-filter" not in LOOK and "blur(" not in LOOK, "the glass is light, never blur (it resprung Ethan's iPhone)"


def test_the_pill_breathes_only_for_readers_who_allow_motion():
    at = LOOK.index(".rt-dot { animation: rt-breathe")
    assert LOOK.rfind("prefers-reduced-motion: no-preference", 0, at) > LOOK.rfind("}\n}", 0, at)
    assert "@keyframes rt-breathe" in LOOK


def test_team_colours_are_a_setting_off_by_default_and_tokens_until_set():
    assert 'teamColors: "off",' in APP
    # A switch in the settings list since 2026-10-25 (account.js setListHTML).
    assert 'end: setSwitch(s.teamColors === "on", `data-set-switch="teamColors"' in APP
    at = APP.index("function applySport() {")
    assert "applyTeamColors();" in APP[at:at + 400]
    root = CSS[CSS.index(":root {"):CSS.index("}", CSS.index(":root {"))]
    assert "--team-1: var(--brand);" in root and "--team-2: var(--brand-2);" in root
    assert "--grad-team: linear-gradient(90deg, var(--team-1), var(--team-2));" in root
    for sel in (".team-tint .topbar::after", ".team-tint .tb-center-disc", ".team-tint .tb-item.active"):
        assert sel in LOOK, sel


def _tint(settings, sport):
    at = APP.index("function applyTeamColors() {")
    fn = APP[at:APP.index("\n}\n", at) + 2]
    js = """
const props = {}; let cls = false;
global.document = { documentElement: { classList: { toggle: (c, on) => { cls = on; } },
  style: { setProperty: (k, v) => { props[k] = v; } } } };
const S = %s; const settings = () => S; const state = { sport: %s };
const TEAMS = { DET: { primary: "#005a8b", secondary: "#b0b7bc" } };
const NBA_TEAMS = { BOS: { primary: "#007a33" } };
const teamsForSport = (s) => s === "nba" ? NBA_TEAMS : s === "nfl" ? TEAMS : {};
%s
applyTeamColors();
console.log(JSON.stringify({ cls, props }));
""" % (json.dumps(settings), json.dumps(sport), fn)
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_colours_are_the_team_you_follow_in_this_league():
    both = ["nba:BOS", "nfl:DET"]
    assert _tint({"teamColors": "on", "teams": both}, "nfl") == \
        {"cls": True, "props": {"--team-1": "#005a8b", "--team-2": "#b0b7bc"}}
    assert _tint({"teamColors": "on", "teams": both}, "nba")["props"] == {"--team-1": "#007a33", "--team-2": "#007a33"}
    assert _tint({"teamColors": "on", "teams": both}, "nhl")["props"]["--team-1"] == "#007a33", "else the first you follow"
    assert _tint({"teamColors": "off", "teams": both}, "nfl") == {"cls": False, "props": {}}
    assert _tint({"teamColors": "on", "teams": []}, "nfl") == {"cls": False, "props": {}}


def test_in_a_browser_the_ios_app_floats_a_capsule_a_tab_does_not_and_the_team_tints():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    got = {}
    measure = """() => { const bar = document.querySelector('.tabbar'), r = bar.getBoundingClientRect(), s = getComputedStyle(bar);
        const disc = getComputedStyle(document.querySelector('.tb-center-disc'));
        const edge = getComputedStyle(document.querySelector('.topbar'), '::after');
        const probe = document.createElement('i');
        probe.style.color = 'color-mix(in oklab, var(--team-1) 12%, transparent)';
        document.querySelector('.topbar').appendChild(probe);
        const spill = getComputedStyle(probe).color; probe.remove();
        renderRidingTray([{ player: "Amon-Ra St. Brown", line: 5.5, current: 3, market: "receptions" }]);
        const tray = document.getElementById('riding-tray'), t = tray.getBoundingClientRect();
        return { radius: parseFloat(s.borderTopLeftRadius), left: r.left, right: innerWidth - r.right, gap: innerHeight - r.bottom,
                 tint: document.documentElement.classList.contains('team-tint'),
                 team: getComputedStyle(document.documentElement).getPropertyValue('--team-1').trim(),
                 disc: disc.backgroundImage, edge: edge.backgroundImage, spill,
                 tray: { hidden: tray.hidden, mid: t.left + t.width / 2, width: t.width, above: r.top - t.bottom,
                         bg: getComputedStyle(tray).backgroundColor },
                 pad: parseFloat(getComputedStyle(document.body).paddingBottom), vw: innerWidth }; }"""
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for name, query, theme in (("ios", "?app=ios", "dark"), ("ios light", "?app=ios", "light"), ("tab", "", "dark")):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              device_scale_factor=2, service_workers="block")
                    page = ctx.new_page()
                    page.add_init_script("""try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');
                        localStorage.setItem('qb_settings_v1', JSON.stringify({ teamColors: 'on', teams: ['nfl:DET'] }));
                        localStorage.setItem('qb.sport', 'nfl'); } catch (e) {}""")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.goto(f"http://127.0.0.1:{port}/index.html{query}#recommended", wait_until="load")
                    page.wait_for_timeout(1200)
                    if theme == "light":
                        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
                    got[name] = page.evaluate(measure)
                    if SHOTS:
                        page.wait_for_timeout(300)
                        page.screenshot(path=os.path.join(SHOTS, f"iphone_glass_{name.replace(' ', '_')}.png"))
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    ios, light, tab = got["ios"], got["ios light"], got["tab"]
    assert ios["radius"] > 30 and 8 <= ios["left"] <= 16 and 8 <= ios["right"] <= 16 and ios["gap"] >= 8, ios
    assert tab["radius"] == 0 and tab["left"] == 0 and tab["gap"] == 0, ("a browser tab keeps the full bar", tab)
    assert ios["tint"] and ios["team"] == "#005a8b", ios
    assert "rgb(0, 90, 139)" in ios["disc"], ios
    # The bar's edge wears the team's colour as light spilling down from it
    # since "No hard lines" (2026-10-27), not a 2px stripe; since 2026-10-28
    # the bar wears it too, 12% of it, and the spill runs on from there.
    assert ios["edge"].startswith("linear-gradient(") and ios["spill"] in ios["edge"], ios
    for g in (ios, light, tab):
        tr = g["tray"]
        assert not tr["hidden"] and abs(tr["mid"] - g["vw"] / 2) < 1.5 and tr["width"] <= g["vw"] - 32 + 0.5, tr
    assert ios["tray"]["above"] > 0, ("the pill floats above the capsule", ios["tray"])
    for g in (ios, light):
        bg = g["tray"]["bg"]           # color-mix() computes to oklab(L a b), else rgb()
        first = float(re.findall(r"[\d.]+", bg)[0])
        assert (first < 0.25) if bg.startswith("oklab(") else (first < 40), ("dark glass in both themes", bg)
    assert ios["pad"] >= 150, "the page keeps room for the capsule and the pill"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
