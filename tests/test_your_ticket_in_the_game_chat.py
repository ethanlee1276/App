"""Your ticket in the game's chat: a saved parlay's legs in this game, with
the box's number so far, pinned under the room's scoreboard
(engine/sliplive.room_tickets, POST /api/chat/ticket, js/chat.js).

The score's facts and nothing of the membership's: no chance, no hedge, no
cash-out. Only the legs in THIS game; a leg in another game is counted, not
drawn. The tickets are the reader's own, from My Bets on their device.

    python3 tests/test_your_ticket_in_the_game_chat.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import sliplive as SL                                  # noqa: E402


def _fast(d):
    base = Path(d)
    (base / "pbp").mkdir(parents=True)
    (base / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "55", "home": "CIN", "away": "PIT",
         "live": {"state": "live", "home_score": 17, "away_score": 14, "period": 3, "clock": "4:12"}},
        {"event_id": "66", "home": "KC", "away": "BUF", "live": {"state": "scheduled"}}]}))
    (base / "pbp" / "nfl_55.json").write_text(json.dumps({"league": "nfl", "event_id": "55", "home": "CIN", "away": "PIT",
        "players": [{"player": "Ja'Marr Chase", "team": "CIN", "stats": {"receptions": 6, "rec_yds": 58}},
                    {"player": "Joe Burrow", "team": "CIN", "stats": {"pass_yds": 301, "pass_td": 2}}]}))
    return base


TICKET = {"id": "t1", "desc": "3-leg parlay: Chase o71.5 rec yds + Burrow o274.5 pass yds + Allen o1.5 pass TD",
          "legs": [{"sport": "NFL", "player": "Ja'Marr Chase", "team": "CIN", "game": "PIT @ CIN",
                    "market": "rec_yds", "side": "OVER", "line": 71.5, "odds": -115},
                   {"sport": "nfl", "player": "Joe Burrow", "team": "CIN", "game": "PIT @ CIN",
                    "market": "pass_yds", "side": "OVER", "line": 274.5, "odds": -110},
                   {"sport": "nfl", "player": "Josh Allen", "team": "BUF", "game": "BUF @ KC",
                    "market": "pass_td", "side": "OVER", "line": 1.5, "odds": -140}]}


def test_only_this_games_legs_with_the_box_number_and_never_the_chance():
    with tempfile.TemporaryDirectory() as d:
        base = _fast(d)
        got = SL.room_tickets([TICKET], "nfl", "CIN", "PIT", fast_dir=base, now=time.time())
        assert len(got) == 1 and got[0]["of"] == 3 and got[0]["id"] == "t1"
        legs = got[0]["legs"]
        assert [l["player"] for l in legs] == ["Ja'Marr Chase", "Joe Burrow"], "Allen's game is another room"
        assert legs[0]["current"] == 58 and legs[0]["result"] is None and legs[0]["state"] == "live"
        assert legs[1]["current"] == 301 and legs[1]["result"] == "won", "an over past its number has won"
        assert all(set(l) == {"player", "market", "side", "line", "current", "result", "state"} for l in legs), \
            "no chance, no hedge, no price"
        assert SL.room_tickets([TICKET], "nfl", "KC", "BUF", fast_dir=base, now=time.time())[0]["legs"][0]["current"] is None
        assert SL.room_tickets([TICKET], "nba", "CIN", "PIT", fast_dir=base) == []
        assert SL.room_tickets(["junk", {"legs": "x"}], "nfl", "CIN", "PIT", fast_dir=base) == []


def test_the_endpoint_needs_a_real_room_and_no_account():
    import server
    with tempfile.TemporaryDirectory() as d:
        keep = server.WEB
        server.WEB = Path(d)
        (Path(d) / "data" / "pbp").mkdir(parents=True)
        (Path(d) / "data" / "pbp" / "nfl_55.json").write_text(json.dumps({"home": "CIN", "away": "PIT"}))
        out = {}
        h = object.__new__(server.Handler)
        h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
        h._rate_limited = lambda limit, bucket="read": False
        try:
            for bad in ("", "nfl_55/../x", "soccer_1", "nfl_99"):
                h._chat_ticket({"room": bad, "tickets": [TICKET]})
                assert out["code"] == 404, bad
            h._chat_ticket({"room": "nfl_55", "tickets": "nope"})
            assert out["code"] == 200 and out["body"] == {"tickets": []}
        finally:
            server.WEB = keep
    src = (ROOT / "server.py").read_text()
    post = src[src.index("    def _chat_post(self, path: str, body: dict):"):]
    assert post.index('return self._chat_ticket(body)') < post.index("who = self._account(conn)"), \
        "the tickets are the reader's own, from their device: no account needed to read the box"


def test_the_chat_draws_it_and_shares_it():
    chat = (ROOT / "web" / "js" / "chat.js").read_text()
    assert '<div class="gch-tix" hidden></div>' in chat
    head = chat[chat.index("function chatDrawHead("):chat.index("function chatTixMine(")]
    assert "chatDrawTix();" in head
    fn = chat[chat.index("async function chatDrawTix("):]
    fn = fn[:fn.index("\n}\n")]
    assert '"/api/chat/ticket"' in fn and "Date.now() - CH.tixAt < 30000" in fn
    leg = chat[chat.index("function chatTixLegHTML("):chat.index("async function chatDrawTix(")]
    assert "chEsc(l.player)" in leg and "chEsc(word" in leg
    assert 'if (act === "tikshare") {' in chat
    mine = chat[chat.index("function chatTixMine("):chat.index("function chatTixLegHTML(")]
    assert 'b.result === "pending" && b.src === "slip"' in mine


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
