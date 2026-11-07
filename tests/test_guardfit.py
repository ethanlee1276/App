"""guardfit: what surcharge does the record support at short prices?

The favourite guard charges extra net edge as the price shortens, and its
slope has always been a chosen number. It is measurable, because the gate
passes a bet when its net edge beats the surcharge — so if the model's
claims run over by g(q) points at implied probability q, the surcharge
that would have made the gate honest IS g(q). The right slope is the
calibration gap as a function of price, which the journal contains.

These tests are mostly about the fit refusing to overreach: recovering a
slope it was given, but reporting an interval wide enough to say "cannot
tell" on the sample sizes this journal actually has — which is the honest
answer and the one it will usually give.

Run directly: `python3 tests/test_guardfit.py`
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import guardfit as gf                                         # noqa: E402
from engine.betting import (FAV_GUARD_FROM,                   # noqa: E402
                            FAV_GUARD_SLOPE, favourite_surcharge)

PRICES = (-110, -130, -150, -175, -200, -250, -300)


def synth(true_slope, n_per=400, seed=11, edge=0.03):
    """Bets whose claim overstates by true_slope · (implied − hinge).

    Deterministic: the same seed is the same book, so a test that passes
    is a measurement rather than a lucky draw.
    """
    rnd = random.Random(seed)
    rows = []
    for odds in PRICES:
        q = gf.implied(odds)
        over = max(0.0, q - FAV_GUARD_FROM) * true_slope
        for _ in range(n_per):
            claimed = q + edge
            rows.append({"sport": "mlb", "market": "hits", "side": "OVER",
                         "odds": odds, "hit_prob": claimed,
                         "status": "won" if rnd.random() < claimed - over
                                   else "lost"})
    return rows


# --- the arithmetic the whole thing rests on ---------------------------------
def test_implied_matches_the_engine_s_own_surcharge_input():
    """The fit has to band on the same quantity the guard keys off, or it
    is fitting a slope for a curve the engine does not have."""
    from engine.odds import american_to_prob
    for odds in PRICES + (120, 250):
        assert abs(gf.implied(odds) - american_to_prob(odds)) < 1e-9


def test_the_hinge_shape_is_the_guard_s_shape():
    """Zero below FROM, linear above. Fitting a free intercept would
    produce a number engine/betting cannot express."""
    assert favourite_surcharge(-110) == 0.0          # 52.4% implied, under
    q = gf.implied(-200)
    expect = FAV_GUARD_SLOPE * (q - FAV_GUARD_FROM)
    assert abs(favourite_surcharge(-200) - expect) < 1e-9


def test_bands_report_claimed_against_landed():
    rows = [{"sport": "mlb", "market": "hits", "side": "OVER", "odds": -200,
             "hit_prob": 0.70, "status": "won" if i < 60 else "lost"}
            for i in range(100)]
    b = gf.bands(rows)[0]
    assert b["n"] == 100
    assert abs(b["claimed"] - 0.70) < 1e-9
    assert abs(b["landed"] - 0.60) < 1e-9
    # Positive gap = claimed more than delivered, the direction a surcharge
    # must cover. Getting this sign backwards would invert every verdict.
    assert abs(b["gap"] - 0.10) < 1e-9


# --- recovery ----------------------------------------------------------------
def test_it_recovers_a_slope_it_was_given():
    """The positive control. Without it, "cannot tell" is just a function
    that never commits."""
    for truth in (0.10, 0.18, 0.45):
        f = gf.fit_slope(gf.bands(synth(truth)), FAV_GUARD_FROM)
        assert f["slope"] is not None
        assert abs(f["slope"] - truth) < 2 * f["se"], (truth, f)


def test_a_perfectly_calibrated_book_fits_a_flat_slope():
    f = gf.fit_slope(gf.bands(synth(0.0)), FAV_GUARD_FROM)
    assert abs(f["slope"]) < 2 * f["se"]


# --- refusal -----------------------------------------------------------------
def test_a_thin_book_refuses_to_fit_at_all():
    f = gf.fit_slope(gf.bands(synth(0.45, n_per=4)), FAV_GUARD_FROM)
    assert f["slope"] is None
    out = _run(synth(0.45, n_per=4))
    assert "Not enough above the hinge" in out
    assert "shipped slope stands" in out


def test_thin_bands_are_shown_but_never_fitted():
    """A band with six bets belongs on the page — it is evidence about
    where the sample is — and nowhere near the regression."""
    rows = synth(0.18, n_per=200)
    rows += [{"sport": "mlb", "market": "hits", "side": "OVER", "odds": -400,
              "hit_prob": 0.95, "status": "lost"} for _ in range(6)]
    out = _run(rows)
    assert "(thin)" in out
    fitted = gf.fit_slope(gf.bands(rows), FAV_GUARD_FROM)
    assert fitted["n"] < len(rows)


def test_the_interval_is_reported_and_wide_when_the_sample_is_small():
    """The honest headline on a young journal: 0.18 and 0.45 are not
    distinguishable on a few hundred bets, and the page must say so rather
    than printing a point estimate that reads as an answer."""
    # Width first, independent of where the point estimate happened to land.
    f = gf.fit_slope(gf.bands(synth(0.45, n_per=60)), FAV_GUARD_FROM)
    assert f["se"] > 0.05, "interval implausibly tight for this sample"
    assert 2 * f["se"] > 0.25, "0.18 and 0.45 should not be separable here"
    assert "95% interval" in _run(synth(0.45, n_per=60))

    # And when the estimate DOES sit on the shipped value, the page says
    # it cannot tell, and says what would settle it.
    out = _run(synth(FAV_GUARD_SLOPE, n_per=200))
    assert "INSIDE THE INTERVAL" in out, out
    assert "needs ~" in out and "bets above the hinge" in out


# --- verdicts ----------------------------------------------------------------
def _run(rows, hinge=FAV_GUARD_FROM, shipped=FAV_GUARD_SLOPE):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        gf.report(rows, hinge, shipped)
    return " ".join(buf.getvalue().split())


def test_a_clearly_shallow_guard_is_called_out():
    out = _run(synth(0.60, n_per=1200))
    assert "TOO SHALLOW" in out
    assert "PRICING change" in out, "no warning that this removes bets"


def test_a_clearly_steep_guard_is_called_out_more_cautiously():
    """Loosening a guard is the direction where being wrong costs money
    rather than opportunity, and the copy has to say so."""
    out = _run(synth(-0.40, n_per=1200))
    assert "TOO STEEP" in out
    assert "costs money rather than opportunity" in out


def test_it_never_edits_the_constant():
    """The whole doctrine: measure, report, let a person decide. A tool
    that quietly rewrote a pricing constant would be the one thing this
    file must not be."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "guardfit.py"), encoding="utf-8").read()
    assert "FAV_GUARD_SLOPE =" not in src, "guardfit assigns the constant"
    assert "write_text" not in src and "open(" not in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
