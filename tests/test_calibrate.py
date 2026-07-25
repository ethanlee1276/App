"""Probability calibration — recovering a known miscalibration.

Calibration is the one part of "does the model have an edge" that can be
measured from outcomes alone, so these tests generate data with a *known*
distortion and assert the fitter recovers it.

Run directly: `python3 tests/test_calibrate.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.calibrate import (
    apply_temperature, brier, fit, fit_temperature, load, save, reset_cache,
    temperature_for, Calibration,
)


def _distort(p, k):
    """Restate probability p as if the model used temperature k."""
    o = p / (1 - p)
    s = o ** (1.0 / k)
    return s / (1 + s)


def _sample(k, n=4000, seed=5):
    """(stated, outcome) pairs where outcomes follow the TRUE probability but
    the model states a distorted one."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        true_p = rnd.uniform(0.05, 0.95)
        out.append((_distort(true_p, k), 1 if rnd.random() < true_p else 0))
    return out


def test_apply_temperature_endpoints():
    assert abs(apply_temperature(0.5, 2.0) - 0.5) < 1e-9      # 50% is a fixed point
    assert apply_temperature(0.8, 1.0) == 0.8                  # T=1 is a no-op
    assert apply_temperature(0.8, 3.0) < 0.8                   # T>1 pulls toward 50%
    assert apply_temperature(0.8, 0.5) > 0.8                   # T<1 sharpens
    assert 0.0 < apply_temperature(1.0, 2.0) < 1.0             # endpoints stay finite


def test_fit_recovers_overconfidence():
    # Model states MORE extreme than truth -> needs T > 1 to pull it back.
    c = fit(_sample(k=0.5), sport="mlb", market="total_bases")
    assert c.temperature > 1.3
    assert c.brier_after < c.brier_before
    assert "over-confident" in c.verdict


def test_fit_recovers_underconfidence():
    # Model states LESS extreme than truth -> needs T < 1 to sharpen it.
    c = fit(_sample(k=1.8), sport="mlb", market="hits")
    assert c.temperature < 0.8
    assert c.brier_after < c.brier_before
    assert "under-confident" in c.verdict


def test_well_calibrated_model_is_left_alone():
    c = fit(_sample(k=1.0), sport="mlb", market="hits")
    assert abs(c.temperature - 1.0) < 0.15
    # No meaningful "improvement" should be manufactured.
    assert c.brier_after <= c.brier_before + 1e-9


def test_small_samples_are_not_trusted():
    """A handful of games can't prove miscalibration — refuse to correct."""
    assert fit_temperature(_sample(k=0.5, n=40), min_samples=200) == 1.0


def test_save_load_roundtrip(tmp_path=None):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "calibration.json"
        save({"mlb:hits": Calibration(temperature=0.75, intercept=-0.3, samples=900)}, p)
        assert load(p) == {"mlb:hits": (0.75, -0.3)}
        # Unknown market falls back to no correction.
        reset_cache()
        assert temperature_for("mlb", "hits", p) == 0.75
        assert temperature_for("mlb", "nope", p) == 1.0
        from engine.calibrate import correction_for
        assert correction_for("mlb", "hits", p) == (0.75, -0.3)
        assert correction_for("mlb", "nope", p) == (1.0, 0.0)
        reset_cache()


def test_temperature_alone_cannot_fix_a_centre_bias():
    """Temperature has 50% as a fixed point, so a model whose predictions sit
    near 50% while outcomes run at 42% needs the intercept — this is the exact
    failure real backtests showed, with T running to the search ceiling while
    the gap survived."""
    from engine.calibrate import apply_temperature, fit_correction

    for T in (1.0, 2.5, 6.0, 50.0):
        assert abs(apply_temperature(0.5, T) - 0.5) < 1e-9   # never moves

    rnd = random.Random(7)
    pairs = []
    for _ in range(4000):
        stated = min(max(rnd.gauss(0.52, 0.05), 0.05), 0.95)
        pairs.append((stated, 1 if rnd.random() < 0.42 else 0))

    t, b = fit_correction(pairs)
    assert b < -0.1, "must find a negative (optimistic-bias) intercept"
    centre = apply_temperature(0.5, t, b)
    assert centre < 0.47, "a stated 50% should be corrected downward"
    # And the two-parameter fit must beat temperature alone.
    from engine.calibrate import brier
    assert brier(pairs, t, b) < brier(pairs, 6.0, 0.0)


def test_missing_file_means_no_correction():
    from pathlib import Path
    reset_cache()
    assert load(Path("/nonexistent/calibration.json")) == {}
    reset_cache()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
