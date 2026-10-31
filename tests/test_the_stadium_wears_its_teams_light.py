"""Every game's stadium is lit in its two teams' colours (Ethan, 2026-10-28,
two Home tiles circled, Patriots @ Dolphins and Chiefs @ Broncos: "these
colors are not blending well at all and not matching the teams").

The photograph was the home kit's render, chosen by the first colour of the
home team's kit: Miami's stadium green, Denver's blue (their navy, not
their orange). The teams' own colours were a wash laid over it, so a tile
carried three colours, one of them nobody's, and went brown where they met.

What these hold:

  * a team's colour as light is its vivid colour lifted to a lightness a dark
    tile can show, in OKLab: the hue and the strength kept (a burgundy stays
    a deep red, not a fire-engine one), a bright colour left alone, a kit
    with no colour a grey that lights nothing;
  * the game card and the game page it opens are lit by both teams, the
    away side from the left and the home side from the right, and take
    their family's neutral render (the carry charts, one team's, keep the
    kit's render);
  * the light is an overlay on a grey photograph (Safari has no hue blend
    modes), the stadium its own group, a faint glow of the same colours
    under the fade, and no wash over the whole card;
  * three clubs wear their own colours again (the Jets carried the Packers'
    green; the Rams and the Commanders what they wore before 2020 and 2022);
  * in a browser, at an iPhone's width and in both themes, each side of a
    tile's stadium is its own team's hue.

Run directly: `python3 tests/test_the_stadium_wears_its_teams_light.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
DETAIL_CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
TEAMS = (ROOT / "web" / "js" / "teams.js").read_text(encoding="utf-8")
VARIANTS = ROOT / "web" / "img" / "venues" / "variants"


def _fn(src: str, head: str) -> str:
    i = src.index(head)
    return src[i:src.index("\n}\n", i) + 2]


def _rule(src: str, selector: str) -> str:
    i = src.index(selector + " {")
    return src[i:src.index("}", i) + 1]


def _oklch(hex_: str):
    """OKLab lightness, chroma and hue (degrees) of a #rrggbb."""
    lin = []
    for i in (1, 3, 5):
        c = int(hex_[i:i + 2], 16) / 255
        lin.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = lin
    lms = [0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
           0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b]
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def _apart(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _node(prog: str) -> str:
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run([shutil.which("node"), path], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_a_teams_light_is_its_colour_lifted_not_changed():
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    kits = {"PHI": ("#004953", "#a5acaf"), "BAL": ("#241773", "#000000"), "WAS": ("#5a1414", "#ffb612"),
            "NYY": ("#0c2340", "#c4ced3"), "NYJ": ("#125740", "#000000"), "DEN": ("#002244", "#fb4f14"),
            "PIT": ("#000000", "#ffb612"), "MIA": ("#008e97", "#fc4c02"), "SEA": ("#002244", "#69be28"),
            "LV": ("#000000", "#a5acaf"), "GB": ("#203731", "#ffb612"), "CHI": ("#0b162a", "#c83803"),
            "CWS": ("#27251f", "#c4ced4")}
    table = {k: {"primary": p, "secondary": s} for k, (p, s) in kits.items()}
    prog = (f"const T = {json.dumps(table)};\nconst activeTeams = () => T;\n"
            + _fn(APP, "function teamVivid(a) {") + _fn(APP, "function teamLight(a) {")
            + f"\nconsole.log(JSON.stringify(Object.fromEntries({json.dumps(list(kits) + ['XX'])}"
              ".map((k) => [k, [teamVivid(k), teamLight(k)]]))));")
    got = json.loads(_node(prog))
    assert got["XX"] == ["var(--brand)", "var(--brand)"], "a team the table does not know keeps the brand"
    for team in ("PHI", "BAL", "WAS", "NYY", "NYJ", "MIA"):
        vivid, light = got[team]
        L0, C0, H0 = _oklch(vivid)
        L1, C1, H1 = _oklch(light)
        assert L1 >= 0.59, (team, vivid, light, "bright enough to light a dark tile")
        assert _apart(H0, H1) <= 12, (team, vivid, light, "the same hue")
        # No stronger than the kit (a burgundy stays deep), past the least a
        # light needs to read as a colour at all (0.08: the Packers' sage).
        assert C1 <= max(C0 * 1.08 + 0.01, 0.085) and C1 >= 0.07, (team, vivid, light, C0, C1)
    for team in ("DEN", "PIT", "SEA"):
        vivid, light = got[team]
        assert vivid == light, (team, got[team], "a colour bright enough already is left alone")
    L, C, _ = _oklch(got["LV"][1])
    assert C < 0.02 and 0.55 < L < 0.7, (got["LV"], "black and silver light nothing: a mid grey")
    # …nor does a black a shade warm: the White Sox are not lit khaki.
    L, C, _ = _oklch(got["CWS"][1])
    assert got["CWS"][0] == "#27251f" and C < 0.02 and 0.55 < L < 0.7, (got["CWS"], C)
    # A dark green keeps itself and is lifted (the Packers were lit gold); a
    # navy still gives way to the club's bright colour (the Bears' orange).
    gb = _oklch(got["GB"][1])
    assert got["GB"][0] == "#203731" and _apart(gb[2], _oklch("#203731")[2]) <= 12 and gb[1] >= 0.07, (got["GB"], gb)
    assert got["CHI"][0] == "#c83803", got["CHI"]


def test_the_card_and_the_page_it_opens_are_lit_by_both_teams():
    card = _fn(APP, "function gameCard(g, i) {")
    assert 'style="--ta:${escapeAttr(teamLight(g.away))};--tb:${escapeAttr(teamLight(g.home))}"' in card, \
        "the away side's light from the left, the home side's from the right"
    assert "venuePhotoTag(state.sport, g.home, homeTeam, i === 0, true)" in card
    assert ('<div class="gp-hero is-hero" style="--ta:${escapeAttr(teamLight(g.away))};'
            '--tb:${escapeAttr(teamLight(g.home))}">') in DETAIL
    assert "venuePhotoTag(state.sport, g.home, (window.ACTIVE_TEAMS || {})[g.home] || {}, false, true)" in DETAIL


def test_a_lit_stadium_takes_its_familys_neutral_render():
    fam = APP[APP.index("const VENUE_FAMILY = "):]
    families = set(re.findall(r'"([a-z]+)"', fam[:fam.index("};")]))
    base = APP[APP.index("const VENUE_LIT_BASE = "):]
    base = dict(re.findall(r'([a-z]+): "([a-z]+)"', base[:base.index("};")]))
    assert set(base) == families, (base, families)
    for family, variant in base.items():
        for name in (f"{family}-{variant}.jpg", f"{family}-{variant}.webp", f"{family}-{variant}@800.webp"):
            assert (VARIANTS / name).exists(), name
    assert base["football"] == "steel", "the sharp neutral render, not a tile cut from the colour sheet"
    tag = _fn(APP, "function venuePhotoTag(sport, home, homeTeam, lead, lit) {")
    assert "${lit ? VENUE_LIT_BASE[fam] : venueVariant(homeTeam)}" in tag
    for f in ("carrychart.js", "chart-mlb.js"):
        src = (ROOT / "web" / "js" / f).read_text(encoding="utf-8")
        for call in re.findall(r"venuePhotoTag\(([^()]*(?:\([^()]*\)[^()]*)*)\)", src):
            args = re.sub(r"\([^()]*\)", "()", call).split(",")
            assert len(args) == 3, (f, call, "one team's chart keeps the kit's render")


def test_the_light_is_an_overlay_on_a_grey_photograph():
    tokens = _rule(CSS, ".game-card, .gp-hero")
    # Each half its own team's (Ethan, the same evening: "the stadium art
    # should be half each color"): the two meet in the middle fifth.
    assert "--grad-teams-light: linear-gradient(90deg, var(--ta) 40%, var(--tb) 60%);" in tokens
    assert "--grad-teams-glow: linear-gradient(90deg, color-mix(in oklab, var(--ta) 24%, transparent)" in tokens
    assert ".hero-games .stadium-wrap { isolation: isolate; }" in CSS, "the light reaches the photograph and nothing past it"
    # In a group of its own, an overlay on nothing is its colour at full
    # strength: the light draws only over a photograph, and a photograph
    # still loading is night under it (the browser check below).
    assert ".hero-games .stadium-wrap .venue-photo { filter: var(--venue-grade-lit); background-color: var(--night); }" in CSS
    light = _rule(CSS, ".hero-games .stadium-wrap:has(.venue-photo)::before")
    assert "mix-blend-mode: overlay;" in light and "background-image: var(--grad-teams-light);" in light, light
    grades = re.findall(r"--venue-grade-lit: ([^;]+);", CSS)
    assert len(grades) == 2 and all(g.startswith("grayscale(1) ") for g in grades), \
        ("both themes grey the photograph, so the only colours on it are the teams'", grades)
    assert "background: var(--grad-tile-fade), var(--grad-teams-glow);" in _rule(CSS, ".hero-games .stadium-wrap::after")
    for src in (CSS, DETAIL_CSS):
        assert not re.search(r"mix-blend-mode: *(hue|saturation|color|luminosity)\b", src), \
            "Safari has no non-separable blend modes: the light would paint as a solid colour"
    assert ".game-card::after" not in CSS and "--grad-teams-wash" not in CSS, "no wash over the whole card"
    # The game page: the same light, under its own fade.
    assert ".gp-hero.is-hero .gp-art { isolation: isolate; }" in DETAIL_CSS
    assert ".gp-hero.is-hero .gp-art .venue-photo { filter: var(--venue-grade-lit); background-color: var(--night); }" in DETAIL_CSS
    gp = _rule(DETAIL_CSS, ".gp-hero.is-hero .gp-art:has(.venue-photo)::before")
    assert "z-index: 2;" in gp and "background-image: var(--grad-teams-light);" in gp and "mix-blend-mode: overlay;" in gp
    fade = _rule(DETAIL_CSS, ".gp-hero.is-hero .gp-art::after")
    assert "z-index: 2;" in fade and "background: var(--grad-gp-fade), var(--grad-teams-glow);" in fade, \
        "the fade is drawn after the light, so it covers it"


def test_three_clubs_wear_their_own_colours_again():
    def kit(key):
        m = re.search(r'  "%s": \{[^}]*"primary": "([^"]*)",\s*"secondary": "([^"]*)"' % key, TEAMS)
        return m.groups()
    assert kit("NYJ") == ("#125740", "#000000"), "the Jets' green, not the Packers'"
    assert kit("NYJ")[0] != kit("GB")[0]
    assert kit("LA") == kit("LAR") == ("#003594", "#ffa300"), "the Rams' royal and sol since 2020"
    assert kit("WAS")[0] == "#5a1414", "the Commanders' burgundy since 2022"


def _board():
    def game(i, away, home):
        return {"home": home, "away": away, "date": f"2099-01-0{i}", "kickoff": "16:25", "spread": -3.5, "favorite": home,
                "total": 44.5, "home_ml": -180, "away_ml": 160, "weather_checked": True,
                "weather": {"temp_f": 62, "wind_mph": 4, "wind_dir": "N", "measured": True}}
    return {"sport": "nfl", "date": "2099-W01", "recommendations": [], "most_likely": [],
            "games": [game(1, "NE", "MIA"), game(2, "KC", "DEN")], "player_stats": {}}


def _hue(pixels) -> float:
    """The chroma-weighted mean hue of some pixels, in degrees."""
    x = y = 0.0
    for r, g, b in pixels:
        mx, mn = max(r, g, b), min(r, g, b)
        c = mx - mn
        if c < 12:
            continue
        if mx == r:
            h = ((g - b) / c) % 6
        elif mx == g:
            h = (b - r) / c + 2
        else:
            h = (r - g) / c + 4
        x += c * math.cos(math.radians(h * 60))
        y += c * math.sin(math.radians(h * 60))
    return math.degrees(math.atan2(y, x)) % 360


def _srgb_hue(hex_: str) -> float:
    return _hue([tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5))])


def test_in_a_browser_each_side_of_the_stadium_is_its_own_teams_hue():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError:
        print("      (skipped: no Playwright or no Pillow)")
        return
    import rendercheck
    body = json.dumps(_board())
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
                    errs = []
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                         f" localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', '{theme}'); }} catch (e) {{}}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                    page.wait_for_function("() => document.querySelectorAll('#games .game-card').length === 2", timeout=20000)
                    # The chips off, so what is measured is the stadium and its light.
                    page.add_style_tag(content=".stadium-wrap .game-time-chip, .stadium-wrap .game-wx-chip, .stadium-wrap .gc-picks,"
                                               " .stadium-wrap .top-game-tag, .stadium-wrap .fav-tag { visibility: hidden !important; }")
                    page.evaluate("""() => { const c = document.querySelector('#games .game-card');
                      window.scrollTo(0, window.scrollY + c.getBoundingClientRect().top - 140); }""")
                    for i in range(2):
                        page.evaluate(f"""() => {{ const s = document.querySelector('#games');
                          s.scrollLeft = s.querySelectorAll('.game-card')[{i}].offsetLeft - 12; }}""")
                        page.wait_for_function(f"""() => {{ const im = document.querySelectorAll('#games .game-card')[{i}].querySelector('.venue-photo');
                          return im && im.complete && im.naturalWidth > 0; }}""", timeout=20000)
                        page.wait_for_timeout(200)
                        card = page.locator("#games .game-card").nth(i)
                        # A BUSY MACHINE PAINTS THE LIGHT LATE (2026-10-28: the full browser
                        # run read the Dolphins' side grey once, and alone it passed four
                        # times in four). The photograph is in, but the overlay over it can
                        # land a frame or two after: the sides are read again, a few times,
                        # until each wears its team's hue. A wrong colour still fails; it is
                        # only no longer judged before it has painted.
                        ta, tb = re.search(r"--ta: ?(#[0-9a-f]{6}); ?--tb: ?(#[0-9a-f]{6})",
                                           card.get_attribute("style")).groups()
                        for _ in range(5):
                            band = card.locator(".stadium-wrap").bounding_box()
                            box = card.bounding_box()
                            shot = Image.open(io.BytesIO(card.screenshot())).convert("RGB")
                            k = shot.size[0] / box["width"]
                            top, bottom = int((band["y"] - box["y"]) * k), int((band["y"] - box["y"] + band["height"]) * k)
                            w = shot.size[0]
                            pix = shot.load()
                            side = lambda x0, x1: [pix[x, y] for y in range(top + 4, bottom) for x in range(x0, x1)]  # noqa: E731
                            left, right = _hue(side(int(w * .04), int(w * .3))), _hue(side(int(w * .7), int(w * .96)))
                            if _apart(left, _srgb_hue(ta)) <= 30 and _apart(right, _srgb_hue(tb)) <= 30:
                                break
                            page.wait_for_timeout(300)
                        found[(theme, i)] = {
                            "left": left, "right": right,
                            "style": card.get_attribute("style"),
                            "src": card.locator(".venue-photo").get_attribute("src"),
                            "filter": card.locator(".venue-photo").evaluate("(e) => getComputedStyle(e).filter"),
                            "blend": card.locator(".stadium-wrap").evaluate("(e) => getComputedStyle(e, '::before').mixBlendMode"),
                        }
                    found[(theme, "errs")] = errs
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for theme in ("dark", "light"):
        assert not found[(theme, "errs")], found[(theme, "errs")]
        for i, (away, home) in enumerate((("NE", "MIA"), ("KC", "DEN"))):
            f = found[(theme, i)]
            ta, tb = re.search(r"--ta: ?(#[0-9a-f]{6}); ?--tb: ?(#[0-9a-f]{6})", f["style"]).groups()
            assert "football-steel" in f["src"], (theme, away, home, f["src"], "the neutral render, not the home kit's")
            assert f["filter"].startswith("grayscale(1)") and f["blend"] == "overlay", (theme, f)
            assert _apart(f["left"], _srgb_hue(ta)) <= 30, (theme, away, "the away side's light on the left", f["left"], ta)
            assert _apart(f["right"], _srgb_hue(tb)) <= 30, (theme, home, "the home side's light on the right", f["right"], tb)
        f = found[(theme, 0)]
        assert _apart(f["left"], f["right"]) >= 90, (theme, "the Patriots' red and the Dolphins' aqua, two colours", f)


def test_in_a_browser_a_stadium_still_loading_is_night_not_a_block_of_colour():
    """The light is an overlay in a group of its own, and an overlay on
    nothing is its own colour at full strength: before the :has gate and
    the night under the photograph, a tile whose photograph had not
    arrived was two solid slabs of the teams' colours. A transparent frame
    stands in for the photograph still on its way: an element with nothing
    painted in it yet."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError:
        print("      (skipped: no Playwright or no Pillow)")
        return
    import rendercheck
    body = json.dumps(_board())
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                          has_touch=True, service_workers="block", color_scheme="dark")
                page = ctx.new_page()
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', 'dark'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_function("() => document.querySelector('#games .game-card .venue-photo')", timeout=20000)
                page.evaluate("""() => new Promise((done) => {
                  const im = document.querySelector('#games .game-card .venue-photo');
                  im.removeAttribute('data-alt');
                  im.addEventListener('load', () => done(), { once: true });
                  im.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
                })""")
                page.add_style_tag(content=".stadium-wrap .game-time-chip, .stadium-wrap .game-wx-chip, .stadium-wrap .gc-picks,"
                                           " .stadium-wrap .top-game-tag, .stadium-wrap .fav-tag { visibility: hidden !important; }")
                page.evaluate("""() => { const c = document.querySelector('#games .game-card');
                  window.scrollTo(0, window.scrollY + c.getBoundingClientRect().top - 140); }""")
                page.wait_for_timeout(500)
                card = page.locator("#games .game-card").first
                got["empty"] = card.locator(".venue-photo").evaluate("(e) => e.naturalWidth === 1")
                got["night"] = card.locator(".venue-photo").evaluate("(e) => getComputedStyle(e).backgroundColor")
                band, box = card.locator(".stadium-wrap").bounding_box(), card.bounding_box()
                shot = Image.open(io.BytesIO(card.screenshot())).convert("RGB")
                k = shot.size[0] / box["width"]
                pix = shot.load()
                px = [pix[x, y] for y in range(int((band["y"] - box["y"]) * k) + 4, int((band["y"] - box["y"] + band["height"]) * k))
                      for x in range(int(shot.size[0] * .04), int(shot.size[0] * .96))]
                got["brightest"] = sorted(max(p) for p in px)[int(len(px) * .95)]
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["empty"], "the photograph was meant to have nothing in it yet"
    assert got["night"] == "rgb(7, 11, 22)", got
    assert got["brightest"] < 110, ("a tile still loading is dark, not two slabs of colour", got)


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
