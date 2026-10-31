"""The NFL board turns to the new week on Tuesday morning.

Ethan, Tuesday 2026-09-29, 8:52 AM, with Monday night's PHI@CHI still the
Pick of the Day and the Thursday before leading the stadiums: "It's a new
nfl week so the board need to update for that. Every Tuesday morning it
should update for the new week."

The launcher built the week of the game NEAREST today, either way. A
Tuesday sits one day after Monday night and two before Thursday night, so
every Tuesday of the season the board stayed on the week just played and
turned only on Wednesday. The rule is now the week of the NEXT game still
to be played, judged on the Eastern date with the small hours counted as
the day before — a Monday game can end past midnight, and the box runs on
UTC, where Tuesday starts at 8 PM Eastern with Monday's game in its first
quarter. So the week turns at 6 AM Eastern on Tuesday.

A schedule of fixture rows — never the box's cache.

Run directly: `python3 tests/test_the_nfl_week_turns_on_tuesday_morning.py`
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch                                                       # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def _rows():
    """Week 3 Thu–Mon, week 4 Thu–Mon, week 18 then a wild-card week, and
    a Super Bowl two weeks after the conference games."""
    games = [
        (2026, 3, "2026-09-24"), (2026, 3, "2026-09-27"), (2026, 3, "2026-09-28"),
        (2026, 4, "2026-10-01"), (2026, 4, "2026-10-04"), (2026, 4, "2026-10-05"),
        (2026, 18, "2027-01-10"), (2026, 19, "2027-01-16"), (2026, 19, "2027-01-18"),
        (2026, 21, "2027-01-31"), (2026, 22, "2027-02-14"),
    ]
    return [{"season": str(s), "week": str(w), "gameday": d} for s, w, d in games]


def _week_at(when: str, tz=ET):
    now = dt.datetime.fromisoformat(when).replace(tzinfo=tz)
    return launch._current_nfl_week(today=launch._nfl_slate_day(now), rows=_rows())


def test_monday_night_keeps_its_week_and_tuesday_morning_turns_it():
    assert _week_at("2026-09-28 20:15") == (2026, 3)      # Monday night kickoff
    assert _week_at("2026-09-28 23:59") == (2026, 3)
    assert _week_at("2026-09-29 00:40") == (2026, 3)      # an overtime past midnight
    assert _week_at("2026-09-29 05:59") == (2026, 3)
    assert _week_at("2026-09-29 06:00") == (2026, 4)      # Tuesday morning: the new week
    assert _week_at("2026-09-29 08:52") == (2026, 4)      # when Ethan looked
    # The old nearest-game rule held week 3 all of Tuesday; the new week
    # holds from Tuesday through its own Monday night.
    assert _week_at("2026-09-30 12:00") == (2026, 4)
    assert _week_at("2026-10-04 13:00") == (2026, 4)
    assert _week_at("2026-10-05 23:00") == (2026, 4)
    # The fixture has no week 5; past week 4 the next game is January, far
    # outside the run-up window, so nothing is current — never week 4 again.
    assert _week_at("2026-10-06 06:00") is None


def test_the_box_clock_is_utc_and_the_week_still_waits_for_eastern_morning():
    # 00:30 UTC Tuesday is 8:30 PM Monday in the East — Monday's game on.
    assert _week_at("2026-09-29 00:30", tz=UTC) == (2026, 3)
    # 09:59 UTC is 5:59 AM Eastern: still Monday's week.
    assert _week_at("2026-09-29 09:59", tz=UTC) == (2026, 3)
    assert _week_at("2026-09-29 10:00", tz=UTC) == (2026, 4)


def test_the_turn_hour_is_six_eastern_and_named():
    assert launch.NFL_WEEK_TURNS_HOUR_ET == 6
    d = launch._nfl_slate_day(dt.datetime(2026, 9, 29, 5, 59, tzinfo=ET))
    assert d == dt.date(2026, 9, 28)
    d = launch._nfl_slate_day(dt.datetime(2026, 9, 29, 6, 0, tzinfo=ET))
    assert d == dt.date(2026, 9, 29)


def test_the_postseason_gaps_point_forward():
    # The Tuesday after week 18: the wild-card week, not week 18 again.
    assert _week_at("2027-01-12 09:00") == (2026, 19)
    # Between the conference games and the Super Bowl — a two-week gap the
    # old nearest-game rule answered with the week already played.
    assert _week_at("2027-02-02 09:00") == (2026, 22)


def test_it_never_reaches_backwards_and_the_offseason_is_nothing():
    assert _week_at("2027-02-16 09:00") is None                # the Super Bowl is over
    assert launch._current_nfl_week(today=dt.date(2027, 3, 15), rows=_rows()) is None
    # 40 days before the fixture's first game: inside the 45-day run-up.
    assert launch._current_nfl_week(today=dt.date(2026, 8, 15), rows=_rows()) == (2026, 3), \
        "the run-up still finds the first upcoming week"


def test_a_row_with_no_date_is_skipped_not_fatal():
    rows = _rows() + [{"season": "2026", "week": "4", "gameday": ""},
                      {"season": "x", "week": "4", "gameday": "2026-10-01"}]
    assert launch._current_nfl_week(today=dt.date(2026, 9, 29), rows=rows) == (2026, 4)


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
