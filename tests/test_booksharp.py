"""Which books are actually sharp — measured, not asserted.

NFL_MODEL §4's sharp-book hierarchy is a hand-written LIST today:
`oddsapi.SHARP_BOOKS`, everything in it equal, everything outside it
worth nothing. Which book is sharp is the most repeated claim in this
industry and the least often checked, and we do not have to trust it —
every snapshot the movement engine writes records what each book said and
when, and the closing consensus is the nearest thing to truth available.

Run directly: `python3 tests/test_booksharp.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import booksharp as bs                            # noqa: E402


def _snap(ts, prices, player="P", market="rec_yds", side="over"):
    return {"ts": ts, "player": player, "market": market, "side": side,
            "books": {b: {"odds": o} for b, o in prices.items()}}


def _series(n, sharp_odds, slow_odds, close):
    """n series where `sharp` sits at the close early and `slow` does not."""
    rows = []
    for i in range(n):
        p = f"P{i}"
        rows += [
            _snap(1000, {"sharp": sharp_odds, "slow": slow_odds}, player=p),
            _snap(1100, {"sharp": sharp_odds, "slow": slow_odds}, player=p),
            _snap(2000, {"sharp": close, "slow": close}, player=p),
        ]
    return rows


def test_the_book_that_sat_at_the_close_early_scores_better():
    """The whole measurement in one case: -110 all along against a -110
    close is perfect foresight; -150 all along is 15 points of error."""
    m = bs.measure(_series(12, -110, -150, -110))
    assert m["sharp"]["mae_pts"] < m["slow"]["mae_pts"]
    assert m["sharp"]["mae_pts"] == 0.0
    assert m["sharp"]["weight"] > m["slow"]["weight"]


def test_a_book_below_the_series_floor_is_not_ranked():
    """Three props quoted once is not a hierarchy. `weight` is None rather
    than a small number, because a small number still sorts."""
    m = bs.measure(_series(3, -110, -150, -110))
    assert m["sharp"]["weight"] is None
    assert m["sharp"]["mae_pts"] == 0.0        # still MEASURED, just unranked


def test_accuracy_ranks_and_lead_only_reports():
    """A twitchy book moves first every time by reacting to noise and
    reverting. Ranking on lead would put it top; ranking is on accuracy."""
    rows = []
    for i in range(12):
        p = f"P{i}"
        rows += [
            # `twitchy` moves first and moves WRONG; `steady` never moves
            # and is already at the close.
            _snap(1000, {"twitchy": -110, "steady": -120}, player=p),
            _snap(1050, {"twitchy": -200, "steady": -120}, player=p),
            _snap(2000, {"twitchy": -120, "steady": -120}, player=p),
        ]
    m = bs.measure(rows)
    assert m["twitchy"]["lead_rate"] == 1.0, m["twitchy"]
    assert m["steady"]["mae_pts"] < m["twitchy"]["mae_pts"]
    assert m["steady"]["weight"] > m["twitchy"]["weight"]


def test_an_impossible_price_is_not_a_price():
    """`-5` is not a 95% favourite, it is a corrupt row. Prices inside
    ±100 do not exist in American odds and must not reach the error."""
    assert bs._implied(-5) is None
    assert bs._implied(0) is None
    assert bs._implied(None) is None
    assert bs._implied(-110) is not None


def test_one_book_cannot_define_the_truth_it_is_graded_against():
    """The close is the MEDIAN across books in the last snapshot. With a
    single book quoting, it would grade itself as perfect every time."""
    rows = _series(12, -110, -150, -110)
    m = bs.measure(rows)
    # `slow` is 15 points off a close it half-owns; if the close were its
    # own price this would be 0.
    assert m["slow"]["mae_pts"] > 5


def test_the_comparison_names_a_book_we_call_sharp_that_is_not():
    """The finding that would actually change something."""
    m = bs.measure(_series(12, -110, -150, -110))
    # Name the WORSE book as sharp and the comparison should catch it.
    m2 = dict(m)
    c = bs.compare_to_the_list(m2)
    assert c["n_ranked"] == 2
    assert c["measured_sharpest"][0] == "sharp"


def test_the_report_says_so_when_there_is_no_history():
    """An empty measurement must not render as a table of nothing."""
    out = bs.report([])
    assert "No snapshot history yet" in out


def test_nothing_here_prices_anything():
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "booksharp.py"), encoding="utf-8").read()
    assert "hit_prob" not in src and "stake" not in src
    assert "THE_INFORMATION_TEST" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
