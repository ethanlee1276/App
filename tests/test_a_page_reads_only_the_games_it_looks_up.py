"""A player's page and game log read only the games they look up (step AGD, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". A player's page and his game log read every game
of his league's season to find his own results and his club's record: college basketball's season is about 6,000
games, 80 to 350 ms of each college page's answer on the live site. They now read only his clubs' and his
opponents' games (each club's whole season, so a record counts as before) and his own rows' games by id (a game
his school is filed under another code for still answers). What these hold: the read is that narrow, and the page
and the log say exactly what they said reading every game.

Offline. Run directly: `python3 tests/test_a_page_reads_only_the_games_it_looks_up.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, gamelog as GL, playerpage as PP                 # noqa: E402


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    games, rows = [], []
    clubs = [f"C{i:02d}" for i in range(40)]
    gid = 0
    for day in range(1, 21):                                 # the league's other games, every club every day
        for i in range(0, 40, 2):
            gid += 1
            games.append(("cbb", 2026, f"2026-11-{day:02d}", f"g{gid}", clubs[i], clubs[i + 1], 70 + i % 9, 65 + day % 7,
                          f"2026-11-{day:02d}"))
    # His club DUKE: three games, one filed under the school's other code ("DUK") with his row's own id.
    games += [("cbb", 2026, "2026-11-21", "d1", "DUKE", "C00", 80, 70, "2026-11-21"),
              ("cbb", 2026, "2026-11-23", "d2", "C05", "DUKE", 75, 72, "2026-11-23"),
              ("cbb", 2026, "2026-11-25", "d3", "DUK", "C07", 90, 60, "2026-11-25")]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", games)
    for period, g, opp, pts in (("2026-11-21", "d1", "C00", 22), ("2026-11-23", "d2", "C05", 18),
                                ("2026-11-25", "d3", "C07", 30)):
        for m, v in {"min": 33, "pts": pts, "reb": 9, "ast": 3, "fgm": 8, "fga": 15}.items():
            rows.append(("cbb", 2026, period, g, "Cameron Boozer", "DUKE", opp, "F", 1, m, v))
    for i in range(40):                                       # one player a club, so the league table has a field
        rows.append(("cbb", 2026, "2026-11-01", f"g{i // 2 + 1}", f"Player {i}", clubs[i], clubs[i ^ 1], "G", 1, "min", 30))
        rows.append(("cbb", 2026, "2026-11-01", f"g{i // 2 + 1}", f"Player {i}", clubs[i], clubs[i ^ 1], "G", 1, "pts", 10 + i))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def test_the_read_is_his_clubs_his_opponents_and_his_own_games():
    path = _history()
    conn = _db.connect(path)
    every, _ = GL._results(conn, "cbb", 2026)
    mine, pairs = GL._results(conn, "cbb", 2026, clubs={"DUKE", "C00", "C05", "C07"}, ids={"d1", "d2", "d3"})
    conn.close()
    assert len(every) == 403
    assert set(mine) >= {"d1", "d2", "d3"} and len(mine) == 3 + 3 * 20, "his three, and each opponent's twenty"
    assert all({"DUKE", "C00", "C05", "C07"} & {g["home"], g["away"]} or k == "d3" for k, g in mine.items())
    assert ("2026-11-25", frozenset(("DUK", "C07"))) in pairs


def _strip(monkey):
    real = GL._results
    GL._results = lambda conn, sport, season, clubs=None, ids=None: real(conn, sport, season) if monkey else \
        real(conn, sport, season, clubs, ids)
    return real


def test_the_page_and_the_log_say_what_reading_every_game_said():
    path = _history()
    PP._RANKS.clear()
    narrow_page = PP.page("cbb", "Cameron Boozer", db_path=path, data_dir=tempfile.mkdtemp())
    narrow_log = GL.season_log("cbb", "Cameron Boozer", db_path=path)
    real = _strip(True)
    try:
        PP._RANKS.clear()
        wide_page = PP.page("cbb", "Cameron Boozer", db_path=path, data_dir=tempfile.mkdtemp())
        wide_log = GL.season_log("cbb", "Cameron Boozer", db_path=path)
    finally:
        GL._results = real
    assert json.dumps(narrow_page, sort_keys=True) == json.dumps(wide_page, sort_keys=True)
    assert json.dumps(narrow_log, sort_keys=True) == json.dumps(wide_log, sort_keys=True)
    last = narrow_page["last"]
    assert (last["result"], last["score"], last["record"]) == ("W", "90-60", "1-1"), \
        "the game filed under DUK answers by its id; the record counts DUKE's own games, as reading every game did"
    assert [g.get("result") for g in narrow_log["games"]] == ["W", "L", "W"]
    assert [g.get("score") for g in narrow_log["games"]] == ["90-60", "72-75", "80-70"], \
        "the game DUKE is filed under DUK for reads from its own side, by the opponent's code"


def test_home_is_read_off_either_club():
    assert GL.home_of({"home": "DUKE", "away": "C07"}, "DUKE", "C07", 0) is True
    assert GL.home_of({"home": "DUK", "away": "C07"}, "DUKE", "C07", 0) is True, "his opponent's code says it"
    assert GL.home_of({"home": "C07", "away": "DUK"}, "DUKE", "C07", 1) is False
    assert GL.home_of({"home": "X", "away": "Y"}, "DUKE", "C07", 1) is True, "neither: his row's own word"
    assert GL.home_of(None, "DUKE", "C07", 0) is False


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
