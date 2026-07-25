"""Odds request budgeting.

Refreshing a full slate's odds costs about one API request per game, so naive
constant polling spends a free plan's entire month in under an hour. These tests
pin the behaviour that prevents that.

Run directly: `python3 tests/test_oddsbudget.py`
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.oddsbudget import (
    BudgetState, RESERVE, daily_allowance, days_left_in_month, load,
    min_seconds_between, mark_refreshed, record_quota, save, should_refresh,
)


def _tmp():
    return Path(tempfile.mkdtemp()) / "budget.json"


def test_state_roundtrip_and_missing_file():
    p = _tmp()
    assert load(p).remaining == 500              # sane default before first call
    save(BudgetState(remaining=321, used=179), p)
    st = load(p)
    assert st.remaining == 321 and st.used == 179


def test_record_quota_tracks_the_real_account():
    p = _tmp()
    record_quota("437", "63", p)
    assert load(p).remaining == 437
    # Garbage headers must not corrupt the budget.
    record_quota("?", "?", p)
    assert load(p).remaining == 437


def test_daily_allowance_spreads_what_is_left():
    st = BudgetState(remaining=500)
    per_day = daily_allowance(st)
    # Whatever the date, a month's worth is rationed, never spent at once.
    assert 0 < per_day <= 500 - RESERVE
    assert per_day * days_left_in_month() <= 500


def test_refresh_gap_widens_as_quota_shrinks():
    """The scheduler must slow down as the allowance runs down."""
    rich = min_seconds_between(16, BudgetState(remaining=500))
    poor = min_seconds_between(16, BudgetState(remaining=120))
    assert poor > rich >= 60


def test_cheaper_refresh_allows_more_frequent_polling():
    """Re-pricing only live/soon games costs less, so it can run more often —
    the whole point of the active-game filter."""
    whole_slate = min_seconds_between(16, BudgetState(remaining=500))
    live_only = min_seconds_between(4, BudgetState(remaining=500))
    assert live_only < whole_slate


def test_exhausted_quota_stops_odds_but_not_the_app():
    p = _tmp()
    # A recent refresh, so this isn't due for the periodic recovery probe.
    save(BudgetState(remaining=RESERVE, last_refresh_ts=1_000_000.0), p)
    ok, reason = should_refresh(16, now=1_000_060.0, path=p)
    assert ok is False
    assert "quota" in reason.lower()
    # A reserve is deliberately preserved rather than spent to zero.
    assert load(p).remaining >= RESERVE


def test_refresh_is_rate_limited_between_calls():
    p = _tmp()
    save(BudgetState(remaining=500), p)
    ok, _ = should_refresh(16, now=1_000_000.0, path=p)
    assert ok is True                       # nothing spent yet -> allowed
    mark_refreshed(1_000_000.0, p)
    ok, reason = should_refresh(16, now=1_000_060.0, path=p)
    assert ok is False                      # a minute later -> too soon
    assert "next odds refresh" in reason


def test_active_game_filter_targets_what_still_matters():
    import datetime as dt
    from engine.sources.oddsapi import _is_active
    from engine.mlb.models import MLBGame
    from engine.models import LiveStatus

    now = dt.datetime.now()
    live = MLBGame(home="A", away="B", park="x", live=LiveStatus(state="live"))
    final = MLBGame(home="A", away="B", park="x", live=LiveStatus(state="final"))
    soon = MLBGame(home="A", away="B", park="x",
                   kickoff=(now + dt.timedelta(hours=2)).isoformat())
    later = MLBGame(home="A", away="B", park="x",
                    kickoff=(now + dt.timedelta(hours=20)).isoformat())

    assert _is_active(live, 6.0) is True
    assert _is_active(final, 6.0) is False      # finished — price can't matter
    assert _is_active(soon, 6.0) is True
    assert _is_active(later, 6.0) is False      # tomorrow — don't spend on it
    # Unknown start time is treated as active rather than silently skipped.
    assert _is_active(MLBGame(home="A", away="B", park="x"), 6.0) is True


def test_assumed_quota_is_labelled_as_assumed():
    """An assumed 500 looks identical to a confirmed 500 — say which it is."""
    from engine.oddsbudget import summary, is_measured
    p = _tmp()
    assert is_measured(load(p)) is False
    assert "not yet measured" in summary(p)
    record_quota("412", "88", p)
    assert is_measured(load(p)) is True
    text = summary(p)
    assert "412 left" in text and "not yet measured" not in text


def test_new_key_recovers_from_an_exhausted_budget():
    """A replacement key must not inherit the dead key's zero balance."""
    from engine.oddsbudget import reset, is_measured
    p = _tmp()
    record_quota(0, None, p)                       # old key ran out
    mark_refreshed(1_000_000.0, p)                 # ...and we just tried
    assert should_refresh(16, now=1_000_060.0, path=p)[0] is False
    reset(p)
    assert is_measured(load(p)) is False            # clean slate, re-learns on next call
    assert should_refresh(16, now=1_000_000.0, path=p)[0] is True


def test_exhausted_budget_probes_occasionally():
    """Plans reset monthly; without an occasional probe the budgeter would
    refuse to call and so never discover the quota came back."""
    from engine.oddsbudget import PROBE_INTERVAL
    p = _tmp()
    save(BudgetState(remaining=0, last_refresh_ts=1_000_000.0), p)
    soon, _ = should_refresh(16, now=1_000_000.0 + 60, path=p)
    assert soon is False
    later, reason = should_refresh(16, now=1_000_000.0 + PROBE_INTERVAL + 1, path=p)
    assert later is True and "probing" in reason


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
