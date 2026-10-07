"""The Feed, third cut: Ethan's render and one profile for the whole site.

Ethan, 2026-10-07, with a render of the social page: "The social page
looks cluttered … Here is renders you must follow … the account page on
the feed page and the main account page should be one page … it should
all be one main profile for the whole site."

What this file pins:
  - ONE PROFILE: the friends list, friend search, the streak leaderboard
    and the account endpoint all read the site profile.
  - The render's rail: Trending Picks (people, not taps; open legs only;
    paid legs stay locked), Top Bettors by Win % / Units / Followers over
    7 days / 30 days / all time (graded posts only, five to qualify),
    Community Stats (counted, never estimated).
  - The composer: a take needs words, not a title; #tags; polls (one
    final vote); links (https only, not on day one); a parlay picked
    from today's board (the public board without a plan).
  - The verified badge and the site's own reserved names.

Run directly: `python3 tests/test_social_v3.py`
"""

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import social as SOC                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402
from engine import streak as STK                             # noqa: E402

import importlib.util as _ilu                                # noqa: E402
_spec = _ilu.spec_from_file_location("feed_fixtures", os.path.join(ROOT, "tests", "test_social_feed.py"))
T = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(T)

GOOD = "correct-horse-battery"


def _db(n=4, profiles=True):
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    ids = []
    for i in range(n):
        _, out = A.create_user(conn, f"u{i}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        if profiles:
            SF.profile_set(conn, out["id"], f"user{i}", "")
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    return conn, ids


def _post(conn, uid, d, legs=(T.PROP_FREE, T.GAME), caption=""):
    return SF.create_post(conn, uid, "nfl", "2026-10-11", [T._leg(r) for r in legs], caption, data_dir=d)


def _graded(conn, uid, results, days_ago=1):
    """Graded parlays straight into the table — the grading itself has
    its own tests in test_social_full.py."""
    now = time.time()
    for i, (res, u) in enumerate(results):
        conn.execute("INSERT INTO feed_posts (user_id, sport, date, legs, caption, created_at, kind, result, units) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (uid, "nfl", "2026-10-01", "[]", "", now - days_ago * 86400 - i, "parlay", res, u))
    conn.commit()


# --- one profile for the whole site ------------------------------------------

def test_friends_see_the_profile_name_not_the_email_or_an_old_streak_name():
    conn, (a, b, *_) = _db(profiles=False)
    STK.ensure_tables(conn)
    STK.set_name(conn, a, "OldStreakName")
    assert SOC.display_name(conn, a) == "OldStreakName"
    assert SOC.display_name(conn, b) == "u1"                  # the email's local part, as before
    SF.profile_set(conn, a, "EthanLocks", "", name="Ethan L")
    assert SOC.display_name(conn, a) == "Ethan L"
    SF.profile_set(conn, a, "EthanLocks", "", name="")
    assert SOC.display_name(conn, a) == "EthanLocks"


def test_friend_search_finds_the_profile_and_never_the_left_behind_streak_name():
    conn, (a, b, c, _) = _db(profiles=False)
    STK.ensure_tables(conn)
    STK.set_name(conn, b, "Gridiron Greg")
    STK.set_name(conn, c, "Casey streak")
    SF.profile_set(conn, b, "SharpTony", "", name="Tony")
    hits = SOC.find_users(conn, a, "tony")
    assert [h["handle"] for h in hits] == ["SharpTony"] and hits[0]["name"] == "Tony"
    assert SOC.find_users(conn, a, "gridiron") == []           # the old name no longer finds him
    assert [h["name"] for h in SOC.find_users(conn, a, "casey")] == ["Casey streak"]
    assert SOC.find_users(conn, a, "u1@") == []                 # emails never match
    assert SF.profile_set(conn, a, "user0", "")[0] == 200
    SF.toggle_block(conn, b, "user0")
    assert SOC.find_users(conn, a, "tony") == []                # a block hides both ways


def test_the_streak_board_shows_the_profile_name_and_keeps_the_opt_in():
    conn, (a, b, *_) = _db(profiles=False)
    STK.ensure_tables(conn)
    STK.set_name(conn, a, "streaker")
    conn.execute("UPDATE streak_state SET current=3, best=4 WHERE user_id=?", (a,))
    conn.execute("INSERT INTO streak_state (user_id, name, current, best) VALUES (?, '', 9, 9)", (b,))
    conn.commit()
    SF.profile_set(conn, b, "PrivatePlayer", "")
    SF.profile_set(conn, a, "EthanLocks", "", name="Ethan L")
    rows = STK.leaders(conn)
    # b has a profile but never opted in: still private.
    assert [(r["name"], r["handle"]) for r in rows] == [("Ethan L", "EthanLocks")]


def test_the_account_endpoint_and_the_feed_share_one_row():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    acct = src[src.index("def _account_get"):]
    acct = acct[:acct.index('if path == "data":')]
    assert 'out["profile"] = SF.profile_of(conn, who["id"])' in acct
    assert "suggest_handle" in acct


def test_a_starting_handle_comes_from_the_streak_name_when_it_is_free_and_legal():
    conn, (a, b, c, _) = _db(profiles=False)
    STK.ensure_tables(conn)
    STK.set_name(conn, a, "Ethan Locks")
    STK.set_name(conn, b, "QellysFan")                        # a site name: never suggested
    assert SF.suggest_handle(conn, a) == "Ethan_Locks"
    assert SF.suggest_handle(conn, b) == ""
    SF.profile_set(conn, c, "Ethan_Locks", "")
    assert SF.suggest_handle(conn, a) == ""                   # taken


# --- verified and the site's own names -----------------------------------------

def test_site_names_are_reserved_until_the_owner_claims_one():
    conn, (a, b, *_) = _db()
    for bad in ("Qellys_Book", "TheQellysGuy", "zeno_picks", "Official_Bets", "admin"):
        assert SF.profile_set(conn, a, bad, "")[0] == 400, bad
    assert SF.profile_set(conn, a, "user0", "", name="Qellys Official")[0] == 400
    code, out = SF.claim(conn, "u1@example.com", "Qellys_Book", name="Qellys Book")
    assert code == 200 and out["profile"]["verified"]
    p = SF.profile_of(conn, b)
    assert p["handle"] == "Qellys_Book" and p["verified"]
    # A verified handle stays put — the badge must not move to a new name.
    assert SF.profile_set(conn, b, "SomethingElse", "")[0] == 403
    assert SF.profile_set(conn, b, None, "Bio is fine")[0] == 200
    assert SF.claim(conn, "nobody@example.com", "Qellys_Two")[0] == 404


def test_the_official_account_wears_the_site_mark_and_others_never_do():
    conn, (a, b, *_) = _db()
    SF.claim(conn, "u1@example.com", "Qellys_Book")
    SF.create_talk(conn, b, "nfl", "", "Slate is up")
    SF.create_talk(conn, a, "nfl", "", "Hello")
    SF.set_verified(conn, "user0", True)                       # verified, but not the site
    posts = {p["handle"]: p for p in SF.feed(conn, a)["posts"]}
    assert posts["Qellys_Book"]["verified"] and posts["Qellys_Book"]["official"]
    assert posts["user0"]["verified"] and not posts["user0"]["official"]


def test_only_the_owner_hands_out_the_badge():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def _feed_post"):src.index("def _social_get")]
    assert 'if path in ("hide", "verify") and self._owner_refused()' in body


# --- the composer: words, tags, polls, links -----------------------------------

def test_tags_are_read_from_the_words_capped_and_filterable():
    conn, (a, b, *_) = _db()
    SF.create_talk(conn, a, "nfl", "", "Lions cover #NFL #Week6 #lions #nfl #a1 #b2 #c3 #d4")
    SF.create_talk(conn, b, "nba", "", "Opening night #NBA")
    SF.create_talk(conn, b, "nfl", "", "colour#notatag and &#39; are not tags")
    p = SF.feed(conn, a, tag="nfl")["posts"]
    assert len(p) == 1 and p[0]["tags"][:3] == ["NFL", "Week6", "lions"] and len(p[0]["tags"]) == 5
    assert len(SF.feed(conn, a, tag="#WEEK6")["posts"]) == 1
    assert SF.feed(conn, a, tag="notatag")["posts"] == []
    tags = {t["tag"].lower(): t["posts"] for t in SF.trending_tags(conn, a)}
    assert tags["nfl"] == 1 and tags["nba"] == 1


def test_editing_a_post_re_reads_its_tags():
    conn, (a, *_) = _db()
    _, out = SF.create_talk(conn, a, "nfl", "", "Early lean #Under")
    SF.edit_post(conn, a, out["id"], body="Changed my mind #Over")
    assert SF.feed(conn, a, tag="under")["posts"] == []
    assert len(SF.feed(conn, a, tag="over")["posts"]) == 1


def test_a_poll_takes_one_final_vote_each_and_closes():
    conn, (a, b, c, _) = _db()
    assert SF.create_talk(conn, a, "nfl", "", "Who wins?", poll=["DET"])[0] == 400
    assert SF.create_talk(conn, a, "nfl", "", "Who wins?", poll=["DET", "det"])[0] == 400
    assert SF.create_talk(conn, a, "nfl", "", "Who wins?", poll=["A", "B", "C", "D", "E"])[0] == 400
    code, out = SF.create_talk(conn, a, "nfl", "", "Who wins?", poll=["DET", "GB", "Tie"])
    assert code == 200
    pid = out["id"]
    assert SF.vote(conn, b, pid, 0)[0] == 200
    SF.vote(conn, b, pid, 1)                                  # a second tap changes nothing
    assert SF.vote(conn, c, pid, 1)[0] == 200
    assert SF.vote(conn, c, pid, 7)[0] == 400
    poll = SF.feed(conn, b)["posts"][0]["poll"]
    assert poll["counts"] == [1, 1, 0] and poll["mine"] == 0 and poll["total"] == 2
    conn.execute("UPDATE feed_polls SET closes_at=? WHERE post_id=?", (time.time() - 1, pid))
    conn.commit()
    assert SF.vote(conn, a, pid, 2)[0] == 409
    assert SF.feed(conn, a)["posts"][0]["poll"]["closed"]


def test_links_are_https_only_and_not_for_day_old_accounts():
    conn, (a, *_) = _db()
    assert SF.create_talk(conn, a, "nfl", "", "read", link="http://example.com/x")[0] == 400
    assert SF.create_talk(conn, a, "nfl", "", "read", link="javascript:alert(1)")[0] == 400
    code, out = SF.create_talk(conn, a, "nfl", "", "read this", link="https://www.espn.com/nfl/story")
    assert code == 200
    p = SF.feed(conn, a)["posts"][0]
    assert p["link"] == "https://www.espn.com/nfl/story" and p["domain"] == "espn.com"
    _, out = A.create_user(conn, "new@example.com", GOOD, confirmed=True)
    SF.profile_set(conn, out["id"], "newbie", "")
    assert SF.create_talk(conn, out["id"], "nfl", "", "buy my picks", link="https://spam.example")[0] == 403
    assert SF.create_talk(conn, out["id"], "nfl", "", "just talking")[0] == 200


def test_ufc_and_soccer_talk_filter_like_any_sport():
    conn, (a, *_) = _db()
    SF.create_talk(conn, a, "ufc", "", "Main event under")
    SF.create_talk(conn, a, "soccer", "", "Arsenal BTTS")
    SF.create_talk(conn, a, "nfl", "", "Lions")
    assert [p["body"] for p in SF.feed(conn, a, sport="ufc")["posts"]] == ["Main event under"]
    assert [p["body"] for p in SF.feed(conn, a, sport="soccer")["posts"]] == ["Arsenal BTTS"]


def test_latest_is_newest_first_and_for_you_never_runs_dry():
    conn, (a, b, *_) = _db()
    _, old = SF.create_talk(conn, a, "nfl", "", "Old but loved")
    for who in (b,):
        SF.toggle_like(conn, who, old["id"])
    conn.execute("UPDATE feed_posts SET created_at=created_at-? WHERE id=?", (20 * 86400, old["id"]))
    conn.commit()
    SF.create_talk(conn, b, "nfl", "", "Fresh")
    assert [p["body"] for p in SF.feed(conn, a, order="latest")["posts"]] == ["Fresh", "Old but loved"]
    # A quiet fortnight must not leave For You empty.
    assert len(SF.feed(conn, a, order="hot")["posts"]) == 2


# --- the parlay picker ------------------------------------------------------------

def test_the_parlay_picker_searches_todays_board_and_keeps_paid_rows_paid():
    d = T._board_dir()
    free = SF.leg_search("nfl", "", entitled=False, data_dir=d)
    names = {l.get("player") or l.get("matchup") for l in free["legs"]}
    assert "Amon-Ra St. Brown" in names and "Jahmyr Gibbs" not in names and "Nobody" not in names
    paid = SF.leg_search("nfl", "gibbs", entitled=True, data_dir=d)
    assert [l["player"] for l in paid["legs"]] == ["Jahmyr Gibbs"]
    assert all("links" not in l for l in paid["legs"])        # Tail hands out links, nothing else
    assert SF.leg_search("nfl", "st brown", entitled=False, data_dir=d)["legs"][0]["odds"] == -115
    assert SF.leg_search("xfl", "", entitled=True, data_dir=d)["legs"] == []


def test_a_parlay_from_the_composer_dates_itself_from_its_legs():
    conn, (a, *_) = _db()
    d = T._board_dir()
    row = dict(T.PROP_FREE, game_date="2026-10-11", kickoff="2099-10-11T17:00:00Z")
    for f in (d / "recommendations.json", d / "built" / "recommendations.json"):
        doc = json.loads(f.read_text())
        doc["recommendations"] = [row if r["player"] == row["player"] else r for r in doc["recommendations"]]
        f.write_text(json.dumps(doc))
    code, out = SF.create_post(conn, a, "nfl", "", [T._leg(row)], "from the composer", data_dir=d)
    assert code == 200
    got = conn.execute("SELECT date FROM feed_posts WHERE id=?", (out["id"],)).fetchone()
    assert got["date"] == "2026-10-11"                         # what grading reads the journal by


# --- the rail ---------------------------------------------------------------------

def test_trending_picks_count_people_and_lock_paid_legs():
    conn, (a, b, c, e) = _db()
    d = T._board_dir()
    _, p1 = _post(conn, a, d, legs=(T.PROP_FREE, T.GAME))
    _, p2 = _post(conn, b, d, legs=(T.PROP_FREE, T.PROP_PAID))
    SF.tail(conn, c, p1["id"], entitled=True, data_dir=d)
    SF.tail(conn, c, p2["id"], entitled=True, data_dir=d)    # c twice: still one person
    SF.create_talk(conn, e, "nfl", "", "just talk")           # talk is not a pick
    out = SF.trending_picks(conn, e, entitled=False)
    assert out["active"] == 3
    top = out["picks"][0]
    assert top["leg"]["player"] == "Amon-Ra St. Brown" and top["people"] == 3 and top["pct"] == 100
    gibbs = [p for p in out["picks"] if p["leg"].get("player") == "Jahmyr Gibbs"][0]
    assert gibbs["leg"]["locked"] and "line" not in gibbs["leg"] and gibbs["people"] == 2
    assert SF.trending_picks(conn, e, entitled=True)["picks"][1]["leg"].get("line") is not None


def test_a_leg_whose_game_began_leaves_trending():
    conn, (a, *_) = _db()
    d = T._board_dir()
    _post(conn, a, d, legs=(T.PROP_FREE,))
    row = conn.execute("SELECT id, legs FROM feed_posts").fetchone()
    legs = json.loads(row["legs"])
    legs[0]["kickoff"] = "2020-01-01T17:00:00Z"
    conn.execute("UPDATE feed_posts SET legs=? WHERE id=?", (json.dumps(legs), row["id"]))
    conn.commit()
    assert SF.trending_picks(conn, a)["picks"] == []


def test_top_bettors_rank_win_rate_units_and_followers_over_a_window():
    conn, (a, b, c, e) = _db()
    _graded(conn, a, [("won", 1.0)] * 4 + [("lost", -1.0)] + [("push", 0)])     # 80% (push left out)
    _graded(conn, b, [("won", 3.0)] * 3 + [("lost", -1.0)] * 2)                 # 60%, +7u
    _graded(conn, c, [("won", 1.0)] * 4)                                        # 4 graded: not yet
    win = SF.leaders(conn, e, 30, "win")
    assert [(x["handle"], x["value"]) for x in win["top"]] == [("user0", 80), ("user1", 60)]
    units = SF.leaders(conn, e, 30, "units")
    assert [x["handle"] for x in units["top"]] == ["user1", "user0"] and units["top"][0]["units"] == 7.0
    assert SF.leaders(conn, e, 7, "win")["top"][0]["handle"] == "user0"
    conn.execute("UPDATE feed_posts SET created_at=created_at-? WHERE user_id=?", (40 * 86400, a))
    conn.commit()
    assert [x["handle"] for x in SF.leaders(conn, e, 30, "win")["top"]] == ["user1"]
    assert [x["handle"] for x in SF.leaders(conn, e, None, "win")["top"]] == ["user0", "user1"]
    for who in (b, c, e):
        SF.toggle_follow(conn, who, "user0")
    SF.toggle_follow(conn, a, "user1")
    fol = SF.leaders(conn, e, 7, "followers")
    assert [(x["handle"], x["value"]) for x in fol["top"]] == [("user0", 3), ("user1", 1)]


def test_community_stats_are_counted_and_the_win_rate_waits_for_ten():
    conn, (a, b, *_) = _db()
    SF.create_talk(conn, a, "nfl", "", "hello")
    _graded(conn, b, [("won", 1.0)] * 6 + [("lost", -1.0)] * 3)
    s = SF.community_stats(conn)
    assert s["members"] == 4 and s["posts"] == 10 and s["graded"] == 9 and s["win_rate"] is None
    _graded(conn, b, [("won", 1.0)])
    assert SF.community_stats(conn)["win_rate"] == 70


# --- the account's own rows -----------------------------------------------------

def test_delete_and_export_cover_tags_polls_and_votes():
    conn, (a, b, *_) = _db()
    _, out = SF.create_talk(conn, a, "nfl", "", "Pick one #poll", poll=["Yes", "No"])
    SF.vote(conn, b, out["id"], 1)
    _, mine = SF.create_talk(conn, b, "nfl", "", "My own #take", poll=["A", "B"])
    SF.vote(conn, a, mine["id"], 0)
    exp = A.export_user(conn, b)
    assert exp["public_feed"]["votes"] == [{"post_id": out["id"], "option": 1}]
    A.delete_user(conn, b)
    assert conn.execute("SELECT COUNT(*) FROM feed_votes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM feed_polls").fetchone()[0] == 1   # a's poll stays
    assert {r[0] for r in conn.execute("SELECT tag FROM feed_tags")} == {"poll"}
    SF.delete(conn, a, "post", out["id"])
    for t in ("feed_tags", "feed_polls", "feed_votes"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    assert set(("feed_tags", "feed_polls", "feed_votes")) <= set(SF.FEED_TABLES)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            n += 1
    print(f"\n{n} tests passed.")
