"""Most Likely shows the side we think happens, not the side with the value.

Ethan, 2026-09-27, on "Allen O1.5 pass TD — 57% over, market 61%. No
edge, no fight": "for the most likely bets we need to show what we
genuinely think is going to happen and not stumping a pick bc there is
no edge. for the edge bets thats ok bc they are EDGE bets, but for the
most likely bets, thats wrong".

The cause was one line deep. The board reads each prop's EDGE row, and
`betting.choose_side` hands that row whichever side has the better
VALUE — Allen's arrived as UNDER 1.5 at 43% (the soft +125), Shakir's as
UNDER 3.5 at 41%. The board only ever asked about that side, and the
alternate ladder (the only other place it looked) is not sold for
passing touchdowns. So the over we think happens was never a candidate,
and on a thin slate the reserve filled the board with sub-50% value
sides. The other side of the main number is now a candidate like any
rung — at its own best bettable price, as the complement of the number
the main side shows, only when it is the likelier side, held to the same
floor, cap and credibility bar.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as L                                       # noqa: E402

# Josh Allen's passing-TD row as the edge engine hands it over (the real
# numbers from the Chargers @ Bills build: DraftKings 1.5, -159 / +125).
ALLEN = {"player": "Josh Allen", "team": "BUF", "opponent": "LAC", "market": "pass_td",
         "market_label": "Passing TDs", "side": "UNDER", "line": 1.5, "odds": 125, "book": "DraftKings",
         "hit_prob": 0.4338, "raw_prob": 0.466, "fair_prob": 0.4199, "has_market": True,
         "projection": 1.8, "proj_std": 1.337, "recent_values": [2, 1, 3, 2, 1],
         "all_lines": [{"book": "DraftKings", "line": 1.5, "over_odds": -159, "under_odds": 125}]}
NO_FITS = {}


def test_the_edge_side_under_the_floor_turns_into_the_side_we_think_happens():
    got = L.from_prop(dict(ALLEN), lambda m: True, fits=NO_FITS)
    assert got is not None, "the over we think happens was never a candidate — the bug"
    assert (got["side"], got["line"], got["odds"], got["book"]) == ("over", 1.5, -159, "DraftKings")
    assert got["model_prob"] == round(1 - 0.4338, 4), "the complement of the number the edge card shows"
    assert got["rung"] == "main" and got["main_side"] == "UNDER", "the edge engine's side stays on the row"
    assert abs(got["implied_prob"] - round(1 - 0.4199, 4)) < 1e-9, "judged against its own side of the market"


def test_the_other_side_is_only_a_candidate_when_it_is_the_likelier_side():
    # A value side at 51% — its other side, 49%, must never be offered, or
    # a read's lean could pick the minority (Allen's yards, 2026-09-27).
    row = dict(ALLEN, market="pass_yds", side="UNDER", line=238.5, odds=-105, hit_prob=0.5112,
               fair_prob=0.4878, projection=231.3, proj_std=60.0,
               all_lines=[{"book": "FanDuel", "line": 238.5, "over_odds": -115, "under_odds": -105}])
    assert L._main_other_side(row, "pass_yds", NO_FITS, floor=0.0) is None
    got = L.from_prop(row, lambda m: True, fits=NO_FITS, floor=0.40,
                      lean="over")
    assert got is None or got["side"].lower() == "under", "a read's lean never picks a minority side"


def test_the_bars_still_hold_on_the_other_side():
    # The cap: no book prices the over at -250 or better → no candidate.
    heavy = dict(ALLEN, all_lines=[{"book": "DraftKings", "line": 1.5, "over_odds": -400, "under_odds": 300}])
    assert L._main_other_side(heavy, "pass_td", NO_FITS) is None
    # Credibility: 57% against a market that says 80% on the over is refused.
    far = dict(ALLEN, fair_prob=0.20)
    assert L._main_other_side(far, "pass_td", NO_FITS) is None
    # No real market, no candidate.
    assert L._main_other_side(dict(ALLEN, has_market=False), "pass_td", NO_FITS) is None
    # Both sides of one number sum to one.
    cand = L._main_other_side(dict(ALLEN), "pass_td", NO_FITS, floor=0.0)
    assert abs(cand["prob"] + ALLEN["hit_prob"] - 1.0) < 1e-4


def test_a_prop_with_no_alternate_ladder_still_gets_its_other_side():
    rows = L.rungs(dict(ALLEN, alt_lines=[]), "pass_td", NO_FITS)
    assert [(c["side"], c["line"], c.get("main")) for c in rows] == [("over", 1.5, True)]


def test_the_edge_board_is_left_alone():
    """The fix lives in the likelihood board; the edge row is not touched."""
    row = dict(ALLEN)
    L.from_prop(row, lambda m: True, fits=NO_FITS)
    assert row["side"] == "UNDER" and row["odds"] == 125 and row["hit_prob"] == 0.4338


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
