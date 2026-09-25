"""Every read carries the player's touchdown chance and price.

Ethan, 2026-09-25, the Most Likely touchdown shelf beside the reads: "I'm
seeing a lot of good candidates and breakout candidates and shit like
that, but I'm not seeing these people in the anytime touchdowns ... those
players should be recommended to get touchdowns."

The box that night: 30 positive reads, four with a touchdown row anywhere
on the board, nine scorers priced on the whole board. Every quoted scorer
WAS priced (pipeline._long_shots ranks them all); only the top of the
list was published. `gamescan.stamp_touchdowns` puts each read's chance
and price on the read (``td``) from the full ranked list the scan hook
sees, `stamp_picks` adds whether the board seated him, and the card says
it — a 41% tight end reads as 41%, never as a pick.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _reads():
    return {"LAC@BUF": {"players": [
        {"player": "Dalton Kincaid", "team": "BUF", "read": "good"},
        {"player": "James Cook", "team": "BUF", "read": "good"},
        {"player": "Josh Allen", "team": "BUF", "read": "good"}]}}


def _result():
    return {"long_shots": [{"player": "Keon Coleman", "model_prob": 0.31, "odds": 260, "book": "DraftKings"}],
            "longshot_watch": [
                {"player": "James Cook", "model_prob": 0.4787, "odds": -170, "book": "Novig"},
                {"player": "Dalton Kincaid", "model_prob": 0.41, "odds": 140, "book": "DraftKings"},
                {"player": "Dalton Kincaid", "model_prob": 0.39, "odds": 150, "book": "FanDuel"},
                {"player": "Nobody Priced", "model_prob": 0.2, "odds": None}]}


def test_the_read_carries_his_chance_price_and_seat():
    reads = _reads()
    assert G.stamp_touchdowns(reads, _result()) == 2, "Allen has no scorer row; he is not stamped"
    k, c, a = reads["LAC@BUF"]["players"]
    assert k["td"] == {"model_prob": 0.41, "odds": 140, "book": "DraftKings"}, "the higher chance wins"
    assert c["td"]["odds"] == -170 and "td" not in a
    G.stamp_picks(reads, {}, board=[{"kind": "td", "player": "James Cook"}, {"kind": "prop", "player": "Dalton Kincaid"}])
    assert c["td"]["on_board"] is True and k["td"]["on_board"] is False


def test_the_scan_stamps_before_the_board_and_the_board_stamps_after():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    body = src[src.index("def attach_nfl("):src.index("# ═══ COLLEGE")]
    assert "stamp_touchdowns(reads, result)" in body
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert "stamp_picks(_partial[\"scan_reads\"], _lean_report, board=_likely)" in pipe


def test_the_card_says_it_on_both_read_cards():
    fn = APP[APP.index("function scanTdHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "Anytime TD:" in fn and "on the Most Likely board" in fn and "under the 55% bar" in fn
    assert 'String(p.market || "") === "anytime_td"' in fn, "a touchdown pick is not said twice"
    assert '${scanPickHTML(x, "sct-pick")}${scanTdHTML(x, "sct-pick")}' in APP, "the dashboard list"
    assert "${scanPickHTML(x)}${scanTdHTML(x)}" in APP, "the game page card"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
