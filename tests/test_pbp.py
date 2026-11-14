"""Pitch-by-pitch parsing — §5's velocity trend, TTO and pitch counts.

`docs/PITCH_LEVEL_SCOPE.md`: three of §5's four parked items need no new
feed. statsapi's playByPlay carries per-pitch speed, spin, break, location
and type for free, on a host this repo already uses.

The fixture below is the shape of a real payload, trimmed. Every parser
here is pure, so none of these tests touch the network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.sources import pbp                                # noqa: E402


def _play(inning, ab, pitcher, batter, events):
    return {"about": {"inning": inning, "halfInning": "top", "atBatIndex": ab},
            "matchup": {"pitcher": {"id": pitcher, "fullName": f"P{pitcher}"},
                        "batter": {"id": batter, "fullName": f"B{batter}"}},
            "playEvents": events}


def _pitch(speed, code="FF", n=1, spin=2300.0, is_pitch=True):
    return {"isPitch": is_pitch, "pitchNumber": n,
            "details": {"type": {"code": code, "description": code},
                        "call": {"code": "S"}},
            "pitchData": {"startSpeed": speed, "endSpeed": speed - 8,
                          "extension": 6.4, "zone": 5,
                          "coordinates": {"pX": 0.1, "pZ": 2.4},
                          "breaks": {"spinRate": spin, "breakAngle": 28.0,
                                     "breakLength": 4.1}}}


FIXTURE = {"allPlays": [
    _play(1, 0, 660271, 1, [_pitch(95.1), _pitch(94.8, n=2),
                            # a pickoff throw: same list, not a pitch
                            {"isPitch": False, "details": {"description":
                                                           "Pickoff Attempt"}}]),
    _play(1, 1, 660271, 2, [_pitch(84.2, code="SL")]),
    _play(4, 2, 660271, 1, [_pitch(93.4), _pitch(83.1, code="SL", n=2)]),
    # a reliever, so TTO must restart for him
    _play(7, 3, 700000, 1, [_pitch(99.0, code="FF")]),
]}


def test_a_pickoff_is_not_counted_as_a_pitch():
    """THE ONE THING EASY TO GET WRONG. Pickoffs, mound visits,
    substitutions and stepoffs all live in `playEvents`. A parser that
    skips the `isPitch` check counts a pickoff throw as a 0 mph fastball,
    which drags every velocity average down by exactly as much as the
    pitcher holds runners."""
    rows = pbp.pitches(FIXTURE)
    assert len(rows) == 6, [r["speed"] for r in rows]
    assert all(r["speed"] is not None for r in rows)


def test_is_pitch_is_read_from_either_place_it_lives():
    """Newer payloads put it on the event, older ones under details.
    Reading only one silently drops every pitch in the other shape."""
    old = {"allPlays": [_play(1, 0, 1, 1, [
        {"pitchNumber": 1, "details": {"isPitch": True,
                                       "type": {"code": "FF"}},
         "pitchData": {"startSpeed": 96.0}}])]}
    assert len(pbp.pitches(old)) == 1


def test_a_pitch_with_no_pitchData_does_not_crash_the_build():
    """statsapi omits whole sub-objects on some events. A KeyError here
    would take down a nightly over one malformed pitch in a
    rain-shortened game."""
    thin = {"allPlays": [_play(1, 0, 1, 1, [{"isPitch": True,
                                             "details": {}}])]}
    rows = pbp.pitches(thin)
    assert len(rows) == 1
    assert rows[0]["speed"] is None and rows[0]["pitch_type"] is None


def test_velocity_is_averaged_BY_PITCH_TYPE():
    """§5 calls a 1+ mph drop a red flag for injury. Averaged across all
    pitches, a starter who threw more breaking balls in a cold game fires
    that flag without losing a tick — the mix moved, not the arm. Only a
    four-seam against a four-seam means what the rule says."""
    rows = pbp.pitches(FIXTURE)
    v = pbp.velocity_by_type(rows, pitcher_id=660271)
    assert v["FF"] == (94.43, 3), v
    assert v["SL"] == (83.65, 2), v
    # The reliever's 99 must not reach the starter's average.
    assert v["FF"][0] < 95.0


def test_velocity_is_scoped_to_one_pitcher_when_asked():
    rows = pbp.pitches(FIXTURE)
    assert pbp.velocity_by_type(rows, pitcher_id=700000) == {"FF": (99.0, 1)}
    both = pbp.velocity_by_type(rows)
    assert both["FF"][1] == 4, "unscoped must include every pitcher"


def test_pitch_counts_are_per_pitcher():
    counts = pbp.pitch_counts(pbp.pitches(FIXTURE))
    assert counts == {660271: 5, 700000: 1}


def test_times_through_the_order_counts_plate_appearances_not_pitches():
    """Batter 1 is faced in the 1st and again in the 4th: that is TTO 1
    then 2, however many pitches each took."""
    rows = pbp.pitches(FIXTURE)
    tto = pbp.times_through_order(rows, 660271)
    assert tto[(1, 0)] == 1
    assert tto[(2, 1)] == 1
    assert tto[(1, 2)] == 2, tto


def test_tto_restarts_for_a_relief_pitcher():
    """TTO is familiarity accumulating within one matchup. A reliever
    entering in the 7th has never faced anyone, whatever the starter
    did — counting it per game rather than per pitcher would hand him the
    starter's third-time-through penalty on his first batter."""
    rows = pbp.pitches(FIXTURE)
    tto = pbp.times_through_order(rows, 700000)
    assert tto == {(1, 3): 1}, tto


def test_the_parsers_touch_no_network():
    import inspect
    src = inspect.getsource(pbp)
    body = src[src.index("def pitches("):]
    for verb in ("urlopen", "requests", "_get_json", "fetch_"):
        assert verb not in body, f"a parser calls {verb}"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
