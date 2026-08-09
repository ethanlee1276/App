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


def _h(date, counts=None, **by_type):
    return {"date": date, "game_pk": hash(date) % 100000,
            "by_type": by_type, "counts": counts or {}}


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


def test_the_primary_pitch_is_decided_by_VOLUME_not_the_alphabet():
    """CAUGHT ON THE FIRST REAL PITCHER. Gerrit Cole's four-seam and
    slider both appear in all five starts, so presence tied — and the
    tiebreak fell through to sorting, where "SL" beats "FF". The tool
    reported his slider and called a fastball pitcher's arm on it.

    Volume decides. These are his real counts."""
    hist = [_h("2026-08-08", counts={"FF": 42, "SL": 13}, FF=96.65, SL=89.35),
            _h("2026-08-02", counts={"FF": 40, "SL": 15}, FF=96.79, SL=90.59),
            _h("2026-07-28", counts={"FF": 45, "SL": 12}, FF=97.22, SL=90.38)]
    assert V.primary_pitch(hist) == "FF"


def test_presence_still_decides_when_no_counts_were_recorded():
    """A history built before counts existed must not silently pick by
    alphabet again — presence ranks it, and the sort is the last resort
    rather than the rule."""
    hist = [_h("a", FF=97.0, SL=89.0), _h("b", FF=97.1), _h("c", FF=97.2)]
    assert V.primary_pitch(hist) == "FF"


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


def test_every_pitch_type_is_reported_not_just_the_primary():
    """THE CASE THAT MOTIVATED IT, from Cole's real five starts: his
    four-seam was flat while his changeup went 87.64, 86.48, 86.26, 85.09
    and then vanished. A single primary-pitch verdict said "SL within 0.8
    mph" and hid a 2.5 mph slide on another pitch — the exact shape §5
    asks us to notice."""
    hist = [_h("2026-08-08", counts={"FF": 42}, FF=96.65, SL=89.35),
            _h("2026-08-02", counts={"FF": 40}, FF=96.79, SL=90.59, CH=85.09),
            _h("2026-07-28", counts={"FF": 45}, FF=97.22, SL=90.38, CH=86.26),
            _h("2026-07-22", counts={"FF": 44}, FF=96.86, SL=89.49, CH=86.48),
            _h("2026-07-17", counts={"FF": 46}, FF=97.28, SL=90.21, CH=87.64)]
    got = {r["pitch_type"]: r for r in V.trend_all(hist)}
    assert set(got) == {"FF", "SL", "CH"}
    assert got["CH"]["dropped"] is True
    assert got["FF"]["delta"] is not None and abs(got["FF"]["delta"]) < 0.5


def test_a_pitch_he_stopped_throwing_is_reported_not_silently_missing():
    """Shelving a pitch is itself a signal — it is what a pitcher does
    when one is not working or hurts. Returning nothing would make the
    most informative case the silent one."""
    hist = [_h("new", counts={"FF": 40}, FF=97.0),
            _h("b", FF=97.1, CH=86.0), _h("c", FF=97.2, CH=86.4)]
    ch = [r for r in V.trend_all(hist) if r["pitch_type"] == "CH"]
    assert ch and ch[0]["dropped"] is True
    assert ch[0]["latest"] is None, "a dropped pitch must not invent a reading"
    assert ch[0]["flag"] is False, "absence is not a velocity drop"


def test_trend_all_sorts_the_worst_drop_first():
    hist = [_h("new", counts={"FF": 40}, FF=94.0, SL=89.9),
            _h("b", FF=97.0, SL=90.0), _h("c", FF=97.0, SL=90.0)]
    got = V.trend_all(hist)
    assert got[0]["pitch_type"] == "FF" and got[0]["flag"] is True
    assert got[1]["pitch_type"] == "SL" and got[1]["flag"] is False


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
