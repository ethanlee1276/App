"""Tests for the backtest/calibration math (pure, no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backtest import (
    SettledProp, evaluate, settle_recommendations, _norm,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def _sp(hit_prob, actual, line=50.0, proj=55.0, odds=-110, rec=False, stake=1.0, close=None):
    return SettledProp("P", "rec_yds", line, odds, hit_prob, proj, actual,
                       recommended=rec, stake_units=stake, closing_line=close)


def test_outcome_over_under_push():
    assert _sp(0.5, 60, line=50).outcome == 1   # over hit
    assert _sp(0.5, 40, line=50).outcome == 0   # missed
    assert _sp(0.5, 50, line=50).outcome is None  # push


def test_projection_error():
    settled = [_sp(0.5, 50, proj=55), _sp(0.5, 60, proj=55)]  # errors +5, -5
    r = evaluate(settled)
    assert approx(r.mae, 5.0) and approx(r.rmse, 5.0)


def test_brier_perfect_vs_worst():
    perfect = [_sp(1.0, 60, line=50), _sp(0.0, 40, line=50)]   # confident & right
    worst = [_sp(0.0, 60, line=50), _sp(1.0, 40, line=50)]     # confident & wrong
    assert approx(evaluate(perfect).brier, 0.0)
    assert approx(evaluate(worst).brier, 1.0)


def test_calibration_well_calibrated():
    # 10 props predicted at 0.7; exactly 7 hit -> bin is perfectly calibrated.
    settled = [_sp(0.7, 60, line=50) for _ in range(7)] + \
              [_sp(0.7, 40, line=50) for _ in range(3)]
    r = evaluate(settled, n_bins=5)
    bin70 = next(b for b in r.bins if b.lo <= 0.7 < b.hi)
    assert bin70.n == 10 and approx(bin70.mean_pred, 0.7) and approx(bin70.hit_rate, 0.7)
    assert approx(r.ece, 0.0)


def test_calibration_miscalibrated_has_error():
    # Predicts 0.9 but only half hit -> large calibration error.
    settled = [_sp(0.9, 60, line=50) for _ in range(5)] + \
              [_sp(0.9, 40, line=50) for _ in range(5)]
    r = evaluate(settled)
    assert r.ece > 0.35


def test_betting_roi_and_winrate():
    # 3 recommended bets at +100 (decimal 2.0): 2 win, 1 loss, flat 1u.
    settled = [
        _sp(0.6, 60, line=50, odds=100, rec=True),  # win +1
        _sp(0.6, 70, line=50, odds=100, rec=True),  # win +1
        _sp(0.6, 40, line=50, odds=100, rec=True),  # loss -1
        _sp(0.6, 60, line=50, odds=100, rec=False), # not a bet
    ]
    r = evaluate(settled)
    assert r.n_bets == 3 and r.wins == 2
    assert approx(r.win_rate, 2/3)
    assert approx(r.net_units, 1.0)          # +1 +1 -1
    assert approx(r.roi, 1.0/3.0)            # net 1 / staked 3


def test_push_excluded_from_bets():
    settled = [_sp(0.6, 50, line=50, odds=-110, rec=True)]  # push
    r = evaluate(settled)
    assert r.n_bets == 1 and r.pushes == 1 and r.units_staked == 0.0


def test_clv_average():
    settled = [
        _sp(0.6, 60, line=48, odds=-110, rec=True, close=50),  # +2 CLV
        _sp(0.6, 40, line=49, odds=-110, rec=True, close=50),  # +1 CLV
    ]
    r = evaluate(settled)
    assert approx(r.avg_clv, 1.5)


def test_settle_recommendations_matches_by_name_market():
    recs = [
        {"player": "Amon-Ra St. Brown", "market": "rec_yds", "line": 79.5, "odds": -110,
         "hit_prob": 0.58, "projection": 88.0, "recommended": True, "stake_units": 0.7},
        {"player": "Nobody", "market": "rush_yds", "line": 40.5, "odds": -110,
         "hit_prob": 0.5, "projection": 42.0, "recommended": False, "stake_units": 0.0},
    ]
    actuals = {(_norm("Amon-Ra St. Brown"), "rec_yds"): 101.0}
    settled = settle_recommendations(recs, actuals)
    assert len(settled) == 1 and settled[0].actual == 101.0 and settled[0].outcome == 1


def test_backtest_driver_walk_forward():
    # Stub the data layer so the walk-forward loop can be exercised offline.
    import engine.sources.nflverse as nv
    import engine.pipeline as pl
    from engine import backtest as bt

    stats = [{"week": "5", "player_display_name": "RB One", "rushing_yards": "80",
              "passing_yards": "0", "receiving_yards": "0", "receptions": "0"}]
    saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
    nv.load_weekly_stats = lambda season: stats
    nv.build_slate = lambda season, w, upto_week=None: object()
    pl.run_slate = lambda slate, config=None, model=None: {"recommendations": [{
        "player": "RB One", "market": "rush_yds", "line": 70.0, "odds": -110,
        "hit_prob": 0.6, "projection": 82.0, "recommended": True, "stake_units": 1.0,
    }]}
    try:
        r = bt.backtest_from_stats(2024, [5])
        # actual 80 > line 70 -> the recommended bet wins.
        assert r.n == 1 and r.n_bets == 1 and r.wins == 1
    finally:
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = saved


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
