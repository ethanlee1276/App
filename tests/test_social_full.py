"""The full social feature: profiles, follows, blocks, talk posts, threads,
notifications, the graded record, the leaderboard, search.

Ethan, 2026-10-07: "a full social feature … take reference from something
like facebook or reddit … there needs to be profiles for users." The audit
is docs/SOCIAL_AUDIT.md. What this file pins is each rule the audit names,
above all the one the betting apps are built on: the record cannot be
faked — a leg posts only before kickoff, never changes afterwards, and is
graded from the journal's own recorded stat at the line its poster took.

Run directly: `python3 tests/test_social_full.py`
"""

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

# The board fixtures (PROP_FREE, GAME, _board_dir, _leg) are the first
# feed file's own, loaded by path so the two files share one copy.
import importlib.util as _ilu                                # noqa: E402
_spec = _ilu.spec_from_file_location("feed_fixtures", os.path.join(ROOT, "tests", "test_social_feed.py"))
T = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(T)

GOOD = "correct-horse-battery"


def _db(n=4):
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    ids = []
    for i in range(n):
        _, out = A.create_user(conn, f"u{i}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        SF.profile_set(conn, out["id"], f"user{i}", "")
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    return conn, ids


def _ledger(rows):
    """A journal with only the columns grading reads."""
    lc = sqlite3.connect(":memory:")
    lc.row_factory = sqlite3.Row
    lc.execute("CREATE TABLE bets (sport TEXT, date TEXT, game_day TEXT, player TEXT, market TEXT, "
               "side TEXT, line REAL, status TEXT, actual REAL)")
    for r in rows:
        lc.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?)", r)
    return lc


def _post(conn, uid, d, legs=(T.PROP_FREE, T.GAME), caption="", now=None):
    return SF.create_post(conn, uid, "nfl", "2026-10-11", [T._leg(r) for r in legs], caption,
                          data_dir=d, now=now)


def _age(conn, pid, seconds):
    conn.execute("UPDATE feed_posts SET created_at=created_at-? WHERE id=?", (seconds, pid))
    conn.commit()


# --- profiles -----------------------------------------------------------------

def test_a_profile_carries_name_colour_team_and_a_record():
    conn, (a, b, *_) = _db()
    code, out = SF.profile_set(conn, a, "ethan", "Lions fan", name="Ethan L", color=3, team="nfl:DET")
    assert code == 200 and out["profile"]["team"] == "nfl:DET" and out["profile"]["color"] == 3
    assert SF.profile_set(conn, a, "ethan", "", team="nope")[0] == 400
    code, page = SF.profile_page(conn, "ethan", viewer=b)
    p = page["profile"]
    assert code == 200 and p["name"] == "Ethan L" and p["record"]["n"] == 0
    assert p["followers"] == 0 and p["following_count"] == 0 and not p["following"] and not p["mine"]
    assert SF.profile_page(conn, "ethan", viewer=a)[1]["profile"]["mine"]


def test_a_display_name_is_filtered_like_a_handle():
    conn, (a, *_) = _db()
    import codecs
    assert SF.profile_set(conn, a, "user0", "", name="big " + codecs.decode("fuvg", "rot13"))[0] == 400
    assert SF.profile_set(conn, a, "user0", "", name="Qellys")[0] == 400


# --- follows and blocks ------------------------------------------------------

def test_follow_counts_notifies_and_fills_the_following_feed():
    conn, (a, b, c, _) = _db()
    d = T._board_dir()
    _post(conn, b, d)
    _post(conn, c, d, legs=(T.GAME,))
    assert SF.feed(conn, a, order="following")["posts"] == []
    code, out = SF.toggle_follow(conn, a, "user1")
    assert code == 200 and out == {"following": True, "followers": 1}
    handles = [p["handle"] for p in SF.feed(conn, a, order="following")["posts"]]
    assert handles == ["user1"]
    kinds = [n["kind"] for n in SF.notifications(conn, b)["items"]]
    assert kinds == ["follow"]
    assert SF.follow_list(conn, "user1", "followers")[1]["people"][0]["handle"] == "user0"
    assert SF.toggle_follow(conn, a, "user1")[1]["following"] is False
    assert SF.toggle_follow(conn, a, "user0")[0] == 400       # yourself


def test_a_block_hides_both_ways_and_stops_follows_and_comments():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, b, d)
    SF.toggle_follow(conn, a, "user1")
    assert SF.toggle_block(conn, a, "user1")[1] == {"blocked": True}
    assert SF.feed(conn, a)["posts"] == [] and SF.feed(conn, b)["posts"] != []  # b's own post
    assert SF.post_detail(conn, out["id"], a)[0] == 404
    assert SF.profile_page(conn, "user1", viewer=a)[0] == 404
    assert SF.profile_page(conn, "user0", viewer=b)[0] == 404   # both ways
    assert SF.toggle_follow(conn, a, "user1")[0] == 403
    assert SF.toggle_follow(conn, b, "user0")[0] == 403
    assert SF.add_comment(conn, a, out["id"], "hi")[0] == 404
    assert SF.toggle_like(conn, a, out["id"])[0] == 404
    assert conn.execute("SELECT COUNT(*) FROM feed_follows").fetchone()[0] == 0
    SF.toggle_block(conn, a, "user1")
    assert SF.feed(conn, a)["posts"]


# --- talk posts and edits -----------------------------------------------------

def test_a_talk_post_has_a_title_and_body_and_no_tail():
    conn, (a, b, *_) = _db()
    code, out = SF.create_talk(conn, a, "nfl", "Who starts at QB for the Jets?", "Thoughts?")
    assert code == 200
    p = SF.feed(conn, b, kind="text")["posts"][0]
    assert p["kind"] == "text" and p["title"].startswith("Who starts") and p["legs"] == []
    assert SF.tail(conn, b, out["id"], entitled=True)[0] == 404
    assert SF.create_talk(conn, a, "nfl", "", "body")[0] == 400
    assert SF.feed(conn, b, kind="parlay")["posts"] == []


def test_words_edit_for_fifteen_minutes_and_legs_never():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d, caption="first")
    assert SF.edit_post(conn, b, out["id"], caption="x")[0] == 404
    assert SF.edit_post(conn, a, out["id"], caption="fixed")[0] == 200
    p = SF.feed(conn, a)["posts"][0]
    assert p["caption"] == "fixed" and p["edited"]
    _age(conn, out["id"], 16 * 60)
    assert SF.edit_post(conn, a, out["id"], caption="later")[0] == 403
    import inspect
    assert "legs" not in inspect.signature(SF.edit_post).parameters


# --- threads, comment likes, mentions ----------------------------------------

def test_replies_thread_one_level_and_notify_the_right_people():
    conn, (a, b, c, _) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d)
    _, c1 = SF.add_comment(conn, b, out["id"], "nice one")
    _, c2 = SF.add_comment(conn, c, out["id"], "agreed", parent_id=c1["id"])
    _, c3 = SF.add_comment(conn, a, out["id"], "thanks", parent_id=c2["id"])   # reply to a reply
    code, det = SF.post_detail(conn, out["id"], a)
    top = det["post"]["comment_list"]
    assert len(top) == 1 and [r["body"] for r in top[0]["replies"]] == ["agreed", "thanks"]
    assert {n["kind"] for n in SF.notifications(conn, a)["items"]} == {"comment"}
    assert {n["kind"] for n in SF.notifications(conn, b)["items"]} == {"reply"}
    assert SF.toggle_comment_like(conn, a, c1["id"])[1] == {"likes": 1, "liked": True}
    assert "comment_like" in {n["kind"] for n in SF.notifications(conn, b)["items"]}
    # Deleting a top comment takes its thread with it.
    SF.delete(conn, b, "comment", c1["id"])
    assert SF.post_detail(conn, out["id"], a)[1]["post"]["comment_list"] == []


def test_mentions_notify_and_self_actions_never_do():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d, caption="tail this @user1 and @nobody_here")
    assert [n["kind"] for n in SF.notifications(conn, b)["items"]] == ["mention"]
    SF.toggle_like(conn, a, out["id"])
    SF.tail(conn, a, out["id"], entitled=True, data_dir=d)
    assert SF.notifications(conn, a)["items"] == []
    assert SF.unseen(conn, b) == 1
    SF.mark_seen(conn, b)
    assert SF.unseen(conn, b) == 0


# --- the record ---------------------------------------------------------------

def test_a_leg_cannot_be_posted_after_kickoff():
    conn, (a, *_) = _db()
    d = T._board_dir()
    full = json.loads((d / "built" / "recommendations.json").read_text())
    full["recommendations"][0]["kickoff"] = "2026-10-11T17:00:00Z"
    (d / "built" / "recommendations.json").write_text(json.dumps(full))
    before = dt.datetime(2026, 10, 11, 16, 0, tzinfo=dt.timezone.utc).timestamp()
    after = dt.datetime(2026, 10, 11, 17, 1, tzinfo=dt.timezone.utc).timestamp()
    code, out = _post(conn, a, d, legs=(T.PROP_FREE,), now=after)
    assert code == 400 and "already started" in out["error"]
    assert _post(conn, a, d, legs=(T.PROP_FREE,), now=before)[0] == 200


def test_legs_are_graded_from_the_journal_at_the_posters_line():
    leg = {"kind": "prop", "player": "Amon-Ra St. Brown", "market": "rec_yds", "side": "OVER",
           "line": 64.5, "game_date": "2026-10-11"}
    lc = _ledger([("nfl", "W6", "2026-10-11", "Amon-Ra St. Brown", "rec_yds", "OVER", 70.5, "lost", 66.0)])
    # The journal's own row lost at 70.5; the poster took 64.5, and 66 clears it.
    assert SF.grade_leg(lc, "nfl", leg) == "won"
    assert SF.grade_leg(lc, "nfl", dict(leg, side="UNDER")) == "lost"
    assert SF.grade_leg(lc, "nfl", dict(leg, line=66.0)) == "push"
    assert SF.grade_leg(lc, "nfl", dict(leg, game_date="2026-10-18")) is None
    lv = _ledger([("nfl", "W6", "2026-10-11", "Amon-Ra St. Brown", "rec_yds", "OVER", 64.5, "void", None)])
    assert SF.grade_leg(lv, "nfl", leg) == "void"


def test_game_legs_grade_through_the_journals_game_keys():
    spread = {"kind": "game", "market": "spread", "team": "DET", "side": "DET", "line": -3,
              "matchup": "GB @ DET", "game_date": "2026-10-11"}
    # The journal stores a spread as the team at OVER the negated number;
    # `actual` is the margin.
    lc = _ledger([("nfl", "W6", "2026-10-11", "DET", "spread", "OVER", 3.0, "won", 7.0),
                  ("nfl", "W6", "2026-10-11", "GB@DET", "total", "OVER", 47.5, "won", 51.0),
                  ("nfl", "W6", "2026-10-11", "DET", "moneyline", "OVER", 0.5, "won", 1.0)])
    assert SF.grade_leg(lc, "nfl", spread) == "won"
    assert SF.grade_leg(lc, "nfl", dict(spread, line=-7.5)) == "lost"
    total = {"kind": "game", "market": "total", "side": "Under", "line": 49.5, "matchup": "GB @ DET",
             "game_date": "2026-10-11"}
    assert SF.grade_leg(lc, "nfl", total) == "lost"
    ml = {"kind": "game", "market": "moneyline", "team": "DET", "matchup": "GB @ DET",
          "game_date": "2026-10-11"}
    assert SF.grade_leg(lc, "nfl", ml) == "won"


def test_a_parlay_result_follows_the_book_rules():
    W = lambda o: {"result": "won", "odds": o}                       # noqa: E731
    assert SF.post_result([W(-110), {"result": "lost", "odds": -110}]) == ("lost", -1.0)
    assert SF.post_result([{"result": "lost"}, {"result": None}]) == ("lost", -1.0)   # dead early
    assert SF.post_result([W(-110), {"result": None}])[0] == "pending"
    res, units = SF.post_result([W(100), W(100)])
    assert res == "won" and units == 3.0
    assert SF.post_result([W(100), {"result": "void", "odds": -300}]) == ("won", 1.0)
    assert SF.post_result([{"result": "push"}, {"result": "void"}]) == ("push", 0.0)
    assert SF.post_result([W(100), {"result": "nograde"}])[0] == "nograde"


def test_settling_grades_due_posts_notifies_and_builds_the_record():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d, legs=(T.PROP_FREE,))
    opened = []

    def opener():
        opened.append(1)
        return _ledger([("nfl", "2026-10-11", "2026-10-11", "Amon-Ra St. Brown", "rec_yds", "OVER",
                         64.5, "won", 80.0)])
    # Not due yet: the journal is never even opened.
    assert SF.settle_pending(conn, opener) == 0 and not opened
    _age(conn, out["id"], 3 * 3600)
    assert SF.settle_pending(conn, opener) == 1
    p = SF.feed(conn, b)["posts"][0]
    assert p["result"] == "won" and p["legs"][0]["result"] == "won" and p["units"] == 0.87
    assert "won" in [n["kind"] for n in SF.notifications(conn, a)["items"]]
    rec = SF.profile_page(conn, "user0")[1]["profile"]["record"]
    assert rec["w"] == 1 and rec["units"] == 0.87
    assert SF.profile_page(conn, "user0", tab="record")[1]["posts"][0]["result"] == "won"


def test_tail_closes_once_the_games_begin():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d, legs=(T.PROP_FREE,))
    assert SF.feed(conn, b)["posts"][0]["closed"] is False
    legs = json.loads(conn.execute("SELECT legs FROM feed_posts").fetchone()["legs"])
    legs[0]["kickoff"] = "2020-01-01T00:00:00Z"
    conn.execute("UPDATE feed_posts SET legs=?", (json.dumps(legs),))
    conn.commit()
    assert SF.feed(conn, b)["posts"][0]["closed"] is True
    assert SF.tail(conn, b, out["id"], entitled=True, data_dir=d)[0] == 409
    _, talk = SF.create_talk(conn, a, "nfl", "Talk is never closed", "")
    assert SF.feed(conn, b, kind="text")["posts"][0]["closed"] is False


def test_a_graded_paid_leg_is_shown_to_everybody():
    leg = {"paid": True, "player": "Jahmyr Gibbs", "side": "OVER", "line": 71.5, "result": None}
    assert SF.public_leg(leg, entitled=False)["locked"]
    shown = SF.public_leg(dict(leg, result="won"), entitled=False)
    assert "locked" not in shown and shown["side"] == "OVER" and shown["result"] == "won"


def test_the_leaderboard_needs_five_graded_posts():
    conn, (a, b, c, _) = _db()
    now = time.time()
    for i in range(5):
        conn.execute("INSERT INTO feed_posts (user_id, sport, legs, created_at, kind, result, units) "
                     "VALUES (?,?,?,?,?,?,?)", (a, "nfl", "[]", now - i, "parlay", "won", 1.0))
    for i in range(4):
        conn.execute("INSERT INTO feed_posts (user_id, sport, legs, created_at, kind, result, units) "
                     "VALUES (?,?,?,?,?,?,?)", (b, "nfl", "[]", now - i, "parlay", "won", 5.0))
    conn.commit()
    top = SF.leaders(conn)["top"]
    assert [p["handle"] for p in top] == ["user0"] and top[0]["units"] == 5.0 and top[0]["roi"] == 100.0
    assert [p["handle"] for p in SF.suggestions(conn, c)][0] == "user0"
    assert "user0" not in [p["handle"] for p in SF.suggestions(conn, a)]


# --- sorting, search, caps ----------------------------------------------------

def test_hot_lifts_an_engaged_post_and_top_ranks_by_score():
    conn, (a, b, c, e) = _db()
    d = T._board_dir()
    _, p1 = _post(conn, a, d, legs=(T.PROP_FREE,))
    _, p2 = SF.create_talk(conn, b, "nfl", "Newest but quiet", "")
    for who in (b, c, e):
        SF.toggle_like(conn, who, p1["id"])
    SF.tail(conn, c, p1["id"], entitled=True, data_dir=d)
    assert [p["id"] for p in SF.feed(conn, order="new")["posts"]][0] == p2["id"]
    assert [p["id"] for p in SF.feed(conn, order="hot")["posts"]][0] == p1["id"]
    assert [p["id"] for p in SF.feed(conn, order="top", window="day")["posts"]][0] == p1["id"]
    _age(conn, p1["id"], 2 * 86400)
    assert [p["id"] for p in SF.feed(conn, order="top", window="day")["posts"]] == [p2["id"]]


def test_search_finds_people_and_posts():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    SF.profile_set(conn, a, "LionsLocks", "", name="Detroit Dan")
    _post(conn, b, d, legs=(T.PROP_FREE,))
    SF.create_talk(conn, b, "nfl", "Gibbs workload talk", "")
    out = SF.search(conn, "lions")
    assert [p["handle"] for p in out["people"]] == ["LionsLocks"]
    assert SF.search(conn, "detroit")["people"][0]["handle"] == "LionsLocks"
    assert len(SF.search(conn, "St. Brown")["posts"]) == 1
    assert len(SF.search(conn, "gibbs")["posts"]) == 1
    assert SF.search(conn, "x") == {"people": [], "posts": []}


def test_a_new_account_posts_three_times_on_day_one():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    _, out = A.create_user(conn, "new@example.com", GOOD, confirmed=True)
    uid = out["id"]
    SF.profile_set(conn, uid, "fresh", "")
    for i in range(SF.NEW_ACCOUNT_POSTS):
        assert SF.create_talk(conn, uid, "nfl", f"Thread {i}", "")[0] == 200
    code, res = SF.create_talk(conn, uid, "nfl", "One more", "")
    assert code == 429 and "first day" in res["error"]


def test_reports_carry_a_reason():
    conn, (a, b, c, e) = _db()
    _, out = SF.create_talk(conn, a, "nfl", "Buy my picks at scam dot com", "")
    for who, why in ((b, "spam"), (c, "scam"), (e, "bogus")):
        SF.report(conn, who, "post", out["id"], why)
    item = SF.reported(conn)[0]
    assert item["hidden"] and item["reasons"] == ["other", "scam", "spam"]


# --- the account owns its rows ------------------------------------------------

def test_deleting_an_account_clears_every_social_table():
    conn, (a, b, *_) = _db()
    d = T._board_dir()
    _, out = _post(conn, a, d)
    _, c1 = SF.add_comment(conn, b, out["id"], "hi")
    SF.toggle_comment_like(conn, a, c1["id"])
    SF.toggle_follow(conn, b, "user0")
    SF.toggle_follow(conn, a, "user1")
    SF.toggle_block(conn, a, "user3")
    exp = A.export_user(conn, a)["public_feed"]
    assert exp["following"] == ["user1"] and exp["blocked"] == ["user3"]
    A.delete_user(conn, a)
    for t in SF.FEED_TABLES:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        cols = rows[0].keys() if rows else []
        for r in rows:
            for col in ("user_id", "follower_id", "followee_id", "blocked_id", "actor_id"):
                if col in cols:
                    assert r[col] != a, (t, col)


def test_the_social_code_loads_on_first_use_not_on_the_first_visit():
    """13 KB gz that most first visits never open: social.js and social.css
    load when The Feed does (app.js loadSocial), never from index.html."""
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "social.js" not in html and "social.css" not in html
    assert 's.src = "js/social.js"' in app and 'css.href = "css/social.css"' in app
    soc = open(os.path.join(ROOT, "web", "js", "social.js"), encoding="utf-8").read()
    assert "window.QBSocial = {" in soc
    # A link to a book is only ever drawn through safeHref.
    assert 'href="${safeHref(url)}"' in soc and "href=\"${url}" not in soc


def test_the_server_has_every_route():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def _feed_get"):src.index("def _social_get")]
    for route in ("list", "rail", "post", "profile", "follows", "leaders", "search", "notifications",
                  "reported", "talk", "edit", "comment-like", "follow", "block", "seen", "friend"):
        assert f'"{route}"' in body, route
    assert "settle_pending" in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
