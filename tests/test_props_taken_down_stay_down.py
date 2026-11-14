"""A player the books took down stays down until a pull prices him again.

Ethan's Patriots–Bears report, 2026-10-22, under "What changed" at Thu
7:12 AM ET: "Kyle Monangai (CHI RB)'s props are back up" — beside a report
that listed him out for a third straight game. One pull priced him, the
next did not (pulled), and the one after that did not either; but
engine/pricedplayers only compared the last two pulls, so the third read
as nobody pulled, and engine/reportlog wrote the difference as a return.

  * the pull memory keeps him (``gone``) until a pull prices him again, and
    a pull that priced nobody clears no one;
  * a build whose payload is too old to price from still hangs the
    memory's answer on the game (engine/sources/oddsapi), so a stale build
    is not a return either;
  * the change log never says "back up" for a player the report lists out.

Run directly: `python3 tests/test_props_taken_down_stay_down.py`
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import pricedplayers as P                              # noqa: E402
from engine import reportlog as L                                  # noqa: E402

ODDS = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"), encoding="utf-8").read()


def test_a_third_pull_without_him_keeps_him_down():
    d = {}
    P.record("ev", ["Kyle Monangai", "D'Andre Swift"], 1000.0, d)
    P.record("ev", ["D'Andre Swift"], 2000.0, d)
    assert P.pulled("ev", d) == ["Kyle Monangai"]
    P.record("ev", ["D'Andre Swift"], 3000.0, d)
    assert P.pulled("ev", d) == ["Kyle Monangai"], "the third pull without him is not a return"
    P.record("ev", [], 4000.0, d)
    assert P.pulled("ev", d) == ["Kyle Monangai"], "a pull that priced nobody brings nobody back"
    P.record("ev", ["D'Andre Swift", "Kyle Monangai"], 5000.0, d)
    assert P.pulled("ev", d) == [] and "gone" not in d["ev"], "priced again: back"
    # A memory the box kept before ``gone`` existed reads as it did.
    kept = {"ev2": {"latest_at": 2000.0, "latest": ["B"], "earlier_at": 1000.0, "earlier": ["A", "B"]}}
    assert P.pulled("ev2", kept) == ["A"]


def test_a_new_spelling_is_neither_a_pull_nor_a_man_who_never_comes_back():
    d = {}
    P.record("ev", ["D.J. Moore", "Luka Dončić", "Carlton Davis III"], 1000.0, d)
    P.record("ev", ["DJ Moore", "Luka Doncic", "Carlton Davis"], 2000.0, d)
    assert P.pulled("ev", d) == [], "the same men, spelled another way"
    P.record("ev", ["Luka Doncic", "Carlton Davis"], 3000.0, d)
    assert P.pulled("ev", d) == ["DJ Moore"]
    P.record("ev", ["D.J. Moore", "Luka Doncic", "Carlton Davis"], 4000.0, d)
    assert P.pulled("ev", d) == [], "back under the first spelling is back"


def test_the_tracker_keeps_him_down_across_builds():
    path = os.path.join(tempfile.mkdtemp(), "priced.json")
    t = P.Tracker(path)
    t.see("ev", ["Kyle Monangai", "D'Andre Swift"], age_s=100.0, now=10_000.0)
    t.save()
    t = P.Tracker(path)
    assert t.see("ev", ["D'Andre Swift"], age_s=50.0, now=20_000.0) == ["Kyle Monangai"]
    t.save()
    t = P.Tracker(path)
    assert t.see("ev", ["D'Andre Swift"], age_s=10.0, now=30_000.0) == ["Kyle Monangai"]
    t.save()
    assert json.load(open(path))["ev"]["gone"] == ["Kyle Monangai"]
    # A stale build asks with no age: nothing recorded, the answer stands.
    assert P.Tracker(path).see("ev", [], age_s=None) == ["Kyle Monangai"]


def test_a_stale_payload_still_hangs_the_memory_on_the_game():
    assert "_prop_leg = props_ok" in ODDS, "the leg check is kept before staleness clears props_ok"
    assert "elif _prop_leg:" in ODDS
    assert '_mark_pulled(ev, game, _priced.see(ev.get("id") or "", [], None), home, away)' in ODDS
    assert "_mark_pulled(ev, game, _gone, home, away)" in ODDS, "the fresh path marks the same way"
    assert ODDS.count("float(_cur.get(\"latest_at\") or 0) < _kick_ts") == 1, "one kickoff rule for both"


def test_the_change_log_never_says_back_up_for_a_player_listed_out():
    who = {"Kyle Monangai": "CHI RB"}
    old = {"injuries": {"Kyle Monangai": "out"}, "pulled": ["Kyle Monangai"], "who": who}
    new = {"injuries": {"Kyle Monangai": "out"}, "pulled": [], "who": who}
    assert L.diff(old, new, "CHI", "NE") == []
    for st in ("ir", "doubtful", "suspended"):
        assert L.diff(old, {**new, "injuries": {"Kyle Monangai": st}}, "CHI", "NE") == \
            [f"Kyle Monangai (CHI RB) is now {L.STATUS_WORDS[st]}; he was out"]
    # Not listed out: a return is news, and so is a player the books take
    # down after the report already has him out.
    assert L.diff({"injuries": {}, "pulled": ["Zay Flowers"]}, {"injuries": {}, "pulled": []},
                  "BAL", "DAL") == ["Zay Flowers's props are back up"]
    assert L.diff({"injuries": {}, "pulled": ["Zay Flowers"]},
                  {"injuries": {"Zay Flowers": "questionable"}, "pulled": []}, "BAL", "DAL") == \
        ["Zay Flowers was listed questionable", "Zay Flowers's props are back up"]
    assert L.diff({"injuries": {"Kyle Monangai": "out"}, "pulled": []},
                  {"injuries": {"Kyle Monangai": "out"}, "pulled": ["Kyle Monangai"]}, "CHI", "NE") == \
        ["Every book took Kyle Monangai's props down"]


def test_the_line_already_written_goes_on_the_next_build():
    """Thu 7:12 AM's line was kept in the box's log; the next build drops
    it while the report still lists him out, and keeps everything else."""
    path = os.path.join(tempfile.mkdtemp(), "reportlog_nfl.json")
    key = "NE@CHI|2026-10-22"
    snap = {"spread": -3.0, "total": 50.5, "injuries": {"Kyle Monangai": "out"}, "pulled": [],
            "who": {"Kyle Monangai": "CHI RB"}}
    json.dump({"games": {key: {"first": "2026-10-20T18:55:00", "last": snap, "entries": [
        {"at": "2026-10-21T15:00:00", "changes": ["Every book took Kyle Monangai (CHI RB)'s props down"]},
        {"at": "2026-10-22T07:12:00", "changes": ["Kyle Monangai (CHI RB)'s props are back up"]},
        {"at": "2026-10-22T09:00:00", "changes": ["The total moved from 50 to 50.5",
                                                  "Kyle Monangai (CHI RB)'s props are back up"]}]}}},
              open(path, "w"))
    got = L.update(path, {key: (snap, "CHI", "NE")}, "2026-10-22T18:00:00")[key]["entries"]
    assert got == [{"at": "2026-10-21T15:00:00", "changes": ["Every book took Kyle Monangai (CHI RB)'s props down"]},
                   {"at": "2026-10-22T09:00:00", "changes": ["The total moved from 50 to 50.5"]}], got
    assert json.load(open(path))["games"][key]["entries"] == got, "the file is cleaned, so Ask reads it clean too"
    # A return for a player NOT listed out is kept.
    entries = [{"at": "x", "changes": ["Zay Flowers (BAL WR)'s props are back up"]}]
    assert L.drop_false_returns(entries, {"injuries": {}, "who": {"Zay Flowers": "BAL WR"}}) == entries


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
