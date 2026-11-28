"""Every game has a chat, and every play has a thread (engine/gamechat).

Ethan, 2026-10-25: "it has like live chats on each game for the
play-by-plays ... make it where we have like a live chat for each game so
users can talk about their props". The app is Real: each play carries a
reaction counter and its own comment thread, and the game a room around
them.

What this file pins: a room is a real game's key, a handle comes before
the first word, slurs are refused and swearing masked for readers who did
not ask, the bet chip is the writer's own words with nothing that could
be a link, the poll is cheap (only what moved since the last ask), a face
taken back still reports the change, three reports hide a message, a
block hides both ways, the vote closes at the final, and the server
routes exist behind the account rules.

Run directly: `python3 tests/test_every_game_has_a_chat.py`
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
from engine import gamechat as GC                            # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew", "kai"):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    for uid, h in zip(ids[:4], ("ethan", "sam", "casey", "drew")):
        SF.profile_set(conn, uid, h, "")
    return conn, ids


def _live_dir(state="live"):
    d = Path(tempfile.mkdtemp())
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401873017", "home": "ATL", "away": "SF", "live": {"state": state}}]}))
    return d


def test_a_room_is_a_real_game_key():
    conn, ids = _db()
    for bad in ("", "nfl", "nfl_", "xfl_123", "nfl_12a", "nfl_123;drop", "../nfl_1"):
        code, _ = GC.send(conn, ids[0], bad, "hi", now=1000.0)
        assert code == 400, bad
    assert GC.room_ok("mlb_778899") and GC.room_ok("wnba_401") and not GC.room_ok("ufc_1")


def test_a_handle_comes_before_the_first_word():
    conn, ids = _db()
    code, out = GC.send(conn, ids[4], ROOM, "first!", now=1000.0)
    assert code == 409 and out.get("need_handle"), out


def test_send_read_and_the_poll_only_carries_what_is_new():
    conn, ids = _db()
    assert GC.send(conn, ids[0], ROOM, "Purdy to Kittle!", now=1000.0)[0] == 200
    assert GC.send(conn, ids[1], ROOM, "that drive is cooking", play="4018730171234", now=1001.0)[0] == 200
    code, v = GC.room_view(conn, ROOM, ids[2], now=1002.0)
    assert code == 200 and [m["body"] for m in v["messages"]] == ["Purdy to Kittle!", "that drive is cooking"]
    assert v["messages"][1]["play"] == "4018730171234"
    assert v["messages"][0]["by"]["handle"] == "ethan" and not v["messages"][0]["own"]
    assert v["threads"] == {"4018730171234": 1}
    last = v["messages"][-1]["id"]
    # The next ask: nothing new, nothing moved.
    code, v2 = GC.room_view(conn, ROOM, ids[2], after=last, since=v["t"] + 2, now=1010.0)
    assert v2["messages"] == [] and v2["plays"] == {} and v2["reacts"] == {} and v2["threads"] == {}


def test_slurs_are_refused_and_swearing_is_masked_unless_asked():
    conn, ids = _db()
    slur = codecs.decode("snttbg", "rot13")
    code, out = GC.send(conn, ids[0], ROOM, f"you {slur}", now=1000.0)
    assert code == 400 and "slur" in out["error"]
    swear = codecs.decode("shpx", "rot13")
    assert GC.send(conn, ids[0], ROOM, f"what the {swear}", now=1010.0)[0] == 200
    _, v = GC.room_view(conn, ROOM, ids[1], now=1011.0)
    assert swear not in v["messages"][0]["body"] and "f***" in v["messages"][0]["body"]
    _, v = GC.room_view(conn, ROOM, ids[1], strong=True, now=1011.0)
    assert swear in v["messages"][0]["body"]


def test_the_bet_chip_is_the_writers_own_words_and_never_a_link():
    chip = GC.clean_bet({"player": "Christian McCaffrey", "market": "Rush yds", "side": "OVER",
                         "line": "79.5", "odds": "-115", "book": "FanDuel", "url": "https://evil.example",
                         "probability": 0.71})
    assert chip == {"player": "Christian McCaffrey", "market": "Rush yds", "side": "OVER",
                    "line": 79.5, "odds": -115, "book": "FanDuel"}, chip
    assert GC.clean_bet({"player": "go to www.scam.com", "market": "x"}) == {"market": "x"}
    assert GC.clean_bet({"odds": -110}) is None, "a chip names somebody or something"
    assert GC.clean_bet({"player": "A", "odds": 50})["player"] == "A" and "odds" not in GC.clean_bet({"player": "A", "odds": 50})
    conn, ids = _db()
    assert GC.send(conn, ids[0], ROOM, "", bet={"player": "Bijan Robinson", "market": "Anytime TD"}, now=1000.0)[0] == 200
    _, v = GC.room_view(conn, ROOM, None, now=1001.0)
    assert v["messages"][0]["bet"] == {"player": "Bijan Robinson", "market": "Anytime TD"}


def test_the_rate_caps_hold():
    import time
    conn, ids = _db()
    # On the real clock: the accounts were made two days ago by it, and a
    # stamp from 1970 would read every one of them as brand new.
    t0 = time.time()
    assert GC.send(conn, ids[0], ROOM, "one", now=t0)[0] == 200
    assert GC.send(conn, ids[0], ROOM, "two", now=t0 + 1)[0] == 429, "one message every few seconds"
    t = t0 + 4
    for i in range(GC.MSGS_PER_MIN - 1):
        assert GC.send(conn, ids[0], ROOM, f"m{i}", now=t)[0] == 200
        t += GC.MSG_GAP_S
    assert GC.send(conn, ids[0], ROOM, "too many", now=t)[0] == 429
    # A new account's minute is shorter.
    conn.execute("UPDATE users SET created_at=? WHERE id=?", (t, ids[1]))
    conn.commit()
    for i in range(GC.NEW_MSGS_PER_MIN):
        assert GC.send(conn, ids[1], ROOM, f"n{i}", now=t + 1 + i * GC.MSG_GAP_S)[0] == 200
    assert GC.send(conn, ids[1], ROOM, "more", now=t + 1 + GC.NEW_MSGS_PER_MIN * GC.MSG_GAP_S)[0] == 429


def test_faces_on_messages_and_plays_toggle_and_a_taken_back_face_still_reports():
    conn, ids = _db()
    _, out = GC.send(conn, ids[0], ROOM, "TOUCHDOWN", now=1000.0)
    mid = out["id"]
    assert GC.react(conn, ids[1], mid, "fire", now=1001.0) == (200, {"ok": True, "mine": "fire"})
    assert GC.react(conn, ids[2], mid, "fire", now=1001.0)[0] == 200
    assert GC.react(conn, ids[1], mid, "nope", now=1001.0)[0] == 400
    assert GC.react_play(conn, ids[1], ROOM, "p77", "wow", now=1002.0)[1]["mine"] == "wow"
    assert GC.react_play(conn, ids[2], ROOM, "p77", "wow", now=1002.0)[0] == 200
    _, v = GC.room_view(conn, ROOM, ids[1], now=1003.0)
    assert v["messages"][0]["reacts"] == {"fire": 2} and v["messages"][0]["mine"] == "fire"
    assert v["plays"] == {"p77": {"wow": 2}} and v["mine_plays"] == {"p77": "wow"}
    t = v["t"]
    # Both take their faces back: the next poll says so, at zero.
    assert GC.react(conn, ids[1], mid, "fire", now=1010.0)[1]["mine"] == ""
    assert GC.react(conn, ids[2], mid, "fire", now=1010.0)[1]["mine"] == ""
    GC.react_play(conn, ids[1], ROOM, "p77", "wow", now=1010.0)
    GC.react_play(conn, ids[2], ROOM, "p77", "wow", now=1010.0)
    _, v2 = GC.room_view(conn, ROOM, ids[1], after=mid, since=t + 2, now=1011.0)
    assert v2["reacts"] == {str(mid): {}}, v2["reacts"]
    assert v2["plays"] == {"p77": {}}, v2["plays"]


def test_three_reports_hide_a_message_and_the_founder_can_restore_it():
    conn, ids = _db()
    _, out = GC.send(conn, ids[0], ROOM, "buy my picks at scam dot com", now=1000.0)
    mid = out["id"]
    assert GC.report(conn, ids[0], mid)[0] == 400, "not your own"
    for uid in ids[1:4]:
        assert GC.report(conn, uid, mid, "scam", now=1001.0)[0] == 200
    _, v = GC.room_view(conn, ROOM, None, now=1002.0)
    assert v["messages"] == []
    assert GC.reported(conn)[0]["reasons"] == ["scam"]
    assert GC.set_hidden(conn, mid, False)[0] == 200
    _, v = GC.room_view(conn, ROOM, None, now=1003.0)
    assert len(v["messages"]) == 1


def test_a_block_hides_both_ways_and_delete_is_your_own():
    conn, ids = _db()
    _, a = GC.send(conn, ids[0], ROOM, "from ethan", now=1000.0)
    GC.send(conn, ids[1], ROOM, "from sam", now=1001.0)
    SF.toggle_block(conn, ids[0], "sam")
    _, v = GC.room_view(conn, ROOM, ids[0], now=1002.0)
    assert [m["body"] for m in v["messages"]] == ["from ethan"]
    _, v = GC.room_view(conn, ROOM, ids[1], now=1002.0)
    assert [m["body"] for m in v["messages"]] == ["from sam"]
    assert GC.delete(conn, ids[1], a["id"])[0] == 404
    assert GC.delete(conn, ids[0], a["id"])[0] == 200


def test_a_reply_joins_the_thread_it_answers():
    conn, ids = _db()
    _, a = GC.send(conn, ids[0], ROOM, "what a catch", play="p9", now=1000.0)
    _, b = GC.send(conn, ids[1], ROOM, "one hand!", reply_to=a["id"], now=1001.0)
    _, v = GC.room_view(conn, ROOM, None, now=1002.0)
    assert v["messages"][1]["reply_to"] == a["id"] and v["messages"][1]["play"] == "p9"
    assert GC.send(conn, ids[1], "nfl_999", "elsewhere", reply_to=a["id"], now=1010.0)[0] == 404


def test_the_vote_is_open_until_the_final():
    conn, ids = _db()
    d = _live_dir("live")
    assert GC.vote(conn, ids[0], ROOM, "away", data_dir=d)[0] == 200
    assert GC.vote(conn, ids[1], ROOM, "home", data_dir=d)[0] == 200
    assert GC.vote(conn, ids[1], ROOM, "away", data_dir=d)[1]["mine"] == "away", "a mind may change"
    assert GC.vote(conn, ids[2], ROOM, "draw", data_dir=d)[0] == 400
    _, v = GC.room_view(conn, ROOM, ids[1], data_dir=d)
    assert v["votes"] == {"home": 0, "away": 2, "mine": "away", "open": True}
    assert GC.vote(conn, ids[2], ROOM, "home", data_dir=_live_dir("final"))[0] == 409


def test_here_now_counts_pages_and_forgets_them():
    GC._HERE.clear()
    assert GC.touch(ROOM, "u1", now=1000.0) == 1
    assert GC.touch(ROOM, "aABC", now=1001.0) == 2
    assert GC.touch(ROOM, "u1", now=1002.0) == 2
    assert GC.here(ROOM, now=1000.0 + GC.HERE_S + 5) == 0


def test_counts_for_the_live_tab():
    conn, ids = _db()
    GC.send(conn, ids[0], ROOM, "big play", play="p1", now=2000.0)
    GC.react_play(conn, ids[1], ROOM, "p1", "fire", now=2001.0)
    out = GC.counts(conn, [ROOM, "bogus", ROOM], now=2002.0)
    assert list(out) == [ROOM] and out[ROOM]["plays"] == {"p1": 2} and out[ROOM]["recent"] == 1


def test_the_server_routes_and_their_account_rules():
    src = (Path(ROOT) / "server.py").read_text()
    assert 'if parsed.path.startswith("/api/chat/"):\n            return self._chat_get(' in src
    assert 'or parsed.path.startswith("/api/chat/")' in src, "the POST body is read as JSON like the feed's"
    post = src[src.index("    def _chat_post("):src.index("    def _social_get(")]
    assert 'if path == "hide":\n                if not self._founder_or_owner(conn):' in post
    assert 'return self._send(401, b\'{"error":"Make a free account to join the chat."}\'' in post
    get = src[src.index("    def _chat_get("):src.index("    def _chat_post(")]
    assert "_HERE_SALT + self._client_ip()" in get, "an anonymous reader is a salted hash, never an address"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
