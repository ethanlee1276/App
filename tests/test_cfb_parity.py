"""Everything built for the NFL board this week, reaching the college one.

Ethan, 2026-08-30: "you also need to go back and implement all the new
work and shit we need for nfl today into cfb."

The audit found one structural cause behind most of it, and it is this
codebase's most-repeated bug wearing a new hat.

`likely.build` takes rows from two makers: `from_prop` for the priced
prop board, and `from_watch` for the touchdown chain. Only `from_prop`
enforced anything — the 30% floor, the sane-price check, the proxy
refusal, the credibility bar all lived there. `build`'s own comment
claimed "one board means one bar" while applying that bar on one of its
two paths.

AND COLLEGE IS ENTIRELY THE UNGATED PATH. `cfb_build` calls
`build([], rows, watch)` with no props at all, so every refusal added to
this module protected the NFL prop board and left the whole college
board open. Measured before the fix, all three of these published:

    an 8% row     on a board whose floor is 30%
    a -97 price   no book can post
    a proxy quote the model invented, priced as though it were a market

So the bar moved into `admissible`, which `build` applies to every row
whatever built it. The floor is a claim about the word on the page —
MIN_PROB says a probability under it "is not likely by any reading" — so
a college board that empties under it is one honestly reporting nothing
likely tonight, not one relabelling 8%.

THE SAME GUARD WAS MISSING A SECOND PLACE. `best_scorer_price` shops
every anytime-touchdown quote in BOTH leagues with a bare `max`, which
is precisely the shape that selects a dead-zone price. `odds.best_over_line`
was taught this and that function was missed.

Run directly: `python3 tests/test_cfb_parity.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely
from engine.sources.oddsapi import best_scorer_price


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _watch(player, prob, odds=-150, book="DK", implied=None):
    return {"player": player, "team": player[0], "model_prob": prob,
            "implied_prob": prob - 0.02 if implied is None else implied,
            "odds": odds, "book": book}


def _cfb(watch, census=None):
    """A college board: watch rows only, which is all cfb_build passes."""
    return likely.build([], [], watch, sport="cfb", census=census)


# --- one bar, both paths --------------------------------------------------
def test_a_row_under_the_floor_does_not_reach_a_college_board():
    board = _cfb([_watch("Under", 0.08, odds=900)])
    assert board == [], board


def test_a_price_no_book_could_post_does_not_reach_it():
    assert _cfb([_watch("Dead", 0.55, odds=-97)]) == []


def test_a_proxy_quote_does_not_reach_it():
    """A fabricated price. `from_prop` catches this as `has_market`;
    watch rows carry no such key and the book name is the tell."""
    assert _cfb([_watch("Proxy", 0.60, book="proxy")]) == []


def test_a_row_that_disagrees_with_the_market_does_not_reach_it():
    assert _cfb([_watch("Wild", 0.90, implied=0.30)]) == []


def test_a_good_row_still_reaches_it():
    board = _cfb([_watch("Fine", 0.62)])
    assert [r["player"] for r in board] == ["Fine"]


def test_the_floor_is_the_one_the_module_publishes():
    """Not a second copy that can drift from MIN_PROB."""
    just_under = likely.MIN_PROB - 0.01
    assert _cfb([_watch("Low", just_under)]) == []
    assert len(_cfb([_watch("Ok", likely.MIN_PROB)])) == 1


def test_the_gate_is_one_function_not_two_copies():
    src = _src("engine", "likely.py")
    assert "def admissible(row: dict) -> str:" in src
    at = src.index("    def keep(got) -> bool:")
    body = src[at:src.index("out.sort(", at)]
    # Both loops go through it.
    assert body.count("not keep(got)") == 2, body


# --- and it says why ------------------------------------------------------
def test_the_refusals_are_counted_for_the_caller():
    census: dict = {}
    _cfb([_watch("Under", 0.08), _watch("Dead", 0.55, odds=-97),
          _watch("Proxy", 0.60, book="proxy"), _watch("Fine", 0.62)],
         census=census)
    assert sum(census.values()) == 3, census
    assert "under the likelihood floor" in census


def test_the_census_is_optional_so_no_caller_had_to_change():
    assert _cfb([_watch("Fine", 0.62)])          # no census kwarg


def test_the_census_never_rides_on_a_row():
    """An earlier cut stashed it on board[0], which would have followed
    the row into the journal."""
    board = _cfb([_watch("Fine", 0.62)])
    assert "_refused" not in board[0]


def test_both_builds_publish_the_census():
    assert 'out["likely_census"] = _ml_census' in _src("cfb_build.py")
    assert '"likely_census": _likely_census,' in _src("engine", "pipeline.py")


# --- the second unguarded shop --------------------------------------------
def test_the_scorer_shop_refuses_a_dead_zone_price():
    """-97 is the numeric max, so a bare `max` selects it — and this
    function shops the touchdown quotes for BOTH leagues."""
    got = best_scorer_price([{"yes_odds": -105, "book": "DK"},
                             {"yes_odds": -97, "book": "FD"}])
    assert got["yes_odds"] == -105, got


def test_the_scorer_shop_still_takes_the_best_real_price():
    got = best_scorer_price([{"yes_odds": 320}, {"yes_odds": 355}])
    assert got["yes_odds"] == 355


def test_an_all_corrupt_menu_is_no_market_rather_than_a_bad_one():
    assert best_scorer_price([{"yes_odds": -97}, {"yes_odds": 50}]) is None


def test_an_empty_menu_still_answers_none():
    assert best_scorer_price([]) is None
    assert best_scorer_price(None) is None


# --- the page furniture college was missing -------------------------------
def test_college_publishes_the_board_guide():
    """Without it `boardGuide` renders nothing and the college board
    carries no trust line at all."""
    assert 'out["board_guide"] = _boards.guide()' in _src("cfb_build.py")


def test_college_publishes_the_shelves():
    assert 'out["board_shelves"] = _boards.shelves("cfb"' in _src("cfb_build.py")


def test_college_gets_the_football_shelves():
    from engine import boards
    assert ([s["key"] for s in boards.shelves("cfb")]
            == [s["key"] for s in boards.shelves("nfl")])


def test_a_touchdown_only_board_gets_exactly_one_shelf():
    """College prices touchdowns and nothing else, so the other three
    shelves have no rows and drop rather than drawing empty."""
    from engine import boards
    got = boards.shelves("cfb", [{"market": "anytime_td"}])
    assert [s["key"] for s in got] == ["touchdowns"]


def test_college_journals_the_board_like_the_nfl_does():
    assert "ledger.log_most_likely(" in _src("cfb_build.py")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
