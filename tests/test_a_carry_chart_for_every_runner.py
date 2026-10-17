"""Every run a player made, drawn the way the league's carry chart draws it.

Ethan, 2026-10-13, with the NFL's Next Gen Stats carry chart for Josh
Allen at the Rams on the screen: "one feature too add for nfl and CFB is a
carry chart exactly in the screenshot for every player ... Users should be
able too look at a Carry chart for past games and also just a kinda
'average' carry chart showing where they run."

What is pinned, offline, on databases built here:

  * THE NFL RUNS (engine/carries.NflCarries): the hole from the
    play-by-play's run_location and run_gap, the yards, scrambles,
    touchdowns, a lost fumble only when it was the runner's; two-point
    tries and preseason left out; the site's own spelling of the name and
    the jersey off the roster;
  * THE SCREENSHOT GAME: Allen's ten carries at the Rams as the 2026 file
    has them come back out of the chart as the screenshot's numbers — 10
    carries, 121 yards, a touchdown — four of them off left end;
  * COLLEGE (CfbCarries): the play file's runs on the team keys the logs
    use, a touchdown by name or by the geometry, a fumble said as fumbled,
    no hole and no clock, because the file records neither reliably;
  * ONE READ EACH: the college runs ride the play-file read the player
    logs already make; the NFL runs ride the nightly play-by-play read,
    which now also runs while a finished game has no chart;
  * RUSHING YARDS OVER EXPECTED only where the league published it;
  * THE ENDPOINT: football only, ungated, nothing for a player with no runs;
  * THE PAGE: loaded on first use, no inline handlers, every carry drawn
    through its hole and listed under the chart, and the note that says
    which part of a line is the record and which part is drawn.

Run directly: `python3 tests/test_a_carry_chart_for_every_runner.py`
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

from engine import carries as CR, db as D                      # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

ALLEN = "00-0034857"
#: Allen at the Rams, 2026 week 5, as the play-by-play file has it:
#: (quarter, seconds left in it, location, gap, yards, scramble, TD, yards to go to the end zone).
SCREENSHOT = [(1, 264, "left", "end", 8, 1, 0, 47), (1, 65, "left", "end", 6, 1, 0, 11),
              (2, 437, "left", "end", 7, 1, 0, 65), (3, 229, "right", "end", 9, 1, 0, 13),
              (4, 770, "middle", "NA", 22, 1, 0, 55), (4, 693, "middle", "NA", 1, 0, 1, 1),
              (4, 354, "right", "guard", 15, 1, 0, 66), (4, 120, "right", "guard", 21, 1, 0, 26),
              (5, 215, "middle", "NA", 19, 1, 0, 59), (5, 170, "left", "end", 13, 0, 0, 40)]


def _pbp(**kw):
    row = {"play_type": "run", "season": "2026", "season_type": "REG", "week": "5",
           "game_id": "2026_05_BUF_LA", "home_team": "LA", "away_team": "BUF", "posteam": "BUF",
           "defteam": "LA", "game_date": "2026-10-12", "rusher_player_id": ALLEN,
           "rusher_player_name": "J.Allen", "rushing_yards": "8", "yards_gained": "8",
           "run_location": "left", "run_gap": "end", "qb_scramble": "0", "two_point_attempt": "0",
           "fumble_lost": "0", "fumbled_1_player_id": "NA", "rush_touchdown": "0",
           "first_down_rush": "0", "down": "1", "ydstogo": "10", "yardline_100": "47", "qtr": "1",
           "quarter_seconds_remaining": "264", "play_id": "100"}
    row.update(kw)
    return row


def _screenshot_rows():
    out = []
    for i, (q, secs, loc, gap, yds, scr, td, yl) in enumerate(SCREENSHOT):
        out.append(_pbp(qtr=str(q), quarter_seconds_remaining=str(secs), run_location=loc, run_gap=gap,
                        rushing_yards=str(yds), yards_gained=str(yds), qb_scramble=str(scr),
                        rush_touchdown=str(td), yardline_100=str(yl), play_id=str(100 + 25 * i),
                        first_down_rush="1" if yds >= 10 or td else "0"))
    return out


NAMES = {ALLEN: {"name": "Josh Allen", "position": "QB", "jersey": "17"}}


def _conn_with_allen(path=":memory:"):
    conn = D.connect(str(path))
    fold = CR.NflCarries(2026)
    for r in _screenshot_rows():
        fold.add(r)
    # Week 4 at home: two more runs, one of them a lost fumble.
    fold.add(_pbp(week="4", game_id="2026_04_NE_BUF", home_team="BUF", away_team="NE", defteam="NE",
                  game_date="2026-10-04", rushing_yards="-3", yards_gained="-3", run_location="right",
                  run_gap="tackle", fumble_lost="1", fumbled_1_player_id=ALLEN, play_id="300"))
    fold.add(_pbp(week="4", game_id="2026_04_NE_BUF", home_team="BUF", away_team="NE", defteam="NE",
                  game_date="2026-10-04", rushing_yards="7", yards_gained="7", play_id="420",
                  run_location="NA", run_gap="NA"))
    D.upsert_carries(conn, fold.rows(NAMES))
    return conn


# --- the NFL runs -----------------------------------------------------------
def test_the_hole_is_the_play_by_plays_own_two_columns():
    assert CR.hole_of("middle", "NA") == "M"
    assert CR.hole_of("left", "end") == "LE" and CR.hole_of("right", "guard") == "RG"
    assert CR.hole_of("left", "tackle") == "LT" and CR.hole_of("right", "end") == "RE"
    assert CR.hole_of("left", "NA") == "", "a side with no gap is not guessed into a lane"
    assert CR.hole_of("NA", "NA") == "" and CR.hole_of(None, None) == ""


def test_every_run_is_kept_and_nothing_that_is_not_a_carry():
    fold = CR.NflCarries(2026)
    fold.add(_pbp())
    fold.add(_pbp(play_type="pass"))
    fold.add(_pbp(two_point_attempt="1"))
    fold.add(_pbp(season_type="PRE"))
    fold.add(_pbp(rusher_player_id="NA"))
    fold.add(_pbp(season_type="POST", week="19", play_id="7"))
    fold.add(_pbp(rushing_yards="NA", yards_gained="4", play_id="8"))
    # A fumble on the play that was somebody else's is not the runner's lost ball.
    fold.add(_pbp(fumble_lost="1", fumbled_1_player_id="00-0000001", play_id="9"))
    fold.add(_pbp(fumble_lost="1", fumbled_1_player_id=ALLEN, play_id="10"))
    rows = fold.rows(NAMES)
    assert len(rows) == 5, "a pass, a two-point try, preseason and a run with no runner are not carries"
    r = rows[0]
    assert (r["sport"], r["season"], r["period"], r["game_id"], r["play_id"]) == ("nfl", 2026, "005", "BUF@LA", "100")
    assert r["player"] == "Josh Allen" and r["jersey"] == "17" and r["position"] == "QB"
    assert r["team"] == "BUF" and r["opponent"] == "LA" and r["home"] == 0
    assert r["hole"] == "LE" and r["clock"] == "4:24" and r["yardline_100"] == 47 and r["date"] == "2026-10-12"
    assert rows[1]["period"] == "019", "playoff runs are carries too"
    assert rows[2]["yards"] == 4.0, "no rushing yards credited: the play's yards stand"
    assert rows[3]["fumble_lost"] == 0 and rows[4]["fumble_lost"] == 1 and rows[4]["fumble"] == 1
    # Without a name map the play-by-play's short name stands rather than nothing.
    assert CR.NflCarries(2026).rows() == []
    bare = CR.NflCarries(2026)
    bare.add(_pbp())
    assert bare.rows()[0]["player"] == "J.Allen"


def test_the_name_is_the_one_the_sites_game_logs_use():
    roster = [{"gsis_id": ALLEN, "full_name": "Joshua Allen", "position": "QB", "jersey_number": "17"},
              {"gsis_id": "00-0099999", "full_name": "Rookie Back", "position": "RB", "jersey_number": "38.0"}]
    weekly = [{"player_id": ALLEN, "player_display_name": "Josh Allen", "position": "QB"}]
    names = CR.nfl_names(2026, roster_rows=roster, weekly_rows=weekly)
    assert names[ALLEN] == {"name": "Josh Allen", "position": "QB", "jersey": "17"}, \
        "the weekly file's display name is what player_game_logs stores"
    assert names["00-0099999"]["name"] == "Rookie Back" and names["00-0099999"]["jersey"] == "38"


# --- the screenshot game ----------------------------------------------------
def test_the_screenshot_game_comes_back_as_the_screenshot():
    conn = _conn_with_allen()
    c = CR.chart(conn, "nfl", "Josh Allen", 2026)
    assert c["player"] == "Josh Allen" and c["holes"] is True and c["jersey"] == "17"
    g = c["games"][0]
    assert (g["id"], g["week"], g["opp"], g["home"], g["date"]) == ("BUF@LA", 5, "LA", False, "2026-10-12"), \
        "games newest first"
    line = g["line"]
    assert (line["n"], line["yds"], line["td"], line["long"]) == (10, 121.0, 1, 22.0), \
        "10 carries, 121 yards and a touchdown — the screenshot's own numbers"
    holes = [x["h"] for x in g["carries"]]
    assert holes.count("LE") == 4 and holes.count("M") == 3 and holes.count("RG") == 2 and holes.count("RE") == 1
    assert [x["q"] for x in g["carries"]] == [1, 1, 2, 3, 4, 4, 4, 4, 5, 5], "in the order they were run"
    assert sum(1 for x in g["carries"] if x["sc"]) == 8
    td = next(x for x in g["carries"] if x["td"])
    assert td["y"] == 1.0 and td["h"] == "M" and td["band"] == "gain", "a touchdown is a gain whatever its length"
    assert all(x["band"] == "gain" for x in g["carries"])
    # The week before: a lost fumble for a loss, and a run with no hole recorded.
    wk4 = c["games"][1]
    assert [x["band"] for x in wk4["carries"]] == ["loss", "gain"]
    assert wk4["carries"][0]["fl"] is True and wk4["carries"][1]["h"] == ""
    assert wk4["home"] is True and wk4["opp"] == "NE"


def test_the_season_view_says_where_he_runs():
    conn = _conn_with_allen()
    c = CR.chart(conn, "nfl", "Josh Allen")
    assert c["season"] == 2026 and c["seasons"] == [2026]
    s = c["season_line"]
    assert s["n"] == 12 and s["yds"] == 125.0 and s["fum"] == 1 and s["stuffed"] == round(1 / 12, 3)
    by = {h["hole"]: h for h in c["by_hole"]}
    assert [h["hole"] for h in c["by_hole"]] == ["LE", "LT", "LG", "M", "RG", "RT", "RE"]
    assert by["LE"]["n"] == 4 and by["LE"]["share"] == round(4 / 11, 3), "a run with no hole is not in the shares"
    assert abs(sum(h["share"] for h in c["by_hole"]) - 1) < 0.01
    assert by["RG"]["ypc"] == 18.0 and by["LG"]["n"] == 0 and by["LG"]["ypc"] is None
    assert c["kinds"]["scramble"]["n"] == 8 and c["kinds"]["designed"]["n"] == 4
    assert c["bands"] == {"loss": 1, "short": 0, "gain": 11}
    assert [d["down"] for d in c["by_down"]] == [1]
    gl = next(z for z in c["by_zone"] if z["zone"] == "gl")
    assert gl["n"] == 1 and gl["td"] == 1


def test_success_is_the_standard_rule():
    assert CR.success(1, 10, 4, False) is True and CR.success(1, 10, 3, False) is False
    assert CR.success(2, 10, 6, False) is True and CR.success(2, 10, 5, False) is False
    assert CR.success(3, 2, 2, False) is True and CR.success(4, 2, 1, False) is False
    assert CR.success(3, 9, 1, True) is True, "a touchdown always is"
    assert CR.success(None, 10, 5, False) is None and CR.success(1, None, 5, False) is None


def test_a_name_finds_his_runs_and_a_stranger_finds_nothing():
    conn = _conn_with_allen()
    assert CR.resolve(conn, "nfl", "Josh Allen") == "Josh Allen"
    assert CR.resolve(conn, "nfl", "josh allen jr.") == "Josh Allen", "case, punctuation and a suffix forgiven"
    assert CR.resolve(conn, "nfl", "Josh Alen") == "", "a different name is not guessed"
    assert CR.chart(conn, "nfl", "Nobody Here") == {}
    assert CR.chart(conn, "cfb", "Josh Allen") == {}, "one league's runs never answer for another's"


# --- RYOE: the league's number where it published one -----------------------
def test_rushing_yards_over_expected_is_the_leagues_own_and_only_where_published():
    conn = _conn_with_allen()
    rows = CR.ngs_rows([
        {"season": "2026", "season_type": "REG", "week": "5", "player_gsis_id": ALLEN,
         "player_display_name": "Josh Allen", "team_abbr": "BUF", "rush_attempts": "10", "rush_yards": "121",
         "rush_touchdowns": "1", "expected_rush_yards": "89.0", "rush_yards_over_expected": "32.0",
         "rush_yards_over_expected_per_att": "3.2", "percent_attempts_gte_eight_defenders": "10.0",
         "avg_time_to_los": "2.9", "efficiency": "3.1"},
        {"season": "2026", "season_type": "REG", "week": "0", "player_gsis_id": ALLEN,
         "player_display_name": "Josh Allen", "team_abbr": "BUF", "rush_attempts": "12",
         "rush_yards_over_expected": "30.5", "rush_yards_over_expected_per_att": "2.5"},
        {"season": "2026", "season_type": "POST", "week": "19", "player_gsis_id": ALLEN,
         "rush_yards_over_expected": "99"},
        {"season": "2026", "week": "5", "player_gsis_id": "NA"},
    ])
    assert len(rows) == 3, "a row with no league id is not stored"
    assert D.upsert_ngs_rushing(conn, rows) == 3
    c = CR.chart(conn, "nfl", "Josh Allen", 2026)
    assert c["games"][0]["ryoe"] == 32.0 and c["games"][0]["xyds"] == 89.0
    assert c["games"][1]["ryoe"] is None, "a week the league did not publish says nothing, not zero"
    assert c["ngs"]["ryoe"] == 30.5 and c["ngs"]["ryoe_per_att"] == 2.5, "week 0 is the season line"


# --- college ----------------------------------------------------------------
GAMES = {"401": {"period": "2026-09-13", "home": "UGA", "away": "ALA",
                 "home_name": "Georgia", "away_name": "Alabama"}}
ROSTER = {"55": {"name": "Nate Frazier", "position": "RB", "headshot": ""}}


def _cfb(**kw):
    row = {"game_id": "401", "season": "2026", "week": "3", "team": "Georgia", "opponent": "Alabama",
           "play_id": "401000000000000101", "period": "2", "clock_minutes": "7", "clock_seconds": "5",
           "yards_to_goal": "60", "down": "1", "distance": "10", "rush_player_id": "55",
           "rush_player": "Nate Frazier", "rush_yds": "12", "touchdown_player": "NA", "fumble_player": "NA"}
    row.update(kw)
    return row


def _cfb_rows():
    return [_cfb(),
            _cfb(play_id="401000000000000205", yards_to_goal="30", rush_yds="30", down="2", distance="3"),
            _cfb(play_id="401000000000000309", touchdown_player="Nate Frazier", yards_to_goal="4", rush_yds="4",
                 down="3", distance="4"),
            _cfb(play_id="401000000000000412", rush_yds="-2", fumble_player="Nate Frazier"),
            _cfb(play_id="401000000000000500", team="Tennessee"),
            _cfb(game_id="999", play_id="999000000000000001"),
            _cfb(play_id="401000000000000600", rush_player="NA")]


def test_college_runs_land_on_the_logs_team_keys_with_no_hole_and_no_clock():
    fold = CR.CfbCarries(2026, GAMES, ROSTER)
    for r in _cfb_rows():
        fold.add(r)
    rows = fold.rows()
    assert len(rows) == 4, "a team not in the game, a game not ingested and a play with no runner are not carries"
    r = rows[0]
    assert (r["sport"], r["season"], r["period"], r["game_id"], r["date"]) == ("cfb", 2026, "2026-09-13", "401", "2026-09-13")
    assert (r["player"], r["position"], r["team"], r["opponent"], r["home"]) == ("Nate Frazier", "RB", "UGA", "ALA", 1)
    assert r["hole"] == "" and r["clock"] == "", "the file records no hole, and its clock is often the drive's"
    assert r["qtr"] == 2 and r["first_down"] == 1 and r["fumble_lost"] is None
    assert rows[1]["td"] == 1, "a gain of exactly the distance to the goal line is a touchdown"
    assert rows[2]["td"] == 1 and rows[2]["first_down"] == 1, "the feed's own scorer"
    assert rows[3]["fumble"] == 1 and rows[3]["fumble_lost"] is None, "fumbled, never 'lost': the file does not say"
    conn = D.connect(":memory:")
    D.upsert_carries(conn, rows)
    c = CR.chart(conn, "cfb", "Nate Frazier")
    assert c["holes"] is False and c["by_hole"] == [] and c["kinds"] == {}
    assert c["games"][0]["line"]["n"] == 4 and c["games"][0]["line"]["td"] == 2
    assert [x["y"] for x in c["games"][0]["carries"]] == [12.0, 30.0, 4.0, -2.0], "in play order (an 18-digit id)"


def test_the_college_runs_ride_the_play_file_read_the_logs_already_make():
    from engine import ingest
    from engine.sources import cfbstats
    tmp = tempfile.mkdtemp()
    try:
        conn = D.connect(os.path.join(tmp, "history.db"))
        D.upsert_games(conn, [{"sport": "cfb", "season": 2026, "period": "2026-09-13", "game_id": "401",
                               # A final the two touchdowns account for: the college parser
                               # drops a week whose scores its touchdowns cannot explain.
                               "home": "UGA", "away": "ALA", "home_score": 14.0, "away_score": 0.0,
                               "extra": json.dumps({"home_name": "Georgia", "away_name": "Alabama"})}])
        keep = (cfbstats._stream, cfbstats.fetch_rosters)
        reads = []

        def stream(url, name, ttl):
            reads.append(name)
            return iter(_cfb_rows())
        cfbstats._stream = stream
        cfbstats.fetch_rosters = lambda season, ttl=0: ROSTER
        try:
            res = ingest.ingest_cfb_player_history(conn, [2026], quiet=True)
        finally:
            cfbstats._stream, cfbstats.fetch_rosters = keep
        assert reads == ["cfb_player_stats_2026.csv"], "one read of the play file, both folds on it"
        n = conn.execute("SELECT COUNT(*) FROM carries WHERE sport='cfb' AND player='Nate Frazier'").fetchone()[0]
        assert n == 4, "the runs are stored by the same pass that stores the logs"
        assert res["rows"] > 0, "the logs are still written"
        assert conn.execute("SELECT value FROM player_game_logs WHERE sport='cfb' AND player='Nate Frazier' "
                            "AND market='carries'").fetchone()[0] == 4.0, "the logs saw every row the fold saw"
        conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tap_hands_every_row_through_once():
    seen = []
    out = list(CR.tap(iter([1, 2, 3]), seen.append))
    assert out == [1, 2, 3] and seen == [1, 2, 3]


# --- keeping it current -----------------------------------------------------
def test_a_finished_game_with_no_chart_keeps_the_nightly_reading():
    conn = D.connect(":memory:")
    today = dt.date(2026, 10, 13)
    assert CR.nfl_behind(conn, 2026, today) is False, "no games, nothing owed"
    D.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": "005", "game_id": "BUF@LA",
                           "home": "LA", "away": "BUF", "home_score": 24.0, "away_score": 27.0,
                           "date": "2026-10-12"},
                          {"sport": "nfl", "season": 2026, "period": "006", "game_id": "BUF@NYJ",
                           "home": "NYJ", "away": "BUF", "home_score": None, "away_score": None,
                           "date": "2026-10-19"}])
    assert CR.nfl_behind(conn, 2026, today) is True
    fold = CR.NflCarries(2026)
    fold.add(_pbp(game_date="2026-10-05", week="4"))
    D.upsert_carries(conn, fold.rows(NAMES))
    assert CR.nfl_behind(conn, 2026, today) is True, "last week's chart is not this week's"
    fold = CR.NflCarries(2026)
    fold.add(_pbp())
    D.upsert_carries(conn, fold.rows(NAMES))
    assert CR.nfl_behind(conn, 2026, today) is False, "caught up: the nightly stops reading"
    assert CR.missing_seasons(conn, "nfl", (2025, 2026)) == [2025]
    assert CR.missing_seasons(conn, "cfb", (2025,)) == [2025]


def test_the_nightly_reads_the_runs_with_the_units_and_fills_last_season_once():
    from engine import maintenance
    src = inspect.getsource(maintenance._run_chores)
    i = src.index("_carries_behind = False")
    block = src[i:src.index("THE DEEP fitters", i) if "THE DEEP fitters" in src[i:] else i + 6000]
    assert "today.weekday() == 1 or _units_behind or _carries_behind" in block, \
        "a Thursday or Monday game's chart does not wait for Tuesday"
    assert "runs = _carries.NflCarries(season)" in block and "units.add(r)" in block and "runs.add(r)" in block, \
        "one read of the file, both folds"
    assert "_carries.PBP_COLS" in block and "names = _carries.nfl_names(season)" in block
    assert "upsert_carries(_pc, runs.rows(names))" in block
    assert "fetch_ngs_rushing()" in block and "missing_seasons(_cc, \"nfl\", (season - 1,))" in block
    assert "backfill_nfl(_cc, past)" in block and "backfill_cfb(_cc, past)" in block


def test_the_box_check_says_what_is_stored_and_reads_the_screenshot_back():
    import carryfill
    empty = D.connect(":memory:")
    lines = carryfill.check(empty)
    assert lines[0].startswith("NFL  no carries stored yet") and lines[1].startswith("CFB  no carries stored yet")
    lines = carryfill.check(_conn_with_allen())
    assert lines[0] == "NFL  2026: 12 carries in 2 games · newest 2026-10-12 · hole recorded on 92%"
    assert lines[-1] == ("CHECK Josh Allen 2026 week 5 at LA: 10 carries, 121 yards, 1 TD — "
                         "the screenshot's numbers")
    src = (ROOT / "carryfill.py").read_text(encoding="utf-8")
    assert '"--fill" in argv' in src, "the check is read-only unless asked to fill"


# --- the endpoint -----------------------------------------------------------
def test_the_endpoint_serves_football_only_and_gates_nothing():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    try:
        path = Path(tmp) / "history.db"
        _conn_with_allen(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_carries({"sport": ["nfl"], "player": ["Josh Allen"]})
        h._players_carries({"sport": ["mlb"], "player": ["Josh Allen"]})
        h._players_carries({"sport": ["nfl"], "player": ["Nobody Here"]})
        h._players_carries({"sport": ["nfl"], "player": ["Josh Allen"], "season": ["2031"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    code, body = sent[0]
    assert code == 200 and body["season_line"]["n"] == 12 and "face" in body
    assert sent[1][0] == 400, "a carry chart is football's"
    assert sent[2] == (200, {})
    assert sent[3][1]["season"] == 2026, "a season he has no runs in falls back to his latest"
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/players/carries"' in src
    i = src.index("def _players_carries(")
    body_src = src[i:src.index("\n    def ", i + 10)]
    assert "_entitled" not in body_src, "where a back ran is a fact, not a pick"


# --- the page ---------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
      const teamNameIn = (lg, a) => ({ LA: "Rams", NE: "Patriots", ALA: "Alabama" })[a] || a;
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


def test_the_page_draws_every_carry_through_its_hole_and_lists_it():
    conn = _conn_with_allen()
    c = CR.chart(conn, "nfl", "Josh Allen", 2026)
    nfl_game = c["games"][0]
    conn2 = D.connect(":memory:")
    fold = CR.CfbCarries(2026, GAMES, ROSTER)
    for r in _cfb_rows():
        fold.add(r)
    D.upsert_carries(conn2, fold.rows())
    cfb = CR.chart(conn2, "cfb", "Nate Frazier")
    got = _node(f"""
      const g = {json.dumps(nfl_game)}, d = {json.dumps(c)}, cg = {json.dumps(cfb["games"][0])}, cd = {json.dumps(cfb)};
      const svg = T.gameChart(g, "nfl", true), season = T.seasonChart(d);
      const csvg = T.gameChart(cg, "cfb", false), cseason = T.seasonChart(cd);
      return {{
        carries: (svg.match(/class="cc-carry"/g) || []).length,
        tds: (svg.match(/class="cc-td"/g) || []).length,
        lanes: ["LE", "LT", "LG", "M", "RG", "RT", "RE"].every((h) => svg.includes(`>${{h}}</text>`)),
        gains: (svg.match(/class="cc-run gain/g) || []).length,
        aria: /aria-label="Carry chart: 10 carries at Rams/.test(svg),
        rays: (season.match(/class="cc-ray /g) || []).length,
        rayLabels: (season.match(/class="cc-raylbl"/g) || []).length,
        faint: (season.match(/class="cc-faint /g) || []).length,
        cCarries: (csvg.match(/class="cc-carry"/g) || []).length,
        cLanes: csvg.includes(">LE</text>"),
        cTicks: csvg.includes(">Q2</text>"),
        cAvg: cseason.includes("cc-avg"),
        list: (T.listHTML(g, "nfl").match(/class="cc-row/g) || []).length,
        listText: T.listHTML(g, "nfl"),
        chip: T.chipLabel(g, "nfl"),
        chip19: T.chipLabel({{ week: 19, home: true, opp: "KC" }}, "nfl"),
        title: T.gameTitle(g, "nfl", 2026),
        spotOwn: T.spot({{ yl: 65 }}, g), spotOpp: T.spot({{ yl: 11 }}, g), spotMid: T.spot({{ yl: 50 }}, g),
        goal: T.downDist({{ dn: 2, ds: 1, yl: 1 }}), dd: T.downDist({{ dn: 3, ds: 4, yl: 30 }}),
        tilesRyoe: T.tilesFor(g.line, 32.4), tilesNo: T.tilesFor(g.line, null),
        noteNfl: T.noteHTML(d), noteCfb: T.noteHTML(cd),
        far: T.proj(0, 30, 30)[1] < T.proj(0, 0, 30)[1],
        narrow: Math.abs(T.proj(20, 30, 30)[0] - 320) < Math.abs(T.proj(20, 0, 30)[0] - 320),
        ymax: [T.yMaxFor([3, 8]), T.yMaxFor([22]), T.yMaxFor([75])],
      }};""")
    if got is None:
        print("  SKIP node not installed")
        return
    assert got["carries"] == 10 and got["gains"] == 10 and got["tds"] == 1, "every carry drawn, the touchdown marked"
    assert got["lanes"] and got["aria"]
    # LE 4, M 3, RG 2, RE 1, RT 1 of the eleven with a hole: five rays, every share past 6%.
    assert got["rays"] == 5 and got["rayLabels"] == 5, "a ray per hole he used, labelled where his share is 6%+"
    assert got["faint"] == 12, "the season view draws every carry under the rays"
    assert got["cCarries"] == 4 and not got["cLanes"] and got["cTicks"] and got["cAvg"], \
        "college: no hole lanes, quarters along the bottom, the average across"
    assert got["list"] == 10 and "Left end" in got["listText"] and "Scramble" in got["listText"]
    assert "Q4 2:00" in got["listText"] and "LA 26" in got["listText"]
    assert got["chip"] == "W5 @ LA" and got["chip19"] == "WC vs KC"
    assert got["title"].startswith("2026 at Rams · Week 5")
    assert (got["spotOwn"], got["spotOpp"], got["spotMid"]) == ("BUF 35", "LA 11", "midfield")
    assert got["goal"] == "2nd & Goal" and got["dd"] == "3rd & 4"
    assert "RYOE" in got["tilesRyoe"] and "+32" in got["tilesRyoe"] and "1st downs" in got["tilesNo"]
    assert "not tracked" in got["noteNfl"] and "doesn’t record which hole" in got["noteCfb"]
    assert got["far"] and got["narrow"], "the field recedes: farther yards higher and narrower"
    assert got["ymax"] == [20, 30, 50]


def test_the_chart_loads_on_first_use_and_runs_under_the_pages_csp():
    # Since 2026-10-14 the player page has one door to his charts in every
    # league with one ("routed correctly like nfl"); a runner's carries
    # lead it through the chart module's kindsFor (pinned in
    # test_the_pick_page_draws_his_chart).
    i = APP_JS.index("function chartDoor(")
    assert '/^(nfl|cfb|nba|wnba|nhl|mlb)$/.test(lg)' in APP_JS[i:i + 300], "every charted league, football's first"
    assert 'ccDoor(player, lg, "auto", "His charts", r.headshot, r)' in APP_JS[i:i + 300]
    assert "+ chartDoor(player, lg, priced.get(mkt) || r0)" in APP_JS, \
        "every profile card variant carries it beside the head-to-head, with the row it shows (face, bet, position)"
    i = APP_JS.index('e.target.closest(".cc-open")')
    loader = APP_JS[i:i + 900]
    assert 'css.href = "css/carrychart.css";' in loader and 'el.src = "js/carrychart.js";' in loader
    assert "m.open(d.carry, d.lg, d.kind, d.face, d.mkt, d.pos, d.opp)" in loader, \
        "the door says which charts, and hands over the face, the bet, his position and tonight's opponent"
    assert "onclick" not in CC_JS and "onerror" not in CC_JS, "no inline handlers under the page's CSP"
    assert "/api/players/carries?sport=" in CC_JS
    for cls in (".cc-run", ".cc-run.loss", ".cc-run.short", ".cc-run.gain", ".cc-td", ".cc-fum", ".cc-los",
                ".cc-ray", ".cc-row", ".cc-tbl", ".cc-legend", ".cc-tip", "prefers-reduced-motion"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only: it re-tints in light mode with the rest"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
