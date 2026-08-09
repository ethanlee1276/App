"""Velocity, start over start — MLB_MODEL §5's injury tell.

    A drop of 1+ mph is a red flag — check injury and mechanics reporting
    before trusting any projection of him.

Every test here is pure: the arithmetic lives apart from the two fetch
wrappers precisely so it can be checked without a network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import velocity as V                             # noqa: E402


def _h(date, **by_type):
    return {"date": date, "game_pk": hash(date) % 100000, "by_type": by_type}


def test_a_full_mph_drop_is_flagged():
    """§5's rule, directly. 96.0 against a 97.2 baseline is -1.2."""
    hist = [_h("2026-08-08", FF=96.0),
            _h("2026-08-02", FF=97.1), _h("2026-07-27", FF=97.3),
            _h("2026-07-21", FF=97.2)]
    t = V.trend(hist)
    assert t["pitch_type"] == "FF"
    assert t["delta"] == -1.2, t
    assert t["flag"] is True
    assert "check injury and mechanics reporting" in t["reading"]


def test_ordinary_variation_is_not_flagged():
    """A start's mean fastball moves +/-0.3-0.5 mph on nothing at all. A
    flag that fires on that is a flag nobody reads."""
    hist = [_h("2026-08-08", FF=96.9),
            _h("2026-08-02", FF=97.1), _h("2026-07-27", FF=97.3)]
    t = V.trend(hist)
    assert t["flag"] is False
    assert "within 0.3 mph" in t["reading"], t["reading"]


def test_gaining_velocity_is_never_a_red_flag():
    """The threshold is signed. An absolute comparison would flag a
    pitcher who came back throwing HARDER, which is the opposite of the
    thing §5 is worried about."""
    hist = [_h("2026-08-08", FF=98.6),
            _h("2026-08-02", FF=97.1), _h("2026-07-27", FF=97.3)]
    t = V.trend(hist)
    assert t["delta"] > 1.0 and t["flag"] is False


def test_it_compares_within_a_pitch_type():
    """The whole reason `pbp` splits by type. Here the four-seam is
    unchanged and the pitcher simply threw more curveballs — an overall
    average would show a large 'drop' from a mix shift and flag a healthy
    arm."""
    hist = [_h("2026-08-08", FF=97.2, KC=81.0),
            _h("2026-08-02", FF=97.1), _h("2026-07-27", FF=97.3)]
    t = V.trend(hist)
    assert t["pitch_type"] == "FF"
    assert abs(t["delta"]) < 0.3, t


def test_a_thin_start_is_dropped_not_averaged():
    """Six four-seams in a rain-shortened outing is not a reading.
    Treating it as one manufactures a red flag out of noise."""
    rows = ([{"pitcher_id": 1, "pitch_type": "FF", "speed": 90.0}] * 6
            + [{"pitcher_id": 1, "pitch_type": "SL", "speed": 84.0}] * 20)
    got = V.start_velocity(rows, 1, min_pitches=10)
    assert "FF" not in got, "a 6-pitch sample survived the floor"
    assert got["SL"] == 84.0


def test_no_baseline_returns_none_rather_than_zero():
    """None is the honest answer and it is common in April. A zero would
    read as 'no change' and claim a measurement nobody made."""
    assert V.trend([_h("2026-08-08", FF=96.0)]) is None
    # A latest start whose pitch type never appears earlier.
    assert V.trend([_h("2026-08-08", FF=96.0),
                    _h("2026-08-02", SI=93.0)]) is None
    assert V.trend([]) is None


def test_the_primary_pitch_is_the_one_present_across_starts():
    """Not the fastest, and not simply the most thrown last time. A
    pitcher who shelved his slider for one outing would otherwise be
    judged on a pitch with no baseline."""
    hist = [_h("2026-08-08", SI=94.0, FF=97.0),
            _h("2026-08-02", SI=94.2), _h("2026-07-27", SI=94.1)]
    assert V.primary_pitch(hist) == "SI"


def test_the_baseline_is_his_own_not_the_leagues():
    """92 is alarming for Cole and ordinary for a soft-tosser. Both of
    these are steady arms and neither may flag."""
    hard = [_h("a", FF=97.0), _h("b", FF=97.1), _h("c", FF=96.9)]
    soft = [_h("a", FF=89.0), _h("b", FF=89.1), _h("c", FF=88.9)]
    assert V.trend(hard)["flag"] is False
    assert V.trend(soft)["flag"] is False


def test_the_baseline_window_is_bounded():
    """"Recent form", not season-to-date. A 10-start-old outing must not
    drag the comparison."""
    hist = [_h("new", FF=96.0)] + [_h(f"m{i}", FF=97.0) for i in range(4)] \
        + [_h(f"old{i}", FF=99.0) for i in range(6)]
    t = V.trend(hist, baseline_starts=4)
    assert t["baseline"] == 97.0, t
    assert t["baseline_starts"] == 4


def test_the_arithmetic_touches_no_network():
    import inspect
    for fn in (V.trend, V.primary_pitch, V.start_velocity):
        src = inspect.getsource(fn)
        for verb in ("urlopen", "fetch_playbyplay", "fetch_game_log"):
            assert verb not in src, f"{fn.__name__} calls {verb}"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
