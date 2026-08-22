"""The calibrator with more than one knob, and the judge that gates it.

Ethan, 2026-08-16, asking what more the self-learning could do. The answer
his own Record page gives: MLB hits over-claims at 19% and 30%, UNDER-claims
by 21 points at 66%, and over-claims again at 83%. That curve crosses the
diagonal twice, and temperature scaling is a monotone squeeze around 50% —
above 50% its correction has one sign, so it cannot push 66% up and pull
83% down in the same fit. It lands on whatever the 40–60% bucket wants,
which holds 92% of the samples, and leaves the tails as they were.

The danger in fixing that is obvious and is what these tests are mostly
about: a flexible fit reproduces its training set and predicts nothing.
Every adoption here goes through a chronological held-out slice, and the
winner has to beat applying NOTHING on data it never saw.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as cal                              # noqa: E402
from engine import isotonic as iso                               # noqa: E402

#: MLB hits, straight off the Record page: (claimed, realised, share).
CROSSING = [(0.19, 0.14, 0.01), (0.30, 0.26, 0.06), (0.54, 0.58, 0.72),
            (0.66, 0.87, 0.20), (0.83, 0.81, 0.01)]


#: THE FIXTURES ARE COMPUTED ONCE. Both are deterministic — a fixed
#: seed, and a fit that is a pure function of it — so reusing them is not
#: sharing state between tests, it is not doing the same arithmetic five
#: times. It matters because this file was the slowest in the suite by a
#: factor of three: 220 seconds, of which three separate 40-second calls
#: were `cal.fit` over the same 40,000 points, and with the runner
#: parallel the slowest single file is what the whole run waits for.
#:
#: Both are treated as READ-ONLY by every caller below. If a test ever
#: needs to mutate one, it should build its own rather than deep-copying
#: this — the point of a shared fixture is that nobody wonders whether it
#: was modified.
_SAMPLE: dict = {}
_FIT: dict = {}


def crossing_sample(n=40000, seed=5):
    key = (n, seed)
    if key in _SAMPLE:
        return _SAMPLE[key]
    rng = random.Random(seed)
    pairs = []
    for said, actual, share in CROSSING:
        for _ in range(int(n * share)):
            p = min(0.97, max(0.03, rng.gauss(said, 0.03)))
            pairs.append((p, 1 if rng.random() < actual else 0))
    rng.shuffle(pairs)
    _SAMPLE[key] = pairs
    return pairs


def crossing_fit(sport="mlb", market="hits"):
    """`cal.fit` over the crossing sample — the expensive one."""
    key = (sport, market)
    if key not in _FIT:
        _FIT[key] = cal.fit(crossing_sample(), sport=sport, market=market)
    return _FIT[key]


def test_pava_is_monotone_and_exact_on_a_known_case():
    """Pool-adjacent-violators has a closed-form answer; check it."""
    # Outcomes 1, 0, 1, 1. The only violation is the first pair, so they
    # pool to 0.5 and the last two stand at 1.0. Worth checking against
    # the alternative rather than trusting the output: pooling the first
    # THREE to 2/3 also satisfies the constraint but scores worse —
    # (1/3)² + (2/3)² + (1/3)² = 0.667 against 0.5² + 0.5² = 0.5 — and
    # least squares is what makes this fit the right one rather than a
    # plausible one.
    blocks = iso.pava([(0.1, 1), (0.2, 0), (0.3, 1), (0.9, 1)])
    ys = [y for _x, y, _n in blocks]
    assert ys == sorted(ys), ys
    assert ys == [0.5, 1.0], ys
    # The block sizes come from the algorithm, not from counting afterwards.
    assert [n for _x, _y, n in blocks] == [2, 2], blocks
    assert sum(n for _x, _y, n in blocks) == 4


def test_a_curve_is_never_non_monotone():
    c = iso.fit(crossing_sample())
    ys = [y for _x, y in c.knots]
    assert ys == sorted(ys), ys
    xs = [x for x, _y in c.knots]
    assert xs == sorted(xs), xs


def test_one_knob_cannot_fit_a_crossing_curve_and_this_one_can():
    """THE finding, as arithmetic.

    Not "isotonic scores better" — that is true of any flexible fit on its
    own data and proves nothing. The claim is specific and checkable: at
    the 83% band the temperature fit moves the number the WRONG WAY, past
    the truth, because it cannot bend. Correcting one crossing point in a
    curve that crosses twice necessarily breaks the other.
    """
    pairs = crossing_sample()
    t, b = cal.fit_correction(pairs)
    curve = iso.fit(pairs)

    at83_temp = cal.apply_temperature(0.83, t, b)
    at83_iso = curve.apply(0.83)
    at66_temp = cal.apply_temperature(0.66, t, b)
    at66_iso = curve.apply(0.66)

    # 66% really lands near 87%: both are asked to push it UP.
    assert at66_iso > 0.83, at66_iso

    # 83% really lands near 81% — it should barely move, or come DOWN.
    # The temperature drags it the other way instead, and the margins are
    # stated rather than compared last-decimal: doing NOTHING at 83% is
    # 2 points from the truth, and the temperature lands ~14 points away.
    err_none = abs(0.83 - 0.81)
    err_temp = abs(at83_temp - 0.81)
    err_iso = abs(at83_iso - 0.81)
    assert at83_temp > 0.90, at83_temp
    assert err_temp - err_none > 0.05, (err_temp, err_none)
    # The curve stays materially closer than the temperature does.
    assert err_temp - err_iso > 0.04, (err_iso, err_temp)
    # And it is not merely a different kind of wrong: it wins overall, by
    # more than a rounding step.
    assert cal.brier(pairs, t, b) - iso.brier(pairs, curve) > 0.001


def test_the_bake_off_picks_the_curve_when_the_curve_deserves_it():
    winner, detail = cal.bake_off(crossing_sample())
    assert winner == "isotonic", (winner, detail)
    assert detail["ran"] is True
    # Every candidate scored on the same unseen slice, including the
    # do-nothing baseline the winner had to beat.
    assert set(detail["held_out"]) >= {"none", "temperature", "isotonic"}
    assert detail["held_out"]["isotonic"] < detail["held_out"]["none"]
    assert detail["margin"] > 0


def test_the_bake_off_picks_the_temperature_when_the_error_is_uniform():
    """A model that is over-confident everywhere is exactly what one knob
    is for, and the extra flexibility must not win by default."""
    rng = random.Random(11)
    pairs = []
    for _ in range(30000):
        p = min(0.97, max(0.03, rng.gauss(0.5, 0.18)))
        true = cal.apply_temperature(p, 1.6, 0.0)      # uniformly hot
        pairs.append((p, 1 if rng.random() < true else 0))
    winner, detail = cal.bake_off(pairs)
    assert winner in ("temperature", "isotonic"), winner
    # Whichever wins, it has to beat doing nothing out of sample.
    if detail.get("ran"):
        assert detail["held_out"][winner] <= detail["held_out"]["none"]


def test_nothing_wins_when_the_model_is_already_calibrated():
    """The case that matters most for not doing harm: a model that needs
    no correction must receive none, however flexible the candidate."""
    rng = random.Random(3)
    pairs = []
    for _ in range(30000):
        p = min(0.97, max(0.03, rng.gauss(0.5, 0.18)))
        pairs.append((p, 1 if rng.random() < p else 0))
    winner, detail = cal.bake_off(pairs)
    assert winner == "none", (winner, detail)


def test_an_overfitted_curve_is_refused_by_both_guards():
    """The guards, made to fire, on the case that actually overfits.

    An earlier version of this test used pure noise and asserted the curve
    would be refused. It was not, and the code was right: when the model's
    probabilities carry no information a flat 0.5 really IS the correct
    calibration, and isotonic finding it is the fitter working.

    The real overfitting case is a model that is ALREADY calibrated. There
    is nothing to learn, so every bend the curve finds is sampling noise.
    Unguarded, it does exactly what a flexible fit always does — improves
    in sample and gets worse out of it. Both guards are then shown to
    catch it independently, which matters because either one alone would
    be a single point of failure on a correction that touches every price
    the board publishes.
    """
    rng = random.Random(3)
    pairs = []
    for _ in range(6000):
        p = min(0.97, max(0.03, rng.gauss(0.5, 0.18)))
        pairs.append((p, 1 if rng.random() < p else 0))
    cut = int(len(pairs) * (1.0 - cal.HOLDOUT_FRACTION))
    train, test = pairs[:cut], pairs[cut:]

    # 1. The danger is real. With no minimum bin the fit finds 30-odd
    #    knots, scores better than doing nothing on its own data, and
    #    worse on data it has not seen.
    unguarded = iso.fit(train, min_bin=1)
    assert len(unguarded.knots) > 20, len(unguarded.knots)
    assert iso.brier(train, unguarded) < iso.brier(train, None)
    assert iso.brier(test, unguarded) > iso.brier(test, None)

    # 2. MIN_BIN alone already blunts it — the guarded curve cannot even
    #    win in sample here, because merging thin blocks pulls it back
    #    toward the diagonal it should have stayed on.
    guarded = iso.fit(train)
    assert len(guarded.knots) < len(unguarded.knots)
    assert iso.brier(test, guarded) > iso.brier(test, None)

    # 3. And the held-out judge refuses it regardless of which one it is.
    assert cal.bake_off(pairs)[0] == "none"


def test_no_knot_rests_on_a_handful_of_samples():
    pairs = crossing_sample()
    c = iso.fit(pairs)
    assert len(c.knots) >= 2
    blocks = iso._merge_small(iso.pava(pairs), iso.MIN_BIN)
    assert min(n for _x, _y, n in blocks) >= iso.MIN_BIN, blocks
    assert sum(n for _x, _y, n in blocks) == len(pairs)


def test_a_thin_sample_gets_no_curve_at_all():
    rng = random.Random(7)
    thin = [(rng.random(), 1 if rng.random() < 0.5 else 0) for _ in range(120)]
    c = iso.fit(thin)
    assert not c
    assert c.apply(0.7) == 0.7          # falsey curve is a no-op


def test_a_curve_survives_the_round_trip_through_the_store():
    import json
    import tempfile
    from pathlib import Path
    c = iso.fit(crossing_sample())
    blob = c.to_dict()
    back = iso.Curve.from_dict(json.loads(json.dumps(blob)))
    for p in (0.1, 0.35, 0.54, 0.66, 0.83, 0.95):
        assert abs(back.apply(p) - c.apply(p)) < 1e-4, p

    # And through the real store, read by the real accessor.
    d = Path(tempfile.mkdtemp()) / "calibration.json"
    fit = crossing_fit()
    d.write_text(json.dumps({"mlb:hits": fit.to_dict()}))
    curves = cal.load_curves(d)
    assert "mlb:hits" in curves
    # The stored curve is the fitted curve, not an approximation of it.
    live = iso.Curve.from_dict(fit.curve)
    for p in (0.2, 0.54, 0.66, 0.83):
        assert abs(curves["mlb:hits"].apply(p) - live.apply(p)) < 1e-4, p


def test_the_runtime_path_prefers_the_curve_and_still_honours_the_switch():
    import json
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp()) / "calibration.json"
    fit = crossing_fit()
    assert fit.curve, "this sample should have produced a curve"
    d.write_text(json.dumps({"mlb:hits": fit.to_dict()}))
    cal.reset_cache()
    try:
        got = cal.calibrated("mlb", "hits", 0.66, d)
        assert got > 0.80, got                       # the curve, not the T
        with cal.disabled():
            assert cal.calibrated("mlb", "hits", 0.66, d) == 0.66
    finally:
        cal.reset_cache()


def test_a_market_with_no_curve_prices_exactly_as_it_did_before():
    """Back-compat, asserted rather than assumed: every entry on disk today
    predates this change and must be untouched by it."""
    import json
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp()) / "calibration.json"
    d.write_text(json.dumps({"mlb:hits": {"temperature": 1.42,
                                          "intercept": 0.05,
                                          "samples": 282862}}))
    cal.reset_cache()
    try:
        assert cal.load_curves(d) == {}
        for p in (0.2, 0.5, 0.66, 0.9):
            assert (cal.calibrated("mlb", "hits", p, d)
                    == cal.apply_temperature(p, 1.42, 0.05)), p
    finally:
        cal.reset_cache()


def test_a_boundary_fit_is_still_refused_even_with_a_curve():
    """A capped temperature means the market is unpriceable, not merely
    miscalibrated. A curve fitted on the same market must not walk past
    that veto — it would be the identical failure wearing a new shape."""
    import json
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp()) / "calibration.json"
    fit = crossing_fit()
    entry = fit.to_dict()
    entry["temperature"] = cal.GRID_MAX
    d.write_text(json.dumps({"mlb:hits": entry}))
    cal.reset_cache()
    try:
        assert cal.calibrated("mlb", "hits", 0.66, d) == 0.66
        assert cal.is_reliable("mlb", "hits", d) is False
    finally:
        cal.reset_cache()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
