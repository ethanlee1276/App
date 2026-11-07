"""Every player chart in the frame of Ethan's two renders.

Ethan, 2026-10-14, with two renders of the carry and route chart pages:
"I like how it has the stadium art behind the team logos. And I like how
much better the charts and shit look in this page look. So follow these
renders for how our pages should look." Pinned here:

  * THE FINAL AND THE RECORDS come off the games table and nothing else
    (engine/carries.scoreboard): his team's score first; in the NFL both
    teams' records through the game, regular season only, so a playoff
    game carries the season's record; a game with no final shows none,
    and a college game never shows a record (the college table keeps the
    FBS games only, so a record could be short a game). Every football
    chart builder adds them;
  * THE GAME OVER ITS STADIUM: his team on the left, the opponent on the
    right, each in its own colour — a colour only as the team data spells
    one — the home team's building behind, "VS"/"AT" before a final, the
    season's count in the season view, nothing for a chart with no team;
  * WHICH SIDE OF THE FIELD: a run's hole as the play-by-play splits it,
    a target's or a throw's third, and the counts under the field;
  * EVERY PLAY AS A TABLE: a row per play that still reads the whole play
    in words (its label), a result that never says more than the file
    does ("Gain", not "Tackle"), the filter's tokens, and the spreadsheet;
  * THE ROUTE CHART'S OTHER VIEWS: Route type and Coverage only for a
    season the league charted, Depth for every NFL season, none in college;
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): the real module in
    Chromium — the side filter fades the other sides, the table's filter
    hides rows, the "i" opens the note, the arrows step through the games,
    the download is the game's plays, and a phone never scrolls sideways.

    QB_BROWSER_TESTS=1 python3 tests/test_the_chart_page_follows_ethans_renders.py
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

from engine import carries as CR, db as D                # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")

# (week, opponent, his team at home?, kickoff day, hole of each run)
ALLEN_GAMES = ((1, "ARI", False, "2026-09-13", ("LE", "RT")),
               (5, "ATL", True, "2026-10-12", ("LE", "LT", "M", "RE")),
               (19, "KC", True, "2027-01-10", ("RG",)))
LOC = {"LE": ("left", "end"), "LT": ("left", "tackle"), "M": ("middle", "NA"), "RG": ("right", "guard"),
       "RT": ("right", "tackle"), "RE": ("right", "end")}
FINALS = [  # week, away, home, away score, home score
    (1, "BUF", "ARI", 27, 20), (1, "ATL", "TB", 24, 17), (2, "BUF", "NYJ", 24, 24),
    (3, "MIA", "BUF", 31, 13), (3, "CAR", "ATL", 10, 27), (5, "ATL", "BUF", 20, 27),
    (19, "KC", "BUF", 3, 30), (6, "BUF", "NE", None, None)]


def _allen_conn():
    conn = D.connect(":memory:")
    runs = CR.NflCarries(2026)
    for wk, opp, home, date, holes in ALLEN_GAMES:
        for i, h in enumerate(holes):
            loc, gap = LOC[h]
            runs.add({"season": "2026", "season_type": "REG" if wk <= 18 else "POST", "week": str(wk),
                      "home_team": "BUF" if home else opp, "away_team": opp if home else "BUF",
                      "posteam": "BUF", "defteam": opp, "game_date": date, "two_point_attempt": "0",
                      "play_type": "run", "rusher_player_id": "00-0034857", "rusher_player_name": "J.Allen",
                      "rushing_yards": str(3 + i * 4), "yards_gained": str(3 + i * 4), "run_location": loc,
                      "run_gap": gap, "qb_scramble": "0", "fumble_lost": "0", "rush_touchdown": "0",
                      "first_down_rush": "1" if i == 2 else "0", "down": "1", "ydstogo": "10",
                      "yardline_100": str(60 - i * 5), "qtr": str(1 + i), "quarter_seconds_remaining": "600",
                      "play_id": str(100 + i)})
    D.upsert_carries(conn, runs.rows({"00-0034857": {"name": "Josh Allen", "position": "QB", "jersey": "17"}}))
    D.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": f"{w:03d}", "game_id": f"{a}@{h}",
                           "home": h, "away": a, "away_score": as_, "home_score": hs}
                          for w, a, h, as_, hs in FINALS])
    return conn


# --- the final and the records ---------------------------------------------
def test_the_final_and_both_records_come_off_the_games_table():
    c = CR.chart(_allen_conn(), "nfl", "Josh Allen")
    by_week = {g["week"]: g for g in c["games"]}
    w1, w5, w19 = by_week[1], by_week[5], by_week[19]
    assert w1["score"] == [27.0, 20.0], "his team's score first, away or home"
    assert (w1["rec"], w1["orec"]) == ("1-0", "0-1")
    assert w5["score"] == [27.0, 20.0] and (w5["rec"], w5["orec"]) == ("2-1-1", "2-1"), \
        "a tie is the third number; the records are through this game"
    assert w19["score"] == [30.0, 3.0] and w19["rec"] == "2-1-1", "a playoff game carries the regular season's record"
    assert w19["orec"] == "", "a team with no regular-season final on file has no record, not 0-0"


def test_a_game_with_no_final_and_a_college_game_say_only_what_the_table_holds():
    conn = _allen_conn()
    games = [{"period": "006", "team": "BUF", "opp": "NE", "home": False}]
    assert CR.scoreboard(conn, "nfl", 2026, games) == [{"period": "006", "team": "BUF", "opp": "NE", "home": False}]
    D.upsert_games(conn, [{"sport": "cfb", "season": 2026, "period": "2026-09-06", "game_id": "UGA@ALA",
                           "home": "ALA", "away": "UGA", "away_score": 24, "home_score": 31}])
    cfb = CR.scoreboard(conn, "cfb", 2026, [{"period": "2026-09-06", "team": "UGA", "opp": "ALA", "home": False}])
    assert cfb[0]["score"] == [24.0, 31.0] and "rec" not in cfb[0] and "orec" not in cfb[0], \
        "college: the final, never a record the FBS-only table could have short"
    assert CR.scoreboard(conn, "mlb", 2026, [{"period": "x"}]) == [{"period": "x"}]


def test_every_football_chart_builder_adds_them():
    for name, call in (("carries", "scoreboard(conn, sport, pick, out_games)"),
                       ("targets", "scoreboard(conn, sport, pick, out_games)"),
                       ("passes", 'scoreboard(conn, "nfl", pick, out_games)'),
                       ("kicks", 'scoreboard(conn, "nfl", pick, out_games)')):
        src = (ROOT / "engine" / f"{name}.py").read_text(encoding="utf-8")
        i = src.index("\ndef chart(")
        j = src.find("\ndef ", i + 10)
        assert call in src[i:j if j > 0 else len(src)], name


# --- the page ----------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a, px) => `<i class="mark" data-px="${px}">${a}</i>`;
      const teamNameIn = (lg, a) => a;
      const lockScroll = () => {};
      const window = {};
      const TEAMS = { BUF: { name: "Buffalo Bills", nick: "Bills", loc: "Buffalo", primary: "#00338d" },
                      ATL: { name: "Atlanta Falcons", nick: "Falcons", loc: "Atlanta", primary: "#a71930" },
                      BAD: { name: "Bad Team", nick: "Bad", primary: "red;background:url(x)" } };
      const teamsIn = () => TEAMS;
      const venuePhotoTag = (sport, home) => `<img class="venue-photo" data-home="${home}">`;
    """
    prog = f"{stubs}\n{CC_JS}\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_game_over_its_stadium():
    got = _node("""
      const g = { week: 5, date: "2026-10-12", opp: "ATL", home: true, team: "BUF", score: [27, 20], rec: "4-1", orec: "2-3" };
      const away = { week: 6, date: "2026-10-19", opp: "ATL", home: false, team: "BUF" };
      const d = { team: "BUF", season: 2026, games: [g, away], sport: "nfl" };
      return { hero: T.heroHTML(g, d, "nfl", ["", ""]), away: T.heroHTML(away, d, "nfl", ["", ""]),
               season: T.heroHTML(null, d, "nfl", ["70", "carries"]),
               bad: T.heroHTML(Object.assign({}, g, { opp: "BAD" }), d, "nfl", ["", ""]),
               none: T.heroHTML(Object.assign({}, g, { team: "" }), Object.assign({}, d, { team: "" }), "ufc", ["", ""]) };""")
    if got is None:
        print("      (skipped: no node)")
        return
    h = got["hero"]
    assert "--ta:#00338d" in h and "--tb:#a71930" in h, "each side over its own team's colour"
    assert 'data-home="BUF"' in h, "the home team's building behind"
    for want in (">Buffalo<", ">Bills<", ">4-1<", ">Atlanta<", ">Falcons<", ">2-3<", "<em>27</em>", "<em>20</em>",
                 "Final · W", ">Week 5<", "Oct 12, 2026"):
        assert want in h, want
    assert h.index(">Bills<") < h.index(">Falcons<"), "his team on the left"
    assert 'data-home="ATL"' in got["away"] and ">AT<" in got["away"] and "Final" not in got["away"], \
        "away and no final on file: their building, AT, no score"
    s = got["season"]
    assert "Season" in s and ">70<" in s and ">carries<" in s and ">2026<" in s and "2 games" in s
    assert "red;background" not in got["bad"] and "--tb" not in got["bad"], "a colour only as the team data spells one"
    assert got["none"] == "", "no team to draw: the chart keeps its title"


def test_which_side_of_the_field_and_its_counts():
    got = _node("""
      const cs = ["LE", "LT", "M", "RG", ""].map((h) => ({ h, y: 3, band: "short" }));
      return { sides: T.sidesHTML("carries", cs, T.kindOf("carries", "nfl"), true),
               still: T.sidesHTML("carries", cs, T.kindOf("carries", "nfl"), false),
               none: T.sidesHTML("carries", [{ h: "" }], T.kindOf("carries", "cfb"), true),
               passes: T.sidesHTML("passes", [{ k: "pass", s: "L" }, { k: "sack", s: "" }, { k: "pass", s: "R" }],
                                   T.kindOf("passes", "nfl"), true),
               of: [T.sideOf("carries", { h: "LG" }), T.sideOf("carries", { h: "" }), T.sideOf("routes", { s: "R" }),
                    T.sideOf("passes", { k: "sack", s: "L" }), T.sideOf("passes", { k: "pass", s: "M" })] };""")
    if got is None:
        return
    s = got["sides"]
    assert "<b>2 <small>carries</small></b><i>40%</i>" in s, "LE and LT: the left, two of five"
    assert "<b>1 <small>carry</small></b><i>20%</i>" in s
    assert 'data-side="L"' in s and 'data-side="R"' in s, "a game's counts are buttons that filter"
    assert "data-side" not in got["still"], "the season's counts only count"
    assert got["none"] == "", "no side on file: no counts"
    assert "<b>1 <small>throw</small></b><i>50%</i>" in got["passes"], "a sack is not a throw to a side"
    assert got["of"] == ["L", "", "R", "", "M"]


def test_every_play_as_a_table_that_says_no_more_than_the_file():
    got = _node("""
      const g = { opp: "LA", team: "BUF", home: false, carries: [
        { q: 4, clk: "2:00", dn: 1, ds: 10, yl: 26, y: 12, h: "LE", sc: false, td: false, fl: false, fd: true, band: "gain" },
        { q: 1, clk: "9:00", dn: 2, ds: 5, yl: 70, y: -2, h: "", sc: true, td: false, fl: false, fd: false, band: "loss" }] };
      const t = { opp: "LA", team: "BUF", home: false, targets: [
        { q: 1, clk: "1:00", dn: 1, ds: 10, yl: 60, ay: 8, s: "R", c: true, yac: 3, y: 11, td: false, int: false, fd: true,
          rt: "", cov: "", sh: "", fl: [] }] };
      const college = { opp: "UGA", team: "ALA", home: true, targets: [{ q: 2, dn: 3, ds: 2, yl: 4, c: false, y: 0 }] };
      return { list: T.listHTML(g, "nfl"), routes: T.routeList(t), college: T.routeList(college),
               results: [{ td: true, y: 5 }, { fl: true, y: 2 }, { fd: true, y: 11 }, { y: -3 }, { y: 0 }, { y: 4 }]
                 .map((c) => T.carryResult(c, "nfl").map((x) => x.join(":"))),
               cfbFumble: T.carryResult({ fl: true, y: 1 }, "cfb")[0][0],
               flags: [T.carryFlags({ y: 7, fd: true, sc: true }), T.targetFlags({ c: true, td: true }),
                       T.targetFlags({ c: false }), T.targetFlags({ c: false, int: true })],
               desc: T.descOf("carries", "nfl") };""")
    if got is None:
        return
    lst = got["list"]
    assert len(re.findall(r'class="cc-row cc-tr', lst)) == 2 and ">Yard line<" in lst
    assert 'data-f="big fd"' in lst and 'data-f="loss sc"' in lst
    assert 'aria-label="Q4 2:00, 1st &amp; 10 · LA 26, Left end, +12 yds, 1st down"' in lst, \
        "the row reads the whole play in words"
    assert "Hole not recorded" in lst and ">Scramble<" in lst
    assert got["results"] == [["Touchdown:good"], ["Fumble lost:bad"], ["1st down:gold"], ["Loss:bad"],
                              ["No gain:mute"], ["Gain:mute"]], "never 'tackle': the file does not say"
    assert got["cfbFumble"] == "Fumbled", "college does not say who recovered it"
    assert got["flags"] == ["big fd sc", "c fd td", "inc", "int"]
    r = got["routes"]
    assert ">Right<" in r and ">Depth<" in r and ">8<" in r and ">+11<" in r and ">1st down<" in r
    assert ">Depth<" not in got["college"] and "Goal line" in got["college"] and ">Inc<" in got["college"], \
        "a college target has no depth or side on file"
    assert got["desc"] == "every run he made: the hole, how far it went, and where on the field"


def test_the_spreadsheet_is_the_games_plays():
    got = _node("""
      const g = { opp: "LA", team: "BUF", home: false, carries: [
        { q: 4, clk: "2:00", dn: 1, ds: 10, yl: 26, y: 12, h: "LE", sc: false, td: false, fl: false, fd: true }] };
      const t = { opp: "LA", team: "BUF", home: false, targets: [
        { q: 1, clk: "1:00", dn: 1, ds: 10, yl: 60, ay: 8, s: "R", c: true, yac: 3, y: 11, td: false, int: false, fd: true,
          rt: "SLANT", cov: "zone", sh: "Cover 3, robber" }] };
      return { car: T.csvOf("carries", g).split("\\r\\n"), tgt: T.csvOf("routes", t).split("\\r\\n") };""")
    if got is None:
        return
    assert got["car"][0].startswith("#,Quarter,Clock,Down,To go,Yard line,Hole,Yards")
    assert got["car"][1] == "1,4,2:00,1,10,LA 26,Left end,12,0,0,1,0"
    assert got["tgt"][1] == '1,1,1:00,1,10,BUF 40,Slant,8,right,1,11,3,0,0,1,zone,"Cover 3, robber"', \
        "a comma in a value is quoted"


def test_the_route_charts_other_views_follow_the_leagues_charting():
    got = _node("""
      const z = [{ depth: "short", side: "L", tgt: 3, rec: 2, yds: 20, td: 0, yac: 5 },
                 { depth: "short", side: "R", tgt: 1, rec: 1, yds: 8, td: 1, yac: 2 },
                 { depth: "deep", side: "M", tgt: 1, rec: 0, yds: 0, td: 0, yac: 0 }];
      return { views: [T.routeViews({ air: true, by_route: [], by_cov: [], by_shell: [] }),
                       T.routeViews({ air: true, by_route: [{}], by_cov: [{}], by_shell: [] }),
                       T.routeViews({ air: false })].map((v) => v.map((x) => x[0]).join(",")),
               depth: T.routeBars({ by_zone: z, season_line: { tgt: 5 } }, "depth"),
               cov: T.routeBars({ by_cov: [{ coverage: "man", tgt: 2, rec: 1, ypt: 4 }],
                                  by_shell: [{ shell: "Cover 1", tgt: 2, rec: 1, ypt: 4 }] }, "cov") };""")
    if got is None:
        return
    assert got["views"] == ["depth", "route,depth,cov", ""], "routes and coverage only where the league charted them"
    d = got["depth"]
    assert ">0–9 yards<" in d and '<b class="cc-bv">4<small>80%</small></b>' in d and "3/4 caught" in d and "1 TD" in d
    assert ">20+ yards<" in d and "Behind the line" not in d, "a depth he was never thrown at has no bar"
    assert "Man or zone" in got["cov"] and "Coverage shell" in got["cov"] and ">Cover 1<" in got["cov"]


def test_the_frame_and_its_styles():
    i = CC_JS.index("  function render() {")
    body = CC_JS[i:CC_JS.index("\n  function applySide()", i)]
    for part in ("heroHTML(g, d, sport,", "gamesRow(d, sport,", "distCard(K,", "sidesHTML(S.kind,", "statsCard(",
                 "playsCard(\"Every carry\"", "playsCard(\"Every target\"", "toolsHTML(\"carries\"", "routeViews(d)"):
        assert part in body, part
    assert 'data-step="-1"' in CC_JS and 'data-step="1"' in CC_JS
    i = CC_JS.index("  function bind(ov) {")
    bind = CC_JS[i:CC_JS.index("\n  }\n", i)]
    for sel in ('"[data-step]"', '"[data-side]"', '"[data-info]"', '"[data-dl]"', 'addEventListener("change"',
                '"[data-filt]"'):
        assert sel in bind, sel
    assert "const HEX = /^#[0-9a-fA-F]{3,8}$/;" in CC_JS, "a team colour reaches a style only as a hex code"
    assert "onclick" not in CC_JS and "onerror" not in CC_JS and not re.search(r"on(error|load)\s*=", CC_JS)
    for sel in (".cc-hero {", ".cc-hero::before", ".cc-hero-in", ".cc-car {", ".cc-step {", ".cc-seg {", ".cc-sides {",
                ".cc-card {", ".cc-pill.good", ".cc-tiles-7", ".cc-row[hidden] { display: none; }", ".cc-carry.off",
                ".cc-halo", ".rc-halo", ".cc-bars", "@container (min-width: 560px)"):
        assert sel in CC_CSS, sel
    i = CC_CSS.index("@media (prefers-reduced-motion: reduce)")
    assert ".cc-halo" in CC_CSS[i:i + 200] and ".rc-halo" in CC_CSS[i:i + 200], "the glow never animates for a reader who asked"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


# --- the browser, opt-in --------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i>${{a}}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.fetch = async (q) => ({{ ok: true, json: async () => window.CHART }});
</script>
<script>{js}</script></body></html>"""


def test_in_a_browser_every_control_works_and_a_phone_never_scrolls_sideways():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    chart = CR.chart(_allen_conn(), "nfl", "Josh Allen")
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(PAGE.format(css=CC_CSS, js=CC_JS))
            page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Josh Allen', 'nfl', 'carries'); }", chart)
            page.wait_for_selector("#cc-overlay .cc-stage svg", timeout=5000)
            # Newest first: the wild card game has one run, through the right guard.
            page.click("#cc-overlay [data-step='1']")
            assert page.evaluate("document.querySelector('.cc-games .cc-chip.on').dataset.gi") == "1"
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry').length") == 4, "week 5's four runs"
            page.click(".cc-seg [data-side='L']")
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry.off').length") == 2, \
                "LE and LT stay; the middle and the right end fade"
            assert page.evaluate("document.querySelector('.cc-sd.on').dataset.sd") == "L"
            page.select_option("[data-filt]", "fd")
            assert page.evaluate("[...document.querySelectorAll('.cc-row[data-f]')].filter((r) => !r.hidden).length") == 1
            page.click("[data-info]")
            assert page.evaluate("!document.querySelector('.cc-pop').hidden")
            with page.expect_download() as dl:
                page.click("[data-dl]")
            assert dl.value.suggested_filename == "josh-allen-carries-2026-w5-vs-atl.csv"
            lines = Path(dl.value.path()).read_text(encoding="utf-8").splitlines()
            assert len(lines) == 5 and lines[1].split(",")[6] == "Left end"
            assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
            assert page.evaluate("(() => { const c = document.querySelector('#cc-overlay .cc'); return c.scrollWidth - c.clientWidth; })()") == 0
            page.click("[data-view='season']")
            assert page.evaluate("!!document.querySelector('.cc-hero.season')"), "the season over his team's building"
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
