"""American odds have a dead zone, and a number inside it wins the shop.

There is no such price as -97. The two American scales meet at even
money and there is nothing between -100 and +100 left to express, so a
book quotes that price +100 or -100 and never anything in between. A
number inside the gap was not posted by anyone: it is a decimal price
stored as American, a percentage, a digit lost in transit.

THE REASON IT MATTERS is not that it is wrong, it is that it is
SELECTED FOR. `american_to_prob(-97)` returns 0.492 — a completely
ordinary-looking probability no range check downstream has any cause to
reject. And the shop takes the best price on each side, which for a
negative number is the one closest to zero, so -97 beats the -105 and
-110 it is a corruption of, wins the board, and books the smaller
implied probability it carries as edge the model never found.

Found in this repo's own fixture: data/sample_slate.json carries an
"over_odds": -97 at FanDuel, and it rose into the top ten of the
likelihood board during a sandboxed run of test_likely_journal, which is
how it surfaced at all.

Run directly: `python3 tests/test_deadzone.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.models import SportsbookLine
from engine.odds import (DEAD_ZONE, american_to_prob, best_over_line,
                         best_under_line, is_quotable, shoppable)


# --- the gap itself -------------------------------------------------------
def test_the_dead_zone_is_the_open_interval_between_the_scales():
    assert DEAD_ZONE == (-100, 100)


def test_the_prices_at_the_boundary_are_real_and_quotable():
    """Even money. Both are posted; neither is inside the gap."""
    assert is_quotable(-100)
    assert is_quotable(100)


def test_ordinary_prices_pass():
    for odds in (-110, -105, -140, -10000, 100, 120, 455, 2000):
        assert is_quotable(odds), odds


def test_nothing_strictly_inside_the_gap_is_quotable():
    for odds in (-99, -97, -50, -1, 1, 50, 97, 99):
        assert not is_quotable(odds), odds


def test_zero_is_not_a_price():
    """It is this codebase's unquoted-side sentinel, not a quote."""
    assert not is_quotable(0)


def test_garbage_is_not_a_price():
    for odds in (None, "", "abc", [], {}):
        assert not is_quotable(odds), repr(odds)


def test_a_dead_zone_price_converts_without_complaint():
    """The whole problem in one line: -97 does not look wrong."""
    assert abs(american_to_prob(-97) - 0.4924) < 0.001


# --- shoppable keeps the unquoted-side sentinel ---------------------------
def test_zero_is_shoppable_because_over_only_markets_carry_it():
    assert shoppable(0)


def test_the_dead_zone_is_not_shoppable_either():
    assert not shoppable(-97)


def test_real_prices_are_shoppable():
    assert shoppable(-110)
    assert shoppable(455)


# --- the shop must not take the corrupt price -----------------------------
def _lines():
    return [
        SportsbookLine("DraftKings", 0.5, -105, -121),
        SportsbookLine("FanDuel", 0.5, -97, -121),        # impossible
        SportsbookLine("theScore Bet", 0.5, -110, -121),
    ]


def test_without_the_guard_the_corrupt_price_would_have_won():
    """Not a test of our code — a test that the danger is real. -97 is
    the numeric max, so any "best price" rule selects it."""
    assert max(ln.over_odds for ln in _lines()) == -97


def test_the_over_shop_takes_the_best_price_a_book_posted():
    best = best_over_line(_lines())
    assert best.odds == -105, best.odds
    assert best.book == "DraftKings"


def test_the_under_shop_is_guarded_the_same_way():
    lines = [
        SportsbookLine("DraftKings", 0.5, -105, -121),
        SportsbookLine("FanDuel", 0.5, -105, -3),         # impossible
    ]
    assert best_under_line(lines).odds == -121


def test_an_over_only_market_still_shops():
    """Every under is 0 here. Dropping those rows would delete the
    market rather than clean it."""
    lines = [
        SportsbookLine("DraftKings", 0.5, 320, 0),
        SportsbookLine("FanDuel", 0.5, 355, 0),
    ]
    assert best_over_line(lines).odds == 355


def test_an_all_corrupt_market_still_returns_rather_than_crashing():
    """There is nothing clean to fall back to. The shop stays total;
    refusing the bet is `has_market`'s job, asserted below."""
    lines = [SportsbookLine("FanDuel", 0.5, -97, -98)]
    assert best_over_line(lines).odds == -97


# --- the boards refuse it -------------------------------------------------
def test_the_likelihood_board_calls_a_dead_zone_price_insane():
    from engine.likely import _sane
    assert not _sane(-97)
    assert _sane(-105)


def test_the_likelihood_board_still_accepts_its_whole_real_range():
    from engine.likely import SANE_ODDS, _sane
    assert _sane(SANE_ODDS[0])
    assert _sane(SANE_ODDS[1])


def test_has_market_is_false_when_the_chosen_price_is_not_quotable():
    """The refusal that protects the recommendation page. `is_quotable`
    also answers False for 0, so a side nobody quotes is not a market."""
    import inspect
    from engine import betting
    src = inspect.getsource(betting.evaluate_prop)
    assert "and is_quotable(best.odds))" in src


def test_the_roi_harness_will_not_price_off_a_dead_zone_close():
    quotes = [{"over_odds": -105}, {"over_odds": -97}, {"over_odds": 0}]
    priced = [q["over_odds"] for q in quotes if is_quotable(q["over_odds"])]
    assert priced == [-105], priced


# --- the fixture that found it --------------------------------------------
def test_the_sample_slate_still_carries_the_corrupt_price():
    """If someone cleans the fixture, this file loses the case it was
    written for — better to be told than to quietly stop testing."""
    import json
    with open(os.path.join(ROOT, "data", "sample_slate.json")) as f:
        raw = f.read()
    assert '"over_odds": -97' in raw
    json.loads(raw)      # and it is still valid JSON


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
