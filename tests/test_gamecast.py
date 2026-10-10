"""The live game page in ESPN's layout (2026-10-08).

Ethan, with three screenshots of ESPN's app on a live Bucs–Cowboys game:
"I want the page to look like ESPN's app looks … see the game and stadium
like I have now then scroll down and see the live game leaders and shit
and see the actual play by play and all of that. We should have the box
score and all of that."

Two halves. The deep file (livescore_build.pbp_doc) now carries the whole
box score, each side's game totals, the two records and the drive in
progress, all read off the summary already in hand
(engine/sources/espnplays) — numbers under labels, never ESPN's sentences.
The page's rooms (web/js/gamecast.js, loaded on first use) draw them as
Gamecast · Box score · Play-by-play · Team stats · Odds & picks.

Run directly: `python3 tests/test_gamecast.py`
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

import livescore_build as B                                  # noqa: E402
from engine import shrink                                    # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
GC_CSS = (ROOT / "web" / "css" / "gamecast.css").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")

TEXT = "ESPN's own sentence describing the play"
DESC = "ESPN's drive summary sentence"
BLURB = "ESPN's paragraph about the athlete"


def _team(abbr, tid, name):
    return {"id": tid, "abbreviation": abbr, "displayName": name}


DAL = _team("DAL", "6", "Dallas Cowboys")
TB = _team("TB", "27", "Tampa Bay Buccaneers")


def _ath(name, aid, pos, stats, blurb=False):
    info = {"id": aid, "displayName": name, "position": {"abbreviation": pos}}
    if blurb:
        info["summary"] = BLURB
    return {"athlete": info, "stats": stats}


#: Two plays carry a sentence shaped like ESPN's, naming players the box
#: score knows: the builder keeps the NAMES (espnplays._football_players,
#: a roster match) and never the sentence.
PASS_TEXT = "D.Prescott pass short right to G.Pickens for 29 yards (J.Trotter)."
TD_TEXT = "J.Williams up the middle for 1 yard, TOUCHDOWN. B.Aubrey extra point is GOOD."


def _play(pid, *, team, down=1, dist=10, to_go=75, yards=4, ptype="Rush", scoring=False,
          turnover=False, period=1, clock="11:02", away=0, home=0, text=TEXT):
    return {"id": pid, "period": {"number": period}, "clock": {"displayValue": clock},
            "start": {"down": down, "distance": dist, "yardLine": 100 - to_go, "yardsToEndzone": to_go,
                      "team": {"id": team}},
            "statYardage": yards, "type": {"text": ptype, "abbreviation": "X"},
            "scoringPlay": scoring, "isTurnover": turnover, "isPenalty": False,
            "awayScore": away, "homeScore": home, "text": text}


def _summary():
    """Bucs @ Cowboys, DAL home: a punt drive done, a touchdown drive in
    progress (the probe's shape: the current drive is also the tail of
    `previous`)."""
    d1 = {"id": "d1", "team": DAL, "offensivePlays": 3, "yards": 4, "timeElapsed": {"displayValue": "1:40"},
          "start": {"yardLine": 25, "period": {"number": 1}}, "displayResult": "Punt", "description": DESC,
          "plays": [_play("p1", team="6", to_go=75, yards=4), _play("p2", team="6", down=2, dist=6, to_go=71, yards=0),
                    _play("p3", team="6", down=3, dist=6, to_go=71, yards=0, ptype="Punt")]}
    d2 = {"id": "d2", "team": DAL, "offensivePlays": 7, "yards": 66, "timeElapsed": {"displayValue": "3:23"},
          "start": {"yardLine": 30, "period": {"number": 1}}, "displayResult": "Touchdown", "description": DESC,
          "plays": [_play("p4", team="6", to_go=70, yards=29, ptype="Pass Reception", text=PASS_TEXT),
                    _play("p5", team="6", to_go=41, yards=25, ptype="Rush"),
                    _play("p6", team="6", down=1, dist=4, to_go=4, yards=0, ptype="Rush", clock="11:02"),
                    _play("p7", team="6", down=2, dist=4, to_go=4, yards=1, ptype="Rushing Touchdown",
                          scoring=True, clock="10:51", away=0, home=7, text=TD_TEXT)]}
    return {
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "team": DAL, "record": [{"type": "total", "summary": "2-2"}, {"type": "home", "summary": "1-1"}]},
            {"homeAway": "away", "team": TB, "record": [{"type": "total", "summary": "0-4"}]}]}]},
        "drives": {"previous": [d1, d2], "current": d2},
        "boxscore": {
            "teams": [
                {"team": DAL, "statistics": [
                    {"name": "firstDowns", "displayValue": "12", "label": "1st Downs"},
                    {"name": "thirdDownEff", "displayValue": "5-12", "label": "3rd down efficiency"},
                    {"name": "possessionTime", "displayValue": "31:12", "label": "Possession"},
                    {"name": "totalYards", "displayValue": "341", "label": "Total Yards"},
                    {"name": "nope", "displayValue": "", "label": "Empty"},
                    {"name": "long", "displayValue": "1", "label": "x" * 60}]},
                {"team": TB, "statistics": [
                    {"name": "firstDowns", "displayValue": "9", "label": "1st Downs"},
                    {"name": "thirdDownEff", "displayValue": "2-10", "label": "3rd down efficiency"},
                    {"name": "possessionTime", "displayValue": "28:48", "label": "Possession"},
                    {"name": "totalYards", "displayValue": "212", "label": "Total Yards"}]}],
            "players": [
                {"team": DAL, "statistics": [
                    {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"],
                     "athletes": [_ath("Dak Prescott", "3042", "QB", ["3/4", "37", "9.3", "0", "0", "0-0", "88.1", "99.0"], blurb=True)]},
                    {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
                     "athletes": [_ath("Javonte Williams", "4361", "RB", ["4", "26", "6.5", "1", "25"]),
                                  _ath("Dak Prescott", "3042", "QB", ["0", "0", "0.0", "0", "0"])]},
                    {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
                     "athletes": [_ath("George Pickens", "4426", "WR", ["2", "29", "14.5", "0", "19", "2"]),
                                  _ath("Nobody Yet", "1", "WR", ["", "--", "", "", "", ""])]},
                    {"name": "defensive", "labels": ["TOT", "SOLO", "SACKS", "TFL", "PD", "QB HTS", "TD"],
                     "athletes": [_ath("DaRon Bland", "4567", "CB", ["1", "1", "0", "0", "1", "0", "0"])]},
                    {"name": "empty", "labels": [], "athletes": []}]},
                {"team": TB, "statistics": [
                    {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"],
                     "athletes": []},
                    {"name": "defensive", "labels": ["TOT", "SOLO", "SACKS", "TFL", "PD", "QB HTS", "TD"],
                     "athletes": [_ath("Jalen Trotter", "7001", "LB", ["2", "1", "0", "0", "0", "0", "0"]),
                                  _ath("David Walker", "7002", "DE", ["1", "1", "0", "0", "0", "0", "0"])]}]}]}}


def _game(state="live"):
    return {"event_id": "e9", "home": "DAL", "away": "TB", "home_name": "Dallas Cowboys",
            "away_name": "Tampa Bay Buccaneers", "home_id": "6", "away_id": "27", "tv": ["Prime Video"],
            "live": {"state": state, "home_score": 7, "away_score": 0, "period": "Q1", "clock": "10:51",
                     "detail": "2nd & Goal at TB 4", "yard_line": 4, "possession": "DAL", "start_time": "",
                     "win_prob": {"home": "DAL", "away": "TB", "home_win_prob": 0.92, "away_win_prob": 0.08}}}


# --- the deep file ---------------------------------------------------------------
def test_the_whole_box_score_is_read_as_groups_under_espns_labels():
    box = E.summary_box(_summary(), "nfl")
    assert [b["team"] for b in box] == ["DAL", "TB"]
    dal = {g["name"]: g for g in box[0]["groups"]}
    assert list(dal) == ["passing", "rushing", "receiving", "defensive"], "a group with no labels is not a group"
    assert dal["passing"]["labels"] == ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"]
    assert dal["passing"]["rows"] == [{"name": "Dak Prescott", "stats": ["3/4", "37", "9.3", "0", "0", "0-0", "88.1", "99.0"],
                                       "pos": "QB", "id": "3042"}]
    assert [r["name"] for r in dal["receiving"]["rows"]] == ["George Pickens"], "a row with no stats is dropped"
    assert [r["name"] for r in dal["rushing"]["rows"]] == ["Javonte Williams", "Dak Prescott"], "a zero is a stat"
    tb = {g["name"]: g for g in box[1]["groups"]}
    assert list(tb) == ["defensive"], "a group with no rows is not a group"
    flat = json.dumps(box)
    assert BLURB not in flat and "summary" not in flat


def test_team_stats_and_records_come_off_the_summary_and_nothing_longer_than_a_label():
    ts = E.summary_team_stats(_summary(), "nfl")
    assert [r["label"] for r in ts["DAL"]] == ["1st Downs", "3rd down efficiency", "Possession", "Total Yards"], \
        "an empty value and a sixty-character label are not stats"
    assert ts["DAL"][1] == {"name": "thirdDownEff", "label": "3rd down efficiency", "value": "5-12"}
    assert ts["TB"][0]["value"] == "9"
    assert E.team_records(_summary(), "nfl") == {"DAL": "2-2", "TB": "0-4"}, "the season record, not the home one"
    bad = _summary()
    bad["header"]["competitions"][0]["competitors"][0]["record"] = [{"type": "total", "summary": "two and two"}]
    assert E.team_records(bad, "nfl") == {"TB": "0-4"}
    assert E.summary_team_stats({}, "nfl") == {} and E.team_records({"header": {}}, "nfl") == {}
    assert E.summary_box({"boxscore": {"players": "no"}}, "nfl") == []


def test_each_drive_says_how_it_ended_and_the_current_one_is_named():
    drives = E.football_drives(_summary(), "nfl", home="DAL", away="TB")
    assert [d.get("result") for d in drives] == ["Punt", "Touchdown"]
    cur = E.current_drive(_summary(), "nfl")
    assert cur["result"] == "Touchdown" and cur["plays"] == 7 and cur["yards"] == 66 and cur["elapsed"] == "3:23"
    long = _summary()
    long["drives"]["current"]["displayResult"] = "A sentence long enough to be prose rather than a label"
    long["drives"]["current"].pop("result", None)
    assert "result" not in E.current_drive(long, "nfl")
    assert E._drive_result({"result": "Field Goal"}) == "Field Goal" and E._drive_result({}) == ""


def test_the_deep_file_carries_the_rooms_and_none_of_the_writing():
    doc = B.pbp_doc("nfl", _game(), _summary())
    assert doc["records"] == {"DAL": "2-2", "TB": "0-4"}
    assert doc["drive"]["team"] == "DAL" and doc["drive"]["result"] == "Touchdown"
    assert [b["team"] for b in doc["box"]] == ["DAL", "TB"]
    assert doc["team_stats"]["TB"][3]["value"] == "212"
    assert doc["drives"][1]["result"] == "Touchdown" and doc["plays"][-1]["id"] == "p7"
    assert doc["tv"] == ["Prime Video"]
    # The names, never the sentence (the roster match; a tackler in
    # brackets is cut before matching).
    assert doc["plays"][-1]["players"] == ["Javonte Williams"]
    assert doc["drives"][1]["plays"][0]["players"] == ["Dak Prescott", "George Pickens"]
    flat = json.dumps(doc)
    for prose in (TEXT, DESC, BLURB, PASS_TEXT, TD_TEXT, "up the middle", "pass short right",
                  '"text"', '"description"', '"summary"'):
        assert prose not in flat, prose
    # A summary without the blocks carries no keys for them — absent, never empty.
    thin = B.pbp_doc("nfl", _game(), {"drives": {"previous": [], "current": None}})
    for key in ("box", "team_stats", "records", "drive"):
        assert key not in thin, key
    # Hoops: the box and the team stats ride too; no drive, no drives.
    hoops = B.pbp_doc("wnba", {"event_id": "h1", "home": "LVA", "away": "IND", "home_id": "14", "away_id": "5",
                               "live": {"state": "live", "start_time": ""}},
                      {"plays": [], "boxscore": {"players": [], "teams": []}})
    assert "drive" not in hoops and "drives" not in hoops and "box" not in hoops


def test_a_room_that_fails_to_read_costs_that_key_alone():
    real = E.summary_team_stats
    E.summary_team_stats = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("shape"))
    try:
        doc = B.pbp_doc("nfl", _game(), _summary())
    finally:
        E.summary_team_stats = real
    assert "team_stats" not in doc and doc["box"] and doc["records"] and doc["drive"]


# --- the page --------------------------------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def test_the_page_loads_the_gamecast_on_first_use_and_draws_its_tabs():
    assert 'let _pbpTab = "gamecast";' in APP
    assert ('const GC_TABS = [["gamecast", "Gamecast"], ["box", "Box score"], ["plays", "Play-by-play"],\n'
            '                 ["team", "Team stats"], ["odds", "Odds & picks"], ["injuries", "Injuries"]];') in APP
    assert 'const pbpTabsFor = (league) => league === "mlb" ? PBP_TABS : GC_TABS;' in APP
    loader = _fn("loadGamecast")
    assert 'css.href = "css/gamecast.css";' in loader and 'el.src = "js/gamecast.js";' in loader
    assert "if (window.QBGamecast) return Promise.resolve(window.QBGamecast);" in loader
    page = _fn("renderPbpPage")
    assert "const tabs = pbpTabsFor(league);" in page
    assert 'const GC = league === "mlb" ? null : (window.QBGamecast || null);' in page
    assert 'loadGamecast().then((mod) => { if (mod && state.view === "pbp") renderPbpPage(); });' in page
    assert "GC ? GC.panel(tab, { d, league, faces, boardGame })" in page
    assert "Loading the gamecast…" in page
    assert "pbpTabsHTML(tab, boardGame, tabs)" in page
    # The hero: the records and the carrier, absent when unknown.
    assert '`<div class="mini pbp-hero-rec">${escapeHtml((d.records || {})[abbr])}</div>` : ""' in page
    assert '`<span class="pbp-hero-tv">${escapeHtml((d.tv || [])[0])}</span>` : ""' in page
    assert ".pbp-hero-rec {" in CSS and ".pbp-hero-tv {" in CSS
    # The box score's team toggle, wired like every other button on the page.
    assert 'host.querySelectorAll("[data-gc-team]")' in page and "window.QBGamecast.setTeam(b.dataset.gcTeam)" in page
    # Baseball keeps its four rooms.
    assert 'tab === "players" ? pbpPlayersHTML(d, league)' in page and ': league === "mlb" ? infoPanel' in page


def test_the_module_draws_numbers_and_never_a_sentence():
    assert 'window.QBGamecast = {' in GC
    for prose in ("p.text", "p.description", "shortDescription", "d.text", "athlete.summary", "row.summary"):
        assert prose not in GC, prose
    assert "(d.live || {}).win_prob" in GC, "the win percentage is our model's"
    assert "Win % (our model)" in GC
    assert "https://a.espncdn.com/i/headshots/${dir}/players/full/" in GC
    assert 'const FACE_DIR = { nfl: "nfl", cfb: "college-football", nba: "nba", wnba: "wnba", nhl: "nhl" };' in GC
    assert "onerror" not in GC and "onclick" not in GC, "no inline handlers under the page's CSP"
    for cls in (".gc-drive", ".gc-tiles", ".gc-last", ".gc-chip", ".gc-win", ".gc-leaders", ".gc-lead-row",
                ".gc-toggle", ".gc-tog.active", ".gc-ts-row", ".gc-bar", ".gc-dr", ".gc-tag.turnover", ".gc-face"):
        assert cls in GC_CSS, cls
    assert "js/gamecast.js" in shrink.FILES and "css/gamecast.css" in shrink.FILES
    caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    assert "/js/gamecast.js /css/gamecast.css" in caddy


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const escapeAttr = escapeHtml;
      const icon = (n) => `<i class="ico-${n}"></i>`;
      const teamMarkIn = (lg, a, size) => `<span class="mark">${a}</span>`;
      const teamNameIn = (lg, a) => ({ DAL: "Cowboys", TB: "Buccaneers" })[a] || a;
      const pbpOrd = (n) => n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
      const pbpAgo = () => "just now";
      const trueMinus = (s) => s;
      const hockeyPeriod = (n) => `P${n}`;
      const panelEmpty = (t) => `<p>${t}</p>`;
      const gameId = (g) => g.id || "g";
      const playsHTML = (g) => (g.plays || []).map((p) => `<div class="lb-play">${p.event} ${p.players ? p.players.join("/") : ""}</div>`).join("");
      const pbpGroups = () => [];
      const pbpPropsHTML = () => "<div>picks</div>";
      const lineTrackHTML = () => "<div>track</div>";
      const pbpPlayersHTML = () => "<div>old box</div>";
      const pbpTotalsHTML = () => "<div>old totals</div>";
      const window = {};
    """
    prog = f"{stubs}\n{GC}\nconsole.log(JSON.stringify((() => {{ const QBGamecast = window.QBGamecast; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_rooms_draw_the_drive_the_last_play_the_leaders_the_box_and_the_totals():
    doc = B.pbp_doc("nfl", _game(), _summary())
    doc["plays"][-1]["text"] = TEXT                      # if a sentence ever got in, the page would still not draw it
    got = _node(f"""
      const d = {json.dumps(doc)};
      const ctx = {{ d, league: "nfl", faces: {{ "javonte williams": "img/jw.png" }}, boardGame: {{ id: "TB@DAL", line_track: [1] }} }};
      QBGamecast.setTeam("DAL");                     // the away side opens first; the test reads the home box
      return {{
        spot: [QBGamecast.spotWord(d, 4), QBGamecast.spotWord(d, 96), QBGamecast.spotWord(d, 50), QBGamecast.spotWord(d, 120)],
        lead: QBGamecast.leaderOf(d, "DAL", "rushing", "YDS"),
        line: QBGamecast.playerLine(d, "Dak Prescott", "pass0").line,
        rbLine: QBGamecast.playerLine(d, "Javonte Williams", "any").line,
        unknown: QBGamecast.playerLine(d, "Nobody", "any").line,
        face: QBGamecast.faceURL("nfl", {{ name: "Dak Prescott", id: "3042" }}, ctx.faces),
        own: QBGamecast.faceURL("nfl", {{ name: "Javonte Williams", id: "4361" }}, ctx.faces),
        gamecast: QBGamecast.panel("gamecast", ctx),
        box: QBGamecast.panel("box", ctx),
        team: QBGamecast.panel("team", ctx),
        plays: QBGamecast.panel("plays", ctx),
        odds: QBGamecast.panel("odds", ctx),
      }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["spot"] == ["DAL 4", "TB 4", "50", ""], "home's half counts from the home goal line"
    assert got["lead"]["v"] == 26 and got["lead"]["row"]["name"] == "Javonte Williams"
    assert got["line"] == "3/4, 37 YDS, 0 TD, 0 INT" and got["rbLine"] == "4 CAR, 26 YDS, 1 TD" and got["unknown"] == ""
    assert got["face"] == "https://a.espncdn.com/i/headshots/nfl/players/full/3042.png"
    assert got["own"] == "img/jw.png", "the board's own face first"
    g = got["gamecast"]
    for want in ("Current drive", "7 plays, 66 yards, 3:23", ">Down<", "2nd &amp; Goal", ">Ball on<", "TB 4",
                 "Last play · Q1 10:51", "Rushing Touchdown · 1 yd", "Win % (our model)", "<b>92.0</b>",
                 "Game leaders", ">Passing<", ">Rushing<", ">Receiving<", ">Tackles<", "Dak Prescott",
                 "George Pickens", "Jalen Trotter", "2 TOT, 1 SOLO", "img/jw.png", ">Score<"):
        assert want in g, want
    assert ">Sacks<" not in g, "nobody has a sack: the row is not drawn"
    # The last play's chips: the man named on it, his face, his line so
    # far, and the snap it came from — no sentence anywhere on the page.
    assert g.count('class="gc-chip"') == 1 and "2nd &amp; 4 at TB 4" in g
    assert "TB 0 – 7 DAL" in g
    for prose in (TEXT, TD_TEXT, PASS_TEXT, "up the middle"):
        assert prose not in g and prose not in got["plays"] and prose not in got["box"], prose
    b = got["box"]
    assert 'data-gc-team="TB"' in b and 'data-gc-team="DAL"' in b and "gc-tog active" in b
    assert ">Passing<" in b and ">C/ATT<" in b and ">3/4<" in b and "Javonte Williams" in b
    assert "Nobody Yet" not in b, "a row with no stats is not drawn"
    t = got["team"]
    assert "1st Downs" in t and ">12<" in t and ">9<" in t and "gc-bar" in t
    assert "5-12" in t and t.count("gc-bar") == 2, "bars for the two plain numbers, none for 5-12 or 31:12"
    p = got["plays"]
    assert p.index("Touchdown") < p.index("Punt"), "newest drive first"
    assert "7 plays · 66 yd · 3:23 · Q1" in p and "0–7" in p
    assert "picks" in got["odds"] and "track" in got["odds"] and "Full game page" in got["odds"]


def test_the_box_toggle_remembers_the_side_and_a_final_says_so():
    doc = B.pbp_doc("nfl", _game(state="final"), _summary())
    got = _node(f"""
      const d = {json.dumps(doc)};
      const ctx = {{ d, league: "nfl", faces: {{}}, boardGame: null }};
      QBGamecast.setTeam("TB");
      const box = QBGamecast.panel("box", ctx);
      return {{ team: QBGamecast.team(), tbActive: box.indexOf('data-gc-team="TB"') < box.indexOf("gc-tog active") + 40,
               hasTrotter: box.includes("Jalen Trotter"), noDak: !box.includes("Dak Prescott"),
               gamecast: QBGamecast.panel("gamecast", ctx) }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["team"] == "TB" and got["hasTrotter"] and got["noDak"]
    assert "Current drive" not in got["gamecast"], "a final has no drive in progress"
    assert "Final." in got["gamecast"] and "Game leaders" in got["gamecast"]


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
    print(f"\n{len(tests) - fails} passed, {fails} failed." if fails else f"\n{len(tests)} tests passed.")
    sys.exit(1 if fails else 0)
