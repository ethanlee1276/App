"""Karma, round four: the game chat's @mentions in Activity, the friends
ladder, Monday's recap and pinned badges (engine/gamechat, engine/karma,
engine/socialfeed; Ethan, 2026-10-28: "keep building … keep inventing …
we want to keep user retainment").

  * @MENTIONS (Discord's and Slack's, and Social's own): a game chat
    message that names a reader lands in their Activity with the words and
    the game to open; in a watch party, anyone it names, member or not,
    the link opening the party (Ethan, 2026-10-28: "@ any profile in a chat
    should notify them they were mentioned"). Never the writer, never past
    a block, three names a message at most; a message hidden or deleted
    takes its notices back.
  * THE FRIENDS LADDER (Duolingo's friends league): this week's karma among
    the viewer and their friends (both sides of the friendship), never a
    one-way follow or a stranger, never a friend who took themselves off
    the ladders; signed in only.
  * MONDAY'S RECAP (Duolingo's and Strava's weekly recap): whoever is not
    told a top-ten place hears their week in a line, once, if they had one.
  * PINNED BADGES (Steam's and Xbox's showcase): up to three earned badges
    lead the profile.

Run directly: `python3 tests/test_mentions_friends_ladder_and_pins.py`
"""
import datetime as _dt
import os
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import gamechat as GC                            # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import pushalerts as PA                          # noqa: E402
from engine import pushmine as PM                            # noqa: E402
from engine import social as SOC                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"
ET = ZoneInfo("America/New_York")
FCM = "https://fcm.googleapis.com/fcm/send/"
# Wednesday 28 October 2026, noon, Eastern: the week began Monday the 26th.
NOON = _dt.datetime(2026, 10, 28, 12, 0, tzinfo=ET).timestamp()


def _db(n=5):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    SOC.ensure_tables(conn)
    K.ensure_tables(conn)
    PM.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew", "jordan")[:n]:
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


def _notes(conn, uid, kind="chat_mention"):
    return [n for n in SF.notifications(conn, uid)["items"] if n["kind"] == kind]


def test_a_chat_mention_lands_in_activity_with_its_game():
    conn, ids = _db()
    me, sam, casey, drew, jordan = ids
    t = time.time()
    code, out = GC.send(conn, me, ROOM, "what a catch @sam, @casey @ethan @nobody_here @sam", now=t)
    assert code == 200, out
    got = _notes(conn, sam)
    assert len(got) == 1, got
    n = got[0]
    assert n["handle"] == "ethan" and n["link"] == "#pbp/nfl/401873017", n
    assert n["snippet"].startswith("what a catch @sam"), n
    assert len(_notes(conn, casey)) == 1
    assert _notes(conn, me) == [], "never the writer"
    assert SF.unseen(conn, sam) == 1
    # Three names a message at most.
    GC.send(conn, me, ROOM, "@drew @casey @sam @jordan", now=t + 60)
    assert len(_notes(conn, drew)) == 1 and _notes(conn, jordan) == [], "the fourth name is not told"
    # A block in either direction stops it.
    SF.toggle_block(conn, jordan, "ethan")
    GC.send(conn, me, ROOM, "@jordan you there", now=t + 120)
    assert _notes(conn, jordan) == []
    # Nobody named: nothing at all.
    before = conn.execute("SELECT COUNT(*) FROM feed_notifs").fetchone()[0]
    GC.send(conn, me, ROOM, "no names here", now=t + 180)
    assert conn.execute("SELECT COUNT(*) FROM feed_notifs").fetchone()[0] == before


def test_a_hidden_or_deleted_message_takes_its_mentions_back():
    conn, ids = _db()
    me, sam, casey = ids[:3]
    t = time.time()
    _, one = GC.send(conn, me, ROOM, "@sam look", now=t)
    _, two = GC.send(conn, me, ROOM, "@casey look", now=t + 60)
    assert len(_notes(conn, sam)) == 1 and len(_notes(conn, casey)) == 1
    GC.set_hidden(conn, one["id"], True)
    assert _notes(conn, sam) == [], "hidden for everyone: gone from Activity"
    assert GC.delete(conn, me, two["id"])[0] == 200
    assert _notes(conn, casey) == [], "deleted: gone from Activity"


def test_a_watch_partys_mention_reaches_anyone_named_and_the_link_opens_the_party():
    conn, ids = _db()
    me, sam, casey = ids[:3]
    code, party = GC.party_create(conn, me, ROOM, "Sunday crew")
    assert code == 200, party
    assert GC.party_join(conn, sam, party["token"])[0] == 200
    code, out = GC.send(conn, me, ROOM, "@sam @casey party time", now=time.time(), party=party["id"])
    assert code == 200, out
    for uid in (sam, casey):
        got = _notes(conn, uid)
        assert len(got) == 1 and got[0]["link"] == f"#pbp/nfl/401873017/party/{party['token']}", (uid, got)
    assert GC.party_join(conn, casey, party["token"])[0] == 200, "named, and the link lets them in"
    drew = ids[3]
    SF.toggle_block(conn, drew, "ethan")
    GC.send(conn, me, ROOM, "@drew too", now=time.time(), party=party["id"])
    assert _notes(conn, drew) == [], "a block still stops it"
    js = Path(ROOT, "web", "js", "social.js").read_text(encoding="utf-8")
    assert 'chat_mention: "mentioned you in a game chat"' in js
    assert r"/^#pbp\/[a-z]+\/\d+(\/party\/[A-Za-z0-9_-]{8,40})?$/.test(n.link" in js


def test_the_friends_ladder_is_this_weeks_karma_among_friends():
    conn, ids = _db(4)
    me, sam, casey, drew = ids
    _friends(conn, me, sam)
    _friends(conn, casey, me, both=False)                     # they added me; I never answered
    K.award(conn, me, "watch_join", "r1", pts=10, now=NOON)
    K.award(conn, sam, "watch_join", "r1", pts=30, now=NOON)
    K.award(conn, sam, "trophy", "2026-10-19", pts=100, now=NOON)   # last week's, paid this week
    K.award(conn, sam, "watch_join", "old", pts=500, now=NOON - 7 * 86400)
    K.award(conn, casey, "watch_join", "r1", pts=50, now=NOON)
    K.award(conn, drew, "watch_join", "r1", pts=100, now=NOON)
    lad = K.ladder(conn, "friends", me, now=NOON)
    assert lad["scope"] == "friends" and lad["friends"] == 1, lad
    assert [(r["handle"], r["points"], r["me"]) for r in lad["rows"]] == [("sam", 30, False), ("ethan", 10, True)], lad
    assert lad["mine"] == {"rank": 2, "points": 10}, lad["mine"]
    # A friend off the ladders is off this one too; the viewer never is.
    K.set_prefs(conn, sam, ladder=False)
    K.set_prefs(conn, me, ladder=False)
    lad = K.ladder(conn, "friends", me, now=NOON)
    assert [r["handle"] for r in lad["rows"]] == ["ethan"] and lad["friends"] == 1, lad
    assert K.ladder(conn, "friends", None, now=NOON)["rows"] == [], "signed out: no circle"
    alone = K.ladder(conn, "friends", drew, now=NOON)
    assert alone["friends"] == 0 and [r["handle"] for r in alone["rows"]] == ["drew"]
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert 'if scope == "friends" and not who:' in srv
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    assert '["friends", "Friends"]' in kjs and 'lad.scope === "friends" && !lad.friends' in kjs


def _phone(conn, uid):
    code, out = PA.subscribe(conn, FCM + str(uid), kind="web", user_id=uid, topics=["bets"])
    assert code == 200, out


def _queued(conn, uid):
    return [(r[0], r[1]) for r in conn.execute("SELECT id, title FROM push_mine WHERE user_id=? ORDER BY at", (uid,))]


def test_monday_tells_everyone_else_their_week_in_a_line_once():
    conn, ids = _db(4)
    top, quiet, idle = ids[0], ids[2], ids[3]
    for uid in (top, quiet, idle):
        _phone(conn, uid)
        K.set_prefs(conn, uid, remind=True)
    K.set_prefs(conn, quiet, ladder=False)                    # off the ladders: never ranked
    monday = _dt.datetime(2026, 11, 2, 10, 0, tzinfo=ET).timestamp()
    tue, thu = monday - 6 * 86400, monday - 4 * 86400
    K.award(conn, top, "watch_join", "r1", pts=20, now=thu)
    K.award(conn, quiet, "watch_join", "r1", pts=10, now=tue)
    K.award(conn, quiet, "watch_join", "r2", pts=10, now=thu)
    K.alerts_pass(conn, now=monday)
    assert ("karma:trophy:2026-10-26", "#1 on last week's karma ladder") in _queued(conn, top)
    assert not any(i.startswith("karma:week:") for i, _ in _queued(conn, top)), "the place says it already"
    assert _queued(conn, quiet) == [("karma:week:2026-10-26", "Your week: +20 karma")], _queued(conn, quiet)
    body, url = conn.execute("SELECT body, url FROM push_mine WHERE user_id=?", (quiet,)).fetchone()
    assert body.startswith("2 days on Qellys, level 1 now.") and url == "/#account", body
    assert _queued(conn, idle) == [], "no karma last week: nothing to say"
    K.alerts_pass(conn, now=monday + 1800)
    assert len(_queued(conn, quiet)) == 1, "once"


def test_pinned_badges_lead_the_profile():
    conn, ids = _db(2)
    me = ids[0]
    now = time.time()
    for room in ("nfl_1", "nba_2"):
        conn.execute("INSERT INTO karma_watch (user_id, room, league, first_at, last_at) VALUES (?,?,?,?,?)",
                     (me, room, room.split("_")[0], now, now))
    conn.commit()
    K.award(conn, me, "recruit", "friend:1", now=now)
    earned = {b["key"] for b in K.badges(conn, me) if b["tier"]}
    assert {"founding", "live", "sports", "recruiter"} <= earned, earned
    assert K.set_prefs(conn, me, pins=["founding", "live", "sports", "recruiter"])[0] == 400, "three at most"
    assert K.set_prefs(conn, me, pins=["caller"])[0] == 400, "only a badge you have earned"
    code, out = K.set_prefs(conn, me, pins=["zzz", "recruiter", "recruiter", "live"])
    assert code == 200 and out["pins"] == ["recruiter", "live"], out
    mine = K.me(conn, me)
    assert mine["pins"] == ["recruiter", "live"] and mine["pins_max"] == K.PINS_MAX == 3
    shown = [b["key"] for b in K.public(conn, me)["badges"]]
    assert shown[:2] == ["recruiter", "live"] and set(shown) == earned, shown
    rows = K.badges(conn, me)
    assert [b["key"] for b in K.top_badges(rows, pins=["sports"])][0] == "sports"
    assert [b["key"] for b in K.top_badges(rows, pins=["caller"])][0] != "caller", "an unearned pin is never shown"
    assert K.set_prefs(conn, me, pins=[])[1]["pins"] == []
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    assert 'data-kr="pin"' in kjs and "krPrefs({ pins }, root)" in kjs


def test_the_policy_names_pins_the_friends_ladder_and_chat_mentions():
    policy = Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8")
    for want in ("up to three badges you pin", "friends' ladder", "game chat message that names you",
                 "week's karma in a line"):
        assert want in policy, want


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
