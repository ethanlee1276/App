"""A kept answer past its time answers at once and is rebuilt behind it (step AFM, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". The server keeps a player's page five minutes, a
chart fifteen and the sign-up screen's first look one, and the first reader after that waited for a whole build:
Amon-Ra St. Brown's page once took 4.4 s to answer and his role chart 7.5 s, where the kept copies answer in a
fraction of a second, and the first look 2.5 s. Now a kept answer past its time, up to an hour old (the first look's
ten minutes), is sent at once and one build in the background replaces it; older than that, the reader waits for a
fresh one, so nothing shown is hours old. A player's very first page still waits for its build.

Offline. Run directly: `python3 tests/test_a_kept_answer_past_its_time_answers_at_once.py`
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import charts as CH, db as D  # noqa: E402


def _until(check, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


def test_a_chart_past_its_time_answers_now_and_is_rebuilt_behind_it():
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    D.connect(path).close()
    real, built, gate = CH.answer, [], threading.Event()

    def slow(conn, kind, sport, player, season=None, opp="", fam=""):
        built.append(player)
        if len(built) > 1:
            gate.wait(5)                     # the rebuild is slow; the reader must not wait for it
        return {"player": player, "kind": kind, "games": [{"id": len(built)}]}
    CH.forget()
    CH.answer = slow
    keep = CH.ANSWER_TTL
    try:
        first = CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        CH.ANSWER_TTL = -1                   # every kept answer now past its time...
        key = next(iter(CH._KEPT))
        with CH._LOCK:
            CH._KEPT[key] = (time.time() - 1, CH._KEPT[key][1])
        t0 = time.time()
        again = CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        assert again == first and time.time() - t0 < 1.0, "the kept chart, at once"
        assert _until(lambda: len(built) == 2), "and one rebuild behind it"
        assert CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown") == first, "one build at a time"
        assert len(built) == 2
        gate.set()
        assert _until(lambda: not CH._BUILDING)
        CH.ANSWER_TTL = keep
        # The rebuild kept its answer under the TTL of -1 set above, past its time the moment it landed; kept as
        # fresh here, or the next ask starts one more rebuild behind it, which (on a busy machine, gate 830) can
        # land after the hour-old stamp below and answer for it.
        with CH._LOCK:
            CH._KEPT[key] = (time.time() + keep,) + tuple(CH._KEPT[key][1:])
        assert json.loads(CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown"))["games"] == [{"id": 2}], \
            "the rebuilt one replaced it"
        assert not CH._BUILDING and len(built) == 2, "and, kept fresh, starts no other"
        # Older than its window (a chart of his own games, a day: step AGJ), the reader waits for a fresh one.
        assert CH._stale_max(key) == 24 * 60 * 60
        with CH._LOCK:
            CH._KEPT[key] = (time.time() - CH._stale_max(key) - 5, CH._KEPT[key][1])
        CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        assert len(built) == 3 and not CH._BUILDING
    finally:
        CH.ANSWER_TTL = keep
        CH.answer = real
        gate.set()
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_a_rebuild_that_fails_says_so_once_and_the_kept_chart_stands():
    import contextlib
    import io
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    D.connect(path).close()
    real = CH.answer
    calls = []

    def flaky(conn, kind, sport, player, season=None, opp="", fam=""):
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("the box score table is locked")
        return {"player": player, "kind": kind, "games": [{"id": 1}]}
    CH.forget()
    CH.answer = flaky
    CH._BEHIND_SAID[0] = False
    err = io.StringIO()
    try:
        first = CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        key = next(iter(CH._KEPT))
        with contextlib.redirect_stderr(err):
            for _ in range(2):
                with CH._LOCK:
                    CH._KEPT[key] = (time.time() - 1, CH._KEPT[key][1])
                assert CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown") == first, "the kept chart stands"
                assert _until(lambda: not CH._BUILDING)
        said = err.getvalue()
        assert said.count("a chart not rebuilt behind its kept answer") == 1, said
        assert "RuntimeError" in said and "role" in said, said
    finally:
        CH.answer = real
        CH._BEHIND_SAID[0] = False
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def _handler(sent):
    import server
    h = object.__new__(server.Handler)
    h._send = lambda code, body, ext=".json", mtime=None, headers=None: sent.append((code, body, headers or []))
    return h


def test_a_player_page_past_its_time_answers_now_and_is_rebuilt_behind_it():
    import server
    real, built, gate = server._player_page_made, [], threading.Event()

    def made(sport, player, team, season, took=None):
        built.append(player)
        if len(built) > 1:
            gate.wait(5)
        return json.dumps({"player": player, "n": len(built)}).encode()
    keep = dict(server._PLAYER_PAGES)
    server._PLAYER_PAGES.clear()
    server._player_page_made = made
    sent = []
    try:
        q = {"sport": ["nfl"], "player": ["Amon-Ra St. Brown"], "team": ["DET"]}
        h = _handler(sent)
        h._players_page(q)
        assert json.loads(sent[-1][1]) == {"player": "Amon-Ra St. Brown", "n": 1}, "a first page waits for its build"
        key = next(iter(server._PLAYER_PAGES))
        server._PLAYER_PAGES[key] = (time.time() - server.PLAYER_PAGE_TTL - 1, server._PLAYER_PAGES[key][1])
        t0 = time.time()
        h._players_page(q)
        assert time.time() - t0 < 1.0 and json.loads(sent[-1][1])["n"] == 1, "the kept page, at once"
        assert ("Server-Timing", "stale;dur=0") in sent[-1][2]
        assert _until(lambda: len(built) == 2)
        h._players_page(q)
        assert len(built) == 2, "one rebuild at a time"
        gate.set()
        assert _until(lambda: json.loads(server._PLAYER_PAGES[key][1])["n"] == 2)
        h._players_page(q)
        assert json.loads(sent[-1][1])["n"] == 2 and ("Server-Timing", "kept;dur=0") in sent[-1][2]
        server._PLAYER_PAGES[key] = (time.time() - server.PLAYER_PAGE_STALE_MAX - 1, server._PLAYER_PAGES[key][1])
        h._players_page(q)
        assert json.loads(sent[-1][1])["n"] == 3, "older than the hour: built before it answers"
        assert server.PLAYER_PAGE_TTL == 300 and server.PLAYER_PAGE_STALE_MAX == 3600
    finally:
        gate.set()
        server._player_page_made = real
        server._PLAYER_PAGES.clear()
        server._PLAYER_PAGES.update(keep)


def test_a_game_landed_since_means_the_reader_waits_for_the_fresh_one():
    """STEP AFQ: past its time, a kept chart or page answers at once only while the player's games are as they were
    built from; a box score of theirs landed since, and the reader waits for the fresh one."""
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    conn = D.connect(path)
    row = {"sport": "nfl", "season": 2026, "period": "011", "game_id": "DET-011", "player": "Amon-Ra St. Brown",
           "team": "DET", "opponent": "NYG", "position": "WR", "home": 1, "market": "receptions", "value": 8.0}
    D.upsert_player_logs(conn, [row])
    conn.commit()
    conn.close()
    real, built = CH.answer, []

    def fake(conn, kind, sport, player, season=None, opp="", fam=""):
        built.append(player)
        return {"player": player, "kind": kind, "games": [{"id": len(built)}]}
    CH.forget()
    CH.answer = fake
    try:
        first = CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        key = next(iter(CH._KEPT))
        assert CH._KEPT[key][2] == (1, CH._KEPT[key][2][1]), "kept with his games' stamp"
        with CH._LOCK:
            CH._KEPT[key] = (time.time() - 1, *CH._KEPT[key][1:])
        assert CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown") == first, "his games as they were: at once"
        assert _until(lambda: not CH._BUILDING and len(built) == 2)
        conn = D.connect(path)
        D.upsert_player_logs(conn, [dict(row, period="012", game_id="DET-012", opponent="GB", value=11.0)])
        conn.commit()
        conn.close()
        with CH._LOCK:
            CH._KEPT[key] = (time.time() - 1, *CH._KEPT[key][1:])
        fresh = json.loads(CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown"))
        assert fresh["games"] == [{"id": 3}] and len(built) == 3, "a game landed since: built before it answers"
    finally:
        CH.answer = real
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)
    import server
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert ("len(hit) < 3 or hit[2] is None or _player_games_stamp(sport, hit[2][0]) == hit[2]):") in src
    assert "_player_page_keep(key, body, _player_games_stamp(sport, body))" in src
    assert server._player_games_stamp("nfl", b"{}") is None and server._player_games_stamp("ufc", "Jon Jones") is None
    # The page: kept with a stamp; the stamp moved, so the page is built before it answers.
    real_made, real_stamp = server._player_page_made, server._player_games_stamp
    made = []
    server._player_page_made = lambda sport, player, team, season, took=None: (
        made.append(1), json.dumps({"player": player, "n": len(made)}).encode())[1]
    keep = dict(server._PLAYER_PAGES)
    server._PLAYER_PAGES.clear()
    sent = []
    try:
        q = {"sport": ["nfl"], "player": ["Amon-Ra St. Brown"], "team": ["DET"]}
        k = ("nfl", "amon-ra st. brown", "DET", "")
        server._PLAYER_PAGES[k] = (time.time() - server.PLAYER_PAGE_TTL - 1, b'{"player": "Amon-Ra St. Brown", "n": 0}',
                                   ("Amon-Ra St. Brown", 1, 5))
        server._player_games_stamp = lambda sport, x: ("Amon-Ra St. Brown", 2, 9)
        _handler(sent)._players_page(q)
        assert json.loads(sent[-1][1])["n"] == 1 and ("Server-Timing", "stale;dur=0") not in sent[-1][2], sent[-1]
    finally:
        server._player_page_made, server._player_games_stamp = real_made, real_stamp
        server._PLAYER_PAGES.clear()
        server._PLAYER_PAGES.update(keep)


def test_the_first_look_past_its_minute_answers_now():
    import server
    real, built, gate = server._firstlook_build, [], threading.Event()

    def build():
        built.append(1)
        if len(built) > 1:
            gate.wait(5)
        server._FIRSTLOOK.update(at=time.time(), body=json.dumps({"n": len(built)}).encode())
    keep = dict(server._FIRSTLOOK)
    server._FIRSTLOOK.clear()
    server._firstlook_build = build
    sent = []
    try:
        h = _handler(sent)
        h._firstlook()
        assert json.loads(sent[-1][1]) == {"n": 1}
        server._FIRSTLOOK["at"] = time.time() - server.FIRSTLOOK_TTL_S - 1
        t0 = time.time()
        h._firstlook()
        assert time.time() - t0 < 1.0 and json.loads(sent[-1][1]) == {"n": 1}, "the kept one, at once"
        assert _until(lambda: len(built) == 2)
        gate.set()
        assert _until(lambda: json.loads(server._FIRSTLOOK["body"]) == {"n": 2})
        server._FIRSTLOOK["at"] = time.time() - server.FIRSTLOOK_STALE_MAX_S - 1
        h._firstlook()
        assert json.loads(sent[-1][1]) == {"n": 3}, "older than ten minutes: built before it answers"
    finally:
        gate.set()
        server._firstlook_build = real
        server._FIRSTLOOK.clear()
        server._FIRSTLOOK.update(keep)


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
