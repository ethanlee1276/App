"""Staking invariants — the rules that keep "bet 0.00 units" impossible.

The bug these lock down: grades were scored against the DE-VIGGED fair
probability while Kelly was scored against the price actually charged.
At standard −110/−110 juice break-even sits ~2.4 points above fair, so a
"Lean" at +1.2 points over fair was a 1.2-point LOSS at the window —
recommended on the board, then sized by Kelly at 0.00 units, then
journaled as a bet that could never win or lose a unit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.betting import (MARKET_SHRINK, MAX_CREDIBLE_EDGE, MIN_STAKE_UNITS,
                            _grade, _kelly_stake, favourite_surcharge, net_edge)
from engine.odds import american_to_prob, devig_two_way, expected_value

PRICES = (-200, -140, -120, -115, -110, -105, 100, 120, 150, 250, 400)
PROBS = [x / 200.0 for x in range(20, 190)]      # 0.10 … 0.945


def test_net_edge_is_measured_against_the_real_price():
    # At −110/−110 the fair number is 50% but you must clear 52.38%.
    fair_over, _ = devig_two_way(-110, -110)
    assert abs(fair_over - 0.5) < 1e-9
    assert abs(american_to_prob(-110) - 0.5238) < 1e-4
    # A model at 51.5% beats "fair" by 1.5 pts but LOSES to the price.
    assert 0.515 - fair_over > 0.01
    assert net_edge(0.515, -110) < 0
    assert expected_value(0.515, -110) < 0


def test_no_graded_bet_is_ever_unsizeable():
    """Every bet the board grades must be one Kelly will stake."""
    offenders = [(p, o) for o in PRICES for p in PROBS
                 for conf in (4.5, 6.5, 8.0, 10.0)
                 if _grade(conf, net_edge(p, o), o) != "Pass"
                 and _kelly_stake(p, o) <= 0]
    assert not offenders, f"graded but unsizeable: {offenders[:5]}"


def test_no_graded_bet_is_ever_negative_ev():
    offenders = [(p, o) for o in PRICES for p in PROBS
                 for conf in (4.5, 6.5, 8.0, 10.0)
                 if _grade(conf, net_edge(p, o), o) != "Pass"
                 and expected_value(p, o) <= 0]
    assert not offenders, f"graded but −EV: {offenders[:5]}"


def test_positive_kelly_never_rounds_away_to_zero():
    """A real edge must never render as 0.00u — the floor exists so the
    display and the journal agree that this is a bet."""
    for o in PRICES:
        be = american_to_prob(o)
        for bump in (0.0005, 0.001, 0.003, 0.01):
            p = be + bump
            if p >= 1.0:
                continue
            s = _kelly_stake(p, o)
            assert s >= MIN_STAKE_UNITS, (o, p, s)
    # Below break-even Kelly still says zero, loudly and correctly.
    for o in PRICES:
        assert _kelly_stake(american_to_prob(o) - 0.01, o) == 0.0


def test_stake_scales_with_edge_and_stays_capped():
    small = _kelly_stake(0.53, -110)
    mid = _kelly_stake(0.56, -110)
    big = _kelly_stake(0.75, -110)
    assert MIN_STAKE_UNITS <= small < mid < big <= 1.0


def test_grade_ladder_requires_real_net_edge():
    # Thresholds are net of the vig now: at −110 these are the model
    # probabilities each tier demands.
    assert _grade(10.0, net_edge(0.520, -110), -110) == "Pass"   # below the price
    assert _grade(10.0, net_edge(0.528, -110), -110) == "Lean"
    assert _grade(10.0, net_edge(0.535, -110), -110) == "Play"
    assert _grade(10.0, net_edge(0.546, -110), -110) == "Strong Play"
    # Confidence still gates independently of price edge.
    assert _grade(3.0, net_edge(0.600, -110), -110) == "Pass"


def test_favourite_surcharge_targets_the_measured_failure():
    """The journal showed favourites hitting 45.7% against a 66.9%
    break-even (p=0.001) while underdogs held up. The surcharge must
    therefore bite on chalk and leave everything else alone."""
    # Underdogs and near-even prices: untouched.
    for o in (250, 150, 120, 100, -105, -110, -120):
        assert favourite_surcharge(o) == 0.0 or favourite_surcharge(o) < 0.001, o
    # Requirement climbs monotonically as the price shortens.
    sur = [favourite_surcharge(o) for o in (-140, -170, -200, -235, -300)]
    assert sur == sorted(sur) and sur[0] > 0 and sur[-1] > sur[0]


def test_heavy_chalk_is_unreachable_even_at_a_maximum_edge():
    """−235 and shorter is the band that produced a −40% ROI. Even the
    largest edge the model is allowed to claim must not grade there."""
    def best_possible_net(o, u):
        fair, _ = devig_two_way(o, u)
        best_hit = fair + MARKET_SHRINK * MAX_CREDIBLE_EDGE
        return best_hit - american_to_prob(o)
    for o, u in ((-235, 195), (-300, 250), (-400, 320)):
        net = best_possible_net(o, u)
        assert _grade(10.0, net, o) == "Pass", (o, net)
    # Moderate favourites stay reachable — this is a surcharge, not a ban.
    for o, u in ((-140, 120), (-170, 145), (-200, 170)):
        assert _grade(10.0, best_possible_net(o, u), o) != "Pass", o


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
