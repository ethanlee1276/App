"""Phase 3 of the MLB readiness audit: the arithmetic, checked by hand.

Ethan's MLB readiness brief (2026-09-01): "Write tests with hand-computed
expected values and keep them" — price conversions at long-shot HR prices
and heavy favourites, de-vigging by market type, EV sign, Kelly at zero
edge and the slate cap, CLV direction, grade boundaries, parlay odds and
the fourth leg, the Poisson conversion for home runs, and plate
appearances by lineup slot. Every expected number below was worked on
paper before the assertion was written; where the code and the paper
disagreed, the paper won and a finding went in MLB_READINESS.md.

Run directly: `python3 tests/test_mlb_readiness_math.py`
"""

import inspect
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import parlays as P
from engine.correlation import apply_exposure_caps, GAME_CAP_U, SLATE_CAP_U
from engine.devig import (expected_distinct_hr_hitters, fair_probability,
                          hold_multiplier)
from engine.longshots import prob_at_least_one
from engine.mlb import homeruns as HR
from engine.mlb.quality import MLB_QUALITY_FLOOR, mlb_letter
from engine.odds import (ONE_SIDED_HOLD, american_to_decimal, american_to_prob,
                         devig_two_way, expected_value, pair_is_sane)
from engine.staking import kelly_fraction, kelly_units
from engine import mlbrecord


def close(a, b, tol=1e-4):
    return abs(a - b) <= tol


# --- price conversions -------------------------------------------------------
def test_long_shot_hr_prices_convert_by_hand():
    # +300 → 100/400; +650 → 100/750; +1000 → 100/1100
    assert close(american_to_prob(300), 0.25)
    assert close(american_to_prob(650), 0.133333)
    assert close(american_to_prob(1000), 0.090909)
    assert american_to_decimal(300) == 4.0
    assert american_to_decimal(1000) == 11.0


def test_heavy_favourites_do_not_overflow_or_divide_by_zero():
    assert close(american_to_prob(-2000), 2000 / 2100)
    assert close(american_to_decimal(-2000), 1.05)
    # ±100 are the same coin and neither is a division by zero
    assert american_to_prob(-100) == 0.5 == american_to_prob(100)
    assert american_to_decimal(-100) == 2.0 == american_to_decimal(100)


def test_decimal_to_american_round_trips_the_parlay_prices():
    assert P.decimal_to_american(4.0) == 300
    assert P.decimal_to_american(1.05) == -2000
    assert P.decimal_to_american(2.0) == -100        # Ethan's spelling, QA audit


# --- de-vig by market type ---------------------------------------------------
def test_a_two_sided_market_normalises_the_pair():
    # −115 / −105: .534884 + .512195 = 1.047079; over = .534884 / 1.047079
    over, under = devig_two_way(-115, -105)
    assert close(over, 0.510834) and close(over + under, 1.0)


def test_a_one_sided_hr_market_divides_by_the_measured_or_assumed_hold():
    # +400 quoted alone: raw .20, assumed hold 1.06 → .188679
    over, _ = devig_two_way(400, 0)
    assert close(over, 0.20 / ONE_SIDED_HOLD)
    assert ONE_SIDED_HOLD == 1.06


def test_a_fabricated_under_is_not_normalised_against():
    """The naive method the brief warns about: pair +400 with a fake −110
    under and normalise. That says .2000 / (.2000 + .5238) = .2763 — the
    "fair" HR probability goes UP by six points and the EV filter would
    pass bad bets. The pair is impossible (sums to .72 < .95) and the
    code treats it as one-sided, same answer as no under at all."""
    assert not pair_is_sane(400, -110)
    assert devig_two_way(400, -110) == devig_two_way(400, 0)
    naive = 0.2 / (0.2 + american_to_prob(-110))
    assert close(naive, 0.2763, 1e-3) and naive > devig_two_way(400, 0)[0]


def test_the_market_sum_method_measures_the_hr_boards_own_hold():
    # a 9-run total supports 9 × .25 × .95 = 2.1375 distinct HR hitters
    assert close(expected_distinct_hr_hitters(9.0), 2.1375)
    implied = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.4, 0.45]      # sums to 2.8
    mult = hold_multiplier(implied, 2.1375)
    assert close(mult, 2.8 / 2.1375)                            # 1.3099
    assert close(fair_probability(0.2, mult), 0.152679)
    # a board whose prices sum to FEWER hitters than the total supports
    # has no hold to measure — None, never a multiplier below 1
    assert hold_multiplier([0.2] * 8, 2.1375) is None
    # and fewer than MIN_PRICED hitters is unmeasurable too
    assert hold_multiplier([0.3] * 5, 2.1375) is None


# --- EV and Kelly ------------------------------------------------------------
def test_ev_sign_against_a_known_losing_bet():
    # 35% at +150: .35 × 1.5 − .65 = −.125 (losing); 45%: +.125
    assert close(expected_value(0.35, 150), -0.125)
    assert close(expected_value(0.45, 150), +0.125)


def test_kelly_is_zero_at_and_below_the_break_even():
    assert kelly_fraction(0.5, -110) == 0.0          # (.909×.5 − .5)/.909 < 0
    assert kelly_units(0.5, -110) == 0.0
    assert kelly_units(0.2, 400) == 0.0              # exactly break-even
    assert close(kelly_fraction(0.25, 400), 0.0625)  # (4×.25 − .75)/4


def test_kelly_only_vetoes_the_price_ladder_sizes():
    # +400 sizes at 1.0 × (1.909 / 5.0) = .38u whatever the edge above zero
    assert kelly_units(0.25, 400) == 0.38
    assert kelly_units(0.40, 400) == 0.38
    assert kelly_units(0.60, -110) == 1.0            # the base unit


def test_the_slate_cap_is_a_total_not_a_per_bet_number():
    """Twenty qualifying props on a fifteen-game night ask 20u; the slate
    cap is 15u and every stake is scaled by the same 0.75."""
    recs = [dict(recommended=True, stake_units=1.0, team=f"T{i}",
                 opponent=f"O{i}", game_date="2026-09-02", player=f"p{i}",
                 market="hits") for i in range(20)]
    apply_exposure_caps(recs, [])
    assert SLATE_CAP_U == 15.0
    assert close(sum(r["stake_units"] for r in recs), 15.0)
    assert all(r["stake_units"] == 0.75 for r in recs)


def test_the_game_cap_binds_a_crowded_fixture():
    recs = [dict(recommended=True, stake_units=1.0, team="PHI", opponent="CHC",
                 game_date="2026-09-02", player=f"p{i}", market="hits")
            for i in range(6)]
    apply_exposure_caps(recs, [])
    assert GAME_CAP_U == 5.0
    assert sum(r["stake_units"] for r in recs) <= 5.0 + 1e-9


# --- CLV ---------------------------------------------------------------------
def test_price_clv_is_positive_when_the_close_is_shorter():
    # HR over taken +400 (.2000), closed +350 (.2222): +2.22 points
    b = {"odds": 400, "closing_odds": 350}
    assert close(mlbrecord.price_clv(b), 0.022222)
    assert mlbrecord.price_clv({"odds": 400, "closing_odds": 450}) < 0
    assert mlbrecord.price_clv({"odds": 400, "closing_odds": None}) is None


def test_the_ledger_and_the_record_tool_agree_on_clv():
    from engine.ledger import _bet_price_clv
    b = {"odds": 400, "closing_odds": 350}
    assert close(_bet_price_clv(b), mlbrecord.price_clv(b))


def test_line_clv_cannot_see_a_home_run_prop_but_price_clv_can():
    """A 0.5 HR line closes at 0.5 forever. Line CLV is 0 on every HR
    bet; the instrument for that market is the price."""
    from engine.ledger import _bet_clv
    assert _bet_clv({"closing_line": 0.5, "line": 0.5, "side": "OVER"}) == 0.0
    assert mlbrecord.price_clv({"odds": 400, "closing_odds": 350}) != 0.0


def test_clv_on_devigged_probabilities_keeps_the_sign_of_raw_clv():
    """The brief asks for CLV "computed on de-vigged probabilities". The
    journal's price CLV is on RAW implied probabilities. With one hold on
    both sides the de-vigged difference is the raw difference divided by
    the hold — same sign, smaller magnitude — so the direction the
    verdict rests on is unaffected. Logged as a P3 in MLB_READINESS.md."""
    raw = american_to_prob(350) - american_to_prob(400)
    devigged = (american_to_prob(350) - american_to_prob(400)) / ONE_SIDED_HOLD
    assert raw > 0 and devigged > 0 and close(devigged, raw / 1.06)


# --- grades ------------------------------------------------------------------
def test_mlb_grade_boundaries_exactly():
    assert MLB_QUALITY_FLOOR == 66.0
    assert mlb_letter(65.99) == "Pass" and mlb_letter(66.0) == "B+"
    assert mlb_letter(79.99) == "B+" and mlb_letter(80.0) == "A"
    assert mlb_letter(89.99) == "A" and mlb_letter(90.0) == "A+"


# --- parlays -----------------------------------------------------------------
def test_two_and_three_leg_combined_odds():
    d = american_to_decimal(-110)                    # 1.90909
    assert P.decimal_to_american(d * d) == 264       # 3.6446 → +264
    assert P.decimal_to_american(d * d * d) == 596   # 6.9579 → +596


def test_a_fourth_leg_is_refused_at_the_ceiling():
    assert P.MAX_LEGS == 3
    legs = [dict(player=f"H{i}", team="PHI", opponent="CHC", market="hits",
                 side="OVER", line=0.5, odds=-110) for i in range(4)]
    out = P.check_ticket("mlb", legs)
    assert out["ok"] is False and "3 legs is the ceiling" in out["reason"]
    assert P.check_ticket("mlb", legs[:3])["ok"] is True


def test_two_hr_props_from_one_lineup_are_priced_as_correlated():
    """The brief's worst case: "a parlay of correlated HR props priced as
    independent legs". The taxonomy carries +0.186 measured on 27,613
    games of lineup stacks. Until 2026-09-02 the slip allowed the pair
    with that number as a warning and printed the independent price;
    Ethan closed A-3 ("use hr just not players on the same team in the
    same game"), so the slip now refuses the pair outright."""
    a = dict(player="A", team="PHI", opponent="CHC", market="home_runs",
             side="OVER", line=0.5, odds=400, game_date="2026-09-02")
    b = dict(player="B", team="PHI", opponent="CHC", market="home_runs",
             side="OVER", line=0.5, odds=350, game_date="2026-09-02")
    r = P.relate("mlb", a, b)
    assert r.verdict == "ok" and r.measured and close(r.rho, 0.186, 1e-3)
    out = P.check_ticket("mlb", [a, b])
    assert out["ok"] is False and out["reason"] == P.SAME_LINEUP_HR_REASON
    # the same two bats on opposite sides of the game are two lineups
    b2 = dict(b, team="CHC", opponent="PHI")
    assert P.check_ticket("mlb", [a, b2])["ok"] is True


def test_an_hr_prop_and_the_opposing_strikeout_over_is_killed():
    a = dict(player="A", team="PHI", opponent="CHC", market="home_runs",
             side="OVER", line=0.5, odds=400)
    k = dict(player="P", team="CHC", opponent="PHI", market="strikeouts",
             side="OVER", line=6.5, odds=-115)
    r = P.relate("mlb", a, k)
    assert r.verdict == "kill" and r.clash == 7


def test_an_hr_prop_and_the_game_over_is_a_prior_not_a_measurement():
    """Allowed and named at +0.10 — but that number is a floor from §1.1,
    not a measurement. Finding, not a defect: the pair is disclosed."""
    a = dict(player="A", team="PHI", opponent="CHC", market="home_runs",
             side="OVER", line=0.5, odds=400)
    t = dict(home="PHI", away="CHC", market="total", side="OVER", line=8.5,
             odds=-110)
    r = P.relate("mlb", a, t)
    assert r.verdict == "ok" and not r.measured and r.rho > 0


def test_the_engines_own_tickets_refuse_hr_legs_outright():
    assert "home_runs" in P.EXTREME_MARKETS


# --- Poisson and plate appearances ------------------------------------------
def test_at_least_one_is_one_minus_exp_not_lambda_times_pa():
    # λ = 0.2 → 1 − e^−0.2 = .181269; the naive "λ" overstates by 1.9 pts
    assert close(prob_at_least_one(0.2), 1 - math.exp(-0.2))
    assert close(prob_at_least_one(0.2), 0.181269)
    assert prob_at_least_one(0.0) == 0.0 and prob_at_least_one(-1) == 0.0


def test_the_hr_model_converts_a_per_game_rate_through_poisson():
    src = inspect.getsource(HR.hr_probability)
    assert "pa = plate_appearances(" in src
    assert "prob = prob_at_least_one(rate)" in src
    # per-PA rate × PA is the Poisson rate, never the probability
    assert "rate = " in src


def test_plate_appearances_fall_down_the_order():
    spots = [HR.plate_appearances(s) for s in range(1, 10)]
    assert spots[0] == 4.6 and spots[-1] == 3.7
    assert all(a > b for a, b in zip(spots, spots[1:]))
    assert HR.plate_appearances(0) == HR.DEFAULT_PA == 4.0


def test_plate_appearances_do_not_yet_know_home_from_away():
    """The brief: PAs depend on "home/away (a home team may not bat in the
    ninth)". They do not here — the function takes the slot alone. Pinned
    so the gap is visible; it is a Phase 3 finding, not a silent
    assumption."""
    sig = inspect.signature(HR.plate_appearances)
    assert list(sig.parameters) == ["spot"]


def test_two_pa_tables_disagree_and_that_is_logged():
    """`homeruns.PA_BY_SPOT` prices real money; `gamesim.PA_BY_SPOT` is the
    (disabled) joint sim's. They differ by 0.05–0.15 PA per slot. Neither is
    changed here (brief rule 2); the finding is in MLB_READINESS.md."""
    from engine.mlb import gamesim
    diffs = {s: gamesim.PA_BY_SPOT[s] - HR.PA_BY_SPOT[s] for s in range(1, 10)}
    assert all(0.0 < d <= 0.15 + 1e-9 for d in diffs.values()), diffs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
