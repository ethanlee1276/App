"""A player's market logs are kept as the game log is (step AHB, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". A player not priced tonight asks for
their market logs (/api/players/logs) with their page, for the market cards at its foot, and the logs were read again
on every visit: 20 to 100 ms of the server's own time on the live site, in the one process every page waits behind.
They are kept now as the game log is (step AGV): five minutes; past that, up to the hour while the player's games are
the ones they were read from, answered at once and read again behind; a box score of the player's since, and they are
read before they answer.

Offline. Run directly: `python3 tests/test_a_players_market_logs_are_kept.py`
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


def test_the_logs_are_kept_read_behind_and_read_again_for_a_new_game():
    import server
    real_made, real_stamp = server._player_logs_made, server._player_games_stamp
    made, stamp, slow = [], [("Jalen Brunson", 240, 900)], threading.Event()

    def stand_in(sport, player):
        made.append(player)
        if len(made) == 2:
            slow.wait(5)                                  # the read behind is slow; the reader must not wait
        return json.dumps({"player": player, "stats": {"Points": [{"value": 22.0}]}, "n": len(made)}).encode()
    server._player_logs_made = stand_in
    server._player_games_stamp = lambda sport, body_or_name: stamp[0]
    server._PLAYER_LOGS.clear()
    sent = []
    try:
        h = _handler(sent)
        q = {"sport": ["nba"], "player": ["Jalen Brunson"]}
        h._players_logs(q)
        h._players_logs(q)
        assert [s[1]["n"] for s in sent] == [1, 1] and len(made) == 1, "kept"
        assert sent[1][2] == [("Server-Timing", "kept;dur=0")]
        key = next(iter(server._PLAYER_LOGS))
        server._PLAYER_LOGS[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._PLAYER_LOGS[key][1:]
        t0 = time.time()
        h._players_logs(q)
        assert sent[-1][1]["n"] == 1 and time.time() - t0 < 1.0, "past its five minutes: at once..."
        assert sent[-1][2] == [("Server-Timing", "stale;dur=0")]
        assert _until(lambda: len(made) == 2), "...and read again behind it"
        slow.set()
        assert _until(lambda: json.loads(server._PLAYER_LOGS[key][1])["n"] == 2)
        server._PLAYER_LOGS[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._PLAYER_LOGS[key][1:]
        stamp[0] = ("Jalen Brunson", 254, 905)            # a box score of the player's since
        h._players_logs(q)
        assert len(made) == 3 and sent[-1][1]["n"] == 3, "a game since: read before it answers"
        h._players_logs({"sport": ["nope"], "player": ["Jalen Brunson"]})
        assert sent[-1][0] == 400 and len(made) == 3, "refused before anything is read"
    finally:
        slow.set()
        server._player_logs_made, server._player_games_stamp = real_made, real_stamp
        server._PLAYER_LOGS.clear()


def test_the_answer_is_the_one_it_was_and_the_kept_stay_under_their_count():
    import server
    from engine import statlogs
    real_for, real_stamp = statlogs.for_player, server._player_games_stamp
    statlogs.for_player = lambda sport, player: {"Points": [{"opponent": "IND", "value": 22.0}]}
    server._player_games_stamp = lambda sport, body_or_name: None
    server._PLAYER_LOGS.clear()
    keep = server.PLAYER_LOGS_KEEP
    try:
        assert json.loads(server._player_logs_made("nba", "Jalen Brunson")) == {
            "player": "Jalen Brunson", "stats": {"Points": [{"opponent": "IND", "value": 22.0}]}}, "the same shape"
        server.PLAYER_LOGS_KEEP = 3
        for i in range(5):
            server._player_logs_keep(("nba", f"p{i}"), "nba", f"P{i}", b"{}")
        assert len(server._PLAYER_LOGS) == 3 and ("nba", "p0") not in server._PLAYER_LOGS, "the oldest out"
    finally:
        server.PLAYER_LOGS_KEEP = keep
        statlogs.for_player, server._player_games_stamp = real_for, real_stamp
        server._PLAYER_LOGS.clear()


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
