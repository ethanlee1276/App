"""Every throw a quarterback made, drawn the way the route chart draws a target.

Ethan, 2026-10-13, on the list of charts the data could carry next: "Yes
do all of them and don't stop till they are all done, then make sure they
are all routed correctly like nfl." The first of them is the passer's:
the route chart turned round.

What is pinned, offline, on databases built here:

  * THE THROWS (engine/passes.NflPasses): every dropback that ended in a
    throw, a spike or a sack — a throwaway with nobody named is an attempt;
    a spike is an incomplete attempt, as in the box score; a sack is no
    attempt; two-point tries, wiped-out plays, runs and preseason are out;
  * THE BOX SCORE'S LINE: attempts, completions, yards, touchdowns,
    interceptions and sacks come back out as the box score counts them;
  * FTN'S WORDS, a blitz from five or more rushers, and no drop or
    throwaway on a completion;
  * THE SPLITS: depth by third, kept clean against hit, blitzed, play
    action, by down, and who he threw to;
  * NEXT GEN STATS only where the league published them;
  * ONE READ: the throws ride the nightly play-by-play read the carry and
    route charts share, and the chart filler owes the table like theirs;
  * ONE DOOR: /api/players/chart answers the passing chart, refuses a
    chart a league does not have, says "filling" while no one has a row;
  * THE PAGE: a quarterback's chart is his throws whatever the bet, every
    throw drawn and every dropback listed, the sacks marked behind him.

Run directly: `python3 tests/test_a_passing_chart_for_every_passer.py`
"""
import inspect
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

from engine import charts as CH, chartfill as CF, db as D, maintenance as M, passes as PS  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SLIP_JS = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")

ALLEN, SHAKIR, KINCAID = "00-0034857", "00-0037261", "00-0038696"
NAMES = {ALLEN: {"name": "Josh Allen", "position": "QB", "jersey": "17"},
         SHAKIR: {"name": "Khalil Shakir", "position": "WR", "jersey": "10"},
         KINCAID: {"name": "Dalton Kincaid", "position": "TE", "jersey": "86"}}


def _row(**kw):
    row = {"play_type": "pass", "season": "2026", "season_type": "REG", "week": "5",
           "game_id": "2026_05_BUF_LA", "home_team": "LA", "away_team": "BUF", "posteam": "BUF",
           "defteam": "LA", "game_date": "2026-10-12", "passer_player_id": ALLEN,
           "passer_player_name": "J.Allen", "receiver_player_id": SHAKIR,
           "receiver_player_name": "K.Shakir", "air_yards": "8", "pass_location": "left",
           "complete_pass": "1", "passing_yards": "12", "yards_gained": "12", "yards_after_catch": "4",
           "pass_touchdown": "0", "interception": "0", "first_down_pass": "1", "two_point_attempt": "0",
           "sack": "0", "qb_hit": "0", "down": "1", "ydstogo": "10", "yardline_100": "75", "qtr": "1",
           "quarter_seconds_remaining": "800", "cp": "0.7", "fumble_lost": "0", "play_id": "100"}
    row.update(kw)
    return row


#: Allen's afternoon, in play order: a completion, an incompletion, a
#: touchdown, an interception, a throwaway, a sack he fumbled, a spike —
#: and what is not a dropback: a two-point try, a play wiped out by a
#: penalty, a run and a preseason throw.
PLAYS = [
    _row(play_id="100"),
    _row(play_id="140", complete_pass="0", passing_yards="NA", yards_gained="0", yards_after_catch="NA",
         first_down_pass="0", air_yards="22", pass_location="middle", receiver_player_id=KINCAID,
         receiver_player_name="D.Kincaid", qb_hit="1", cp="0.4", down="2"),
    _row(play_id="300", air_yards="18", pass_location="right", passing_yards="25", yards_gained="25",
         yards_after_catch="7", pass_touchdown="1", receiver_player_id=KINCAID, receiver_player_name="D.Kincaid",
         yardline_100="25", qtr="2", cp="0.5", down="3"),
    _row(play_id="420", complete_pass="0", interception="1", passing_yards="NA", yards_gained="0",
         yards_after_catch="NA", first_down_pass="0", air_yards="31", pass_location="right", cp="0.3",
         qtr="2", down="1"),
    _row(play_id="510", complete_pass="0", passing_yards="NA", yards_gained="0", yards_after_catch="NA",
         first_down_pass="0", air_yards="NA", pass_location="right", receiver_player_id="NA",
         receiver_player_name="NA", cp="NA", qtr="3"),
    _row(play_id="600", sack="1", qb_hit="1", complete_pass="0", passing_yards="NA", yards_gained="-8",
         yards_after_catch="NA", first_down_pass="0", air_yards="NA", pass_location="NA",
         receiver_player_id="NA", receiver_player_name="NA", fumble_lost="1", cp="NA", qtr="3", down="3"),
    _row(play_id="900", play_type="qb_spike", complete_pass="0", passing_yards="NA", yards_gained="0",
         yards_after_catch="NA", first_down_pass="0", air_yards="-1", pass_location="NA",
         receiver_player_id="NA", receiver_player_name="NA", cp="NA", qtr="4"),
    _row(play_id="950", two_point_attempt="1"),
    _row(play_id="960", play_type="no_play"),
    _row(play_id="970", play_type="run"),
    _row(play_id="980", season_type="PRE"),
]


def _fold(rows=PLAYS, season=2026, charting=None):
    fold = PS.NflPasses(season)
    for r in rows:
        fold.add(r)
    return fold.rows(NAMES, charting or {})


def _conn(path=":memory:"):
    conn = D.connect(path)
    words = {("2026_05_BUF_LA", "300"): ("play action", "blitz"), ("2026_05_BUF_LA", "100"): ("drop", "screen"),
             ("2026_05_BUF_LA", "600"): ("blitz", "out of pocket")}
    D.upsert_passes(conn, _fold(charting=words))
    # Week 4 at home, so the chart has two games, newest first.
    D.upsert_passes(conn, _fold([_row(play_id="55", week="4", game_id="2026_04_NO_BUF", home_team="BUF",
                                      away_team="NO", defteam="NO", game_date="2026-10-05")]))
    D.upsert_passes(conn, _fold([_row(play_id="77", season="2025", week="9")], season=2025))
    D.upsert_ngs_passing(conn, PS.ngs_rows([
        {"season": "2026", "season_type": "REG", "week": "5", "player_gsis_id": ALLEN,
         "player_display_name": "Josh Allen", "team_abbr": "BUF", "attempts": "19",
         "avg_time_to_throw": "2.919", "completion_percentage_above_expectation": "-2.45",
         "aggressiveness": "10.5", "avg_intended_air_yards": "7.9"},
        {"season": "2026", "season_type": "REG", "week": "0", "player_gsis_id": ALLEN,
         "player_display_name": "Josh Allen", "team_abbr": "BUF", "attempts": "138",
         "avg_time_to_throw": "2.94", "completion_percentage_above_expectation": "1.58",
         "aggressiveness": "10.9", "avg_intended_air_yards": "9.3"}]))
    return conn


# --- the throws -------------------------------------------------------------------
def test_every_dropback_is_kept_and_nothing_else():
    rows = _fold()
    assert [r["play_id"] for r in rows] == ["100", "140", "300", "420", "510", "600", "900"], \
        "a two-point try, a wiped-out play, a run and preseason are not dropbacks"
    kinds = [r["kind"] for r in rows]
    assert kinds == ["pass", "pass", "pass", "pass", "pass", "sack", "spike"]
    by = {r["play_id"]: r for r in rows}
    assert by["100"]["player"] == "Josh Allen" and by["100"]["receiver"] == "Khalil Shakir"
    assert by["100"]["position"] == "QB" and by["100"]["jersey"] == "17"
    assert by["300"]["td"] == 1 and by["300"]["yards"] == 25.0 and by["300"]["side"] == "R"
    assert by["420"]["interception"] == 1 and by["420"]["complete"] == 0 and by["420"]["yards"] == 0.0
    assert by["510"]["receiver"] == "" and by["510"]["air_yards"] is None, "a throwaway names nobody"
    assert by["600"]["yards"] == -8.0 and by["600"]["fumble_lost"] == 1 and by["600"]["hit"] == 1
    assert by["600"]["air_yards"] is None and by["600"]["side"] == ""
    assert by["900"]["air_yards"] is None and by["900"]["complete"] == 0, "a spike is never drawn as a throw"
    assert by["140"]["hit"] == 1 and by["100"]["hit"] == 0
    assert by["100"]["cp"] == 0.7 and by["600"]["cp"] is None
    assert by["100"]["game_id"] == "BUF@LA" and by["100"]["period"] == "005" and by["100"]["home"] == 0


def test_ftn_words_and_the_blitz():
    got = PS.ftn_map([
        {"nflverse_game_id": "G", "nflverse_play_id": "1.0", "is_play_action": "TRUE", "n_pass_rushers": "5"},
        {"nflverse_game_id": "G", "nflverse_play_id": "2", "is_throw_away": "TRUE", "n_pass_rushers": "4"},
        {"nflverse_game_id": "G", "nflverse_play_id": "3", "is_drop": "FALSE", "n_pass_rushers": "NA"},
        {"nflverse_game_id": "G", "nflverse_play_id": "4", "is_interception_worthy": "TRUE",
         "is_qb_out_of_pocket": "TRUE", "is_screen_pass": "TRUE", "is_drop": "TRUE", "n_pass_rushers": "6"}])
    assert got == {("G", "1"): ("play action", "blitz"), ("G", "2"): ("throwaway",),
                   ("G", "4"): ("screen", "out of pocket", "should have been picked", "drop", "blitz")}
    rows = {r["play_id"]: r for r in _fold(charting={
        ("2026_05_BUF_LA", "100"): ("drop", "throwaway", "screen"),
        ("2026_05_BUF_LA", "140"): ("drop", "blitz"),
        ("2026_05_BUF_LA", "600"): ("blitz", "out of pocket", "play action")})}
    assert rows["100"]["charting"] == "screen", "no drop and no throwaway on a completion"
    assert rows["140"]["charting"] == "drop,blitz"
    assert rows["600"]["charting"] == "blitz", "a sack keeps only the rush that got him"
    assert PS.charting_for(2021) == {}, "FTN starts in 2022: nothing asked"


# --- the chart ------------------------------------------------------------------
def test_the_box_score_line():
    d = PS.chart(_conn(), "Josh Allen")
    g = d["games"][0]
    assert d["season"] == 2026 and d["seasons"] == [2026, 2025] and [x["week"] for x in d["games"]] == [5, 4]
    L = g["line"]
    assert (L["att"], L["cmp"], L["yds"], L["td"], L["int"], L["sk"], L["sk_yds"]) == (6, 2, 37.0, 1, 1, 1, -8.0), \
        "the spike is an attempt, the sack is not"
    assert L["n"] == 6, "what the page weighs his charts by: his attempts"
    assert L["pct"] == round(2 / 6, 3) and L["ypa"] == round(37 / 6, 2)
    assert L["adot"] == round((8 + 22 + 18 + 31) / 4, 1), "air yards over the throws that have them"
    # CPOE over the throws nflfastR priced: (1-.7) + (0-.4) + (1-.5) + (0-.3), over four.
    assert L["cpoe"] == round((0.3 - 0.4 + 0.5 - 0.3) / 4, 3)
    assert L["deep"] == 2 and L["deep_cmp"] == 0 and L["away"] == 0 and L["long"] == 25.0, "22 and 31 air yards"
    assert L["first"] == 2 and L["yac"] == 11.0 and L["hit"] == 2
    assert [t["k"] for t in g["throws"]] == ["pass", "pass", "pass", "pass", "pass", "sack", "spike"], \
        "in the order they happened"
    assert g["throws"][2]["fl"] == ["play action", "blitz"] and g["throws"][2]["to"] == "Dalton Kincaid"
    assert d["position"] == "QB" and d["jersey"] == "17" and d["team"] == "BUF"
    assert PS.chart(_conn(), "josh allen") ["player"] == "Josh Allen", "the loose spelling finds him"
    assert PS.chart(_conn(), "Nobody Here") == {}
    assert PS.chart(_conn(), "Josh Allen", 2019)["season"] == 2026, "a season he has none in: his latest"


def test_the_splits():
    d = PS.chart(_conn(), "Josh Allen")
    zones = {(z["depth"], z["side"]): z for z in d["by_zone"]}
    assert len(d["by_zone"]) == 12
    assert zones[("short", "L")]["att"] == 2 and zones[("short", "L")]["cmp"] == 2, "week 5's and week 4's"
    assert zones[("mid", "R")]["td"] == 1 and zones[("deep", "R")]["int"] == 1 and zones[("deep", "M")]["att"] == 1
    when = {x["when"]: x for x in d["by_pressure"]}
    assert set(when) == {"Kept clean", "Hit or sacked", "Blitzed (5+ rushers)", "Play action"}
    assert when["Hit or sacked"]["sk"] == 1 and when["Hit or sacked"]["att"] == 1
    assert when["Blitzed (5+ rushers)"]["att"] == 1 and when["Blitzed (5+ rushers)"]["sk"] == 1
    assert when["Kept clean"]["att"] == 6 and when["Play action"]["td"] == 1
    assert [x["down"] for x in d["by_down"]] == [1, 2, 3]
    assert [(x["to"], x["tgt"], x["rec"]) for x in d["by_target"]] == [("Khalil Shakir", 3, 2), ("Dalton Kincaid", 2, 1)]
    assert d["ngs"]["time_to_throw"] == 2.94 and d["games"][0]["ngs"]["cpoe"] == -2.45
    assert d["games"][1]["ngs"] is None, "never an estimate where the league published none"


def test_the_ngs_rows():
    rows = PS.ngs_rows([{"season": "2026", "season_type": "REG", "week": "0", "player_gsis_id": ALLEN,
                         "player_display_name": "Josh Allen", "team_abbr": "BUF", "attempts": "138",
                         "completions": "91", "pass_yards": "1249", "pass_touchdowns": "7", "interceptions": "4",
                         "avg_time_to_throw": "2.94", "completion_percentage_above_expectation": "1.58",
                         "aggressiveness": "10.9", "avg_intended_air_yards": "9.3",
                         "avg_completed_air_yards": "6.2", "avg_air_yards_to_sticks": "0.7",
                         "max_air_distance": "55.1"},
                        {"season": "2026", "week": "NA", "player_gsis_id": ALLEN}])
    assert len(rows) == 1 and rows[0]["week"] == 0 and rows[0]["attempts"] == 138
    assert rows[0]["cpoe"] == 1.58 and rows[0]["time_to_throw"] == 2.94 and rows[0]["max_air"] == 55.1


# --- one read, owed like the others ----------------------------------------------
def test_it_rides_the_nightly_read_and_the_filler_owes_it():
    src = inspect.getsource(M)
    i = src.index("_carries_behind = False")
    block = src[i:src.index("# The DEEP fitters", i)]
    assert "_ps.nfl_behind(_cconn, _cseason, today)" in block, "a game with no throws starts the read too"
    assert "throws = _passes.NflPasses(season)" in block and "throws.add(r)" in block
    assert "_passes.PBP_COLS" in block and "_targets.PBP_COLS), also=_each)" in block, "one read, every fold"
    assert "upsert_passes(_pc, throws.rows(names, _passes.charting_for(season)))" in block
    assert "fetch_ngs_passing()" in block and "_ps2.missing_seasons(_qc, (season - 1,))" in block
    assert "backfill_nfl(_qc, past)" in block
    assert ("nfl", "passes") in CF.TABLES
    assert "passes" in __import__("engine.carries", fromlist=["CHART_TABLES"]).CHART_TABLES


# --- one door ---------------------------------------------------------------------
def test_the_door_answers_the_passing_chart():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        D.connect(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_chart({"kind": ["passes"], "sport": ["nfl"], "player": ["Josh Allen"]})
        _conn(path).close()
        h._players_chart({"kind": ["passes"], "sport": ["nfl"], "player": ["Josh Allen"]})
        h._players_chart({"kind": ["passes"], "sport": ["nfl"], "player": ["Josh Allen"], "season": ["2025"]})
        h._players_chart({"kind": ["passes"], "sport": ["nfl"], "player": ["Nobody Here"]})
        h._players_chart({"kind": ["passes"], "sport": ["cfb"], "player": ["Josh Allen"]})
        h._players_chart({"kind": ["nothing"], "sport": ["nfl"], "player": ["Josh Allen"]})
        h._players_chart({"kind": ["carries"], "sport": ["nfl"], "player": ["Nobody Here"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True}), "no one has a throw yet: the charts are being filled"
    code, body = sent[1]
    assert code == 200 and body["kind"] == "passes" and "face" in body and body["season_line"]["att"] == 7
    assert sent[2][1]["season"] == 2025
    assert sent[3] == (200, {}), "rows on file: a missing player is just missing"
    assert sent[4][0] == 400 and sent[5][0] == 400, "a chart the league does not have is refused"
    assert sent[6] == (200, {"filling": True}), "the carry chart through the same door"
    assert CH.known("passes", "nfl") and not CH.known("passes", "cfb") and CH.known("carries", "cfb")
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/players/chart"' in src
    i = src.index("def _players_chart(")
    assert "_entitled" not in src[i:src.index("\n    def ", i + 10)], "where a ball was thrown is a fact"


# --- the page -----------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
      const teamNameIn = (lg, a) => ({ LA: "Rams", NO: "Saints" })[a] || a;
      const lockScroll = () => {};
      const window = {};
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


def test_the_page_draws_every_throw_and_lists_every_dropback():
    d = PS.chart(_conn(), "Josh Allen")
    got = _node(f"""
      const d = {json.dumps(d)}, g = d.games[0], P = T.DRAW.passes;
      const svg = T.passGameChart(g), season = T.passSeasonChart(d), list = T.passList(g);
      return {{
        throws: (svg.match(/class="rc-throw/g) || []).length, sacks: (svg.match(/class="rc-sack/g) || []).length,
        marks: (svg.match(/class="cc-carry"/g) || []).length, qb: svg.includes('class="rc-qb"'),
        aria: /aria-label="Passing chart: 5 throws at Rams\\. Each one is listed below\\."/.test(svg),
        cells: (season.match(/class="rc-cell"/g) || []).length, dots: (season.match(/class="rc-dot /g) || []).length,
        rows: (list.match(/class="cc-row/g) || []).length, list,
        tiles: T.passTiles(g.line, g.ngs), tilesNo: T.passTiles(d.games[1].line, d.games[1].ngs),
        tables: T.passTables(d), chip: T.passChip(g), count: P.count(d.season_line),
        side: P.seasonSide(d), note: P.note(d), items: P.items(g).length,
        tip: P.tip(g.throws[5], g, d),
        kinds: [T.kindsFor("nfl", "pass_yds", "QB"), T.kindsFor("nfl", "rush_yds", "QB"), T.kindsFor("nfl", "pass_tds", "")],
        chipName: T.KIND.passes.chip, title: T.KIND.passes.title,
      }};
    """)
    if got is None:
        return                                            # no node on this machine
    assert got["throws"] == 5 and got["sacks"] == 1 and got["marks"] == 6 and got["qb"] and got["aria"], \
        "five throws drawn, the sack marked, the spike only listed"
    assert got["cells"] == 12 and got["dots"] == 6
    assert got["rows"] == 7 and got["items"] == 7, "every dropback listed, the spike and the sack too"
    for want in (">+12<", ">Inc<", ">INT<", ">Sack −8<", ">Spike<", "to Khalil Shakir", "nobody targeted",
                 "22 air yds, middle", ">TD<", ">Fumble lost<", ">Hit<", ">Play action<", ">Blitzed<",
                 "Spiked to stop the clock"):
        assert want in got["list"], want
    assert ">Dropped<" not in got["list"], "never a drop on a completion"
    assert "Throw time" in got["tiles"] and "2.92s" in got["tiles"] and ">2/6<" in got["tiles"]
    assert "Throw time" not in got["tilesNo"] and "Sacked" in got["tilesNo"], "never an estimate in its place"
    for cap in ("How far past the line", "Which third of the field", "Kept clean, hit, blitzed, play action",
                "By down", "Who he threw to"):
        assert cap in got["tables"], cap
    assert got["chip"] == "2/6 · 37" and got["count"] == "7 attempts"
    assert "Next Gen Stats, 2026" in got["side"] and "2.94s to throw" in got["side"] and "Deep (20+)" in got["side"]
    assert "spiked ball counts as an incomplete attempt" in got["note"] and "FTN" in got["note"]
    assert "Sacked, −8 yds" in got["tip"]
    assert got["kinds"] == [["passes", "carries"]] * 3, "a quarterback's own chart is his throws"
    assert got["chipName"] == "Passes" and got["title"] == "Passing chart"


def test_every_door_reaches_it():
    i = APP_JS.index("function chartSlot(")
    # Since 2026-10-13 every player's bet leaves a slot and the chart
    # module's kindsFor picks his charts (pinned above for a passer).
    assert "return r && r.player ?" in APP_JS[i:i + 400], "a passing bet's pick page draws his chart"
    i = SLIP_JS.index("function chartsHTML(")
    assert "/rush|rec|anytime|pass/.test(m)" in SLIP_JS[i:i + 400], "a passing leg carries his charts' door"
    assert '`/api/players/chart?kind=${kind}&sport=`' in CC_JS
    assert 'cand: auto ? (lg === "nfl" ? ["carries", "routes", "passes"] : ["carries", "routes"]) : null' in CC_JS
    for cls in (".rc-sack", ".rc-sack.sel"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    assert "onclick" not in CC_JS and "onerror" not in CC_JS and not re.search(r"on(error|load)\s*=", CC_JS)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
