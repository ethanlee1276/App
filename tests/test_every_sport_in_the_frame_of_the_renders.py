"""Every other sport's chart in the frame of Ethan's two NFL renders.

Ethan, 2026-10-14, after the carry and route pages took his renders:
"Now I need you to take those renders ... and go match it with all the
other sports too, but obviously make sense and correlate it with that
sport. ... we want all these pages to be matching between sports. So it
all looks the same in like one put together professional app". Pinned
here:

  * THE DAILY LEAGUES' FINALS come off the games table and nothing else
    (engine/carries._daily_finals): the row for that day between those two
    teams, his team's score first whichever side was home, never a record
    (a daily league's table is filled night by night), and a doubleheader
    told apart only by the leg the game names. Every daily chart builder
    and the role chart read them;
  * EVERY LEAGUE'S OWN THIRDS, as the render's Left | Middle | Right: a
    shooter's paint, mid-range and threes (a free throw in none), a
    hitter's pull side, middle and opposite field, a pitcher's fastballs,
    breaking balls and offspeed, a skater's slot, high slot and point, a
    kicker's distances — each with its filter and its counts;
  * EVERY PLAY AS THE RENDERS' TABLE in every league (carrychart.js
    gridHTML): a row per play that reads the whole play in its label, the
    filter's tokens, the phone's and the wide card's columns, and the
    spreadsheet;
  * THE OTHER VIEWS as the route chart's Route type | Depth | Coverage:
    bars by each league's own splits, a rate set beside the league's in a
    pill;
  * THE HEROES: a fight over the arena with the result between the two
    fighters, tonight's matchup over both teams' colours;
  * EVERY TILE WEARS ITS ICON, and a name a narrow card would cut is
    fitted rather than cut;
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): the real modules in
    Chromium — a shooter's paint filter fades the rest of the floor, the
    table's filter hides rows, the download is the game's shots, a
    pitcher's fastball filter fades his other pitches, and a phone never
    scrolls sideways.

    QB_BROWSER_TESTS=1 python3 tests/test_every_sport_in_the_frame_of_the_renders.py
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

WEB = ROOT / "web"
CC_JS = (WEB / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (WEB / "css" / "carrychart.css").read_text(encoding="utf-8")
PLUGS = {f: (WEB / "js" / f"chart-{f}.js").read_text(encoding="utf-8")
         for f in ("hoops", "mlb", "nhl", "kicks", "role", "ufc", "matchup")}

# --- a guard's game: four shots from the floor and a free throw ----------------------
SHOTS = {
    "player": "Nikola Jokic", "sport": "nba", "seasons": [2025], "season": 2025, "season_label": "2025-26",
    "team": "DEN",
    "games": [{"id": "g1", "date": "2025-11-02", "opp": "NYK", "home": True, "team": "DEN", "score": [112.0, 104.0],
               "line": {"pts": 10, "fgm": 2, "fga": 4, "fg_pct": 0.5, "fg3m": 1, "fg3a": 1, "fg3_pct": 1.0, "ftm": 1,
                        "fta": 1, "ft_pct": 1.0, "assisted": 1, "paint": 2},
               "box": {"min": 34, "reb": 12, "ast": 9, "stl": 1, "blk": 1, "tov": 2},
               "shots": [
                   {"i": 1, "x": 0, "y": 5, "m": 1, "k": "2pt", "d": 2, "t": "Layup", "ds": "driving", "p": 1,
                    "c": "11:30", "a": "J. Murray", "b": 0, "z": "ra", "q": ""},
                   {"i": 2, "x": 120, "y": 150, "m": 0, "k": "2pt", "d": 18, "t": "Jump Shot", "ds": "", "p": 2,
                    "c": "3:05", "a": "", "b": 1, "z": "mid", "q": ""},
                   {"i": 3, "x": -220, "y": 20, "m": 1, "k": "3pt", "d": 23, "t": "Jump Shot", "ds": "", "p": 3,
                    "c": "7:04", "a": "", "b": 0, "z": "corner3", "q": "fastbreak"},
                   {"i": 4, "x": None, "y": None, "m": 1, "k": "ft", "d": None, "t": "1 of 1", "ds": "", "p": 3,
                    "c": "7:04", "a": "", "b": 0, "z": "", "q": ""},
                   {"i": 5, "x": 40, "y": 90, "m": 0, "k": "2pt", "d": 10, "t": "Hook", "ds": "", "p": 4,
                    "c": "1:00", "a": "", "b": 0, "z": "paint", "q": ""}]}],
    "season_line": {"games": 1, "ppg": 10.0, "fg_pct": 0.5, "fga_pg": 4.0, "fg3_pct": 1.0, "fg3a_pg": 1.0,
                    "ft_pct": 1.0, "ftm": 1, "fta": 1, "fgm": 2, "fga": 4, "assisted": 1},
    "zones": [{"key": "ra", "name": "Restricted area", "fga": 1, "fgm": 1, "pct": 1.0, "share": 0.25, "league": 0.64},
              {"key": "paint", "name": "In the paint", "fga": 1, "fgm": 0, "pct": 0.0, "share": 0.25, "league": 0.42},
              {"key": "mid", "name": "Mid-range", "fga": 1, "fgm": 0, "pct": 0.0, "share": 0.25, "league": 0.41},
              {"key": "corner3", "name": "Corner 3", "fga": 1, "fgm": 1, "pct": 1.0, "share": 0.25, "league": 0.39},
              {"key": "above3", "name": "Above the break 3", "fga": 0, "fgm": 0, "pct": None, "share": 0.0,
               "league": 0.35}],
    "by_type": [{"name": "Jump Shot", "fga": 2, "fgm": 1, "pct": 0.5}, {"name": "Layup", "fga": 1, "fgm": 1, "pct": 1.0}],
    "by_period": [], "by_dist": [{"name": "0-4 ft", "fga": 1, "fgm": 1, "pct": 1.0}],
}
# --- a pitcher's start: a fastball, a slider and a changeup to one batter ---------------
PITCHES = {
    "player": "Tarik Skubal", "sport": "mlb", "seasons": [2026], "season": 2026, "team": "DET", "hand": "L",
    "games": [{"id": 1, "date": "2026-09-03", "opp": "NYY", "home": True, "team": "DET",
               "line": {"pitches": 3, "k": 1, "bb": 0, "h": 0, "whiffs": 1, "csw": 0.667},
               "mix": [{"type": "FF", "n": 1, "share": 0.33, "velo": 97.0, "whiff": 0.0, "csw": 1.0}],
               "p": [["FF", 97.1, 0.1, 2.5, "C", 5, 3.4, 1.6, 1, 1, "R"],
                     ["SL", 87.2, 0.6, 1.9, "S", 9, 3.4, 1.6, 1, 1, "R"],
                     ["CH", 86.0, -0.4, 1.2, "S", 13, 3.4, 1.6, 1, 1, "R"]],
               "faced": [{"inn": 1, "half": "T", "b": "Aaron Judge", "bs": "R", "ev": "Strikeout",
                          "et": "strikeout", "np": 3, "ab": 1, "rbi": 0}]}],
    "season_line": {"pitches": 3, "k": 1, "bb": 0, "h": 0, "whiffs": 1, "csw": 0.667, "whiff": 0.5, "zone": 0.67,
                    "bf": 1, "top": 97.1},
    "mix": [{"type": "FF", "n": 1, "share": 0.33, "velo": 97.0, "whiff": 0.0, "csw": 1.0}], "zones": [], "velo": [],
}


# --- the daily leagues' finals --------------------------------------------------------
def _daily_conn():
    conn = D.connect(":memory:")
    D.upsert_games(conn, [
        {"sport": "nba", "season": 2025, "period": "2025-11-02", "game_id": "NYK@DEN", "home": "DEN", "away": "NYK",
         "home_score": 112, "away_score": 104},
        {"sport": "nhl", "season": 2025, "period": "2025-11-01", "game_id": "TOR@NYR", "home": "NYR", "away": "TOR",
         "home_score": 2, "away_score": 4},
        {"sport": "mlb", "season": 2026, "period": "2026-07-04", "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
         "home_score": 3, "away_score": 5},
        {"sport": "mlb", "season": 2026, "period": "2026-07-04", "game_id": "BOS@NYY-G2", "home": "NYY",
         "away": "BOS", "home_score": 7, "away_score": 1},
        {"sport": "nba", "season": 2025, "period": "2025-11-04", "game_id": "DEN@LAL", "home": "LAL", "away": "DEN",
         "home_score": None, "away_score": None}])
    return conn


def test_the_daily_leagues_finals_come_off_the_games_table():
    conn = _daily_conn()
    nba = CR.scoreboard(conn, "nba", 2025, [{"date": "2025-11-02", "team": "DEN", "opp": "NYK", "home": True},
                                            {"date": "2025-11-04", "team": "DEN", "opp": "LAL", "home": False}])
    assert nba[0]["score"] == [112.0, 104.0] and "rec" not in nba[0], "his score first; never a record"
    assert "score" not in nba[1], "a game with no final shows none"
    nhl = CR.scoreboard(conn, "nhl", 2025, [{"date": "2025-11-01", "team": "TOR", "opp": "NYR", "home": None}])
    assert nhl[0]["score"] == [4.0, 2.0], "a rink the table could not place still reads its final the right way round"


def test_a_doubleheader_is_told_apart_only_by_its_leg():
    conn = _daily_conn()
    legs = CR.scoreboard(conn, "mlb", 2026, [{"date": "2026-07-04", "team": "NYY", "opp": "BOS", "leg": 1},
                                             {"date": "2026-07-04", "team": "NYY", "opp": "BOS", "leg": 2}])
    assert legs[0]["score"] == [3.0, 5.0] and legs[1]["score"] == [7.0, 1.0]
    blind = CR.scoreboard(conn, "mlb", 2026, [{"date": "2026-07-04", "team": "NYY", "opp": "BOS"}])
    assert "score" not in blind[0], "two finals that day and no leg named: neither, never the other game's"
    twice = CR.scoreboard(conn, "nba", 2025, [{"date": "2025-11-02", "team": "DEN", "opp": "NYK"},
                                              {"date": "2025-11-02", "team": "DEN", "opp": "NYK"}])
    assert all("score" not in g for g in twice), "two chart games on one day and no leg: neither"


def test_every_daily_chart_builder_and_the_role_chart_read_them():
    for path, call in (("engine/nba/shots.py", 'scoreboard(conn, "nba", pick, out_games)'),
                       ("engine/mlb/charts.py", 'scoreboard(conn, "mlb", pick, out_games)'),
                       ("engine/mlb/charts.py", 'scoreboard(conn, "mlb", pick, games)'),
                       ("engine/nhl/charts.py", 'scoreboard(conn, "nhl", pick, games)'),
                       ("engine/role.py", "scoreboard(conn, sport, pick, games)")):
        assert call in (ROOT / path).read_text(encoding="utf-8"), (path, call)
    role = (ROOT / "engine" / "role.py").read_text(encoding="utf-8")
    assert role.index("scoreboard(conn, sport, pick, games)") < role.index('g.pop("leg", None)'), \
        "the role chart reads its finals while a doubleheader's games still name their leg"
    assert CR.DAILY == ("nba", "wnba", "mlb", "nhl")


# --- the page --------------------------------------------------------------------------
STUBS = """
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i class="mark">${a}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {};
  const icon = (n) => `<svg class="ic" data-n="${n}"></svg>`;
  const TEAMS = { DEN: { name: "Denver Nuggets", nick: "Nuggets", loc: "Denver", primary: "#0e2240" },
                  NYK: { name: "New York Knicks", nick: "Knicks", loc: "New York", primary: "#006bb6" } };
  const teamsIn = () => TEAMS;
  const venuePhotoTag = (sport, home) => `<img class="venue-photo" data-home="${home}">`;
  const venueSrc = (p) => `${p}?v=1`;
  const window = {};
"""


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = (f"{STUBS}\n{CC_JS}\n" + "\n".join(PLUGS.values())
            + f"\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t, P = T.DRAW; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_every_league_names_its_own_thirds():
    got = _node(f"""
      const d = {json.dumps(SHOTS)}, g = d.games[0], K = T.kindOf("shots", "nba");
      const of = (k, x) => T.sideOf(k, x);
      return {{
        shots: g.shots.map((s) => of("shots", s)),
        sides: T.sidesHTML("shots", T.poolOf("shots", g, d), K, true),
        seg: T.segHTML(K, T.zonesOf("shots")),
        spray: ["pull", "center", "oppo", ""].map((dir) => of("spray", {{ dir }})),
        pitches: ["FF", "SI", "FC", "SL", "ST", "CU", "CH", "FS", "PO"].map((t) => of("pitches", [t])),
        hockey: ["crease", "slot", "high", "point", ""].map((z) => of("shotmap", {{ z }})),
        saves: of("saves", {{ z: "high" }}),
        kicks: [[30, "fg"], [39, "fg"], [40, "fg"], [49, "fg"], [50, "fg"], [33, "xp"]].map(([dd, k]) => of("kicks", {{ d: dd, k }})),
        none: ["role", "fights", "matchup"].map((k) => T.zonesOf(k)),
        football: T.zonesOf("carries").list.map((x) => x[0]).join(""),
      }};""")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got["shots"] == ["P", "M", "3", "", "P"], "the restricted area is the paint; a free throw is in no zone"
    s = got["sides"]
    assert "<b>2 <small>shots</small></b><i>50%</i>" in s and "<b>1 <small>shot</small></b><i>25%</i>" in s, \
        "four shots from the floor counted, the free throw not"
    assert ">In the paint<" in s and ">Mid-range<" in s and ">Threes<" in s and 'data-side="P"' in s
    assert ">All shots<" in got["seg"] and ">Paint<" in got["seg"] and ">3PT<" in got["seg"]
    assert got["spray"] == ["pull", "center", "oppo", ""]
    assert got["pitches"] == ["F", "F", "F", "B", "B", "B", "O", "O", ""], "a pitchout is none of them"
    assert got["hockey"] == ["S", "S", "H", "P", ""] and got["saves"] == "H"
    assert got["kicks"] == ["S", "S", "M", "M", "L", ""], "an extra point is in no band"
    assert got["none"] == [None, None, None] and got["football"] == "LMR"


def test_every_play_as_the_renders_table_in_every_league():
    got = _node(f"""
      const d = {json.dumps(SHOTS)}, g = d.games[0], p = {json.dumps(PITCHES)}, pg = p.games[0];
      const grid = T.gridHTML("x", [{{ h: "#", c: "cc-c-n", p: "18px", w: "26px" }}, {{ h: "Time", c: "cc-c-q", w: "64px" }},
                                    {{ h: "Opp", c: "uf-o", p: "70px", w: "90px", r: 1 }}],
                              [{{ i: 0, f: "a b", said: "the whole play", cells: ["1", "Q1", ["22 of 60", ""]] }}]);
      return {{
        grid, list: P.shots.list(g, d), flags: g.shots.map(P.shots.flags),
        tools: T.toolsHTML("shots", g.shots, P.shots.flags, P.shots.filters),
        csv: T.csvOf("shots", g).split("\\r\\n"),
        faced: P.pitches.list(pg, p), pcsv: P.pitches.csv(pg, p).map((r) => r.join("|")),
      }};""")
    if got is None:
        return
    gr = got["grid"]
    assert 'style="--cc-p:18px 70px;--cc-w:26px 64px 90px"' in gr, "a phone's columns and a wide card's"
    assert '<span class="cc-c-q cc-wo">' in gr and '<span class="uf-o">22 of 60</span>' in gr
    assert 'data-f="a b"' in gr and 'aria-label="the whole play"' in gr and '<span class="r">Opp</span>' in gr
    lst = got["list"]
    assert len(re.findall(r'class="cc-row cc-tr', lst)) == 5 and "cc-g-shots" in lst
    assert "Assisted by J. Murray" in lst and ">Made 2<" in lst and ">Missed 2<" in lst and ">Blocked<" in lst
    assert "Free throw 1 of 1" in lst and ">+3<" in lst
    assert got["flags"] == ["m paint ast", "x blk", "m 3", "ft m", "x paint"]
    t = got["tools"]
    assert "Threes (1)" in t and "In the paint (2)" in t and "Free throws (1)" in t and 'data-dl="shots"' in t
    assert "Download this game’s shots as a spreadsheet" in t
    assert got["csv"][0].startswith("#,Period,Clock,Kind,Shot") and len([r for r in got["csv"] if r]) == 6
    assert got["csv"][1].startswith("1,Q1,11:30,2PT,Layup,driving,2,Restricted area,1,2,J. Murray,0")
    f = got["faced"]
    assert "Aaron Judge (R)" in f and "3 pitches" in f and '<em class="cc-pill good">K</em>' in f, \
        "a strikeout is green from the mound"
    assert got["pcsv"][0].startswith("#|Inning|Batter") and got["pcsv"][1].startswith("1|1|Aaron Judge|R|Four-seam|97.1|Called strike")


def test_the_other_views_in_every_league():
    got = _node(f"""
      const d = {json.dumps(SHOTS)};
      return {{ views: P.shots.views(d).map((v) => v[0]).join(","), zone: P.shots.bars(d, "zone"),
                title: P.shots.barTitle("zone"), list: T.barList([["A", 3, "said"], ["B", 0, "none"], ["C", 1, "x", ["+4% vs league", "good"]]]),
                kicks: P.kicks.views({{ by_band: [{{}}], by_place: [], by_weather: [{{}}], by_moment: [] }}).map((v) => v[0]).join(","),
                fights: P.fights.views({{ by_method: [{{ w: 1, l: 0 }}], by_rounds: [], by_finish: [{{}}] }}).map((v) => v[0]).join(",") }};""")
    if got is None:
        return
    assert got["views"] == "zone,type,dist" and got["title"] == "Shots by zone, beside the league"
    z = got["zone"]
    assert ">Restricted area<" in z and "league 64%" in z and '<em class="cc-pill good">+36% vs league</em>' in z
    assert '<em class="cc-pill bad">−42% vs league</em>' in z and "Above the break 3" not in z, "a zone with none has no bar"
    b = got["list"]
    assert '<b class="cc-bv">3<small>75%</small></b>' in b and ">B<" not in b and "+4% vs league" in b
    assert got["kicks"] == "dist,weather" and got["fights"] == "method,finish"


def test_a_fight_over_the_arena_and_tonight_over_both_teams():
    got = _node("""
      const d = { player: "Arman Tsarukyan", position: "Lightweight",
                  season_line: { n: 6, w: 4, l: 1, d: 1, ko_w: 2, sub_w: 1 }, games: [] };
      const g = { opp: "Dan Hooker", date: "2026-08-02", result: "W", method: "KO/TKO", rnd: 2, clock: "3:12",
                  division: "LIGHTWEIGHT" };
      return { fight: P.fights.hero(g, d), career: P.fights.hero(null, d),
               lost: P.fights.hero(Object.assign({}, g, { result: "L" }), d),
               tonight: T.heroHTML({ team: "DEN", opp: "NYK", tonight: true, home: true, label: "2025-26" },
                                   { team: "DEN", games: [] }, "nba", ["", ""]) };""")
    if got is None:
        return
    f = got["fight"]
    assert "img/venues/ufc-hero.jpg" in f and 'data-onerr="remove"' in f, "the site's own octagon render behind"
    assert ">Won<" in f and "KO/TKO · R2 3:12" in f and ">Tsarukyan<" in f and ">Hooker<" in f and ">4-1-1<" in f
    assert 'class="uf-ring me"' in f and ">AT<" in f and ">DH<" in f
    assert "--ta:var(--brand);--tb:var(--text-mute)" in f and "--ta:var(--text-mute);--tb:var(--brand)" in got["lost"], \
        "the winner's side lit"
    assert "Career" in got["career"] and ">won by finish<" in got["career"] and ">3<" in got["career"]
    t = got["tonight"]
    assert ">Tonight<" in t and ">VS<" in t and ">2025-26<" in t and ">Nuggets<" in t and ">Knicks<" in t
    assert "--ta:#0e2240" in t and "--tb:#006bb6" in t and "Final" not in t


def test_every_tile_wears_its_icon_and_a_long_name_is_fitted():
    got = _node(f"""
      const d = {json.dumps(SHOTS)}, p = {json.dumps(PITCHES)};
      return [P.shots.gameSide(d.games[0], d), P.shots.seasonSide(d), P.pitches.gameSide(p.games[0], p),
              P.pitches.seasonSide(p)].join("");""")
    if got is None:
        return
    names = re.findall(r'<span class="cc-k">(.*?)</span>', got)
    assert len(names) >= 20 and all(n.startswith('<svg class="ic"') for n in names), \
        [n for n in names if not n.startswith("<svg")]
    i = CC_JS.index("  function render() {")
    body = CC_JS[i:CC_JS.index("\n  function applySide()", i)]
    assert 'box.querySelectorAll(".cc-k").forEach((k) => { if (k.scrollWidth > k.clientWidth + 1) k.classList.add("tight"); });' in body
    assert ".cc-k.tight .ic { display: none; }" in CC_CSS


def test_the_frame_reads_each_leagues_parts_and_its_styles():
    i = CC_JS.index("  function render() {")
    body = CC_JS[i:CC_JS.index("\n  function applySide()", i)]
    for part in ("P.views(d)", "P.bars(d, S.view)", "P.legend ? P.legend(g, d)", "P.hero ? P.hero(g, d,",
                 "segHTML(K, zonesOf(S.kind))", "poolOf(S.kind, g, d)", "tonight: true"):
        assert part in body, part
    i = CC_JS.index("  function applySide() {")
    assert "el.dataset.z != null ? el.dataset.z" in CC_JS[i:i + 1200], "a league's marks say their own zone"
    for f, src in PLUGS.items():
        assert "onclick" not in src and "onerror" not in src and not re.search(r"on(error|load)\s*=", src), f
    for kind, f in (("shots", "hoops"), ("spray", "mlb"), ("pitches", "mlb"), ("shotmap", "nhl"), ("kicks", "kicks")):
        assert "zones" in PLUGS[f] and "filters" in PLUGS[f] and "csv" in PLUGS[f], kind
    for sel in (".cc-grid .cc-lh, .cc-grid .cc-tr { grid-template-columns: var(--cc-p); }",
                "@container (max-width: 639.98px)", "@container (min-width: 640px)", ".cc-grid .cc-po { display: none; }",
                ".uf-ring", ".nb-zone.hot", ".nb-halo", ".nb-plank", ".mb-mow", ".mb-wall-glow", ".mp-zone-glow",
                ".nh-blue-glow", ".nh-halo.goal", ".kk-mow", ".kk-trail", ".kk-glow line", ".cc-bx .cc-pill"):
        assert sel in CC_CSS, sel
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


# --- the browser, opt-in --------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i>${{a}}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.fetch = async (q) => ({{ ok: true, json: async () => window.CHART }});
</script>
<script>{js}</script></body></html>"""


def test_in_a_browser_every_leagues_controls_work():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    js = CC_JS + "\n" + PLUGS["hoops"] + "\n" + PLUGS["mlb"]
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
            page.set_content(PAGE.format(css=CC_CSS, js=js))
            page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Nikola Jokic', 'nba', 'shots'); }", SHOTS)
            page.wait_for_selector("#cc-overlay .cc-stage svg", timeout=5000)
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry').length") == 4, "the free throw is not drawn"
            page.click(".cc-seg [data-side='P']")
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry.off').length") == 2, \
                "the paint's two stay lit; the mid-range shot and the three fade"
            page.select_option("[data-filt]", "3")
            assert page.evaluate("[...document.querySelectorAll('.cc-row[data-f]')].filter((r) => !r.hidden).length") == 1
            with page.expect_download() as dl:
                page.click("[data-dl]")
            assert dl.value.suggested_filename == "nikola-jokic-shots-2025-nov-2-vs-nyk.csv"
            assert len(Path(dl.value.path()).read_text(encoding="utf-8").splitlines()) == 6
            assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
            assert page.evaluate("(() => { const c = document.querySelector('#cc-overlay .cc'); return c.scrollWidth - c.clientWidth; })()") == 0
            page.click("[data-view='zone']")
            assert page.evaluate("document.querySelectorAll('.cc-bars .cc-brow').length") == 4
            page.evaluate("window.QBCarry.close()")
            page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Tarik Skubal', 'mlb', 'pitches'); }", PITCHES)
            page.wait_for_selector("#cc-overlay .mp-svg", timeout=5000)
            page.click(".cc-seg [data-side='F']")
            assert page.evaluate("document.querySelectorAll('.cc-stage .cc-carry.off').length") == 2, \
                "his fastball stays lit; the slider and the changeup fade"
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
