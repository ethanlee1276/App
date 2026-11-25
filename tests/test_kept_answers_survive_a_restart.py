"""Kept answers survive a restart (step AHJ, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". A player's page, game log and market logs and a team's page were kept in memory only, and every
update restarts the server, so the first visit to each after one waited for a whole build (on the live site a hockey
page's rows 3.4 s, a college page's roster 3.1 s, a team page 1.5 to 4.7 s). Each kept answer is also written to disk
on the live server; with none in memory, one on disk, built by the same code and younger than the hour, answers as the
kept one would.

Offline. Run directly: `python3 tests/test_kept_answers_survive_a_restart.py`
"""
import json
import os
import sys
import tempfile
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


class _Disk:
    """The live server's disk keep, in a folder of the test's own."""

    def __enter__(self):
        import server
        self.s = server
        self.was = (server.KEPT_ON_DISK, server.KEPT_DIR, server._player_page_made, server._player_games_stamp,
                    dict(server._KEPT_CODES))
        server.KEPT_ON_DISK, server.KEPT_DIR = True, Path(tempfile.mkdtemp()) / "kept"
        server._PLAYER_PAGES.clear()
        return self

    def __exit__(self, *exc):
        s = self.s
        s.KEPT_ON_DISK, s.KEPT_DIR, s._player_page_made, s._player_games_stamp, codes = self.was
        s._KEPT_CODES.clear()
        s._KEPT_CODES.update(codes)
        s._PLAYER_PAGES.clear()


def test_a_page_kept_before_a_restart_answers_after_it_without_a_build():
    with _Disk() as d:
        s, made, stamp = d.s, [], [("Connor McDavid", 900, 12345)]

        def stand_in(sport, player, team, season, took=None):
            made.append(player)
            return json.dumps({"player": "Connor McDavid", "n": len(made)}).encode()
        s._player_page_made = stand_in
        s._player_games_stamp = lambda sport, body_or_name: stamp[0]
        sent = []
        h = _handler(sent)
        q = {"sport": ["nhl"], "player": ["Connor McDavid"]}
        h._players_page(q)
        assert len(made) == 1 and list(s.KEPT_DIR.glob("player/*.gz")), "built, kept, and written to disk"
        s._PLAYER_PAGES.clear()                                       # the restart
        h._players_page(q)
        assert len(made) == 1 and sent[-1][1]["n"] == 1, "answered off disk, no build"
        assert sent[-1][2] == [("Server-Timing", "kept;dur=0")]
        key = next(iter(s._PLAYER_PAGES))
        entry = s._PLAYER_PAGES[key]
        s._kept_save("player", key, (time.time() - s.PLAYER_PAGE_TTL - 5,) + entry[1:])
        s._PLAYER_PAGES.clear()
        h._players_page(q)
        assert sent[-1][2] == [("Server-Timing", "stale;dur=0")] and sent[-1][1]["n"] == 1, "past five minutes: at once"
        assert _until(lambda: json.loads(s._PLAYER_PAGES[key][1])["n"] == 2), "...and built again behind it"
        assert _until(lambda: json.loads(s._kept_load("player", key, {})[1])["n"] == 2), "and written again"
        entry = s._PLAYER_PAGES[key]
        s._kept_save("player", key, (time.time() - s.PLAYER_PAGE_TTL - 5,) + entry[1:])
        s._PLAYER_PAGES.clear()
        stamp[0] = ("Connor McDavid", 901, 12399)                    # a box score of his since
        h._players_page(q)
        assert len(made) == 3 and sent[-1][1]["n"] == 3, "his games moved: built before it answers"


def test_a_copy_from_other_code_or_past_the_hour_is_never_served_and_is_pruned():
    with _Disk() as d:
        s = d.s
        key = ("nba", "jalen brunson", "", "")
        s._kept_save("player", key, (time.time(), b'{"player":"Jalen Brunson"}', ("Jalen Brunson", 1, 2)))
        assert s._kept_load("player", key, {})[1] == b'{"player":"Jalen Brunson"}'
        s._KEPT_CODES["player"] = "another-code"
        assert s._kept_load("player", key, {}) is None, "built by other code: not served"
        s._KEPT_CODES.clear()
        s._kept_save("player", key, (time.time() - s.PLAYER_PAGE_STALE_MAX - 5, b'{"x":1}', None))
        assert s._kept_load("player", key, {}) is None, "past the hour: not served"
        path = s._kept_path("player", key)
        os.utime(path, (time.time() - s.PLAYER_PAGE_STALE_MAX - 60,) * 2)
        assert s._kept_prune() == 1 and not path.exists(), "and taken off disk"
        assert s._kept_load("team", ("nhl", "edm", ""), {}) is None, "nothing on disk: none"


def test_only_the_live_server_writes_them_and_every_kept_answer_does():
    import server
    assert server.KEPT_ON_DISK is False, "tests and sample mode keep nothing on disk"
    folder = Path(tempfile.mkdtemp()) / "kept"
    was = server.KEPT_DIR
    try:
        server.KEPT_DIR = folder
        server._kept_save("player", ("nfl", "x", "", ""), (time.time(), b"{}", None))
        assert not folder.exists()
    finally:
        server.KEPT_DIR = was
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    for kind, store in (("player", "_PLAYER_PAGES"), ("gamelog", "_GAMELOGS"), ("logs", "_PLAYER_LOGS"),
                        ("team", "_TEAM_PAGES")):
        assert f'_kept_save("{kind}", key, entry)' in src, kind
        assert f'hit = {store}.get(key) or _kept_load("{kind}", key, {store})' in src, kind
    main = src[src.index("def main() -> None:"):]
    assert "KEPT_ON_DISK = live" in main[:600]


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
