"""A football pick's page draws his route or carry chart, with no tap.

Ethan, 2026-10-13: "I feel like there is more then one place we can route
the route checker on. We should show the route checker on the most likely
bets as well like when you click on the player in the most likely bets it
will automatically show the charts in that area with all the other info."

Every door to a football pick (a Most Likely row or card, an Edge pick, a
bet on the Live tab, a read on the game page) lands on the pick page, so
the chart is drawn there, and on the player page's deep card. Pinned here:

  * the page leaves a slot for a bet the charts speak to (rushing,
    receiving, an anytime touchdown) and none for a passer's yards or any
    other sport; college has carries only;
  * it sits after the form, among the pick's other sections, and first
    under the card on the player page;
  * the settle pass draws every new slot, wherever it was drawn;
  * the page's redraw every minute hands the drawn chart back (ccKeep), so
    the game the reader picked survives it;
  * js/carrychart.js picks the chart from the bet: his targets for
    receiving, his runs for rushing, both behind a switch for rush + rec
    yards and an anytime touchdown, his own first;
  * a pick page's chart asks for its data as it nears the screen, reads the
    last ten minutes' answer first and never scrolls the page; the overlay
    still asks every time;
  * the parlay checker's football legs carry the chart doors.

The browser half is opt-in (QB_BROWSER_TESTS=1): a page holding the module
mounts a slot, draws the route chart, switches to carries, and a redraw of
the host through ccKeep keeps the very same chart.

Run directly: `python3 tests/test_the_pick_page_draws_his_chart.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
SLIP_JS = ROOT / "web" / "js" / "slip.js"
SLIP_CSS = (ROOT / "web" / "css" / "slip.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(prog):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- the page leaves a slot ---------------------------------------------------
def test_a_slot_for_every_football_bet_the_charts_speak_to():
    prog = """
      const escapeAttr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
      const state = { sport: "nfl" };
    """ + _fn(APP, "chartSlot") + """
      const row = (sport, market, player = "Sam LaPorta", position = "TE") => ({ sport, market, player, position });
      console.log(JSON.stringify({
        rec: chartSlot(row("nfl", "receptions")), yds: chartSlot(row("nfl", "rec_yds")),
        rush: chartSlot(row("nfl", "rush_yds")), att: chartSlot(row("nfl", "rush_att")),
        both: chartSlot(row("nfl", "rush_rec_yds")), td: chartSlot(row("nfl", "anytime_td")),
        qbrun: chartSlot(row("nfl", "pass_rush_yds")),
        pass: chartSlot(row("nfl", "pass_yds")), ints: chartSlot(row("nfl", "pass_int")),
        kick: chartSlot(row("nfl", "kick_pts")), tackles: chartSlot(row("nfl", "tackles_ast")),
        cfbRush: chartSlot(row("cfb", "rush_yds")), cfbTd: chartSlot(row("cfb", "anytime_td")),
        cfbRec: chartSlot(row("cfb", "receptions")),
        mlb: chartSlot(row("mlb", "hits")), nba: chartSlot(row("nba", "reb")),
        board: chartSlot({ market: "receptions", player: "Board Default", position: "WR" }),
        nobody: chartSlot({ sport: "nfl", market: "receptions", player: "" }),
        quote: chartSlot(row("nfl", "receptions", 'Ja"Marr <Chase>', "WR")),
      }));"""
    got = _node(prog)
    if got is None:
        return
    for k in ("rec", "yds", "rush", "att", "both", "td", "qbrun", "cfbRush", "cfbTd", "board"):
        assert got[k].startswith('<div class="cc-slot"'), k
    for k in ("pass", "ints", "kick", "tackles", "cfbRec", "mlb", "nba", "nobody"):
        assert got[k] == "", (k, got[k])
    assert 'data-cc="Sam LaPorta" data-lg="nfl" data-mkt="receptions" data-pos="TE"' in got["rec"]
    assert 'data-lg="cfb"' in got["cfbRush"] and 'data-lg="nfl"' in got["board"], "the board's league by default"
    assert 'data-cc="Ja&quot;Marr &lt;Chase>"' in got["quote"], "a name is escaped into its attribute"


def test_it_sits_among_the_picks_sections_and_first_on_the_player_page():
    page = APP[APP.index("function renderPropPage()"):APP.index("function invNorm(")]
    form = page.index("propFormRows(r.form, line, over)")
    slot = page.index("${chartSlot(r)}")
    assert form < slot < page.index("${scriptCardHTML(r)}") < page.index("vsBlockHTML(r.player"), \
        "after the form, before the script and the versus block"
    depth = _fn(APP, "propDepthHTML")
    assert depth.index("${chartSlot(r)}") < depth.index("${booksTableHTML(r)}"), "first under the player's card"


def test_the_settle_pass_draws_every_new_slot():
    now = _fn(APP, "settleNow")
    assert "mountCharts(root);" in now
    mount = _fn(APP, "mountCharts")
    assert '.cc-slot:not([data-on])' in mount and "m.mount" in mount and "el.isConnected" in mount, \
        "a slot drawn once, never after the page has thrown it away"
    load = _fn(APP, "ccLoad")
    assert "--n || ok(" in load and "css.onload = css.onerror = done;" in load, \
        "the chart is drawn once its stylesheet has arrived, not before"


def test_the_minutes_redraw_hands_the_chart_back():
    keep = _fn(APP, "ccKeep")
    assert '.cc-slot[data-on]' in keep and "el.replaceWith(o)" in keep
    assert "const ccKey = (el) => `${el.dataset.lg}|${el.dataset.cc}|${el.dataset.mkt}`;" in APP
    page = APP[APP.index("function renderPropPage()"):APP.index("function invNorm(")]
    assert page.index("const keep = ccKeep(host);") < page.index("host.innerHTML = `\n    <div class=\"pp-nav\">") \
        < page.index("keep(host);"), "lifted out before the redraw, put back after it"
    i = APP.index("async function renderPlayers(")
    players = APP[i:APP.index("\n/* The UFC hero", i)]
    assert players.index("const keep = ccKeep(host);") < players.index("keep(host);")


# --- which chart --------------------------------------------------------------
def _cc(js):
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    return _node(f"{stubs}\n{CC_JS}\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")


def test_the_bet_picks_the_chart_and_his_own_comes_first():
    got = _cc("""
      const k = T.kindsFor;
      return {
        rec: k("nfl", "receptions", "WR"), yds: k("nfl", "rec_yds", "TE"),
        rush: k("nfl", "rush_yds", "RB"), att: k("nfl", "rush_att", "RB"), qb: k("nfl", "pass_rush_yds", "QB"),
        rrRb: k("nfl", "rush_rec_yds", "RB"), rrWr: k("nfl", "rush_rec_yds", "WR"),
        tdTe: k("nfl", "anytime_td", "TE"), tdRb: k("nfl", "anytime_td", "RB"), tdQb: k("nfl", "anytime_td", "QB"),
        tdNone: k("nfl", "anytime_td", ""),
        pass: k("nfl", "pass_yds", "QB"), cfbTd: k("cfb", "anytime_td", "WR"), cfbRec: k("cfb", "receptions", "WR"),
        cfbRush: k("cfb", "rush_yds", "RB"),
        tally: [T.tally(5, 88), T.tally(1, -2), T.tally(3, 0)],
      };""")
    if got is None:
        return
    assert got["rec"] == ["routes"] and got["yds"] == ["routes"]
    assert got["rush"] == got["att"] == got["qb"] == ["carries"]
    assert got["rrRb"] == ["carries", "routes"] and got["rrWr"] == ["routes", "carries"]
    assert got["tdTe"] == ["routes", "carries"] and got["tdRb"] == got["tdQb"] == got["tdNone"] == ["carries", "routes"]
    assert got["pass"] == [] and got["cfbRec"] == []
    assert got["cfbTd"] == ["carries"] and got["cfbRush"] == ["carries"], "the college file has no air yards"
    assert got["tally"] == ["5-88", "1 for −2", "3-0"], "a game he lost yards in reads as one"


def test_a_pick_pages_chart_is_quiet_and_cheap():
    assert "function mount(el)" in CC_JS and "window.QBCarry = { open, close, mount," in CC_JS
    assert "const hit = c.inline && CACHE.get(q);" in CC_JS, "the overlay asks every time, as it always has"
    assert "const CACHE_MS = 10 * 60 * 1000;" in CC_JS and "if (q && !data.filling) CACHE.set(q" in CC_JS, \
        "a chart still being filled is never kept"
    assert 'rootMargin: "800px 0px"' in CC_JS and "io.observe(el);" in CC_JS, "asked for as it nears the screen"
    assert ".scrollIntoView(" not in CC_JS, "a chart halfway down a pick page never pulls the page to it"
    assert "row.scrollLeft +=" in CC_JS, "the chosen game's chip is centred by scrolling its own row"
    # A tap answers only from inside the chart: the page around it carries
    # its own data-view and data-season attributes.
    assert "return x && ov.contains(x) ? x : null;" in CC_JS
    # The long tail folds on a pick page and nowhere else.
    i = CC_JS.index("  function fold(")
    fold = CC_JS[i:CC_JS.index("\n  }\n", i)]
    assert "if (!C.inline || !html) return html;" in fold
    for key in ('fold("list"', 'fold("splits"', 'fold("note"'):
        assert key in CC_JS, key
    assert "onclick" not in CC_JS and "onerror" not in CC_JS, "no inline handlers under the page's CSP"


def test_the_styles():
    for sel in (".cc-slot { margin-top: 34px; }", ".cc-slot > .section-title { margin-top: 0; }",
                ".cc-inline:hover { transform: none; }", ".cc-inline { container-type: inline-size; }",
                "@container (min-width: 760px)", ".cc-kinds + .cc-seasons { margin-left: auto; }",
                ".cc-more > summary"):
        assert sel in CC_CSS, sel
    assert re.search(r"\.cc-split \{ display: grid;", CC_CSS), "a wide card sets the field beside its numbers"
    for sel in (".pgr-charts", ".pgr-chart"):
        assert sel in SLIP_CSS, sel
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS + SLIP_CSS), "tokens only"


# --- the parlay checker -------------------------------------------------------
def test_a_football_leg_in_the_parlay_checker_carries_his_chart_doors():
    leg = lambda sport, market, player="Puka Nacua": {  # noqa: E731
        "sport": sport, "player": player, "team": "LA", "market": market, "side": "over", "line": 5.5,
        "verdict": "strong", "prob": 0.7, "needs": 0.55}
    slip = {"n_legs": 6, "grade": "B", "legs": [
        leg("nfl", "receptions"), leg("nfl", "anytime_td", "Kyren Williams"), leg("cfb", "rush_yds", "Nate Frazier"),
        leg("cfb", "receptions", "College Receiver"), leg("nba", "reb", "Josh Hart"),
        leg("nfl", "receptions", "<img src=x>")]}
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    prog = ("const vm = require('vm'); const fs = require('fs');"
            "const ctx = { window: {} }; vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
            f"process.stdout.write(ctx.window.QBSlip.card({json.dumps(slip)}));")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    html = out.stdout
    doors = re.findall(r'class="pgr-chart cc-open" data-carry="([^"]*)" data-lg="(\w+)" data-kind="(\w+)"', html)
    assert doors == [("Puka Nacua", "nfl", "routes"), ("Kyren Williams", "nfl", "routes"),
                     ("Kyren Williams", "nfl", "carries"), ("Nate Frazier", "cfb", "carries"),
                     ("&lt;img src=x&gt;", "nfl", "routes")], doors
    assert "<img src=x>" not in html


# --- the browser, opt-in --------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div id="host" style="width:360px"></div>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.ASKED = [];
  window.fetch = async (q) => {{ window.ASKED.push(q); return {{ ok: true, json: async () => (q.includes("/routes") ? window.ROUTES : window.CARRIES) }}; }};
  {keep}
</script>
<script>{js}</script>
</body></html>"""


def _routes():
    t = lambda i: {"c": 1, "y": 8 + i, "ay": 5 + i, "s": "LMR"[i % 3], "q": 1 + i % 4, "dn": 1, "ds": 10, "yl": 60}  # noqa: E731
    g = lambda w, n: {"id": f"g{w}", "week": w, "opp": "KC", "home": True, "team": "DET",  # noqa: E731
                      "line": {"tgt": n, "rec": n, "yds": 40, "td": 0, "yac": 10, "adot": 6.0, "first": 2},
                      "targets": [t(i) for i in range(n)]}
    return {"player": "Sam LaPorta", "sport": "nfl", "season": 2026, "seasons": [2026], "routes": False,
            "team": "DET", "games": [g(6, 5), g(5, 4)],
            "season_line": {"tgt": 9, "rec": 9, "yds": 80, "td": 0, "yac": 20, "adot": 6.0, "first": 4,
                            "catch": 1.0, "ypt": 8.9, "contested": 0, "contested_won": 0, "drops": 0},
            "by_zone": [], "by_down": [], "ngs": {}}


def _carries():
    c = lambda i: {"y": 3 + i, "band": "short", "h": "LG", "q": 1, "dn": 1, "ds": 10, "yl": 70}  # noqa: E731
    g = {"id": "g6", "week": 6, "opp": "KC", "home": True, "team": "DET",
         "line": {"n": 3, "yds": 12, "ypc": 4.0, "td": 0, "first": 1}, "carries": [c(i) for i in range(3)]}
    return {"player": "Sam LaPorta", "sport": "nfl", "season": 2026, "seasons": [2026], "holes": True,
            "team": "DET", "games": [g], "season_line": {"n": 3, "yds": 12, "ypc": 4.0, "td": 0, "first": 1,
                                                          "success": 0.3, "stuffed": 0.0, "explosive": 0, "long": 5},
            "by_hole": [], "by_down": [], "by_zone": [], "kinds": None, "ngs": {}}


def test_in_a_browser_the_slot_draws_switches_and_survives_a_redraw():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    keep = APP[APP.index("const ccKey = (el) =>"):APP.index("\n}\n", APP.index("function ccKeep(")) + 2]
    html = PAGE.format(css=CC_CSS, js=CC_JS, keep=keep)
    slot = ('<div class="cc-slot" data-cc="Sam LaPorta" data-lg="nfl" data-mkt="anytime_td" data-pos="TE"></div>'
            '<p>after</p>')
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(html)
            page.evaluate("([r, c]) => { window.ROUTES = r; window.CARRIES = c; }", [_routes(), _carries()])
            page.evaluate(f"document.getElementById('host').innerHTML = {json.dumps(slot)};"
                          "window.QBCarry.mount(document.querySelector('.cc-slot'));")
            page.wait_for_selector(".cc-slot .cc-stage svg", timeout=5000)
            assert page.inner_text(".cc-sec").startswith("Route chart"), "a tight end's targets first"
            assert page.locator("[data-ck]").all_inner_texts() == ["Routes", "Carries"]
            page.click(".cc-games .cc-chip[data-gi='1']")
            page.evaluate("document.querySelector('.cc-slot')._probe = 1")
            asked = page.evaluate("window.ASKED.length")
            # The page's minute: the host redrawn with a fresh twin of the slot.
            page.evaluate(f"""(() => {{ const host = document.getElementById('host');
                const keep = ccKeep(host); host.innerHTML = {json.dumps(slot)}; keep(host); }})()""")
            assert page.evaluate("document.querySelector('.cc-slot')._probe") == 1, "the same chart, handed back"
            assert page.get_attribute(".cc-games .cc-chip.on", "data-gi") == "1", "the game he picked"
            assert page.evaluate("window.ASKED.length") == asked, "nothing asked again"
            page.click("[data-ck=carries]")
            page.wait_for_selector(".cc-slot .cc-stage .cc-run", timeout=5000)
            assert page.inner_text(".cc-sec").startswith("Carry chart")
            assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
            # A mounted slot is mounted once.
            page.evaluate("window.QBCarry.mount(document.querySelector('.cc-slot'))")
            assert page.locator(".cc-slot .cc-inline").count() == 1
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
