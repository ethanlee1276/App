"""`--settle` has to be right in the small hours, which is when it's used.

Two things this locks down.

The baseball day rolls at 5 AM (west-coast games run past midnight), so
picks are journaled under the night being played. `--settle` with no date
used to default to the CALENDAR date, which meant that between midnight
and 5 AM — precisely when you'd reach for it, with the late games just
final — it ingested an empty date and reported grading nothing while last
night's board sat open.

And "some bets aren't settled" is usually several nights, not one. The
sweep has to skip NFL's week labels: those journal under "2026-W1" rather
than an ISO date and grade off weekly stats, so handing one to the MLB
per-date ingest reads as a night whose results never arrived.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch


def test_the_slate_day_rolls_at_five_am_not_midnight():
    real = dt.datetime

    class _At(real):
        frozen = None

        @classmethod
        def now(cls, tz=None):
            return cls.frozen

    launch._dt.datetime = _At
    try:
        # 11:30 PM and 4:30 AM are the SAME baseball night.
        _At.frozen = real(2026, 7, 30, 23, 30)
        assert launch._slate_date() == "2026-07-30"
        _At.frozen = real(2026, 7, 31, 4, 30)
        assert launch._slate_date() == "2026-07-30", "4:30 AM is still last night"
        # 5 AM is the turnover.
        _At.frozen = real(2026, 7, 31, 5, 1)
        assert launch._slate_date() == "2026-07-31"
    finally:
        launch._dt.datetime = real


def test_a_bare_settle_targets_the_slate_night_not_the_calendar_date():
    """At 4:30 AM the two differ, and only the slate night has the picks."""
    seen = {}
    real_slate = launch._slate_date
    launch._slate_date = lambda: "NOT-A-DATE"
    try:
        # A bogus slate date makes settle_now bail at the date check, before
        # it opens any database — so this proves which source it consulted
        # without needing a ledger on disk.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch.settle_now()
        seen["out"] = buf.getvalue()
    finally:
        launch._slate_date = real_slate
    assert "NOT-A-DATE" in seen["out"], \
        "--settle with no date no longer follows the 5 AM slate roll"


def test_settle_all_routes_to_the_sweep():
    called = []
    real = launch.settle_all
    launch.settle_all = lambda: called.append(True)
    try:
        launch.settle_now("all")
    finally:
        launch.settle_all = real
    assert called, "`--settle all` fell through to the single-day path"


def test_the_sweep_skips_nfl_week_labels():
    days = [
        {"date": "2026-07-30", "stale": True},
        {"date": "2026-W1", "stale": True},      # NFL — graded weekly
        {"date": "2026-07-28", "stale": True},
        {"date": "", "stale": True},             # never journaled a date
    ]
    assert launch._settleable_days(days) == ["2026-07-28", "2026-07-30"]


def test_the_sweep_runs_oldest_first():
    # Each pass stores results the next one can grade against; newest-first
    # would settle a day before the history behind it existed.
    days = [{"date": d, "stale": True}
            for d in ("2026-07-30", "2026-07-26", "2026-07-28")]
    assert launch._settleable_days(days) == sorted(launch._settleable_days(days))


def test_an_empty_ledger_is_not_an_error():
    assert launch._settleable_days([]) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
