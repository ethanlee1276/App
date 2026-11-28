"""The playoff race drawn as a bracket (BRACKET1).

Ethan, 2026-11-17, over a screenshot of the NFL's seed lists: "the playoff
page should be layed out as a bracket and not this chart". The NFL's "If the
season ended today" and college football's "If it started today" are drawn
as brackets (js/race.js rcBkRoundsHTML, css/race.css): the rounds left to
right, each game level with the middle of the two that feed it, thin lines
between; the NFL's AFC on the left, the Super Bowl between, the NFC mirrored
on the right where there is room, one above the other on a phone, each
swiping sideways rather than squeezing its rounds.

Guarded here: who meets whom (the NFL's 1 seed's bye, 4 v 5, 3 v 6, 2 v 7;
college's 8/9 to the 1 seed, 5/12 to the 4, 7/10 to the 2, 6/11 to the 3,
the 1 and 4 sides meeting in one semifinal); that the later rounds say who
meets whom in words, never a guessed winner; that a reader without a plan
sees the same bracket; that the NFC turns right to left only where the
whole bracket fits (a right-to-left bracket in a narrow box overflows to the
side no one can scroll to); and, in a browser, that each game sits level
with the middle of its two feeders, the page never scrolls sideways at a
phone's width, and every round can be swiped to.

    python3 tests/test_the_playoff_race_is_drawn_as_a_bracket.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_playoff_race_is_drawn_as_a_bracket.py
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import gate                                       # noqa: E402


class _Races:
    """The race pages' own fixtures and node render (tests/test_the_race_pages.py), loaded when first
    used: a sibling test module is not imported at module scope (test_doctor)."""
    def __getattr__(self, name):
        import test_the_race_pages
        return getattr(test_the_race_pages, name)


T = _Races()

CSS = (ROOT / "web" / "css" / "race.css").read_text()
RACE = (ROOT / "web" / "js" / "race.js").read_text()


#: Which side of the bracket each conference is drawn on (left, right; the title game in the centre).
SIDE = {"AFC": "l", "NFC": "r"}


def _section(html, cls):
    i = html.index(f'<section class="{cls}')
    return html[i:html.index("</section>", i)]


def _seeds(part):
    return [int(x) for x in re.findall(r'<span class="rc-bk-seed">(\d+)</span>', part)]


def _marks(part):
    return re.findall(r'data-mark="([^"]+)"', part)


def test_the_nfl_bracket_pairs_the_seeds_the_way_the_playoffs_do():
    d = T._nfl()
    html = T._render("nflHTML", d)
    for conf in ("AFC", "NFC"):
        part = _section(html, f"rc-bk-conf rc-bk-{SIDE[conf]}")
        # The Wild Card column: the 1 seed beside its bye, then 4 v 5, 3 v 6, 2 v 7; then the 1 seed at home.
        assert _seeds(part) == [1, 4, 5, 3, 6, 2, 7, 1], (conf, _seeds(part))
        by = {s["seed"]: s["team"] for s in d["today"][conf]["seeds"]}
        assert _marks(part) == [by[n] for n in (1, 4, 5, 3, 6, 2, 7, 1)], conf
        assert "Bye" in part and "Lowest seed left" in part and "Wild Card winner" in part
        assert f"{conf} title game" in part and "Divisional winner" in part
        assert ("rc-bk-mirror" in part) == (conf == "NFC"), conf
    sb = _section(html, 'rc-bk-c"')
    assert "AFC champion" in sb and "NFC champion" in sb
    assert html.index('class="rc-bk-conf rc-bk-l"') < html.index('class="rc-bk-c"') < html.index('class="rc-bk-conf rc-bk-r"')
    assert "The divisional round is reseeded" in html
    assert "Just outside in the AFC:" in html and "back of the 7 seed" in html


def test_the_reasons_ride_with_each_seed_and_a_free_reader_sees_the_same_bracket():
    d = T._nfl()
    html = T._render("nflHTML", d)
    one = d["today"]["AFC"]["seeds"][0]
    assert f"{one['record']} · {one['why'].replace('AFC ', '')}" in html
    assert "AFC North leader" not in html, "the conference is the bracket's own heading"
    pub = T._render("nflHTML", gate.redact(d, "nfl_race.json"))
    a, b = (_section(x, "rc-bk-conf rc-bk-l") for x in (html, pub))
    assert a == b, "the bracket is the standings' fact: a member and a reader without a plan see the same one"


def test_the_college_bracket_feeds_each_bye_seed_its_own_first_round_game():
    cfp, _ = T._fixtures()
    html = T._render("cfpHTML", cfp)
    part = _section(html, "rc-bk-conf")
    # First round in the order its winners meet the bye seeds (1, 4, then 2, 3), the better seed first;
    # then the bye seeds themselves.
    assert _seeds(part) == [8, 9, 5, 12, 7, 10, 6, 11, 1, 4, 2, 3], _seeds(part)
    by = {s["seed"]: s["team"] for s in cfp["today"]["seeds"]}
    assert _marks(part) == [by[n] for n in (8, 9, 5, 12, 7, 10, 6, 11, 1, 4, 2, 3)]
    for words in ("8/9 winner", "5/12 winner", "7/10 winner", "6/11 winner",
                  "1 v 8/9 winner", "4 v 5/12 winner", "2 v 7/10 winner", "3 v 6/11 winner",
                  "Semifinal winner", "National title"):
        assert words in part, words
    # The semifinals as the engine plays them (engine/cfprace SEMIS): the 1 and 4 sides, the 2 and 3 sides.
    sf = part[part.index("Semifinals"):part.index("National title")]
    assert sf.index("1 v 8/9") < sf.index("4 v 5/12") < sf.index("2 v 7/10") < sf.index("3 v 6/11")
    assert sf.count('class="rc-bk-game"') == 2


def test_the_later_rounds_say_who_meets_whom_never_a_guessed_winner():
    d = T._nfl()
    html = T._render("nflHTML", d)
    for conf in ("AFC", "NFC"):
        part = _section(html, f"rc-bk-conf rc-bk-{SIDE[conf]}")
        later = part[part.index(f"{conf} title game"):]
        assert "data-mark" not in later, "no team is drawn into a round it has not reached"


def test_the_cup_s_knockouts_and_the_college_playoff_s_real_bracket_draw_the_same_way():
    """The NBA Cup's eight and college football's twelve, once named, on the same bracket: every league's
    playoff page reads alike (Ethan, 2026-11-17: "all sports match eachother where it can")."""
    import importlib
    cup_t = importlib.import_module("test_the_nba_cup_bracket")
    cup = cup_t._render(cup_t._built())
    east, west = _section(cup, "rc-bk-conf rc-bk-l"), _section(cup, "rc-bk-conf rc-bk-r")
    assert "rc-bk-mirror" in west and "rc-bk-mirror" not in east, "the West faces the East across the final"
    for half in (east, west):
        assert len(re.findall(r'class="rc-bk-game[ "]', half)) == 3 and "Winner of 1 v 4" in half
    assert "East champion" in _section(cup, 'rc-bk-c"') and "rc-brk" not in cup
    cfp_t = importlib.import_module("test_the_cfp_bracket")
    cfp = cfp_t._render(cfp_t._built())
    part = _section(cfp, "rc-bk-conf")
    assert _seeds(part) == [8, 9, 5, 12, 7, 10, 6, 11, 1, 4, 2, 3], _seeds(part)
    assert "Winner of 8 v 9" in part and "· our line " in part and "rc-brk" not in cfp
    assert part.index("Quarterfinals") < part.index("Semifinals") < part.index("National championship")


def _render_following(fn, payload, teams):
    """The race page drawn for a reader who follows ``teams`` ("nfl:DET")."""
    import json
    import subprocess
    js = f"""
    const state = {{ sport: "nfl", view: "race" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const teamMarkIn = (sp, t) => `<i data-mark="${{t}}"></i>`;
    const teamNameIn = (sp, t) => t;
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const formatGameDate = (s) => s;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    const settings = () => ({{ teams: {json.dumps(teams)} }});
    const isFavTeam = (abbr, sport) => settings().teams.includes(`${{sport || state.sport}}:${{abbr}}`);
    {RACE}
    console.log(JSON.stringify({fn}({json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-"], input=js, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_team_you_follow_is_lit_on_the_bracket_and_said_first():
    d = T._nfl()
    seeded = d["today"]["AFC"]["seeds"][2]["team"]
    hunted = d["today"]["NFC"]["hunt"][0]
    html = _render_following("nflHTML", d, [f"nfl:{seeded}", f"nfl:{hunted['team']}"])
    mine = html[html.index('class="rc-card rc-mine"'):html.index("</ul>", html.index('class="rc-card rc-mine"'))]
    assert f"the AFC’s 3 seed if the season ended today" in mine
    assert "back of the NFC’s 7 seed" in mine or "level with the NFC’s 7 seed" in mine
    assert "to make the playoffs" in mine, "a member sees each one's chance"
    afc = _section(html, "rc-bk-conf rc-bk-l")
    assert afc.count("rc-bk-mine") == 1 and "a team you follow" in afc, "the 3 seed is lit where it is drawn"
    free = _render_following("nflHTML", gate.redact(d, "nfl_race.json"), [f"nfl:{seeded}"])
    card = free[free.index('class="rc-card rc-mine"'):free.index("</ul>", free.index('class="rc-card rc-mine"'))]
    assert "the AFC’s 3 seed" in card and "to make the playoffs" not in card, "the chance is a member's"
    assert "rc-mine" not in T._render("nflHTML", d), "no teams followed, no card"


def test_the_nfc_turns_right_to_left_only_where_the_whole_bracket_fits():
    q = CSS.index("@container (min-width: 980px)")
    assert CSS.count(".rc-bk-mirror { direction: rtl; }") == 1
    assert CSS.index(".rc-bk-mirror { direction: rtl; }") > q
    assert ".rc-bk-side {" in CSS and "direction: ltr;" in CSS[CSS.index(".rc-bk-side {"):]
    # The lines are bars placed on the inline axis, so they turn with the mirror; never side borders,
    # which would stay put when the NFC turns.
    sect = CSS[CSS.index("/* A BRACKET, DRAWN AS ONE"):]
    assert "border-left" not in sect and "border-right" not in sect and "border-inline" not in sect
    assert "inset-inline-start" in sect and "inset-inline-end" in sect


#: The two class names race.css styles that no source line spells out, because
#: `rc-bk-${side}` builds them from SIDE above (AFC -> l, NFC -> r). Every other
#: class in the stylesheet must appear literally in something that renders.
RACE_CSS_BUILT_NAMES = ("rc-bk-l", "rc-bk-r")


def test_every_class_the_race_stylesheet_styles_is_one_something_renders():
    """Two rules in race.css outlived their elements: `.rc-side .rc-meta`, a
    meta line on a bracket side that ncSlotSide never wrote, and `.rc-conf-k`,
    a heading variant left behind when every caller settled on `.rc-conf-h`.
    Found by the nightly sweep on 2026-11-28; neither had a symptom, because
    dead CSS cannot report itself — it parses, it ships, and it waits to be
    re-used for something else and hand it rules nobody remembers writing.

    The lesson the stylesheets already taught twice (test_typography.py's
    balance check, whose list of files may not name files) applies to the
    other direction too, so this ENUMERATES: read every class back out of
    race.css and require that something under web/ actually emits it. The
    only names allowed to be absent are the ones built from a template, and
    they are named above with the expression that builds them — a list that
    stays short because a growing one means the check has stopped working.

    Source-level and store-free: a dead-rule claim that needed a browser or
    a built slate would pass on CI and rot on the laptop, or the reverse."""
    classes = sorted(set(m.group(1) for m in re.finditer(
        r"\.(-?[_a-zA-Z][\w-]*)", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S))))
    assert len(classes) > 60, "the class scan stopped reading the stylesheet"

    rendered = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted((ROOT / "web").rglob("*"))
        if p.suffix in (".js", ".html") and "vendor" not in p.parts)
    assert "rcBkRoundsHTML" in rendered, "the renderers are not in the corpus"

    for cls in classes:
        if cls in RACE_CSS_BUILT_NAMES:
            continue
        # As a renderer would write it: the name ends where the attribute,
        # a space or an interpolation ends it (`class="rc-bk-game${...}"` is
        # the literal class with a template appending the next one). A bare
        # substring search would call `.rc-conf-h` live off `rc-conf-held`.
        assert re.search(r"[\"'`\s]" + re.escape(cls) + r"""[\"'`\s$]""", rendered), \
            (f".{cls} in race.css matches no element anything under web/ "
             f"renders — the rule is dead, so delete it or render it")

    for built in RACE_CSS_BUILT_NAMES:
        assert f".{built}" in CSS, f"{built} is allowed for a rule that is gone"
        stem = built.rsplit("-", 1)[0]
        assert stem + "-${" in rendered, \
            f"{built} is no longer built from a template; it needs no exemption"


# --- in a browser --------------------------------------------------------------------
GEOMETRY = """() => {
  const mid = (el) => { const r = el.getBoundingClientRect(); return r.top + r.height / 2; };
  const cols = (sec) => [...sec.querySelectorAll('.rc-bk-col')].map((c) => [...c.querySelectorAll('.rc-bk-game')].map(mid));
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
    return [r.left, r.right]; };
  const secs = [...document.querySelectorAll('#race-body .rc-bk-conf')];
  const swipe = [...document.querySelectorAll('#race-body .rc-bk-scroll')].map((s) => {
    s.scrollLeft = 1e6;
    const last = [...s.querySelectorAll('.rc-bk-col')].pop().getBoundingClientRect();
    const r = s.getBoundingClientRect();
    const reach = last.right <= r.right + 1 && last.left >= r.left - 1;
    s.scrollLeft = 0;
    return reach;
  });
  const nfc = document.querySelector('.rc-bk-r .rc-bk-rounds');
  const nfcCols = nfc ? [...nfc.querySelectorAll('.rc-bk-col')].map((c) => c.getBoundingClientRect().left) : [];
  return {cols: secs.map(cols), swipe, wide: document.documentElement.scrollWidth > innerWidth + 1,
          dir: nfc ? getComputedStyle(nfc).direction : null, nfcCols,
          afc: box('.rc-bk-l'), sb: box('.rc-bk-c'), nfcBox: box('.rc-bk-r')};
}"""


def _browser():
    from playwright.sync_api import sync_playwright
    import rendercheck
    cfp, _ = T._fixtures()
    nfl = T._nfl()
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for sport, name, payload in (("nfl", "nfl_race.json", nfl), ("cfb", "cfp_race.json", cfp)):
                    for width in (390, 1366):
                        ctx = browser.new_context(viewport={"width": width, "height": 900}, service_workers="block")
                        page = ctx.new_page()
                        page.on("pageerror", lambda e: errs.append(str(e)))
                        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                        body = json.dumps(payload)

                        def ok(text):
                            return lambda r, *_: r.fulfill(status=200, content_type="application/json", body=text)
                        page.route(f"**/api/board/{name}", ok(body))
                        page.route(f"**/data/{name}", ok(body))
                        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                        page.goto(f"http://127.0.0.1:{port}/index.html?sport={sport}#race", wait_until="load")
                        page.wait_for_selector("#race-body .rc-bk-game", timeout=15000)
                        got[(sport, width)] = page.evaluate(GEOMETRY)
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def _level(a, b, c=None):
    want = a if c is None else (a + c) / 2
    return abs(b - want) <= 2.5


def test_in_a_browser_each_game_sits_level_with_its_feeders_and_every_round_can_be_reached():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    got, errs = _browser()
    assert not errs, errs
    for (sport, width), g in got.items():
        assert not g["wide"], f"{sport} at {width}px: the page scrolls sideways"
        assert all(g["swipe"]), f"{sport} at {width}px: a round no one can swipe to"
    for width in (390, 1366):
        for wc, div, title in got[("nfl", width)]["cols"]:
            assert len(wc) == 4 and len(div) == 2 and len(title) == 1
            assert _level(wc[0], div[0], wc[1]) and _level(wc[2], div[1], wc[3]), (width, wc, div)
            assert _level(div[0], title[0], div[1]), (width, div, title)
        (fr, qf, sf, fin), = got[("cfb", width)]["cols"]
        assert all(_level(a, b) for a, b in zip(fr, qf)), (width, fr, qf)
        assert _level(qf[0], sf[0], qf[1]) and _level(qf[2], sf[1], qf[3]), (width, qf, sf)
        assert _level(sf[0], fin[0], sf[1]), (width, sf, fin)
    phone, wide = got[("nfl", 390)], got[("nfl", 1366)]
    assert phone["dir"] == "ltr" and phone["nfcCols"] == sorted(phone["nfcCols"]), "on a phone the NFC reads left to right"
    assert wide["dir"] == "rtl" and wide["nfcCols"] == sorted(wide["nfcCols"], reverse=True), "the NFC mirrors the AFC"
    assert wide["afc"][1] <= wide["sb"][0] + 1 and wide["sb"][1] <= wide["nfcBox"][0] + 1, "AFC, Super Bowl, NFC"


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
                print(f"  FAIL {name}: {exc!r}")
    print()
    print(f"{fails} failed" if fails else f"{ran} tests passed.")
    sys.exit(1 if fails else 0)
