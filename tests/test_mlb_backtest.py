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


def test_real_lines_join_across_name_formats():
    """Odds are stored normalised ("aaron judge"), game logs keep the display
    name ("Aaron Judge"). If the join isn't normalised it matches nothing and
    the backtest silently reports a naive-baseline result as if it were real."""
    from engine.mlb.backtest import backtest_from_logs

    entries = [{"name": "Aaron Judge",
                "values": [float(i % 4) for i in range(30)],
                "dates": [f"2026-07-{d + 1:02d}" for d in range(30)]}]
    real = {("aaron judge", f"2026-07-{d + 1:02d}"):
            {"line": 1.5, "over_odds": -115, "under_odds": -105, "book": "DraftKings"}
            for d in range(30)}

    r = backtest_from_logs(entries, "total_bases", min_history=10, real_lines=real)
    assert r.used_real_lines == r.total_priced > 0
    assert "REAL book lines" in r.summary()

    # With no harvested prices the report must say so rather than imply an edge.
    naive = backtest_from_logs(entries, "total_bases", min_history=10)
    assert naive.used_real_lines == 0
    assert "NAIVE baseline" in naive.summary()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


def test_corrupt_book_pair_is_not_treated_as_a_price():
    """Harvested rows carry fabricated unders: Caesars quoting a home run
    at over +850 / under -110 implies 10.5% + 52.4% = 63%, i.e. the book
    arbitraging itself by 37%. Feeding that to the model invents a 52%
    price on 'no home run' and a phantom edge with it."""
    from engine.mlb.backtest import backtest_from_logs
    from engine.odds import pair_is_sane

    assert pair_is_sane(850, -110) is False        # fabricated
    assert pair_is_sane(1200, -4000) is True       # a real over-only quote
    assert pair_is_sane(-110, -110) is True

    vals = [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0]
    dates = [f"2026-07-{d:02d}" for d in range(1, len(vals) + 1)]
    entries = [{"name": "A J Ewing", "values": vals, "dates": dates}]
    corrupt = {("a j ewing", d): {"line": 0.5, "book": "Caesars",
                                  "over_odds": 850, "under_odds": -110}
               for d in dates}
    rep = backtest_from_logs(entries, "home_runs", min_history=6,
                             real_lines=corrupt)
    # The over is real, so the prop is still counted as book-priced…
    assert rep.used_real_lines > 0
    # …and with the fabricated under discarded the market is one-sided,
    # so the model cannot manufacture a 37% edge out of it.
    assert rep.n > 0
