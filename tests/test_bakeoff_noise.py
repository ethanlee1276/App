"""A curve has to beat the temperature by more than the noise on the gap.

WHAT THIS WAS WRITTEN AFTER. On 2026-08-28 `nfl:anytime_td` fitted a
29-knot isotonic curve and stored it, because on the held-out slice it
scored 0.14171 against the temperature's 0.14178. That margin is SEVEN
HUNDRED-THOUSANDTHS of a Brier point on 6,631 rows; the paired standard
error on the same comparison is about 0.00018, so the decision was made
at z = -0.38. A coin flip picked the form.

The coin flip was not free. Replayed over 22,099 player-weeks, the model
under that stored curve claims 44.5% in its 40%-60% band where 55.0%
actually score — a ten-point miss on the strongest rows of the Most
Likely board, the ones a reader trusts most. The temperature it beat,
fitted leave-one-season-out, holds every band inside 1.4% and the
aggregate at 20.3% claimed against 20.0% landed.

`bake_off`'s own docstring already said the right thing — "isotonic can
bend where the data bends, which also means it can bend where the noise
bends; the held-out slice is the only thing standing between those two."
The code under it compared three means with a bare argmin, which lets a
curve win by any margin at all, noise included. The sentence was true and
nothing enforced it. That is the same shape as the devigfit haircut
shipping without an error bar, and as every other rule this codebase has
announced in prose and checked nowhere.

Run directly: `python3 tests/test_bakeoff_noise.py`
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as C                       # noqa: E402

#: Fitting a bake-off is not cheap and several tests ask about the same
#: draw. Memoised so the suite pays for each distinct sample once.
_CACHE: dict = {}


def off(gen, seed, n=None):
    """`C.bake_off` of one fixture draw, computed at most once."""
    key = (gen.__name__, seed, n)
    if key not in _CACHE:
        _CACHE[key] = C.bake_off(gen(seed) if n is None else gen(seed, n))
    return _CACHE[key]

#: Big enough that the held-out slice can certify a real curve, small
#: enough to stay cheap. The power cost of the bar at smaller sizes is
#: itself measured below rather than left to be rediscovered.
BIG = 12000
SMALL = 8000


# --- fixtures -------------------------------------------------------------
def _draw(rng, n, curve):
    """`n` (claimed, outcome) pairs where the truth is `curve(claimed)`."""
    out = []
    for _ in range(n):
        p = rng.random() * 0.6 + 0.05
        true = min(max(curve(p), 0.01), 0.99)
        out.append((p, int(rng.random() < true)))
    return out


def honest(seed, n=SMALL):
    """A model that is already right. No form has anything to find."""
    return _draw(random.Random(seed), n, lambda p: p)


def temperature_miss(seed, n=SMALL):
    """One monotone squeeze — exactly what a temperature is shaped for."""
    return _draw(random.Random(seed), n,
                 lambda p: C.apply_temperature(p, 1.15, 0.22))


def two_signed(seed, n=BIG):
    """The MLB-hits shape the bake-off was written for: 92% of the mass in
    one crowded middle bucket needing a big push UP, a thin top needing a
    small pull DOWN. A single temperature is a monotone squeeze around
    50% and cannot do both; this is the case a curve exists to serve."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        if rng.random() < 0.92:
            p = 0.62 + rng.random() * 0.10
            true = p + 0.21
        else:
            p = 0.80 + rng.random() * 0.08
            true = p - 0.02
        out.append((p, int(rng.random() < min(max(true, 0.01), 0.99))))
    rng.shuffle(out)
    return out


# --- the gate lets a real curve through -----------------------------------
def test_the_curve_the_bake_off_exists_for_still_wins():
    """If the bar silenced this, the bar would be wrong. The docstring's
    own motivating case has to clear it, on every draw."""
    for seed in range(3):
        winner, detail = off(two_signed, seed)
        assert winner == "isotonic", (seed, detail)
        assert detail["curve_z"] <= -C.CURVE_Z, (seed, detail["curve_z"])


def test_a_wiggle_no_temperature_can_follow_wins_too():
    """A miss that changes sign three times. A monotone squeeze can only
    trade one end against the other; the curve genuinely bends."""
    for seed in range(2):
        pairs = _draw(random.Random(seed), BIG,
                      lambda p: p + 0.12 * math.sin(p * 12.0))
        winner, detail = C.bake_off(pairs)   # one draw, one caller
        assert winner == "isotonic", (seed, detail)


# --- and refuses one that won on nothing ----------------------------------
def test_a_curve_is_refused_when_its_margin_is_inside_the_noise():
    """THE FIXTURE IS THE BUG. This draw from a PERFECTLY CALIBRATED model
    is one where the isotonic curve happens to score best on the held-out
    slice, at z = -0.05. The old argmin adopted it. There is nothing there
    to adopt."""
    winner, detail = off(honest, 46)
    h = detail["held_out"]
    assert min(h, key=h.get) == "isotonic", \
        "fixture no longer reproduces the argmin trap: " + repr(h)
    assert abs(detail["curve_z"]) < C.CURVE_Z, detail["curve_z"]
    assert winner != "isotonic", detail


def test_the_same_trap_on_a_model_that_really_is_miscalibrated():
    """Not only a lucky curve over a lucky nothing. Here the temperature
    is genuinely right and earns its place, and the curve still edges it
    on the slice — by more than the last fixture, at z = -1.4, which is
    the near-miss worth having in the suite. The right answer is still the
    temperature."""
    winner, detail = off(temperature_miss, 32)
    h = detail["held_out"]
    assert min(h, key=h.get) == "isotonic", repr(h)
    assert -C.CURVE_Z < detail["curve_z"] < -1.0, detail["curve_z"]
    assert winner == "temperature", detail
    assert h["temperature"] < h["none"]


def test_an_honest_model_never_gets_a_curve_across_many_draws():
    """One seed proves the gate can fire. Ten say it is not a fluke — and
    that the OLD behaviour was not either, since the argmin picks a curve
    on a model with nothing wrong with it often enough to be seen in ten
    draws, and every one of those is noise."""
    got = [off(honest, s)[0] for s in range(8)]
    assert "isotonic" not in got, got


# --- the arithmetic, stated so it can be disagreed with -------------------
def test_the_bar_is_on_the_paired_difference_not_two_separate_means():
    """Both forms are scored on the IDENTICAL held-out rows, so most of
    the variance — which rows happened to be hard — cancels. Pairing is
    what makes a bar this high still able to detect a real curve: on the
    NFL touchdown replay the paired error on that comparison is 0.00018
    where an unpaired one is several times larger."""
    a = [0.10, 0.20, 0.30, 0.40, 0.50]
    b = [0.11, 0.21, 0.31, 0.41, 0.51]          # worse by exactly 0.01 each
    z = C._paired_z(a, b)
    assert z is not None and z < -1e6, z         # no variance in the gap
    assert C._paired_z(a, a) is None             # no difference at all
    assert C._paired_z(None, b) is None
    assert C._paired_z(a, b[:3]) is None         # unequal lengths
    assert C._paired_z([0.1], [0.2]) is None     # one row decides nothing


def test_the_decision_is_reconstructable_from_the_store():
    """A stored fit that does not say what its curve had to clear cannot
    be argued with later, which is how the 2026-08-28 one survived."""
    _winner, detail = off(two_signed, 0)
    assert detail["curve_bar"] == C.CURVE_Z
    assert isinstance(detail["curve_z"], float)
    assert set(detail["held_out"]) == {"none", "temperature", "isotonic"}


def test_the_temperature_rung_is_deliberately_not_gated():
    """A DECISION, NOT AN OVERSIGHT. Two parameters fitted on thousands of
    rows cannot meaningfully overfit, and `fit_correction` already returns
    the exact neutral when its grid finds nothing — so the null is not a
    form the temperature has to out-argue.

    The cost of getting this wrong is measured. A significance bar on this
    rung would discard the CFB touchdown correction, whose held-out Brier
    gain reads as noise (z = -0.55 over 8,715 rows) while its band table
    closes +3.0% and +2.3% in the two bands the college longshots actually
    live in. Brier is dominated by resolution and is a poor judge of a few
    points of calibration in the tail; complexity is what needs a bar
    here, not correction."""
    import inspect
    src = inspect.getsource(C.bake_off)
    assert 'simple = min(("none", "temperature"), key=lambda k: scores[k])' \
        in src
    for seed in range(3):
        winner, _ = off(temperature_miss, seed)
        assert winner == "temperature", seed


def test_the_bar_costs_power_on_a_small_sample_and_that_is_the_trade():
    """SAID OUT LOUD SO IT IS NOT REDISCOVERED AS A SURPRISE. The same
    two-signed miss that clears the bar comfortably at 12,000 rows does
    not reliably clear it at 8,000: 2,400 held-out rows cannot separate
    the two forms, and the market keeps its temperature.

    That is the intended trade and the asymmetry behind it is the whole
    argument. A curve wrongly refused leaves the market exactly where it
    was before curves existed. A curve wrongly adopted puts a ten-point
    miss into the top band of a page nobody is checking. Bounded against
    unbounded, on a decision made thousands of times."""
    winners = [off(two_signed, s, SMALL)[0] for s in range(4)]
    assert winners.count("temperature") >= 2, winners
    assert all(off(two_signed, s)[0] == "isotonic" for s in range(2))


def test_fit_stores_no_curve_when_the_bake_off_refused_one():
    """The gate is worthless if `fit` writes the curve anyway. It picks
    the form from the bake-off's winner, and a refused curve must leave
    the stored fit with no knots at all."""
    got = C.fit(honest(46), sport="test", market="td")
    assert not got.curve.get("knots"), got.curve
    kept = C.fit(two_signed(0), sport="test", market="td")
    assert kept.curve.get("knots"), "a curve that earned its place is stored"


def test_a_sample_too_small_to_judge_still_skips_the_bake_off():
    """Unchanged, and worth pinning: below MIN_HOLDOUT there is no slice
    to compute a z on, and the old skip path must still be the one taken
    rather than a z of None being read as a pass."""
    winner, detail = C.bake_off(honest(0)[:600])
    assert detail["ran"] is False, detail
    assert winner in ("none", "temperature")
    assert "curve_z" not in detail


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
