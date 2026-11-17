"""The player page draws the player's charts, and its tables' pinned column is solid (2026-11-17).

Ethan, with Jalon Daniels' page: "We should still have the players route
charts and pass charts and shit on the player page", and with its Recent
games table: "fix this how it's transparent and u can see through it".
What these hold:

  * the Overview has a charts slot under the last game, drawn by the pick
    page's own door (app.js chartSlot) and mounted by the chart module
    (js/carrychart.js `mount`), so a receiver gets the route chart, a passer
    the throws, a back the carries, a hitter the spray chart, a pitcher the
    pitches, a shooter the shots, a skater or a goalie the shot map;
  * the slot names the market the reader came for (the tapped pick's, shown
    first in the market cards), else tonight's first priced one with its
    opponent, else the market the player's role leads with; college's
    passer gets the runs (college keeps no throw locations); a role with no
    chart (a defender) draws nothing; the minute's redraw keeps the chart;
  * the game column that stays put while a table scrolls is opaque: the
    panel over the page's ground (the glass over the club's colour on the
    player page at night), and a tapped row lays its tint over that, so the
    numbers scrolled under it never show through.

Run directly: `python3 tests/test_the_player_page_draws_the_charts.py`
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
GLCSS = (ROOT / "web" / "css" / "gamelog.css").read_text(encoding="utf-8")
PLRCSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")


def _fn(src, name):
    """One top-level function's source, by its name."""
    i = src.index(f"function {name}(")
    j = src.index("\n}\n", i)
    return src[i:j + 3]


def test_the_overview_has_a_charts_slot_under_the_last_game():
    assert ('`<div class="plr-prev"></div><div class="plr-charts"></div><div class="plr-splitlet"></div>`'
            in PAGE), "under the last game, for every league but UFC (a fighter's page has the fight chart)"
    fill = _fn(PAGE, "plrFill")
    assert fill.index('set(".plr-prev", plrPrevHTML(d));') < fill.index("plrChartsInto(page, d);") < fill.index(
        'set(".plr-splitlet", plrSplitletHTML(d));')
    assert "function chartSlot(r)" in APP and "function mountCharts(root)" in APP, "the pick page's own door"


def _run(cases):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    js = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const escapeAttr = esc; const state = { sport: 'nfl' }; const mounted = [];"
          "const mountCharts = (root) => mounted.push(root.name);"
          "let _profRows = new Map(); let _profTab = {};\n"
          + _fn(APP, "chartSlot")
          + PAGE[PAGE.index("const PLR_CHART_MKT = {"):PAGE.index("/* ---------------- News ---------------- */")]
          + f"""
const out = [];
for (const c of {json.dumps(cases)}) {{
  _profRows = new Map(Object.entries(c.rows || {{}}));
  _profTab = c.tab || {{}};
  const slot = {{ name: c.name, innerHTML: '' }};
  const page = {{ _plr: {{ player: c.player, sport: c.sport }}, querySelector: (s) => (s === '.plr-charts' ? slot : null) }};
  plrChartsInto(page, c.d);
  const first = slot.innerHTML;
  plrChartsInto(page, c.d);
  out.push({{ name: c.name, html: first, mounts: mounted.filter((n) => n === c.name).length }});
}}
process.stdout.write(JSON.stringify(out));""")
    got = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-1500:]
    return {x["name"]: x for x in json.loads(got.stdout)}


def _attrs(html):
    return dict(re.findall(r'data-([a-z]+)="([^"]*)"', html))


def test_the_slot_names_the_market_the_reader_came_for_else_the_roles():
    chase = [{"player": "Ja'Marr Chase", "sport": "nfl", "market": "receptions", "market_label": "Receptions",
              "position": "WR", "opponent": "PIT"},
             {"player": "Ja'Marr Chase", "sport": "nfl", "market": "rec_yds", "market_label": "Receiving Yards",
              "position": "WR", "opponent": "PIT"}]
    got = _run([
        {"name": "priced", "player": "Ja'Marr Chase", "sport": "nfl", "rows": {"Ja'Marr Chase": chase},
         "d": {"role": "receiving", "position": "WR"}},
        {"name": "tapped", "player": "Ja'Marr Chase", "sport": "nfl", "rows": {"Ja'Marr Chase": chase},
         "tab": {"Ja'Marr Chase": "Receiving Yards"}, "d": {"role": "receiving"}},
        {"name": "qb", "player": "Jalon Daniels", "sport": "nfl", "d": {"role": "passing", "position": "QB"}},
        {"name": "cfbqb", "player": "Arch Manning", "sport": "cfb", "d": {"role": "passing", "position": "QB"}},
        {"name": "back", "player": "Bijan Robinson", "sport": "nfl", "d": {"role": "rushing", "position": "RB"}},
        {"name": "kicker", "player": "Cameron Dicker", "sport": "nfl", "d": {"role": "kicking", "position": "K"}},
        {"name": "defender", "player": "Will Anderson Jr.", "sport": "nfl", "d": {"role": "defense", "position": "DE"}},
        {"name": "hitter", "player": "Aaron Judge", "sport": "mlb", "d": {"role": "batting", "position": "RF"}},
        {"name": "arm", "player": "Gerrit Cole", "sport": "mlb", "d": {"role": "pitching", "position": "P"}},
        {"name": "shooter", "player": "Jalen Brunson", "sport": "nba", "d": {"role": "box", "position": "G"}},
        {"name": "goalie", "player": "Joseph Woll", "sport": "nhl", "d": {"role": "goalie", "position": "G"}},
        {"name": "skater", "player": "Connor McDavid", "sport": "nhl", "d": {"role": "skater", "position": "C"}}])
    if got is None:
        return
    a = _attrs(got["priced"]["html"])
    assert (a["cc"], a["lg"], a["mkt"], a["pos"], a["opp"]) == ("Ja&#39;Marr Chase", "nfl", "receptions", "WR", "PIT"), a
    assert _attrs(got["tapped"]["html"])["mkt"] == "rec_yds", "the market the tapped pick opened the cards on"
    want = {"qb": ("nfl", "pass_yds", "QB"), "cfbqb": ("cfb", "rush_yds", "QB"), "back": ("nfl", "rush_yds", "RB"),
            "kicker": ("nfl", "kick_pts", "K"), "hitter": ("mlb", "hits", "RF"), "arm": ("mlb", "strikeouts", "P"),
            "shooter": ("nba", "pts", "G"), "goalie": ("nhl", "saves", "G"), "skater": ("nhl", "sog", "C")}
    for name, (lg, mkt, pos) in want.items():
        a = _attrs(got[name]["html"])
        assert (a["lg"], a["mkt"], a["pos"], a["opp"]) == (lg, mkt, pos, ""), (name, a)
        assert got[name]["mounts"] == 1, (name, "mounted once: the redraw keeps the chart")
    assert got["defender"]["html"] == "" and got["defender"]["mounts"] == 0, "no chart, no slot"
    # Each hint is a market the chart module draws a chart for (js/carrychart.js kindsFor).
    cc = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
    kinds = cc[cc.index("  function kindsFor(sport, mkt, pos) {"):cc.index("  //: The charts whose zones")]
    assert 'if (sport === "mlb") return m ? role(/^(strikeouts|outs)$|pitcher' in kinds
    assert 'if (sport === "nfl" && (p === "QB" || (!p && /^pass/.test(m)))) return role(["passes", "carries"]);' in kinds
    assert 'const runs = /rush|anytime/.test(m), catches = /rec|anytime/.test(m);' in kinds


def test_the_pinned_column_is_solid_wherever_it_is_drawn():
    i = GLCSS.index(".gl-table .gl-fix {")
    rule = GLCSS[i:GLCSS.index("}", i)]
    assert "position: sticky; left: 0;" in rule and "background: var(--gl-fix-bg);" in rule
    assert "--gl-fix-bg: linear-gradient(var(--panel), var(--panel)), var(--bg);" in rule, \
        "the panel over the page's own ground: opaque however see-through the panel is"
    i = GLCSS.index(".agate.gl-table tbody tr:hover td.gl-fix {")
    assert "background: var(--gl-fix-tint), var(--gl-fix-bg);" in GLCSS[i:GLCSS.index("}", i)], \
        "a tapped row's tint is laid over the solid column, never in its place (styles.css .agate tr:hover)"
    i = PLRCSS.index('html:not([data-theme="light"]) body.plr-on #view-players .gl-table .gl-fix {')
    assert ("--gl-fix-bg: linear-gradient(var(--panel), var(--panel)), color-mix(in oklab, var(--pw-1) 48%, var(--bg));"
            in PLRCSS[i:PLRCSS.index("}", i)]), "on the player page's glass, the club's colour in the ground"


def _history():
    """Sam LaPorta's targets (the route chart's own fixture) and six weeks of his lines."""
    import test_a_route_chart_for_every_receiver as RT
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = RT._conn_with_laporta(path)
    games, logs = [], []
    for wk, opp, home, rec, yds, tgt in ((1, "GB", 1, 5, 54, 7), (2, "CHI", 0, 6, 71, 8), (3, "TB", 1, 4, 38, 6),
                                         (4, "CAR", 0, 7, 88, 9), (5, "MIN", 1, 3, 29, 5), (6, "SEA", 0, 8, 102, 10)):
        per = f"{wk:03d}"
        h, a = ("DET", opp) if home else (opp, "DET")
        games.append(("nfl", 2026, per, f"{a}@{h}", h, a, 24, 20, f"2026-10-{wk + 3:02d}"))
        for m, v in (("receptions", rec), ("rec_yds", yds), ("targets", tgt), ("rec_td", 0), ("carries", 2),
                     ("rush_yds", 9), ("rush_td", 0), ("pass_att", 1), ("pass_cmp", 1), ("pass_yds", 7),
                     ("pass_td", 0), ("pass_int", 0)):
            logs.append(("nfl", 2026, per, f"DET-{per}", "Sam LaPorta", "DET", opp, "TE", home, m, v))
    conn.executemany("INSERT OR REPLACE INTO games (sport, season, period, game_id, home, away, home_score, away_score,"
                     " date) VALUES (?,?,?,?,?,?,?,?,?)", games)
    conn.executemany("INSERT OR REPLACE INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    conn.commit()
    conn.close()
    return path


def test_in_a_browser_the_overview_draws_the_route_chart_and_the_column_hides_what_scrolls_under_it():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    from engine import db as D
    import rendercheck
    keep = (D.DEFAULT_DB, D.connect.__defaults__)
    path = _history()
    D.DEFAULT_DB, D.connect.__defaults__ = path, (path,)
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          color_scheme="dark")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#player/sam-laporta", wait_until="load")
                page.wait_for_selector(".plr .plr-charts .cc-slot[data-on] .cc-inline", timeout=30000)
                got["slot"] = page.evaluate("Object.assign({}, document.querySelector('.plr-charts .cc-slot').dataset)")
                page.wait_for_selector(".plr-charts .cc-inline .cc-body svg, .plr-charts .cc-inline .cc-body canvas",
                                       timeout=30000)
                got["chart"] = page.locator(".plr-charts .cc-inline").inner_text()
                page.wait_for_selector(".plr-recent .rank-scroll td.gl-fix", timeout=30000)
                got["cell"] = page.evaluate("""(() => {
                  const sc = document.querySelector('.plr-recent .rank-scroll');
                  sc.scrollIntoView({ block: 'center', behavior: 'instant' }); sc.scrollLeft = 260;
                  const td = sc.querySelector('tbody td.gl-fix'), r = td.getBoundingClientRect();
                  const top = document.elementFromPoint(r.left + r.width - 4, r.top + r.height / 2);
                  const cs = getComputedStyle(td);
                  return { scrolled: sc.scrollLeft, mine: td.contains(top), color: cs.backgroundColor,
                           top: top ? `${top.tagName}.${top.className}|${(top.textContent || '').trim().slice(0, 20)}` : null,
                           rect: [r.left, r.top, r.width, r.height, innerHeight],
                           image: cs.backgroundImage };
                })()""")
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
        D.DEFAULT_DB, D.connect.__defaults__ = keep
    s = got["slot"]
    assert (s["cc"], s["lg"], s["mkt"], s["pos"]) == ("Sam LaPorta", "nfl", "rec_yds", "TE"), s
    assert "W5" in got["chart"] or "5-88" in got["chart"], got["chart"][:300]
    c = got["cell"]
    assert c["scrolled"] > 0 and c["mine"], c
    assert "linear-gradient" in c["image"], c
    # Opaque: the bottom colour has no alpha below 1.
    alpha = re.search(r"/\s*([0-9.]+)\)$|rgba\([^)]*,\s*([0-9.]+)\)$", c["color"])
    assert not alpha or float(alpha.group(1) or alpha.group(2)) >= 1.0, c["color"]
    assert not got["errs"], got["errs"]


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
