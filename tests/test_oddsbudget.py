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
    st = BudgetState(remaining=5000)
    per_day = daily_allowance(st)
    # Whatever the date, a month's worth is rationed, never spent at once —
    # and live pricing only ever plans to spend its LIVE_SHARE of the balance.
    assert 0 < per_day <= (5000 - RESERVE)
    assert per_day * days_left_in_month() <= (5000 - RESERVE) * 0.5 + 50


def test_refresh_gap_widens_as_quota_shrinks():
    """The scheduler must slow down as the allowance runs down."""
    from engine.oddsbudget import MIN_REFRESH_GAP
    rich = min_seconds_between(16, BudgetState(remaining=20000))
    poor = min_seconds_between(16, BudgetState(remaining=3000))
    assert poor > rich >= MIN_REFRESH_GAP


def test_cheaper_refresh_allows_more_frequent_polling():
    """Re-pricing only live/soon games costs less, so it can run more often —
    the whole point of the active-game filter."""
    whole_slate = min_seconds_between(16, BudgetState(remaining=20000))
    live_only = min_seconds_between(4, BudgetState(remaining=20000))
    assert live_only < whole_slate


def test_costs_are_denominated_in_credits_not_requests():
    """The API bills per market per region: a 16-event refresh costs
    16 x CREDITS_PER_EVENT credits, not 16. Counting requests was the 4-8x
    invisible overspend that burned a 20k plan in a day."""
    from engine.oddsbudget import CREDITS_PER_EVENT, MIN_REFRESH_GAP
    assert CREDITS_PER_EVENT >= 4
    # With ~1.4k/day allowed at 20k remaining, a 128-credit refresh must be
    # spaced in tens of minutes, not seconds.
    gap = min_seconds_between(16, BudgetState(remaining=20000))
    assert gap >= MIN_REFRESH_GAP


def test_sparse_mode_still_seeds_the_cache_when_broke():
    """~1k credits left: the daily allowance can't cover a single refresh,
    but the board still needs ONE paid pull to cache today's real prices —
    sparse mode allows it every SPARSE_INTERVAL, never below the reserve."""
    from engine.oddsbudget import SPARSE_INTERVAL
    p = _tmp()
    save(BudgetState(remaining=1000, last_refresh_ts=1_000_000.0), p)
    # Too soon -> held, with the cached-prices reassurance.
    ok, reason = should_refresh(16, now=1_000_000.0 + 3600, path=p)
    assert ok is False and "cached" in reason.lower()
    # After the sparse interval -> one pull allowed.
    ok, reason = should_refresh(16, now=1_000_000.0 + SPARSE_INTERVAL + 1, path=p)
    assert ok is True and "sparse" in reason.lower()
    # But never when it would eat into the reserve itself.
    save(BudgetState(remaining=RESERVE + 10, last_refresh_ts=0.0), p)
    ok, _ = should_refresh(16, now=SPARSE_INTERVAL * 10.0, path=p)
    assert ok is False or "prob" in _.lower()


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
    save(BudgetState(remaining=20000), p)
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




def test_sparse_pull_waits_for_the_pregame_window():
    """With ~1.3k credits and a slate, the day's ONE affordable pull must
    land where the prices are — near first pitch — not on a 12h timer that
    fires at noon against proxy lines."""
    from engine.oddsbudget import SPARSE_INTERVAL, PRIME_BEFORE_S
    p = _tmp()
    save(BudgetState(remaining=1327, last_refresh_ts=1_000_000.0), p)
    first_pitch = 1_000_000.0 + SPARSE_INTERVAL + 6 * 3600      # this evening
    kicks = [first_pitch, first_pitch + 3 * 3600]

    # Sparse interval elapsed, but it's noon: held, and the reason says when.
    noon = 1_000_000.0 + SPARSE_INTERVAL + 60
    ok, reason = should_refresh(16, now=noon, path=p, kickoffs=kicks)
    assert ok is False and "pre-game window" in reason

    # Inside the window: the pull fires.
    ok, reason = should_refresh(16, now=first_pitch - PRIME_BEFORE_S + 60,
                                path=p, kickoffs=kicks)
    assert ok is True and "sparse" in reason.lower()

    # Long after the last game: held for tomorrow, not burned at 2am.
    ok, reason = should_refresh(16, now=kicks[-1] + 6 * 3600, path=p,
                                kickoffs=kicks)
    assert ok is False and "closed for tonight" in reason


def test_offpeak_stretches_ordinary_pacing():
    """A healthy budget still leans its refreshes toward the window: the
    off-peak gap is OFFPEAK_STRETCH times wider."""
    from engine.oddsbudget import OFFPEAK_STRETCH
    p = _tmp()
    save(BudgetState(remaining=20000, last_refresh_ts=1_000_000.0), p)
    first_pitch = 1_000_000.0 + 10 * 3600
    kicks = [first_pitch]
    # Find the gap the ordinary path quotes with and without the window.
    ok_in, r_in = should_refresh(16, now=1_000_000.0 + 1,
                                 path=p, kickoffs=[1_000_000.0 - 3600])
    ok_out, r_out = should_refresh(16, now=1_000_000.0 + 1,
                                   path=p, kickoffs=kicks)
    def gap(reason):
        import re
        m = re.search(r"in (\d+)s", reason)
        return int(m.group(1)) if m else None
    g_in, g_out = gap(r_in), gap(r_out)
    if g_in is not None and g_out is not None:
        assert g_out > g_in * (OFFPEAK_STRETCH - 1)
    assert "pre-game window" in r_out or "off-peak" in r_out


def test_junk_kickoff_entries_never_crash_the_held_pull():
    """A stray None or string in the kickoff list must not raise inside the
    hold-for-the-window branch — that code runs on the refresh thread, and
    an exception there kills auto-refresh for the rest of the session."""
    from engine.oddsbudget import SPARSE_INTERVAL
    p = _tmp()
    save(BudgetState(remaining=1327, last_refresh_ts=1_000_000.0), p)
    first_pitch = 1_000_000.0 + SPARSE_INTERVAL + 6 * 3600
    noon = 1_000_000.0 + SPARSE_INTERVAL + 60
    ok, reason = should_refresh(16, now=noon, path=p,
                                kickoffs=[None, "19:05", first_pitch])
    assert ok is False and "pre-game window" in reason


def test_unknown_kickoffs_change_nothing():
    """No kickoff info (NFL "HH:MM" strings, empty slates) must behave
    exactly like the pre-time-aware pacer."""
    p = _tmp()
    save(BudgetState(remaining=1000, last_refresh_ts=1_000_000.0), p)
    from engine.oddsbudget import SPARSE_INTERVAL
    t = 1_000_000.0 + SPARSE_INTERVAL + 1
    a = should_refresh(16, now=t, path=p, kickoffs=None)
    b = should_refresh(16, now=t, path=p, kickoffs=[])
    assert a == b and a[0] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
