"""A player every book stopped pricing before kickoff is treated as out.

Ethan, 2026-09-26: "i dont see zay flowers on any sports book. ik he was
out for hamstring." The report still read Questionable (ESPN, Thursday);
the books had taken his props down. The books move first.

engine/pricedplayers remembers, per event, who the latest pull priced and
who the pull before it priced; oddsapi feeds every served payload's menu
into it and marks the dropped on `Game.pulled_players` when the newer pull
came before kickoff; the matchup scan gives them no read and publishes who
they are; the game page says so.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import pricedplayers as P                            # noqa: E402
from engine import gamescan as G                                 # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_a_newer_pull_without_him_marks_him_pulled_and_a_repeat_does_not():
    d = {}
    P.record("ev1", ["Zay Flowers", "Derrick Henry", "Mark Andrews"], 1000.0, d)
    assert P.pulled("ev1", d) == [], "one pull says nothing"
    P.record("ev1", ["Zay Flowers", "Derrick Henry", "Mark Andrews"], 1000.5, d)
    assert d["ev1"]["latest_at"] == 1000.0, "the same file served again is not a new pull"
    P.record("ev1", ["Derrick Henry", "Mark Andrews"], 5000.0, d)
    assert P.pulled("ev1", d) == ["Zay Flowers"]
    P.record("ev1", ["Derrick Henry", "Mark Andrews", "Zay Flowers"], 9000.0, d)
    assert P.pulled("ev1", d) == [], "back on the books: back in"
    # A newer pull that priced nobody says nothing about anyone.
    P.record("ev2", ["A", "B"], 1000.0, d)
    P.record("ev2", [], 2000.0, d)
    assert P.pulled("ev2", d) == []
    # A week-old earlier menu is another game week.
    P.record("ev3", ["A", "B"], 0.0, d)
    P.record("ev3", ["A"], P.MAX_GAP_S + 10, d)
    assert P.pulled("ev3", d) == []


def test_the_tracker_persists_between_builds():
    path = os.path.join(tempfile.mkdtemp(), "priced.json")
    t = P.Tracker(path)
    t.see("ev1", ["Zay Flowers", "Derrick Henry"], age_s=100.0, now=10_000.0)
    t.save()
    t2 = P.Tracker(path)
    assert t2.see("ev1", ["Derrick Henry"], age_s=10.0, now=20_000.0) == ["Zay Flowers"]
    t2.save()
    assert json.load(open(path))["ev1"]["earlier"] == ["Derrick Henry", "Zay Flowers"]
    assert P.Tracker(path).see("ev1", ["Derrick Henry"], age_s=None) == ["Zay Flowers"], "a cached rebuild keeps the flag"


def test_the_scan_gives_a_pulled_player_no_read_and_names_him():
    usage = {("BAL", G._key("Zay Flowers")): {"name": "Zay Flowers", "tgt_share": 0.29, "targets_pg": 8.0,
                                              "games": 3, "position": "WR"},
             ("BAL", G._key("Rashod Bateman")): {"name": "Rashod Bateman", "tgt_share": 0.2,
                                                 "targets_pg": 5.5, "games": 3, "position": "WR"}}
    out = G.scan_game("DAL", "BAL", ratings={}, charts={}, defenders_now={}, usage=usage,
                      injuries=[], props=[], pulled=["Zay Flowers"])
    assert not [p for p in out["players"] if p["player"] == "Zay Flowers"]
    assert out["pulled"] == ["Zay Flowers"]
    assert G.scan_game("DAL", "BAL", ratings={}, charts={}, defenders_now={}, usage=usage,
                       injuries=[], props=[])["pulled"] == []


def test_the_pull_loop_the_game_and_the_page_are_wired():
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"), encoding="utf-8").read()
    assert "_priced = _PricedTracker()" in src and "_priced.save()" in src
    assert "_gone = _priced.see(ev.get(\"id\") or \"\", sorted(_who), _age)" in src
    assert "float(_cur.get(\"latest_at\") or 0) < _kick_ts" in src, "only a pull before kickoff counts"
    from engine.models import Game
    assert "pulled_players" in Game.__dataclass_fields__
    scan = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert 'pulled=getattr(g, "pulled_players", None) or [])' in scan
    assert "<b>Taken down by the books:</b>" in APP and "(scan.pulled || []).length" in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
