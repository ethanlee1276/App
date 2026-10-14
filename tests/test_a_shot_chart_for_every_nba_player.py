"""Every shot an NBA player took, where from, made or missed: the shot chart.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl."

What is pinned, offline, on a fixture play-by-play and box score shaped
the way the nba_api project documents the league's CDN feed:

  * THE FOLD (engine/nba/shots.fold): one row per field-goal attempt and
    per free throw, named by the box score (the play-by-play carries an
    initial), on the shooter's team; the league's zones (restricted area,
    the paint, mid-range, the corner three, above the break) from the
    feed's own area word or from where it was taken; an assist only on a
    make; nothing that is not a shot;
  * THE GAMES: the season file's finals (never the preseason or the
    All-Star Game); last season by the league's own numbering, newest
    first; a stored game is never read again; five misses in a row on
    last season say the CDN no longer has it; a read keeps no file it
    wrote;
  * THE CHART: his points the box score's way (2s, 3s and free throws),
    each zone beside the league's percentage there, the quarter and
    distance splits, his box score that night off the logs, the season
    named for both its years;
  * THE DOOR, THE FILLER, THE NIGHTLY, THE PAGE: /api/players/chart
    serves it; an empty table is owed and filled; the nightly reads the
    last few days and a budget of older games; every basketball bet has
    a chart slot and a parlay door; the drawing loads as its own module;
  * THE LOGS keep steals, blocks and turnovers from both box-score feeds.

Run directly: `python3 tests/test_a_shot_chart_for_every_nba_player.py`
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

from engine import chartfill as CF, charts as CH, db as D, maintenance as M  # noqa: E402
from engine.nba import shots as NS  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
HOOPS_JS = (ROOT / "web" / "js" / "chart-hoops.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SLIP_JS = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")

JOKIC, MURRAY, BRUNSON = 203999, 1627750, 1628973


def _box(gid="0022500101", date="2025-11-02T20:00:00Z"):
    return {"game": {"gameId": gid, "gameEt": date, "gameCode": "20251102/NYKDEN",
                     "homeTeam": {"teamTricode": "DEN", "players": [
                         {"personId": JOKIC, "name": "Nikola Jokić"},
                         {"personId": MURRAY, "name": "Jamal Murray"}]},
                     "awayTeam": {"teamTricode": "NYK", "players": [
                         {"personId": BRUNSON, "name": "Jalen Brunson"}]}}}


def _act(n, kind, pid, team, made, x=None, y=None, dist=None, sub="Jump Shot", desc="", per=1,
         clock="PT11M30.00S", ast="", blk=0, quals=(), area=None):
    a = {"actionNumber": n, "actionType": kind, "personId": pid, "teamTricode": team,
         "shotResult": "Made" if made else "Missed", "subType": sub, "descriptor": desc,
         "period": per, "clock": clock, "qualifiers": list(quals), "playerNameI": "X. Shooter"}
    if x is not None:
        a.update({"xLegacy": x, "yLegacy": y, "isFieldGoal": 1})
    if dist is not None:
        a["shotDistance"] = dist
    if ast:
        a["assistPlayerNameInitial"] = ast
        a["assistPersonId"] = MURRAY
    if blk:
        a["blockPersonId"] = BRUNSON
    if area:
        a["area"] = area
    return a


def _pbp(gid="0022500101"):
    return {"game": {"gameId": gid, "actions": [
        {"actionNumber": 1, "actionType": "period", "subType": "start", "personId": 0},
        _act(4, "2pt", JOKIC, "DEN", True, x=-10, y=20, dist=2.2, sub="Layup", desc="driving",
             ast="J. Murray", quals=("pointsinthepaint",)),
        _act(7, "3pt", JOKIC, "DEN", False, x=230, y=40, dist=23.4, blk=0),
        _act(9, "2pt", JOKIC, "DEN", True, x=60, y=100, dist=11.7, sub="Hook", desc="turnaround",
             ast="", quals=("pointsinthepaint", "2ndchance")),
        _act(12, "2pt", JOKIC, "DEN", False, x=150, y=100, dist=18.0, blk=1, per=2, clock="PT03M05.00S"),
        _act(15, "3pt", JOKIC, "DEN", True, x=-50, y=250, dist=25.5, desc="step back", ast="J. Murray",
             per=3, clock="PT07M04.00S", quals=("fastbreak",)),
        _act(16, "freethrow", JOKIC, "DEN", True, sub="1 of 2", per=3, clock="PT07M04.00S"),
        _act(17, "freethrow", JOKIC, "DEN", False, sub="2 of 2", per=3, clock="PT07M04.00S"),
        _act(20, "3pt", BRUNSON, "NYK", True, x=10, y=260, dist=26.0, area="Above the Break 3", per=5,
             clock="PT01M00.00S"),
        _act(21, "2pt", 999, "BOS", True, x=0, y=10, dist=1.0),          # not a team in this game
        {"actionNumber": 30, "actionType": "rebound", "personId": JOKIC, "teamTricode": "DEN"},
        _act(31, "2pt", JOKIC, "DEN", True, dist=3.0),                       # no coordinates: by distance
    ]}}


def _conn(path=":memory:"):
    conn = D.connect(path)
    D.upsert_nba_shots(conn, NS.fold(_pbp(), _box()))
    # Last season's other game, a Brunson night.
    g2 = "0022500050"
    D.upsert_nba_shots(conn, NS.fold({"game": {"gameId": g2, "actions": [
        _act(3, "2pt", BRUNSON, "NYK", True, x=-70, y=130, dist=14.8, per=1)]}},
        _box(g2, "2025-10-28T19:30:00Z")))
    return conn


# --- the fold ---------------------------------------------------------------------
def test_one_row_per_shot_and_free_throw_named_by_the_box_score():
    rows = NS.fold(_pbp(), _box())
    by = {r["action"]: r for r in rows}
    assert sorted(by) == [4, 7, 9, 12, 15, 16, 17, 20, 31], "shots and free throws, nothing else"
    j = by[4]
    assert (j["player"], j["team"], j["opponent"], j["home"], j["date"], j["season"]) == \
        ("Nikola Jokić", "DEN", "NYK", 1, "2025-11-02", 2025)
    assert (j["kind"], j["made"], j["zone"], j["assist"], j["clock"], j["quals"]) == \
        ("2pt", 1, "ra", "J. Murray", "11:30", "pointsinthepaint")
    assert by[7]["zone"] == "corner3" and by[9]["zone"] == "paint" and by[12]["zone"] == "mid"
    assert by[12]["blocked"] == 1 and by[12]["assist"] == "" and by[15]["zone"] == "above3"
    assert by[16]["kind"] == "ft" and by[16]["x"] is None and by[16]["zone"] == "" and by[17]["made"] == 0
    assert by[20]["player"] == "Jalen Brunson" and by[20]["home"] == 0 and by[20]["opponent"] == "DEN"
    assert by[20]["zone"] == "above3" and by[20]["area"] == "Above the Break 3", "the feed's own word wins"
    assert by[31]["zone"] == "ra" and by[31]["x"] is None, "no spot on the floor: zoned by distance"
    assert NS.fold(_pbp(), {"game": {}}) == [], "no box score, no rows: whose game is it?"
    # A game in March belongs to the season that tipped off the October before.
    march = NS.fold(_pbp(), _box(date="2026-03-02T19:00:00Z"))
    assert march[0]["season"] == 2025 and march[0]["date"] == "2026-03-02"
    assert NS.clock("PT07M04.00S") == "7:04" and NS.clock("") == ""


def test_the_zones_read_off_the_floor():
    assert NS.zone("3pt", 225, 30, 22.5) == "corner3" and NS.zone("3pt", 0, 260, 26) == "above3"
    assert NS.zone("2pt", 5, 30, 3.0) == "ra" and NS.zone("2pt", 70, 140, 15.7) == "paint"
    assert NS.zone("2pt", 90, 140, 16.6) == "mid" and NS.zone("2pt", 0, 160, 16.0) == "mid"
    assert NS.zone("2pt", 0, 0, None, area="Mid-Range") == "mid"
    assert [k for k, _n in NS.ZONES] == ["ra", "paint", "mid", "corner3", "above3"]


# --- the games --------------------------------------------------------------------
def test_the_games_this_season_and_last():
    sched = {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "0012600001", "gameDateEst": "2026-10-10T00:00:00Z", "gameStatus": 3},   # preseason
        {"gameId": "0022600001", "gameDateEst": "2026-10-20T00:00:00Z", "gameStatus": 3},
        {"gameId": "0022600002", "gameDateEst": "2026-10-21T00:00:00Z", "gameStatus": 2},   # still on
        {"gameId": "0032600001", "gameDateEst": "2027-02-14T00:00:00Z", "gameStatus": 3},   # All-Star
        {"gameId": "0022600003", "gameDateEst": "2026-10-22T00:00:00Z", "gameStatus": 3}]}]}}
    assert NS.schedule_finals(sched, "2026-10-22") == [{"game_id": "0022600001", "date": "2026-10-20"}]
    ids = NS.season_ids(2025)
    assert len(ids) == 1230 and ids[0]["game_id"] == "0022501230" and ids[-1]["game_id"] == "0022500001"


def test_a_game_is_read_once_and_last_season_by_number():
    conn = D.connect(":memory:")
    asked = []

    def read(gid):
        asked.append(gid)
        return (_pbp(gid), _box(gid)) if gid != "0022500003" else (None, None)
    games = [{"game_id": g, "date": ""} for g in ("0022500001", "0022500002", "0022500003")]
    out = NS.ingest_games(conn, games, read=read, workers=1)
    assert out["games"] == 2 and out["failed"] == 1 and out["shots"] == 18
    assert NS.ingest_games(conn, games, read=read, workers=1)["games"] == 0
    assert sorted(asked) == ["0022500001", "0022500002", "0022500003", "0022500003"]
    # The backfill: this season's finals first, then last season's by
    # number, newest first, a budget at a time.
    from engine.sources import nbadata as N
    keep = N.fetch_schedule
    N.fetch_schedule = lambda ttl=0: {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "0022600001", "gameDateEst": "2026-10-20T00:00:00Z", "gameStatus": 3}]}]}}
    try:
        asked.clear()
        got = NS.backfill(conn, dt.date(2026, 10, 23), budget=8, read=read)
    finally:
        N.fetch_schedule = keep
    assert asked[0] == "0022600001" and asked[1:4] == ["0022501230", "0022501229", "0022501228"]
    assert got["games"] == 8 and got["last_season"] == "" and got["left"] > 1000
    # Five misses in a row on last season: the CDN no longer has it.
    conn2 = D.connect(":memory:")
    asked.clear()
    got = NS.backfill(conn2, dt.date(2026, 10, 13), budget=50, read=lambda gid: asked.append(gid) or (None, None))
    assert len(asked) == 5 and got["last_season"] == "not on the CDN" and got["games"] == 0


def test_a_read_keeps_no_file_it_wrote():
    from engine.sources import fetch as F, nbadata as N
    tmp = Path(tempfile.mkdtemp())
    keep = (F.CACHE_DIR, N.fetch_playbyplay, N.fetch_boxscore)

    def pbp(gid, ttl=0):
        (tmp / f"nba_pbp_{gid}.json").write_text("{}")
        return _pbp(gid)

    def box(gid, ttl=0):
        (tmp / f"nba_box_{gid}.json").write_text("{}")
        return _box(gid)
    try:
        F.CACHE_DIR, N.fetch_playbyplay, N.fetch_boxscore = tmp, pbp, box
        (tmp / "nba_box_0022500002.json").write_text("{}")
        assert NS.read_once("0022500001")[0]["game"]["gameId"] == "0022500001"
        assert not list(tmp.glob("*0022500001*")), "both files it wrote are gone"
        NS.read_once("0022500002")
        assert (tmp / "nba_box_0022500002.json").exists(), "a box score the results ingest kept stays"
        assert not (tmp / "nba_pbp_0022500002.json").exists()
        assert "nba_pbp_" in M.PRUNABLE_CACHE_PREFIXES
    finally:
        F.CACHE_DIR, N.fetch_playbyplay, N.fetch_boxscore = keep
        shutil.rmtree(tmp, ignore_errors=True)


# --- the chart --------------------------------------------------------------------
def _with_box(conn):
    """His box score that night, as the logs keep it."""
    D.upsert_player_logs(conn, [{"sport": "nba", "season": 2025, "period": "2025-11-02",
                                 "game_id": "Nikola Jokić-2025-11-02", "player": "Nikola Jokić", "team": "DEN",
                                 "opponent": "NYK", "position": "S", "home": 1, "market": m, "value": v}
                                for m, v in (("min", 36.5), ("reb", 14), ("ast", 9), ("stl", 2), ("blk", 1),
                                             ("tov", 3))])
    return conn


def test_the_chart_reads_his_line_his_zones_and_the_league():
    conn = _with_box(_conn())
    d = NS.chart(conn, "Nikola Jokic")
    assert d["player"] == "Nikola Jokić", "found without the accent"
    assert d["season"] == 2025 and d["season_label"] == "2025-26" and d["team"] == "DEN"
    g = d["games"][0]
    L = g["line"]
    assert (L["fga"], L["fgm"], L["fg3a"], L["fg3m"], L["fta"], L["ftm"]) == (6, 4, 2, 1, 2, 1)
    assert L["pts"] == 2 * 3 + 3 * 1 + 1 == 10 and L["assisted"] == 2 and L["paint"] == 3
    assert g["box"] == {"min": 36.5, "reb": 14, "ast": 9, "stl": 2, "blk": 1, "tov": 3}
    assert [s["i"] for s in g["shots"]] == [4, 7, 9, 12, 15, 16, 17, 31], "in the order taken"
    zones = {z["key"]: z for z in d["zones"]}
    assert (zones["ra"]["fga"], zones["ra"]["fgm"]) == (2, 2) and zones["corner3"]["pct"] == 0.0
    assert zones["above3"]["league"] == 1.0, "the league's own: Jokić's and Brunson's threes up top went in"
    assert zones["paint"]["league"] == 1.0 and zones["ra"]["share"] == round(2 / 6, 3)
    assert [p["key"] for p in d["by_period"]] == ["Q1", "Q2", "Q3"]
    assert d["by_dist"][0]["key"] == "0-4 ft" and d["by_dist"][0]["fga"] == 2
    assert d["season_line"]["games"] == 1 and d["season_line"]["ppg"] == 10.0
    b = NS.chart(conn, "Jalen Brunson")
    assert [x["date"] for x in b["games"]] == ["2025-11-02", "2025-10-28"], "newest first"
    assert b["games"][0]["shots"][0]["p"] == 5 and b["games"][0]["box"] == {}
    assert NS.chart(conn, "Nobody Here") == {}


# --- the door, the filler, the nightly ---------------------------------------------
def test_the_door_serves_it_and_says_filling():
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
        h._players_chart({"kind": ["shots"], "sport": ["nba"], "player": ["Nikola Jokic"]})
        _conn(path).close()
        h._players_chart({"kind": ["shots"], "sport": ["nba"], "player": ["Nikola Jokic"]})
        h._players_chart({"kind": ["shots"], "sport": ["wnba"], "player": ["Nikola Jokic"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "shots" and sent[1][1]["season_line"]["pts"] == 10
    assert "face" in sent[1][1] and sent[2][0] == 400
    assert CH.known("shots", "nba") and not CH.known("shots", "nfl")


def test_an_empty_table_is_owed_and_filled():
    conn = D.connect(":memory:")
    today = dt.date(2026, 10, 13)
    assert CF.owed(conn, today) == []
    D.upsert_games(conn, [{"sport": "nba", "season": 2025, "period": "2026-04-12", "game_id": "NYK@DEN",
                           "home": "DEN", "away": "NYK", "home_score": 120.0, "away_score": 111.0,
                           "date": "2026-04-12"}])
    assert CF.owed(conn, today) == [("nba", 2025, "nba_shots")], "last season, played, no shots"
    keep = NS.backfill
    NS.backfill = lambda conn, today, budget=0, read=None: {"games": 300, "shots": 51234, "failed": 0,
                                                            "left": 930, "last_season": ""}
    try:
        lines = CF.fill(conn, CF.owed(conn, today), log=lambda *_: None)
    finally:
        NS.backfill = keep
    assert lines == ["NBA: 300 games, 51,234 shots; 930 older games left for the nightly"], lines
    D.upsert_nba_shots(conn, NS.fold(_pbp(), _box()))
    assert CF.owed(conn, today) == [], "a season with a stored shot is the nightly's from here"


def test_the_nightly_reads_the_last_days_and_a_budget_of_older_games():
    src = inspect.getsource(M._run_chores)
    i = src.index("NBA SHOT CHART")
    block = src[i:i + 1400]
    assert "_nshots.ingest_recent(_sc, today)" in block and "_nshots.backfill(_sc, today)" in block
    assert "today.month >= 10 or today.month <= 6" in block, "in the NBA's months, as the results ingest"
    assert 100 <= NS.BACKFILL_PER_NIGHT <= 500


# --- the logs ----------------------------------------------------------------------
def test_steals_blocks_and_turnovers_are_kept_from_both_feeds():
    from engine.sources import espnhoops, nbadata
    box = {"game": {"homeTeam": {"teamTricode": "DEN", "players": [
        {"name": "Nikola Jokić", "starter": "1", "personId": JOKIC, "statistics": {
            "minutes": "PT36M00.00S", "points": 30, "reboundsTotal": 14, "assists": 9, "threePointersMade": 1,
            "steals": 2, "blocks": 1, "turnovers": 3}}]}, "awayTeam": {"teamTricode": "NYK", "players": []}}}
    rows = nbadata.parse_boxscore(box)
    assert (rows[0]["stl"], rows[0]["blk"], rows[0]["tov"]) == (2.0, 1.0, 3.0)
    by = {r["market"]: r["value"] for r in nbadata.log_rows(rows, "2025-11-02", "0022500101")}
    assert (by["stl"], by["blk"], by["tov"]) == (2.0, 1.0, 3.0) and by["pts"] == 30.0
    assert {"STL": "stl", "BLK": "blk", "TO": "tov"}.items() <= espnhoops.STAT_MAP.items()


# --- the page ----------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{HOOPS_JS}\n"
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


def test_the_page_draws_the_court():
    conn = _with_box(_conn())
    d = NS.chart(conn, "Nikola Jokic")
    got = _node(f"""
      const d = {json.dumps(d)}, P = T.DRAW.shots, g = d.games[0];
      const game = P.game(g, d), season = P.season(d);
      return {{
        dots: (game.match(/class="nb-shot cx-mark/g) || []).length, made: (game.match(/nb-shot cx-mark m/g) || []).length,
        faint: (season.match(/nb-shot faint/g) || []).length, pills: (season.match(/class="nb-pill"/g) || []).length,
        list: P.list(g, d), tiles: P.gameSide(g, d), side: P.seasonSide(d), tables: P.splits(d),
        chip: P.chip(g), count: P.count(d.season_line), tip: P.tip(g.shots[4], g, d),
        kinds: [T.kindsFor("nba", "pts", "C"), T.kindsFor("nba", "reb", ""), T.kindsFor("nba", "", "")],
        title: T.KIND.shots.title, label: T.gameTitle(g, "nba", "2025-26"),
      }};
    """)
    if got is None:
        return
    assert got["dots"] == 5 and got["made"] == 3, "five shots from the floor have a spot; the free throws do not"
    assert got["faint"] == 5 and got["pills"] >= 3
    assert "Assisted by J. Murray" in got["list"] and "Free throw 1 of 2" in got["list"] and ">Blocked<" in got["list"]
    assert "Q3 7:04" in got["list"] and "Hook · turnaround" in got["list"] and ">Missed 3<" in got["list"]
    assert ">10<" in got["tiles"] and ">4-6<" in got["tiles"] and "Steals" in got["tiles"] and ">37<" in got["tiles"]
    assert "Assisted" in got["side"] and "a game" in got["side"]
    assert "By zone, beside the league" in got["tables"] and "By quarter" in got["tables"]
    assert got["chip"] == "10 pts · 4-6" and got["count"] == "6 shots" and "Made 3" in got["tip"]
    assert got["kinds"] == [["shots", "role"], ["shots", "role"], []] and got["title"] == "Shot chart"
    assert got["label"].startswith("2025-26 vs NYK")


def test_every_door_and_the_module():
    i = APP_JS.index("function chartSlot(")
    assert "return r && r.player ?" in APP_JS[i:i + 500], "every basketball bet leaves a slot"
    i = SLIP_JS.index("function chartsHTML(")
    assert 'lg === "nba" ? ["shots", "Shot chart"]' in SLIP_JS[i:i + 800]
    assert 'shots: "hoops"' in CC_JS and 'Q.draw("shots"' in HOOPS_JS and "window.QBCarry.plug" in HOOPS_JS
    assert "onclick" not in HOOPS_JS and "onerror" not in HOOPS_JS and not re.search(r"on(error|load)\s*=", HOOPS_JS)
    for cls in (".nb-svg", ".nb-paint", ".nb-arc", ".nb-shot.m", ".nb-shot.x", ".nb-pill rect", ".dt.nb-x"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
