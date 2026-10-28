"""Karma, round two: the alerts that bring people back, and the levels on
Social (engine/karma, engine/pushmine, engine/socialfeed).

Ethan, 2026-10-28, after karma shipped: "keep building … keep inventing …
we want to keep user retainment". The two first: the evening reminder
before the days in a row would end (Duolingo's strongest habit), and the
level beside every name on Social, not just in the game chats.

What this file pins:

  * the switch is the account's (the Karma tab), and a phone signed in to it
    carries the karma topic whatever the Alerts page sent; signed out, never;
  * at about eight in the evening, Eastern: a run of two days or more that
    has nothing yet today and no rest day in hand is told once, that day;
    nothing outside the window, for a run already kept today, with a rest
    day in hand, for a run of one, or to an account that did not ask;
  * on a Monday, last week's top ten hear their place, once;
  * a new tier, once, from the level the switch was turned on at;
  * quiet hours hold karma alerts like the watches;
  * Social's posts and comments carry the writer's level and flair, and the
    page draws them beside the name.

Run directly: `python3 tests/test_karma_alerts_and_the_feed.py`
"""
import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import pushalerts as PA                          # noqa: E402
from engine import pushmine as PM                            # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ET = ZoneInfo("America/New_York")
FCM = "https://fcm.googleapis.com/fcm/send/"


def _at(y, mo, d, h, mi=0):
    return _dt.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp()


# Wednesday 28 October 2026, eight in the evening, Eastern.
EVENING = _at(2026, 10, 28, 20, 5)


def _db(n=3):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    K.ensure_tables(conn)
    PM.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], who, "")
    return conn, ids


def _phone(conn, uid, topics=("bets",), name="a"):
    code, out = PA.subscribe(conn, FCM + name, kind="web", user_id=uid, topics=list(topics))
    assert code == 200, out
    return out["topics"]


def _days(conn, uid, n, last_day_offset=1, now=EVENING):
    """Karma on ``n`` days in a row ending ``last_day_offset`` days before now."""
    for k in range(n):
        t = now - (last_day_offset + k) * 86400
        K.award(conn, uid, "day", K.day_of(t), now=t)


def _queued(conn, uid):
    return [(r[0], r[1]) for r in conn.execute("SELECT id, title FROM push_mine WHERE user_id=? ORDER BY at", (uid,))]


def test_the_switch_is_the_accounts_and_its_phones_carry_it():
    conn, ids = _db()
    me = ids[0]
    assert "karma" not in _phone(conn, me, ("bets",))
    code, out = K.set_prefs(conn, me, remind=True)
    assert code == 200 and out["remind"] is True and out["phones"] == 1, out
    topics = conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (me,)).fetchone()[0]
    assert topics.split(",") == ["bets", "karma"], topics
    # The Alerts page re-subscribes without knowing about karma: it stays.
    assert _phone(conn, me, ("bets", "clutch")) == ["bets", "clutch", "karma"]
    # Signed out, a phone never carries an account's alerts.
    code, out = PA.subscribe(conn, FCM + "a", kind="web", user_id=None, topics=["posted", "karma"])
    assert code == 200 and "karma" not in out["topics"], out
    K.set_prefs(conn, ids[1], remind=True)
    assert K.set_prefs(conn, ids[1], remind=True)[1]["phones"] == 0, "no phone yet: the page says to turn alerts on"
    _phone(conn, me, ("bets",))
    K.set_prefs(conn, me, remind=False)
    assert conn.execute("SELECT topics FROM push_subs WHERE user_id=?", (me,)).fetchone()[0] == "bets"
    assert K.me(conn, me, now=EVENING)["remind"] is False


def test_the_evening_nudge_comes_once_for_a_run_that_would_end_tonight():
    conn, ids = _db()
    me = ids[0]
    _phone(conn, me)
    K.set_prefs(conn, me, remind=True)
    _days(conn, me, 3)
    assert K.alerts_pass(conn, now=_at(2026, 10, 28, 18, 0)) == 0, "not before half past seven"
    assert K.alerts_pass(conn, now=EVENING) == 1
    q = _queued(conn, me)
    assert q == [("karma:streak:2026-10-28", "Your 3-day streak ends at midnight")], q
    body = conn.execute("SELECT body, url, kind FROM push_mine WHERE user_id=?", (me,)).fetchone()
    assert body[1] == "/#live" and body[2] == "karma" and "keep it going" in body[0], body
    assert K.alerts_pass(conn, now=EVENING + 1800) == 0, "once a day"
    assert K.alerts_pass(conn, now=_at(2026, 10, 28, 22, 45)) == 0


def test_no_nudge_when_there_is_nothing_to_lose():
    for case in ("kept today", "rest in hand", "one day", "did not ask", "no phone topic"):
        conn, ids = _db()
        me = ids[0]
        _phone(conn, me)
        if case != "did not ask":
            K.set_prefs(conn, me, remind=True)
        if case == "no phone topic":
            conn.execute("UPDATE push_subs SET topics='bets' WHERE user_id=?", (me,))
        if case == "rest in hand":
            _days(conn, me, 8)
        elif case == "one day":
            _days(conn, me, 1)
        else:
            _days(conn, me, 3)
        if case == "kept today":
            K.award(conn, me, "day", K.day_of(EVENING), now=EVENING - 600)
        assert K.alerts_pass(conn, now=EVENING) == 0, case
        assert _queued(conn, me) == [], case


def test_a_bonus_close_by_is_named():
    conn, ids = _db()
    me = ids[0]
    _phone(conn, me)
    K.set_prefs(conn, me, remind=True)
    _days(conn, me, 6)
    K.alerts_pass(conn, now=EVENING)
    body = conn.execute("SELECT body FROM push_mine WHERE user_id=?", (me,)).fetchone()[0]
    assert "1 more for the 7-day bonus." in body, body


def test_monday_tells_the_weeks_top_ten_their_place_once():
    conn, ids = _db()
    a, b, c = ids
    for uid in (a, b):
        _phone(conn, uid, name=str(uid))
        K.set_prefs(conn, uid, remind=True)
    monday = _at(2026, 11, 2, 10, 0)
    last_week = monday - 4 * 86400
    K.award(conn, a, "watch_join", "r1", pts=10, now=last_week)
    K.award(conn, a, "watch_join", "r2", pts=10, now=last_week + 1)
    K.award(conn, b, "watch_join", "r1", pts=10, now=last_week + 2)
    assert K.alerts_pass(conn, now=_at(2026, 11, 2, 8, 0)) == 0, "quiet until nine"
    K.alerts_pass(conn, now=monday)
    assert ("karma:trophy:2026-10-26", "#1 on last week's karma ladder") in _queued(conn, a)
    assert ("karma:trophy:2026-10-26", "#2 on last week's karma ladder") in _queued(conn, b)
    assert conn.execute("SELECT pts FROM karma_events WHERE user_id=? AND kind='trophy'", (a,)).fetchone()[0] == 100
    n = len(_queued(conn, a))
    K.alerts_pass(conn, now=monday + 1800)
    assert len(_queued(conn, a)) == n, "once"


def test_a_new_tier_is_told_once_from_the_level_the_switch_was_turned_on_at():
    conn, ids = _db()
    me = ids[0]
    _phone(conn, me)
    K.award(conn, me, "recruit", "x", pts=300, now=EVENING - 999)        # level 3
    K.set_prefs(conn, me, remind=True)
    noon = _at(2026, 10, 29, 12, 0)
    assert K.alerts_pass(conn, now=noon) == 0, "level 3 was already reached"
    K.award(conn, me, "recruit", "y", pts=500, now=noon)                  # 800: level 5, Starter
    K.alerts_pass(conn, now=noon + 60)
    assert ("karma:tier:5", "Level 5: you're Starter now") in _queued(conn, me), _queued(conn, me)
    K.award(conn, me, "recruit", "z", pts=200, now=noon + 120)            # level 6: same tier
    assert K.alerts_pass(conn, now=noon + 180) == 0
    K.award(conn, me, "recruit", "w", pts=2000, now=_at(2026, 10, 30, 2, 0))   # level 10 in the night
    assert K.alerts_pass(conn, now=_at(2026, 10, 30, 2, 5)) == 0, "quiet hours"
    K.alerts_pass(conn, now=_at(2026, 10, 30, 9, 30))
    assert ("karma:tier:10", "Level 10: you're Pro now") in _queued(conn, me)


def test_quiet_hours_hold_karma_alerts_and_the_minute_runs_the_pass():
    conn, ids = _db()
    me = ids[0]
    _phone(conn, me)
    K.set_prefs(conn, me, remind=True)
    PM.tell(conn, me, "karma:x", "karma", "t", "b", "/#live", now=EVENING)
    sent = []
    stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, now=EVENING + 60, quiet=True)
    assert stats["messages"] == 0 and not sent, stats
    stats = PM.flush(conn, knock=lambda *a, **k: sent.append(a) or 201, vapid={"x": 1}, now=EVENING + 120, quiet=False)
    assert stats["messages"] == 1 and sent, stats
    src = Path(ROOT, "engine", "pushmine.py").read_text(encoding="utf-8")
    run = src[src.index("def run_once("):src.index("def main(")]
    assert "_karma.alerts_pass(conn, now=t)" in run and 'if t - _looked["karma"] >= KARMA_EVERY_S:' in run
    assert "karma" in PA.PERSONAL


def test_socials_posts_and_comments_carry_the_writers_level_and_flair():
    conn, ids = _db()
    a, b = ids[:2]
    K.award(conn, a, "recruit", "x", pts=300, now=EVENING)
    K.set_prefs(conn, a, flair="🔥")
    conn.execute("INSERT INTO feed_posts (user_id, sport, legs, caption, created_at) VALUES (?, 'nfl', '[]', ?, ?)",
                 (a, "Lions cover tonight", EVENING))
    conn.commit()
    rows = conn.execute(SF._POST_SQL + "WHERE p.hidden=0 ORDER BY p.id").fetchall()
    views = SF._views(conn, rows, b, False, False)
    assert views and views[0]["lv"] == 3 and views[0]["cls"] == "t1" and views[0]["flair"] == "🔥", views[0]
    pid = views[0]["id"]
    conn.execute("INSERT INTO feed_comments (post_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
                 (pid, a, "told you", EVENING + 5))
    conn.commit()
    com = SF._comment_views(conn, pid, a, b, False)
    assert com[0]["lv"] == 3 and com[0]["flair"] == "🔥", com[0]
    js = Path(ROOT, "web", "js", "social.js").read_text(encoding="utf-8")
    badge = js[js.index("const badge = (p) =>"):js.index("const isBoss")]
    assert 'class="fd-lv kr-lv kr-${escapeAttr(p.cls || "t1")}"' in badge and "fd-flair" in badge
    assert 'loadRoom("js/karma.js", "css/karma.css")' in js[js.index("async function render(append)"):][:600]


def test_the_policy_and_the_page_name_karma_alerts():
    policy = Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8")
    assert "karma alerts" in policy.lower()
    kjs = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")
    assert 'data-kr="remind"' in kjs and "Karma alerts" in kjs


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
