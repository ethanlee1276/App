"""The site's own account posts each game's big moments in its chat.

The ideas list (2026-10-25, "the live game as a place to be", item 2): a
play rated 8 or more drops into the game's chat from the house, so the
whole room reacts to the same thing (engine/housepost). What these hold:

  - only the site's own account posts — verified, a "qellys" name, never
    the founder's profile — and with none, nothing posts;
  - a game's first look is its baseline: plays already on it are marked,
    not posted, so a restart late in a game replays nothing;
  - each big play posts once, on its own thread (keyed as the chat keys a
    play), with the moment's own line; at most PER_GAME a game;
  - a stale file is not a game in progress;
  - the room shows it from the official account, and the chat draws the
    site's mark beside it.

    python3 tests/test_the_house_posts_the_moment.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import gamechat as GC         # noqa: E402
from engine import housepost as HP        # noqa: E402
from engine import socialfeed as SF       # noqa: E402

CHAT = open(os.path.join(ROOT, "web", "js", "chat.js"), encoding="utf-8").read()


def _user(conn, email):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (email, time.time(), time.time()))
    conn.commit()
    return int(cur.lastrowid)


def _house(conn):
    uid = _user(conn, "site@example.com")
    code, out = SF.claim(conn, "site@example.com", "Qellys_Book", name="Qellys Book")
    assert code == 200, out
    return uid


def _play(i, rating, swing=""):
    p = {"id": f"40{i}", "period": 4, "clock": f"{9 - i}:00", "team": "PIT", "event": "Passing Touchdown",
         "players": ["Joe Burrow"], "away_score": 14 + 7 * i, "home_score": 17, "rating": rating}
    if swing:
        p["swing"] = swing
    return p


def _write(d, plays, league="nfl", eid="990123"):
    path = Path(d) / f"{league}_{eid}.json"
    doc = {"league": league, "event_id": eid, "home": "CIN", "away": "PIT", "plays": plays}
    if league == "mlb":
        doc = {"league": "mlb", "event_id": eid, "home": "NYY", "away": "BOS", "events": plays}
    path.write_text(json.dumps(doc))
    return path


def _pass(conn, d, path, bump):
    t = time.time() + bump
    os.utime(path, (t, t))
    return HP.run(conn, Path(d), now=t + 1)


def _msgs(conn, room="nfl_990123"):
    return conn.execute("SELECT user_id, body, play FROM chat_msgs WHERE room=? ORDER BY id", (room,)).fetchall()


def test_only_the_sites_own_account_posts():
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        assert HP.house_id(conn) is None
        founder = _user(conn, "you@example.com")
        SF.claim(conn, "you@example.com", "Qellys_Owner")
        conn.execute("UPDATE feed_profiles SET founder=1 WHERE user_id=?", (founder,))
        conn.commit()
        assert HP.house_id(conn) is None, "never the founder's own profile"
        house = _house(conn)
        assert HP.house_id(conn) == house
        conn.close()


def test_the_first_look_is_a_baseline_then_each_big_play_posts_once():
    HP._mtimes.clear()
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        house = _house(conn)
        path = _write(d, [_play(0, 9.1, "go_ahead"), _play(1, 3.0)])
        assert _pass(conn, d, path, 0) == 0 and not _msgs(conn), "what was on the file at the first look is not posted"
        path = _write(d, [_play(0, 9.1, "go_ahead"), _play(1, 3.0), _play(2, 8.4), _play(3, 7.9)])
        assert _pass(conn, d, path, 5) == 1
        rows = _msgs(conn)
        assert [(r["user_id"], r["play"]) for r in rows] == [(house, "402")], "the 8.4, on its own thread; not the 7.9"
        assert rows[0]["body"].startswith("Big moment: PIT 28–17 CIN. Joe Burrow — Passing Touchdown, Q4, 7:00.")
        assert "Rated 8.4." in rows[0]["body"]
        assert _pass(conn, d, path, 10) == 0 and len(_msgs(conn)) == 1, "once"
        conn.close()


def test_no_account_marks_but_never_posts_and_never_catches_up():
    HP._mtimes.clear()
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        path = _write(d, [_play(0, 2.0)])
        _pass(conn, d, path, 0)
        path = _write(d, [_play(0, 2.0), _play(1, 9.0)])
        assert _pass(conn, d, path, 5) == 0 and not _msgs(conn)
        _house(conn)
        path = _write(d, [_play(0, 2.0), _play(1, 9.0), _play(2, 9.5, "walkoff")])
        assert _pass(conn, d, path, 10) == 1
        assert [r["play"] for r in _msgs(conn)] == ["402"], "the 9.0 seen before the account existed stays unsaid"
        conn.close()


def test_at_most_per_game():
    HP._mtimes.clear()
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        _house(conn)
        path = _write(d, [_play(0, 1.0)])
        _pass(conn, d, path, 0)
        path = _write(d, [_play(i, 9.0) for i in range(HP.PER_GAME + 3)])
        assert _pass(conn, d, path, 5) == HP.PER_GAME
        conn.close()


def test_baseball_keys_an_at_bat_the_way_the_chat_does_and_a_stale_file_is_skipped():
    HP._mtimes.clear()
    ab = lambda n, r, s="": dict({"kind": "atbat", "at_bat": n, "inning": 9, "half": "B", "batter": "Aaron Judge",  # noqa: E731
                                  "event": "Home Run", "away_score": 3, "home_score": 4, "rating": r},
                                 **({"swing": s} if s else {}))
    assert [k for k, _ in HP.big_plays({"league": "mlb", "events": [ab(61, 9.8, "walkoff"), ab(60, 2.0)]})] == ["ab61"]
    assert HP.big_plays({"league": "nfl", "plays": [{"rating": 9.0}]}) == [], "no id, no thread to post on"
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        _house(conn)
        path = _write(d, [_play(0, 1.0)])
        old = time.time() - HP.FRESH_S - 60
        os.utime(path, (old, old))
        HP.run(conn, Path(d), now=time.time())
        assert conn.execute("SELECT COUNT(*) FROM chat_house_seen").fetchone()[0] == 0, "a stale file is not a game on"
        conn.close()


def test_the_room_shows_it_from_the_official_account_and_the_chat_draws_the_mark():
    HP._mtimes.clear()
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        _house(conn)
        path = _write(d, [_play(0, 1.0)])
        _pass(conn, d, path, 0)
        path = _write(d, [_play(0, 1.0), _play(1, 9.0)])
        _pass(conn, d, path, 5)
        code, out = GC.room_view(conn, "nfl_990123", None)
        assert code == 200
        m = out["messages"][-1]
        assert m["play"] == "401" and m["by"]["official"] and m["by"]["handle"] == "Qellys_Book"
        conn.close()
    assert '${p.official ? " house" : ""}' in CHAT and "p.official ? `<span class=\"gch-av gch-house\" aria-hidden=\"true\">${brandMarkHTML(24)}</span>`" in CHAT


def test_the_minute_loop_runs_it():
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = launch[launch.index("def _slip_watcher()"):]
    body = body[:body.index("\n\n\n")]
    assert "_hp.run_once()" in body and body.index("_pm.run_once(") < body.index("_hp.run_once()")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
