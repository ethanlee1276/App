"""Every pass thrown to a college receiver that the play file names, from 2025.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done ... Can we do the route tracker for CFB?" The college play file has
no air yards and no side of the field, so there is no route to draw; what
it does have, since 2025, is the intended receiver on most incompletions
(78% of 2025's, 92% of 2026's), beside every catch, its yards, the down
and the yards to the goal.

What is pinned, offline:

  * THE TARGETS (engine/targets.CfbTargets): a catch lands on the man who
    caught it even when the file swaps the two names (the logs' own
    `split_pass`); a miss lands on the receiver the file names, never on
    the passer; an interception names nobody and is not a target; 2024
    and before draw nothing; a game not ingested or a school not in it
    draws nothing; a touchdown by the feed's name or the geometry;
  * THE GAMES THE LOGS KEEP: a week the college logs drop (the file lost
    its scoring plays) is dropped from both college charts, and rows an
    earlier read stored for it are cleared — never all of them on a read
    that kept nothing;
  * ONE READ: the nightly college ingest and the chart filler fold the
    carries and the targets off the same pass that writes the logs;
  * THE CHART: `targets.chart(..., sport="cfb")` says it has no air yards,
    keeps the field position split, and no tracking numbers;
  * THE DOOR: /api/players/routes and /api/players/chart serve college;
  * THE PAGE: a college target is drawn straight upfield, a catch as long
    as its yards, a miss a ring at the line; it is called a target chart;
    a college receiver leads with his targets as an NFL one does.

Run directly: `python3 tests/test_a_target_chart_for_every_college_receiver.py`
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

from engine import carries as CR, charts as CH, db as D, targets as TG  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
GAMES = {"401": {"period": "2026-09-13", "home": "UGA", "away": "ALA",
                 "home_name": "Georgia", "away_name": "Alabama"},
         "402": {"period": "2026-09-20", "home": "UGA", "away": "TENN",
                 "home_name": "Georgia", "away_name": "Tennessee"}}
ROSTER = {"77": {"name": "Zachariah Branch", "position": "WR", "headshot": ""},
          "11": {"name": "Gunner Stockton", "position": "QB", "headshot": ""}}


def _row(**kw):
    row = {"game_id": "401", "season": "2026", "week": "3", "team": "Georgia", "play_id": "401000000000000100",
           "period": "1", "yards_to_goal": "75", "down": "1", "distance": "10",
           "completion_player": "Gunner Stockton", "completion_player_id": "11",
           "reception_player": "Zachariah Branch", "reception_player_id": "77",
           "reception_yds": "14", "completion_yds": "14", "incompletion_player": "NA",
           "target_player": "NA", "target_player_id": "NA", "interception_thrown_player": "NA",
           "sack_taken_player": "NA", "touchdown_player": "NA", "rush_player": "NA"}
    row.update(kw)
    return row


def _miss(**kw):
    base = dict(completion_player="NA", completion_player_id="NA", reception_player="NA",
                reception_player_id="NA", reception_yds="NA", completion_yds="NA",
                incompletion_player="Gunner Stockton", target_player="Zachariah Branch", target_player_id="77")
    base.update(kw)
    return _row(**base)


def _rows():
    return [
        _row(),                                                            # a catch for 14
        _miss(play_id="401000000000000200", down="2"),                     # thrown at, incomplete
        # The file swaps the two names on a touchdown; the quarterback's
        # misses (above, below) say who threw it. Geometry: 9 yards from 9.
        _row(play_id="401000000000000300", completion_player="Zachariah Branch", completion_player_id="77",
             reception_player="Gunner Stockton", reception_player_id="11", reception_yds="9",
             completion_yds="9", yards_to_goal="9", touchdown_player="NA", period="2"),
        _miss(play_id="401000000000000400", target_player="Gunner Stockton", target_player_id="11"),  # trick shape
        _row(play_id="401000000000000500", completion_player="NA", reception_player="NA",
             interception_thrown_player="Gunner Stockton"),               # a pick names no receiver
        _miss(play_id="401000000000000600", target_player="NA"),          # a miss the file names nobody on
        _row(play_id="401000000000000700", team="Tennessee"),            # not a school in this game
        _row(game_id="999", play_id="999000000000000001"),               # a game not ingested
        _row(game_id="402", play_id="402000000000000100", reception_yds="31", completion_yds="31",
             yards_to_goal="40", distance="5", touchdown_player="Zachariah Branch", period="3"),
        _miss(game_id="402", play_id="402000000000000200", sack_taken_player="Gunner Stockton",
              incompletion_player="Gunner Stockton"),
    ]


def _fold(season=2026, rows=None):
    fold = TG.CfbTargets(season, GAMES, ROSTER)
    for r in rows or _rows():
        fold.add(r)
    return fold


# --- the targets --------------------------------------------------------------
def test_every_named_target_and_nothing_else():
    rows = _fold().rows()
    assert sorted(r["play_id"] for r in rows) == ["401000000000000100", "401000000000000200",
                                                  "401000000000000300", "402000000000000100",
                                                  "402000000000000200"]
    assert {r["player"] for r in rows} == {"Zachariah Branch"}, "never the passer, even when the names are swapped"
    by = {r["play_id"]: r for r in rows}
    assert by["401000000000000100"]["complete"] == 1 and by["401000000000000100"]["yards"] == 14.0
    assert by["401000000000000100"]["first_down"] == 1 and by["401000000000000100"]["td"] == 0
    assert by["401000000000000200"]["complete"] == 0 and by["401000000000000200"]["yards"] == 0.0
    assert by["401000000000000200"]["interception"] == 0
    assert by["401000000000000300"]["td"] == 1, "a gain of exactly the distance to the goal is a touchdown"
    assert by["402000000000000100"]["td"] == 1 and by["402000000000000100"]["first_down"] == 1, "the feed's scorer"
    r = by["401000000000000100"]
    assert (r["sport"], r["season"], r["period"], r["date"], r["team"], r["opponent"], r["home"]) == \
        ("cfb", 2026, "2026-09-13", "2026-09-13", "UGA", "ALA", 1)
    assert r["position"] == "WR" and r["player_id"] == "77" and r["qtr"] == 1 and r["clock"] == ""
    assert r["air_yards"] is None and r["side"] == "" and r["yac"] is None and r["route"] == "", \
        "the college file records no air yards, no side, no route"
    assert r["yardline_100"] == 75
    assert TG.CfbTargets(2024, GAMES, ROSTER).rows() == [] and _fold(2024).rows() == [], \
        "before 2025 most misses are unnamed: no college target chart"


def test_only_the_games_the_logs_keep():
    fold = _fold()
    assert {r["game_id"] for r in fold.rows({"402"})} == {"402"}
    assert len(fold.rows(None)) == 5, "no keep list keeps them all"
    assert CR.kept_games({"rows": [{"game_id": "401"}, {"game_id": "401"}]}) == {"401"}
    assert CR.kept_games({"rows": []}) is None and CR.kept_games(None) is None, \
        "a parse that kept nothing says nothing about which games are whole"
    conn = D.connect(":memory:")
    runs = CR.CfbCarries(2026, GAMES, ROSTER)
    runs.add({"game_id": "401", "team": "Georgia", "play_id": "1", "rush_player": "Nate Frazier",
              "rush_player_id": "55", "rush_yds": "6", "yards_to_goal": "50", "down": "1", "distance": "10",
              "period": "1"})
    # An earlier read stored a game the logs have since dropped.
    D.upsert_targets(conn, [dict(fold.rows()[0], game_id="400", play_id="old")])
    D.upsert_carries(conn, [dict(runs.rows()[0], game_id="400", play_id="old")])
    n_c, n_t = CR.store_cfb(conn, 2026, runs, _fold(), {"401", "402"})
    assert (n_c, n_t) == (1, 5)
    assert conn.execute("SELECT COUNT(*) FROM targets WHERE game_id='400'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM carries WHERE game_id='400'").fetchone()[0] == 0, \
        "a dropped game's rows are cleared from both charts"
    CR.store_cfb(conn, 2026, runs, _fold(), None)
    assert conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == 5, "nothing cleared on a read that kept none"


def test_one_read_feeds_the_logs_the_carries_and_the_targets():
    from engine import ingest
    from engine.sources import cfbstats
    tmp = tempfile.mkdtemp()
    try:
        conn = D.connect(os.path.join(tmp, "history.db"))
        for gid, period, away, away_name, score in (("401", "2026-09-13", "ALA", "Alabama", 7.0),
                                                     ("402", "2026-09-20", "TENN", "Tennessee", 7.0)):
            D.upsert_games(conn, [{"sport": "cfb", "season": 2026, "period": period, "game_id": gid,
                                   "home": "UGA", "away": away, "home_score": score, "away_score": 0.0,
                                   "extra": json.dumps({"home_name": "Georgia", "away_name": away_name})}])
        keep = (cfbstats._stream, cfbstats.fetch_rosters)
        reads = []

        def stream(url, name, ttl):
            reads.append(name)
            return iter(_rows())
        cfbstats._stream = stream
        cfbstats.fetch_rosters = lambda season, ttl=0: ROSTER
        try:
            ingest.ingest_cfb_player_history(conn, [2026], quiet=True)
            n_c = CR.backfill_cfb(conn, 2026)
        finally:
            cfbstats._stream, cfbstats.fetch_rosters = keep
        assert reads == ["cfb_player_stats_2026.csv"] * 2, "one read each: the nightly, then the filler"
        assert n_c == 0, "these plays carry no runs"
        got = conn.execute("SELECT COUNT(*), SUM(complete) FROM targets WHERE sport='cfb' AND "
                           "player='Zachariah Branch'").fetchone()
        assert tuple(got) == (5, 3), "the targets are stored by the same pass that stores the logs"
        conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- the chart --------------------------------------------------------------------
def _conn(path=":memory:"):
    conn = D.connect(path)
    D.upsert_targets(conn, _fold().rows())
    return conn


def test_the_college_chart_says_what_it_has():
    d = TG.chart(_conn(), "Zachariah Branch", sport="cfb")
    assert d["sport"] == "cfb" and d["air"] is False and d["routes"] is False and d["ngs"] == {}
    assert [g["id"] for g in d["games"]] == ["402", "401"], "newest first"
    assert d["games"][1]["line"]["tgt"] == 3 and d["games"][1]["line"]["rec"] == 2
    assert d["season_line"]["tgt"] == 5 and d["season_line"]["td"] == 2 and d["season_line"]["yds"] == 54.0
    zones = {z["zone"]: z["tgt"] for z in d["by_field"]}
    assert zones == {"own": 3, "mid": 1, "rz": 1}, "9 yards out is the red zone, not the goal line"
    assert TG.chart(_conn(), "Zachariah Branch") == {}, "the NFL's chart is the NFL's"
    assert TG.chart(_conn(), "zachariah branch", sport="cfb")["player"] == "Zachariah Branch"


def test_the_doors_serve_college():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        _conn(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_routes({"sport": ["cfb"], "player": ["Zachariah Branch"]})
        h._players_chart({"kind": ["routes"], "sport": ["cfb"], "player": ["Zachariah Branch"]})
        h._players_routes({"sport": ["nba"], "player": ["Zachariah Branch"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0][0] == 200 and sent[0][1]["air"] is False and "face" in sent[0][1]
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "routes" and sent[1][1]["sport"] == "cfb"
    assert sent[2][0] == 400
    assert CH.known("routes", "cfb")


# --- the page -----------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
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


def test_the_page_draws_college_targets_straight_upfield():
    d = TG.chart(_conn(), "Zachariah Branch", sport="cfb")
    got = _node(f"""
      const d = {json.dumps(d)}, g = d.games[1];
      const svg = T.cfbTargetGame(g), season = T.cfbTargetSeason(d), list = T.routeList(g);
      return {{
        catches: (svg.match(/class="rc-route/g) || []).length, misses: (svg.match(/class="rc-miss/g) || []).length,
        tds: (svg.match(/class="cc-td"/g) || []).length, marks: (svg.match(/class="cc-carry"/g) || []).length,
        aria: /aria-label="Target chart: 3 targets vs ALA\\. Each one is listed below\\."/.test(svg),
        seasonMarks: (season.match(/class="cc-carry"/g) || []).length, avg: season.includes("18.0 a catch"),
        rows: (list.match(/class="cc-row/g) || []).length, list,
        tiles: T.cfbTargetTiles(d.season_line), note: T.cfbTargetNote(d), tables: T.routeTables(d),
        title: T.kindOf("routes", "cfb").title, nflTitle: T.kindOf("routes", "nfl").title,
        kinds: [T.kindsFor("cfb", "receptions", "WR"), T.kindsFor("cfb", "rush_yds", "RB"), T.kindsFor("cfb", "rec_yds", "")],
      }};
    """)
    if got is None:
        return
    assert got["catches"] == 2 and got["misses"] == 1 and got["tds"] == 1 and got["marks"] == 3 and got["aria"]
    assert got["seasonMarks"] == 5 and got["avg"], "54 yards on three catches: 18.0 a catch over the season"
    assert got["rows"] == 3 and ">Inc<" in got["list"] and ">+14<" in got["list"] and "Red zone" in got["list"]
    assert ">5-3<" in got["tiles"] and "Yds/catch" in got["tiles"] and "Catch rate" in got["tiles"]
    assert "aDOT" not in got["tiles"], "no air yards in the college file, so no depth of target"
    assert "92%" in got["note"] and "78%" in got["note"] and "interception" in got["note"]
    assert "By field position" in got["tables"] and "How far past the line" not in got["tables"]
    assert got["title"] == "Target chart" and got["nflTitle"] == "Route chart"
    assert got["kinds"] == [["routes", "carries"], ["carries", "routes"], ["routes", "carries"]], \
        "a college receiver leads with his targets, a back with his carries"


def test_the_styles_and_the_csp():
    assert "onclick" not in CC_JS and "onerror" not in CC_JS and not re.search(r"on(error|load)\s*=", CC_JS)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
