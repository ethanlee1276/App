"""Tests for the MLB Statcast layer (evaluation + Savant CSV parser)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.statcast import evaluate_statcast
from engine.mlb.sources.savant import parse_expected_stats, _norm
from engine.mlb.models import (
    StatcastProfile, MLBProp, MLBGame, MLBGameLog,
    TOTAL_BASES, HOME_RUNS, STRIKEOUTS,
)


def test_positive_regression_boosts():
    eff = evaluate_statcast(StatcastProfile(xslg=0.560, slg=0.500), TOTAL_BASES)
    assert eff.multiplier > 1.0
    assert any("positive regression" in r for r in eff.reasons)


def test_negative_regression_fades():
    eff = evaluate_statcast(StatcastProfile(xslg=0.400, slg=0.480), TOTAL_BASES)
    assert eff.multiplier < 1.0
    assert any("regression risk" in r for r in eff.reasons)


def test_barrel_helps_hr_more_than_tb():
    hr = evaluate_statcast(StatcastProfile(barrel_pct=0.16), HOME_RUNS).multiplier
    tb = evaluate_statcast(StatcastProfile(barrel_pct=0.16), TOTAL_BASES).multiplier
    assert hr > tb > 1.0


def test_pitcher_csw():
    hi = evaluate_statcast(StatcastProfile(csw_pct=0.33), STRIKEOUTS)
    lo = evaluate_statcast(StatcastProfile(csw_pct=0.24), STRIKEOUTS)
    assert hi.multiplier > 1.0 and lo.multiplier < 1.0
    assert any("CSW" in r for r in hi.reasons)


def test_multiplier_is_clamped():
    eff = evaluate_statcast(
        StatcastProfile(xslg=0.9, slg=0.2, barrel_pct=0.30, hard_hit_pct=0.7),
        TOTAL_BASES)
    assert eff.multiplier <= 1.12


def test_empty_profile_neutral():
    assert evaluate_statcast(StatcastProfile(), TOTAL_BASES).multiplier == 1.0


# --- Savant CSV parser ------------------------------------------------------
def test_parse_expected_stats():
    rows = [
        {"last_name": "Harper", "first_name": "Bryce",
         "slg": "0.505", "est_slg": "0.560", "woba": "0.375", "est_woba": "0.400"},
    ]
    board = parse_expected_stats(rows)
    prof = board[_norm("Bryce Harper")]
    assert prof.xslg == 0.560 and prof.slg == 0.505
    assert prof.xwoba == 0.400 and prof.woba == 0.375


def test_parse_combined_name_column():
    rows = [{"last_name": "Judge, Aaron", "first_name": "",
             "slg": "0.610", "est_slg": "0.640"}]
    board = parse_expected_stats(rows)
    assert _norm("Aaron Judge") in board
    assert board[_norm("Aaron Judge")].xslg == 0.640


# --- projection integration -------------------------------------------------
def test_projection_uses_statcast():
    logs = [MLBGameLog(i, "X", 2) for i in range(1, 11)]
    game = MLBGame(home="HOME", away="AWAY", park="generic")

    def prop(sc):
        return MLBProp("H", "AWAY", "HOME", "1B", TOTAL_BASES, logs, 1.8, None,
                       [], bats="R", lineup_spot=3, statcast=sc)

    from engine.mlb.projection import build_mlb_projection
    base = build_mlb_projection(prop(None), game)
    hot = build_mlb_projection(
        prop(StatcastProfile(xslg=0.560, slg=0.490, barrel_pct=0.15)), game)
    assert hot.mean > base.mean
    assert any("regression" in r for r in hot.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
