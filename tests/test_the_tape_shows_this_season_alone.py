"""The tale of the tape shows each rank on THIS SEASON ALONE beside the
blended one. Ethan, 2026-09-27, on the Jets: "how are we ranking the Jets
defense almost the worst in the league when they are ranked 7th". After
two games the blend is 25% this season (the measured forecast), so a
defence 10th this year and 30th last read "28th · Weak" and nothing said
what this season alone says."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_college_ranks_carry_this_season_alone():
    # A: great this season, awful last; B: the reverse. Two games in, the
    # blend still leans on last season, so the blended ranks and this
    # season's ranks disagree — and both are on the cell.
    now = {"A": {"plays": 140, "off": {"overall": 0.25}, "def": {"overall": -0.20}},
           "B": {"plays": 140, "off": {"overall": 0.05}, "def": {"overall": 0.10}}}
    last = {"A": {"off": {"overall": -0.30}, "def": {"overall": 0.30}},
            "B": {"off": {"overall": 0.30}, "def": {"overall": -0.30}}}
    r = G.cfb_ratings(now, last)
    assert r["A"]["blend"] < 1.0
    assert r["A"]["def"]["overall"] == {"value": r["A"]["def"]["overall"]["value"], "rank": 2, "now_rank": 1}
    assert r["B"]["def"]["overall"]["now_rank"] == 2 and r["B"]["def"]["overall"]["rank"] == 1
    assert r["A"]["off"]["overall"]["now_rank"] == 1


def test_no_last_season_means_no_second_number():
    r = G.cfb_ratings({"A": {"plays": 140, "off": {"overall": 0.2}, "def": {"overall": 0.1}},
                       "B": {"plays": 140, "off": {"overall": 0.1}, "def": {"overall": 0.2}}}, None)
    assert r["A"]["blend"] == 1.0
    assert "now_rank" not in r["A"]["def"]["overall"], "the rank already IS this season"


def test_the_nfl_ratings_stamp_it_too():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    body = src.split("def ratings_from_rows(")[1].split("\ndef ")[0]
    assert "_stamp_now_ranks(blended," in body


def test_the_card_draws_it_and_says_what_it_is():
    assert "${ordinal(now)} this season</small>" in APP
    assert "${tapeCell(ra, n, un(away, side, k))}${tapeCell(rh, n, un(home, side, k))}" in APP
    assert "The small line under a rank is this season alone." in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
