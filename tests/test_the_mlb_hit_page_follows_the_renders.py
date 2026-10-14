"""The MLB hit page, laid out to Ethan's four renders of it.

Ethan, 2026-10-14, with four renders of the page: "Also here is renders for
mlb hit page. Follow these." His season over his club's park (the logo, his
name with his position and number, the season to pick, five numbers), the
views as tabs, and: By game — his recent games with a window of 10, 20 or
30, the game's final, every at-bat as the renders' table with the pitch it
ended on and its speed, the pitches of each at-bat a tap away, the game's
summary and where its balls went over his season's; Where he hits it — the
park with every ball, the pull side, the middle and the other way as tiles
that filter it, and his season's numbers against any kind of pitch.

What is pinned, offline, on the hit tracker's own fixture games and
databases built here:

  * THE RECORD UNDER IT (engine/mlb/charts.hits_chart): every plate
    appearance carries the pitches he saw in it, in order, as
    ``[type, mph, call]`` and only his; his line has on base and OPS the
    league's way (walks, hit-by-pitches and sacrifice flies in the
    denominator, a bunt not); ``logged`` is the games the box scores have
    him batting in that season and ``sides`` the sides he batted from;
  * HIS POSITION AND NUMBER (engine/statlogs.roster_meta, engine/charts
    .answer): off his club's published roster and nothing else — a
    namesake on another club, or two men of one name with no club to tell
    them apart, is no answer, and a jersey 0 is a number; a chart that
    names his position keeps it;
  * THE FRAME HANDS A LEAGUE ITS WHOLE PAGE (js/carrychart.js): its own
    hero and views under the switch, its choices kept across redraws, a
    season picker, the side filter on the season's drawing too, and a
    table row with a line under it;
  * THE PAGE (js/chart-mlb.js): its own line is the server's, number for
    number; the at-bats table, the park with the wall's own distances and
    its thirds, the game's numbered balls over his season's, the season
    tiles with xBA and xSLG beside AVG and SLG, the Pitch view;
  * NOTHING THE RECORD DOES NOT HOLD: no runs scored, no stolen bases, no
    barrels, no club records on the day;
  * IN A BROWSER (opt-in, QB_BROWSER_TESTS=1): every control, at a phone's
    width, with no error and no sideways scroll.

Run directly: `python3 tests/test_the_mlb_hit_page_follows_the_renders.py`
"""
import importlib.util
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

from engine import charts as CH, db as D, statlogs as SL  # noqa: E402
from engine.mlb import charts as MC  # noqa: E402

_spec = importlib.util.spec_from_file_location("hit_fixture", ROOT / "tests" / "test_mlb_hit_tracker_and_pitch_chart.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")


def _game(pk, date, plays, home="NYY", away="KC"):
    return pk, MC.fold({"allPlays": plays}, {"game_pk": pk, "date": date, "home": home, "away": away, "type": "R"})


def _onbase_conn():
    """Judge in one game: a single, a walk, a hit-by-pitch, a sacrifice fly,
    a sacrifice bunt, a strikeout and a flyout."""
    conn = D.connect(":memory:")
    J, P = F.J, (600, "Seth Lugo")
    hit = {"launchSpeed": 99.0, "launchAngle": 12, "totalDistance": 240, "trajectory": "line_drive", "location": "8",
           "coordinates": {"coordX": 125.0, "coordY": 100.0}}
    fly = {"launchSpeed": 91.0, "launchAngle": 34, "totalDistance": 320, "trajectory": "fly_ball", "location": "9",
           "coordinates": {"coordX": 170.0, "coordY": 80.0}}
    plays = [F._play(0, "bottom", J, P, "Single", "single", [F._pitch(1, "D", hit=hit)]),
             F._play(1, "bottom", J, P, "Walk", "walk", [F._pitch(i + 1, "B", balls=i + 1, strikes=0) for i in range(4)]),
             F._play(2, "bottom", J, P, "Hit By Pitch", "hit_by_pitch", [F._pitch(1, "H")]),
             F._play(3, "bottom", J, P, "Sac Fly", "sac_fly", [F._pitch(1, "X", hit=fly)], rbi=1),
             F._play(4, "bottom", J, P, "Sac Bunt", "sac_bunt", [F._pitch(1, "X")]),
             F._play(5, "bottom", J, P, "Strikeout", "strikeout", [F._pitch(1, "C"), F._pitch(2, "S"), F._pitch(3, "S")]),
             F._play(6, "bottom", J, P, "Flyout", "field_out", [F._pitch(1, "X", hit=fly)])]
    _pk, (pas, pitches) = _game(775500, "2026-09-01", plays)
    D.upsert_mlb_pa(conn, pas)
    D.upsert_mlb_pitches(conn, pitches)
    return conn


# --- the record under it ------------------------------------------------------------------
def test_every_plate_appearance_carries_its_pitches_in_order_and_only_his():
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    hr, single = d["games"][0]["pas"]
    assert hr["ps"] == [["CH", 86.0, "B"], ["FF", 97.8, "X"]], hr["ps"]
    assert single["ps"] == [["FF", 96.0, "D"]]
    assert d["games"][1]["pas"][0]["ps"] == [["FF", 95.0, "X"]], "the earlier game's at-bat, its own pitch"
    soto = MC.hits_chart(F._conn(), "Juan Soto")
    assert [len(p["ps"]) for g in soto["games"] for p in g["pas"]] == [4], \
        "his walk's four balls; the caught stealing's pitch is no plate appearance of his"


def test_on_base_and_ops_the_leagues_way():
    L = MC.hits_chart(_onbase_conn(), "Aaron Judge")["season_line"]
    assert (L["pa"], L["ab"], L["h"], L["bb"], L["hbp"], L["sf"], L["k"]) == (7, 3, 1, 1, 1, 1, 1)
    # (1 hit + 1 walk + 1 hit by pitch) over (3 at-bats + 1 + 1 + 1 sac fly); the bunt is in neither.
    assert L["obp"] == 0.5 and L["slg"] == round(1 / 3, 3) and L["ops"] == round(0.5 + 1 / 3, 3)
    assert MC.hits_chart(F._conn(), "Juan Soto")["season_line"]["obp"] == 1.0, "a walk is on base with no at-bat"


def test_the_games_the_box_scores_have_and_the_sides_he_batted_from():
    conn = F._conn()
    rows = [("mlb", 2026, "2026-10-11", "g1", "Aaron Judge", "NYY", "DET", "", 1, "pa", 4.0),
            ("mlb", 2026, "2026-10-05", "g2", "Aaron Judge", "NYY", "KC", "", 1, "pa", 1.0),
            ("mlb", 2026, "2026-10-04", "g3", "Aaron Judge", "NYY", "KC", "", 1, "pa", 3.0),
            ("mlb", 2026, "2026-10-03", "g4", "Aaron Judge", "NYY", "KC", "", 1, "pa", 0.0),
            ("mlb", 2026, "2026-10-04", "g3", "Aaron Judge", "NYY", "KC", "", 1, "hits", 2.0),
            ("mlb", 2025, "2025-09-04", "g9", "Aaron Judge", "NYY", "KC", "", 1, "pa", 4.0)]
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    d = MC.hits_chart(conn, "Aaron Judge")
    assert d["logged"] == 3 and len(d["games"]) == 2, "three games batting this season, two of them charted"
    assert d["sides"] == ["R"] and MC.hits_chart(F._conn(), "Nobody") == {}
    assert MC.hits_chart(D.connect(":memory:"), "Aaron Judge") == {}
    # A switch-hitter bats from both sides.
    conn2 = D.connect(":memory:")
    plays = [F._play(0, "bottom", F.J, (600, "Seth Lugo"), "Single", "single", [F._pitch(1, "D")], side="L"),
             F._play(1, "bottom", F.J, (601, "Cole Ragans"), "Groundout", "field_out", [F._pitch(1, "X")], side="R", hand="L")]
    _pk, (pas, pitches) = _game(775600, "2026-09-02", plays)
    D.upsert_mlb_pa(conn2, pas)
    D.upsert_mlb_pitches(conn2, pitches)
    assert MC.hits_chart(conn2, "Aaron Judge")["sides"] == ["L", "R"]


# --- his position and number ------------------------------------------------------------
def _rosters():
    tmp = tempfile.mkdtemp()
    doc = {"teams": {"NYY": {"players": [{"player": "Aaron Judge", "position": "RF", "number": 99},
                                         {"player": "Will Smith", "position": "C", "number": "16"}]},
                     "LAD": {"players": [{"player": "Will Smith", "position": "C", "number": 16}]},
                     "KC": {"players": [{"player": "Willie Smith", "position": "P", "number": 0}]}}}
    Path(tmp, "rosters_mlb.json").write_text(json.dumps(doc))
    return tmp


def test_his_position_and_number_off_his_clubs_roster_only():
    d = _rosters()
    SL._ROSTER.clear()
    try:
        assert SL.roster_meta("mlb", "Aaron Judge", "NYY", data_dir=d) == {"position": "RF", "number": "99"}
        assert SL.roster_meta("mlb", "aaron  JUDGE", "", data_dir=d) == {"position": "RF", "number": "99"}, \
            "a name the league carries once, read the way search reads names"
        assert SL.roster_meta("mlb", "Aaron Judge", "BOS", data_dir=d) == {}, "another club's man is not him"
        assert SL.roster_meta("mlb", "Will Smith", "", data_dir=d) == {}, "two of one name and no club: no answer"
        assert SL.roster_meta("mlb", "Will Smith", "LAD", data_dir=d) == {"position": "C", "number": "16"}
        assert SL.roster_meta("mlb", "Willie Smith", "KC", data_dir=d) == {"position": "P", "number": "0"}, \
            "0 is a number a man wears"
        assert SL.roster_meta("nba", "Aaron Judge", "NYY", data_dir=d) == {}, "no roster on disk is no answer"
        assert SL.roster_meta("mlb", "", "NYY", data_dir=d) == {}
    finally:
        SL._ROSTER.clear()
        shutil.rmtree(d, ignore_errors=True)


def test_every_chart_answer_carries_them_and_a_chart_keeps_its_own():
    d = _rosters()
    keep_dir, keep_kind = SL.ROSTER_DIR, CH.KINDS["spray"]
    SL._ROSTER.clear()
    try:
        SL.ROSTER_DIR = d
        got = CH.answer(F._conn(), "spray", "mlb", "Aaron Judge")
        assert (got["position"], got["jersey"], got["kind"]) == ("RF", "99", "spray")
        CH.KINDS["spray"] = (("mlb",), lambda c, s, p, y: {"player": "Aaron Judge", "team": "NYY", "position": "DH"},
                             keep_kind[2])
        mine = CH.answer(F._conn(), "spray", "mlb", "Aaron Judge")
        assert (mine["position"], mine["jersey"]) == ("DH", "99"), "his chart's own position stands"
    finally:
        SL.ROSTER_DIR, CH.KINDS["spray"] = keep_dir, keep_kind
        SL._ROSTER.clear()
        shutil.rmtree(d, ignore_errors=True)


# --- the frame ------------------------------------------------------------------------------
def test_the_frame_hands_a_league_its_whole_page():
    i = CC_JS.index("  function render() {")
    body = CC_JS[i:CC_JS.index("\n  function settle(", i)]
    assert body.index("if (P && P.page)") < body.index("const items = poolOf(S.kind, g, d)"), \
        "the page is drawn before the frame's own parts are built"
    page = body[body.index("if (P && P.page)"):body.index("const items = poolOf")]
    for part in ("P.page({ d, g, sport, view: S.view, tabs, note", 'fold("note", "How it’s drawn", note)',
                 "return settle(box)"):
        assert part in page, part
    i = CC_JS.index("  function bind(ov) {")
    bind = CC_JS[i:CC_JS.index("\n  function ", i + 30)]
    for part in ('hit(e, "[data-opt][data-v]")', 'hit(e, "[data-tog]")', 'hit(e, "[data-season-pick]")',
                 "load(c, +sp.value)", 'hit(e, "select[data-opt]")', "S.opt = Object.assign({}, S.opt"):
        assert part in bind, part
    i = CC_JS.index("  function applySide() {")
    assert "Z && Z.season" in CC_JS[i:i + 1400], "a league's zones may filter its season's drawing"
    assert 'r.more ? `<span class="cc-c-more">${r.more}</span>`' in CC_JS
    for h in ("face: (d) => faceHTML(d, S)", "team: teamOf", "ink: inkOf", "seasonName,", "seg: (Z) =>",
              "tools: (items, flags, filters) =>", "stats: statsCard", "splits: splitsCard"):
        assert h in CC_JS, h


# --- the page ---------------------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{MLB_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_pages_own_line_is_the_servers():
    for d in (MC.hits_chart(F._conn(), "Aaron Judge"), MC.hits_chart(_onbase_conn(), "Aaron Judge"),
              MC.hits_chart(F._conn(), "Juan Soto")):
        got = _node(f"""
          const d = {json.dumps(d)}, X = T.DRAW.spray._t;
          return X.line([].concat(...d.games.map((g) => g.pas)));""")
        if got is None:
            return
        S = d["season_line"]
        for k in ("pa", "ab", "h", "tb", "hr", "bb", "k", "hbp", "sf", "rbi", "bip", "hard", "sweet"):
            assert got[k] == S[k], (k, got[k], S[k])
        for k in ("avg", "obp", "slg", "ops"):
            assert (got[k] is None and S[k] is None) or round(got[k], 3) == S[k], (k, got[k], S[k])
        assert (got["ev"] is None and S["ev"] is None) or round(got["ev"], 1) == S["ev"]
        assert (got["max"] or None) == S["max_ev"]


def test_the_page_draws_the_renders():
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    got = _node(f"""
      const d = {json.dumps(d)}, SP = T.DRAW.spray, X = SP._t, g = d.games[0];
      return {{
        list: SP.list(g, d), tiles: SP.gameSide(g, d), side: SP.seasonSide(d), game: SP.game(g, d),
        season: SP.season(d), views: SP.views(d), pitch: SP.bars(d, "pitch"), csv: SP.csv(g, d)[0],
        walls: [-45, -22.5, 0, 22.5, 45].map((a) => Math.round(X.wallFt(a))),
        words: g.pas.map(X.result), nth: [1, 2, 3, 4, 11, 12, 13, 21, 22].map(X.nth),
        hrNoFielder: X.result({{ et: "home_run", ev: "Home Run", x: 190, y: 60 }}),
        seen: X.pitchesSeen(d).map(([t, o]) => [t, o.seen, o.pa]),
      }};""")
    if got is None:
        return
    # The at-bats: the pitch it ended on and its speed, what it became and where, how hard, how far.
    for part in (">Four-seam<", ">98<", ">96<", ">Home Run (LF)<", ">Single (RF)<", ">110<", ">431 ft<", "1 RBI"):
        assert part in got["list"], part
    assert got["words"] == ["Home Run (LF)", "Single (RF)"] and got["hrNoFielder"] == "Home Run (RF)"
    assert got["nth"] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]
    # The game's numbers, its home run lit.
    assert ">2-2<" in got["tiles"] and "Total bases" in got["tiles"] and 'class="cc-tile hot"' in got["tiles"]
    # The park: the wall's own distances on it, the thirds' shares, the season's balls in their zones.
    assert got["walls"] == [330, 375, 400, 375, 330]
    for ft in (">330<", ">375<", ">400<"):
        assert ft in got["season"], ft
    assert "Pulled" in got["season"] and "Opposite field" in got["season"] and "Up the middle" in got["season"]
    assert 'data-z="pull"' in got["season"] and 'data-z="oppo"' in got["season"]
    assert len(re.findall(r'class="mb-ball mb-dot ', got["season"])) == 3
    # A game's drawing: its balls numbered as the table numbers them, over his season's, faint.
    assert len(re.findall(r'class="mb-num"', got["game"])) == 2 and "mb-dot h faint" in got["game"]
    assert len(re.findall(r'class="mb-ball cx-mark', got["game"])) == 2
    # The season's tiles: xBA and xSLG (when there are any) beside his own; launch angle; OPS.
    for part in (">OPS<", "Launch angle", "Exit velocity", "Sweet spot", "% of PA", "OBP"):
        assert part in got["side"], part
    assert [v[0] for v in got["views"]] == ["type", "dir", "pitch"] and got["views"][2][1] == "Pitch"
    assert "Every pitch he saw, by kind" in got["pitch"] and "Four-seam" in got["pitch"]
    assert "Against right- and left-handers" in got["pitch"]
    assert dict((t, (n, pa)) for t, n, pa in got["seen"]) == {"FF": (3, 3), "CH": (1, 0)}, \
        "four pitches seen in three at-bats, each ended on a four-seamer"
    assert "Pitch" in got["csv"] and "Every pitch" in got["csv"]


def test_nothing_the_record_does_not_hold():
    tiles = re.findall(r'tile\("([^"]+)"', MLB_JS)
    for label in tiles:
        assert not re.match(r"^(R|SB|Runs|Stolen bases|Barrels?|Barrel %)$", label), label
    assert "Barrel" not in "".join(re.findall(r'\["[^"]*", "([^"]*)"\]', MLB_JS)), "no barrel view"
    page = MLB_JS[MLB_JS.index("function gameCard("):MLB_JS.index("const AB_COLS")]
    assert ".rec" not in page and "orec" not in page, "a club's record on the day is not printed"
    note = MLB_JS[MLB_JS.index("note: (d) =>"):MLB_JS.index("// The page's own arithmetic")]
    assert "Runs scored, stolen bases and barrels are not shown" in note
    assert "The wall is the drawing’s, not his park’s" in note


def test_the_styles_are_tokens_and_the_handlers_are_listeners():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    for sel in (".mb-hero-in", ".mb-hero-tiles", ".mb-pick select", ".mb-chips .cc-chip.mb-chip", ".mb-board",
                ".cc-tile.hot", ".mb-seq", ".mb-pc.w", ".mb-park .venue-photo", ".mb-zones .mb-zbar i", ".mb-split",
                ".mb-hero ~ .cc-tabs .cc-tab", ".cc-c-more"):
        assert sel in CC_CSS, sel
    assert ".mb-form" not in CC_CSS, "the My Bets form's class is the site's, not the hit page's"
    assert "onclick" not in MLB_JS and "onerror" not in MLB_JS and not re.search(r"on(error|load)\s*=", MLB_JS)


# --- the browser, opt-in --------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i>${{a}}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.fetch = async (q) => ({{ ok: true, json: async () => (String(q).includes("season=2025") ? window.OLD : window.CHART) }});
</script>
<script>{js}</script></body></html>"""


def test_in_a_browser_every_control_of_the_hit_page_works():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    d.update(seasons=[2026, 2025], position="RF", jersey="99", kind="spray", face="")
    old = json.loads(json.dumps(d))
    old.update(season=2025)
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(PAGE.format(css=CC_CSS, js=CC_JS + "\n" + MLB_JS))
            page.evaluate("([c, o]) => { window.CHART = c; window.OLD = o; window.QBCarry.open('Aaron Judge', 'mlb', 'spray'); }", [d, old])
            page.wait_for_selector("#cc-overlay .mb-hero", timeout=5000)
            hero = page.evaluate("document.querySelector('.mb-hero').textContent.replace(/\\s+/g, ' ')")
            assert "Aaron" in hero and "Judge" in hero and "RF  #99" in page.evaluate(
                "document.querySelector('.mb-hero-who span').textContent") and "2026 season" in hero
            assert page.evaluate("[...document.querySelectorAll('.cc-tab')].map((t) => t.textContent)") == \
                ["By game", "Where he hits it", "Batted ball", "Direction", "Pitch"]
            # By game: two chips, the at-bats, a tap on one lights its ball and its words.
            assert page.evaluate("document.querySelectorAll('.mb-chip').length") == 2
            assert page.evaluate("document.querySelectorAll('.cc-g-ab .cc-row').length") == 2
            page.click(".cc-g-ab .cc-row[data-i='0']")
            assert "Home Run (LF)" in page.evaluate("document.querySelector('.cc-tip').textContent")
            assert page.evaluate("document.querySelector('.mb-ball.cx-mark.sel') !== null")
            page.click("[data-tog='pbk']")
            assert page.evaluate("document.querySelectorAll('.mb-seq').length") == 2
            assert page.evaluate("document.querySelectorAll('.mb-seq .mb-pc').length") == 3
            page.click("[data-tog='pbk']")
            assert page.evaluate("document.querySelectorAll('.mb-seq').length") == 0
            page.click(".cc-chip[data-gi='1']")
            assert page.evaluate("document.querySelectorAll('.cc-g-ab .cc-row').length") == 1
            # Where he hits it: the thirds filter the season's drawing.
            page.click("[data-view='season']")
            page.wait_for_selector(".mb-park-svg", timeout=3000)
            page.click(".cc-seg [data-side='pull']")
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry.off').length") == 1, "the single to right fades"
            assert page.evaluate("document.querySelector('.mb-z.pull').classList.contains('on')")
            page.select_option("select[data-opt='vs']", "L")
            assert "His 2 plate appearances vs left-handers." in page.evaluate("document.querySelector('.mb-stats').textContent")
            assert page.evaluate("document.querySelector('select[data-opt=\"vs\"]').value") == "L", "kept across the redraw"
            page.click("[data-view='pitch']")
            assert "Every pitch he saw, by kind" in page.evaluate("document.querySelector('.cc-dist').textContent")
            # The season picker asks for that season.
            page.select_option("[data-season-pick]", "2025")
            page.wait_for_function("document.querySelector('.mb-hero').textContent.includes('2025 season')", timeout=3000)
            assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
            assert page.evaluate("(() => { const c = document.querySelector('#cc-overlay .cc'); return c.scrollWidth - c.clientWidth; })()") == 0
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
