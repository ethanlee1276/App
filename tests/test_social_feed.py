"""The public feed: posts, the Tail button, likes, comments, bios, bad words.

Ethan, 2026-10-06: a social page where people post parlays, a whale-tail
Tail button with a counter that opens the parlay at the books, likes,
comments, a bio, and bad words handled.

What this file pins: legs are read off the SERVER's board (never the
client's numbers), the paywall holds on paid legs, the tail counter
counts people not taps, slurs are refused and swearing is masked unless
the reader asks, and an account's feed rows die with it.

Run directly: `python3 tests/test_social_feed.py`
"""

import codecs
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import profanity as P                            # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
FD = "https://sportsbook.fanduel.com/addToBetslip"

PROP_FREE = {"player": "Amon-Ra St. Brown", "market": "rec_yds", "market_label": "Receiving yards",
             "side": "OVER", "line": 64.5, "odds": -115, "book": "FanDuel", "team": "DET",
             "opponent": "GB", "bet_links": [["FanDuel", f"{FD}?marketId[0]=1.1&selectionId[0]=11", -115],
                                             ["DraftKings", "https://sportsbook.draftkings.com/event/9?outcomes=0A", -110]]}
PROP_PAID = {"player": "Jahmyr Gibbs", "market": "rush_yds", "market_label": "Rushing yards",
             "side": "OVER", "line": 71.5, "odds": -110, "book": "FanDuel", "team": "DET",
             "opponent": "GB", "bet_links": [["FanDuel", f"{FD}?marketId[0]=2.2&selectionId[0]=22", -110]]}
GAME = {"kind": "game", "bet_type": "spread", "market": "spread", "team": "DET", "side": "DET",
        "line": -3, "odds": -108, "book": "FanDuel", "home": "DET", "away": "GB",
        "bet_links": [["FanDuel", f"{FD}?marketId[0]=3.3&selectionId[0]=33", -108]]}
PROXY = {"player": "Nobody", "market": "rec_yds", "side": "OVER", "line": 9.5, "odds": -110,
         "book": "proxy"}


def _board_dir():
    d = Path(tempfile.mkdtemp())
    (d / "built").mkdir()
    full = {"recommendations": [PROP_FREE, PROP_PAID, PROXY], "game_bets": [GAME]}
    public = {"recommendations": [PROP_FREE], "game_bets": [GAME]}
    (d / "built" / "recommendations.json").write_text(json.dumps(full))
    (d / "recommendations.json").write_text(json.dumps(public))
    return d


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew"):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    # Two days old: the day-one cap has its own test below.
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    return conn, ids


def _leg(r):
    from engine.socialfeed import game_id
    if r.get("kind") == "game":
        return {"gid": game_id(r)}
    return {k: r[k] for k in ("player", "market", "side", "line")}


def _post(conn, uid, d, legs=(PROP_FREE, GAME), caption="lock it in"):
    SF.profile_set(conn, uid, f"user{uid}", "")
    return SF.create_post(conn, uid, "nfl", "2026-10-11", [_leg(r) for r in legs], caption, data_dir=d)


# --- legs come from the board, never from the client -------------------------

def test_a_leg_is_rebuilt_from_the_board_and_ignores_client_numbers():
    conn, (a, *_) = _db()
    d = _board_dir()
    forged = dict(_leg(PROP_FREE), odds=+900, book="Scam", url="https://evil.example")
    SF.profile_set(conn, a, "ethan", "")
    code, out = SF.create_post(conn, a, "nfl", "", [forged, _leg(GAME)], "", data_dir=d)
    assert code == 200, out
    legs = json.loads(conn.execute("SELECT legs FROM feed_posts").fetchone()["legs"])
    assert legs[0]["odds"] == -115 and legs[0]["book"] == "FanDuel"
    assert "evil" not in json.dumps(legs)


def test_a_leg_not_on_the_board_or_at_a_proxy_price_is_refused():
    conn, (a, *_) = _db()
    d = _board_dir()
    SF.profile_set(conn, a, "ethan", "")
    moved = dict(_leg(PROP_FREE), line=70.5)
    code, out = SF.create_post(conn, a, "nfl", "", [moved], "", data_dir=d)
    assert code == 400 and "not on today" in out["error"]
    code, out = SF.create_post(conn, a, "nfl", "", [_leg(PROXY)], "", data_dir=d)
    assert code == 400 and "real book price" in out["error"]


def test_a_post_needs_a_handle_and_no_model_numbers_are_stored():
    conn, (a, *_) = _db()
    d = _board_dir()
    code, out = SF.create_post(conn, a, "nfl", "", [_leg(PROP_FREE)], "", data_dir=d)
    assert code == 409 and out.get("need_handle")
    code, out = _post(conn, a, d)
    assert code == 200, out
    blob = conn.execute("SELECT legs FROM feed_posts").fetchone()["legs"]
    for word in ("prob", "edge", "proj", "tier", "ev\""):
        assert word not in blob, word


def test_the_game_leg_id_matches_the_pages_gameBetId():
    """app.js: ["game", away@home, market||bet_type, side||team, line] — a
    whole-number line prints without '.0' there, so it must here too."""
    assert SF.game_id(GAME) == "game|GB@DET|spread|DET|-3"
    assert SF.game_id(dict(GAME, line=2.5)) == "game|GB@DET|spread|DET|2.5"


# --- the paywall --------------------------------------------------------------

def test_a_paid_leg_shows_only_its_identity_to_an_unentitled_reader():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    code, out = _post(conn, a, d, legs=(PROP_FREE, PROP_PAID))
    assert code == 200, out
    locked = SF.feed(conn, b, entitled=False)["posts"][0]
    paid = locked["legs"][1]
    assert paid["locked"] and paid["player"] == "Jahmyr Gibbs"
    for k in ("side", "line", "odds", "book", "label"):
        assert k not in paid, k
    assert locked["combined"] is None and locked["locked"]
    full = SF.feed(conn, b, entitled=True)["posts"][0]
    assert full["legs"][1]["side"] == "OVER" and full["combined"] is not None


def test_an_unentitled_reader_cannot_tail_a_post_with_paid_legs():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d, legs=(PROP_FREE, PROP_PAID))
    code, res = SF.tail(conn, b, out["id"], entitled=False, data_dir=d)
    assert code == 402 and res.get("locked")
    assert conn.execute("SELECT COUNT(*) FROM feed_tails").fetchone()[0] == 0


def test_the_feed_never_hands_out_links_only_tail_does():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    _post(conn, a, d)
    assert "https://" not in json.dumps(SF.feed(conn, b, entitled=True))


# --- the tail -----------------------------------------------------------------

def test_tail_counts_people_not_taps_and_builds_one_fanduel_slip():
    conn, (a, b, c, _) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d)
    for who in (b, b, c):
        code, res = SF.tail(conn, who, out["id"], entitled=True, data_dir=d)
        assert code == 200, res
    assert res["tails"] == 2
    fd = next(x for x in res["books"] if x["book"] == "FanDuel")
    assert fd["have"] == 2 and fd["combined"]
    assert "marketId[0]=1.1" in fd["combined"] and "marketId[1]=3.3" in fd["combined"]
    assert "selectionId[1]=33" in fd["combined"]
    dk = next(x for x in res["books"] if x["book"] == "DraftKings")
    assert dk["have"] == 1 and not dk["combined"] and dk["legs"][1] is None
    assert res["books"][0]["book"] == "FanDuel"            # complete books first


def test_links_that_cannot_be_shown_to_combine_are_not_combined():
    dk = ["https://sportsbook.draftkings.com/event/9?outcomes=0A",
          "https://sportsbook.draftkings.com/event/9?outcomes=0B"]
    assert SF.combine_links(dk) == ""
    mixed = [f"{FD}?marketId[0]=1&selectionId[0]=1", "https://other.example/x?marketId[0]=2"]
    assert SF.combine_links(mixed) == ""
    assert SF.combine_links([dk[0]]) == dk[0]


# --- likes, comments, deletes, reports ---------------------------------------

def test_likes_toggle_and_comments_need_a_handle():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d)
    assert SF.toggle_like(conn, b, out["id"])[1] == {"likes": 1, "liked": True}
    assert SF.toggle_like(conn, b, out["id"])[1] == {"likes": 0, "liked": False}
    code, res = SF.add_comment(conn, b, out["id"], "nice")
    assert code == 409 and res.get("need_handle")
    SF.profile_set(conn, b, "sam", "Lions fan")
    assert SF.add_comment(conn, b, out["id"], "nice")[0] == 200
    code, det = SF.post_detail(conn, out["id"], a)
    assert det["post"]["comments"] == 1
    assert det["post"]["comment_list"][0]["can_delete"]     # the post's author may


def test_three_reports_hide_a_post_and_the_owner_can_restore_it():
    conn, (a, b, c, e) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d)
    for who in (b, b, c):
        SF.report(conn, who, "post", out["id"])
    assert SF.feed(conn)["posts"]                            # two people so far
    SF.report(conn, e, "post", out["id"])
    assert not SF.feed(conn)["posts"]
    assert SF.set_hidden(conn, "post", out["id"], False)[0] == 200
    assert SF.feed(conn)["posts"]


def test_only_the_author_deletes_a_post():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d)
    assert SF.delete(conn, b, "post", out["id"])[0] == 404
    assert SF.delete(conn, a, "post", out["id"])[0] == 200
    assert not SF.feed(conn)["posts"]


def test_posts_are_capped_per_day():
    conn, (a, *_) = _db()
    d = _board_dir()
    SF.profile_set(conn, a, "ethan", "")
    for i in range(SF.POSTS_PER_DAY):
        code, out = SF.create_post(conn, a, "nfl", "", [_leg(PROP_FREE)], f"take {i}", data_dir=d)
        conn.execute("UPDATE feed_posts SET legs=legs||' ' WHERE id=?", (out["id"],))
    code, out = SF.create_post(conn, a, "nfl", "", [_leg(GAME)], "one more", data_dir=d)
    assert code == 429


# --- handles, bios, bad words ------------------------------------------------

def test_handles_are_unique_clean_and_not_reserved():
    conn, (a, b, *_) = _db()
    assert SF.profile_set(conn, a, "Ethan_1", "")[0] == 200
    assert SF.profile_set(conn, b, "ethan_1", "")[0] == 409
    assert SF.profile_set(conn, b, "qellys", "")[0] == 400
    assert SF.profile_set(conn, b, "x", "")[0] == 400
    assert SF.profile_set(conn, b, "big_" + codecs.decode("fuvg", "rot13"), "")[0] == 400
    assert SF.profile_set(conn, b, "assassin", "")[0] == 200


def test_slurs_are_refused_everywhere_text_is_written():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    slur = codecs.decode("ergneq", "rot13")
    assert SF.profile_set(conn, a, "ethan", f"you {slur}")[0] == 400
    SF.profile_set(conn, a, "ethan", "")
    assert SF.create_post(conn, a, "nfl", "", [_leg(PROP_FREE)], f"{slur}s", data_dir=d)[0] == 400
    _, out = _post(conn, a, d)
    SF.profile_set(conn, b, "sam", "")
    assert SF.add_comment(conn, b, out["id"], f"what a {slur}")[0] == 400


def test_swearing_is_masked_unless_the_reader_asks():
    conn, (a, *_) = _db()
    d = _board_dir()
    word = codecs.decode("shpxvat", "rot13")
    _post(conn, a, d, caption=f"{word} lock")
    masked = SF.feed(conn)["posts"][0]
    assert masked["caption"].startswith("f" + "*" * (len(word) - 1)) and masked["strong"]
    raw = SF.feed(conn, strong=True)["posts"][0]
    assert raw["caption"] == f"{word} lock"


def test_the_filter_leaves_ordinary_words_alone():
    for w in ("class", "assess", "Scunthorpe", "Dickens", "pass", "assassin", "spicy", "cocky",
              "Bass", "raccoon", "as", "hello"):
        assert P.mask(w) == w, w
    assert P.mask("sh1t") == "s***" and P.mask("a$$") == "a**"


# --- the account owns its rows ------------------------------------------------

def test_deleting_an_account_removes_its_posts_and_marks():
    conn, (a, b, *_) = _db()
    d = _board_dir()
    _, out = _post(conn, a, d)
    SF.toggle_like(conn, b, out["id"])
    SF.tail(conn, b, out["id"], entitled=True, data_dir=d)
    exp = A.export_user(conn, a)
    assert exp["public_feed"]["profile"]["handle"] == f"user{a}"
    assert exp["public_feed"]["posts"][0]["caption"] == "lock it in"
    A.delete_user(conn, a)
    for t in ("feed_posts", "feed_likes", "feed_tails", "feed_profiles"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t


def test_the_server_routes_exist_and_hide_is_owner_only():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"/api/feed/"' in src and "def _feed_get" in src and "def _feed_post" in src
    body = src[src.index("def _feed_post"):src.index("def _social_get")]
    # Hiding a post and handing out the verified badge are the owner's
    # alone: the owner token, or (Ethan, 2026-10-07, "make my profile like
    # the god profile") the founder's own signed-in session — the account
    # only the box command engine/socialfeed.crown marks. Checked before
    # either runs; anyone else is refused.
    assert 'if path in ("hide", "verify") and not self._founder_or_owner(conn):' in body
    assert body.index("_founder_or_owner(conn)") < body.index("SF.set_hidden(") < body.index("SF.set_verified(")
    door = src[src.index("def _founder_or_owner"):src.index("def _owner_refused")]
    assert "return not self._owner_refused()" in door and "SF.is_founder(conn, who[\"id\"])" in door
    assert '"founder only"' in door
    reads = src[src.index("def _feed_get"):src.index("def _feed_post")]
    rep = reads[reads.index('if path == "reported":'):]
    assert rep.index("_founder_or_owner(conn)") < rep.index("SF.reported(conn)")
    # The client's leg is reduced to its identity before the engine sees it.
    assert '"odds"' not in body.split('if path == "post":')[1].split("elif")[0]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
