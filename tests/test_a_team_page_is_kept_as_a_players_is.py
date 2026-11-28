"""A team's page is kept as a player's page is (step AHA, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". A team's page (/api/team) was built again
on every visit: on the live site 0.5 s of the server's own time asked twice in a row (the Knicks, the Oilers), 1.3 s
for the Yankees, and 2.3 to 3.8 s the first time, in the one process every other page waits behind. It is kept now as
a player's page and game log are: five minutes; past that, up to the hour while the team has played no game since it
was built, answered at once and built again behind it; a game since, and it is built before it answers. One season's
schedule (the Schedule tab's chips) and an answer that is not one team's page (a name two teams share) are not kept.

Offline. Run directly: `python3 tests/test_a_team_page_is_kept_as_a_players_is.py`
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


def test_a_team_page_is_kept_read_behind_and_built_again_for_a_game_since():
    import server
    real_made, real_stamp = server._team_made, server._team_games_stamp
    made, stamp, slow = [], [(40, 900)], threading.Event()

    def stand_in(sport, name, opp="", only="", season=None):
        made.append((name, only))
        if len(made) == 2:
            slow.wait(5)                                  # the build behind is slow; the reader must not wait
        return 200, json.dumps({"team": "NYK", "n": len(made)}).encode(), [("Server-Timing", "profile;dur=300")], "NYK"
    server._team_made = stand_in
    server._team_games_stamp = lambda sport, team: stamp[0]
    server._TEAM_PAGES.clear()
    sent = []
    try:
        h = _handler(sent)
        q = {"sport": ["nba"], "team": ["NYK"]}
        h._team(q)
        h._team(q)
        assert [s[1]["n"] for s in sent] == [1, 1] and len(made) == 1, "kept"
        assert sent[0][2] == [("Server-Timing", "profile;dur=300")], "a build says where its time went, as before"
        assert sent[1][2] == [("Server-Timing", "kept;dur=0")]
        h._team({"sport": ["nba"], "team": ["nyk "]})
        assert len(made) == 1, "the same address, as asked"
        key = next(iter(server._TEAM_PAGES))
        server._TEAM_PAGES[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._TEAM_PAGES[key][1:]
        t0 = time.time()
        h._team(q)
        assert sent[-1][1]["n"] == 1 and time.time() - t0 < 1.0, "past its five minutes: at once..."
        assert sent[-1][2] == [("Server-Timing", "stale;dur=0")]
        assert _until(lambda: len(made) == 2), "...and built again behind it"
        slow.set()
        assert _until(lambda: json.loads(server._TEAM_PAGES[key][1])["n"] == 2)
        server._TEAM_PAGES[key] = (time.time() - server.PLAYER_PAGE_TTL - 5,) + server._TEAM_PAGES[key][1:]
        stamp[0] = (41, 905)                              # a final of the team's since
        h._team(q)
        assert len(made) == 3 and sent[-1][1]["n"] == 3, "a game since: built before it answers"
        server._TEAM_PAGES[key] = (time.time() - server.PLAYER_PAGE_STALE_MAX - 5,) + server._TEAM_PAGES[key][1:]
        h._team(q)
        assert len(made) == 4 and sent[-1][1]["n"] == 4, "past the hour: built before it answers"
        n = len(made)
        h._team({"sport": ["nba"], "team": ["NYK"], "only": ["schedule"], "season": ["2025"]})
        h._team({"sport": ["nba"], "team": ["NYK"], "only": ["schedule"], "season": ["2025"]})
        assert len(made) == n + 2 and made[-1] == ("NYK", "schedule"), "one season's schedule is never kept"
        h._team({"sport": ["nope1"], "team": ["NYK"]})
        assert sent[-1][0] == 400 and len(made) == n + 2, "refused before anything is built"
    finally:
        slow.set()
        server._team_made, server._team_games_stamp = real_made, real_stamp
        server._TEAM_PAGES.clear()


def test_an_answer_that_is_not_one_teams_page_is_not_kept():
    import server
    real = server._team_made
    made = []

    def stand_in(sport, name, opp="", only="", season=None):
        made.append(name)
        return 200, json.dumps({"sport": sport, "query": name, "resolved": [{"team": "LAR"}, {"team": "LAC"}]}
                               ).encode(), None, None
    server._team_made = stand_in
    server._TEAM_PAGES.clear()
    sent = []
    try:
        h = _handler(sent)
        h._team({"sport": ["nfl"], "team": ["Los Angeles"]})
        h._team({"sport": ["nfl"], "team": ["Los Angeles"]})
        assert len(made) == 2 and not server._TEAM_PAGES, "a name two teams share asks the reader, every time"
    finally:
        server._team_made = real
        server._TEAM_PAGES.clear()


def test_the_kept_pages_stay_under_their_count_and_a_build_is_the_one_it_was():
    import server
    real = server._team_games_stamp
    server._team_games_stamp = lambda sport, team: None
    server._TEAM_PAGES.clear()
    keep = server.TEAM_KEEP
    try:
        server.TEAM_KEEP = 3
        for i in range(5):
            server._team_keep(("nba", f"t{i}", ""), b"{}", "nba", f"T{i}")
        assert len(server._TEAM_PAGES) == 3 and ("nba", "t0", "") not in server._TEAM_PAGES, "the oldest out"
    finally:
        server.TEAM_KEEP = keep
        server._team_games_stamp = real
        server._TEAM_PAGES.clear()
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    made = src[src.index("def _team_made("):src.index("\ndef _player_page_whole(")]
    for part in ("profile", "opponents", "squad", "stats", "schedule", "roster", "depth"):
        assert f'timed("{part}"' in made, part
    assert 'return 200, json.dumps(out).encode(), ([("Server-Timing", timing)] if timing else None), team' in made
    assert "team history unavailable" in made, "a failure answers 503, as it did"


def test_the_games_stamp_moves_with_a_final():
    import server
    from engine import db as D
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                 "VALUES ('nba', 2026, '2026-11-20', 'g1', 'NYK', 'BOS', 110, 104)")
    conn.commit()
    real = D.DEFAULT_DB
    try:
        D.DEFAULT_DB = Path(path)
        a = server._team_games_stamp("nba", "NYK")
        assert a[0] == 1 and server._team_games_stamp("nba", "BOS")[0] == 1
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('nba', 2026, '2026-11-22', 'g2', 'IND', 'NYK', 100, 113)")
        conn.commit()
        assert server._team_games_stamp("nba", "NYK") != a, "a final of the team's moves it"
        assert server._team_games_stamp("nba", "") is None
    finally:
        D.DEFAULT_DB = real
        conn.close()


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
