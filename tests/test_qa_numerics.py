"""Hand-computed checks of the money math — the QA audit's Phase 2 core.

Every expected value below was worked by hand from the formula's
definition (not copied from the function's output), so a regression
that changes a sign, a rounding, or a threshold boundary lands here.
Margins are explicit where floats are compared.

Run directly: `python3 tests/test_qa_numerics.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import odds as O                                   # noqa: E402
from engine import betting as B                                # noqa: E402
from engine import staking as S                                # noqa: E402
from engine import parlays as P                                # noqa: E402
from engine.ledger import _bet_clv, _bet_price_clv, process_grade  # noqa: E402

EPS = 1e-6


def close(a, b, eps=EPS):
    assert abs(a - b) < eps, (a, b)


# --- odds conversions ---------------------------------------------------------
def test_american_to_implied_probability_by_hand():
    close(O.american_to_prob(-110), 110 / 210)        # 0.5238095
    close(O.american_to_prob(+150), 100 / 250)        # 0.4
    close(O.american_to_prob(-100), 0.5)
    close(O.american_to_prob(+100), 0.5)
    close(O.american_to_prob(+400), 0.2)
    close(O.american_to_prob(-200), 2 / 3)
    close(O.american_to_prob(-1000), 1000 / 1100)     # 0.909090


def test_american_to_decimal_by_hand():
    close(O.american_to_decimal(-110), 1 + 100 / 110)  # 1.909090
    close(O.american_to_decimal(+150), 2.5)
    close(O.american_to_decimal(-100), 2.0)
    close(O.american_to_decimal(+100), 2.0)
    # The parlay module keeps its own copy; the two must agree.
    for o in (-110, +150, -100, +100, +400, -250):
        close(P.american_to_decimal(o), O.american_to_decimal(o))


def test_decimal_to_american_round_trips_and_the_even_money_seam():
    assert P.decimal_to_american(2.5) == 150
    assert P.decimal_to_american(2.0) == 100          # exactly even money
    assert P.decimal_to_american(1 + 100 / 110) == -110
    assert P.decimal_to_american(1.5) == -200
    for o in (-110, -150, -250, +120, +300, +100):
        assert P.decimal_to_american(P.american_to_decimal(o)) == o, o
    # -100 and +100 are the same price (decimal 2.0); a decimal cannot
    # remember which spelling it came from, so the round trip lands on
    # +100. Equivalent money, a display seam only — logged in QA_AUDIT.md.
    assert P.decimal_to_american(P.american_to_decimal(-100)) == 100


# --- vig removal --------------------------------------------------------------
def test_devig_two_way_by_hand():
    over, under = O.devig_two_way(-110, -110)
    close(over, 0.5); close(under, 0.5)
    # -120 / +100: implied 0.545454 and 0.5, sum 1.045454
    over, under = O.devig_two_way(-120, +100)
    close(over, (6 / 11) / (6 / 11 + 0.5))            # 0.521739
    close(under, 0.5 / (6 / 11 + 0.5))                 # 0.478261
    close(over + under, 1.0)


def test_one_sided_devig_uses_the_documented_hold_and_sums_to_one():
    over, under = O.devig_two_way(+400, 0)
    close(over, 0.2 / O.ONE_SIDED_HOLD)                # 0.188679 at 1.06
    close(over + under, 1.0)
    assert O.ONE_SIDED_HOLD == 1.06, "the documented one-sided hold moved"


def test_an_impossible_pair_is_treated_as_one_sided():
    """+850 / -110 sums to 63% implied — a fabricated under. Devigging
    it as a real pair inflated both fairs (the 'Under 0.5 Home Runs'
    incident); it must price like the one-sided +850 it really is."""
    over, _ = O.devig_two_way(+850, -110)
    one_sided, _ = O.devig_two_way(+850, 0)
    close(over, one_sided)


# --- expected value and its sign ----------------------------------------------
def test_expected_value_sign_convention_by_hand():
    # p=0.55 at -110: win 0.909090; EV = 0.55*0.909090 - 0.45 = +0.05
    close(O.expected_value(0.55, -110), 0.55 * (100 / 110) - 0.45)
    assert O.expected_value(0.55, -110) > 0
    # a fair coin at -110 loses the juice: 0.5*0.909090 - 0.5 = -0.045454
    close(O.expected_value(0.5, -110), -0.5 / 11)
    assert O.expected_value(0.5, -110) < 0
    # exactly break-even: p equal to the implied probability → EV 0
    close(O.expected_value(110 / 210, -110), 0.0)
    # stake scales linearly
    close(O.expected_value(0.55, -110, stake=3), 3 * O.expected_value(0.55, -110))


def test_net_edge_is_model_minus_break_even_not_minus_fair():
    close(B.net_edge(0.55, -110), 0.55 - 110 / 210)   # +0.026190
    close(B.net_edge(0.5, -110), 0.5 - 110 / 210)     # -0.023809 (juice)


# --- Kelly and fractional Kelly ----------------------------------------------
def test_kelly_fraction_by_hand_and_never_negative():
    # b = 0.909090; f = (b*p - q)/b = (0.5 - 0.45)/0.909090 = 0.055
    close(S.kelly_fraction(0.55, -110), (100 / 110 * 0.55 - 0.45) / (100 / 110))
    assert S.kelly_fraction(0.5, -110) == 0.0          # edge < 0 → 0, not negative
    assert S.kelly_fraction(110 / 210, -110) < 1e-9     # break-even → 0 (float noise ≤ 1e-9)
    assert S.kelly_fraction(0.0, +100) == 0.0
    assert S.kelly_fraction(1.0, +100) == 1.0


def test_stake_units_are_zero_at_no_edge_and_capped_otherwise():
    assert S.kelly_units(0.5, -110) == 0.0
    assert S.kelly_units(0.40, +100) == 0.0
    u = S.kelly_units(0.55, -110)
    assert u > 0
    for p in (0.0, 0.3, 0.5, 0.55, 0.7, 0.9, 1.0):
        for o in (-1000, -250, -110, +100, +250, +800):
            got = S.kelly_units(p, o)
            assert got >= 0.0, (p, o, got)
            assert got <= S.MAX_PRICED_U, (p, o, got)
    # The bankroll ceiling is a real cap: a certainty at a long price
    # still cannot exceed it.
    assert S.kelly_units(1.0, +800) <= S.MAX_PRICED_U


# --- CLV direction -------------------------------------------------------------
def test_line_clv_is_positive_when_the_market_moved_our_way():
    over = {"closing_line": 62.5, "line": 60.5, "side": "OVER"}
    under = {"closing_line": 62.5, "line": 60.5, "side": "UNDER"}
    assert _bet_clv(over) == 2.0
    assert _bet_clv(under) == -2.0
    assert _bet_clv({"closing_line": None, "line": 60.5, "side": "OVER"}) is None
    assert process_grade(over) == "good"
    assert process_grade(under) == "bad"
    assert process_grade({"closing_line": 60.5, "line": 60.5,
                          "side": "OVER"}) == "flat"


def test_price_clv_is_positive_when_the_close_is_shorter_than_we_took():
    # took -110 (0.523810), closed -130 (0.565217): +0.041408 points
    b = {"closing_odds": -130, "odds": -110}
    close(_bet_price_clv(b), 130 / 230 - 110 / 210)
    assert _bet_price_clv(b) > 0
    # took +400 (0.2), closed +500 (0.166667): the market moved AWAY
    assert _bet_price_clv({"closing_odds": 500, "odds": 400}) < 0
    assert _bet_price_clv({"closing_odds": None, "odds": -110}) is None
    assert _bet_price_clv({"closing_odds": -130, "odds": 0}) is None


# --- parlay pricing and the leg cap ------------------------------------------
def test_three_leg_parlay_price_by_hand():
    dec = P.american_to_decimal(-110) ** 3             # 6.958696
    assert P.decimal_to_american(dec) == 596           # (6.958696-1)*100 = 595.87
    dec2 = P.american_to_decimal(-110) * P.american_to_decimal(+150)
    close(dec2, (1 + 100 / 110) * 2.5)                 # 4.772727
    assert P.decimal_to_american(dec2) == 377


def test_the_leg_cap_is_three_and_the_engine_never_builds_past_it():
    assert P.MAX_LEGS == 3
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "parlays.py"),
        encoding="utf-8").read()
    assert "max_legs: int = MAX_LEGS" in src
    assert "for k in (2, min(rules.max_legs, 3)):" in src, \
        "ticket sizes are enumerated past the cap"


# --- grade thresholds, exactly on the boundary --------------------------------
def test_grade_boundaries_land_where_the_table_says():
    assert B.BASE_THRESHOLDS == (("Strong Play", 8.0, 0.020), ("Play", 6.5, 0.010))
    assert B._grade(8.0, 0.020) == "Strong Play"       # exactly on both
    assert B._grade(8.0, 0.0199999) == "Play"          # a hair under net → next tier
    assert B._grade(7.9999, 0.05) == "Play"            # a hair under confidence
    assert B._grade(6.5, 0.010) == "Play"              # exactly on both
    assert B._grade(6.5, 0.0099999) == "Pass"
    assert B._grade(6.4999, 0.10) == "Pass"
    assert B._grade(0.0, 0.0) == "Pass"


def test_the_favourite_surcharge_by_hand():
    # -200 → implied 0.666667; surcharge = 0.18 * (0.666667 - 0.55) = 0.021
    close(B.favourite_surcharge(-200), 0.18 * (2 / 3 - 0.55))
    assert B.favourite_surcharge(+150) == 0.0          # under the 55% floor
    close(B.favourite_surcharge(-122.2222), 0.0, eps=1e-3)  # right at 55%
    # At -200, Strong Play needs 0.020 + 0.021 = 0.041 of net edge.
    assert B._grade(9.0, 0.040, odds=-200) == "Play"
    assert B._grade(9.0, 0.042, odds=-200) == "Strong Play"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
