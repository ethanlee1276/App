"""The player search says where its time went (step AHC, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". A player's page opened from its address asks the league search first, and on the live site a
college search ("jeremiah smith") once took 2.9 s, 0.26 s of it work and the rest waiting, then 16 ms asked again. Its
answer said nothing of which read waited. It says each part now, as the page's own answer does: the names, the
games counted for them, each hit's club and face, the roster's top-up.

Offline. Run directly: `python3 tests/test_the_search_says_where_its_time_went.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, statlogs  # noqa: E402


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("cfb", 2026, "12", "g1", "Jeremiah Smith", "OSU", "MICH", "WR", 1, "receptions", 7.0),
                      ("cfb", 2026, "11", "g0", "Jeremiah Smith", "OSU", "PUR", "WR", 0, "receptions", 5.0),
                      ("cfb", 2025, "10", "g9", "Jeremiah Smithers", "UTSA", "NT", "RB", 1, "carries", 9.0)])
    conn.commit()
    conn.close()
    return path


def test_the_parts_are_said_and_the_answer_is_the_same():
    path, data = _history(), tempfile.mkdtemp()
    took = []
    plain = statlogs.search("cfb", "jeremiah smith", db_path=path, data_dir=data)
    timed = statlogs.search("cfb", "jeremiah smith", db_path=path, data_dir=data, took=took)
    assert timed == plain and plain and plain[0]["player"] == "Jeremiah Smith", "timing changes nothing"
    assert [p for p, _ in took] == ["names", "games", "clubs", "roster"], took
    assert all(ms >= 0 for _, ms in took)


def test_the_answer_carries_them():
    import server
    path = _history()
    real = D.DEFAULT_DB
    sent = []
    h = object.__new__(server.Handler)
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, json.loads(body), headers))
    try:
        D.DEFAULT_DB = Path(path)
        h._players_search({"sport": ["cfb"], "q": ["jeremiah smith"], "scope": ["sport"]})
    finally:
        D.DEFAULT_DB = real
    code, body, headers = sent[-1]
    assert code == 200 and body["players"][0]["player"] == "Jeremiah Smith"
    timing = dict(headers)["Server-Timing"]
    for part in ("names;dur=", "games;dur=", "clubs;dur=", "roster;dur="):
        assert part in timing, (part, timing)


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
