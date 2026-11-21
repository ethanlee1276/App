"""Every kick a kicker tried: the NFL kicker chart.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list
had an NFL kicker chart on it.

What is pinned, offline, on play-by-play rows shaped like nflverse's:

  * THE KICKS (engine/kicks.NflKicks): every field goal and extra point,
    made, missed, blocked, or an extra point that never got off; a fake,
    a two-point try and preseason are no kicks; a field goal with no kick
    distance on the row is the line of scrimmage plus 17;
  * THE BOX SCORE'S LINE: field goals and extra points made and tried,
    his points (three a field goal, one an extra point), his long, his
    50-yarders, and a blocked kick an attempt not made;
  * THE SPLITS: each distance band beside the league's rate that season,
    indoors and outdoors, wind and cold outdoors only, late and close;
  * ONE READ: the kicks ride the nightly play-by-play read the other
    football charts share, last season's are read once, and the chart
    filler owes the table like theirs;
  * THE DOOR AND THE PAGE: /api/players/chart answers kind=kicks for the
    NFL only; a kicking bet draws it; the parlay checker's kicking leg
    has its door; the drawing is its own module.

Run directly: `python3 tests/test_a_kicker_chart_for_every_kicker.py`
"""
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import charts as CH, chartfill as CF, db as D, kicks as K, maintenance as M  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
KK_JS = (ROOT / "web" / "js" / "chart-kicks.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
SLIP_JS = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")

TUCKER, AUBREY = "00-0029597", "00-0036162"
NAMES = {TUCKER: {"name": "Justin Tucker", "position": "K", "jersey": "9"},
         AUBREY: {"name": "Brandon Aubrey", "position": "K", "jersey": "17"}}


def _row(**kw):
    row = {"play_type": "field_goal", "season": "2026", "season_type": "REG", "week": "5",
           "game_id": "2026_05_BAL_DEN", "home_team": "DEN", "away_team": "BAL", "posteam": "BAL",
           "defteam": "DEN", "game_date": "2026-10-11", "field_goal_attempt": "1", "field_goal_result": "made",
           "extra_point_attempt": "0", "extra_point_result": "NA", "kick_distance": "47",
           "kicker_player_id": TUCKER, "kicker_player_name": "J.Tucker", "score_differential": "3",
           "qtr": "2", "quarter_seconds_remaining": "271", "roof": "outdoors", "surface": "grass",
           "temp": "41", "wind": "12", "two_point_attempt": "0", "yardline_100": "29", "play_id": "100"}
    row.update(kw)
    return row


#: Tucker at Denver, in play order: a 47 made, a 55 missed, a 33 blocked,
#: two extra points (one good, one that never got off), a field goal with
#: no distance on the row (the 12, so 29 yards); and what is no kick: a
#: fake, a two-point try, a preseason kick.
PLAYS = [
    _row(play_id="100"),
    _row(play_id="200", field_goal_result="missed", kick_distance="55", qtr="4", score_differential="-2"),
    _row(play_id="300", field_goal_result="blocked", kick_distance="33", qtr="4"),
    _row(play_id="400", play_type="extra_point", field_goal_attempt="0", field_goal_result="NA",
         extra_point_attempt="1", extra_point_result="good", kick_distance="33"),
    _row(play_id="500", play_type="extra_point", field_goal_attempt="0", field_goal_result="NA",
         extra_point_attempt="1", extra_point_result="aborted", kick_distance="NA"),
    _row(play_id="600", kick_distance="NA", yardline_100="12", qtr="1", score_differential="0"),
    _row(play_id="700", play_type="run", field_goal_attempt="0", field_goal_result="NA"),
    _row(play_id="800", play_type="extra_point", field_goal_attempt="0", field_goal_result="NA",
         extra_point_attempt="0", two_point_attempt="1"),
    _row(play_id="900", season_type="PRE"),
]


def _fold(rows=PLAYS, season=2026):
    fold = K.NflKicks(season)
    for r in rows:
        fold.add(r)
    return fold.rows(NAMES)


def _conn(path=":memory:"):
    conn = D.connect(path)
    D.upsert_kicks(conn, _fold())
    # Week 4 at home under a dome, and another kicker's season for the
    # league's rate.
    D.upsert_kicks(conn, _fold([_row(play_id="55", week="4", game_id="2026_04_CLE_BAL", home_team="BAL",
                                     away_team="CLE", defteam="CLE", game_date="2026-10-04", roof="dome",
                                     temp="NA", wind="NA", kick_distance="51")]))
    D.upsert_kicks(conn, _fold([_row(play_id=str(1000 + i), posteam="DAL", defteam="NYG", home_team="DAL",
                                     away_team="NYG", game_id="2026_05_NYG_DAL", kicker_player_id=AUBREY,
                                     kicker_player_name="B.Aubrey", kick_distance=str(d),
                                     field_goal_result="made" if i % 4 else "missed")
                                for i, d in enumerate((44, 46, 48, 41, 52, 58, 25, 36))]))
    D.upsert_kicks(conn, _fold([_row(play_id="77", season="2025", week="9")], season=2025))
    return conn


def test_every_kick_and_nothing_that_is_not_one():
    rows = _fold()
    assert [r["play_id"] for r in rows] == ["100", "200", "300", "400", "500", "600"]
    by = {r["play_id"]: r for r in rows}
    assert by["100"]["player"] == "Justin Tucker" and by["100"]["kind"] == "fg" and by["100"]["distance"] == 47
    assert by["300"]["result"] == "blocked" and by["400"]["kind"] == "xp" and by["400"]["result"] == "made"
    assert by["500"]["result"] == "aborted", "an extra point that never got off"
    assert by["600"]["distance"] == 29, "no distance on the row: the line of scrimmage plus 17"
    assert by["100"]["home"] == 0 and by["100"]["opponent"] == "DEN" and by["100"]["game_id"] == "BAL@DEN"
    assert by["100"]["wind"] == 12.0 and by["100"]["temp"] == 41.0 and by["100"]["score_diff"] == 3
    assert by["100"]["clock"] == "4:31" and by["200"]["qtr"] == 4


def test_the_box_score_s_line_and_the_splits():
    d = K.chart(_conn(), "justin tucker")
    assert d["player"] == "Justin Tucker" and d["seasons"] == [2026, 2025] and d["position"] == "K"
    g = d["games"][0]
    assert g["week"] == 5 and g["opp"] == "DEN" and g["home"] is False
    L = g["line"]
    assert (L["fga"], L["fgm"], L["xpa"], L["xpm"], L["pts"]) == (4, 2, 2, 1, 7)
    assert L["long"] == 47 and L["blocked"] == 1 and (L["fg50"], L["fga50"]) == (0, 1) and L["n"] == 6
    assert [k["d"] for k in g["kicks"] if k["k"] == "fg"] == [47, 55, 33, 29], "in the order he tried them"
    S = d["season_line"]
    assert (S["fga"], S["fgm"], S["fg50"]) == (5, 3, 1) and S["long"] == 51
    bands = {b["key"]: b for b in d["by_band"]}
    assert bands["u30"]["fga"] == 1 and bands["50"]["fga"] == 2 and bands["50"]["fgm"] == 1
    # The league's 40-49: Tucker's 47 (made) and Aubrey's 44, 46, 48, 41
    # (the 44 missed) — 4 of 5.
    assert bands["40s"]["league"] == 0.8
    place = {x["key"]: x for x in d["by_place"]}
    assert place["in"]["fga"] == 1 and place["out"]["fga"] == 4
    weather = {x["key"]: x for x in d["by_weather"]}
    assert weather["windy"]["fga"] == 4 and "cold" not in weather, "41°F is not under 40"
    moment = {x["key"]: x for x in d["by_moment"]}
    assert moment["late"]["fga"] == 2 and moment["late"]["fgm"] == 0
    assert moment["close"]["fga"] == 5
    assert K.chart(_conn(), "Justin Tucker", 2025)["season"] == 2025
    assert K.chart(_conn(), "Nobody") == {}


def test_it_rides_the_nightly_read_and_the_filler_owes_it():
    src = inspect.getsource(M)
    i = src.index("_carries_behind = False")
    block = src[i:src.index("# The DEEP fitters", i)]
    assert "_kk.nfl_behind(_cconn, _cseason, today)" in block, "a game with no kicks starts the read too"
    assert "kicked = _kicks.NflKicks(season)" in block and "kicked.add(r)" in block
    assert "+ _kicks.PBP_COLS + _targets.PBP_COLS), also=_each)" in block, "one read, every fold"
    assert "upsert_kicks(_pc, kicked.rows(names))" in block
    assert "_kk2.missing_seasons(_kc, (season - 1,))" in block and "_kk2.backfill_nfl(_kc, past)" in block
    assert ("nfl", "kicks") in CF.TABLES
    fill = inspect.getsource(CF.fill)
    assert "KK.NflKicks(s)" in fill and "kicked.add(r)" in fill and "db.upsert_kicks(conn, kicked.rows(names))" in fill
    assert "kicks" in __import__("engine.carries", fromlist=["CHART_TABLES"]).CHART_TABLES


def test_the_door_answers_the_kicker_chart():
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
        h._players_chart({"kind": ["kicks"], "sport": ["nfl"], "player": ["Justin Tucker"]})
        _conn(path).close()
        h._players_chart({"kind": ["kicks"], "sport": ["nfl"], "player": ["Justin Tucker"]})
        h._players_chart({"kind": ["kicks"], "sport": ["cfb"], "player": ["Justin Tucker"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "kicks" and sent[1][1]["season_line"]["fga"] == 5
    assert "face" in sent[1][1] and sent[2][0] == 400
    assert CH.known("kicks", "nfl") and not CH.known("kicks", "cfb")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{KK_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_every_field_goal():
    d = K.chart(_conn(), "Justin Tucker")
    got = _node(f"""
      const d = {json.dumps(d)}, P = T.DRAW.kicks, g = d.games[0];
      const game = P.game(g, d), season = P.season(d);
      return {{
        marks: (game.match(/class="cc-carry"/g) || []).length, flights: (game.match(/kk-flight/g) || []).length,
        blocked: (game.match(/cx-mark blocked/g) || []).length, faint: (season.match(/kk-ball faint|kk-ball (made|missed|blocked) faint|blocked faint/g) || []).length,
        pills: (season.match(/class="kk-pill"/g) || []).length, list: P.list(g, d), tiles: P.gameSide(g, d),
        side: P.seasonSide(d), tables: P.splits(d), chip: P.chip(g), count: P.count(d.season_line),
        note: P.note(d), tip: P.tip(g.kicks[1], g, d), items: P.items(g).length,
        kinds: [T.kindsFor("nfl", "kick_pts", "K"), T.kindsFor("nfl", "fg_made", ""), T.kindsFor("nfl", "tackles_ast", "LB"),
                T.kindsFor("cfb", "kick_pts", "K")],
        title: T.KIND.kicks.title,
      }};
    """)
    if got is None:
        return
    assert got["marks"] == 4 and got["flights"] == 3 and got["blocked"] == 1, "four field goals; a blocked kick has no flight"
    assert got["pills"] == 4 and got["items"] == 6
    assert "Aborted (never got off)" in got["list"] and "Extra point" in got["list"] and "12 mph wind" in got["list"]
    assert "down 2" in got["list"] and ">2/4<" in got["tiles"] and ">Points<" in got["tiles"]
    assert "league" in got["tables"].lower() and "In the weather" in got["tables"]
    assert got["chip"] == "2/4 FG" and got["count"] == "5 field goals" and "set side by side" in got["note"]
    assert "55-yd field goal · Missed" in got["tip"]
    assert got["kinds"] == [["kicks"], ["kicks"], [], []] and got["title"] == "Kicker chart"


def test_every_door_and_the_module():
    # A kicking leg's door asks for his charts with its bet (2026-10-14);
    # kindsFor sends a kicking bet to his kicks (pinned above).
    i = SLIP_JS.index("function chartsHTML(")
    assert 'data-kind="auto" data-mkt="${esc(l.market || "")}"' in SLIP_JS[i:i + 600]
    assert 'nfl: ["carries", "routes", "passes", "kicks", "role"]' in CC_JS, "a door with no bet still finds his kicks"
    assert 'kicks: "kicks"' in CC_JS and 'Q.draw("kicks"' in KK_JS
    assert "onclick" not in KK_JS and "onerror" not in KK_JS and not re.search(r"on(error|load)\s*=", KK_JS)
    for cls in (".kk-svg", ".kk-post", ".kk-flight.missed", ".kk-ball.made", ".kk-pill rect", ".dt.kk-x"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


def test_the_past_seasons_backfill_leaves_no_download_it_made():
    # Box run, 2026-10-17: kick physics had 1,467 kicks and the bar needs
    # 2,000 held out, so past seasons are read once — and a season's ~100 MB
    # play file, which nothing prunes, goes once read unless it was there.
    t = Path(tempfile.mkdtemp())
    conn = D.connect(t / "h.db")
    (t / "pbp_2022.csv").write_text("kept")
    real, said = K.backfill_nfl, []

    def fake(c, season):               # the fetch reuses a cached file
        f = t / f"pbp_{season}.csv"
        if not f.exists():
            f.write_text("downloaded")
        return 7
    K.backfill_nfl = fake
    try:
        got = K.backfill_past(conn, (2022, 2023), say=said.append, cache_dir=t)
    finally:
        K.backfill_nfl = real
    assert got == {2022: 7, 2023: 7}, got
    assert (t / "pbp_2022.csv").read_text() == "kept" and not (t / "pbp_2023.csv").exists()
    assert said == ["  2022: 7 kick(s) stored", "  2023: 7 kick(s) stored · its download removed"], said


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
