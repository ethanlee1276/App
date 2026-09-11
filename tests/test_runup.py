"""The run-up to a season is not the offseason.

Reported 2026-08-08: "we do show pre season now but also show we are still
working of sample data for the nfl page."

`_current_nfl_week()` only called a week current if the nearest fixture was
within SEVEN days. Week 1 2026 kicks off on September 9; on August 8 that
is 32 days out, so every launch got None, `refresh_nfl` printed "no current
slate (offseason / schedule unavailable) — kept existing data", and the NFL
board went on serving the illustrative sample slate — the one whose games
are dated January 4. It was doing exactly what it was told. Nobody had told
it that a buildable week existed.

It is buildable. `engine/carry.py` exists precisely so weeks 1-3 have
projections before the new season has played a snap, and books post Week 1
lines all summer — the schedule refresh in maintenance.py already pulls
next season's fixtures for that reason.

FORWARD ONLY, and that is the whole subtlety. Widening the existing
nearest-game rule in both directions would, in March, find last February's
Super Bowl closer than September's opener and rebuild the board around a
game five weeks gone. The run-up rule looks at UPCOMING fixtures alone, and
only when nothing is within a week.

Run directly: `python3 tests/test_runup.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch                                                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FixedDate(dt.date):
    """A date class whose `today()` is whatever the test says it is."""
    _now = dt.date(2026, 8, 8)

    @classmethod
    def today(cls):
        return cls._now


def _week_on(day):
    real = launch._dt.date
    try:
        _FixedDate._now = day
        launch._dt.date = _FixedDate
        return launch._current_nfl_week()
    finally:
        launch._dt.date = real


def _have_schedule():
    """These read the cached nflverse schedule; skip cleanly without it."""
    return os.path.exists(os.path.join(ROOT, "data", "cache", "games.csv"))


def test_the_run_up_to_week_one_builds_a_board():
    """THE BUG. 32 days from the opener, with a carry that can fill it."""
    if not _have_schedule():
        return
    assert _week_on(dt.date(2026, 8, 8)) == (2026, 1)


def test_the_day_before_the_opener_still_builds():
    if not _have_schedule():
        return
    assert _week_on(dt.date(2026, 9, 8)) == (2026, 1)


def test_in_season_the_nearest_game_still_wins():
    """The run-up rule must not disturb the normal case — it only runs when
    nothing is within a week."""
    if not _have_schedule():
        return
    assert _week_on(dt.date(2026, 9, 13)) == (2026, 1)


def test_the_deep_offseason_is_still_nothing():
    """March is not the run-up to anything, and the board should keep
    whatever it has rather than build a slate for a fixture five months
    out."""
    if not _have_schedule():
        return
    assert _week_on(dt.date(2026, 3, 15)) is None


def test_it_never_reaches_backwards():
    """The failure the forward-only scan prevents. A symmetric window would
    find LAST season's postseason nearer than the coming opener and rebuild
    the board around a game already played — a stale slate presented as
    tonight's, which is worse than the sample it replaced."""
    if not _have_schedule():
        return
    import csv
    with open(os.path.join(ROOT, "data", "cache", "games.csv"),
              encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    past = [r for r in rows if r.get("season") == "2025"
            and r.get("game_type") in ("SB", "CON")]
    if not past:
        return
    # A date shortly after that postseason, still months from the opener.
    got = _week_on(dt.date(2026, 3, 1))
    assert got is None, f"reached back to {got}"


def test_the_window_is_named_and_explained():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "SEASON_RUNUP_DAYS" in src
    i = src.index("SEASON_RUNUP_DAYS = ")
    assert "45" in src[i:i + 40]
    why = src[max(0, i - 500):i]
    assert "32 days" in why, "the measurement the window is sized from is gone"


def test_the_forward_only_reasoning_is_written_down():
    """Someone will eventually simplify this back into a symmetric window."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("FORWARD ONLY")
    block = src[i:i + 400]
    assert "Super Bowl" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
