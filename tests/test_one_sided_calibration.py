"""A calibration that can only ever name one side is not a calibration.

Found on the droplet, 2026-08-28. The fitted isotonic curve for
`nfl:rush_yds`:

    raw 0.400 -> 0.210    raw 0.669 -> 0.402
    raw 0.500 -> 0.305    raw 0.800 -> 0.402
    raw 0.600 -> 0.401

It saturates. Every raw probability from 0.6 upward returns 0.402, and
an over needs about 0.53 to clear the bar at -115 — so for ANY player,
in ANY game, that market could never claim the over was more likely than
not. Every NFL rushing-yards pick on the board was an UNDER by
construction.

Ethan caught it from the front end: a card siding UNDER 58.5 on a player
the model projected for 71.6 yards, with the card's own comps line
saying 715 similar spots went 45% to the under.

WHY THE BAKE-OFF LET IT THROUGH. It scores beautifully — Brier 0.19204
-> 0.13244 on 26,670 pairs. A correction fitted on the model's own
claims is only defined over the band those claims occupy, and flat-lines
past it; the held-out slice comes from the same band, so nothing in the
bake-off can see the extrapolation the live path then walks into. The
live path meets a genuine 0.669 that the training data never contained.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate

#: The droplet's curve, to the numbers it printed.
SATURATING = [[0.0, 0.05], [0.4, 0.210], [0.5, 0.305],
              [0.6, 0.401], [1.0, 0.402]]


def _store(entries):
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    json.dump(entries, open(tmp, "w"))
    calibrate.reset_cache()
    return tmp


def _entry(temp=1.1, bias=0.02, knots=None, sport="nfl", market="rush_yds"):
    return {"temperature": temp, "intercept": bias, "samples": 26670,
            "curve": {"knots": knots} if knots else {},
            "sport": sport, "market": market}


# --- what one_sided detects --------------------------------------------------
def test_the_droplets_curve_is_caught():
    tmp = _store({"nfl:rush_yds": _entry(0.54, -0.98, SATURATING)})
    assert calibrate.one_sided("nfl", "rush_yds", tmp)


def test_an_ordinary_correction_is_not_caught():
    tmp = _store({"nfl:receptions": _entry(1.1, 0.02, market="receptions")})
    assert not calibrate.one_sided("nfl", "receptions", tmp)


def test_a_market_with_no_fit_is_not_caught():
    tmp = _store({})
    assert not calibrate.one_sided("nfl", "never-fitted", tmp)


def test_a_curve_pinned_high_is_caught_the_same_way():
    """The mirror image: a correction that can never say the UNDER is
    likely forces overs forever, and is exactly as broken."""
    pinned = [[0.0, 0.61], [0.5, 0.72], [1.0, 0.95]]
    tmp = _store({"nfl:rush_yds": _entry(1.0, 0.0, pinned)})
    assert calibrate.one_sided("nfl", "rush_yds", tmp)


def test_a_correction_that_merely_shifts_is_left_alone():
    """Crossing 0.5 is normal and must not trip this. What is refused is
    a correction that can NEVER cross it."""
    shifted = [[0.0, 0.02], [0.5, 0.44], [1.0, 0.93]]
    tmp = _store({"nfl:rush_yds": _entry(1.0, 0.0, shifted)})
    assert not calibrate.one_sided("nfl", "rush_yds", tmp)


# --- what happens to a pick --------------------------------------------------
def test_a_one_sided_correction_is_never_applied():
    tmp = _store({"nfl:rush_yds": _entry(0.54, -0.98, SATURATING)})
    saved = calibrate.DEFAULT_PATH
    try:
        calibrate.DEFAULT_PATH = tmp
        calibrate.reset_cache()
        for p in (0.4, 0.6, 0.669, 0.8):
            assert abs(calibrate.calibrated("nfl", "rush_yds", p, tmp) - p) < 1e-9
    finally:
        calibrate.DEFAULT_PATH = saved
        calibrate.reset_cache()


def test_the_market_is_reported_unpriceable_rather_than_silently_raw():
    """Not applying it is half the answer. `betting.evaluate_prop` reads
    `is_reliable` and refuses to bet a market whose calibration cannot be
    trusted — better than pricing raw and saying nothing."""
    tmp = _store({"nfl:rush_yds": _entry(0.54, -0.98, SATURATING)})
    assert not calibrate.is_reliable("nfl", "rush_yds", tmp)


def test_a_healthy_market_stays_reliable_and_still_corrected():
    tmp = _store({"nfl:receptions": _entry(1.4, 0.05, market="receptions")})
    assert calibrate.is_reliable("nfl", "receptions", tmp)
    got = calibrate.calibrated("nfl", "receptions", 0.60, tmp)
    assert abs(got - 0.60) > 1e-6, "a healthy correction must still apply"


def test_the_side_survives_the_veto():
    """The whole point: with the veto the model's own read of the game
    reaches `pick_side` intact."""
    from engine.betting import pick_side
    from engine.models import SportsbookLine
    from engine.statmath import prob_over
    tmp = _store({"nfl:rush_yds": _entry(0.54, -0.98, SATURATING)})
    saved = calibrate.DEFAULT_PATH
    try:
        calibrate.DEFAULT_PATH = tmp
        calibrate.reset_cache()
        p = lambda ln: calibrate.calibrated("nfl", "rush_yds",
                                            prob_over(ln, 71.6038, 29.9), tmp)
        side, best, win, fair, edge = pick_side(
            [SportsbookLine("theScore Bet", 58.5, -115, -115)], p)
        assert side == "OVER", (
            f"a projection of 71.6 against a 58.5 line took the {side}")
        assert best.line == 58.5
    finally:
        calibrate.DEFAULT_PATH = saved
        calibrate.reset_cache()


# --- the plumbing ------------------------------------------------------------
def test_the_veto_does_not_recurse_through_the_thing_it_vetoes():
    """`calibrated` consults `one_sided`, so `one_sided` must read the
    correction directly rather than calling back through it."""
    import inspect
    assert "_apply_raw" in inspect.getsource(calibrate.one_sided)
    assert "calibrated(" not in inspect.getsource(calibrate.one_sided)


def test_the_disable_switch_still_wins():
    tmp = _store({"nfl:rush_yds": _entry(0.54, -0.98, SATURATING)})
    saved = calibrate._enabled
    try:
        calibrate._enabled = False
        assert not calibrate.one_sided("nfl", "rush_yds", tmp)
        assert calibrate.calibrated("nfl", "rush_yds", 0.7, tmp) == 0.7
    finally:
        calibrate._enabled = saved
        calibrate.reset_cache()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
