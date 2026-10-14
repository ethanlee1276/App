"""Every pass thrown to a player, drawn the way the league's route chart draws it.

Ethan, 2026-10-13, with the NFL's Next Gen Stats route chart for Sam
LaPorta against the Cardinals on the screen: "We can add route charts for
wr and shit too. And if we don't have access too this info then we should
be able too make it. There should be enough data and tools we have access
too too make this for nfl".

What is pinned, offline, on databases built here:

  * THE TARGETS (engine/targets.NflTargets): every pass with a receiver
    named — air yards, the third of the field, caught or not, yards after
    the catch, a touchdown only when the receiver scored it; sacks,
    two-point tries, throwaways and preseason left out;
  * THE SCREENSHOT GAME: LaPorta's five targets at the Cardinals as the
    2026 file has them come back out of the chart as the screenshot's
    numbers — 5 targets, 5 catches, 88 yards, 44 after the catch, a TD;
  * THE LEAGUE'S ROUTE, NEVER A GUESS: the participation file's route,
    man or zone and shell join by the league's own game and play ids; a
    season it has not published joins nothing, and the page draws those
    targets as the throw;
  * FTN'S WORDS, and a drop or "not catchable" never on a catch;
  * SEPARATION only where the league published it;
  * ONE READ: the targets ride the nightly play-by-play read the carry
    chart and the unit ratings already share;
  * THE ENDPOINT: the NFL and, since the college target chart, college;
    ungated, nothing for a player with no targets;
  * THE PAGE: the same lazy module as the carry chart, every target drawn
    and listed, and the note that says what is the record and what is
    drawn.

Run directly: `python3 tests/test_a_route_chart_for_every_receiver.py`
"""
import datetime as dt
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

from engine import carries as CR, db as D, targets as TG       # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

LAPORTA = "00-0039065"
GAME = "2026_05_DET_ARI"
#: LaPorta at the Cardinals, 2026 week 5, as the play-by-play file has it:
#: (play id, quarter, seconds left in it, down, to go, yards to the end
#: zone, air yards, location, yards after the catch, receiving yards, TD,
#: first down).
SCREENSHOT = [(1157, 2, 817, 4, 3, 47, 11, "middle", 1, 12, 0, 1),
              (1484, 2, 605, 3, 12, 49, -1, "right", 12, 11, 0, 0),
              (1567, 2, 578, 4, 1, 38, 14, "right", 24, 38, 1, 1),
              (2706, 3, 739, 1, 10, 57, 2, "left", 6, 8, 0, 0),
              (3841, 4, 572, 2, 8, 48, 18, "left", 1, 19, 0, 1)]
NAMES = {LAPORTA: {"name": "Sam LaPorta", "position": "TE", "jersey": "87"}}


def _pbp(**kw):
    row = {"play_type": "pass", "season": "2026", "season_type": "REG", "week": "5", "game_id": GAME,
           "home_team": "ARI", "away_team": "DET", "posteam": "DET", "defteam": "ARI",
           "game_date": "2026-10-11", "receiver_player_id": LAPORTA, "receiver_player_name": "S.LaPorta",
           "air_yards": "11", "pass_location": "middle", "complete_pass": "1", "yards_after_catch": "1",
           "receiving_yards": "12", "pass_touchdown": "0", "td_player_id": "NA", "interception": "0",
           "first_down_pass": "1", "two_point_attempt": "0", "sack": "0", "down": "4", "ydstogo": "3",
           "yardline_100": "47", "qtr": "2", "quarter_seconds_remaining": "817", "play_id": "1157"}
    row.update(kw)
    return row


def _screenshot_rows():
    out = []
    for pid, q, secs, dn, togo, yl, air, loc, yac, yds, td, fd in SCREENSHOT:
        out.append(_pbp(play_id=str(pid), qtr=str(q), quarter_seconds_remaining=str(secs), down=str(dn),
                        ydstogo=str(togo), yardline_100=str(yl), air_yards=str(air), pass_location=loc,
                        yards_after_catch=str(yac), receiving_yards=str(yds), pass_touchdown=str(td),
                        td_player_id=LAPORTA if td else "NA", first_down_pass=str(fd)))
    return out


def _conn_with_laporta(path=":memory:"):
    """2026: the screenshot game and a week-4 game with a drop, a contested
    catch and an interception. 2025: one game the league charted."""
    conn = D.connect(str(path))
    fold = TG.NflTargets(2026)
    for r in _screenshot_rows():
        fold.add(r)
    wk4 = dict(week="4", game_id="2026_04_DET_CAR", home_team="CAR", away_team="DET", defteam="CAR",
               game_date="2026-10-04")
    fold.add(_pbp(**wk4, play_id="200", air_yards="8", pass_location="left", complete_pass="0",
                  yards_after_catch="NA", receiving_yards="NA", first_down_pass="0"))
    fold.add(_pbp(**wk4, play_id="300", air_yards="22", pass_location="right", yards_after_catch="0",
                  receiving_yards="22"))
    fold.add(_pbp(**wk4, play_id="400", air_yards="16", pass_location="middle", complete_pass="0",
                  interception="1", yards_after_catch="NA", receiving_yards="NA", first_down_pass="0"))
    charting = TG.ftn_map([
        {"nflverse_game_id": "2026_04_DET_CAR", "nflverse_play_id": "200", "is_drop": "TRUE",
         "is_catchable_ball": "TRUE"},
        {"nflverse_game_id": "2026_04_DET_CAR", "nflverse_play_id": "300", "is_contested_ball": "TRUE",
         "is_catchable_ball": "TRUE"},
        {"nflverse_game_id": "2026_04_DET_CAR", "nflverse_play_id": "400", "is_catchable_ball": "FALSE"}])
    D.upsert_targets(conn, fold.rows(NAMES, {}, charting))
    past = TG.NflTargets(2025)
    wk = dict(season="2025", week="10", game_id="2025_10_DET_WAS", home_team="WAS", away_team="DET",
              defteam="WAS", game_date="2025-11-09")
    past.add(_pbp(**wk, play_id="500", air_yards="5", pass_location="left", yards_after_catch="9",
                  receiving_yards="14"))
    past.add(_pbp(**wk, play_id="600", air_yards="27", pass_location="right", complete_pass="0",
                  yards_after_catch="NA", receiving_yards="NA", first_down_pass="0"))
    routes = TG.route_map([
        {"nflverse_game_id": "2025_10_DET_WAS", "play_id": "500", "route": "SHALLOW CROSS/DRAG",
         "defense_man_zone_type": "ZONE_COVERAGE", "defense_coverage_type": "COVER_3"},
        {"nflverse_game_id": "2025_10_DET_WAS", "play_id": "600", "route": "GO",
         "defense_man_zone_type": "MAN_COVERAGE", "defense_coverage_type": "COVER_1"}])
    D.upsert_targets(conn, past.rows(NAMES, routes, {}))
    D.upsert_ngs_receiving(conn, TG.ngs_rows([
        {"season": "2026", "season_type": "REG", "week": "5", "player_gsis_id": LAPORTA,
         "player_display_name": "Sam LaPorta", "team_abbr": "DET", "targets": "5", "receptions": "5",
         "avg_separation": "4.51", "avg_cushion": "3.6", "avg_intended_air_yards": "8.64",
         "avg_yac_above_expectation": "0.27"},
        {"season": "2026", "season_type": "REG", "week": "0", "player_gsis_id": LAPORTA,
         "player_display_name": "Sam LaPorta", "team_abbr": "DET", "targets": "37", "avg_separation": "3.63",
         "percent_share_of_intended_air_yards": "17.2"},
        {"season": "2026", "season_type": "POST", "week": "4", "player_gsis_id": LAPORTA,
         "player_display_name": "Sam LaPorta", "team_abbr": "DET", "avg_separation": "9.9"}]))
    return conn


# --- the targets ------------------------------------------------------------
def test_every_target_is_kept_and_nothing_that_is_not_one():
    fold = TG.NflTargets(2026)
    fold.add(_pbp())
    fold.add(_pbp(play_type="run"))
    fold.add(_pbp(sack="1", play_id="2"))
    fold.add(_pbp(two_point_attempt="1", play_id="3"))
    fold.add(_pbp(season_type="PRE", play_id="4"))
    fold.add(_pbp(receiver_player_id="NA", play_id="5"))
    rows = fold.rows(NAMES)
    assert len(rows) == 1, "sacks, two-point tries, throwaways and the preseason are not targets"
    r = rows[0]
    assert (r["player"], r["position"], r["jersey"]) == ("Sam LaPorta", "TE", "87")
    assert (r["period"], r["game_id"], r["opponent"], r["home"]) == ("005", "DET@ARI", "ARI", 0)
    assert (r["air_yards"], r["side"], r["complete"], r["yac"], r["yards"]) == (11.0, "M", 1, 1.0, 12.0)
    assert (r["clock"], r["down"], r["distance"], r["yardline_100"], r["first_down"]) == ("13:37", 4, 3, 47, 1)
    assert (r["route"], r["coverage"], r["shell"], r["charting"]) == ("", "", "", "")


def test_a_touchdown_or_a_first_down_is_his_only_when_he_caught_it():
    fold = TG.NflTargets(2026)
    fold.add(_pbp(play_id="1", pass_touchdown="1", td_player_id="00-0000001"))
    fold.add(_pbp(play_id="2", complete_pass="0", first_down_pass="1", yards_after_catch="NA",
                  receiving_yards="NA"))
    fold.add(_pbp(play_id="3", yards_after_catch="NA", receiving_yards="12", air_yards="9"))
    a, b, c = fold.rows()
    assert a["td"] == 0, "somebody else scored on the play"
    assert (b["complete"], b["yards"], b["yac"], b["first_down"]) == (0, 0.0, None, 0)
    assert c["yac"] == 3.0, "a catch with no YAC recorded keeps yards minus air yards"
    assert a["player"] == "S.LaPorta", "no name map: the play-by-play's own short name stands"


def test_the_screenshot_game_reads_back_as_the_screenshot():
    d = TG.chart(_conn_with_laporta(), "Sam LaPorta")
    assert d["season"] == 2026 and d["seasons"] == [2026, 2025] and d["routes"] is False
    g = d["games"][0]
    assert (g["week"], g["opp"], g["home"]) == (5, "ARI", False), "newest game first"
    L = g["line"]
    assert (L["tgt"], L["rec"], L["yds"], L["yac"], L["td"]) == (5, 5, 88.0, 44.0, 1), \
        "the league's chart: 5-5, 88 yards, 44 after the catch, a touchdown"
    assert [t["ay"] for t in g["targets"]] == [11.0, -1.0, 14.0, 2.0, 18.0], "in the order thrown"
    td = g["targets"][2]
    assert (td["td"], td["s"], td["yac"], td["y"], td["q"], td["clk"]) == (True, "R", 24.0, 38.0, 2, "9:38")
    assert g["ngs"]["separation"] == 4.51, "that week's NGS row"
    assert d["ngs"]["separation"] == 3.63, "week 0 is the season line, never the playoffs"


def test_the_league_route_joins_by_its_own_ids_and_is_never_guessed():
    rows = [{"nflverse_game_id": "2025_10_DET_WAS", "play_id": "500.0", "route": "slant",
             "defense_man_zone_type": "MAN_COVERAGE", "defense_coverage_type": "2_MAN"},
            {"nflverse_game_id": "2025_10_DET_WAS", "play_id": "501", "route": "",
             "defense_man_zone_type": "ZONE_COVERAGE", "defense_coverage_type": "COVER_3"}]
    m = TG.route_map(rows)
    assert m == {("2025_10_DET_WAS", "500"): ("SLANT", "man", "2-Man")}, "no route charted, nothing kept"
    d = TG.chart(_conn_with_laporta(), "Sam LaPorta", 2025)
    assert d["routes"] is True
    t = d["games"][0]["targets"]
    assert [(x["rt"], x["cov"], x["sh"]) for x in t] == [("SHALLOW CROSS/DRAG", "zone", "Cover 3"),
                                                          ("GO", "man", "Cover 1")]
    assert [r["route"] for r in d["by_route"]] == ["GO", "SHALLOW CROSS/DRAG"]
    assert {c["coverage"]: c["tgt"] for c in d["by_cov"]} == {"man": 1, "zone": 1}
    assert [s["shell"] for s in d["by_shell"]] == ["Cover 1", "Cover 3"]
    this = TG.chart(_conn_with_laporta(), "Sam LaPorta", 2026)
    assert this["by_route"] == [] and this["by_cov"] == [], "2026: nothing charted, nothing claimed"


def test_ftn_words_ride_along_and_a_catch_is_never_a_drop():
    m = TG.ftn_map([
        {"nflverse_game_id": "G", "nflverse_play_id": "7", "is_screen_pass": "TRUE", "is_play_action": "TRUE",
         "is_catchable_ball": "TRUE"},
        {"nflverse_game_id": "G", "nflverse_play_id": "8", "is_drop": "TRUE", "is_catchable_ball": "FALSE"},
        {"nflverse_game_id": "G", "nflverse_play_id": "9", "is_catchable_ball": "TRUE"}])
    assert m == {("G", "7"): ("screen", "play action"), ("G", "8"): ("drop", "not catchable")}
    fold = TG.NflTargets(2026)
    fold.add(_pbp(game_id="G", play_id="8"))
    (r,) = fold.rows(NAMES, {}, m)
    assert r["charting"] == "", "FTN's drop and uncatchable on a ball he caught are not said"
    d = TG.chart(_conn_with_laporta(), "Sam LaPorta", 2026)
    wk4 = d["games"][1]
    assert [t["fl"] for t in wk4["targets"]] == [["drop"], ["contested"], ["not catchable"]]
    assert (wk4["line"]["drops"], wk4["line"]["contested"], wk4["line"]["contested_won"]) == (1, 1, 1)
    assert wk4["line"]["int"] == 1 and wk4["ngs"] is None, "no NGS row that week, none shown"


def test_the_season_view_says_where_his_targets_go():
    d = TG.chart(_conn_with_laporta(), "Sam LaPorta", 2026)
    assert d["season_line"]["tgt"] == 8 and d["season_line"]["rec"] == 6
    cells = {(z["depth"], z["side"]): z["tgt"] for z in d["by_zone"]}
    assert len(cells) == 12, "four depths by three thirds, empty ones kept"
    assert cells[("behind", "R")] == 1 and cells[("short", "L")] == 2 and cells[("mid", "M")] == 2
    assert cells[("mid", "L")] == 1 and cells[("mid", "R")] == 1 and cells[("deep", "R")] == 1
    assert sum(cells.values()) == 8
    assert [x["down"] for x in d["by_down"]] == [1, 2, 3, 4]
    assert TG.depth_of(-1) == "behind" and TG.depth_of(0) == "short" and TG.depth_of(19.5) == "mid"
    assert TG.depth_of(20) == "deep" and TG.depth_of(None) == ""


def test_a_name_is_found_the_way_the_carry_chart_finds_one():
    conn = _conn_with_laporta()
    assert TG.resolve(conn, "Sam LaPorta") == "Sam LaPorta"
    assert TG.resolve(conn, "sam laporta") == "Sam LaPorta"
    assert TG.resolve(conn, "Sam LaPorta Jr.") == "Sam LaPorta"
    assert TG.resolve(conn, "Nobody") == "" and TG.chart(conn, "Nobody") == {}
    assert TG.chart(conn, "Sam LaPorta", 2031)["season"] == 2026, "an unknown season falls back to his latest"


# --- keeping it current -----------------------------------------------------
def test_the_nightly_reads_targets_while_a_finished_game_has_none():
    today = dt.date(2026, 10, 13)
    conn = D.connect(":memory:")
    D.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": "005", "game_id": "DET@ARI",
                           "home": "ARI", "away": "DET", "home_score": 20, "away_score": 31,
                           "date": "2026-10-11"}])
    assert TG.nfl_behind(conn, 2026, today) is True
    fold = TG.NflTargets(2026)
    fold.add(_pbp())
    D.upsert_targets(conn, fold.rows(NAMES))
    assert TG.nfl_behind(conn, 2026, today) is False, "caught up: the nightly stops reading"
    assert TG.missing_seasons(conn, (2025, 2026)) == [2025]
    try:
        CR.nfl_behind(conn, 2026, today, table="games; DROP TABLE carries")
    except ValueError:
        pass
    else:
        raise AssertionError("only the two chart tables are asked about")


def test_a_season_with_no_route_file_joins_nothing_and_reads_only_what_it_needs():
    from engine.sources import fetch as F
    keep = F.fetch_text
    asked = []

    def gone(url, cache, **kw):
        asked.append(cache)
        raise F.DataUnavailable("404")

    def part(url, cache, **kw):
        asked.append(cache)
        return ("﻿nflverse_game_id,play_id,offense_names,route,defense_man_zone_type,defense_coverage_type\n"
                "2025_01_DET_GB,40,a;b;c,GO,MAN_COVERAGE,COVER_1\n2025_01_DET_GB,41,x,,,\n")
    try:
        F.fetch_text = gone
        assert TG.routes_for(2026) == {}, "nflverse has no 2026 file: no route, and no guess"
        assert asked == ["pbp_participation_2026.csv"] * 2, "the cached file nflpart reads, both spellings"
        asked.clear()
        assert TG.charting_for(2021) == {} and asked == [], "FTN starts in 2022: nothing asked"
        assert TG.charting_for(2026) == {}
        F.fetch_text = part
        assert TG.routes_for(2025) == {("2025_01_DET_GB", "40"): ("GO", "man", "Cover 1")}
    finally:
        F.fetch_text = keep


def test_the_nightly_folds_targets_into_the_one_play_by_play_read():
    from engine import maintenance
    src = inspect.getsource(maintenance._run_chores)
    i = src.index("_carries_behind = False")
    block = src[i:src.index("THE DEEP fitters", i) if "THE DEEP fitters" in src[i:] else i + 8000]
    assert "_tg.nfl_behind(_cconn, _cseason, today)" in block, "a game with no route chart starts the read too"
    assert "catches = _targets.NflTargets(season)" in block and "catches.add(r)" in block
    assert "_targets.PBP_COLS), also=_each)" in block, "one read of the file, every fold"
    assert "upsert_targets(_pc, catches.rows(names, _targets.routes_for(season)," in block
    assert "_targets.charting_for(season)" in block
    assert "fetch_ngs_receiving()" in block and "_tg2.missing_seasons(_rc, (season - 1,))" in block
    assert "backfill_nfl(_rc, past)" in block


def test_the_box_check_says_what_is_stored_and_reads_the_screenshot_back():
    import routefill
    assert routefill.check(D.connect(":memory:"))[0].startswith("NFL  no targets stored yet")
    lines = routefill.check(_conn_with_laporta())
    assert lines[0] == ("NFL  2026: 8 targets in 2 games · newest 2026-10-11 · the league's route on 0% "
                        "· an FTN word on 38%")
    assert lines[1].startswith("NFL  2025: 2 targets in 1 games") and "route on 100%" in lines[1]
    assert lines[-1] == ("CHECK Sam LaPorta 2026 week 5 at ARI: 5 targets, 5 catches, 88 yards, "
                         "44 after the catch, 1 TD — the screenshot's numbers")
    src = (ROOT / "routefill.py").read_text(encoding="utf-8")
    assert '"--fill" in argv' in src, "the check is read-only unless asked to fill"


# --- the endpoint -----------------------------------------------------------
def test_the_endpoint_serves_both_footballs_and_gates_nothing():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    try:
        path = Path(tmp) / "history.db"
        _conn_with_laporta(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_routes({"sport": ["nfl"], "player": ["Sam LaPorta"]})
        h._players_routes({"sport": ["cfb"], "player": ["Sam LaPorta"]})
        h._players_routes({"sport": ["nfl"], "player": ["Nobody Here"]})
        h._players_routes({"player": ["Sam LaPorta"], "season": ["2025"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    code, body = sent[0]
    assert code == 200 and body["games"][0]["line"]["yds"] == 88.0 and "face" in body
    # College since the college target chart (2026-10-13): no college
    # target is on file here, so the league's table is still being filled.
    assert sent[1] == (200, {"filling": True}), sent[1]
    assert sent[2] == (200, {})
    assert sent[3][1]["season"] == 2025 and sent[3][1]["routes"] is True, "the NFL is the default"
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/players/routes"' in src
    i = src.index("def _players_routes(")
    body_src = src[i:src.index("\n    def ", i + 10)]
    assert "_entitled" not in body_src, "where a ball was thrown is a fact, not a pick"


# --- the page ---------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
      const teamNameIn = (lg, a) => ({ ARI: "Cardinals", CAR: "Panthers", WAS: "Commanders" })[a] || a;
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


def test_the_page_draws_every_target_and_lists_it():
    conn = _conn_with_laporta()
    now, past = TG.chart(conn, "Sam LaPorta", 2026), TG.chart(conn, "Sam LaPorta", 2025)
    got = _node(f"""
      const d = {json.dumps(now)}, p = {json.dumps(past)};
      const g = d.games[0], w4 = d.games[1], pg = p.games[0];
      const svg = T.routeGameChart(g), svg4 = T.routeGameChart(w4), psvg = T.routeGameChart(pg);
      const season = T.routeSeasonChart(d);
      const ends = ["GO", "SLANT", "QUICK OUT", "HITCH/CURL", "IN/DIG", "DEEP OUT", "POST", "CORNER",
                    "SHALLOW CROSS/DRAG", "SCREEN", "SWING", "WHEEL", "TEXAS/ANGLE"].map((rt) => {{
        const pts = T.routePoints(rt, 12, 9, 1); const e = pts[pts.length - 1];
        return Math.abs(e[0] - 12) < 1e-9 && Math.abs(e[1] - 9) < 1e-9 && pts.every((q) => Math.abs(q[0]) <= 26);
      }});
      const xs = T.catchXs([{{ s: "L" }}, {{ s: "L" }}, {{ s: "M" }}, {{ s: "R" }}, {{ s: "" }}]);
      return {{
        targets: (svg.match(/class="cc-carry"/g) || []).length,
        throws: (svg.match(/class="rc-throw/g) || []).length,
        routes: (svg.match(/class="rc-route/g) || []).length,
        yac: (svg.match(/class="rc-yac"/g) || []).length,
        tds: (svg.match(/class="cc-td"/g) || []).length,
        qb: svg.includes('class="rc-qb"'), thirds: [">Left<", ">Middle<", ">Right<"].every((x) => svg.includes(x)),
        aria: /aria-label="Route chart: 5 targets at Cardinals\\. Each one is listed below\\."/.test(svg),
        miss: svg4.includes("rc-throw miss"), int: svg4.includes('class="rc-int"'),
        pRoutes: (psvg.match(/class="rc-route/g) || []).length, pQb: psvg.includes("rc-qb"),
        pMiss: psvg.includes("rc-route miss"),
        cells: (season.match(/class="rc-cell"/g) || []).length,
        dots: (season.match(/class="rc-dot /g) || []).length,
        seasonAria: /aria-label="Route chart: 8 targets this season\\."/.test(season),
        ends, xs,
        list: (T.routeList(g).match(/class="cc-row/g) || []).length,
        listText: T.routeList(g), list4: T.routeList(w4), plist: T.routeList(pg),
        tiles: T.routeTiles(g.line, g.ngs), tilesNo: T.routeTiles(w4.line, w4.ngs),
        noteNow: T.routeNote(d), notePast: T.routeNote(p),
        tables: T.routeTables(p), tablesNow: T.routeTables(d),
        legend: T.routeLegend(false, false), legendPast: T.routeLegend(true, false), legendSeason: T.routeLegend(false, true),
      }};
    """)
    if got is None:
        return                                            # no node on this machine
    assert got["targets"] == 5 and got["throws"] == 5 and got["routes"] == 0, "2026: each drawn as the throw"
    assert got["yac"] == 5 and got["tds"] == 1 and got["qb"] and got["thirds"] and got["aria"]
    assert got["miss"] and got["int"], "an incompletion is dashed, an interception crossed"
    assert got["pRoutes"] == 2 and not got["pQb"] and got["pMiss"], "2025: the league's routes, the miss dashed"
    assert got["cells"] == 12 and got["dots"] == 8 and got["seasonAria"]
    assert all(got["ends"]), "every route shape ends where the ball arrived, inside the sidelines"
    xs = got["xs"]
    assert xs[0] < xs[1] < -10 and abs(xs[2]) < 6 and xs[3] > 10 and abs(xs[4]) < 6, \
        "the third is the record; two in one third never share a spot"
    assert got["list"] == 5 and "+38" in got["listText"] and "14 air yds, right" in got["listText"]
    assert "24 yds after catch" in got["listText"] and ">TD<" in got["listText"]
    assert ">Inc<" in got["list4"] and ">INT<" in got["list4"] and ">Drop<" in got["list4"]
    assert ">Contested<" in got["list4"] and ">Not catchable<" in got["list4"]
    assert "Shallow cross · 5 air yds, left" in got["plist"] and "Zone · Cover 3" in got["plist"]
    assert ">5-5<" in got["tiles"] and ">88<" in got["tiles"] and ">44<" in got["tiles"]
    assert "Separation" in got["tiles"] and "4.5" in got["tiles"]
    assert "Separation" not in got["tilesNo"] and "1st downs" in got["tilesNo"], "never an estimate in its place"
    assert "Each line is the throw" in got["noteNow"]
    assert "43%" in got["noteNow"] and "through 2025" in got["noteNow"]
    assert "drawn, not tracked" in got["notePast"] and "43%" not in got["notePast"]
    assert "By route — the league’s charting" in got["tables"] and "Against man and zone" in got["tables"]
    assert "By route" not in got["tablesNow"] and "How far past the line" in got["tablesNow"]
    assert ">Throw<" in got["legend"] and ">Route<" in got["legendPast"] and ">Caught<" in got["legendSeason"]


def test_the_door_and_the_styles():
    assert re.search(r'const catches = lg === "nfl" && tabs\.some\(\(t\) => /recei\|recep\|target/i\.test\(t\)\);',
                     APP_JS), "the door is the NFL's, for a player with a receiving log"
    assert 'ccDoor(player, lg, "routes", "Route chart", face)' in APP_JS and 'data-kind="${kind}"' in APP_JS
    assert "/api/players/routes" in CC_JS and 'S.kind === "routes"' in CC_JS
    for cls in (".rc-route", ".rc-throw", ".rc-route.miss", ".rc-yac", ".rc-catch", ".rc-miss", ".rc-int",
                ".rc-cell", ".rc-dot.c", ".rc-lbl", ".cc-tiles-6"):
        assert cls in CC_CSS, cls
    i = CC_CSS.index("@media (prefers-reduced-motion: reduce)")
    assert ".rc-route" in CC_CSS[i:i + 200] and ".rc-yac" in CC_CSS[i:i + 200]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    assert "onclick" not in CC_JS and "onerror" not in CC_JS, "no inline handlers under the page's CSP"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
