"""The NFL board is re-priced after the inactive lists post.

Ethan, 2026-09-27, noon, with the books open beside the site: Garrett
Wilson's line "shot up to like 80 yards … because other people were ruled
out, but yet we're still displaying 50 yards at minus 250 when they now
have 50 yards at minus 386 … we need to make sure everything's getting
updated right at like twelve, twelve thirty."

The readiness pull had fired at 10:16; every ask after it fell to the
day's ceiling (672 of 808, a pull costs 272), and the noon touchpoint sits
below that check. Pinned here: once the next kickoff is within
INACTIVES_BEFORE_S, the NFL gets one pull through the day's ceiling and
the ordinary gap — once per wave, never the reserve, NFL only.

Run directly: `python3 tests/test_inactives_pull.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as ob                          # noqa: E402
from engine.oddsbudget import (BudgetState, save, should_refresh,  # noqa: E402
                               inactives_window, INACTIVES_BEFORE_S,
                               INACTIVES_SPORTS, READY_BEFORE_S, RESERVE,
                               MIN_REFRESH_GAP)

NOW = 1_800_000_000.0
KICK = NOW + 60 * 60                 # an hour out: inside the inactives window
COST = 272                           # the 16-game Sunday pull


def _state(remaining, last, sport="nfl"):
    path = os.path.join(tempfile.mkdtemp(), "budget.json")
    save(BudgetState(remaining=remaining, last_refresh_ts=last,
                     sport_last_refresh={sport: last}), path)
    return path


def _spent(fn):
    real = ob.spent_today
    ob.spent_today = lambda *a, **k: 10 ** 6       # the day's ceiling is reached
    try:
        fn()
    finally:
        ob.spent_today = real


def test_the_window_opens_after_the_lists_and_before_the_kick():
    assert INACTIVES_BEFORE_S < 90 * 60 < READY_BEFORE_S   # lists post at 90 minutes
    assert inactives_window([KICK], NOW) == KICK - INACTIVES_BEFORE_S
    assert inactives_window([NOW + INACTIVES_BEFORE_S + 60], NOW) is None
    assert inactives_window([NOW - 60], NOW) is None
    assert inactives_window(None, NOW) is None
    # The staggered Sunday: the next wave's window, not the first's.
    assert inactives_window([NOW - 3600, KICK, NOW + 4 * 3600], NOW) == KICK - INACTIVES_BEFORE_S
    assert INACTIVES_SPORTS == ("nfl",)


def test_the_morning_pull_does_not_use_up_the_post_inactives_price():
    """Sunday as it happened: readiness pull at 10:16 for a 1pm kick, the
    day's ceiling spent, noon — the pull goes through."""
    def check():
        p = _state(remaining=20000, last=NOW - 105 * 60)     # before the window opened
        ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl", credits=COST)
        assert ok is True and "inactives pull" in why, why
        assert f"{COST} credit" in why, why
    _spent(check)


def test_once_per_wave():
    def check():
        opened = KICK - INACTIVES_BEFORE_S
        p = _state(remaining=20000, last=opened + 60)        # already pulled inside it
        ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl", credits=COST)
        assert ok is False and "inactives" not in why, why
    _spent(check)


def test_the_fifteen_minute_floor_and_the_reserve_still_hold():
    def check():
        kick = NOW + INACTIVES_BEFORE_S - 5 * 60              # opened five minutes ago
        p = _state(remaining=20000, last=NOW - 10 * 60)      # pulled before it, 10 minutes ago
        assert 10 * 60 < MIN_REFRESH_GAP
        ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[kick],
                                 sport="nfl", credits=COST)
        assert ok is False and "inactives" not in why, why
        for remaining in (RESERVE, RESERVE + COST - 1):
            p = _state(remaining=remaining, last=NOW - 2 * 3600)
            ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[KICK],
                                     sport="nfl", credits=COST)
            assert ok is False and "inactives" not in why, (remaining, why)
    _spent(check)


def test_college_and_baseball_wait_as_before():
    def check():
        for sport in ("cfb", "mlb"):
            p = _state(remaining=20000, last=NOW - 105 * 60, sport=sport)
            ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[KICK],
                                     sport=sport, credits=COST)
            assert "inactives" not in why, (sport, why)
    _spent(check)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
