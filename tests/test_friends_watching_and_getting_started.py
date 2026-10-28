"""Friends watching now, getting started, and the Season ticket
(engine/karma; Ethan, 2026-10-28: "keep building … keep inventing … it
feel complete and like a real app … keep user retainment").

  * FRIENDS WATCHING NOW (Discord's and Xbox's "playing now"): a friend's
    live game shows on the Live tab and in the game's chat while their page
    asked in the last two and a half minutes. Friends only — both sides of
    the friendship — never a follower or a stranger; a friend who turned it
    off is never shown; a game that went final drops off.
  * GETTING STARTED (Duolingo's and Strava's first-week checklists): five
    firsts, +20 each once and +50 for all five, shown an account's first
    two weeks or until done.
  * SEASON TICKET (Real's games-watched-per-sport-per-season badges, as one
    badge): the most live games of one league this season.

Run directly: `python3 tests/test_friends_watching_and_getting_started.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import gamechat as GC                            # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import social as SOC                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"


def _db(n=4):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    SOC.ensure_tables(conn)
    K.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def _friends(conn, a, b, both=True):
    t = time.time()
    conn.execute("INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?,?,?)", (a, b, t))
    if both:
        conn.execute("INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?,?,?)", (b, a, t))
    conn.commit()


def _watching(conn, uid, room, at):
    conn.execute("INSERT INTO karma_watch (user_id, room, league, first_at, last_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(user_id, room) DO UPDATE SET last_at=excluded.last_at",
                 (uid, room, room.split("_")[0], at, at))
    conn.commit()


def _live(state="live"):
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "GB", "away": "CAR", "live": {"state": state}}]}))
    return d


def test_friends_only_and_only_while_they_are_on_it():
    conn, ids = _db()
    me, friend, one_way, stranger = ids
    _friends(conn, me, friend)
    _friends(conn, one_way, me, both=False)                  # they added me; I never answered
    now = time.time()
    for uid in (friend, one_way, stranger):
        _watching(conn, uid, ROOM, now - 30)
    got = K.friends_watching(conn, me, now)
    assert [f["handle"] for f in got] == ["sam"], got
    assert got[0]["room"] == ROOM and got[0]["league"] == "nfl"
    assert K.friends_watching(conn, me, now + K.FRIEND_FRESH_S + 60) == [], "gone two and a half minutes after"
    assert [f["handle"] for f in K.friends_watching(conn, me, now, room=ROOM)] == ["sam"]
    assert K.friends_watching(conn, me, now, room="nfl_1") == []
    keep = K.DATA
    try:
        K.DATA = _live("live")
        got = K.friends_watching(conn, me, now)
        assert got and got[0]["away"] == "CAR" and got[0]["home"] == "GB", got
        K.DATA = _live("final")
        assert K.friends_watching(conn, me, now) == [], "a game that went final drops off"
    finally:
        K.DATA = keep


def test_a_friend_who_hid_it_is_never_shown():
    conn, ids = _db()
    me, friend = ids[:2]
    _friends(conn, me, friend)
    _watching(conn, friend, ROOM, time.time())
    assert K.set_prefs(conn, friend, share=False)[1]["share"] is False
    assert K.friends_watching(conn, me) == []
    K.set_prefs(conn, friend, share=True)
    assert len(K.friends_watching(conn, me)) == 1


def test_the_chat_says_which_friends_are_in_the_room():
    conn, ids = _db()
    me, friend, other = ids[:3]
    _friends(conn, me, friend)
    _watching(conn, friend, ROOM, time.time())
    _watching(conn, other, ROOM, time.time())
    code, v = GC.room_view(conn, ROOM, me)
    assert code == 200 and v["friends"] == ["sam"], v.get("friends")
    code, v = GC.room_view(conn, ROOM, None)
    assert "friends" not in v, "nobody signed in has friends here"
    js = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    assert "CH.friends = Array.isArray(v.friends) ? v.friends : [];" in js and "${chatFriendsHere()}" in js


def test_getting_started_pays_each_first_once_and_goes_when_done():
    conn, ids = _db()
    me = ids[0]
    c = K.camp(conn, me)
    assert c and c["of"] == 5 and [x["key"] for x in c["steps"]] == [k for k, _ in K.CAMP]
    assert c["done"] == 1 and c["steps"][0]["done"], "a username is the first, and this account has one"
    from engine import alerts as AL
    AL.ensure_tables(conn) if hasattr(AL, "ensure_tables") else None
    conn.execute("INSERT INTO alert_watches (user_id, kind, value, created_at) VALUES (?, 'team', 'nfl:GB', ?)",
                 (me, time.time()))
    _watching(conn, me, ROOM, time.time())
    K.award(conn, me, "chat_day", "2026-10-28")
    c = K.camp(conn, me)
    assert c["done"] == 4, c
    from engine import callit as CI
    CI.ensure_tables(conn)
    conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at) VALUES (?, 'mlb_1', 'ab1', 'hit', ?)",
                 (me, time.time()))
    conn.commit()
    assert K.camp(conn, me) is None, "all five: the list goes"
    paid = {k: int(s) for k, s in conn.execute(
        "SELECT kind, SUM(pts) FROM karma_events WHERE user_id=? AND kind IN ('camp','camp_done') GROUP BY kind", (me,))}
    assert paid == {"camp": 100, "camp_done": 50}, paid
    K.camp(conn, me)
    assert conn.execute("SELECT SUM(pts) FROM karma_events WHERE user_id=? AND kind LIKE 'camp%'", (me,)).fetchone()[0] == 150


def test_getting_started_is_for_the_first_two_weeks():
    conn, ids = _db()
    me = ids[0]
    conn.execute("UPDATE users SET created_at=? WHERE id=?", (time.time() - 15 * 86400, me))
    conn.commit()
    assert K.camp(conn, me) is None
    out = K.me(conn, me)
    assert out["camp"] is None and "friends" in out and out["share"] is True


def test_the_season_ticket_counts_one_leagues_games_this_season():
    conn, ids = _db()
    me = ids[0]
    t = K.SEASON_START + 86400
    for i in range(6):
        _watching(conn, me, f"nfl_9{i}", t + i)
    for i in range(3):
        _watching(conn, me, f"nba_8{i}", t + i)
    _watching(conn, me, "nfl_77", K.SEASON_START - 86400)       # last season
    assert K.season_best(conn, me) == ("nfl", 6)
    row = {b["key"]: b for b in K.badges(conn, me)}["season"]
    assert row["n"] == 6 and row["tier"] == 1 and row["next"] == 10, row
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    assert 'season: "🎟️"' in kjs


def test_the_page_draws_the_list_the_friends_and_the_switch():
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    for want in ("function krCampHTML(v)", "function krFriendsHTML(v)", 'data-kr="game"',
                 'krSwitch(v.share !== false, "share"', "${krFriendsHTML(v)}", "${krCampHTML(v)}"):
        assert want in kjs, want
    policy = Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8")
    assert "which live game you have open" in policy


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
