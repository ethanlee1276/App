"""A game that ended after its board moved on is still graded and archived
(engine/gamereport._archive_departed), CFBFACT1.

Live on 17 November, How our reports did held 14 NFL games, 12 of college
basketball, 8 of the NBA, 2 of the NHL and none of college football. A
finished report is graded and archived off the board's own game, and college
football's board is a day's: it moves to its next slate at midnight Eastern
while Saturday's late games are still being played, so a final the board no
longer held was never checked; any league's game whose box score lands after
its board has moved had the same end. What these hold:

  * a game off the board, final in the history with its box score in, is
    graded from the report kept before its start and archived, its kept
    tickets and picks with it, and counts on the reports' record; the build's
    line says so, once;
  * a box score not in yet is tried again next build, and a game with no
    final in the history is left alone;
  * a final still on its board is archived the ordinary way and never twice;
  * the NFL, whose board is its week's, is left to that; no board path, or no
    history, archives nothing; a broken kept file never raises.

    python3 tests/test_a_final_off_the_board_is_still_graded.py
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import db, gamereport as R, reportarchive, reportkeep, reportrecord   # noqa: E402
from engine.gate import _full_dir_for                                            # noqa: E402

T = __import__("test_the_college_game_report")                  # the college board and its history (a sibling test)

META = {"MIA@IU": {"neutral_site": False, "conference_game": False}}
DAY = "2026-10-24"


def _out():
    out = Path(tempfile.mkdtemp()) / "web" / "data" / "cfb.json"
    out.parent.mkdir(parents=True)
    return str(out)


def _build(board, conn, out, at):
    return R.attach(board, conn=conn, sport="cfb", season=2026, meta=META, out=out, at=at)


def _final(conn, box=True):
    """The history's own final for Miami at Indiana, and (``box``) its box score."""
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, extra) "
                 "VALUES ('cfb', 2026, ?, 'gfinal', 'IU', 'MIA', 31, 20, '{}')", (DAY,))
    conn.commit()
    if box:
        _box(conn)


def _box(conn):
    rows = []

    def log(player, team, opp, **stats):
        rows.extend({"sport": "cfb", "season": 2026, "period": DAY, "game_id": "gfinal", "player": player,
                     "team": team, "opponent": opp, "position": "", "home": 1 if team == "IU" else 0,
                     "market": k, "value": float(v)} for k, v in stats.items())
    log("Roman Hemby", "IU", "MIA", carries=20, rush_yds=110, rush_td=1, receptions=2, rec_yds=14, rec_td=0)
    log("Elijah Sarratt", "IU", "MIA", receptions=5, rec_yds=70, rec_td=1)
    log("Kurtis Rourke", "IU", "MIA", pass_att=30, pass_yds=250, pass_td=2)
    log("Carson Beck", "MIA", "IU", pass_att=35, pass_yds=260, pass_td=1)
    db.upsert_player_logs(conn, rows)


def _next_slate():
    """The board a week on: the same clubs, another day, so Saturday's game is off it."""
    b = T._board()
    b["date"] = "2026-10-25"
    b["games"][0].update(date="2026-10-31", kickoff="2026-10-31T19:30Z")
    return b


def _kept(out):
    path = reportkeep.path_for("cfb", _full_dir_for(out))
    return path, json.loads(Path(path).read_text(encoding="utf-8"))


def _files(out):
    where = _full_dir_for(out)
    return sorted(str(p.relative_to(where)) for p in Path(where).rglob("*.json.gz"))


def test_a_final_off_the_board_is_graded_from_the_kept_report_and_archived():
    out, conn = _out(), T._conn()
    _build(T._board(), conn, out, f"{DAY}T12:00:00")
    path, kept = _kept(out)
    assert f"MIA@IU|{DAY}" in kept["games"], "kept before its start"
    # What the game's page drew before the start goes with it.
    kept["games"][f"MIA@IU|{DAY}"]["parlays"] = {"home": "IU", "away": "MIA", "game": "MIA@IU", "threes": [
        {"legs": [{"player": "Roman Hemby", "market": "rush_yds", "side": "OVER", "line": 79.5}], "joint": 0.3}]}
    kept["games"][f"MIA@IU|{DAY}"]["picks"] = {"likely": [{"player": "Roman Hemby", "team": "IU", "opponent": "MIA",
                                                         "market": "rush_yds", "side": "Over", "line": 79.5}]}
    Path(path).write_text(json.dumps(kept), encoding="utf-8")
    _final(conn)
    line = _build(_next_slate(), conn, out, "2026-10-25T05:30:00")
    assert "1 more archived after leaving the board" in line, line
    assert _files(out) == [f"report_archive/cfb/{DAY}/MIA@IU.json.gz"], _files(out)
    doc = reportarchive.load("cfb", DAY, "MIA", "IU", where=_full_dir_for(out))
    assert doc["final"] == {"away": 20, "home": 31} and doc["date"] == DAY and doc["label"] == DAY, doc["final"]
    g = doc["report"]["graded"]
    assert g["status"] == "graded" and g["graded"] >= 1, g
    assert doc["parlays"]["threes"] and doc["picks"]["likely"][0]["player"] == "Roman Hemby"
    assert "_bets" not in doc["report"]
    tot = reportrecord.record(_full_dir_for(out), "cfb")["totals"]
    assert tot["games"] == 1 and tot["through"] == DAY, tot
    # Once: the next build finds it archived.
    again = _build(_next_slate(), conn, out, "2026-10-25T06:00:00")
    assert "archived after leaving the board" not in again, again


def test_a_box_score_not_in_yet_is_tried_again_and_no_final_is_left_alone():
    out, conn = _out(), T._conn()
    _build(T._board(), conn, out, f"{DAY}T12:00:00")
    # No final in the history yet: nothing to grade.
    line = _build(_next_slate(), conn, out, "2026-10-25T05:30:00")
    assert "archived" not in line and _files(out) == [], line
    # The final is in, its box score is not: pending, so not archived.
    _final(conn, box=False)
    line = _build(_next_slate(), conn, out, "2026-10-25T05:40:00")
    assert "archived" not in line and _files(out) == [], line
    _box(conn)
    line = _build(_next_slate(), conn, out, "2026-10-25T05:50:00")
    assert "1 more archived after leaving the board" in line, line


def test_a_final_still_on_its_board_is_archived_the_ordinary_way_and_never_twice():
    out, conn = _out(), T._conn()
    _build(T._board(), conn, out, f"{DAY}T12:00:00")
    _final(conn)
    board = T._board()
    board["games"][0]["live"] = {"state": "final", "home_score": 31, "away_score": 20}
    line = _build(board, conn, out, "2026-10-25T01:30:00")
    assert "1 finished report archived" in line and "leaving the board" not in line, line
    # Then the board moves on: the archive already holds it.
    line = _build(_next_slate(), conn, out, "2026-10-25T05:30:00")
    assert "archived" not in line and len(_files(out)) == 1, line


def test_the_nfl_no_path_no_history_and_a_broken_file_archive_nothing():
    out, conn = _out(), T._conn()
    _build(T._board(), conn, out, f"{DAY}T12:00:00")
    _final(conn)
    moved = _next_slate()
    assert R._archive_departed(moved, "nfl", out, conn) == 0, "its board is the week's"
    assert R._archive_departed(moved, "cfb", None, conn) == 0 and R._archive_departed(moved, "cfb", out, None) == 0
    path, kept = _kept(out)
    whole = Path(path).read_text(encoding="utf-8")
    Path(path).write_text("{not json", encoding="utf-8")
    assert R._archive_departed(moved, "cfb", out, conn) == 0
    Path(path).write_text(json.dumps({"games": {"nonsense": {"report": {}}, f"MIA@IU|{DAY}": "x"}}), encoding="utf-8")
    assert R._archive_departed(moved, "cfb", out, conn) == 0
    Path(path).write_text(whole, encoding="utf-8")
    assert R._archive_departed(copy.deepcopy(moved), "cfb", out, conn) == 1
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    i = src.index("def keep_started(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("reportarchive.save(result, reports, sport, out)") \
        < body.index("_archive_departed(result, sport, out, conn)"), "the board's own finals first"
    lr = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert "reports, kept = keep_started(result, reports, sport, out, at, conn)" in lr, "every league's build"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
