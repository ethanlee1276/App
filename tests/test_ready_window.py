"""Every football slate is priced at least three hours before kickoff.

Ethan, 2026-09-07: "i prefer to do whatever gives us props and picks
every single day ready for every game at least 3 hours before. i want
to prioritize NFL and CFB over anything so if we gotta limit MLB pulls
im ok with that. i want to make sure we are ready for NFL game days and
can look any time at nfl and cfb and have up to date information."

Three things, pinned here:

  * THE PACER CAN SEE NFL KICKOFFS NOW. The launcher's kickoff reader
    skipped any time without a date, and an NFL game's kickoff is
    "HH:MM" Eastern beside a "YYYY-MM-DD" date — so the pre-game
    window, the burst, the closing window and everything keyed on the
    kickoff list were blind for the NFL all season.
  * THE READINESS PULL. Once the next kickoff is within READY_BEFORE_S,
    a football league that has not pulled since the window opened gets
    one pull through the day's ceiling and the ordinary gap. Never the
    reserve, once per window per sport, football only.
  * BASEBALL STEPS BACK in the day's split.

Run directly: `python3 tests/test_ready_window.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as ob                          # noqa: E402
from engine.oddsbudget import (BudgetState, save, should_refresh, ready_window,  # noqa: E402
                               READY_BEFORE_S, READY_SPORTS, RESERVE,
                               MIN_REFRESH_GAP, CLOSE_WINDOW_S)
import launch                                                # noqa: E402

NOW = 1_800_000_000.0
KICK = NOW + 2 * 3600                # kickoff two hours out: inside 3h, outside the close
COST = 1200                          # a full pull on a dear day: the ordinary gap is hours


def _tmp():
    return os.path.join(tempfile.mkdtemp(), "budget.json")


def _state(path, remaining, last, sport="nfl"):
    save(BudgetState(remaining=remaining, last_refresh_ts=last,
                     sport_last_refresh={sport: last}), path)
    return path


def test_the_window_opens_three_hours_before_the_next_kickoff():
    assert READY_BEFORE_S == 3 * 3600
    assert ready_window([KICK], NOW) == KICK - READY_BEFORE_S
    assert ready_window([NOW + READY_BEFORE_S + 60], NOW) is None
    assert ready_window([NOW - 60], NOW) is None
    assert ready_window([], NOW) is None and ready_window(None, NOW) is None
    # A staggered slate: the NEXT kickoff's window, not the first's.
    assert ready_window([NOW - 3600, KICK, NOW + 6 * 3600], NOW) == KICK - READY_BEFORE_S
    assert ready_window(["13:00", None, KICK], NOW) == KICK - READY_BEFORE_S
    assert set(READY_SPORTS) == {"nfl", "cfb"}


def test_the_readiness_pull_goes_through_the_ordinary_gap_for_football_only():
    """Two hours since the last pull — before the window opened — and
    an expensive ask inside it: the ordinary cadence says wait hours;
    the readiness pull says price the slate. Baseball, the same
    numbers, waits."""
    p = _state(_tmp(), remaining=20000, last=NOW - 2 * 3600)
    ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[KICK],
                             sport="nfl", credits=COST)
    assert ok is True and "readiness pull" in why, why
    assert "3h before" in why and f"{COST} credit" in why
    p = _state(_tmp(), remaining=20000, last=NOW - 2 * 3600, sport="mlb")
    ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[KICK],
                             sport="mlb", credits=COST)
    assert ok is False and "next odds refresh" in why, why
    # The cheap lines lane spends the NFL's money and is the NFL for
    # this purpose too: through the day's ceiling with its league.
    real = ob.spent_today
    ob.spent_today = lambda *a, **k: 10 ** 6
    try:
        p = _state(_tmp(), remaining=20000, last=NOW - 2 * 3600, sport="nfl_lines")
        ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl_lines", credits=3)
        assert ok is True and "readiness pull" in why, why
    finally:
        ob.spent_today = real


def test_the_readiness_pull_goes_through_the_days_ceiling():
    real = ob.spent_today
    ob.spent_today = lambda *a, **k: 10 ** 6
    try:
        # An ordinary-priced pull (the day can afford several; the
        # ledger says the day already spent them all).
        p = _state(_tmp(), remaining=20000, last=NOW - 6 * 3600)
        ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl", credits=200)
        assert ok is True and "readiness pull" in why, why
        # Outside the window the ceiling refuses exactly as it did.
        far = [NOW + READY_BEFORE_S + 3600]
        ok, why = should_refresh(16, now=NOW, path=p, kickoffs=far,
                                 sport="nfl", credits=200)
        assert ok is False and "budget is spent" in why, why
    finally:
        ob.spent_today = real


def test_once_per_window_per_sport_and_never_the_reserve():
    opened = KICK - READY_BEFORE_S
    # Pulled after the window opened: the ordinary cadence again, which
    # at this price says wait.
    p = _state(_tmp(), remaining=20000, last=opened + 60)
    ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[KICK],
                             sport="nfl", credits=COST)
    assert ok is False and "readiness" not in why, why
    assert "next odds refresh" in why, why
    # Fifteen-minute floor still applies: a window that opened ten
    # minutes ago, a pull twelve minutes ago (before it opened).
    kick = NOW + READY_BEFORE_S - 10 * 60
    p = _state(_tmp(), remaining=20000, last=NOW - 12 * 60)
    assert NOW - 12 * 60 < ready_window([kick], NOW) and 12 * 60 < MIN_REFRESH_GAP
    ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[kick],
                             sport="nfl", credits=COST)
    assert ok is False and "readiness" not in why, why
    # A month at its reserve does not buy a readiness pull — that door
    # is the close's, and the close is cheap. Neither does a month that
    # can afford the pull only by reaching into the reserve: the
    # starvation rule answers first, and the readiness branches sit
    # below it.
    for remaining in (RESERVE, RESERVE + COST - 1):
        # Two hours since the last pull: past the fifteen-minute floor,
        # short of the six-hourly quota probe the reserve branch runs.
        p = _state(_tmp(), remaining=remaining, last=NOW - 2 * 3600)
        ok, why = should_refresh(16, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl", credits=COST)
        assert ok is False and "readiness" not in why, (remaining, why)
    # …and the close still wins inside its own window.
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 6 * 3600)
    ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[NOW + CLOSE_WINDOW_S - 60],
                             sport="nfl", credits=3)
    assert ok is True and "closing window" in why, why


def test_the_prime_window_now_opens_before_the_readiness_pull():
    assert ob.PRIME_BEFORE_S > READY_BEFORE_S


def test_the_launcher_reads_nfl_kickoffs_from_date_and_eastern_clock():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "recommendations.json")
    with open(path, "w") as fh:
        json.dump({"games": [
            {"home": "KC", "away": "BUF", "date": "2026-09-13", "kickoff": "13:00"},
            {"home": "DET", "away": "CHI", "date": "2026-09-13", "kickoff": "20:20"},
            {"home": "X", "away": "Y", "date": "2026-W02", "kickoff": "13:00"},   # a slate label, not a date
            {"home": "NYY", "away": "BOS", "kickoff": "2026-09-13T23:05:00Z"},   # the ISO shape, as before
            {"home": "Z", "away": "W", "kickoff": ""}]}, fh)
    got = sorted(launch._slate_kickoffs(path))
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    one = dt.datetime(2026, 9, 13, 13, 0, tzinfo=et).timestamp()
    two = dt.datetime(2026, 9, 13, 20, 20, tzinfo=et).timestamp()
    iso = dt.datetime(2026, 9, 13, 23, 5, tzinfo=dt.timezone.utc).timestamp()
    assert got == sorted([one, two, iso]), got
    assert launch._eastern_epoch("2026-W02", "13:00") is None
    assert launch._eastern_epoch("2026-09-13", "nope") is None


def test_baseball_steps_back_behind_football():
    assert launch.SPORT_WEIGHT["mlb"] < launch.SPORT_WEIGHT["nfl"] == launch.SPORT_WEIGHT["cfb"]
    launch._live_sports = lambda: ["mlb", "nfl", "cfb"]
    nfl, cfb, mlb = (launch._budget_share(s) for s in ("nfl", "cfb", "mlb"))
    assert nfl > mlb and cfb > mlb, (nfl, cfb, mlb)
    # At equal weights baseball drew about 0.15 of a three-league day
    # (its play-days scaling is 1 against football's 2.3 and 3.5); at
    # 0.6 it draws under 0.12.
    assert mlb < 0.12, mlb
    assert mlb > 0, "baseball was switched off rather than deprioritised"
    assert abs(nfl + cfb + mlb - 1.0) < 1e-9


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
