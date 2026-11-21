"""CFB readiness audit, Phase 3 — the college-specific arithmetic, by hand.

Every expected number was worked on paper from the documented formula
before the function was called. Heavy favourites (−2000 shows up every
college Saturday), the 12% slate cap on a sixty-game board, the college
margin width against the NFL's, and the parlay conflicts §8 names.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import odds as O
from engine import parlays as P
from engine import devig as D
from engine import gamebets as G
from engine.cfb import model as M
from engine.cfb import ratings as R
from engine.cfb import pipeline as CP
from engine.ledger import _bet_clv, _bet_price_clv
from engine.statmath import normal_cdf


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


# --- heavy favourites ---------------------------------------------------------
# Hand: −2000 → 2000/2100 = 0.952381, decimal 1.05; +1000 → 100/1100 =
# 0.090909, decimal 11.0. Pair sums 1.043290; fair favourite = 0.91286.

def test_minus_2000_converts_without_overflow_or_bad_rounding():
    assert close(O.american_to_prob(-2000), 2000 / 2100)
    assert close(O.american_to_decimal(-2000), 1.05)
    assert close(P.american_to_decimal(-2000), 1.05)
    assert P.decimal_to_american(1.05) == -2000
    assert D.american(2000 / 2100) == -2000
    assert close(M._dec(-2000), 1.05) and close(CP._dec(-2000), 1.05)
    assert close(CP.break_even(-2000), 2000 / 2100, 5e-5)   # rounded to 4 places


def test_the_extreme_ends_of_the_price_scale_do_not_divide_by_zero():
    for odds in (-100000, -2000, -101, -100, 100, 101, 2000, 100000):
        p = O.american_to_prob(odds)
        assert 0.0 < p < 1.0
        assert O.american_to_decimal(odds) > 1.0
    assert close(O.american_to_prob(-100000), 100000 / 100100)
    assert close(O.american_to_decimal(100000), 1001.0)


def test_devig_of_a_minus_2000_plus_1000_pair():
    fav, dog = O.devig_two_way(-2000, 1000)
    assert close(fav, (2000 / 2100) / (2000 / 2100 + 100 / 1100), 1e-9)
    assert close(fav, 0.91286, 1e-5)
    assert close(fav + dog, 1.0)
    # the CFB pipeline's own copy is the same formula rounded to 4 places
    a, b = CP.devig(-2000, 1000)
    assert close(a, fav, 5e-5) and close(b, dog, 5e-5)


# --- EV sign at the actual price ------------------------------------------------
# Hand at −2000: p·0.05 − (1−p). p = 0.95 → 0.0475 − 0.05 = −0.0025 (a loser
# even at 95%); p = 0.96 → 0.048 − 0.04 = +0.008. Breakeven exactly 0.952381.

def test_a_ninety_five_percent_favourite_at_minus_2000_loses_money():
    assert close(O.expected_value(0.95, -2000), -0.0025)
    assert close(O.expected_value(0.96, -2000), 0.008)
    assert close(O.expected_value(2000 / 2100, -2000), 0.0, 1e-12)


# --- Kelly, the per-play cap, the slate cap -------------------------------------
# Hand: at −2000, b = 0.05. p = 0.94 → (0.047 − 0.06)/0.05 < 0 → 0. At −110,
# p = 0.99 → full = (0.9 − 0.01)/0.909 = 0.979; quarter 0.2448 → capped 0.02.

def test_kelly_is_zero_when_the_edge_is_gone_and_capped_at_two_percent():
    assert M.kelly_stake(0.94, -2000, M.LOW, 80) == 0.0
    assert M.kelly_stake(0.50, -110, M.LOW, 80) == 0.0
    assert close(M.kelly_stake(0.99, -110, M.STANDARD, 85), M.CAP_PER_PLAY)
    # half Kelly only for an A+ in a low-attention spot: p = 0.58 at −110,
    # full = (0.58·0.90909 − 0.42)/0.90909 = 0.118; quarter 0.0295 → cap 0.02;
    # so use p = 0.55: full 0.055, quarter 0.01375, half 0.0275 → capped 0.02
    assert close(M.kelly_stake(0.55, -110, M.STANDARD, 95), 0.01375, 1e-5)
    assert close(M.kelly_stake(0.55, -110, M.LOW, 95), M.CAP_PER_PLAY)
    assert close(M.kelly_stake(0.55, -110, M.LOW, 89), 0.01375, 1e-5)
    # a drawdown halves
    assert close(M.kelly_stake(0.55, -110, M.STANDARD, 95, drawdown=True), 0.006875, 1e-5)


def test_a_sixty_game_saturday_cannot_exceed_the_twelve_percent_slate_cap():
    """Seven plays at the 2% per-play cap ask 14%; the slate allows 12%, so
    the LOWEST-graded play is the one trimmed to 0 — in grade order, the
    cap costs the worst play, not a random one."""
    plays = [{"game_id": f"g{i}", "grade": 90 - i, "stake_fraction": 0.02}
             for i in range(7)]
    out = M.apply_caps(plays)
    assert close(sum(p["stake_fraction"] for p in out), M.CAP_PER_SLATE)
    by = {p["game_id"]: p for p in out}
    assert by["g6"]["stake_fraction"] == 0.0 and by["g6"]["capped"]
    assert all(by[f"g{i}"]["stake_fraction"] == 0.02 for i in range(6))
    # 5% per game: three plays in one game at 2% → 2 + 2 + 1
    same = [{"game_id": "one", "grade": 90 - i, "stake_fraction": 0.02}
            for i in range(3)]
    out2 = M.apply_caps(same)
    assert close(sum(p["stake_fraction"] for p in out2), M.CAP_PER_GAME)
    assert min(p["stake_fraction"] for p in out2) == 0.01


# --- CLV on de-vigged probabilities ----------------------------------------------
# Hand: took −2000 (0.952381), closed −2500 (0.961538) → +0.009158, the
# market moved toward us; took −110 (0.52381), closed +100 (0.5) → −0.02381.

def test_clv_is_measured_in_probability_points_and_signed_by_direction():
    assert close(_bet_price_clv({"closing_odds": -2500, "odds": -2000}),
                 2500 / 2600 - 2000 / 2100)
    assert close(_bet_price_clv({"closing_odds": 100, "odds": -110}), 0.5 - 110 / 210)
    # a spread bet: laid −24, closed −27 → the favourite side gained 3
    assert close(_bet_clv({"closing_line": 27.0, "line": 24.0, "side": "OVER"}), 3.0)
    assert close(_bet_clv({"closing_line": 27.0, "line": 24.0, "side": "UNDER"}), -3.0)


# --- grade boundaries ------------------------------------------------------------
# §9 weights: edge 40 · information 20 · attention 10 · situational 10 ·
# matchup 10 · environment 10. Edge exactly at the tier's bar scores 0.5 →
# 20 points; every context at 1.0 → +60 → 80 (A). Every context at the
# neutral 0.6 → 20 + 36 = 56 (Pass). Twice the bar → 0.75 → 30.

def test_grade_boundaries_at_their_exact_numbers():
    assert M.grade_label(69) == "Pass" and M.grade_label(70) == "B+"
    assert M.grade_label(79) == "B+" and M.grade_label(80) == "A"
    assert M.grade_label(89) == "A" and M.grade_label(90) == "A+"
    full = M.GradeInput(edge_after_haircut=M.MIN_EDGE[M.LOW], tier=M.LOW,
                        information_certainty=1, attention_fit=1,
                        situational_fit=1, matchup_fit=1, environment_fit=1)
    assert M.grade(full) == 80
    neutral = M.GradeInput(edge_after_haircut=M.MIN_EDGE[M.LOW], tier=M.LOW,
                           information_certainty=.6, attention_fit=.6,
                           situational_fit=.6, matchup_fit=.6, environment_fit=.6)
    assert M.grade(neutral) == 56
    assert close(M._edge_score(2 * M.MIN_EDGE[M.LOW], M.LOW), 0.75)
    assert close(M._edge_score(3 * M.MIN_EDGE[M.LOW], M.LOW), 1.0)
    assert M._edge_score(0.0, M.LOW) == 0.0


def test_the_haircut_and_the_bar_by_attention_tier():
    # §3.5 / §3.6: +6% raw is +3.0% in a marquee game (under the 4% bar),
    # +3.9% standard (over 3%), +4.5% low (over 2.5%)
    assert close(M.haircut_edge(0.06, M.MARQUEE), 0.03)
    assert close(M.haircut_edge(0.06, M.STANDARD), 0.039)
    assert close(M.haircut_edge(0.06, M.LOW), 0.045)
    assert M.min_edge_for(M.MARQUEE) == 0.04 and M.min_edge_for(M.LOW) == 0.025
    assert M.min_edge_for(M.LOW, "prop") == 0.04


# --- the margin-to-win-probability conversion is college-shaped -----------------
# Hand: Φ(24/16.5) = Φ(1.4545) = 0.9271; the NFL width 13.5 gives Φ(1.7778)
# = 0.9623. A 24-point college favourite is NOT a 96% winner.

def test_a_24_point_spread_uses_the_college_margin_width_not_the_nfl_one():
    R.install(R.PRIOR)
    assert G.MARGIN_SD["cfb"] == R.PRIOR.margin_sd == 16.5
    assert G.MARGIN_SD["nfl"] != G.MARGIN_SD["cfb"]
    p = R.win_prob(24.0, R.PRIOR)
    assert close(p, normal_cdf(24 / 16.5), 1e-9)
    assert 0.925 < p < 0.929
    assert normal_cdf(24 / 13.5) > 0.96
    # pricing the spread itself: a projection equal to the number is a
    # coin flip either side, whatever the number's size
    card = G.price_spread("cfb", "H", "A", 24.0, -24.0)
    assert close(card["win_prob"], 0.5, 1e-6) and card["grade"] == "Pass"


# --- parlays --------------------------------------------------------------------

def _gl(market, team, home, away, side, line, odds=-110):
    return {"market": market, "bet_type": market, "team": team, "home": home,
            "away": away, "side": side, "line": line, "odds": odds,
            "win_prob": 0.6, "date": "2026-09-05", "game_date": "2026-09-05",
            "recommended": True, "grade": "B+"}


def test_two_and_three_legs_price_by_hand_and_a_fourth_is_refused():
    d = P.american_to_decimal(-110)
    assert P.decimal_to_american(d * d) == 264
    assert P.decimal_to_american(d ** 3) == 596
    # −2000 twice is 1.1025 → −100/0.1025 = −975.6 → −976
    assert P.decimal_to_american(1.05 * 1.05) == -976
    legs = [_gl("spread", f"T{i}", f"T{i}", f"O{i}", f"T{i}", -3.0) for i in range(4)]
    out = P.check_ticket("cfb", legs)
    assert out["ok"] is False and "3 legs is the ceiling" in out["reason"]
    assert P.check_ticket("cfb", legs[:3])["ok"] is True
    assert P.RULES["cfb"].max_legs == 3 == P.MAX_LEGS


def test_cfb_conflicts_are_killed_or_priced_never_independent():
    home, away = "UGA", "CLEM"
    fav = _gl("spread", home, home, away, home, -17.0)
    over = _gl("total", "", home, away, "Over", 55.5)
    under = _gl("total", "", home, away, "Under", 55.5)
    tt_under = _gl("team_total", home, home, away, "Under", 31.5)
    tt_over = _gl("team_total", home, home, away, "Over", 31.5)
    # a team total against the full game total in the same direction is
    # one opinion twice; opposite directions cannot both be right
    r = P.relate("cfb", tt_over, over)
    assert r.verdict in ("kill", "duplicate") and r.clash in (1, 6)
    r = P.relate("cfb", tt_under, over)
    assert r.verdict == "kill"
    # backing the favourite while betting its own total under: opposite scripts
    r = P.relate("cfb", fav, tt_under)
    assert r.verdict == "kill" and r.clash == 2
    # side + total in one game is PRICED (a correlation), never treated as
    # independent and never silently allowed at the product price
    r = P.relate("cfb", fav, over)
    assert r.verdict in ("ok", "kill") and r.rho != 0.0
    # both sides of a total, both sides of a spread
    assert P.relate("cfb", over, under).verdict == "kill"
    dog = _gl("spread", away, home, away, away, 17.0)
    assert P.relate("cfb", fav, dog).verdict == "kill"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
