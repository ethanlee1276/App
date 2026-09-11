"""Under pressure — clutch, reliability, comeback and choke, per team.

Ethan, 2026-09-05: "Add under pressure data for teams, like clutch win %
and reliability % and comeback % and choke % and see if we can have that
as live data as well like when games are going."

Counted in engine/pressure.py from the same finished games as the
standings table, ridden on standings_<sport>.json, and read in three
places on the page: a ranked section on the standings page, a two-team
table on the game page, and a line on the live card that reads the
scoreboard against the two teams' rates. The situational sentence runs
for real in node (skipped without it).

Run directly: `python3 tests/test_pressure.py`
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, pressure

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _conn(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def _insert(conn, sport, season, rows):
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score, spread, extra) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(sport, season, p, f"{sport}{season}g{i}", h, a, hs, as_, sp, ex)
         for i, (p, h, a, hs, as_, sp, ex) in enumerate(rows)])
    conn.commit()


# Team A's season, one row per kind of thing the counters must tell apart.
NFL_2025 = [
    # period, home, away, hs, as, spread (home-relative), extra
    ("001", "A", "B", 23, 20, -3.0, None),    # favourite, won by 3: clutch win, reliable
    ("002", "A", "C", 20, 22, -3.0, None),    # favourite, lost by 2: a choke
    ("003", "B", "A", 14, 24, -4.0, None),    # underdog, won by 10: a comeback, not one-score
    ("004", "A", "D", 34, 14, -7.5, None),    # favourite, won by 20: reliable, not one-score
    ("005", "C", "A", 13, 13, 0.0, None),     # pick'em, tied: one-score, not won, nobody favoured
    ("006", "A", "D", 16, 17, None, '{"ml":[-150,130]}'),  # favourite by moneyline, lost by 1: choke
    ("019", "A", "B", 21, 20, -3.0, None),    # postseason: never counted
    # The other three, so four teams reach four games.
    ("007", "B", "C", 27, 20, -3.0, None),
    ("008", "C", "D", 27, 20, -3.0, None),
    ("009", "D", "B", 27, 20, -3.0, None),
]


def test_the_four_rates_count_what_they_say_they_count():
    conn = _conn()
    _insert(conn, "nfl", 2025, NFL_2025)
    got = pressure.team_pressure(conn, "nfl", 2025)
    a = got["teams"]["A"]
    assert (a["games"], a["wins"], a["ties"]) == (6, 3, 1), a
    assert a["record"] == "3-2-1"
    assert (a["one_score_games"], a["one_score_wins"]) == (4, 1)
    assert a["clutch"] == 25.0
    assert (a["fav_games"], a["fav_wins"], a["fav_one_score_losses"]) == (4, 2, 2)
    assert a["reliability"] == 50.0 and a["choke"] == 50.0
    assert (a["dog_games"], a["dog_wins"]) == (1, 1) and a["comeback"] == 100.0
    assert got["season_used"] == 2025 and got["one_score"] == 8 and got["lined"] is True
    assert got["note"] == ""
    # Ranked high-first, with the count beside every rate; a rate on
    # fewer than three games of its kind is a fact about the team but
    # not a rank — A's 100% comeback is on one game.
    clutch = got["ranked"]["clutch"]
    assert [(r["rank"], r["team"], r["value"], r["n"]) for r in clutch] == [
        (1, "D", 66.7, 3), (2, "C", 50.0, 4), (3, "B", 33.3, 3), (4, "A", 25.0, 4)]
    assert "A" not in [r["team"] for r in got["ranked"]["comeback"]]
    assert got["ranked"]["choke"][0] == {"rank": 1, "team": "A", "value": 50.0, "n": 4, "record": "3-2-1"}
    assert got["min_rate_n"] == 3 and got["min_games"] == 4


def test_the_favourite_is_the_spread_then_the_shorter_moneyline_then_nobody():
    f = pressure.favourite
    assert f(-3.0, None) == "home" and f(3.0, None) == "away" and f(0.0, None) is None
    assert f(None, '{"ml":[-150,130]}') == "home"
    assert f(None, '{"ml":[140,-160]}') == "away"
    assert f(None, '{"ml":[-110,-110]}') is None
    assert f(None, None) is None and f(None, "{}") is None and f(None, "not json") is None
    assert f(None, {"ml": [-200, 170]}) == "home", "a dict works too"


def test_a_thin_season_falls_back_to_the_one_before_and_says_so():
    conn = _conn()
    _insert(conn, "nfl", 2025, NFL_2025)
    _insert(conn, "nfl", 2026, [("001", "A", "B", 30, 27, -3.0, None)])
    got = pressure.team_pressure(conn, "nfl", 2026)
    assert got["season"] == 2026 and got["season_used"] == 2025
    assert got["teams"]["A"]["games"] == 6, "2026's one game is not mixed into 2025's"
    assert pressure.team_pressure(conn, "nfl", 2028) is None, "neither 2028 nor 2027 has games"
    assert pressure.team_pressure(conn, "ufc", 2025) is None, "no one-score margin defined"


def test_a_sport_with_no_closing_lines_keeps_clutch_and_says_why_the_rest_are_missing():
    conn = _conn()
    rows = [("2025-06-0%d" % (i + 1), h, a, hs, as_, None, None) for i, (h, a, hs, as_) in enumerate([
        ("NYY", "BOS", 3, 2), ("BOS", "NYY", 5, 1), ("NYY", "TOR", 2, 3), ("TOR", "NYY", 4, 3),
        ("BOS", "TOR", 1, 0), ("TOR", "BOS", 6, 2), ("BAL", "NYY", 2, 1), ("BAL", "BOS", 3, 2),
        ("TOR", "BAL", 8, 1), ("BAL", "TOR", 4, 3)])]
    _insert(conn, "mlb", 2025, rows)
    got = pressure.team_pressure(conn, "mlb", 2025)
    assert got["lined"] is False and got["one_score"] == 1
    assert "No closing lines on file for MLB" in got["note"]
    bal = got["teams"]["BAL"]
    assert bal["clutch"] == 100.0 and bal["one_score_games"] == 3
    assert bal["reliability"] is None and bal["comeback"] is None and bal["choke"] is None
    assert got["ranked"]["clutch"][0]["team"] == "BAL"
    assert got["ranked"]["reliability"] == [] and got["ranked"]["choke"] == []


def test_college_rows_still_keyed_by_espn_id_are_read_under_the_board_abbreviation():
    conn = _conn()
    rows = [("2025-09-%02d" % (i + 1), h, a, hs, as_, sp, None) for i, (h, a, hs, as_, sp) in enumerate([
        ("espn:61", "espn:228", 24, 21, -7.0), ("espn:228", "espn:61", 10, 31, 3.0),
        ("espn:61", "espn:99", 42, 7, -20.0), ("espn:99", "espn:61", 20, 27, 6.5),
        ("espn:228", "espn:99", 14, 13, -1.0), ("espn:99", "espn:228", 30, 10, -3.0),
        ("espn:2", "espn:61", 17, 20, 2.5), ("espn:2", "espn:228", 21, 24, -3.0),
        ("espn:99", "espn:2", 28, 27, -3.0), ("espn:2", "espn:99", 35, 3, -10.0)])]
    _insert(conn, "cfb", 2025, rows)
    got = pressure.team_pressure(conn, "cfb", 2025,
                                 id_to_abbr={"61": "UGA", "228": "CLEM", "99": "LSU", "2": "AUB"})
    assert set(got["teams"]) == {"UGA", "CLEM", "LSU", "AUB"}
    uga = got["teams"]["UGA"]
    assert uga["record"] == "5-0" and uga["fav_games"] == 5 and uga["reliability"] == 100.0
    assert uga["one_score_games"] == 3 and uga["clutch"] == 100.0


def test_the_standings_build_rides_the_table_on_the_same_payload():
    import standings_build
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = _conn(path); _insert(conn, "nfl", 2025, NFL_2025); conn.close()
    keep = (standings_build.connect, standings_build._live_table)
    standings_build.connect = lambda: _conn(path)
    standings_build._live_table = lambda s, se, c: (None, "offline")
    try:
        blob = standings_build.build("nfl", 2025, today="2026-03-01")
        assert blob["pressure"]["season_used"] == 2025
        assert blob["pressure"]["teams"]["A"]["choke"] == 50.0
        assert blob["games_counted"] == 9, "the table and the rates count the same regular season"
        empty = standings_build.build("nfl", 2030, today="2030-11-01")
        assert "pressure" not in empty, "nothing to say is no key, not an empty table"
    finally:
        standings_build.connect, standings_build._live_table = keep


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n(function")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("PRESSURE_ONE_SCORE")}
      {_fn("pressurePct")}
      {_fn("pressureLate")}
      {_fn("pressureFav")}
      {_fn("pressureSituation")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


PR = """{ season: 2026, season_used: 2025, teams: {
      KC: { clutch: 64.3, reliability: 81.0, comeback: 40.0, choke: 12.5 },
      DEN: { clutch: 84.6, reliability: 70.0, comeback: 80.0, choke: 30.0 },
      NYJ: { clutch: null, reliability: null, comeback: null, choke: null } } }"""


def test_the_live_line_reads_the_scoreboard_against_the_two_teams_rates():
    got = _node(f"""
      const pr = {PR};
      const s = (g) => pressureSituation({{ sport: "nfl", g, pr }});
      const base = {{ home: "KC", away: "DEN", spread: -3.0 }};
      return {{
        pre: s({{ ...base, live: {{ state: "scheduled" }} }}),
        final: s({{ ...base, live: {{ state: "final", home_score: 27, away_score: 24, period: "F" }} }}),
        favTrails: s({{ ...base, live: {{ state: "live", home_score: 17, away_score: 20, period: "Q3" }} }}),
        favUpLate: s({{ ...base, live: {{ state: "live", home_score: 24, away_score: 20, period: "Q4", clock: "2:11" }} }}),
        tiedLate: s({{ ...base, live: {{ state: "live", home_score: 20, away_score: 20, period: "OT" }} }}),
        eightUp: s({{ ...base, live: {{ state: "live", home_score: 28, away_score: 20, period: "Q4" }} }}),
        nineUp: s({{ ...base, live: {{ state: "live", home_score: 29, away_score: 20, period: "Q4" }} }}),
        noFavLate: s({{ home: "KC", away: "DEN", live: {{ state: "live", home_score: 21, away_score: 17, period: "4th" }} }}),
        early: s({{ ...base, live: {{ state: "live", home_score: 21, away_score: 3, period: "Q2" }} }}),
        awayFav: s({{ home: "KC", away: "DEN", spread: 2.5, live: {{ state: "live", home_score: 14, away_score: 10, period: "Q1" }} }}),
        unknown: s({{ home: "KC", away: "NE", live: {{ state: "live", home_score: 1, away_score: 0, period: "Q4" }} }}),
        noRates: s({{ home: "KC", away: "NYJ", live: {{ state: "scheduled" }} }}),
        late: ["Q4", "4th", "OT", "2OT", "Q3", "1st", "", null].map((p) => pressureLate("nfl", p)),
        mlbLate: ["Top 9th", "Bot 7th", "Mid 6th", "3rd", ""].map((p) => pressureLate("mlb", p)),
        fav: [pressureFav({{ favorite: "DEN", home: "KC", away: "DEN", spread: -3 }}),
              pressureFav({{ home: "KC", away: "DEN", spread: -3 }}),
              pressureFav({{ home: "KC", away: "DEN", spread: 3 }}),
              pressureFav({{ home: "KC", away: "DEN", spread: 0 }}),
              pressureFav({{ home: "KC", away: "DEN" }})],
        pct: [pressurePct(64.3), pressurePct(null), pressurePct(0)],
      }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["pre"] == "KC wins 64% of its one-score games · DEN 85%"
    assert got["final"] == got["pre"], "after the game, the season rates again"
    assert got["favTrails"] == "KC trails as the favourite · wins 81% when favoured · DEN wins 80% as the underdog"
    assert got["favUpLate"] == "One-score game late · KC has let 13% of these slip as the favourite · DEN wins 85% of its one-score games"
    assert got["tiedLate"] == got["favUpLate"], "tied late asks the favourite the same question"
    assert got["eightUp"] == got["favUpLate"], "eight points is one score — a touchdown and two"
    assert got["nineUp"] == "KC clutch 64% · DEN clutch 85%", "nine is not"
    assert got["noFavLate"] == "One-score game late · KC wins 64% of these · DEN 85%"
    assert got["early"] == "KC clutch 64% · DEN clutch 85%"
    assert got["awayFav"] == "DEN trails as the favourite · wins 70% when favoured · KC wins 40% as the underdog"
    assert got["unknown"] == "", "a team with no rates gets no sentence, not a dash-filled one"
    assert got["noRates"] == "KC wins 64% of its one-score games · NYJ —"
    assert got["late"] == [True, True, True, True, False, False, False, False]
    assert got["mlbLate"] == [True, True, False, False, False]
    assert got["fav"] == ["DEN", "KC", "DEN", None, None]
    assert got["pct"] == ["64%", "—", "0%"]


def test_the_three_surfaces_read_the_same_payload():
    assert "${pressureHTML(d.pressure, d)}" in APP, "the standings page, under the rankings"
    assert "    ${linesGrid}\n    ${pressureLiveHTML(sport, g)}\n    ${playsHTML(g)}" in APP, "the live card"
    assert "  const games = await fetchAllLive();\n  await pressureWarm(games.map((x) => x.sport));" in APP
    assert "${pressurePairHTML(state.sport, g)}" in APP, "the game page"
    ph = _fn("pressureHTML")
    assert 'if (!pr || !pr.ranked) return "";' in ph
    assert "last season’s, until this one has four games a team" in ph
    assert "won as the market’s underdog" in APP, "comeback says which underdog it means"
    pp = _fn("pressurePairHTML")
    assert "if (_standingsCache[sport] === undefined) {" in pp and 'document.getElementById("gp-pressure")' in pp
    assert 'return `<div id="gp-pressure" hidden></div>`;' in pp
    for sel in (".pr-buckets", ".pr-table", ".pr-defs", ".lb-pressure", ".lb-pressure .lb-pk"):
        assert sel in CSS, sel
    lb = CSS[CSS.index(".lb-pressure {"):]
    lb = lb[:lb.index("}")]
    assert "var(--hairline) solid var(--border)" in lb and "var(--lh-body)" in lb


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
