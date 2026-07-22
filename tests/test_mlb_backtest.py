"""Tests for the MLB walk-forward backtest driver (offline)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.backtest import backtest_from_logs, _naive_line
from engine.mlb.models import TOTAL_BASES, HITS, HOME_RUNS


def test_walk_forward_count():
    # Each entry contributes (len - min_history) settled props.
    entries = [
        {"name": "A", "values": [1, 2, 0, 3, 1, 2, 1, 0, 2, 3]},
        {"name": "B", "values": [2, 1, 1, 0, 2, 3, 1, 1, 2, 1]},
    ]
    r = backtest_from_logs(entries, TOTAL_BASES, min_history=8)
    assert r.n == (10 - 8) * 2


def test_report_has_calibration_and_bins():
    entries = [{"name": f"P{i}", "values": [(i + j) % 4 for j in range(30)]}
               for i in range(12)]
    r = backtest_from_logs(entries, HITS, min_history=8)
    assert r.n > 0
    assert 0.0 <= r.brier <= 1.0
    assert r.bins  # reliability bins populated
    for r_ in [r]:
        assert 0.0 <= r_.ece <= 1.0


def test_projection_tracks_constant_players():
    # A player who posts the same value every game should be projected very
    # close to it (walk-forward, so only prior games are used).
    entries = [{"name": "Steady4", "values": [4] * 20},
               {"name": "Zero", "values": [0] * 20}]
    r = backtest_from_logs(entries, TOTAL_BASES, min_history=8)
    assert r.n == (20 - 8) * 2
    assert r.mae < 0.5   # projection nails constants


def test_naive_line_home_runs_is_half():
    assert _naive_line([0, 1, 0, 1], HOME_RUNS) == 0.5
    # trailing avg ~2 -> line 1.5 (round then step under)
    assert _naive_line([2, 2, 2, 2], TOTAL_BASES) == 1.5


def test_empty_entries():
    r = backtest_from_logs([], TOTAL_BASES)
    assert r.n == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
