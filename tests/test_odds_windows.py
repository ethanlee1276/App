"""Guaranteed odds-refresh windows.

The pacer in ``engine/oddsbudget`` spends a credit where a credit buys the
most, which means it holds its money for the pre-game hours and lets the
morning board sit on yesterday's prices. That was the right trade while
nobody was looking at the site. It stopped being the right trade the day
the site had subscribers, so a floor was added: four times a day — 7am,
noon, 3pm, 6pm Eastern — the day's first paid pull for a sport is allowed
through even when off-peak pacing would have held it.

These tests pin the two things that make that floor safe rather than
expensive: it fires ONCE per window per sport, and it never spends money
the month does not have.

Run directly: `python3 tests/test_odds_windows.py`
"""

import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget
from engine.oddsbudget import (
    BudgetState, MIN_REFRESH_GAP, RESERVE, TOUCHPOINTS, TOUCHPOINT_GRACE_S,
    load, mark_refreshed, paid_pull_result, record_quota, save,
    should_refresh, touchpoint_due,
)

EAST = ZoneInfo("America/New_York")
# A midsummer Saturday: nothing about the arithmetic depends on the date
# except days-left-in-the-month, which the tests below take into account.
DAY = (2026, 8, 15)


def _tmp():
    return Path(tempfile.mkdtemp()) / "budget.json"


def at(hour, minute=0, day=None):
    """An epoch stamp for a wall-clock time in EASTERN, not in UTC."""
    y, m, d = DAY
    return _dt.datetime(y, m, day or d, hour, minute, tzinfo=EAST).timestamp()


def _funded(p, last_refresh_hour=6, sport="mlb", remaining=20000):
    """A state with real money and a pull an hour ago — the shape where
    off-peak pacing says "wait" and only a window can say otherwise."""
    save(BudgetState(remaining=remaining,
                     last_refresh_ts=at(last_refresh_hour),
                     sport_last_refresh={sport: at(last_refresh_hour)}), p)


def test_the_windows_are_the_hours_that_were_asked_for():
    assert TOUCHPOINTS == (7, 12, 15, 18)


def test_off_peak_pacing_would_otherwise_hold_the_morning():
    """The premise. If ordinary pacing already allowed a 7am pull there
    would be nothing for a window to override, and every test below would
    be passing for the wrong reason."""
    p = _tmp()
    _funded(p)
    # Claim the 7am window first, so only ordinary pacing is left to answer.
    st = load(p)
    st.sport_touchpoint["mlb"] = "2026-08-15:07"
    save(st, p)
    ok, why = should_refresh(16, now=at(7), path=p, sport="mlb",
                             kickoffs=[at(19, 5)])
    assert ok is False and "next odds refresh in" in why


def test_each_window_opens_the_gate_once():
    p = _tmp()
    _funded(p)
    kicks = [at(19, 5)]

    ok, why = should_refresh(16, now=at(7), path=p, sport="mlb", kickoffs=kicks)
    assert ok is True, why
    assert "7am refresh window" in why
    mark_refreshed(at(7), p, sport="mlb")

    # Same window, half an hour later: the pull already happened.
    ok, why = should_refresh(16, now=at(7, 30), path=p, sport="mlb",
                             kickoffs=kicks)
    assert ok is False, why
    # Still inside the grace period, still served.
    ok, _ = should_refresh(16, now=at(8, 30), path=p, sport="mlb",
                           kickoffs=kicks)
    assert ok is False

    # Noon is a different window and gets its own pull.
    ok, why = should_refresh(16, now=at(12), path=p, sport="mlb",
                             kickoffs=kicks)
    assert ok is True and "12pm refresh window" in why


def test_a_window_never_beats_the_fifteen_minute_floor():
    """MIN_REFRESH_GAP is the hard floor the whole module rests on: it is
    what stops a refresh loop ticking every 60s from turning one window
    into sixty paid pulls."""
    p = _tmp()
    save(BudgetState(remaining=20000, last_refresh_ts=at(6, 55),
                     sport_last_refresh={"mlb": at(6, 55)}), p)
    ok, why = should_refresh(16, now=at(7, 5), path=p, sport="mlb",
                             kickoffs=[at(19, 5)])
    assert ok is False, why
    assert "window" not in why or "pre-game" in why
    # Ten minutes later the floor is cleared and the window is still owed.
    ok, why = should_refresh(16, now=at(7, 12), path=p, sport="mlb",
                             kickoffs=[at(19, 5)])
    assert ok is True and "7am" in why
    assert at(7, 12) - at(6, 55) >= MIN_REFRESH_GAP


def test_a_window_cannot_spend_into_the_reserve():
    """A balance that cannot afford a refresh gets no window pull. The
    reserve is the last thing standing between a bad month and a board
    with no prices on it at all."""
    p = _tmp()
    # 900 credits: above the reserve, so this is not the exhausted-quota
    # short circuit — the day simply cannot afford a 128-credit refresh.
    save(BudgetState(remaining=RESERVE + 400, last_refresh_ts=at(6),
                     sport_last_refresh={"mlb": at(6)}), p)
    ok, why = should_refresh(16, now=at(7), path=p, sport="mlb",
                             kickoffs=[at(19, 5)])
    assert ok is False, why
    assert load(p).sport_touchpoint == {}       # nothing was claimed either


def test_the_hours_are_eastern_not_the_droplets_utc():
    """The server runs UTC — its backups stamp 13:09Z while the clock on
    the desk reads 9:09am. A naive local hour would put the "7am" window
    at 3am Eastern and nobody would notice, because the symptom (a stale
    morning board) is the same symptom the window exists to fix."""
    p = _tmp()
    seven_eastern = at(7)
    assert oddsbudget._local(seven_eastern).hour == 7
    # The same instant in UTC is not 7 — so a UTC reading would disagree.
    assert _dt.datetime.fromtimestamp(seven_eastern, _dt.timezone.utc).hour != 7
    st = load(p)
    assert touchpoint_due(st, "mlb", seven_eastern) == "2026-08-15:07"
    # 3am Eastern is 7am UTC: owed under a naive implementation, not here.
    three_eastern = at(3)
    assert _dt.datetime.fromtimestamp(three_eastern, _dt.timezone.utc).hour == 7
    assert touchpoint_due(st, "mlb", three_eastern) is None


def test_nothing_is_owed_before_the_first_window():
    st = BudgetState()
    assert touchpoint_due(st, "mlb", at(5)) is None
    assert touchpoint_due(st, "mlb", at(6, 59)) is None


def test_a_missed_window_expires_instead_of_firing_at_midnight():
    st = BudgetState()
    assert touchpoint_due(st, "mlb", at(8, 59)) == "2026-08-15:07"
    # Past the grace period with no later window yet: the 7am pull is not
    # worth buying at 9:30, and the noon one is a different decision.
    late = at(7) + TOUCHPOINT_GRACE_S + 60
    assert touchpoint_due(st, "mlb", late) is None


def test_windows_are_per_sport():
    """A shared claim would mean whichever sport the launcher checks first
    each cycle eats every window and the other board stays stale — the
    same starvation the per-sport refresh clock was added to fix."""
    p = _tmp()
    save(BudgetState(remaining=20000,
                     sport_last_refresh={"mlb": at(11), "nfl": at(11)}), p)
    ok, _ = should_refresh(16, now=at(12), path=p, sport="mlb",
                           kickoffs=[at(19, 5)])
    assert ok is True
    mark_refreshed(at(12), p, sport="mlb")
    ok, why = should_refresh(16, now=at(12, 5), path=p, sport="nfl",
                             kickoffs=[at(19, 5)])
    assert ok is True and "12pm" in why, why


def test_a_claim_survives_being_written_and_read_back():
    """load() dropping this field would forget every claim between calls,
    and a forgotten claim re-authorises the window every 15 minutes for
    the whole two-hour grace period — eight paid pulls where one was
    intended."""
    p = _tmp()
    _funded(p)
    mark_refreshed(at(7), p, sport="mlb")
    assert load(p).sport_touchpoint.get("mlb") == "2026-08-15:07"


def test_the_production_path_claims_its_window():
    """launch.py confirms paid pulls through paid_pull_result, not through
    mark_refreshed. A claim that only happened in mark_refreshed would
    never happen at all in the live app."""
    p = _tmp()
    _funded(p)
    before = load(p).last_seen_iso
    record_quota(19872, 128, p)                  # the API answered
    assert paid_pull_result(before, path=p, now=at(7), sport="mlb") is True
    assert load(p).sport_touchpoint.get("mlb") == "2026-08-15:07"


def test_a_pull_the_burst_paid_for_still_claims_the_window():
    """The window wants a fresh board at 6pm, not a second purchase of
    prices the app already has. Whatever authorised the pull claims it."""
    p = _tmp()
    save(BudgetState(remaining=20000,
                     sport_last_refresh={"mlb": at(14)}), p)
    kicks = [at(19, 5)]                          # pre-game window opens 16:35
    ok, why = should_refresh(16, now=at(18, 10), path=p, sport="mlb",
                             kickoffs=kicks)
    assert ok is True, why
    mark_refreshed(at(18, 10), p, sport="mlb")
    assert load(p).sport_touchpoint.get("mlb") == "2026-08-15:18"


def test_a_failed_pull_claims_nothing():
    """Authorisation is not a pull. If the API never answered, the window
    is still owed — the whole reason paid_pull_result exists."""
    p = _tmp()
    _funded(p)
    before = load(p).last_seen_iso
    assert paid_pull_result(before, path=p, now=at(7), sport="mlb") is False
    assert load(p).sport_touchpoint == {}


def test_yesterdays_claims_are_pruned():
    p = _tmp()
    save(BudgetState(remaining=20000,
                     sport_touchpoint={"nfl": "2026-08-14:18"},
                     sport_last_refresh={"mlb": at(11)}), p)
    mark_refreshed(at(12), p, sport="mlb")
    assert load(p).sport_touchpoint == {"mlb": "2026-08-15:12"}


def test_the_windows_can_be_moved_without_a_deploy():
    p = _tmp()
    st = load(p)
    os.environ["QB_ODDS_WINDOWS"] = "6, 9"
    try:
        assert oddsbudget._touchpoints() == (6, 9)
        assert touchpoint_due(st, "mlb", at(6, 30)) == "2026-08-15:06"
        assert touchpoint_due(st, "mlb", at(12, 30)) is None
        os.environ["QB_ODDS_WINDOWS"] = "nonsense"
        assert oddsbudget._touchpoints() == TOUCHPOINTS   # bad input ignored
    finally:
        os.environ.pop("QB_ODDS_WINDOWS", None)


def test_four_windows_a_day_are_affordable_on_the_real_plan():
    """The arithmetic that made this safe to ship: a 15-game slate costs
    ~128 credits a pull, the balance in hand is ~20k, and half of what is
    left after the reserve is what live pricing may spend."""
    p = _tmp()
    save(BudgetState(remaining=20000), p)
    per_pull = 16 * oddsbudget.CREDITS_PER_EVENT
    assert per_pull == 128
    # Mid-month, with 17 days to go.
    afford = oddsbudget.daily_allowance(load(p), _dt.date(2026, 8, 15))
    assert afford // per_pull >= len(TOUCHPOINTS)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
