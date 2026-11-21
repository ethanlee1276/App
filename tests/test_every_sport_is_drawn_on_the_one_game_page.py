"""Every sport's live game page is the NFL's page (step AAI, 21 November 2026).

Ethan, 21 November 2026: "go work on the nba and CFB and all other sports live
page to try to match nfl. We have put a lot of work into nfls live page and
nfl in general so all sports in all aspects should be trying to match nfl and
that should be automatic when we do any visual changes and anything in that
aspect".

THE PAGE WAS THREE. Football drew detail.js's page. Basketball and hockey each
drew a whole page of their own (js/hoopscast.js, js/rinkcast.js): a scoreboard,
an arena and cards with tabs of their own, restyled by hand to look like
football's. Nothing done to football's page reached them: no bar that stays
when the page scrolls, no ⋯ menu, no card for the play right now, no Standings
tab, their footer in the middle of the page.

NOW IT IS ONE (detail.js gpPageHTML), for every sport but baseball, and a sport
brings only what is its own (gpKit): the picture under the score, its newest
play in words, its rows and its words for a play, what its Stats room counts
itself, and the little a score says that is one sport's. So a change to the
page is a change to every sport's page, with nothing to copy across.

Pinned here:
  * one page function, chosen by the tab set, with no sport named in it;
  * a sport's file hands over parts and draws none of the page: none of the
    page's class names, no scoreboard, no tabs, no footer, no host of its own;
  * a sport's stylesheet styles only its own picture and cards, and sizes
    them by the card they sit in, never the screen;
  * the newest play is the one card, made of the same four parts, whichever
    sport says it;
  * in a browser: football, college football, basketball, college basketball
    and hockey draw the same page in the same order with the same tabs, the
    same bar that stays and the same ⋯ menu, on a phone and on a desktop.

Baseball (out of season) keeps its own four rooms: its game file is the MLB
builder's own shape. Offline; the browser half is opt-in (QB_BROWSER_TESTS=1)
and aborts every request that leaves the page's own server.

Run directly: `python3 tests/test_every_sport_is_drawn_on_the_one_game_page.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
DETAIL, GC = READ("web", "js", "detail.js"), READ("web", "js", "gamecast.js")
FILES = {"hoopscast": READ("web", "js", "hoopscast.js"), "rinkcast": READ("web", "js", "rinkcast.js")}
SHEETS = {"hoopscast": READ("web", "css", "hoopscast.css"), "rinkcast": READ("web", "css", "rinkcast.css")}
DETAIL_CSS = READ("web", "css", "detail.css")

#: What a sport may hand the page (detail.js gpKit): each is read by the page, by name.
PARTS = ("stage", "now", "rows", "say", "teamStats", "boxes", "statsExtra", "ball", "ballIcon", "ballTitle",
         "marks", "mid", "down", "live", "wire")


class _Sibling:
    """A sibling test module, imported when a test first needs it (never at module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


NBA, NHL, FB = (_Sibling("test_the_nba_live_page"), _Sibling("test_the_nhl_live_page"), _Sibling("test_the_live_trackers"))


def _fn(src, name, indent=""):
    """A function's text; `indent` for one declared inside a module's own scope (js/gamecast.js)."""
    i = src.index(f"function {name}(")
    return src[i:src.index(f"\n{indent}}}\n", i) + 2]


# --- one page ----------------------------------------------------------------------
def test_one_page_function_draws_every_sport_but_baseball():
    assert 'const pbpTabsFor = (league) => (league === "mlb" ? PBP_TABS : GP_TABS);' in DETAIL
    assert 'const GP_TABS = [["stats", "Stats"], ["plays", "Play-By-Play"], ["standings", "Standings"], ["props", "Our picks"]];' in DETAIL
    page = DETAIL[DETAIL.index("async function renderPbpPage("):DETAIL.index("THE GAME PAGE IN THE CLUBS' COLOURS")]
    assert "const one = tabs === GP_TABS;" in page
    assert "const kit = one ? gpKit({ d, league, lv, GC, boardGame, faces, event }) : null;" in page
    assert "host.innerHTML = one ? gpPageHTML({ d, league, lv, tab, tabs, GC, boardGame, faces, stripHTML, back, event, kit }) : `" in page
    # Two layouts in the whole file: the one page, and baseball's own rooms.
    assert DETAIL.count('<div class="pbp-layout') == 2 and page.count('<div class="pbp-layout gp">') == 1
    # No other way in: the handover to a sport's own page is gone, from here and from the shared module.
    for gone in ("GC.hoops", "GC.panel", ".render(host", "gpFootballHTML", "GP_FB_TABS", "GC_TABS"):
        assert gone not in DETAIL, gone
    for gone in ("function hoops(", "function rink(", "function panel(", "QBHoops", "QBRink"):
        assert gone not in GC, gone


def test_the_page_names_no_sport_where_it_lays_itself_out():
    """Football is asked for only where a thing IS football's (its field, its drives, its timeouts); a part is
    taken from whichever sport handed it over. A sport's name in the page's own layout is how three pages began."""
    for name in ("gpPageHTML", "gpCompactHTML", "gpStatsHTML", "gpPlaysHTML", "gpNowHTML", "gpPeriodsHTML", "gpKit", "gpPlainKit",
                 "gpPicksHTML", "gpRailPicksHTML"):
        named = re.findall(r'"(nba|wnba|cbb|nhl|nfl|cfb)"', _fn(DETAIL, name))
        assert not named, (name, named)
    page = _fn(DETAIL, "gpPageHTML")
    order = ["${gpCompactHTML(d, league, at, tabs, tab, kit)}", "${pbpBoardHTML(d, league, at, {", "${stage}", "${gpLineHTML(d, league, at)}",
             "${pbpAwayHTML(d, league)}${pbpRecapHTML(d, league)}", "${gpNowHTML(d, league, faces, boardGame, GC, !!stage, kit)}",
             "${pbpMineSlotsHTML()}", '${lv.state === "live" ? pbpCallItHTML(d, league) : ""}', '<div class="gch-entry-slot"></div>',
             "${pbpTabsHTML(tab, null, tabs)}", '<div class="pbp-panel" data-pbp-panel="${tab}">${panel}</div>', "${back}", "${pbpFootHTML()}"]
    at = [page.index(part) for part in order]
    assert at == sorted(at), "the page's order, top to bottom, the same for every sport"
    # Each part a sport may hand over is read by the page somewhere, by its name.
    readers = "".join(_fn(DETAIL, n) for n in ("gpPageHTML", "gpCompactHTML", "gpStatsHTML", "gpPlaysHTML", "gpNowHTML", "pbpBoardHTML",
                                                "renderPbpPage"))
    for part in PARTS:
        assert re.search(rf"\b(kit|k|o|opt)\)?(\s*\|\|\s*\{{\}}\))?\.{part}\b", readers), part


def test_a_sport_that_cannot_bring_its_parts_is_still_the_same_page():
    kit = _fn(DETAIL, "gpKit")
    assert "if (PBP_FOOTBALL.has(league)) return { stage: gpFieldHTML(d, league, o.lv) };" in kit
    assert "const plain = gpPlainKit(o);" in kit, "the parts any game file can make"
    assert "try { return { ...plain, ...mod.parts(o) }; } catch (e) { console.error(\"gpKit\", league, e); return plain; }" in kit
    mod = _fn(DETAIL, "gpSportMod")
    assert 'if (!name || (name === "rinkcast" && !(d || {}).rink)) return { mod: null, wait: "" };' in mod
    assert "return { mod: null, wait: _gpSportFile[name] === \"loading\" ? GP_SPORT_STAGE[name] : \"\" };" in mod
    assert 'const GP_SPORT_FILE = { nba: "hoopscast", wnba: "hoopscast", cbb: "hoopscast", nhl: "rinkcast" };' in DETAIL
    assert 'const GP_SPORT_MOD = { hoopscast: "QBHoops", rinkcast: "QBRink" };' in DETAIL


# --- a sport's file ----------------------------------------------------------------
def test_a_sports_file_hands_over_parts_and_draws_none_of_the_page():
    for name, js in FILES.items():
        assert "function parts(ctx) {" in js and re.search(r"window\.QB\w+ = \{\n    parts,\n", js), name
        body = js[js.index("function parts(ctx) {"):]
        body = body[:body.index("\n  }\n")]
        keys = set(re.findall(r"^\s{6}(\w+)[:,]", body, flags=re.M)) | set(re.findall(r", (ballIcon|ballTitle|say|wire|down)[:,]", body))
        assert keys <= set(PARTS), (name, sorted(keys - set(PARTS)))
        assert {"stage", "now", "say", "statsExtra", "ball", "wire"} <= keys, (name, sorted(keys))
        # None of the page: no host of its own, no scoreboard, no tabs, no footer, no chat slot, no picks rail.
        for gone in ("host.innerHTML", "function render(", "stripHTML", "pbpFootHTML", "pbpTabsHTML", "gch-entry-slot", "pbpPropsHTML",
                     "pbpCallItHTML", "watchHTML", "chatPlayBadge", "gpLineHTML"):
            assert gone not in js, (name, gone)
        # None of the page's own class names: its boxes are made by the page's builders.
        assert not re.search(r'class="[^"$]*\b(gp|pbp-sb|pbp-tab|pbp-panel|pbp-layout|pbp-hero)-?', js), name
        for builder in ("gpStageHTML(", "gpCardHTML("):
            assert builder in js, (name, builder)
        assert "G.playNow(d, " in js, (name, "the newest play goes to the page's one card")
    assert "gpTsCardHTML(" in FILES["rinkcast"] and "gpBoxCardHTML(" in FILES["rinkcast"], "hockey's own count, in the page's cards"
    for builder in ("gpStageHTML", "gpCardHTML", "gpTsRowHTML", "gpTsCardHTML", "gpBoxCardHTML"):
        assert f"function {builder}(" in DETAIL, builder
    assert "const gpNoteHTML = (text) =>" in DETAIL and "const gpChipHTML = (text, colour) =>" in DETAIL


def test_a_sports_stylesheet_styles_only_its_own_and_by_its_own_width():
    for name, css in SHEETS.items():
        own = "hc" if name == "hoopscast" else "rc"
        selectors = re.findall(r"(?m)^([^@/{}\n][^{}\n]*)\{", css)
        for sel in selectors:
            for part in sel.split(","):
                part = part.strip()
                if not part or part.startswith(("from", "to")) or re.match(r"^\d+%", part):
                    continue
                assert re.match(rf"^\.{own}-", part), (name, part, "a rule that does not start from the sport's own class")
        # What gives way on a narrow card is asked of the card (a container query), never the screen.
        assert "@media (max-width" not in css and "@media (min-width" not in css, name
        assert f"container: {own}stage / inline-size;" in css and f"@container {own}stage (max-width:" in css, name
        # The old page's own scoreboard, cards and tabs left no rules behind.
        for gone in (f".{own}-score", f".{own}-tab", f".{own}-plays", f".{own}-odds", f".{own}-lineup", f".{own}-caption", f".{own}-goal-word"):
            assert gone not in css, (name, gone)
    # The page's sheet holds no copy of a sport's score (the "same score on the wash" block went with their pages).
    assert not re.search(r"\.(hc|rc)-", DETAIL_CSS), "detail.css styles the page; a sport's sheet styles the sport"


# --- the one card for the newest play ----------------------------------------------
def test_the_newest_play_is_one_card_made_of_the_same_four_parts():
    for part in ("function nowCardHTML(o) {", "function nowHeadHTML(league, team, k, title) {",
                 "function nowChipHTML(league, faces, name, row, where, line) {", "function nowLastHTML(o) {"):
        assert GC.count(part) == 1, part
    football = _fn(GC, "driveViewHTML", "  ") + _fn(GC, "dvLastHTML", "  ")
    others = _fn(GC, "playNowHTML", "  ")
    for call in ("nowCardHTML(", "nowHeadHTML(", "nowChipHTML(", "nowLastHTML("):
        assert call in football and call in others, call
    assert 'class="card gc-dv"' in _fn(GC, "nowCardHTML", "  ") and 'class="card gc-dv"' not in football + others, "one box, written once"
    assert "playNow: playNowHTML, plainNow: plainNowHTML," in GC


def test_the_sports_parts_meet_the_pages_builders_in_node():
    """Basketball's and hockey's parts, drawn with the page's real builders (tests/_app.page_builders): the same
    boxes, whichever sport is in them."""
    nba, nhl = NBA._parts(NBA._deep()), NHL._parts(NHL._deep())
    if nba is None or nhl is None:
        print("      (skipped: no node)")
        return
    for name, P, own in (("basketball", nba, "hc"), ("hockey", nhl, "rc")):
        assert P["stage"].startswith(f'<div class="card gp-stage {own}-stage v-live" style="--ca:'), name
        assert P["now"].startswith('<div class="card gc-dv" data-gc-dv>'), name
        assert '<div class="gc-dv-who"><div class="gc-k">Last play · ' in P["now"], name
        cards = re.findall(r'<div class="card gp-card ([\w-]+)"', P["statsExtra"])
        assert len(cards) == 2 and len(set(cards)) == 1, (name, cards)
        assert P["statsExtra"].count('<div class="gp-card-head"><b>') == 2, name
        assert P["wire"] == "function", name
    assert nhl["teamStats"].startswith('<div class="card gp-card gp-tscard">') and nhl["boxes"].count('class="card gp-card gp-boxcard"') == 2


# --- in a browser (opt-in) ---------------------------------------------------------
SHAPE = """(() => {
  const main = document.querySelector('.pbp-layout.pbp-has-tabs.gp .pbp-main');
  if (!main) return null;
  const first = (el) => (typeof el.className === 'string' ? el.className.split(' ').filter(Boolean) : []);
  const kids = [...main.children].map(first);
  const at = (cls) => kids.findIndex((k) => k.includes(cls));
  const css = (sel, prop) => { const el = document.querySelector(sel); return el ? getComputedStyle(el)[prop] : null; };
  return {
    order: ['gp-stick', 'pbp-hero', 'STAGE', 'gp-line', 'gc-dv', 'gch-entry-slot', 'pbp-tabs', 'pbp-panel', 'pbp-foot']
      .map((c) => (c === 'STAGE' ? Math.max(at('gp-stage'), at('gp-field')) : at(c))),
    tabs: [...document.querySelectorAll('.pbp-tabs .pbp-tab')].map((b) => b.textContent.trim()),
    active: (document.querySelector('.pbp-tab.active') || {}).textContent,
    compact: [...document.querySelectorAll('.gp-compact .gp-ctab')].map((b) => b.textContent.trim()),
    more: !!document.querySelector('.pbp-hero .gp-more'),
    periods: document.querySelectorAll('.pbp-panel details.gp-dr').length,
    open: document.querySelectorAll('.pbp-panel details.gp-dr[open]').length,
    said: !!document.querySelector('.gc-dv .gc-dv-said'),
    hero: [css('.pbp-hero', 'borderRadius'), css('.pbp-hero', 'backgroundColor'), css('.pbp-sb-pts', 'fontSize'), css('.pbp-sb-nick', 'fontSize')],
    card: [css('.gc-dv', 'borderRadius'), css('.gc-dv', 'backgroundColor'), css('.pbp-tabs', 'borderRadius'), css('details.gp-dr', 'borderRadius')],
    rail: !!document.querySelector('.pbp-rail .pbp-railcard'),
    wide: document.scrollingElement.scrollWidth - innerWidth,
  };
})()"""


def _games():
    """One live game a league, each from its own test's builder."""
    fb = FB._fb_doc()
    fb["event_id"] = "e9"
    cfb = json.loads(json.dumps(fb).replace('"DAL"', '"ALA"').replace('"TB"', '"MSST"'))
    cfb.update({"league": "cfb", "event_id": "e10"})
    nba = NBA._deep()
    cbb = dict(nba, league="cbb", event_id="401810011")
    nhl = dict(NHL._deep(), linescores={"NYR": [0, 0, 0], "BOS": [0, 1, 0]})
    return [("nfl", fb), ("cfb", cfb), ("nba", nba), ("cbb", cbb), ("nhl", nhl)]


def test_in_a_browser_five_leagues_draw_the_same_page():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    for league, doc in _games():
                        ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                                  has_touch=width < 600, service_workers="block")
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        # Nothing leaves the machine: fonts, logos and faces are refused.
                        page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        ev = doc["event_id"]
                        page.route(f"**/data/pbp/{league}_{ev}.json*", serve(doc))
                        page.route(f"**/data/live_{league}.json*", serve({"games": [
                            {"event_id": ev, "home": doc["home"], "away": doc["away"], "live": doc["live"]}]}))
                        page.goto(f"http://127.0.0.1:{port}/index.html#pbp/{league}/{ev}", wait_until="load")
                        # The page is drawn at once and again when a sport's own file lands: wait for its picture.
                        page.wait_for_selector(".pbp-main > .gp-field, .pbp-main > .gp-stage:not(.gp-stage-wait)", timeout=30000)
                        page.wait_for_selector(".gc-dv .gc-dv-said", timeout=15000)
                        page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                        shape = page.evaluate(SHAPE)
                        assert shape, f"{league} at {width}px: not the one page"
                        shape["errors"] = errors
                        got[(league, width)] = shape
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for width in (390, 1280):
        nfl = got[("nfl", width)]
        for league in ("nfl", "cfb", "nba", "cbb", "nhl"):
            g, at = got[(league, width)], f"{league} at {width}px"
            assert not g["errors"], (at, g["errors"])
            assert all(i >= 0 for i in g["order"]) and g["order"] == sorted(g["order"]), (at, g["order"])
            assert g["tabs"][:4] == ["Stats", "Play-By-Play", "Standings", "Our picks"] and g["active"].strip() == "Play-By-Play", (at, g["tabs"])
            assert g["compact"] == nfl["compact"] and len(g["compact"]) == 4, (at, "the bar that stays, with the same four tabs")
            assert g["more"], (at, "the ⋯ menu by the score")
            assert g["said"], (at, "the play right now, in words")
            assert g["periods"] >= 2 and g["open"] == 1, (at, "the game so far in cards, the one being played open", g["periods"], g["open"])
            assert g["wide"] <= 0, (at, "nothing scrolls sideways")
            # AUTOMATIC: the same boxes in the same styles, because they are the same boxes.
            assert g["hero"] == nfl["hero"], (at, "the score", g["hero"], nfl["hero"])
            assert g["card"] == nfl["card"], (at, "the cards and the tabs", g["card"], nfl["card"])
            assert g["rail"] == nfl["rail"], (at, "the list beside the page")


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
            traceback.print_exc()
    if fails:
        sys.exit(1)
    print(f"\n{len(tests) - fails} tests passed.")
