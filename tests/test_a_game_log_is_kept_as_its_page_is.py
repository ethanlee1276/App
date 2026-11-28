"""A player's game log is kept as his page is (step AGV, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". Every player page asks for its game log beside its numbers (step AFT), and the log was read
again on every visit: 0.1 to 0.7 s of the server's own time on the live site (Juan Soto's 162-game season, 0.67 s).
It is now kept as the page is: five minutes; past that, up to the hour while his games are the ones it was read
from, answered at once and read again behind it; a box score of his since, and it is read before it answers.

Offline. Run directly: `python3 tests/test_a_game_log_is_kept_as_its_page_is.py`
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())


def _until(check, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


def _handler(sent):
    import server
    h = object.__new__(server.Handler)
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, json.loads(body), headers))
    return h


def test_the_log_is_kept_read_behind_and_read_again_for_a_new_game():
    import server
    real_made, real_stamp = server._gamelog_made, server._player_games_stamp
    made, stamp, slow = [], [("Juan Soto", 150, 900)], threading.Event()

    def stand_in(sport, player, club, season):
        made.append(player)
        if len(made) == 2:
            slow.wait(5)                                  # the read behind is slow; the reader must not wait
        return json.dumps({"player": "Juan Soto", "n": len(made)}).encode()
    server._gamelog_made = stand_in
    server._player_games_stamp = lambda sport, body: stamp[0]
    server._GAMELOGS.clear()
    sent = []
    try:
        h = _handler(sent)
        q = {"sport": ["mlb"], "player": ["Juan Soto"]}
        h._players_gamelog(q)
        h._players_gamelog(q)
        assert [s[1]["n"] for s in sent] == [1, 1] and len(made) == 1, "kept"
        assert sent[1][2] == [("Server-Timing", "kept;dur=0")]
        key = next(iter(server._GAMELOGS))
        server._GAMELOGS[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._GAMELOGS[key][1:]
        t0 = time.time()
        h._players_gamelog(q)
        assert sent[-1][1]["n"] == 1 and time.time() - t0 < 1.0, "past its five minutes: at once..."
        assert sent[-1][2] == [("Server-Timing", "stale;dur=0")]
        assert _until(lambda: len(made) == 2), "...and read again behind it"
        slow.set()
        assert _until(lambda: json.loads(server._GAMELOGS[key][1])["n"] == 2)
        server._GAMELOGS[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._GAMELOGS[key][1:]
        stamp[0] = ("Juan Soto", 151, 905)                # a box score of his since
        h._players_gamelog(q)
        assert len(made) == 3 and sent[-1][1]["n"] == 3, "a game since: read before it answers"
        h._players_gamelog({"sport": ["nope"], "player": ["Juan Soto"]})
        assert sent[-1][0] == 400
    finally:
        slow.set()
        server._gamelog_made, server._player_games_stamp = real_made, real_stamp
        server._GAMELOGS.clear()


def test_the_kept_logs_stay_under_their_count():
    import server
    real = server._player_games_stamp
    server._player_games_stamp = lambda sport, body: None
    server._GAMELOGS.clear()
    keep = server.GAMELOG_KEEP
    try:
        server.GAMELOG_KEEP = 3
        for i in range(5):
            server._gamelog_keep(("nba", f"p{i}", "", ""), b"{}")
        assert len(server._GAMELOGS) == 3 and ("nba", "p0", "", "") not in server._GAMELOGS, "the oldest out"
    finally:
        server.GAMELOG_KEEP = keep
        server._player_games_stamp = real
        server._GAMELOGS.clear()


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
