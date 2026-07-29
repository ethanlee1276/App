"""The unified 0–100 grade, market tiers and volatility (docs/NFL_MODEL.md
§3, §8, §10) — plus the drawdown circuit-breaker.

The spec's core promises, verified:
- tiers scale both the haircut and the minimum edge (noisy markets need
  bigger cushions);
- ONE grade with the spec's exact weights, and edge dominates it;
- there is no Lean anywhere — below 70 is a Pass, not a softer yes;
- movement against a pick can reject it outright;
- a 10u drawdown halves every stake until the peak is recovered.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.quality import (MARKET_TIER, TIER_SHRINK, TIER_MIN_EDGE,
                            market_tier, tier_shrink, tier_min_edge,
                            volatility, letter, quality_score,
                            apply_movement, GRADE_BANDS, STAKE_CAP_U)


def _score(**over):
    """A neutral, healthy Tier-1 receptions play; tests override one knob."""
    kw = dict(edge=0.05, market="receptions", side="OVER",
              favored=None, spread_abs=0.0,
              matchup_mult=1.0, weather_mult=1.0,
              cv=0.30, cv_typical=0.34, sample_games=10)
    kw.update(over)
    return quality_score(**kw)


def test_tiers_scale_haircut_and_minimum_edge():
    # Count props are the most modelable; touchdowns the least. Both the
    # trust in a raw edge and the bar to bet must move together.
    assert market_tier("receptions") == 1
    assert market_tier("rush_yds") == market_tier("pass_yds") == 2
    assert market_tier("anytime_td") == 3
    assert tier_shrink("receptions") > tier_shrink("rush_yds") > tier_shrink("anytime_td")
    assert tier_min_edge("receptions") < tier_min_edge("rush_yds") < tier_min_edge("anytime_td")
    assert TIER_MIN_EDGE[1] == 0.025 and TIER_MIN_EDGE[2] == 0.040 and TIER_MIN_EDGE[3] == 0.060
    assert TIER_SHRINK[1] == 0.50


def test_volatility_ratings_match_the_spec():
    # "5 receptions = LOW; 85 receiving yards = HIGH; anytime TD = EXTREME."
    assert volatility("receptions") == "LOW"
    assert volatility("rec_yds") == "HIGH"
    assert volatility("anytime_td") == "EXTREME"


def test_no_lean_band_exists():
    # A+ / A / B+ / Pass. Nothing between 0 and 70 grades as anything.
    names = [n for n, _ in GRADE_BANDS]
    assert "Lean" not in names and "lean" not in [n.lower() for n in names]
    assert letter(69.9) == "Pass"
    assert letter(70) == "B+" and letter(80) == "A" and letter(90) == "A+"


def test_edge_dominates_the_score():
    # 40% weight: doubling the edge must move the score more than maxing
    # out any 10-point component can.
    lo, _ = _score(edge=0.025)
    hi, _ = _score(edge=0.050)
    perfect_matchup, _ = _score(edge=0.025, matchup_mult=1.10)
    assert hi - lo > perfect_matchup - lo


def test_unstable_role_costs_points_regardless_of_edge():
    # §5: if the role fluctuates, the projection is built on sand.
    steady, _ = _score(cv=0.30)
    rotation, notes = _score(cv=0.70)
    assert steady - rotation >= 4
    assert any("stability" in n.lower() or "volatile" in n.lower() for n in notes)


def test_game_script_fit_moves_the_score_both_ways():
    # Rushing overs want a favorite; a big-dog rushing over loses points.
    fav, _ = _score(market="rush_yds", favored=True, spread_abs=7.5,
                    cv=0.40, cv_typical=0.42)
    dog, _ = _score(market="rush_yds", favored=False, spread_abs=7.5,
                    cv=0.40, cv_typical=0.42)
    assert fav > dog


def test_stake_caps_step_down_with_grade():
    # §10: minimum-stake grades can never take maximum-stake sizes.
    assert STAKE_CAP_U["A+"] == 2.0 > STAKE_CAP_U["A"] > STAKE_CAP_U["B+"]


def test_movement_against_can_reject_a_pick():
    rec = {"quality": 72, "grade": "B+", "recommended": True,
           "stake_units": 0.4, "confidence": 7.2}
    apply_movement(rec, with_us=False, steam=True)
    assert rec["quality"] < 70
    assert rec["grade"] == "Pass" and rec["recommended"] is False
    assert rec["stake_units"] == 0.0
    assert any("rejected" in w for w in rec["warnings"])


def test_movement_with_raises_the_letter_but_never_the_stake():
    rec = {"quality": 88, "grade": "A", "recommended": True,
           "stake_units": 0.6, "confidence": 8.8}
    apply_movement(rec, with_us=True, steam=True)
    assert rec["quality"] >= 90 and rec["grade"] == "A+"
    assert rec["stake_units"] == 0.6          # sizing stays conservative


def test_movement_never_promotes_a_pass():
    rec = {"quality": 66, "grade": "Pass", "recommended": False,
           "stake_units": 0.0, "confidence": 6.6}
    apply_movement(rec, with_us=True, steam=True)
    assert rec["grade"] == "Pass" and rec["recommended"] is False


def test_drawdown_factor_halves_after_ten_units_off_peak():
    from engine import ledger
    path = os.path.join(tempfile.mkdtemp(), "led.db")
    conn = ledger.connect(path)
    rows = [("2026-09-01", 8.0), ("2026-09-02", 4.0),     # peak 12u
            ("2026-09-03", -7.0), ("2026-09-04", -4.5)]   # trough 0.5 → dd 11.5
    for i, (d, pnl) in enumerate(rows):
        conn.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, odds, "
            "grade, stake_units, status, pnl_units, category) VALUES "
            "('nfl', ?, ?, 'receptions', 'OVER', 4.5, -110, 'A', 1.0, "
            "?, ?, 'main')", (d, f"P{i}", "won" if pnl > 0 else "lost", pnl))
    conn.commit()
    assert ledger.drawdown_factor(conn, sport="nfl") == 0.5
    # Recovery: back within 10u of the peak → full stakes again.
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "grade, stake_units, status, pnl_units, category) VALUES "
        "('nfl', '2026-09-05', 'P9', 'receptions', 'OVER', 4.5, -110, 'A', "
        "1.0, 'won', 6.0, 'main')")
    conn.commit()
    assert ledger.drawdown_factor(conn, sport="nfl") == 1.0
    conn.close()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
