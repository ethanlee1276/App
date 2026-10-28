"""Karma: levels and badges for watching live games and talking (engine/karma).

Ethan, 2026-10-28: "diving back to the Real app there's a feature at hand
where they give you karma for viewing live games and talking and chatting
… it's like a type of a level up feature and you can get badges … look
more deeper into that. And see what other apps do like that as well then
implement features like that".

What this file pins:

  * the level curve and its tiers;
  * every way to earn, each paid once for what it is for and inside its
    day's ceiling — a live game joined and watched (one stretch at a time,
    a game's worth at most, never a game that is not on), a big play seen
    live, the day's first message and one a minute after, reactions from
    other people (never your own), the who-wins vote and its right side at
    the final, Call it and trivia right, watch parties, follows, a friend
    who became a member;
  * a hidden message gives back what it earned;
  * days in a row, with one missed day forgiven after seven, and their
    milestones; the day's three quests;
  * badges by tier, the founding fan, the profile's best;
  * the week's and all-time ladders: usernames, the opt-out, the site's own
    account off them, the week's trophies paid once and never towards the
    next week;
  * the room's heat, paying the people in it;
  * everything said and played before karma began counted once, by the
    same rules;
  * the flair opens at level 3; a chat's names carry their level;
  * nothing is ever paid for a bet, a sportsbook, a parlay or a plan;
  * deleted and exported with the account; named in the Privacy Policy;
  * the server's routes.

Run directly: `python3 tests/test_karma_for_watching_and_talking.py`
"""
import datetime as _dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import callit as CI                              # noqa: E402
from engine import gamechat as GC                            # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"
ET = ZoneInfo("America/New_York")
# A Wednesday evening, Eastern: 2026-10-28 20:00.
T0 = _dt.datetime(2026, 10, 28, 20, 0, tzinfo=ET).timestamp()


def _db(n=5):
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    K.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew", "kai")[:n]:
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    for uid, h in zip(ids, ("ethan", "sam", "casey", "drew", "kai")):
        SF.profile_set(conn, uid, h, "")
    return conn, ids


def _live_dir(state="live", home=None, away=None):
    d = Path(tempfile.mkdtemp())
    live = {"state": state}
    if home is not None:
        live.update(home_score=home, away_score=away)
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "ATL", "away": "SF", "live": live}]}))
    return d


def _kinds(conn, uid):
    return {k: int(s) for k, s in conn.execute("SELECT kind, SUM(pts) FROM karma_events WHERE user_id=? GROUP BY kind",
                                               (uid,))}


def test_the_level_curve_and_its_tiers():
    assert [K.need(lv) for lv in (1, 2, 3, 5, 10, 20, 40)] == [0, 100, 250, 700, 2700, 10450, 40950]
    assert [K.level_of(p) for p in (0, 99, 100, 249, 250, 2699, 2700, 10450, 40950)] == [1, 1, 2, 2, 3, 9, 10, 20, 40]
    for p in range(0, 60000, 37):
        lv = K.level_of(p)
        assert K.need(lv) <= p < K.need(lv + 1), p
    assert [K.tier_of(lv)[0] for lv in (1, 4, 5, 9, 10, 15, 20, 29, 30, 40, 99)] == [
        "Rookie", "Rookie", "Starter", "Starter", "Pro", "All-Star", "MVP", "MVP", "Hall of Famer", "Legend", "Legend"]
    v = K.level_view(400)
    assert v["level"] == 3 and v["from"] == 250 and v["to"] == 450 and v["progress"] == 0.75, v


def test_talking_pays_the_first_message_then_one_a_minute_inside_the_ceiling():
    conn, ids = _db()
    me = ids[0]
    t = T0
    k = K.on_message(conn, me, 1, now=t)
    assert k["got"] == 10 and k["why"] == "First message of the day", k
    assert K.on_message(conn, me, 2, now=t + 30) is None, "one a minute"
    assert K.on_message(conn, me, 3, now=t + 61)["got"] == 2
    for i in range(30):
        K.on_message(conn, me, 10 + i, now=t + 200 + 61 * i)
    assert _kinds(conn, me) == {"chat_day": 10, "chat": 20}, "twenty a day past the first"
    # Tomorrow starts again.
    assert K.on_message(conn, me, 99, now=t + 86400)["got"] == 10


def test_a_reaction_pays_its_writer_once_per_person_and_never_their_own():
    conn, ids = _db()
    a, b, c = ids[:3]
    _, m = GC.send(conn, a, ROOM, "Purdy to Kittle!", now=T0)
    mid = m["id"]
    assert K.on_react(conn, a, mid, "fire", now=T0)["why"] == "Reacted", "your own: the reactor's day, not a like"
    assert _kinds(conn, a).get("liked") is None
    K.on_react(conn, b, mid, "fire", now=T0 + 1)
    K.on_react(conn, b, mid, "wow", now=T0 + 2)              # changed their face: still one person
    K.on_react(conn, c, mid, "lol", now=T0 + 3)
    assert K.on_react(conn, c, mid, "", now=T0 + 4) is None    # taken back: nothing
    assert _kinds(conn, a)["liked"] == 2
    assert _kinds(conn, b) == {"react_day": 5} and _kinds(conn, c) == {"react_day": 5}


def test_a_hidden_message_gives_back_what_it_earned():
    conn, ids = _db()
    a, b, c, d = ids[:4]
    _, m1 = GC.send(conn, a, ROOM, "first", now=T0)
    _, m2 = GC.send(conn, a, ROOM, "second", now=T0 + 70)
    K.on_message(conn, a, m1["id"], now=T0)
    K.on_message(conn, a, m2["id"], now=T0 + 70)
    K.on_react(conn, b, m2["id"], "fire", now=T0 + 80)
    assert _kinds(conn, a) == {"chat_day": 10, "chat": 2, "liked": 1}
    for who in (b, c, d):
        GC.report(conn, who, m2["id"], "spam", now=T0 + 90)
    assert _kinds(conn, a) == {"chat_day": 10}, "three reports hid it: its 2 and its like went back"
    GC.set_hidden(conn, m1["id"], True)
    assert _kinds(conn, a) == {"chat_day": 10}, "the day's first message pays the day, not the message"


def test_watching_a_live_game_pays_by_the_stretch_and_never_a_game_that_is_not_on():
    conn, ids = _db()
    me = ids[0]
    off = _live_dir("final", 20, 17)
    assert K.watch(conn, me, ROOM, now=T0, data_dir=off)[1] == {"ok": True, "live": False}
    d = _live_dir("live")
    code, out = K.watch(conn, me, ROOM, now=T0, data_dir=d)
    assert code == 200 and out["karma"]["got"] == 10 and out["karma"]["why"] == "Joined a live game", out
    assert "karma" not in K.watch(conn, me, ROOM, now=T0 + 60, data_dir=d)[1], "a stretch is five minutes"
    assert K.watch(conn, me, ROOM, now=T0 + 300, data_dir=d)[1]["karma"]["got"] == 2
    assert "karma" not in K.watch(conn, me, ROOM, now=T0 + 360, data_dir=d)[1]
    for i in range(2, 30):
        K.watch(conn, me, ROOM, now=T0 + 300 * i, data_dir=d)
    assert _kinds(conn, me) == {"watch_join": 10, "watch": K.WATCH_PER_GAME}, "a game's worth at most"
    assert K.watch(conn, me, "nfl_12;x", now=T0, data_dir=d)[0] == 400


def test_two_games_at_once_watch_as_one():
    conn, ids = _db()
    me = ids[0]
    d = _live_dir("live")
    (d / "live_nba.json").write_text(json.dumps({"games": [{"event_id": "77", "live": {"state": "live"}}]}))
    for i in range(0, 13):
        K.watch(conn, me, ROOM, now=T0 + 60 * i, data_dir=d)
        K.watch(conn, me, "nba_77", now=T0 + 60 * i + 1, data_dir=d)
    got = _kinds(conn, me)
    assert got["watch_join"] == 20 and got["watch"] == 4, got
    assert K.badge_counts(conn, me)["sports"] == 2 and K.badge_counts(conn, me)["live"] == 2


def test_a_big_play_seen_live_and_the_night_owl():
    conn, ids = _db()
    me, late = ids[:2]
    d = _live_dir("live")
    K.watch(conn, me, ROOM, now=T0, data_dir=d)
    import engine.housepost as HP
    HP.ensure_tables(conn)
    conn.execute("INSERT INTO chat_house_seen (game, play, at, posted) VALUES (?, ?, ?, 1)", (ROOM, "p1", T0 + 100))
    conn.commit()
    out = K.watch(conn, me, ROOM, now=T0 + 160, data_dir=d)[1]
    assert out.get("witness") == 1 and _kinds(conn, me)["witness"] == 5, out
    # Joined after the play: was not there.
    K.watch(conn, late, ROOM, now=T0 + 400, data_dir=d)
    assert "witness" not in _kinds(conn, late)
    night = _dt.datetime(2026, 10, 29, 1, 30, tzinfo=ET).timestamp()
    K.watch(conn, late, ROOM, now=night, data_dir=d)
    assert any(b["key"] == "nightowl" and b["tier"] for b in K.badges(conn, late))


def test_the_vote_pays_once_and_the_right_side_at_the_final():
    conn, ids = _db()
    a, b = ids[:2]
    live = _live_dir("live")
    GC.vote(conn, a, ROOM, "home", now=T0, data_dir=live)
    GC.vote(conn, b, ROOM, "away", now=T0, data_dir=live)
    assert K.on_vote(conn, a, ROOM, now=T0)["got"] == 5
    assert K.on_vote(conn, a, ROOM, now=T0 + 5) is None, "changing your mind pays nothing more"
    K.on_vote(conn, b, ROOM, now=T0)
    assert K.grade_votes(conn, ROOM, _live_dir("live", 7, 3), now=T0 + 10) == 0, "not before the final"
    assert K.grade_votes(conn, ROOM, _live_dir("final", 24, 17), now=T0 + 20) == 1
    assert K.grade_votes(conn, ROOM, _live_dir("final", 24, 17), now=T0 + 30) == 0, "once"
    assert _kinds(conn, a) == {"vote": 5, "vote_won": 10} and _kinds(conn, b) == {"vote": 5}


def _calls_doc(results):
    """A baseball game with at-bats ended as ``results`` (one per index)."""
    events = [{"kind": "atbat", "at_bat": i, "event_type": r} for i, r in enumerate(results)]
    return {"league": "mlb", "event_id": "778899", "events": events, "live": {"state": "live"}}


def test_call_it_pays_each_call_right_as_it_grades_and_five_in_a_row():
    conn, ids = _db()
    me, other = ids[:2]
    CI.ensure_tables(conn)
    game = "mlb_778899"
    for i in range(7):
        for uid, call in ((me, "hit"), (other, "out")):
            conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at) VALUES (?,?,?,?,?)",
                         (uid, game, f"ab{i}", call, T0 + i))
    conn.commit()
    doc = _calls_doc(["single"] * 6 + ["strikeout"])
    CI.grade(conn, doc)
    assert _kinds(conn, me)["call_won"] == 30 and "call_won" not in _kinds(conn, other)
    K.me(conn, me, now=T0 + 600)
    assert _kinds(conn, me).get("call_streak") is None, "the run ended on the strikeout: six, then a miss"
    conn.execute("DELETE FROM callit_calls WHERE unit='ab6'")
    conn.commit()
    K._cache.clear()
    K.me(conn, me, now=T0 + 700)
    assert _kinds(conn, me)["call_streak"] == 25, "six right in a row now: one bonus at five"
    K.me(conn, me, now=T0 + 800)
    assert _kinds(conn, me)["call_streak"] == 25, "once"


def test_trivia_parties_follows_and_a_friend_who_joins():
    conn, ids = _db()
    host, guest = ids[:2]
    assert K.on_trivia(conn, guest, ROOM, "q1", False, now=T0) is None
    assert K.on_trivia(conn, guest, ROOM, "q1", True, now=T0)["got"] == 5
    assert K.on_trivia(conn, guest, ROOM, "q1", True, now=T0) is None
    _, p = GC.party_create(conn, host, ROOM, "Sunday", now=T0)
    GC.party_join(conn, guest, p["token"], now=T0 + 5)
    assert K.on_party_join(conn, guest, p["id"], now=T0 + 5)["got"] == 5
    assert K.on_party_join(conn, host, p["id"], now=T0 + 5) is None, "your own party"
    assert _kinds(conn, host)["party_host"] == 15
    for i in range(14):
        K.on_follow(conn, guest, "team", f"nfl:T{i}", now=T0)
    assert K.on_follow(conn, guest, "price", "x", now=T0) is None, "a price alert is about a bet"
    assert _kinds(conn, guest)["follow"] == 5 * K.FOLLOW_MAX
    from engine import referrals as RF
    RF.init(conn)
    conn.execute("INSERT INTO referrals (referred_id, referrer_id, code, attached_at, paid_at) VALUES (?,?,?,?,?)",
                 (guest, host, "ABC", T0, T0 + 50))
    conn.commit()
    K.sync_user(conn, host, now=T0 + 60)
    assert _kinds(conn, host)["recruit"] == 100


def test_days_in_a_row_with_a_rest_day_after_seven():
    days = lambda *ds: [f"2026-10-{d:02d}" for d in ds]     # noqa: E731
    s = K.streak(days(1, 2, 3), "2026-10-03")
    assert (s["now"], s["best"], s["today"]) == (3, 3, True)
    assert K.streak(days(1, 2, 3), "2026-10-04")["now"] == 3, "alive until today ends"
    assert K.streak(days(1, 2, 3), "2026-10-05")["now"] == 0, "a missed day before seven breaks it"
    assert K.streak(days(1, 2, 4), "2026-10-04")["now"] == 1
    run = days(*range(1, 8))
    assert K.streak(run, "2026-10-09")["now"] == 7 and K.streak(run, "2026-10-09")["rest"], "seven in: a rest in hand"
    s = K.streak(run + days(9, 10), "2026-10-10")
    assert s["now"] == 9 and s["start"] == "2026-10-01" and not s["rest"], "the 8th forgiven, adding nothing"
    assert K.streak(run + days(9, 11), "2026-10-11")["now"] == 1, "a second miss inside seven breaks it"
    assert K.streak([], "2026-10-11") == {"now": 0, "best": 0, "start": None, "rest": False, "today": False}


def test_the_days_milestones_pay_once_a_run():
    conn, ids = _db()
    me = ids[0]
    for i in range(7):
        K.me(conn, me, now=T0 + 86400 * i)
    got = _kinds(conn, me)
    assert got["day"] == 35 and got["streak_bonus"] == 10 + 25, got
    K.me(conn, me, now=T0 + 86400 * 6 + 60)
    assert _kinds(conn, me)["streak_bonus"] == 35


def test_three_quests_a_day_watching_first():
    seen = set()
    for uid in range(1, 40):
        q = K.quests_for(uid, "2026-10-28")
        assert len(q) == 3 == len(set(q)) and q[0] == "watch" and set(q) <= set(K.QUESTS)
        assert K.quests_for(uid, "2026-10-28") == q, "the same all day"
        seen.add(tuple(q))
    assert len(seen) >= 6, "a different pair for different people"
    conn, ids = _db()
    me = ids[0]
    d = _live_dir("live")
    for i in range(0, 11):
        K.watch(conn, me, ROOM, now=T0 + 60 * i, data_dir=d)
    q = {x["key"]: x for x in K.quests(conn, me, K.day_of(T0), now=T0 + 700)}
    assert q["watch"]["done"] and q["watch"]["n"] == 2
    todo = [k for k in q if k != "watch"]
    for key in todo:
        if key == "chat":
            K.on_message(conn, me, 5, now=T0 + 701)
        elif key == "react":
            K.on_play_react(conn, me, "fire", now=T0 + 701)
        elif key == "vote":
            K.on_vote(conn, me, ROOM, now=T0 + 701)
        elif key == "call":
            CI.ensure_tables(conn)
            conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at) VALUES (?,?,?,?,?)",
                         (me, "mlb_1", "ab1", "hit", T0 + 701))
        elif key == "trivia":
            from engine import trivia as TV
            TV.ensure_tables(conn)
            conn.execute("INSERT INTO trivia_answers (user_id, room, qkey, pick, at) VALUES (?,?,?,?,?)",
                         (me, ROOM, "q", 0, T0 + 701))
    conn.commit()
    q = K.quests(conn, me, K.day_of(T0), now=T0 + 702)
    assert all(x["done"] for x in q), q
    got = _kinds(conn, me)
    assert got["quest"] == 30 and got["quests_all"] == 20, got


def test_badges_by_tier_the_founding_fan_and_a_profiles_best():
    conn, ids = _db()
    me = ids[0]
    for i in range(12):
        K.award(conn, me, "call_won", f"g:{i}", now=T0 + i)
    rows = {b["key"]: b for b in K.badges(conn, me)}
    assert rows["caller"]["tier"] == 1 and rows["caller"]["tier_name"] == "Bronze" and rows["caller"]["next"] == 50
    assert rows["live"]["tier"] == 0 and rows["live"]["next"] == 1
    assert rows["founding"]["tier"] == 1, "made in 2026"
    conn.execute("UPDATE users SET created_at=? WHERE id=?", (K.FOUNDING_BEFORE + 10, me))
    assert not {b["key"]: b for b in K.badges(conn, me)}["founding"]["tier"]
    best = K.top_badges(K.badges(conn, ids[1]))
    assert [b["key"] for b in best] == ["founding"] and all(b["tier"] for b in best)
    pub = K.public(conn, me)
    assert pub["level"] == 1 and pub["points"] == 60 and pub["badges"][0]["key"] == "caller"


def test_the_ladders_names_opt_out_and_the_house_kept_off():
    conn, ids = _db()
    a, b, c = ids[:3]
    K.award(conn, a, "watch_join", "r1", pts=10, now=T0)
    K.award(conn, b, "watch_join", "r1", pts=10, now=T0 + 1)
    K.award(conn, b, "watch_join", "r2", pts=10, now=T0 + 2)
    K.award(conn, c, "watch_join", "r1", pts=10, now=T0 + 3)
    lad = K.ladder(conn, "week", viewer=a, now=T0 + 10)
    assert [r["handle"] for r in lad["rows"]] == ["sam", "ethan", "casey"] and lad["mine"] == {"rank": 2, "points": 10}
    K.set_prefs(conn, b, ladder=False)
    lad = K.ladder(conn, "week", viewer=b, now=T0 + 11)
    assert [r["handle"] for r in lad["rows"]] == ["ethan", "casey"] and lad["mine"]["hidden"]
    # The site's own account stands on no ladder.
    conn.execute("UPDATE feed_profiles SET verified=1, handle='qellys_book' WHERE user_id=?", (c,))
    conn.commit()
    K._cache.clear()
    import engine.housepost as HP
    if HP.house_id(conn) == c:
        assert [r["handle"] for r in K.ladder(conn, "week", now=T0 + 12)["rows"]] == ["ethan"]
    assert K.ladder(conn, "all", now=T0 + 13)["since"] == 0.0


def test_a_weeks_top_ten_take_trophies_once_and_never_into_the_next_week():
    conn, ids = _db()
    a, b = ids[:2]
    last_week = T0 - 7 * 86400
    K.award(conn, a, "watch_join", "w1", pts=10, now=last_week)
    K.award(conn, a, "watch_join", "w2", pts=10, now=last_week + 1)
    K.award(conn, b, "watch_join", "w1", pts=10, now=last_week + 2)
    K.me(conn, a, now=T0)
    K.me(conn, b, now=T0)
    assert _kinds(conn, a)["trophy"] == 100 and _kinds(conn, b)["trophy"] == 50
    K.me(conn, a, now=T0 + 60)
    assert _kinds(conn, a)["trophy"] == 100, "once"
    week = K.ladder(conn, "week", viewer=a, now=T0 + 61)
    assert week["mine"]["points"] < 100, ("a trophy is not this week's karma", week["mine"])
    assert K.ladder(conn, "all", viewer=a, now=T0 + 62)["mine"]["points"] > 100


def test_the_rooms_heat_pays_the_people_in_it():
    conn, ids = _db()
    people = ids[:4]
    for i in range(12):
        GC.send(conn, people[i % 3], ROOM, f"go {i}", now=T0 + 10 * i - 200)
    h = K.hype(conn, ROOM, viewer=people[0], now=T0)
    assert h["level"] == 1 and h["karma"]["got"] == 5, h
    assert "karma" not in K.hype(conn, ROOM, viewer=people[0], now=T0 + 6), "each level once an hour"
    assert "karma" not in K.hype(conn, ROOM, viewer=people[3], now=T0 + 12), "not part of it"
    K._cache.clear()
    assert K.hype(conn, ROOM, now=T0 + 600)["level"] == 0, "five minutes quiet: cold"
    two = _db()[0]
    for i in range(30):
        GC.send(two, (i % 2) + 1, ROOM, f"x {i}", now=T0 + 4 * i - 150)
    assert K.hype(two, ROOM, now=T0)["level"] == 0, "two people are a conversation, not a room"


def test_what_was_said_before_karma_counts_once_by_the_same_rules():
    conn, ids = _db()
    a, b = ids[:2]
    for i in range(5):
        GC.send(conn, a, ROOM, f"m{i}", now=T0 + 10 * i)          # 0, 10, … 40 s: one minute
    _, m = GC.send(conn, b, ROOM, "late", now=T0 + 120)
    GC.react(conn, a, m["id"], "fire", now=T0 + 130)
    GC.vote(conn, b, ROOM, "home", now=T0, data_dir=_live_dir("live"))
    CI.ensure_tables(conn)
    conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at, result, won) VALUES (?,?,?,?,?,?,?)",
                 (a, "mlb_1", "ab1", "hit", T0, "hit", 1))
    conn.commit()
    assert K.backfill(conn, now=T0 + 500) is True
    assert K.backfill(conn, now=T0 + 501) is False, "once"
    assert _kinds(conn, a) == {"chat_day": 10, "react_day": 5, "call_won": 5}, _kinds(conn, a)
    assert _kinds(conn, b) == {"chat_day": 10, "liked": 1, "vote": 5}, _kinds(conn, b)
    day = conn.execute("SELECT day FROM karma_events WHERE user_id=? AND kind='chat_day'", (a,)).fetchone()[0]
    assert day == "2026-10-28", "on the day it was said"


def test_the_flair_opens_at_level_three_and_the_chat_wears_the_level():
    conn, ids = _db()
    me = ids[0]
    assert K.set_prefs(conn, me, flair="🔥")[0] == 403
    K.award(conn, me, "recruit", "x", pts=300, now=T0)
    assert K.set_prefs(conn, me, flair="💩")[0] == 400
    assert K.set_prefs(conn, me, flair="🔥") == (200, {"ok": True, "flair": "🔥", "ladder": True, "remind": False,
                                                    "phones": 0})
    GC.send(conn, me, ROOM, "hello", now=T0)
    _, v = GC.room_view(conn, ROOM, ids[1], now=T0 + 1)
    by = v["messages"][0]["by"]
    assert by["lv"] == 3 and by["cls"] == "t1" and by["flair"] == "🔥", by
    assert "hype" in v and v["hype"]["level"] == 0


def test_the_day_check_in_and_a_level_crossed_said_once():
    conn, ids = _db()
    me = ids[0]
    first = K.me(conn, me, now=T0)
    assert first["today"] == 5 and "up_from" not in first
    assert K.me(conn, me, now=T0 + 60)["today"] == 5, "once a day"
    K.award(conn, me, "recruit", "x", pts=200, now=T0 + 61)
    up = K.me(conn, me, now=T0 + 120)
    assert up["level"] == 2 and up["up_from"] == 1, up
    assert "up_from" not in K.me(conn, me, now=T0 + 180), "said once"


def test_nothing_is_ever_paid_for_money_or_bets():
    for kind in K.RULES:
        assert not re.search(r"bet|track|tail|fade|parlay|stake|book|plan|pay|wager|odds|slip", kind), kind
    src = Path(ROOT, "server.py").read_text(encoding="utf-8")
    for handler in ("def _tailfade_post", "def _parlay_check", "def _parlay_build", "def _mybets_closes",
                    "def _mybets_risk", "def _ask_slip", "def _ask_track"):
        i = src.find(handler)
        if i < 0:
            continue
        body = src[i:src.find("\n    def ", i + 10)]
        assert "karma" not in body.lower(), handler


def test_deleted_and_exported_with_the_account_and_named_in_the_policy():
    conn, ids = _db()
    me = ids[0]
    K.award(conn, me, "recruit", "x", pts=100, now=T0)
    K.watch(conn, me, ROOM, now=T0, data_dir=_live_dir("live"))
    K.set_prefs(conn, me, ladder=False)
    out = A.export_user(conn, me)
    assert out["karma"] and out["live_games_watched"][0]["game"] == ROOM and out["karma_settings"]["on_ladders"] is False
    A.delete_user(conn, me)
    for table in ("karma_events", "karma_watch", "karma_prefs", "karma_weeks"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (me,)).fetchone()[0] == 0, table
    policy = Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8")
    for table in ("karma_events", "karma_watch", "karma_prefs", "karma_weeks"):
        assert f"<code>{table}</code>" in policy, table


def test_the_servers_routes():
    src = Path(ROOT, "server.py").read_text(encoding="utf-8")
    i = src.index("    def _karma(self")
    body = src[i:src.index("\n    def ", i + 10)]
    for want in ('("me", "ladder", "watch", "prefs")', "K.me(conn, who[\"id\"])", "K.watch(conn, who[\"id\"]",
                 '"Make a free account to earn karma."', "K.ladder(conn, scope"):
        assert want in body, want
    assert 'parsed.path.startswith("/api/karma/")' in src
    # Each chat action carries what it earned back to the page.
    for hook in ("K.on_message(conn, uid", "K.on_react(conn, uid", "K.on_play_react(conn, uid",
                 "K.on_vote(conn, uid, room)", "K.on_party_join(conn, uid", "K.on_trivia(conn, who[\"id\"]",
                 "K.on_follow(conn, who[\"id\"]", "K.grade_votes(conn, out[\"room\"])"):
        assert hook in src, hook


KJS = Path(ROOT, "web", "js", "karma.js").read_text(encoding="utf-8")


def test_the_page_knows_the_same_tiers_quests_badges_and_rules():
    tiers = re.findall(r'\[(\d+), "([^"]+)", "(t\d)"\]', KJS[KJS.index("const KR_TIERS"):KJS.index("];", KJS.index("const KR_TIERS"))])
    assert [(int(a), b, c) for a, b, c in tiers] == list(K.TIERS), tiers
    unlock = KJS[KJS.index("const KR_UNLOCK"):KJS.index("};", KJS.index("const KR_UNLOCK"))]
    assert sorted(int(x) for x in re.findall(r"\b(\d+): \"", unlock)) == sorted({K.FLAIR_AT, K.COLOR_AT, K.RING_AT})
    short = KJS[KJS.index("const KR_QUEST_SHORT"):KJS.index("};", KJS.index("const KR_QUEST_SHORT"))]
    assert set(re.findall(r"(\w+): \"", short)) == set(K.QUESTS)
    icons = KJS[KJS.index("const KR_BADGE_ICON"):KJS.index("};", KJS.index("const KR_BADGE_ICON"))]
    assert set(re.findall(r"(\w+): \"", icons)) == {f[0] for f in K.FAMILIES} | {o[0] for o in K.ONE_OFF}
    groups = KJS[KJS.index("const KR_RULE_GROUPS"):KJS.index("]]];", KJS.index("const KR_RULE_GROUPS"))]
    listed = re.findall(r'"([a-z_]+)"', groups.split("[", 1)[1])
    paying = {k for k, v in K.RULES.items() if v[0] > 0}
    named = [k for k in listed if k in K.RULES]
    assert sorted(named) == sorted(paying) and len(named) == len(set(named)), (sorted(set(named) ^ paying))


def test_karma_loads_with_the_pages_that_show_it_and_never_with_the_first_paint():
    sw = Path(ROOT, "web", "sw.js").read_text(encoding="utf-8")
    lazy = sw[sw.index("const LAZY = ["):sw.index("];", sw.index("const LAZY = ["))]
    shell = sw[sw.index("const SHELL = ["):sw.index("];", sw.index("const SHELL = ["))]
    assert '"/js/karma.js", "/css/karma.css"' in lazy and "karma" not in shell
    html = Path(ROOT, "web", "index.html").read_text(encoding="utf-8")
    assert "karma" not in html.lower(), "the first visit downloads none of it"
    chat = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    for want in ('loadRoom("js/karma.js", "css/karma.css")', "karmaStripMount(kh)", "karmaNote(k)",
                 'fetch("/api/karma/watch"', "if (out && out.karma) chatKarma(out.karma);", "CH.hype = v.hype || null;"):
        assert want in chat, want
    # The watching clock only runs for a live game, in view, signed in.
    tick = chat[chat.index("async function chatWatchTick("):chat.index("\n}", chat.index("async function chatWatchTick("))]
    assert 'state === "live"' in tick and "_acctUser.signed_in" in tick and "!document.hidden" in tick
    social = Path(ROOT, "web", "js", "social.js").read_text(encoding="utf-8")
    assert '["karma", "Karma"]' in social and "karmaPanelMount(kp)" in social and "karmaProfileMount(host, p.karma, mine)" in social


def test_in_a_browser_the_chat_the_strip_the_tab_and_a_level_crossed():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import shutil
    import time
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    from test_the_chat_doors_open_without_errors import _game
    conn, ids = _db()
    me = ids[0]
    d = _live_dir("live")
    K.watch(conn, me, ROOM, now=T0, data_dir=d)
    for i in range(8):
        K.award(conn, me, "call_won", f"g{i}", now=T0 + i)
    K.award(conn, ids[1], "recruit", "x", pts=300, now=T0)
    K.set_prefs(conn, ids[1], flair="🏈")
    v = K.me(conn, me, now=T0 + 60)
    cards = K.cards(conn, ids)
    msgs = [{"id": 100 + i, "at": time.time() - 60 * (5 - i), "body": f"message {i}", "own": False, "reacts": {}, "mine": "",
             "by": {"handle": h, "color": i, **cards.get(ids[i], {})}} for i, h in enumerate(("ethan", "sam", "casey"))]
    room = {"room": "nfl_990077", "t": time.time(), "messages": msgs, "older": False, "reacts": {}, "plays": {}, "threads": {},
            "mine_plays": {}, "votes": {"home": 3, "away": 2, "mine": "", "open": True}, "vote_path": [], "here": 9,
            "me": {"signed_in": True, "handle": "ethan"}, "hype": {"level": 2, "n": 30, "next": 50, "progress": 0.2}}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    prof = {"profile": {"handle": "ethan", "name": "Ethan", "color": 1, "bio": "", "since": T0, "verified": False,
                        "official": False, "founder": False, "posts": 0, "tails": 0, "likes": 0, "followers": 0,
                        "following_count": 0, "record": {"n": 0}, "record30": {"n": 0}, "streak": "", "mine": True,
                        "karma": K.public(conn, me)}, "posts": [], "more": False, "next": 0}
    pbp = os.path.join(ROOT, "web", "data", "pbp")
    made = not os.path.isdir(pbp)
    os.makedirs(pbp, exist_ok=True)
    path = os.path.join(pbp, "nfl_990077.json")
    with open(path, "w") as fh:
        fh.write(json.dumps(_game("990077", 1)))
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/**", ful(json.dumps({"posts": []})))
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/feed/profile*", ful(json.dumps(prof)))
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/karma/watch*", ful(json.dumps({"ok": True, "live": True, "karma": {
                    "got": 10, "why": "Joined a live game", "total": v["points"] + 10, "level": v["level"], "up": False}})))
                page.route("**/api/chat/room*", ful(json.dumps(room)))
                page.route("**/api/chat/counts*", ful(json.dumps({"rooms": {}})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.route("**/api/callit/**", ful(json.dumps({"open": None, "kind": "football", "board": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb_chat_rules_v1','1');"
                                     f"localStorage.setItem('qb_kr_level','{v['level']}');}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/990077", wait_until="load")
                page.wait_for_timeout(6500)
                got["note"] = page.evaluate("[...document.querySelectorAll('.kr-note')].map((n) => n.textContent).join('|')")
                page.evaluate("(() => { const c = document.querySelector('.gch-entry'); c.scrollIntoView({block: 'center'}); c.click(); })()")
                page.wait_for_timeout(900)
                got["chips"] = page.evaluate("[...document.querySelectorAll('#gch-sheet .gch-lv')].map((c) => c.textContent)")
                got["flair"] = page.evaluate("[...document.querySelectorAll('#gch-sheet .gch-flair')].map((c) => c.textContent)")
                got["heat"] = page.evaluate("(document.querySelector('#gch-sheet .gch-heat') || {}).textContent || ''")
                got["tier"] = page.evaluate("getComputedStyle(document.querySelector('#gch-sheet .gch-lv')).color")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(3000)
                got["strip"] = page.evaluate("(document.querySelector('.kr-strip') || {}).textContent || ''")
                page.evaluate("try { sessionStorage.setItem('qb_acct_tab', 'karma'); } catch (e) {}")
                page.goto(f"http://127.0.0.1:{port}/index.html#account", wait_until="load")
                page.wait_for_timeout(3500)
                got["badges"] = page.evaluate("document.querySelectorAll('.kr-panel-host .kr-badge').length")
                got["hero"] = page.evaluate("(document.querySelector('.kr-hero h2') || {}).textContent || ''")
                got["row"] = page.evaluate("(document.querySelector('.kr-prof') || {}).textContent || ''")
                got["switches"] = page.evaluate("document.querySelectorAll('.kr-panel-host .kr-switch [role=switch]').length")
                page.evaluate("karmaNote({got: 40, why: 'All three quests', total: 99999, level: 60, up: true})")
                page.wait_for_timeout(500)
                got["up"] = page.evaluate("(document.querySelector('.kr-up h3') || {}).textContent || ''")
                page.evaluate("document.querySelector('[data-kr=up-close]').click()")
                got["closed"] = page.evaluate("!document.querySelector('.kr-up')")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
        os.remove(path)
        if made:
            shutil.rmtree(pbp, ignore_errors=True)
    assert not errs, errs[:3]
    assert "+10Joined a live game" in got["note"], got
    assert got["chips"] == [str(v["level"]), "3", "1"] and got["flair"] == ["🏈"], got
    assert "Room heat · level 2" in got["heat"], got
    assert got["tier"] not in ("rgba(0, 0, 0, 0)", ""), got
    assert f"Level {v['level']}" in got["strip"] and "karma" in got["strip"], got
    assert got["badges"] == len(K.FAMILIES) + len(K.ONE_OFF) and got["hero"].startswith(f"Level {v['level']}"), got
    assert f"Level {v['level']}" in got["row"], got
    assert got["switches"] == 2, got
    assert got["up"] == "Level 60", got
    assert got["closed"], got


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
