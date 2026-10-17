"""Every credit spent, none of it where the prices were.

Reported at 5:27pm on a fifteen-game Saturday, an hour and a half before
first pitch:

    PROPS ANALYZED 856 · RECOMMENDED BETS 0
    no real book price yet          629
    Book prices: last pulled 12:37 PM · pre-game window is open

"600 bets it didn't scan because of no book price is impossible if the games
start in an hour."

He was right, and the odds feed was not the problem. The pacer was.

The arithmetic: fifteen games is sixteen events, sixteen events is 128
credits a refresh, and `daily_allowance` divides the balance by the days
left in the month — on the 1st, by 31. A 20,000-credit balance therefore
offers ~314 credits for the whole of August 1st, which is 2.45 refreshes,
which `min_seconds_between` then spread across a nominal 14-hour day: one
pull every 5.7 HOURS. It fired at 12:37, and the next slot fell after the
games had started.

Two things were wrong with that, and they compound:

  * the day's allowance was spread over hours that have no prices. Books
    post hitter props near first pitch; a credit at 9am buys proxy lines and
    silence, and the module's own comment says so.
  * a flat 1/31st treats a fifteen-game Saturday exactly like a Tuesday in
    February. Those quiet days' credits are not lost — they are still in
    `remaining` — but the divisor cannot see the difference.

So: inside the pre-game window, spread over the WINDOW rather than the day,
and allow a bounded burst of the flat daily rate. Off-peak keeps the
conservative pace, so the quiet week still funds the busy Saturday.
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as ob


def _ts(h, m=0):
    return datetime.datetime(2026, 8, 1, h, m).timestamp()


#: The reported slate: an early game, the 7pm block, a late one.
KICKS = [_ts(15, 7)] + [_ts(19, 5)] * 10 + [_ts(20, 10)] * 3 + [_ts(22, 10)]
LAST_PULL = _ts(12, 37)
EVENTS = 16                       # fifteen games + one


def _state(remaining, path=None):
    path = path or os.path.join(tempfile.mkdtemp(), "b.json")
    st = ob.BudgetState(remaining=remaining, last_refresh_ts=LAST_PULL,
                        sport_last_refresh={"mlb": LAST_PULL})
    with open(path, "w") as fh:
        fh.write(json.dumps(st.to_dict()))
    return path


def _allowed(remaining, h, m=0, kicks=KICKS):
    ok, why = ob.should_refresh(EVENTS, now=_ts(h, m), kickoffs=kicks,
                                sport="mlb", path=_state(remaining))
    return ok, why


# --- the reported night -----------------------------------------------------
def test_a_fifteen_game_slate_gets_priced_before_first_pitch():
    """The whole complaint in one assertion."""
    for remaining in (20000, 10000, 5000):
        ok, why = _allowed(remaining, 18, 30)      # 35 minutes before 19:05
        assert ok, f"{remaining} credits still holding at 18:30 — {why}"


def test_the_old_flat_day_would_have_failed_this_test():
    """Guard the guard: if the fixture stops reproducing the bug, the test
    above stops meaning anything. Forcing the nominal 14-hour day back puts
    the 10k case behind first pitch again."""
    st = ob.BudgetState(remaining=10000)
    # Exactly the old computation: flat 14-hour day, no in-window burst.
    old_gap = ob.min_seconds_between(EVENTS, st, today=datetime.date(2026, 8, 1),
                                     active_hours=14.0, share=1.0)
    waited = _ts(18, 30) - LAST_PULL           # 12:37 -> 18:30 is 5h53m
    assert old_gap > waited, (
        f"the fixture no longer reproduces the reported night: the old pacer "
        f"would have allowed a pull after {waited / 3600:.1f}h and its gap "
        f"was {old_gap / 3600:.1f}h")
    # …and the new one clears it on the same slate.
    ok, _ = _allowed(10000, 18, 30)
    assert ok


def test_the_window_is_where_the_spending_happens():
    """Off-peak stays conservative — the point is redistribution, not a
    raise. At 8am on the same slate nothing should fire."""
    ok, why = _allowed(20000, 8, 0)
    assert not ok
    assert "off-peak" in why or "next odds refresh" in why


# --- the mechanism ----------------------------------------------------------
def test_the_window_shrinks_as_the_evening_goes_on():
    """The same remaining allowance concentrates into the time that is
    left, so a slate does not end the night holding credits it saved for
    hours that no longer exist."""
    early = ob._window_hours_left(KICKS, _ts(16, 0))
    late = ob._window_hours_left(KICKS, _ts(21, 0))
    assert early > late > 0


def test_an_unknown_kickoff_falls_back_rather_than_dividing_by_nothing():
    assert ob._window_hours_left([], _ts(18)) == 14.0
    assert ob._window_hours_left(None, _ts(18)) == 14.0


def test_the_burst_is_bounded_and_named():
    assert ob.PRIME_BURST == 3.0
    # It multiplies the SHARE, so the reserve and the month's balance still
    # bound it — this is a redistribution, not an override.
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "oddsbudget.py"),
        encoding="utf-8").read()
    assert "share = share * PRIME_BURST" in src


def test_the_reserve_is_still_untouchable():
    """A burst that can eat the emergency reserve is not a burst, it is a
    leak."""
    ok, why = _allowed(ob.RESERVE, 18, 30)
    assert not ok
    assert "exhausted" in why or "reserve" in why


def test_a_slate_with_no_kickoffs_keeps_the_old_behaviour():
    """prime_window returns None when it cannot tell, and None is not True —
    an unknown slate must not silently get the burst."""
    ok_known, _ = _allowed(10000, 18, 30)
    ok_blind, _ = _allowed(10000, 18, 30, kicks=[])
    assert ok_known and not ok_blind


# --- and the page says so ---------------------------------------------------
def test_the_next_paid_pull_is_reported_to_the_page():
    """"629 props with no book price" an hour before first pitch is
    unanswerable from the page unless it also says when the next pull is
    due. That reasoning lived only in the launcher's terminal."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = open(os.path.join(root, "mlb_build.py"), encoding="utf-8").read()
    assert 'odds_status["next_pull_at"]' in build
    js = open(os.path.join(root, "web", "js", "app.js"), encoding="utf-8").read()
    assert "next_pull_at" in js and "next paid pull" in js


def test_a_pull_already_due_is_not_advertised_as_pending():
    js = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "js", "app.js"),
        encoding="utf-8").read()
    i = js.index("next paid pull")
    assert "due > Date.now()" in js[i - 200:i]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
