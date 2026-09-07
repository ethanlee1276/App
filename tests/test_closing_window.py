"""The reserve may not skip the close.

Ethan, 2026-09-07, setting the data plan: "Add an intraday snapshot loop
through the betting window, and stop letting the 500-credit reserve skip
the close."

Every settled bet is graded against the number the market closed at.
Closing-line value is the only evidence about the PROCESS that arrives
before the results do, and a bet with no stored close cannot be graded
at all. Below RESERVE the pacer authorised nothing but a six-hourly
recovery probe, and the daily ceiling refused on its own account — so at
the end of a billing month, or on a thin plan, the last pull before
kickoff was exactly the pull that did not happen.

The exemption is narrow on purpose, and every bound here is one of the
guards that keeps it from becoming a hole in the budget.

Run directly: `python3 tests/test_closing_window.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as ob                          # noqa: E402
from engine.oddsbudget import (BudgetState, CLOSE_FLOOR,     # noqa: E402
                               CLOSE_MAX_CREDITS, CLOSE_WINDOW_S,
                               MIN_REFRESH_GAP, RESERVE, closing_window,
                               save, should_refresh)

NOW = 1_800_000_000.0
KICK = NOW + 20 * 60                 # kickoff twenty minutes out
CHEAP = 3                            # the board endpoint: whole slate, 3 credits


def _tmp():
    return os.path.join(tempfile.mkdtemp(), "budget.json")


def _state(path, remaining, last=0.0, sport="nfl"):
    save(BudgetState(remaining=remaining, last_refresh_ts=last,
                     sport_last_refresh={sport: last}), path)
    return path


def test_the_window_opens_before_the_next_kickoff_and_closes_behind_it():
    assert closing_window([KICK], NOW) == KICK - CLOSE_WINDOW_S
    # Too far out: not a close yet, just an ordinary refresh.
    assert closing_window([NOW + CLOSE_WINDOW_S + 60], NOW) is None
    # Every game started: there is no close left to buy.
    assert closing_window([NOW - 60], NOW) is None
    assert closing_window([], NOW) is None and closing_window(None, NOW) is None
    # A staggered slate answers for the NEXT wave, not the first or last.
    waves = [NOW - 3600, KICK, NOW + 4 * 3600]
    assert closing_window(waves, NOW) == KICK - CLOSE_WINDOW_S
    # A non-numeric kickoff cannot crash the refresh thread.
    assert closing_window(["20:20", None, KICK], NOW) == KICK - CLOSE_WINDOW_S


def test_a_month_down_to_its_reserve_still_buys_the_close():
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 3 * 3600)
    ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                             sport="nfl", credits=CHEAP)
    assert ok is True and "closing window" in why, why
    assert "graded against" in why
    # Outside the window the same ask is refused, as it always was.
    early = NOW - CLOSE_WINDOW_S
    ok, why = should_refresh(0, now=early, path=p, kickoffs=[KICK],
                             sport="nfl", credits=CHEAP)
    assert ok is False and "quota" in why.lower(), why


def test_only_a_cheap_pull_may_spend_the_reserve():
    """The board endpoint bills three credits for a whole slate; the event
    endpoint bills eight PER GAME. Letting the expensive one through this
    door would drain the reserve it is carved out of."""
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 3 * 3600)
    ok, _ = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                           sport="nfl", credits=CLOSE_MAX_CREDITS)
    assert ok is True
    ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                             sport="nfl", credits=CLOSE_MAX_CREDITS + 1)
    assert ok is False, why
    # A sixteen-game prop pull is 136 credits and is refused outright.
    ok, why = should_refresh(17, now=NOW, path=p, kickoffs=[KICK], sport="nfl")
    assert ok is False, why


def test_the_account_can_never_be_spent_to_zero_by_this_path():
    p = _state(_tmp(), remaining=CLOSE_FLOOR + CHEAP, last=NOW - 3 * 3600)
    ok, _ = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                           sport="nfl", credits=CHEAP)
    assert ok is True, "one credit above the floor still buys the close"
    p = _state(_tmp(), remaining=CLOSE_FLOOR + CHEAP - 1, last=NOW - 3 * 3600)
    ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                            sport="nfl", credits=CHEAP)
    assert ok is False, why


def test_one_close_per_window_per_sport():
    """No new state keeps the count: the pull stamps the sport's own clock
    INSIDE the window, so the second ask no longer qualifies."""
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 3 * 3600)
    ok, _ = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                           sport="nfl", credits=CHEAP)
    assert ok is True
    landed = NOW + 60                        # the pull stamps the clock
    _state(p, remaining=RESERVE, last=landed, sport="nfl")
    ok, why = should_refresh(0, now=landed + MIN_REFRESH_GAP + 1, path=p,
                             kickoffs=[KICK], sport="nfl", credits=CHEAP)
    assert ok is False, why
    # …and another sport's clock is its own — college's close is not
    # spent by football's.
    ok, _ = should_refresh(0, now=landed + MIN_REFRESH_GAP + 1, path=p,
                           kickoffs=[KICK], sport="cfb", credits=CHEAP)
    assert ok is True


def test_the_fifteen_minute_floor_still_applies():
    """Same discipline the touchpoint override keeps: a close is a floor
    under the schedule, not a licence to re-price every minute.

    The last pull has to sit BEFORE the window opened for this to be
    about the floor at all — a pull inside the window is already refused
    by the one-per-window guard, and a fixture that mixes the two proves
    neither. The window opened ten minutes ago; this pull was twelve
    minutes ago, so only the fifteen-minute floor can refuse it."""
    assert NOW - 700 < closing_window([KICK], NOW) < NOW, "the fixture isolates the floor"
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 700)
    ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                             sport="nfl", credits=CHEAP)
    assert ok is False, why
    p = _state(_tmp(), remaining=RESERVE, last=NOW - MIN_REFRESH_GAP - 1)
    ok, _ = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                           sport="nfl", credits=CHEAP)
    assert ok is True


def test_the_days_ceiling_does_not_refuse_the_close():
    """A funded month whose slate has already spent its daily allowance
    still records the number its open bets settle against."""
    p = _tmp()
    save(BudgetState(remaining=40000, last_refresh_ts=NOW - 3 * 3600,
                     sport_last_refresh={"nfl": NOW - 3 * 3600}), p)
    real = ob.spent_today
    ob.spent_today = lambda *a, **k: 10 ** 6      # the day is long gone
    try:
        ok, why = should_refresh(0, now=NOW, path=p, kickoffs=[KICK],
                                 sport="nfl", credits=CHEAP)
        assert ok is True and "closing window" in why, why
        # …and an ask outside the window is still refused by that ceiling.
        ok, why = should_refresh(0, now=NOW - CLOSE_WINDOW_S, path=p,
                                 kickoffs=[KICK], sport="nfl", credits=CHEAP)
        assert ok is False and "budget is spent" in why, why
    finally:
        ob.spent_today = real


def test_a_slate_with_no_kickoffs_paces_exactly_as_it_did():
    """The legacy call — no kickoffs known — must not change behaviour."""
    p = _state(_tmp(), remaining=RESERVE, last=NOW - 3 * 3600)
    ok, why = should_refresh(0, now=NOW, path=p, sport="nfl", credits=CHEAP)
    assert ok is False and "quota" in why.lower(), why


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
