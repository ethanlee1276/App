"""The hit page's seven missing pieces, each off MLB's own record.

Ethan, 2026-10-14, after asking what data the MLB hit page was missing and
where it could come from: "And yes do the first 7 page items" —

  1. his runs scored and stolen bases, game by game;
  2. each club's record on the day ("88-74");
  3. the ballpark ("@ Dodger Stadium") and a View Game button;
  4. barrels: per ball by MLB's published rule, and his season's rate;
  5. MLB's own expected average and slugging beside ours;
  6. the video of each at-bat, on Baseball Savant;
  7. his action photo in place of his headshot.

What is pinned, offline, on the hit tracker's fixture games and on
databases, schedules, game logs and Savant boards built here:

  * THE GAMES TABLE (engine/mlb/charts.games_info): the park, the final,
    both clubs' records as the schedule gives them, a doubleheader's game
    number and October's series, for finals of the regular season and
    the postseason only; filled from the schedule the nightly already
    reads, and a season read before the table was kept, once
    (`fill_info`);
  * THE RECORD ON THE DAY (`_standing`): given only where our own count
    of the season's finals agrees with the league's figure — after the
    game or before it — and never when a game of that club's is missing;
  * RUNS AND STOLEN BASES (`bat_rows`, `fill_bat`): off his own game log,
    by the game's own id; his postseason log when a playoff game is
    missing; a game neither log carries written down as asked after a few
    days; the season's totals only when every game on the chart has them,
    a game he only ran in counted;
  * BARRELS (`barrel`): MLB's window, 98 mph at 26-30 degrees widening to
    8-50 at 116;
  * THE VIDEO (`play_ids`, `fill_play_ids`): the id of the pitch each
    plate appearance ended on, kept by the fold, and read again for the
    season's last month of games read before it was kept — once;
  * MLB'S OWN NUMBERS (engine/mlb/sources/savant): the page's own copy of
    Savant's boards, every hitter by MLB's id, read from the file and
    never the wire; and the model's two boards no longer frozen on the
    first file they ever wrote;
  * THE PHOTO: his action photo off MLB's CDN, falling back to his
    headshot when it is not there;
  * THE PAGE (js/chart-mlb.js): every piece drawn where it is on file and
    only there, MLB's pages opened beside ours, no link inside a button;
  * THE FILLS: the nightly chores and, the hour the code lands, the chart
    fill (engine/chartfill) read what is owed;
  * IN A BROWSER (opt-in, QB_BROWSER_TESTS=1): the photo and its fallback,
    the links, the tiles, at a phone's width with no sideways scroll.

Run directly: `python3 tests/test_the_hit_page_has_what_the_renders_showed.py`
"""
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import chartfill as CF, db as D  # noqa: E402
from engine.mlb import charts as MC  # noqa: E402
from engine.mlb.sources import mlbstats, savant  # noqa: E402

_spec = importlib.util.spec_from_file_location("hit_fixture", ROOT / "tests" / "test_mlb_hit_tracker_and_pitch_chart.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
MAINT = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")

JUDGE, SOTO, GREENE = F.JUDGE, F.SOTO, 111
TODAY = dt.date(2026, 10, 14)


def _team(tid, ab, score=None, w=None, l=None):  # noqa: E741
    t = {"team": {"id": tid, "abbreviation": ab}}
    if score is not None:
        t["score"] = score
    if w is not None:
        t["leagueRecord"] = {"wins": w, "losses": l, "pct": ".500"}
    return t


def _game(pk, date, home, away, kind="R", state="Final", coded="F", venue="Yankee Stadium", gn=1, **extra):
    g = {"gamePk": pk, "officialDate": date, "gameType": kind, "season": date[:4], "gameNumber": gn,
         "status": {"abstractGameState": state, "codedGameState": coded},
         "teams": {"home": home, "away": away}, "venue": {"id": 3313, "name": venue}}
    g.update(extra)
    return g


def _schedule(*games):
    return {"dates": [{"date": g["officialDate"], "games": [g]} for g in games]}


# The hit tracker's two fixture games, as the league's schedule has them: a
# division-series game at Yankee Stadium and an earlier regular-season one.
SCHEDULE = _schedule(
    _game(775900, "2026-10-05", _team(147, "NYY", 4, 1, 0), _team(118, "KC", 1, 0, 1)),
    _game(776001, "2026-10-11", _team(147, "NYY", 5, 2, 1), _team(116, "DET", 3, 1, 2), kind="D",
          seriesDescription="Division Series", seriesGameNumber=3),
    _game(776002, "2026-10-12", _team(147, "NYY"), _team(116, "DET"), kind="D", state="Live", coded="I"),
    _game(776003, "2026-10-13", _team(147, "NYY"), _team(116, "DET"), kind="D", coded="D"),
    _game(700001, "2026-02-28", _team(147, "NYY", 2, 0, 0), _team(111, "BOS", 1, 0, 0), kind="S"),
)


def _log(pid, games, season=2026):
    """A hitter's `stats=gameLog` answer: ``[(game_pk, date, runs, sb, cs)]``."""
    return {"stats": [{"type": {"displayName": "gameLog"}, "group": {"displayName": "hitting"},
                       "splits": [{"season": str(season), "date": date, "game": {"gamePk": pk},
                                   "player": {"id": pid},
                                   "stat": {"runs": r, "stolenBases": sb, "caughtStealing": cs, "hits": 1}}
                                  for pk, date, r, sb, cs in games]}]}


def _rich():
    """The fixture's database with the games table, his game log's runs
    and steals, and the video ids the fold keeps."""
    conn = F._conn()
    D.upsert_mlb_games(conn, MC.games_info(SCHEDULE))
    D.upsert_mlb_bat_games(conn, MC.bat_rows(_log(JUDGE, [(775900, "2026-10-05", 0, 0, 1),
                                                           (774000, "2026-10-01", 1, 1, 0)]), JUDGE)
                           + MC.bat_rows(_log(JUDGE, [(776001, "2026-10-11", 2, 1, 0)]), JUDGE))
    conn.execute("UPDATE mlb_pa SET play_id='5a1b2c3d-0000-4000-8000-00000000000' || at_bat WHERE game_pk=776001")
    conn.commit()
    return conn


# --- the games table --------------------------------------------------------------
def test_the_schedule_gives_each_final_its_park_records_and_series():
    rows = {r["game_pk"]: r for r in MC.games_info(SCHEDULE)}
    assert sorted(rows) == [775900, 776001], "finals of the season and October only: not live, postponed or spring"
    r = rows[775900]
    assert (r["venue"], r["home"], r["away"], r["home_score"], r["away_score"]) == ("Yankee Stadium", "NYY", "KC", 4, 1)
    assert (r["home_w"], r["home_l"], r["away_w"], r["away_l"], r["season"], r["game_number"]) == (1, 0, 0, 1, 2026, 1)
    assert (r["game_type"], r["series"], r["series_game"]) == ("R", "", None), "no series in the regular season"
    p = rows[776001]
    assert (p["game_type"], p["series"], p["series_game"], p["date"]) == ("D", "Division Series", 3, "2026-10-11")
    assert MC.games_info({}) == [] and MC.games_info(None) == []
    conn = D.connect(":memory:")
    assert D.upsert_mlb_games(conn, list(rows.values())) == 2
    assert conn.execute("SELECT venue FROM mlb_games WHERE game_pk=776001").fetchone()[0] == "Yankee Stadium"


def test_the_nightly_keeps_the_schedule_it_already_reads():
    conn = D.connect(":memory:")
    asked = []
    old = mlbstats.fetch_schedule
    mlbstats.fetch_schedule = lambda start, end: asked.append((start, end)) or SCHEDULE
    try:
        got = MC.backfill(conn, 2026, "2026-10-13", budget=0)
        assert got["info"] == 2 and asked == [("2026-03-01", "2026-10-13")], "one request: the backfill's own"
        conn2 = D.connect(":memory:")
        got2 = MC.ingest_range(conn2, "2026-10-05", "2026-10-13", fetch=lambda pk: {})
        assert got2["info"] == 2 and conn2.execute("SELECT COUNT(*) FROM mlb_games").fetchone()[0] == 2
    finally:
        mlbstats.fetch_schedule = old


def test_a_season_read_before_the_table_was_kept_is_read_once():
    conn = F._conn()
    D.upsert_mlb_pa(conn, [{"game_pk": 660001, "at_bat": 0, "season": 2025, "date": "2025-06-01",
                            "batter_id": JUDGE, "batter": "Aaron Judge", "team": "NYY", "opponent": "BOS",
                            "home": 1, "event": "Single", "event_type": "single", "rbi": 0, "pitches": 1}])
    D.upsert_mlb_games(conn, MC.games_info(SCHEDULE))
    asked = []
    last = _schedule(_game(660001, "2025-06-01", _team(147, "NYY", 3, 30, 25), _team(111, "BOS", 2, 28, 27)))
    got = MC.fill_info(conn, fetch=lambda a, b: asked.append((a, b)) or last)
    assert got == {2025: 1} and asked == [("2025-03-01", "2025-11-30")], "only the season the table has none of"
    assert MC.fill_info(conn, fetch=lambda a, b: asked.append((a, b)) or last) == {} and len(asked) == 1


# --- the record on the day ------------------------------------------------------------
def _season_conn(rows):
    conn = D.connect(":memory:")
    D.upsert_mlb_games(conn, rows)
    return conn


def _g(pk, date, home, away, hs, as_, hw, hl, aw, al, gn=1):
    return {"game_pk": pk, "season": 2026, "date": date, "game_type": "R", "game_number": gn, "home": home,
            "away": away, "home_score": hs, "away_score": as_, "home_w": hw, "home_l": hl, "away_w": aw,
            "away_l": al, "venue": "Fenway Park", "series": "", "series_game": None}


def test_a_record_is_given_only_where_our_own_count_agrees():
    after = [_g(1, "2026-04-01", "NYY", "BOS", 5, 3, 1, 0, 0, 1),
             _g(2, "2026-04-02", "BOS", "NYY", 4, 2, 1, 1, 1, 1, gn=1),     # a doubleheader's first ...
             _g(3, "2026-04-02", "BOS", "NYY", 1, 6, 1, 2, 2, 1, gn=2)]     # ... before its second
    assert MC._standing(_season_conn(after), 2026) == {1: ("1-0", "0-1"), 2: ("1-1", "1-1"), 3: ("1-2", "2-1")}
    # The league's figure the day before the game: the same records, through the game.
    before = [_g(1, "2026-04-01", "NYY", "BOS", 5, 3, 0, 0, 0, 0),
              _g(2, "2026-04-02", "BOS", "NYY", 4, 2, 0, 1, 1, 0, gn=1),
              _g(3, "2026-04-02", "BOS", "NYY", 1, 6, 1, 1, 1, 1, gn=2)]
    assert MC._standing(_season_conn(before), 2026) == {1: ("1-0", "0-1"), 2: ("1-1", "1-1"), 3: ("1-2", "2-1")}
    # A figure that is neither is never shown; the other club's still is.
    wrong = after[:2] + [_g(3, "2026-04-02", "BOS", "NYY", 1, 6, 1, 2, 5, 0, gn=2)]
    assert MC._standing(_season_conn(wrong), 2026)[3] == ("1-2", "")
    # A game missing from the table: every record after it is short a game, so none is given.
    gap = [after[0], after[2]]
    assert MC._standing(_season_conn(gap), 2026)[3] == ("", "")
    # A postseason game is not counted, and a table that cannot answer gives nothing.
    assert MC._standing(D.connect(":memory:"), 2026) == {}


def test_the_hit_chart_carries_the_park_the_final_the_records_and_the_series():
    d = MC.hits_chart(_rich(), "Aaron Judge")
    by = {g["id"]: g for g in d["games"]}
    post, reg = by[776001], by[775900]
    assert (post["venue"], post["score"], post["series"], post["sgame"]) == ("Yankee Stadium", [5, 3], "Division Series", 3)
    assert "rec" not in post and "orec" not in post, "October's games carry the series, not the record"
    assert (reg["venue"], reg["score"], reg["rec"], reg["orec"]) == ("Yankee Stadium", [4, 1], "1-0", "0-1")
    assert "series" not in reg and "dh" not in reg
    # A row whose clubs are not the chart's is not this game.
    conn = _rich()
    conn.execute("UPDATE mlb_games SET away='BOS', venue='Elsewhere' WHERE game_pk=775900")
    conn.commit()
    g = {x["id"]: x for x in MC.hits_chart(conn, "Aaron Judge")["games"]}[775900]
    assert "venue" not in g and "rec" not in g


# --- runs and stolen bases ----------------------------------------------------------------
def test_his_game_log_gives_each_game_its_runs_and_steals_by_its_own_id():
    rows = MC.bat_rows(_log(JUDGE, [(775900, "2026-10-05", 0, 0, 1), (775901, "2026-10-05", 2, 1, 0)]), JUDGE)
    assert [(r["game_pk"], r["runs"], r["sb"], r["cs"], r["season"]) for r in rows] == \
        [(775900, 0, 0, 1, 2026), (775901, 2, 1, 0, 2026)], "a doubleheader's two games, each its own"
    assert MC.bat_rows({}, JUDGE) == [] and MC.bat_rows({"stats": [{"splits": [{"stat": {}}]}]}, JUDGE) == []
    d = MC.hits_chart(_rich(), "Aaron Judge")
    by = {g["id"]: g for g in d["games"]}
    assert (by[776001]["r"], by[776001]["sb"], by[776001]["cs"]) == (2, 1, 0)
    assert (by[775900]["r"], by[775900]["sb"], by[775900]["cs"]) == (0, 0, 1)
    assert d["rs"] == {"r": 3, "sb": 2, "cs": 1}, "the season's, a game he only ran in counted"
    # A game on the chart with none: no season total, the other game's still drawn.
    conn = _rich()
    conn.execute("DELETE FROM mlb_bat_games WHERE game_pk=776001")
    conn.commit()
    d = MC.hits_chart(conn, "Aaron Judge")
    assert d["rs"] is None and "r" not in d["games"][0] and d["games"][1]["r"] == 0


def test_the_hitters_owed_their_logs_are_read_a_budget_a_night():
    conn = F._conn()
    assert set(MC.bat_owed(conn, 2026)) == {JUDGE, SOTO, GREENE}
    asked = []

    def fetch(pid, group, season, kind=""):
        asked.append((pid, kind))
        if pid == GREENE:
            return None                                             # the wire said no
        if pid == JUDGE:
            return _log(JUDGE, [(776001, "2026-10-11", 2, 1, 0)]) if kind == "P" \
                else _log(JUDGE, [(775900, "2026-10-05", 0, 0, 1)])
        if kind == "P":
            raise RuntimeError("no postseason log")
        return _log(SOTO, [])

    got = MC.fill_bat(conn, 2026, fetch=fetch, today=dt.date(2026, 10, 12))
    assert (got["hitters"], got["failed"], got["left"]) == (2, 1, 0)
    assert (JUDGE, "P") in asked, "a playoff game missing from his log asks for the postseason's"
    assert set(MC.bat_owed(conn, 2026)) == {GREENE, SOTO}, "Soto's game is too new to give up on; Greene was not read"
    # Days later, a game neither of his logs carries is written down as asked.
    MC.fill_bat(conn, 2026, fetch=fetch, today=dt.date(2026, 10, 20))
    assert MC.bat_owed(conn, 2026) == [GREENE]
    assert conn.execute("SELECT runs FROM mlb_bat_games WHERE batter_id=?", (SOTO,)).fetchone()[0] is None
    # Tonight's game, still on when his log was read, is never kept: a row
    # once stored is never asked about again. Once it is final it is.
    conn3 = F._conn()
    live = lambda pid, group, season, kind="": _log(pid, [(775900, "2026-10-05", 0, 0, 1),  # noqa: E731
                                                          (776900, "2026-10-14", 1, 0, 0)])
    MC.fill_bat(conn3, 2026, fetch=live, today=TODAY)
    assert conn3.execute("SELECT COUNT(*) FROM mlb_bat_games WHERE game_pk=776900").fetchone()[0] == 0
    D.upsert_mlb_games(conn3, MC.games_info(_schedule(
        _game(776900, "2026-10-14", _team(147, "NYY", 6, 3, 1), _team(116, "DET", 2, 1, 3), kind="D"))))
    conn3.execute("DELETE FROM mlb_bat_games WHERE batter_id=?", (JUDGE,))
    MC.fill_bat(conn3, 2026, fetch=live, today=TODAY)
    assert conn3.execute("SELECT runs FROM mlb_bat_games WHERE game_pk=776900 AND batter_id=?",
                         (JUDGE,)).fetchone()[0] == 1, "a final he only ran in is his"
    # The budget: one hitter a night here, the rest left for the next.
    conn2 = F._conn()
    one = MC.fill_bat(conn2, 2026, budget=1, fetch=fetch, today=TODAY)
    assert (one["hitters"] + one["failed"], one["left"]) == (1, 2)


# --- barrels ------------------------------------------------------------------------------
def test_a_barrel_is_mlbs_published_window():
    assert MC.barrel(98, 26) and MC.barrel(98, 30) and not MC.barrel(98, 25) and not MC.barrel(98, 31)
    assert MC.barrel(100, 24) and MC.barrel(100, 33) and not MC.barrel(100, 34)
    assert MC.barrel(116, 8) and MC.barrel(116, 50) and not MC.barrel(116, 7) and not MC.barrel(120, 51)
    assert not MC.barrel(97.9, 28) and not MC.barrel(None, 28) and not MC.barrel(105, None)
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    hr = d["games"][0]["pas"][0]
    assert hr["et"] == "home_run" and hr["br"] == 1, "110 mph at 28 degrees"
    assert not any(p.get("br") for g in d["games"] for p in g["pas"][1:] if p is not hr)
    assert d["season_line"]["brl"] == 1 and d["games"][1]["line"]["brl"] == 0


# --- the video -----------------------------------------------------------------------------
def _with_ids(payload, ids):
    out = json.loads(json.dumps(payload))
    for play in out["allPlays"]:
        ab = play.get("about", {}).get("atBatIndex")
        for ev in play.get("playEvents") or []:
            if ev.get("isPitch") and ab in ids:
                ev["playId"] = f"{ids[ab]}-{ev['pitchNumber']}"
    return out


def test_each_plate_appearance_keeps_the_id_of_the_pitch_it_ended_on():
    pay = _with_ids(F.PAYLOAD, {1: "aaaa", 3: "bbbb"})
    assert MC.play_ids(pay) == {0: "", 1: "aaaa-2", 2: "", 3: "bbbb-1", 4: "", 5: ""}
    pas, _ = MC.fold(pay, F.GAME)
    assert {p["at_bat"]: p["play_id"] for p in pas} == {0: "", 1: "aaaa-2", 2: "", 3: "bbbb-1"}, \
        "the last pitch's id; read and none is '', never NULL"
    conn = D.connect(":memory:")
    D.upsert_mlb_pa(conn, pas)
    d = MC.hits_chart(conn, "Aaron Judge")
    assert [p.get("vid") for p in d["games"][0]["pas"]] == ["aaaa-2", "bbbb-1"]
    assert "vid" not in {k for p in MC.hits_chart(F._conn(), "Juan Soto")["games"][0]["pas"] for k in p}


def test_the_last_months_games_read_before_the_ids_were_kept_are_read_again_once():
    conn = F._conn()
    D.upsert_mlb_pa(conn, [{"game_pk": 760000, "at_bat": 0, "season": 2026, "date": "2026-08-01",
                            "batter_id": JUDGE, "batter": "Aaron Judge", "team": "NYY", "opponent": "BOS",
                            "home": 1, "event": "Single", "event_type": "single", "rbi": 0, "pitches": 1}])
    conn.execute("UPDATE mlb_pa SET play_id=NULL")
    conn.commit()
    read = []

    def fetch(pk):
        read.append(pk)
        return _with_ids(F.PAYLOAD, {1: "cccc"}) if pk == 776001 else {"allPlays": [
            {"about": {"atBatIndex": 0}, "playEvents": [{"isPitch": True, "pitchNumber": 1}]}]}

    got = MC.fill_play_ids(conn, 2026, fetch=fetch)
    assert sorted(read) == [775900, 776001], "the last month only, newest first; August's game is left"
    assert read[0] == 776001 and got["games"] == 2 and got["left"] == 0
    ids = dict(conn.execute("SELECT at_bat, play_id FROM mlb_pa WHERE game_pk=776001").fetchall())
    assert ids == {0: "", 1: "cccc-2", 2: "", 3: ""}
    assert conn.execute("SELECT play_id FROM mlb_pa WHERE game_pk=775900").fetchone()[0] == "", \
        "a game the feed gives no id is written '' and never read again"
    assert MC.fill_play_ids(conn, 2026, fetch=fetch)["games"] == 0 and len(read) == 2
    assert MC.fill_play_ids(D.connect(":memory:"), 2026, fetch=fetch) == {"games": 0, "pas": 0, "left": 0}


def test_an_old_database_gains_the_column():
    d = tempfile.mkdtemp()
    try:
        path = os.path.join(d, "old.db")
        raw = sqlite3.connect(path)
        # The table as the hit tracker first kept it: every column but the id.
        cols = ", ".join(c for c in MC.PA_COLS if c != "play_id")
        raw.execute(f"CREATE TABLE mlb_pa ({cols}, PRIMARY KEY (game_pk, at_bat))")
        raw.execute("INSERT INTO mlb_pa (game_pk, at_bat, season, batter_id) VALUES (1, 0, 2026, 5)")
        raw.commit()
        raw.close()
        conn = D.connect(path)
        assert "play_id" in {r[1] for r in conn.execute("PRAGMA table_info(mlb_pa)")}
        assert conn.execute("SELECT play_id FROM mlb_pa").fetchone()[0] is None, "a row read before: NULL"
        assert {r[1] for r in conn.execute("PRAGMA table_info(mlb_bat_games)")} >= {"game_pk", "batter_id", "runs", "sb"}
        conn.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- MLB's own numbers ---------------------------------------------------------------------
EXPECTED_CSV = ('﻿"last_name, first_name","player_id","year","pa","bip","ba","est_ba","est_ba_minus_ba_diff",'
                '"slg","est_slg","est_slg_minus_slg_diff","woba","est_woba","est_woba_minus_woba_diff"\n'
                '"Judge, Aaron",592450,2026,700,450,.331,.318,.013,.701,.689,.012,.458,.451,.007\n'
                '"Nobody, A",,2026,1,1,.000,.000,0,.000,.000,0,.000,.000,0\n')
BARRELS_CSV = ('﻿"last_name, first_name","player_id","attempts","avg_hit_angle","anglesweetspotpercent",'
               '"max_hit_speed","avg_hit_speed","ev50","fbld","gb","max_distance","avg_distance","avg_hr_distance",'
               '"ev95plus","ev95percent","barrels","brl_percent","brl_pa"\n'
               '"Judge, Aaron",592450,450,18.5,38.2,118.4,96.0,105.1,95.2,88.1,470,190,420,280,62.2,90,20.0,12.9\n'
               '"Soto, Juan",665742,400,12.0,35.0,115.0,93.0,101.0,93.0,86.0,450,170,410,200,50.0,0.5,0.5,0.3\n')


def _savant_dir():
    d = Path(tempfile.mkdtemp())
    old = savant.CACHE_DIR
    savant.CACHE_DIR = d
    savant._PAGE.clear()
    return d, old


def test_mlbs_own_numbers_are_read_off_the_file_by_his_id_and_never_the_wire():
    d, old = _savant_dir()
    try:
        assert savant.page_board(2026) == {}, "no file, nothing"
        e, b = savant.page_names(2026)
        (d / e).write_text(EXPECTED_CSV, encoding="utf-8")
        (d / b).write_text(BARRELS_CSV, encoding="utf-8")
        board = savant.page_board(2026)
        j = board[JUDGE]
        assert (j["xba"], j["xslg"], j["ba"], j["slg"]) == (0.318, 0.689, 0.331, 0.701)
        assert (j["brl_pct"], j["brl"], j["bbe"]) == (0.2, 90, 450)
        assert j["at"] == dt.date.fromtimestamp((d / b).stat().st_mtime).isoformat()
        assert board[SOTO]["brl_pct"] == 0.005, "a rate in percent is always divided by 100"
        assert set(board) == {JUDGE, SOTO}, "a row with no player id is no one"
        assert savant.page_board(2026) is board, "kept until a file changes"
        os.utime(d / e, (time.time() + 5, time.time() + 5))
        assert savant.page_board(2026) is not board
        out = MC.hits_chart(F._conn(), "Aaron Judge")
        assert out["savant"]["xba"] == 0.318 and out["savant"]["brl_pct"] == 0.2
        assert MC.hits_chart(F._conn(), "Riley Greene")["savant"] is None
    finally:
        savant.CACHE_DIR = old
        savant._PAGE.clear()
        shutil.rmtree(d, ignore_errors=True)


def test_the_nightly_fetches_every_hitters_board_under_the_pages_own_names():
    asked = []
    old = savant.fetch_text
    savant.fetch_text = lambda url, name, ttl=0: asked.append((url, name, ttl)) or (
        EXPECTED_CSV if "expected" in url else BARRELS_CSV)
    try:
        assert savant.fetch_page_boards(2026) == {"expected": 2, "barrels": 2}
    finally:
        savant.fetch_text = old
    (u1, n1, t1), (u2, n2, t2) = asked
    assert "expected_statistics" in u1 and "min=1" in u1 and "min=q" not in u1 and "year=2026" in u1
    assert "leaderboard/statcast" in u2 and "min=1" in u2 and "min=50" not in u2
    assert (n1, n2) == savant.page_names(2026) and t1 == t2 == savant.PAGE_TTL
    assert "min=q" in savant.SAVANT_EXPECTED and "min=50" in savant.SAVANT_BARRELS, "the model's boards are as they were"


def test_the_models_boards_are_no_longer_frozen_on_their_first_file():
    """The same bug the NFL loaders had (tests/test_roster_freshness.py):
    a cached file was read before the fetch layer was asked, and the fetch
    layer writes under that very name — so the first file was served for
    good and the six-hour ttl was dead."""
    d, old_dir = _savant_dir()
    asked = []
    old = savant.fetch_text
    try:
        (d / "savant_barrels_batter_2026.csv").write_text(BARRELS_CSV, encoding="utf-8")
        (d / "savant_expected_batter_2026.csv").write_text(EXPECTED_CSV, encoding="utf-8")
        savant.fetch_text = lambda url, name, ttl=0: asked.append((name, ttl)) or (
            EXPECTED_CSV if "expected" in url else BARRELS_CSV)
        assert savant.load_barrels(2026)["aaron judge"]["barrel_pct"] == 0.2
        assert savant.load_expected_stats(2026)["aaron judge"].xslg == 0.689
        assert asked == [("savant_barrels_batter_2026.csv", 6 * 3600), ("savant_expected_batter_2026.csv", 6 * 3600)]
    finally:
        savant.fetch_text = old
        savant.CACHE_DIR = old_dir
        shutil.rmtree(d, ignore_errors=True)
    src = (ROOT / "engine" / "mlb" / "sources" / "savant.py").read_text(encoding="utf-8")
    assert "load_local_csv(local)" not in src


# --- the photo ---------------------------------------------------------------------------
def test_his_action_photo_off_mlbs_own_cdn():
    assert mlbstats.action_url(JUDGE) == ("https://img.mlbstatic.com/mlb-photos/image/upload/"
                                          "w_480,q_auto:best/v1/people/592450/action/hero/current")
    assert mlbstats.action_url(None) == "" and mlbstats.action_url(0) == "" and mlbstats.action_url("x") == ""
    assert "d_people" not in mlbstats.ACTION_PHOTO, "no default image: a man with none falls back to his headshot"
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    assert d["action"] == mlbstats.action_url(JUDGE) and d["face"] == mlbstats.headshot_url(JUDGE)


# --- the fills ---------------------------------------------------------------------------------
def test_the_chart_fill_reads_the_pages_numbers_the_hour_the_code_lands():
    conn = D.connect(":memory:")
    D.upsert_games(conn, [{"sport": "mlb", "season": 2026, "period": "2026-10-11", "game_id": "776001",
                           "home": "NYY", "away": "DET", "home_score": 4.0, "away_score": 2.0}])
    pas, pitches = MC.fold(F.PAYLOAD, F.GAME)
    D.upsert_mlb_pa(conn, pas)
    D.upsert_mlb_pitches(conn, pitches)
    assert CF.owed(conn, TODAY) == [("mlb", 2026, "mlb_games")]
    called = []
    old = MC.fill_page
    MC.fill_page = lambda c, today=None: called.append(c) or {
        "info": {2026: 12}, "bat": {2026: {"hitters": 3, "games": 40, "failed": 0, "left": 5}},
        "play_ids": {"games": 2, "pas": 9, "left": 0}, "savant": {2026: {"expected": 600, "barrels": 610}}}
    try:
        lines = CF.fill(conn, CF.owed(conn, TODAY), log=lambda *_: None)
    finally:
        MC.fill_page = old
    assert called == [conn]
    assert lines == ["mlb hit page 2026: 12 games' park, final and records",
                     "mlb hit page 2026: runs and steals for 3 hitter(s), 40 game(s), 5 left for the next nights",
                     "mlb hit page: video ids for 2 game(s), 9 at-bat(s)",
                     "mlb hit page 2026: Baseball Savant expected stats 600, barrels 610"], lines
    D.upsert_mlb_games(conn, MC.games_info(SCHEDULE))
    assert CF.owed(conn, TODAY) == [], "a season with its games stored is the nightly's from here"


def test_one_failing_part_never_stops_the_others():
    conn = F._conn()
    D.upsert_mlb_games(conn, MC.games_info(SCHEDULE))
    olds = (MC.fill_info, MC.fill_bat, MC.fill_play_ids, savant.fetch_page_boards)

    def boom(*a, **k):
        raise RuntimeError("down")

    MC.fill_info = boom
    MC.fill_bat = lambda c, s, budget=0, today=None: {"hitters": 2, "games": 7, "failed": 0, "left": 0}
    MC.fill_play_ids = boom
    savant.fetch_page_boards = lambda y: {"expected": 3, "barrels": 3}
    d, old_dir = _savant_dir()
    try:
        got = MC.fill_page(conn, today=TODAY)
    finally:
        MC.fill_info, MC.fill_bat, MC.fill_play_ids, savant.fetch_page_boards = olds
        savant.CACHE_DIR = old_dir
        shutil.rmtree(d, ignore_errors=True)
    assert got["info"].startswith("failed") and got["play_ids"].startswith("failed")
    assert got["bat"] == {2026: {"hitters": 2, "games": 7, "failed": 0, "left": 0}}
    assert got["savant"] == {2026: {"expected": 3, "barrels": 3}, 2025: {"expected": 3, "barrels": 3}}, \
        "last season's boards once, when they are not on file"
    lines = MC.page_lines(got)
    assert any(line.startswith("  ⚠️  mlb hit page parks: failed") for line in lines)


def test_the_nightly_chores_read_them_after_the_backfill():
    i = MAINT.index("back = _mlbc.backfill(_mc, today.year, yesterday.isoformat())")
    j = MAINT.index("_mlbc.page_lines(_mlbc.fill_page(_mc, today=today))")
    assert i < j < MAINT.index('log(f"  ⚠️  mlb charts failed: {exc}")', i)


def test_the_box_check_says_each_piece_in_a_line():
    spec = importlib.util.spec_from_file_location("hitpagecheck", ROOT / "hitpagecheck.py")
    H = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(H)
    lines = H.report(_rich(), TODAY, probe=lambda url: "200 image/jpeg")
    text = "\n".join(lines)
    assert lines[0] == "hit page check — 2026-10-14, season 2026"
    assert "1. runs and steals 2026: 1 of 3 hitters have every game" in text
    assert "the record after the game on 2 club-games, the day before on 0, neither on 0; 2 records shown" in text
    assert "   NYY 2026-10-05 KC@NYY 1-4: the league says 1-0" in text
    assert "3. parks: 2 of 2 games have one" in text and "https://www.mlb.com/gameday/776001" in text
    assert "4. barrels 2026: 1 of 3 balls in play by MLB's rule (33.3%" in text
    assert "5. Baseball Savant 2026:" in text
    assert "6. video 2026: 4 of 5 plate appearances" in text and "sporty-videos?playId=" in text
    assert lines[-1].startswith("7. action photo: https://img.mlbstatic.com/") and lines[-1].endswith("→ 200 image/jpeg")
    # A database the app has not yet given the new tables says so, part by part.
    old = sqlite3.connect(":memory:")
    old.execute("CREATE TABLE mlb_pa (game_pk INTEGER, at_bat INTEGER, season INTEGER, date TEXT, batter_id INTEGER, "
                "launch_speed REAL, launch_angle REAL)")
    old.execute("INSERT INTO mlb_pa VALUES (1, 0, 2026, '2026-10-01', 5, 101.0, 25.0)")
    got = H.report(old, TODAY)
    assert any(x.startswith("1. not there yet: no such table: mlb_bat_games") for x in got), got
    assert any(x.startswith("4. barrels 2026: 1 of 1") for x in got) and got[-1].endswith("(not asked)")
    assert "def main(argv=None)" in (ROOT / "hitpagecheck.py").read_text(encoding="utf-8")
    assert 'mode=ro' in (ROOT / "hitpagecheck.py").read_text(encoding="utf-8"), "read-only, never created"


# --- the page ------------------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{MLB_JS}\n"
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


def _chart():
    d = MC.hits_chart(_rich(), "Aaron Judge")
    d["savant"] = {"xba": 0.318, "xslg": 0.689, "brl_pct": 0.2, "bbe": 450, "brl": 90, "at": "2026-10-13"}
    return d


def test_the_page_draws_each_piece_where_it_is_on_file():
    d = _chart()
    got = _node(f"""
      const d = {json.dumps(d)}, SP = T.DRAW.spray, X = SP._t, post = d.games[0], reg = d.games[1];
      const bare = Object.assign({{}}, reg, {{ r: undefined, sb: undefined }});
      return {{
        tiles: X.gameTiles(post), bare: X.gameTiles(bare), head: X.gameHead(post, "mlb"), regHead: X.gameHead(reg, "mlb"),
        board: X.scoreBoard(reg, "mlb"), postBoard: X.scoreBoard(post, "mlb"), watch: X.watch(post), plain: X.watch(reg),
        side: SP.seasonSide(d), list: SP.list(post, d), csv: SP.csv(post, d), own: X.mlbOwn(d),
        noOwn: X.mlbOwn(Object.assign({{}}, d, {{ savant: null }})), where: X.where({{ dh: 2, venue: "Fenway Park" }}),
        sums: [X.sumOf([{{ r: 1 }}, {{ r: 2 }}], "r"), X.sumOf([{{ r: 1 }}, {{}}], "r"), X.sumOf([], "r")],
        brl: X.line(post.pas).brl,
      }};""")
    if got is None:
        return
    # 1. Runs and stolen bases, the game's own and the season's.
    assert ">R<" in got["tiles"] and ">SB<" in got["tiles"] and "cc-tiles-2" in got["tiles"]
    assert ">R<" not in got["bare"] and ">SB<" not in got["bare"] and "cc-tiles-6" in got["bare"]
    assert ">Runs<" in got["side"] and ">Stolen bases<" in got["side"] and "mb-big6" in got["side"]
    assert got["sums"] == [3, None, None]
    # 2. The record on the day under each club, in the regular season.
    assert '<small class="mb-rec">1-0</small>' in got["board"] and '<small class="mb-rec">0-1</small>' in got["board"]
    assert "mb-rec" not in got["postBoard"]
    # 3. The park, the series, and MLB's own page of the game.
    assert "@ Yankee Stadium · Division Series, Game 3" in got["head"] and "@ Yankee Stadium" in got["regHead"]
    assert 'href="https://www.mlb.com/gameday/776001"' in got["head"] and 'target="_blank"' in got["head"]
    assert 'rel="noopener noreferrer"' in got["head"] and "View game" in got["head"]
    assert got["where"] == "@ Fenway Park · Game 2 of a doubleheader"
    # 4. Barrels: the ball's own, the game's and the season's rate.
    assert got["brl"] == 1 and "mb-brl" in got["list"] and ">Barrel %<" in got["side"] and ">33%<" in got["side"]
    # 5. MLB's own numbers beside ours, with the day they were read.
    assert "MLB’s own · Baseball Savant · as of Oct 13" in got["own"]
    assert "<b>.318</b> xBA" in got["own"] and "<b>.689</b> xSLG" in got["own"] and "<b>20.0%</b> barrels of 450 balls" in got["own"]
    assert got["noOwn"] == "" and "MLB’s own" in got["side"]
    # 6. Every at-bat's video, numbered as the table numbers it, and the game's every pitch.
    vid = "5a1b2c3d-0000-4000-8000-00000000000" + "1"                     # his at-bat 1's, as _rich() keeps it
    assert f'href="https://baseballsavant.mlb.com/sporty-videos?playId={vid}"' in got["watch"]
    assert got["watch"].count('class="mb-vchip') == 2 and "<b>1</b>" in got["watch"] and "<b>2</b>" in got["watch"]
    assert 'href="https://baseballsavant.mlb.com/gamefeed?gamePk=776001"' in got["watch"] and "Every pitch" in got["watch"]
    assert "mb-vchip" not in got["plain"] and "Watch at-bats" in got["plain"] and "gamePk=775900" in got["plain"]
    assert "<a " not in got["list"], "a link is never put inside a row's button"
    assert got["csv"][0][-2:] == ["Barrel", "Video"] and got["csv"][1][-2] == "yes"
    assert got["csv"][1][-1].startswith("https://baseballsavant.mlb.com/sporty-videos?playId=")


def test_the_photo_steps_aside_for_the_headshot_when_it_fails():
    got = _node("""
      const mk = () => { const a = { cls: [], gone: false, classList: { add: (c) => a.cls.push(c) }, remove() { a.gone = true; } };
                         return a; };
      const a1 = mk(), a2 = mk(), s1 = {}, s2 = {};
      T.faceStep("load", { tagName: "IMG", closest: (q) => (q === ".cc-act" ? a1 : null) }, s1);
      T.faceStep("error", { tagName: "IMG", closest: (q) => (q === ".cc-act" ? a2 : null) }, s2);
      const face = { cls: [], classList: { add: (c) => face.cls.push(c) } };
      const img = { tagName: "IMG", src: "a", closest: (q) => (q === ".cc-face" ? face : null), parentNode: face };
      const s3 = { faces: ["a", "b"], fi: 0 };
      T.faceStep("error", img, s3);
      return { a1: a1.cls, s1: s1.act, gone: a2.gone, s2: s2.act, src: img.src, fi: s3.fi };""")
    if got is None:
        return
    assert got == {"a1": ["on"], "s1": True, "gone": True, "s2": False, "src": "b", "fi": 1}
    hero = MLB_JS[MLB_JS.index("  function hero(d, sport) {"):MLB_JS.index("  /* ---------------- the park")]
    assert 'class="cc-act${S && S.act ? " on" : ""}"' in hero and "!(S && S.act === false)" in hero
    assert ".mb-hero-face .cc-act.on + .cc-face { display: none; }" in CC_CSS


def test_the_styles_are_tokens_and_the_handlers_are_listeners():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    for sel in (".mb-hero-face .cc-act.on", ".mb-rec", ".mb-watch", ".mb-vchip", ".mb-own", ".mb-big.mb-big6",
                ".mb-at", ".mb-brl"):
        assert sel in CC_CSS, sel
    assert "onclick" not in MLB_JS and "onerror" not in MLB_JS and not re.search(r"on(error|load)\s*=", MLB_JS)


# --- the browser, opt-in --------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i>${{a}}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.fetch = async (q) => ({{ ok: true, json: async () => window.CHART }});
</script>
<script>{js}</script></body></html>"""
PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def test_in_a_browser_the_photo_the_links_and_the_tiles():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    d = _chart()
    d.update(seasons=[2026], position="RF", jersey="99", kind="spray", face=PNG, action=PNG)
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            for action, shows in ((PNG, True), ("data:image/png;base64,bm90IGFuIGltYWdl", False)):
                page = browser.new_page(viewport={"width": 390, "height": 900})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.set_content(PAGE.format(css=CC_CSS, js=CC_JS + "\n" + MLB_JS))
                page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Aaron Judge', 'mlb', 'spray'); }",
                              dict(d, action=action))
                page.wait_for_selector("#cc-overlay .mb-hero", timeout=5000)
                if shows:
                    page.wait_for_selector(".mb-hero-face .cc-act.on", timeout=3000)
                    assert page.evaluate("getComputedStyle(document.querySelector('.mb-hero-face .cc-face')).display") == "none"
                else:
                    page.wait_for_function("!document.querySelector('.mb-hero-face .cc-act')", timeout=3000)
                    assert page.evaluate("getComputedStyle(document.querySelector('.mb-hero-face .cc-face')).display") != "none"
                # The game: the park, the series, MLB's page, the runs and steals, the videos.
                head = page.evaluate("document.querySelector('.mb-game-h').textContent.replace(/\\s+/g, ' ')")
                assert "@ Yankee Stadium · Division Series, Game 3" in head and "View game" in head
                assert page.evaluate("document.querySelector('.mb-game-h a.mb-ext').href") == "https://www.mlb.com/gameday/776001"
                assert page.evaluate("document.querySelectorAll('.mb-watch a.mb-vchip').length") == 2
                assert page.evaluate("document.querySelectorAll('button a, a button').length") == 0
                tiles = page.evaluate("[...document.querySelectorAll('.mb-game .cc-tile .cc-k')].map((k) => k.textContent)")
                assert "R" in tiles and "SB" in tiles, tiles
                # The regular-season game: each club's record under its score.
                page.click(".cc-chip[data-gi='1']")
                assert page.evaluate("[...document.querySelectorAll('.mb-rec')].map((x) => x.textContent)") == ["1-0", "0-1"]
                # The season: six counting numbers, barrels, MLB's own.
                page.click("[data-view='season']")
                page.wait_for_selector(".mb-stats", timeout=3000)
                assert page.evaluate("document.querySelectorAll('.mb-big6 .cc-tile').length") == 6
                own = page.evaluate("document.querySelector('.mb-own').textContent")
                assert "xBA" in own and "Baseball Savant" in own
                assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
                assert page.evaluate("(() => { const c = document.querySelector('#cc-overlay .cc'); return c.scrollWidth - c.clientWidth; })()") == 0
                assert not errors, errors
                page.close()
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
