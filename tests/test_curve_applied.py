"""The bake-off chose isotonic. Four boards priced through the loser.

`calibrate.calibrated` is the only function that applies a stored
isotonic curve, and its own docstring calls itself "THE entry point":

    A stored isotonic curve wins over the temperature, because the curve
    only exists when it beat the temperature on a held-out slice.

Two callers honoured that — `engine.betting` for NFL yardage props and
`engine.mlb.betting` for MLB. Four did not: the long-shot board (both
football codes' touchdown picks), the NBA/WNBA prop pipeline and the CFB
game-prop pipeline all called `apply_temperature(correction_for(...))`
directly, which cannot see a curve and silently discards one.

It went live on 2026-08-28. With 2021 and 2024 play-by-play backfilled,
`nfl:anytime_td` re-fitted on 22,581 pairs and the held-out slice read:

    none 0.14360 · temperature 0.14226 · isotonic 0.14210

Isotonic won, the curve was written to disk, and the touchdown board went
on pricing every pick through the temperature — the form its own bake-off
had just rejected. A rule stated in a docstring and enforced at two of
six call sites, which is this codebase's most-repeated bug.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate


def _store_with_curve(tmp):
    """A market whose bake-off chooses ISOTONIC.

    A STEP, not a slope: the true rate is flat across a wide middle and
    jumps at both ends. A two-parameter logistic cannot bend like that;
    isotonic can, and beats it on the held-out slice by a wide margin.
    The levels are INTERLEAVED rather than blocked because `bake_off`
    holds out the LATER 30% — blocked, the held-out slice would contain
    one level and settle nothing.
    """
    import random
    levels = {0.10: 0.10, 0.25: 0.55, 0.40: 0.55, 0.55: 0.55, 0.70: 0.95}
    rng = random.Random(7)
    pairs = [(claimed, 1 if rng.random() < true else 0)
             for _ in range(700) for claimed, true in levels.items()]
    fit = calibrate.fit(pairs, sport="zz", market="td")
    calibrate.save({"zz:td": fit}, tmp)
    calibrate.reset_cache()
    return fit


def test_the_two_forms_really_do_disagree_in_this_fixture():
    """Guard on the fixture. If the curve and the temperature happened to
    agree, every assertion below would pass without testing anything."""
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    fit = _store_with_curve(tmp)
    # `to_dict` keys the points "knots", not "x" — reading the wrong key
    # made a stored curve look absent, which is how this fixture was
    # first written and why it appeared to prove the opposite.
    assert fit.curve.get("knots"), "the bake-off did not choose isotonic here"
    assert fit.bake_off["held_out"]["isotonic"] < \
        fit.bake_off["held_out"]["temperature"]
    t, b = calibrate.correction_for("zz", "td", tmp)
    from engine.calibrate import apply_temperature
    gaps = {p: abs(apply_temperature(p, t, b)
                   - calibrate.calibrated("zz", "td", p, tmp))
            for p in (0.10, 0.25, 0.40, 0.55, 0.70)}
    assert max(gaps.values()) > 0.10, gaps


# --- the call sites ----------------------------------------------------------
def _sources():
    import inspect
    from engine import longshots
    from engine.nba import pipeline as nba
    from engine.cfb import pipeline as cfb
    return {
        "longshots.calibrated_prob": inspect.getsource(longshots.calibrated_prob),
        "longshots.build_pick": inspect.getsource(longshots.build_pick),
        "nba.pipeline": inspect.getsource(nba),
        "cfb.pipeline": inspect.getsource(cfb),
    }


def test_no_board_applies_the_temperature_behind_the_bake_offs_back():
    for name, src in _sources().items():
        assert "apply_temperature(" not in src, (
            f"{name} applies the temperature directly, which cannot see a "
            f"stored isotonic curve")


def test_every_board_goes_through_the_entry_point():
    for name, src in _sources().items():
        assert "calibrated(" in src, f"{name} never calls calibrated()"


def test_the_two_callers_that_were_already_right_still_are():
    import inspect
    from engine import betting
    from engine.mlb import betting as mlbb
    assert "calibrated(sport, prop.market, raw)" in inspect.getsource(betting)
    assert 'calibrated("mlb", prop.market, raw)' in inspect.getsource(mlbb)


# --- behaviour ---------------------------------------------------------------
def test_a_market_with_a_curve_is_priced_through_the_curve():
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    _store_with_curve(tmp)
    saved = calibrate.DEFAULT_PATH
    try:
        calibrate.DEFAULT_PATH = tmp
        calibrate.reset_cache()
        from engine.calibrate import apply_temperature
        from engine.longshots import calibrated_prob, MARKET_SHRINK
        got, implied = calibrated_prob("zz", "td", 0.70, 400)
        # The board shrinks toward the market on top of the correction,
        # so neither form survives untouched. Put both through the SAME
        # shrink and ask which one the board's number actually came from.
        t, b = calibrate.correction_for("zz", "td", tmp)
        via_curve = implied + MARKET_SHRINK * (
            calibrate.calibrated("zz", "td", 0.70, tmp) - implied)
        via_temp = implied + MARKET_SHRINK * (
            apply_temperature(0.70, t, b) - implied)
        # Both margins are absolute, not a race between two distances: a
        # bare `abs(x) < abs(y)` passes on a last-decimal difference and
        # would call this proved when the two forms had converged.
        assert abs(via_curve - via_temp) > 0.05, "the fixture stopped biting"
        assert abs(got - via_curve) < 1e-6, (
            f"the board's {got:.4f} is not the curve's {via_curve:.4f}")
        assert abs(got - via_temp) > 0.05, (
            f"the board priced through the temperature ({via_temp:.3f}) "
            f"rather than the curve that won its bake-off ({via_curve:.3f})")
    finally:
        calibrate.DEFAULT_PATH = saved
        calibrate.reset_cache()


def test_a_market_with_no_curve_prices_exactly_as_before():
    """The change must be a no-op everywhere the temperature really won —
    `calibrated` carries the same disable switch and the same boundary
    veto, which is what makes routing everything through it safe."""
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    pairs = [(0.30, 1)] * 40 + [(0.30, 0)] * 60
    fit = calibrate.fit(pairs * 8, sport="zz", market="flat")
    calibrate.save({"zz:flat": fit}, tmp)
    calibrate.reset_cache()
    from engine.calibrate import apply_temperature
    t, b = calibrate.correction_for("zz", "flat", tmp)
    if not fit.curve:
        assert abs(calibrate.calibrated("zz", "flat", 0.30, tmp)
                   - apply_temperature(0.30, t, b)) < 1e-9


def test_an_unfitted_market_is_left_alone():
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    calibrate.save({}, tmp)
    calibrate.reset_cache()
    assert calibrate.calibrated("zz", "never-fitted", 0.42, tmp) == 0.42


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
