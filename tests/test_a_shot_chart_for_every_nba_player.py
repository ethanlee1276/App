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
  * ESPN'S FOLD (`fold_espn`, 2026-10-14: the league's CDN answers the
    box 403 for every file, so the shots come from ESPN's game summary):
    a shooting play is a field goal or a free throw by the points it
    attempts, made by `scoringPlay`, the shooter the first participant and
    the second the assist on a make or the block on a miss; the spot in
    the CDN's units off ESPN's feet, a free throw off the floor; the clubs
    in the league's codes; nothing that is not a shot, and no play's
    written text;
  * THE GAMES: the history's own NBA finals under ESPN's ids, this season's
    and last, newest first (pins changed 2026-10-14 and told to Ethan:
    they held the CDN's season file and its numbering of last season); a
    stored game is never read again; a read keeps no file it wrote;
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


# --- ESPN's fold --------------------------------------------------------------------
def _summary(gid="401810001", home=("7", "DEN"), away=("18", "NY"), plays=None):
    """ESPN's summary of a final, in the shape `sources/espnplays` recorded."""
    def ath(i, name):
        return {"athlete": {"id": str(i), "displayName": name}, "stats": []}
    return {"header": {"id": gid, "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": home[0], "abbreviation": home[1]}},
                {"homeAway": "away", "team": {"id": away[0], "abbreviation": away[1]}}]}]},
            "boxscore": {"players": [
                {"team": {"id": home[0], "abbreviation": home[1]}, "statistics": [{"athletes": [
                    ath(JOKIC, "Nikola Jokić"), ath(MURRAY, "Jamal Murray")]}]},
                {"team": {"id": away[0], "abbreviation": away[1]}, "statistics": [{"athletes": [
                    ath(BRUNSON, "Jalen Brunson")]}]}]},
            "plays": plays if plays is not None else _plays()}


def _play(seq, team, who, pts, made, x=None, y=None, kind="Jump Shot", per=1, clock="11:30"):
    p = {"id": f"9{seq}", "sequenceNumber": str(seq), "period": {"number": per}, "clock": {"displayValue": clock},
         "team": {"id": team}, "participants": [{"athlete": {"id": str(w)}} for w in who],
         "type": {"id": "1", "text": kind}, "shootingPlay": True, "scoringPlay": made,
         "scoreValue": pts if made else 0, "pointsAttempted": pts,
         "text": "ESPN PROSE NEVER STORED", "shortDescription": "NOR THIS"}
    p["coordinate"] = {"x": x, "y": y} if x is not None else {"x": -214748340, "y": -214748365}
    return p


def _plays():
    return [
        {"id": "1", "sequenceNumber": "1", "type": {"text": "Jumpball"}, "shootingPlay": False,
         "team": {"id": "7"}, "participants": [{"athlete": {"id": str(JOKIC)}}]},
        _play(4, "7", (JOKIC, MURRAY), 2, True, x=25, y=2, kind="Driving Layup Shot"),     # 2 ft, assisted
        _play(7, "7", (JOKIC,), 3, False, x=3, y=3),                                      # corner three
        _play(9, "7", (JOKIC, BRUNSON), 2, False, x=30, y=17, per=2),                      # blocked, mid-range
        _play(12, "7", (JOKIC,), 3, True, x=25, y=26, per=3, clock="7:04"),               # above the break
        _play(13, "7", (JOKIC,), 1, True, kind="Free Throw - 1 of 2", per=3, clock="7:04"),
        _play(14, "7", (JOKIC,), 1, False, kind="Free Throw - 2 of 2", per=3, clock="7:04"),
        _play(20, "18", (BRUNSON,), 2, True, x=21, y=10, per=4),                         # in the paint
        _play(21, "99", (BRUNSON,), 2, True, x=25, y=1),                                  # no club in this game
        _play(22, "7", (), 2, True, x=25, y=1)]                                           # nobody shot it


def test_espns_summary_folds_into_the_same_rows():
    rows = NS.fold_espn(_summary(), "2025-11-02")
    by = {r["action"]: r for r in rows}
    assert sorted(by) == [4, 7, 9, 12, 13, 14, 20], "shots and free throws only; no club, no shooter, no row"
    lay, corner, blk, top, ft1, ft2, brun = (by[i] for i in (4, 7, 9, 12, 13, 14, 20))
    assert (lay["kind"], lay["made"], lay["distance"], lay["zone"], lay["assist"]) == \
        ("2pt", 1, 2.0, "ra", "Jamal Murray")
    assert (lay["x"], lay["y"]) == (0.0, 20.0), "ESPN's feet into the CDN's tenths from the basket"
    assert (corner["kind"], corner["made"], corner["zone"], corner["assist"]) == ("3pt", 0, "corner3", "")
    assert blk["blocked"] == 1 and blk["zone"] == "mid" and blk["assist"] == "" and blk["period"] == 2
    assert top["zone"] == "above3" and top["distance"] == 26.0 and top["clock"] == "7:04"
    assert (ft1["kind"], ft1["made"], ft1["x"], ft1["distance"], ft1["zone"]) == ("ft", 1, None, None, "")
    assert ft2["made"] == 0 and ft2["blocked"] == 0
    assert brun["team"] == "NYK" and brun["opponent"] == "DEN" and brun["home"] == 0 and brun["zone"] == "paint"
    assert lay["team"] == "DEN" and lay["home"] == 1 and lay["player"] == "Nikola Jokić"
    assert lay["game_id"] == "401810001" and lay["season"] == 2025 and lay["shot"] == "Driving Layup Shot"
    assert not any("PROSE" in str(v) or "NOR THIS" in str(v) for r in rows for v in r.values())
    assert NS.fold_espn({"plays": _plays()}, "2025-11-02") == [], "no header, no rows: whose game is it?"
    conn = D.connect(":memory:")
    D.upsert_nba_shots(conn, rows)
    assert NS.chart(conn, "Jalen Brunson")["games"][0]["opp"] == "DEN"


def test_the_box_check_holds_a_real_game_to_the_leagues_shape():
    """`nbashotcheck.py` (read-only): where ESPN puts the basket was taken on
    trust, so the box reads one real final and holds the fold to the
    league's shape — a wrong basket reads CHECK, never a quiet chart."""
    import nbashotcheck as K
    lines = K.report(_summary(), "401810001", "2025-11-02")
    assert lines[0].startswith("NBA SHOT CHECK  game 401810001 on 2025-11-02: 10 plays, 9 shooting")
    assert any("a free throw's coordinate" in l for l in lines)
    assert not any("PROSE" in l or "NOR THIS" in l for l in lines), "no play's text"
    # The basket a few feet off: the threes read short and the rim shots long.
    keep = NS.ESPN_HOOP
    NS.ESPN_HOOP = (25.0, 8.0)
    try:
        bad = K.report(_summary(), "401810001", "2025-11-02")
    finally:
        NS.ESPN_HOOP = keep
    assert any(l.startswith("  CHECK median dunk or layup") for l in bad), bad
    assert "no shooting plays" in K.report({"plays": []}, "1", "2025-11-02")[-1]
    src = (ROOT / "nbashotcheck.py").read_text(encoding="utf-8")
    assert "upsert" not in src and "commit" not in src, "it reads; it never stores"


# --- the games --------------------------------------------------------------------
def _finals(conn, games):
    D.upsert_games(conn, [{"sport": "nba", "season": s, "period": d, "game_id": g, "home": "DEN", "away": "NYK",
                           "home_score": sc, "away_score": 100.0 if sc else None, "date": d}
                          for g, s, d, sc in games])


def test_the_games_this_season_and_last():
    conn = D.connect(":memory:")
    _finals(conn, [("401900001", 2026, "2026-10-20", 110.0), ("401900002", 2026, "2026-10-21", None),
                   ("401800050", 2025, "2026-04-12", 99.0), ("401700001", 2024, "2025-04-13", 101.0),
                   ("NYK@DEN", 2026, "2026-10-19", 104.0)])
    got = NS.espn_finals(conn, "2025-10-01", "2026-10-22")
    assert got == [{"game_id": "401900001", "date": "2026-10-20"}, {"game_id": "401800050", "date": "2026-04-12"}]


def test_a_game_is_read_once_and_last_season_and_this_newest_first():
    conn = D.connect(":memory:")
    asked = []

    def read(gid):
        asked.append(gid)
        return _summary(gid) if gid != "401900003" else None
    games = [{"game_id": g, "date": "2025-11-02"} for g in ("401900001", "401900002", "401900003")]
    out = NS.ingest_games(conn, games, read=read, workers=1, espn=True)
    assert out["games"] == 2 and out["failed"] == 1 and out["shots"] == 14
    assert NS.ingest_games(conn, games, read=read, workers=1, espn=True)["games"] == 0
    assert sorted(asked) == ["401900001", "401900002", "401900003", "401900003"]
    # The backfill: the history's finals, this season's then last season's,
    # newest first, a budget at a time, a stored game skipped.
    conn2 = D.connect(":memory:")
    _finals(conn2, [("401900010", 2026, "2026-10-21", 110.0), ("401800020", 2025, "2026-04-12", 99.0),
                    ("401800010", 2025, "2026-03-01", 98.0), ("401700001", 2024, "2025-04-13", 101.0)])
    asked.clear()
    got = NS.backfill(conn2, dt.date(2026, 10, 23), budget=2, read=read)
    assert asked == ["401900010", "401800020"] and got["games"] == 2 and got["left"] == 1
    asked.clear()
    got = NS.backfill(conn2, dt.date(2026, 10, 23), budget=5, read=read)
    assert asked == ["401800010"] and got["left"] == 0, "two seasons, never the one before"
    recent = D.connect(":memory:")
    _finals(recent, [("401900030", 2026, "2026-10-21", 110.0), ("401900031", 2026, "2026-10-15", 100.0)])
    asked.clear()
    NS.ingest_recent(recent, dt.date(2026, 10, 22), read=read)
    assert asked == ["401900030"], "the last three days' finals"


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
    # ESPN's summary the same way: one the results ingest kept stays.
    from engine.sources import espnhoops
    tmp = Path(tempfile.mkdtemp())
    keep = (F.CACHE_DIR, espnhoops.fetch_summary)

    def summ(gid, ttl=0, league="wnba"):
        (tmp / f"espn_nba_box_{gid}.json").write_text("{}")
        return _summary(gid)
    try:
        F.CACHE_DIR, espnhoops.fetch_summary = tmp, summ
        assert NS.read_espn("401900001")["header"]["id"] == "401900001"
        assert not list(tmp.glob("*401900001*")), "the summary it wrote is gone"
        (tmp / "espn_nba_box_401900002.json").write_text("{}")
        NS.read_espn("401900002")
        assert (tmp / "espn_nba_box_401900002.json").exists(), "the results ingest's copy stays"
        assert "espn_nba_" in M.PRUNABLE_CACHE_PREFIXES
    finally:
        F.CACHE_DIR, espnhoops.fetch_summary = keep
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
    # Every leg's door asks for his charts with its bet (2026-10-14); a
    # basketball bet's are his shots and his role (kindsFor, pinned above).
    i = SLIP_JS.index("function chartsHTML(")
    assert '/^(nfl|cfb|nba|wnba|nhl|mlb)$/.test(lg)' in SLIP_JS[i:i + 400] and 'data-kind="auto"' in SLIP_JS[i:i + 600]
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
