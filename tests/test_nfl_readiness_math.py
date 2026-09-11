"""NFL readiness audit, Phase 3 — the arithmetic, done by hand first.

Every expected number here was worked on paper BEFORE the function was
called, from the formula the docs state, so a test that fails is the
code disagreeing with the formula and not the formula being copied
back out of the code. Where a value is irrational the expectation is
given to the precision the hand working reaches and compared with a
tolerance that is tighter than any plausible bug.

Rule from the brief: "leak-free or don't report ROI; never fabricate;
too-good = bug". None of these depend on a backtest.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import odds as O
from engine import parlays as P
from engine import staking as S
from engine import betting as B
from engine import correlation as C
from engine import devig as D
from engine import social
from engine.ledger import _bet_clv, _bet_price_clv, implied_breakeven


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


# --- American odds ---------------------------------------------------------
# Hand: −110 → 110/210 = 0.523809…; +100 → 100/200 = 0.5; −100 → same;
# +600 → 100/700 = 0.142857…; decimal −110 = 1 + 100/110 = 1.909090…;
# +600 = 7.0.

def test_minus_110_implies_52_38_percent():
    assert close(O.american_to_prob(-110), 110 / 210)
    assert close(O.american_to_decimal(-110), 1 + 100 / 110)


def test_plus_100_and_minus_100_are_the_same_price():
    assert close(O.american_to_prob(100), 0.5)
    assert close(O.american_to_prob(-100), 0.5)
    assert close(O.american_to_decimal(100), 2.0)
    assert close(O.american_to_decimal(-100), 2.0)
    assert close(P.american_to_decimal(100), 2.0)
    assert close(P.american_to_decimal(-100), 2.0)


def test_plus_600_is_one_in_seven():
    assert close(O.american_to_prob(600), 1 / 7)
    assert close(O.american_to_decimal(600), 7.0)


def test_decimal_back_to_american_round_trips_the_longshot_and_even_money():
    """Even money is spelled −100 (Ethan, 2026-09-01: "2. b")."""
    assert P.decimal_to_american(7.0) == 600
    assert P.decimal_to_american(2.0) == -100
    assert P.decimal_to_american(1 + 100 / 110) == -110
    assert D.american(1 / 7) == 600
    assert D.american(0.5) == 100 or D.american(0.5) == -100


# --- Two-way de-vig ----------------------------------------------------------
# Hand: −110/−110 → 0.5238 each, sum 1.0476, fair 0.5/0.5.
#       −130/+110 → 130/230 = 0.565217, 100/210 = 0.476190, sum 1.041408;
#       fair over = 0.565217/1.041408 = 0.542744.

def test_a_symmetric_two_way_market_devigs_to_a_coin_flip():
    o, u = O.devig_two_way(-110, -110)
    assert close(o, 0.5) and close(u, 0.5)


def test_an_asymmetric_two_way_market_devigs_to_the_hand_number():
    o, u = O.devig_two_way(-130, 110)
    assert close(o, (130 / 230) / (130 / 230 + 100 / 210), 1e-9)
    assert close(o, 0.542744, 1e-6)
    assert close(o + u, 1.0)


def test_a_one_sided_quote_uses_the_documented_six_percent_hold():
    """Over-only at +600: raw 1/7 = 0.142857, /1.06 = 0.134771."""
    o, _ = O.devig_two_way(600, 0)
    assert close(o, (1 / 7) / 1.06, 1e-9)
    assert close(o, 0.134771, 1e-6)


# --- Anytime-TD market-sum de-vig -------------------------------------------
# A board of eight priced scorers on a game whose lines support 5.0
# expected distinct scorers. Hand: implied sum 5.6 → proportional
# multiplier 1.12, overround +12%; the +600 man's fair is
# 0.142857/1.12 = 0.127551 (−1.5 points off naive), the −150 favourite
# (0.6) goes to 0.535714.

BOARD = [0.60, 0.60, 0.55, 0.50, 0.45, 0.40, 0.30, 0.20]   # sum 3.60


def test_the_market_sum_hold_is_sum_over_expected_scorers():
    # 3.60 / 3.20 = 1.125 exactly
    assert close(D.hold_multiplier(BOARD, 3.2), 1.125)
    assert close(D.fair_probability(0.6, 1.125), 0.6 / 1.125)
    assert close(D.fair_probability(0.6, 1.125), 0.533333, 1e-6)


def test_a_thin_board_or_a_holdless_board_is_unmeasurable_not_one():
    """Five prices is under MIN_PRICED; a sum at or below the expected
    scorers is a book with no hold, which does not happen."""
    assert D.hold_multiplier(BOARD[:5], 3.2) is None
    assert D.hold_multiplier(BOARD, 3.6) is None
    assert D.hold_multiplier(BOARD, 4.0) is None
    assert close(D.fair_probability(0.6, None), 0.6)


def test_the_power_exponent_solves_the_stated_equation():
    k = D.power_exponent(BOARD, 3.2)
    assert k is not None and 1.0 < k < 8.0
    assert close(sum(p ** k for p in BOARD), 3.2, 1e-9)


def test_power_devig_takes_more_off_the_longshot_than_proportional_does():
    """The whole reason the power method exists: the book's margin sits
    on the long prices. At the same overround, a +600 (0.142857) must
    lose MORE under power than under proportional, and the −150 (0.6)
    must lose LESS."""
    dv = D.game_devig(BOARD, 3.2, method=D.POWER)
    pr = D.game_devig(BOARD, 3.2, method=D.PROPORTIONAL)
    assert dv.kind == D.POWER and pr.kind == D.PROPORTIONAL
    assert close(pr.overround, 0.125) and close(dv.overround, 0.125)
    long_naive, fav_naive = 1 / 7, 0.6
    assert dv.fair(long_naive) < pr.fair(long_naive) < long_naive
    assert pr.fair(fav_naive) < dv.fair(fav_naive) < fav_naive


def test_a_devig_object_never_moves_an_impossible_probability():
    dv = D.Devig.proportional(1.125)
    assert dv.fair(0.0) == 0.0 and dv.fair(1.0) == 1.0


# --- Expected value ----------------------------------------------------------
# Hand at +600, 1u: p·6 − (1−p). p = 0.10 → 0.6 − 0.9 = −0.30;
# p = 1/7 → 0.857143 − 0.857143 = 0; p = 0.20 → 1.2 − 0.8 = +0.40.
# At −110: p = 0.55 → 0.55·0.909091 − 0.45 = 0.5 − 0.45 = +0.05.

def test_ev_at_plus_600_changes_sign_exactly_at_one_in_seven():
    assert close(O.expected_value(0.10, 600), -0.30)
    assert close(O.expected_value(1 / 7, 600), 0.0)
    assert close(O.expected_value(0.20, 600), 0.40)


def test_ev_at_minus_110_is_five_cents_at_fifty_five_percent():
    assert close(O.expected_value(0.55, -110), 0.55 * (100 / 110) - 0.45)
    assert close(O.expected_value(0.55, -110), 0.05)


def test_the_breakeven_rate_is_the_implied_probability():
    assert close(implied_breakeven(-110), 110 / 210)
    assert close(implied_breakeven(600), 1 / 7)
    assert implied_breakeven(0) is None and implied_breakeven("x") is None


# --- Kelly ---------------------------------------------------------------------
# Hand: f = (b·p − q)/b. At −110, b = 0.909091: p = 0.55 → (0.5 − 0.45)/
# 0.909091 = 0.055; p = 0.5238 (the implied) → 0; p = 0.50 → negative → 0.
# At +600, b = 6: p = 0.20 → (1.2 − 0.8)/6 = 0.066667; p = 0.10 → 0.

def test_kelly_is_the_textbook_fraction_at_minus_110():
    assert close(S.kelly_fraction(0.55, -110), 0.055, 1e-9)


def test_kelly_is_zero_not_negative_when_the_price_beats_the_edge():
    assert S.kelly_fraction(0.50, -110) == 0.0
    assert S.kelly_fraction(0.10, 600) == 0.0
    assert close(S.kelly_fraction(110 / 210, -110), 0.0, 1e-12)
    assert S.kelly_units(0.50, -110) == 0.0
    assert S.kelly_units(0.10, 600) == 0.0


def test_kelly_at_plus_600_with_a_real_edge():
    assert close(S.kelly_fraction(0.20, 600), (6 * 0.2 - 0.8) / 6)
    assert close(S.kelly_fraction(0.20, 600), 0.0666667, 1e-6)


def test_the_price_ladder_stakes_by_price_not_by_conviction():
    """s ∝ 1/d normalised to 1u at −110: +600 → 1.909/7 = 0.2727u,
    floored at 0.35u; −300 (d 1.3333) → 1.909/1.3333 = 1.4318, capped
    at 1.25u; −110 itself → 1.00u."""
    assert close(S.units_for_price(-110), 1.0)
    assert close(S.units_for_price(600), S.MIN_PRICED_U)
    assert close(S.units_for_price(-300), S.MAX_PRICED_U)
    # a bigger Kelly fraction cannot buy a bigger stake at the same price
    assert close(S.kelly_units(0.20, 600), S.kelly_units(0.40, 600))


# --- Grades ------------------------------------------------------------------
# BASE_THRESHOLDS: Strong Play needs conf ≥ 8.0 and net ≥ 0.020; Play
# needs conf ≥ 6.5 and net ≥ 0.010; otherwise Pass. Favourite surcharge
# 0.18 × max(0, implied − 0.55): at −110 implied 0.5238 → 0; at −200
# implied 0.6667 → 0.18 × 0.1167 = 0.021.

def test_grade_boundaries_are_inclusive_at_the_stated_numbers():
    assert B._grade(8.0, 0.020, -110) == "Strong Play"
    assert B._grade(7.99, 0.020, -110) == "Play"
    assert B._grade(8.0, 0.0199, -110) == "Play"
    assert B._grade(6.5, 0.010, -110) == "Play"
    assert B._grade(6.49, 0.010, -110) == "Pass"
    assert B._grade(6.5, 0.0099, -110) == "Pass"


def test_a_favourite_needs_more_net_edge_at_the_stated_slope():
    assert close(B.favourite_surcharge(-110), 0.0)
    assert close(B.favourite_surcharge(-200), 0.18 * (2 / 3 - 0.55), 1e-9)
    assert close(B.favourite_surcharge(-200), 0.021, 1e-9)
    # 0.020 clears Strong Play at −110 but not at −200 (needs 0.041)
    assert B._grade(8.0, 0.020, -200) == "Pass"
    assert B._grade(8.0, 0.031, -200) == "Play"
    assert B._grade(8.0, 0.041, -200) == "Strong Play"


# --- Exposure caps -------------------------------------------------------------
# Hand: three props in one game at 2u each = 6u > 5u cap → factor 5/6 =
# 0.8333, so 1.67u each. A slate of eight 2u bets across eight games is
# 16u > 15u → factor 15/16 = 0.9375. A 0.11u bet scaled by 5/6 is
# 0.0917 < 0.1 → dropped, not rounded to 0.09.

def _rec(team, opp, units, player="P"):
    return {"player": player, "team": team, "opponent": opp,
            "game_date": "2026-09-13", "recommended": True,
            "stake_units": units, "grade": "Play", "warnings": []}


def test_the_five_unit_game_cap_scales_every_leg_by_the_same_factor():
    recs = [_rec("KC", "LAC", 2.0, "a"), _rec("KC", "LAC", 2.0, "b"),
            _rec("LAC", "KC", 2.0, "c")]
    notes = C.apply_exposure_caps(recs, [])
    assert notes and "5u game cap" in notes[0]
    assert all(close(r["stake_units"], 1.67, 1e-9) for r in recs)
    assert close(sum(r["stake_units"] for r in recs), 5.0, 0.011)


def test_the_fifteen_unit_slate_cap_binds_when_no_game_does():
    teams = ["KC", "BUF", "PHI", "DAL", "SF", "DET", "GB", "MIA"]
    recs = [_rec(t, "X" + t, 2.0, t) for t in teams]
    notes = C.apply_exposure_caps(recs, [])
    assert notes and "15u cap" in notes[0]
    assert all(close(r["stake_units"], 1.88, 1e-9) for r in recs)   # 2 × 0.9375 = 1.875 → 1.88


def test_a_stake_that_scales_under_the_floor_is_dropped_not_rounded():
    recs = [_rec("KC", "LAC", 3.0, "a"), _rec("KC", "LAC", 3.0, "b"),
            _rec("KC", "LAC", 0.11, "c")]
    notes = C.apply_exposure_caps(recs, [])
    small = recs[2]
    assert small["recommended"] is False and small["stake_units"] == 0.0
    assert "1 bet(s) dropped" in notes[0]
    assert all(r["recommended"] for r in recs[:2])


def test_under_both_caps_nothing_moves():
    recs = [_rec("KC", "LAC", 2.0, "a"), _rec("BUF", "NYJ", 2.0, "b")]
    assert C.apply_exposure_caps(recs, []) == []
    assert all(r["stake_units"] == 2.0 for r in recs)


# --- Closing-line value ---------------------------------------------------------
# Hand: bet Over 62.5, closes 64.5 → +2.0; the same on an Under → −2.0.
# Price CLV: took +600 (0.142857), closed +500 (0.166667) → +0.02381:
# the market moved toward us. Took −110, closed +100 → 0.5 − 0.5238 =
# −0.0238: the market moved away.

def test_line_clv_is_signed_by_the_side():
    assert close(_bet_clv({"closing_line": 64.5, "line": 62.5, "side": "OVER"}), 2.0)
    assert close(_bet_clv({"closing_line": 64.5, "line": 62.5, "side": "UNDER"}), -2.0)
    assert _bet_clv({"closing_line": None, "line": 62.5, "side": "OVER"}) is None


def test_price_clv_is_positive_when_the_close_is_shorter_than_the_price_taken():
    assert close(_bet_price_clv({"closing_odds": 500, "odds": 600}), 1 / 6 - 1 / 7)
    assert close(_bet_price_clv({"closing_odds": 500, "odds": 600}), 0.0238095, 1e-6)
    assert close(_bet_price_clv({"closing_odds": 100, "odds": -110}), 0.5 - 110 / 210)
    assert _bet_price_clv({"closing_odds": None, "odds": -110}) is None


# --- Parlay pricing ---------------------------------------------------------------
# Hand: two −110 legs → 1.909091² = 3.644628 → +264; three → 6.958527 →
# +596. Independent joint at 0.55 each: 0.3025 and 0.166375.

def test_two_and_three_minus_110_legs_price_to_the_hand_numbers():
    d = P.american_to_decimal(-110)
    assert P.decimal_to_american(d * d) == 264
    assert P.decimal_to_american(d * d * d) == 596


def test_the_joint_at_zero_correlation_is_the_product():
    assert close(P.joint_two(0.55, 0.55, 0.0), 0.3025, 1e-6)
    assert close(P.joint_three((0.55, 0.55, 0.55), (0.0, 0.0, 0.0)), 0.166375, 1e-5)


def test_a_fourth_leg_is_refused_everywhere_the_engine_counts_legs():
    """Ethan, 2026-09-01: "1. 3 legs". The cap must agree in the engine,
    the slip check, the social share and the reader's slip."""
    assert P.MAX_LEGS == 3 == social.MAX_PARLAY_LEGS
    legs = [{"player": f"P{i}", "team": "T" + str(i), "opponent": "O" + str(i),
             "market": "receptions", "side": "OVER", "line": 4.5, "odds": -110,
             "win_prob": 0.6, "game_date": "2026-09-13"} for i in range(4)]
    out = P.check_ticket("nfl", legs)
    assert out["ok"] is False and "3 legs is the ceiling" in out["reason"]
    assert P.check_ticket("nfl", legs[:3])["ok"] is True
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "web", "js", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    assert "const SLIP_MAX = 3;" in js


# --- Conflict probes -----------------------------------------------------------------
# Every pair the brief names, run through the same relate() the boards
# use. A kill is a kill regardless of edge.

def _prop(player, team, opp, market, side="OVER", line=50.5):
    return {"player": player, "team": team, "opponent": opp, "market": market,
            "side": side, "line": line, "odds": -110, "win_prob": 0.6,
            "game_date": "2026-09-13", "recommended": True, "grade": "Play"}


def _gl(market, team, home, away, side, line):
    return {"market": market, "bet_type": market, "team": team, "home": home,
            "away": away, "side": side, "line": line, "odds": -110,
            "win_prob": 0.6, "date": "2026-09-13", "game_date": "2026-09-13",
            "recommended": True, "grade": "Play"}


def test_both_sides_of_one_spread_kill():
    r = P.relate("nfl", _gl("spread", "KC", "KC", "LAC", "KC", -3.0),
                 _gl("spread", "LAC", "KC", "LAC", "LAC", 3.0))
    assert r.verdict == "kill" and r.clash == 1


def test_both_sides_of_one_total_kill():
    r = P.relate("nfl", _gl("total", "", "KC", "LAC", "Over", 45.5),
                 _gl("total", "", "KC", "LAC", "Under", 45.5))
    assert r.verdict == "kill" and r.clash == 1


def test_the_same_player_over_and_under_kill():
    r = P.relate("nfl", _prop("Travis Kelce", "KC", "LAC", "rec_yds", "OVER"),
                 _prop("Travis Kelce", "KC", "LAC", "rec_yds", "UNDER"))
    assert r.verdict == "kill"


def test_the_same_player_twice_is_never_a_ticket():
    r = P.relate("nfl", _prop("Travis Kelce", "KC", "LAC", "rec_yds"),
                 _prop("Travis Kelce", "KC", "LAC", "receptions"))
    assert r.verdict in ("kill", "duplicate")


def test_a_quarterback_under_against_his_own_receiver_over_kills():
    r = P.relate("nfl", _prop("Patrick Mahomes", "KC", "LAC", "pass_yds", "UNDER", 275.5),
                 _prop("Travis Kelce", "KC", "LAC", "rec_yds", "OVER"))
    assert r.verdict == "kill" and r.clash == 7


def test_two_independent_games_carry_no_clash():
    r = P.relate("nfl", _prop("Travis Kelce", "KC", "LAC", "rec_yds"),
                 _prop("Josh Allen", "BUF", "NYJ", "pass_yds"))
    assert r.verdict == "ok" and r.clash == 0 and close(r.rho, 0.0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
