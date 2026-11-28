"""The league ranks on a player's page survive a restart (step AFO, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". The page's timing line (step AFK) said where a
slow one went: Kerby Joseph's page took 3.7 s to answer, 3.5 s of it building the league's table of defenders'
places, and the next defender's page took 62 ms. The tables lived only in the server's memory, so every restart
(each deploy) emptied them, and the first reader of each kind's page waited for its build until `warm` ran, which on
the box is after the boards are rebuilt. Now:

  * each table built is written beside the history file (cache/ranks/<league>_<season>_<kind>.json), with when it
    was built and a stamp of the code that built it (engine/playerpage.py and engine/gamelog.py);
  * a table missing from memory is read from there; past RANK_TTL (six hours) it answers while a new one is built,
    as a kept one always has; so does one written by other code (step AGE), built over behind it;
  * `warm` takes a fresh file instead of building, and `forget_ranks` drops the files with the tables.

Offline. Run directly: `python3 tests/test_the_league_ranks_survive_a_restart.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, playerpage as PP  # noqa: E402


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = [{"sport": "nfl", "season": 2026, "period": f"{w:03d}", "game_id": f"{t}-{w:03d}", "player": p, "team": t,
             "opponent": "GB", "position": "QB", "home": 1, "market": m, "value": v}
            for w in range(1, 4)
            for p, t, base in (("Jared Goff", "DET", 280.0), ("Jordan Love", "GB", 240.0))
            for m, v in (("pass_yds", base + w), ("pass_att", 35.0), ("pass_cmp", 24.0), ("pass_tds", 2.0))]
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    db.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": f"{w:03d}", "game_id": f"DET-{w:03d}",
                            "home": "DET", "away": "GB", "home_score": 24, "away_score": 17} for w in range(1, 4)])
    conn.commit()
    conn.close()
    return path


def _file(path, kind="passing"):
    return os.path.join(os.path.dirname(path), "cache", "ranks", f"nfl_2026_{kind}.json")


def test_a_table_built_is_kept_on_disk_and_read_back_after_a_restart():
    path = _history()
    PP._RANKS.clear()
    conn = db.connect(path)
    try:
        built = PP.rank_table(conn, "nfl", 2026, "passing", db_path=path)
    finally:
        conn.close()
    assert built["yds"] == {"Jared Goff": 1, "Jordan Love": 2}, built
    doc = json.loads(Path(_file(path)).read_text(encoding="utf-8"))
    assert doc["table"] == built and doc["code"] == PP._RANKS_CODE and time.time() - doc["built"] < 60
    PP._RANKS.clear()                                  # a restart
    real = PP._build_table
    PP._build_table = lambda *a, **k: (_ for _ in ()).throw(AssertionError("built again"))
    try:
        conn = db.connect(path)
        try:
            again = PP.rank_table(conn, "nfl", 2026, "passing")          # db_path from the connection itself
        finally:
            conn.close()
    finally:
        PP._build_table = real
    assert again == built, "read from disk, not built"
    PP._RANKS.clear()


def test_an_old_file_answers_while_a_new_table_is_built_and_so_does_other_codes():
    path = _history()
    PP._RANKS.clear()
    os.makedirs(os.path.dirname(_file(path)), exist_ok=True)
    old = {"yds": {"Jordan Love": 1}}
    Path(_file(path)).write_text(json.dumps({"built": time.time() - PP.RANK_TTL - 5, "code": PP._RANKS_CODE,
                                             "table": old}), encoding="utf-8")
    conn = db.connect(path)
    try:
        assert PP.rank_table(conn, "nfl", 2026, "passing", db_path=path) == old, "the old table answers at once"
    finally:
        conn.close()
    key = ("nfl", 2026, "passing")
    for _ in range(300):
        if key not in PP._REFRESHING and PP._RANKS[key][1] != old:
            break
        time.sleep(0.02)
    assert PP._RANKS[key][1]["yds"]["Jared Goff"] == 1, "and a new one replaces it"
    assert json.loads(Path(_file(path)).read_text(encoding="utf-8"))["table"]["yds"]["Jared Goff"] == 1
    # A file another version of the code wrote answers too, as an old one: at once, and built over behind it
    # (step AGE; until then it was never read, so every update emptied every league's places for a while).
    PP._RANKS.clear()
    Path(_file(path)).write_text(json.dumps({"built": time.time(), "code": "elsewhere", "table": old}),
                                 encoding="utf-8")
    conn = db.connect(path)
    try:
        assert PP.rank_table(conn, "nfl", 2026, "passing", db_path=path, wait=False) == old
    finally:
        conn.close()
    for _ in range(300):
        if key not in PP._REFRESHING and PP._RANKS[key][1] != old:
            break
        time.sleep(0.02)
    assert PP._RANKS[key][1]["yds"]["Jared Goff"] == 1, "and the new code's replaces it"
    assert json.loads(Path(_file(path)).read_text(encoding="utf-8"))["code"] == PP._RANKS_CODE
    PP._RANKS.clear()


def test_warm_takes_a_fresh_file_and_forget_drops_the_files():
    path = _history()
    PP._RANKS.clear()
    PP.warm(db_path=path, delay=0).join(timeout=60)
    assert os.path.exists(_file(path)), "warm keeps what it builds"
    PP._RANKS.clear()
    real, calls = PP._build_table, []
    PP._build_table = lambda conn, sport, season, kind: (calls.append(kind), real(conn, sport, season, kind))[1]
    try:
        PP.warm(db_path=path, delay=0).join(timeout=60)
    finally:
        PP._build_table = real
    assert ("nfl", 2026, "passing") in PP._RANKS and "passing" not in calls, calls
    # Warm puts another code's file in first, so pages answer with it, then builds it again (step AGE).
    PP._RANKS.clear()
    doc = json.loads(Path(_file(path)).read_text(encoding="utf-8"))
    Path(_file(path)).write_text(json.dumps(dict(doc, code="elsewhere")), encoding="utf-8")
    seen = []
    PP._build_table = lambda conn, sport, season, kind: (
        seen.append((kind, ("nfl", 2026, "passing") in PP._RANKS)), real(conn, sport, season, kind))[1]
    try:
        PP.warm(db_path=path, delay=0).join(timeout=60)
    finally:
        PP._build_table = real
    assert ("passing", True) in seen, "answering with the old one while it built the new"
    assert json.loads(Path(_file(path)).read_text(encoding="utf-8"))["code"] == PP._RANKS_CODE
    assert PP.forget_ranks("nfl", db_path=path) >= 1
    assert not [f for f in os.listdir(os.path.dirname(_file(path))) if f.startswith("nfl_")], "the files go too"
    PP._RANKS.clear()


def test_an_in_memory_database_keeps_nothing_on_disk():
    conn = db.connect(":memory:")
    try:
        assert PP._ranks_file(conn, ("nfl", 2026, "passing")) == ""
    finally:
        conn.close()
    PP._ranks_save("", 0.0, {})                        # nothing to write to, nothing raised
    assert PP._ranks_load("") is None


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
