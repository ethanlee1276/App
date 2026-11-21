"""A price past the age ceiling buys a fresh one instead of blanking the board.

Ethan, 2026-09-08, after the ceiling shipped: "I don't want you too stop
working until we display the right lines and prices the books show."

The ceiling (`oddsapi.MAX_GAME_PRICE_AGE`) is half the job. It stops a
stale payload being published as a price, which ends the wrong-line
reports — and on a cycle the pacer declines it leaves the shelf empty
instead, because the cheap whole-slate game-lines pull was authorised by
ordinary pacing only. An empty shelf is honest and it is not what he
asked for.

So the pacer gets a third override, beside the two it already has for
the close and the readiness pull: when the prices this pull would
replace are past the ceiling, the board is REFUSING to show them, and
this pull is the difference between an empty shelf and a real number. It
is bounded exactly like the close — cheap only (`STALE_MAX_CREDITS`),
behind the fifteen-minute floor, and never below the month's reserve,
because a plan with nothing left showing no price is the honest state of
a plan with nothing left.

`launch._lines_stale` is where the fact comes from: the age of the
sport's own whole-slate cache file, asked of the same ceiling the board
refuses on, so the pacer and the board can never disagree about whether
a price is too old.

Run directly: `python3 tests/test_stale_price_pull.py`
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.oddsbudget import (                              # noqa: E402
    BudgetState, MIN_REFRESH_GAP, RESERVE, STALE_MAX_CREDITS, save,
    should_refresh,
)

LINES = 3          # what the whole-slate game-lines pull costs
NOW = 1_700_000_000.0


def _tmp():
    return Path(tempfile.mkdtemp()) / "budget.json"


def _state(p, remaining=20000, last=NOW - 60):
    """A healthy month whose last pull was a minute ago — inside the
    fifteen-minute floor, so ordinary pacing refuses."""
    save(BudgetState(remaining=remaining, last_refresh_ts=last), p)
    return p


# --- the override -------------------------------------------------------------
def test_ordinary_pacing_still_refuses_a_pull_a_minute_after_the_last_one():
    p = _state(_tmp())
    ok, _why = should_refresh(1, now=NOW, path=p, credits=LINES)
    assert ok is False, "the fixture is not exercising a refusal"


def test_a_stale_price_turns_that_refusal_into_a_pull():
    p = _state(_tmp(), last=NOW - MIN_REFRESH_GAP - 1)
    ok, why = should_refresh(1, now=NOW, path=p, credits=LINES)
    assert ok is True, why       # past the floor, a healthy month: allowed anyway
    # …and the point of the branch is the case ordinary pacing refuses.
    p = _state(_tmp(), remaining=RESERVE + 40, last=NOW - MIN_REFRESH_GAP - 1)
    ok, _why = should_refresh(1, now=NOW, path=p, credits=LINES)
    assert ok is False, "a poor month should refuse the ordinary pull"
    ok, why = should_refresh(1, now=NOW, path=p, credits=LINES, prices_stale=True)
    assert ok is True and "past the age ceiling" in why, why
    assert "refusing to show them" in why


def test_the_fifteen_minute_floor_still_holds():
    """A stale price is not a licence to hammer the API: the floor every
    override answers to is the same one."""
    p = _state(_tmp(), remaining=RESERVE + 40, last=NOW - 60)
    ok, why = should_refresh(1, now=NOW, path=p, credits=LINES, prices_stale=True)
    assert ok is False, why


def test_the_override_will_not_authorise_an_expensive_pull():
    """The whole-slate lines call is three credits; the per-event prop
    pull is twelve a GAME. An override that can buy the second is not an
    override."""
    p = _state(_tmp(), remaining=RESERVE + 4000, last=NOW - MIN_REFRESH_GAP - 1)
    ok, why = should_refresh(1, now=NOW, path=p, credits=STALE_MAX_CREDITS,
                             prices_stale=True)
    assert ok is True, why
    ok, why = should_refresh(1, now=NOW, path=p, credits=STALE_MAX_CREDITS + 1,
                             prices_stale=True)
    assert "past the age ceiling" not in why, why


def test_it_never_reaches_the_months_reserve():
    """A plan with nothing left showing no price is the honest state of a
    plan with nothing left, and the close is still the one exception."""
    p = _state(_tmp(), remaining=RESERVE, last=NOW - MIN_REFRESH_GAP - 1)
    ok, why = should_refresh(1, now=NOW, path=p, credits=LINES, prices_stale=True)
    assert ok is False and "quota" in why.lower(), why


def test_it_beats_the_twelve_hour_sparse_timer():
    """Starvation mode holds the day's one pull for the pre-game window.
    That is the right answer for an ordinary refresh and the wrong one
    for a board refusing to show a price right now."""
    p = _state(_tmp(), remaining=RESERVE + 40, last=NOW - MIN_REFRESH_GAP - 1)
    ok, why = should_refresh(1, now=NOW, path=p, credits=LINES,
                             kickoffs=[NOW + 30 * 3600], prices_stale=True)
    assert ok is True and "past the age ceiling" in why, why


def test_the_close_and_the_readiness_pull_are_not_preempted():
    """The two overrides that were already there speak for themselves.
    Inside their windows the staleness branch stands down, so a reader is
    never told the board bought a price because it was old when the real
    reason was the close — the one pull whose value does not come back
    tomorrow."""
    from engine.oddsbudget import CLOSE_WINDOW_S, READY_BEFORE_S
    for kick, word in ((NOW + CLOSE_WINDOW_S - 60, "closing"),
                       (NOW + READY_BEFORE_S - 60, "readiness")):
        p = _state(_tmp(), remaining=RESERVE + 4000, last=NOW - MIN_REFRESH_GAP - 1)
        ok, why = should_refresh(1, now=NOW, path=p, credits=LINES,
                                 sport="nfl", kickoffs=[kick], prices_stale=True)
        assert ok is True, why
        assert "past the age ceiling" not in why, (word, why)


# --- where the fact comes from --------------------------------------------------
def test_launch_asks_the_same_ceiling_the_board_refuses_on():
    import launch
    from engine.sources import oddsapi as oa
    real = (oa.sport_cache_age, oa.price_is_current)
    try:
        oa.sport_cache_age = lambda sport, tag="", now=None: 9 * 3600
        assert launch._lines_stale("nfl") is True
        oa.sport_cache_age = lambda sport, tag="", now=None: 1800
        assert launch._lines_stale("nfl") is False
        # Nothing cached is not stale — there is no price to be old.
        oa.sport_cache_age = lambda sport, tag="", now=None: None
        assert launch._lines_stale("nfl") is False
        # A pacing question is never answered by an exception.
        def boom(*a, **k):
            raise RuntimeError("cache unreadable")
        oa.sport_cache_age = boom
        assert launch._lines_stale("nfl") is False
    finally:
        oa.sport_cache_age, oa.price_is_current = real


def test_both_football_lanes_pass_the_fact():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert 'prices_stale=_lines_stale("nfl")' in src
    assert 'prices_stale=_lines_stale("cfb", "")' in src, \
        "college writes its whole-slate payload with no cache tag"
    assert "prices_stale=prices_stale)" in src, "the flag never reaches the pacer"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
