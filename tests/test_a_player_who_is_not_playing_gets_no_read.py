"""A player who is not playing gets no "could shine" read and no touchdown
scenario; a scenario needs a red-zone role.

Ethan, 2026-09-26, Zay Flowers at the top of Touchdown scenarios: "it says
0.0 redzone chances expected yet we display this pick, and also, this
player isn't even playing for this game."

Two holes. The scenario rule required the defence and the usage but let a
player with no red-zone role through on offence + defence + usage; and
neither the scenario nor the matchup read asked the player's OWN injury
listing (the reads checked his teammates', and `key_players` skipped the
ruled out, but a player the books still priced came in through his props).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402
from engine import tdscenarios as S                              # noqa: E402


class _Inj:
    def __init__(self, player, team, position, status):
        self.player, self.team, self.position, self.status = player, team, position, status


UNITS = {"blend": 0.55, "def": {"passing": {"rank": 32}, "rushing": {"rank": 10}}}


def _read(td, **kw):
    r = {"player": "Zay Flowers", "team": "BAL", "opp": "DAL", "pos": "WR", "read": "good",
         "usage": {"tgt_share": 0.29, "snap_pct": 0.75}, "td": td}
    r.update(kw)
    return r


def _td(**kw):
    t = {"model_prob": 0.52, "odds": 163, "book": "Bally Bet", "implied_total": 28.5, "rz_chances": 1.6}
    t.update(kw)
    return t


def test_no_red_zone_role_is_no_scenario():
    assert S.score(_read(_td()), UNITS), "the full case is a scenario"
    assert S.score(_read(_td(rz_chances=0.0)), UNITS) is None, "0.0 red-zone chances: not one"


def test_any_listing_keeps_him_off_the_shelf():
    for status in ("OUT", "DOUBTFUL", "QUESTIONABLE", "IR"):
        assert S.score(_read(_td(injury_status=status)), UNITS) is None, status
    assert S.score(_read(_td(), own_status="QUESTIONABLE"), UNITS) is None


def test_the_scan_gives_no_read_to_a_ruled_out_player_and_notes_a_questionable_one():
    usage = {("BAL", G._key("Zay Flowers")): {"name": "Zay Flowers", "tgt_share": 0.29, "targets_pg": 8.0,
                                              "games": 3, "position": "WR"},
             ("BAL", G._key("Rashod Bateman")): {"name": "Rashod Bateman", "tgt_share": 0.2, "targets_pg": 5.5,
                                                 "games": 3, "position": "WR"}}
    props = [{"player": "Zay Flowers", "team": "BAL", "opponent": "DAL", "position": "WR",
              "market": "rec_yds", "side": "over", "line": 60.5, "odds": -115}]
    out = G.scan_game("DAL", "BAL", ratings={}, charts={}, defenders_now={}, usage=usage,
                      injuries=[_Inj("Zay Flowers", "BAL", "WR", "OUT")], props=props)
    assert not [p for p in out["players"] if p["player"] == "Zay Flowers"], "ruled out: no read"
    q = G.scan_game("DAL", "BAL", ratings={}, charts={}, defenders_now={}, usage=usage,
                    injuries=[_Inj("Zay Flowers", "BAL", "WR", "QUESTIONABLE")], props=props)
    (me,) = [p for p in q["players"] if p["player"] == "Zay Flowers"]
    assert me["notes"][0] == "Zay Flowers is listed questionable himself — this read assumes he plays"
    assert me["own_status"] == "QUESTIONABLE"


def test_the_stamp_carries_his_listing():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert '"injury_status": r.get("injury_status") or "",' in src
    reads = {"DAL@BAL": {"players": [{"player": "Zay Flowers", "team": "BAL"}]}}
    G.stamp_touchdowns(reads, {"longshot_watch": [{"player": "Zay Flowers", "model_prob": 0.52, "odds": 163,
                                                   "book": "Bally Bet", "injury_status": "OUT"}]})
    assert reads["DAL@BAL"]["players"][0]["td"]["injury_status"] == "OUT"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
