"""A shut tier and a quiet night look identical on the board. They differ.

Ethan, 2026-09-06: "we need to be showing the best bets possible for the
most likely bets."

`quality.TIER_MIN_EDGE` carries the arithmetic it was tuned by, on
2026-07-29: the credibility guard caps a raw disagreement at 10 points,
so the largest believable POST-SHRINK edge is 10% x the tier's shrink —
5.0% in Tier 1, 4.5% in Tier 2 — and each bar was set inside that. The
comment is explicit about what happens when a bar sits outside it: "the
tier is mathematically closed rather than disciplined ... a closed door
wearing a bar's clothes."

That arithmetic was exact when it was written and is not exact now.
`engine/selectionfit.py` shipped on 2026-08-12, and
`betting.evaluate_prop` applies its haircut to `edge` IMMEDIATELY after
the tier shrink and BEFORE the bar is compared (betting.py, the two
lines `hit, edge, credible = temper_edge(...)` then `hit, edge =
apply_selection(hit, edge, sport)`). So the window each bar has to sit
inside is narrower than the tuning comment's by however much the live
haircut is worth, and nothing re-derives it.

The numbers below are measured against the shipped code, not asserted.
They are also currently HYPOTHETICAL: the pooled correction was refused
by its own walk-forward (docs/SELECTION_CORRECTION.md §12, "six cells,
zero passes"), so the live shift is 0.0 and both NFL prop markets are
open today. The fitter re-runs weekly and can adopt, which is exactly
why this is pinned: the day it adopts, the board goes to zero with no
sentence anywhere explaining it.

Run directly: `python3 tests/test_bar_reachable.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.betting import MAX_CREDIBLE_EDGE                 # noqa: E402
from engine.census import bar_notes                          # noqa: E402
from engine.quality import (                                 # noqa: E402
    TIER_MIN_EDGE, TIER_SHRINK, bar_reachable, best_possible_edge,
    market_tier, unreachable_markets,
)

#: The two NFL prop markets still on the board. rush_yds and rec_yds are
#: shut on their distribution (calibrate.SHUT_MARKETS).
OPEN_NFL = ("receptions", "pass_yds")


# --- the arithmetic the tuning comment states -------------------------
def test_with_no_haircut_each_bar_sits_inside_its_own_window():
    """The 2026-07-29 re-tune's own claim, asserted rather than trusted."""
    for tier, markets in ((1, ["receptions"]), (2, ["pass_yds"])):
        for market in markets:
            best = best_possible_edge(market, shift=0.0)
            assert abs(best - MAX_CREDIBLE_EDGE * TIER_SHRINK[tier]) < 1e-9
            assert best > TIER_MIN_EDGE[tier], market


def test_both_open_nfl_prop_markets_are_reachable_today():
    for market in OPEN_NFL:
        ok, best, bar = bar_reachable("nfl", market, shift=0.0)
        assert ok, f"{market}: best {best} < bar {bar}"


def test_tier_three_is_over_its_ceiling_on_purpose():
    """Touchdown and home-run markets are quarantined to the Long Shots
    board. Their bar is deliberately unreachable, so the reporter skips
    them rather than printing the same sentence every cycle forever."""
    ok, best, bar = bar_reachable("nfl", "anytime_td", shift=0.0)
    assert not ok and best < bar
    assert unreachable_markets("nfl", ["anytime_td"]) == []


# --- and what the haircut does to it ----------------------------------
def test_a_small_haircut_shuts_the_only_tier_two_market_the_nfl_prices():
    """2.5 probability points is enough. The over-claim that motivated
    the haircut was measured at 9-10."""
    assert not bar_reachable("nfl", "pass_yds", shift=-0.10)[0]
    assert bar_reachable("nfl", "pass_yds", shift=0.0)[0]


def test_a_four_point_haircut_shuts_the_whole_nfl_prop_board():
    for market in OPEN_NFL:
        assert not bar_reachable("nfl", market, shift=-0.17)[0], market


def test_the_closure_holds_across_the_prices_props_actually_live_at():
    """Not a corner case at one book number: every fair price from .30
    to .70 is shut at a 4.2-point haircut."""
    for fair in (0.30, 0.40, 0.50, 0.55, 0.60, 0.70):
        for market in OPEN_NFL:
            assert not bar_reachable("nfl", market, fair=fair,
                                     shift=-0.17)[0], (market, fair)


def test_the_haircut_is_what_moves_it_and_the_bar_is_untouched():
    """A guard against 'fixing' this by moving the bar in this test."""
    for market in OPEN_NFL:
        wide = best_possible_edge(market, shift=0.0)
        cut = best_possible_edge(market, shift=-0.17)
        assert cut < wide
        assert bar_reachable("nfl", market, shift=0.0)[2] == \
            TIER_MIN_EDGE[market_tier(market)]


# --- the board says it, instead of showing a quiet night --------------
def test_an_open_board_says_nothing():
    assert bar_notes("nfl", markets=list(OPEN_NFL)) == []


def test_a_shut_board_names_the_market_and_both_numbers():
    import engine.selectionfit as SF
    real = SF.shift_for
    SF.shift_for = lambda sport, path=None: -0.17
    try:
        notes = bar_notes("nfl", markets=list(OPEN_NFL))
    finally:
        SF.shift_for = real
    assert len(notes) == 2, notes
    for note in notes:
        assert "no bet is possible at any price" in note
        assert "%" in note and "minimum" in note
        assert "unreachable rather than strict" in note


def test_the_note_reads_off_the_rows_when_no_markets_are_named():
    import engine.selectionfit as SF
    real = SF.shift_for
    SF.shift_for = lambda sport, path=None: -0.17
    try:
        notes = bar_notes("nfl", rows=[{"market": "pass_yds"},
                                       {"market": "pass_yds"},
                                       {"market": "anytime_td"}])
    finally:
        SF.shift_for = real
    assert len(notes) == 1 and notes[0].startswith("pass_yds:")


def test_the_pipeline_publishes_it_beside_the_funnel():
    """The funnel says 'edge under the minimum'; this says whether that
    minimum could have been cleared. They belong on the same payload."""
    from engine.pipeline import run_slate
    out = run_slate("data/sample_slate.json")
    assert "bar_status" in out
    assert isinstance(out["bar_status"], list)
    assert out["bar_status"] == [], "no haircut is live on a fresh clone"


def test_the_haircut_still_runs_before_the_bar():
    """The ordering this whole file is about. If someone moves
    apply_selection after the gate, these tests stop meaning anything."""
    import inspect
    from engine import betting
    src = inspect.getsource(betting.evaluate_prop)
    assert src.index("apply_selection(") < src.index("gate_ok = ")
    assert src.index("temper_edge(") < src.index("apply_selection(")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
