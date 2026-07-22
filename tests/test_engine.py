"""Core math and pipeline sanity checks. Run with: python3 -m pytest (or this
file directly with `python3 tests/test_engine.py`)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.statmath import normal_cdf, prob_over, weighted_mean
from engine.odds import american_to_prob, devig_two_way, best_over_line
from engine.models import SportsbookLine
from engine.pipeline import run_slate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLATE = os.path.join(ROOT, "data", "sample_slate.json")


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


def test_normal_cdf():
    assert approx(normal_cdf(0), 0.5)
    assert approx(normal_cdf(1.96), 0.975, tol=2e-3)
    # Symmetry
    assert approx(normal_cdf(-1) + normal_cdf(1), 1.0)


def test_prob_over():
    # At the mean, P(over) is 0.5; well below the mean it approaches 1.
    assert approx(prob_over(100, 100, 20), 0.5)
    assert prob_over(60, 100, 20) > 0.95


def test_weighted_mean():
    assert approx(weighted_mean([(10, 1), (20, 1)]), 15.0)
    assert approx(weighted_mean([(10, 3), (20, 1)]), 12.5)
    assert weighted_mean([]) == 0.0


def test_american_to_prob():
    assert approx(american_to_prob(-110), 0.5238, tol=1e-3)
    assert approx(american_to_prob(+100), 0.5)
    assert approx(american_to_prob(-200), 0.6667, tol=1e-3)


def test_devig_sums_to_one():
    over, under = devig_two_way(-110, -110)
    assert approx(over + under, 1.0)
    assert approx(over, 0.5)


def test_best_line_shops_lowest_over():
    lines = [
        SportsbookLine("A", 50.5, -110, -110),
        SportsbookLine("B", 48.5, -112, -108),  # lowest line = best over
        SportsbookLine("C", 49.5, -105, -115),
    ]
    best = best_over_line(lines)
    assert best.book == "B"
    assert best.line == 48.5


def test_pipeline_runs_and_ranks():
    result = run_slate(SLATE)
    recs = result["recommendations"]
    assert result["counts"]["props_analyzed"] == len(recs)
    # Sorted so recommended-first, then by confidence descending.
    rec_flags = [r["recommended"] for r in recs]
    assert rec_flags == sorted(rec_flags, reverse=True)
    # Every record carries an explanation and hit probability in [0, 1].
    for r in recs:
        assert 0.0 <= r["hit_prob"] <= 1.0
        assert r["headline"]
        assert isinstance(r["reasons"], list)


def test_injury_hold_rule():
    # Rashee Rice is QUESTIONABLE in the sample slate and must not be
    # recommended even though his raw edge is positive.
    result = run_slate(SLATE)
    rice = next(r for r in result["recommendations"] if r["player"] == "Rashee Rice")
    assert rice["recommended"] is False
    assert any("QUESTIONABLE" in w for w in rice["warnings"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
