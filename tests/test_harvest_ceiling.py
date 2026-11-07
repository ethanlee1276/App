"""The harvest spends the meter the board pull is judged by.

Ethan, 2026-09-10: "We haven't been getting any edge bets or most likely
bets for mlb for a while now."

Measured on the droplet that evening, and every number below is one of
those:

    MLB board            290 props analysed, 0 with a real price
    gate_census          no_real_price 290 (Hits 90, Total Bases 90,
                         Home Runs 90, …)
    decisions, 24h       mlb  0 pull / 235 hold
    the refusal          "today's odds budget is spent for this slate
                         (235 of 136 credits; a pull costs 48)"
    the ledger, today    mlb hist_event  225 cr (9 calls)
                         mlb hist_events  10 cr (1 call)
                         mlb live_*        0 cr
    last paid MLB pull   64.9h ago

Every credit baseball spent went to the HARVEST — `/historical/` calls
that buy the closing line of a game already over, so a settled bet can be
graded. Not one went to the board. And yet the day's ceiling, whose job
is to pace the BOARD pull, counted all 235 of them: 235 against a 136
ceiling refuses a 48-credit pull for the rest of the day, every day.
Sixty-five hours of that is past the 48h show ceiling, so all 290 props
fell back to a proxy line and both boards emptied together.

`should_refresh` states the invariant this broke, in its own words:

    "So the ceiling never blocks the day's FIRST pull; it stops the
     second, third and fortieth."

It could not keep that promise while metering a lane that never asks it.
Football never noticed: its ceiling is four times baseball's.
"""

import sys
import tempfile
import json
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as ob                          # noqa: E402


#: THE DAY, AS A CLOCK AND NOT JUST A STORY. Every number in the docstring
#: above was measured on 2026-09-10, and the day's ceiling is one of them:
#: `daily_allowance` divides the month's balance by the days LEFT in the
#: month, so the same 62,092 credits buy a 136-credit slice for baseball on
#: the 10th and a 204-credit slice on the 17th. Read the wall clock and
#: this file asserts a different arithmetic every morning — which is what
#: happened: the second-pull case spends 176 against that ceiling, so it
#: held until the 13th and then failed every night from the 14th, on code
#: that never changed. `should_refresh` warns about this exact trap in its
#: own comments ("a test that passed on the 28th failed on the 29th"), and
#: gives the answer: take the date from the same clock the rest of the
#: numbers came from. Nothing below reads the real one.
THE_DAY_TS = dt.datetime(2026, 9, 10, 17, 27, 48).timestamp()


def _ledger(rows, when: float = THE_DAY_TS):
    """A spend ledger holding `rows` of (kind, sport, credits), dated `when`.

    The ledger's date has to be the same day the reader asks about, or
    `spent_today` sees an empty day and every ceiling case passes by
    finding nothing spent."""
    tmp = Path(tempfile.mkdtemp()) / "spend.jsonl"
    day = dt.datetime.fromtimestamp(when).isoformat(timespec="seconds")
    with tmp.open("w", encoding="utf-8") as fh:
        for kind, sport, credits in rows:
            fh.write(json.dumps({"ts": 0, "iso": day, "kind": kind,
                                 "sport": sport, "credits": credits,
                                 "detail": ""}) + "\n")
    ob._TODAY_CACHE.clear()
    return tmp


#: The droplet's own numbers, 2026-09-10.
THE_DAY = [("hist_event", "mlb", 25)] * 9 + [("hist_events", "mlb", 10)]


def test_the_harvest_is_named_and_the_board_pull_is_not():
    assert "hist_event" in ob.HARVEST_KINDS and "hist_events" in ob.HARVEST_KINDS
    for live in ("live_event", "live_board", "live_events"):
        assert live not in ob.HARVEST_KINDS, live


def test_a_report_still_counts_every_credit_the_league_spent():
    """The money DID leave the account. Whatever the ceiling meters, the
    question "what did baseball spend today" keeps its old answer, or
    every spend report quietly under-reports."""
    p = _ledger(THE_DAY)
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb") == 235


def test_the_ceiling_does_not_meter_the_harvest():
    p = _ledger(THE_DAY)
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb",
                          exclude=ob.HARVEST_KINDS) == 0


def test_a_board_pull_still_counts_against_itself():
    """The exclusion is one lane, not an amnesty: the ceiling exists to
    stop the second, third and fortieth board pull, and it still does."""
    p = _ledger(THE_DAY + [("live_event", "mlb", 48)])
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb",
                          exclude=ob.HARVEST_KINDS) == 48


def test_the_cache_answers_each_question_with_its_own_number():
    """Both questions read the same file within one cycle. Keyed on the
    league alone, the second would be served the first's answer."""
    p = _ledger(THE_DAY + [("live_event", "mlb", 48)])
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb") == 283
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb",
                          exclude=ob.HARVEST_KINDS) == 48
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb") == 283   # not 48
    assert ob.spent_today(THE_DAY_TS, path=p, sport="mlb",
                          exclude=ob.HARVEST_KINDS) == 48           # not 283


def _verdict(ledger, remaining=62092, share=0.093, games=5, now=THE_DAY_TS,
             last_refresh_ts=0.0):
    """`should_refresh` for baseball, on the droplet's own shape.

    `last_refresh_ts` is left at zero for the ordinary cases — the pacer
    reads the per-SPORT clock for those — and set only where the
    whole-account probe would otherwise answer instead of the branch
    under test.

    `now` defaults to THE_DAY_TS, which fixes the day's ceiling as well as
    the cadence: `should_refresh` derives its date from whatever `now` it
    is handed, so a pinned clock here is what keeps the arithmetic below
    the same one the droplet did.
    """
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    ob.save(ob.BudgetState(remaining=remaining,
                           last_refresh_ts=last_refresh_ts,
                           last_seen_iso="2026-09-10T17:27:48"), tmp)
    keep = ob.SPEND_LOG
    ob.SPEND_LOG = ledger
    try:
        events = games + 1
        return ob.should_refresh(events, now=now, path=tmp, kickoffs=None,
                                 sport="mlb", share=share,
                                 credits=events * ob.credits_per_event("mlb"))
    finally:
        ob.SPEND_LOG = keep
        ob._TODAY_CACHE.clear()


def test_the_days_first_board_pull_survives_a_days_harvest():
    """THE BUG, in the shape it actually had. 235 credits of harvest, a
    136-credit ceiling, a 48-credit pull, and a board that has shown no
    price in sixty-five hours."""
    ok, why = _verdict(_ledger(THE_DAY))
    assert ok, why
    assert "budget is spent for this slate" not in why, why


def test_the_ceiling_still_stops_the_second_board_pull():
    """The other half. A league that has already bought its board today
    is paced exactly as before — this is a ceiling, not a licence."""
    ok, why = _verdict(_ledger(THE_DAY + [("live_event", "mlb", 128)]))
    assert not ok, why
    assert "budget is spent for this slate" in why, why


def test_the_ceiling_stops_the_second_pull_on_every_day_of_the_month():
    """The case above is pinned to one day, which is what makes its numbers
    readable and what makes it blind to the other twenty-nine. The CEILING
    moves by design — the month's balance is divided by the days LEFT in
    it, so baseball's slice of 62,092 credits grows from 95 on the 1st to
    over 2,000 on the 30th — and a case that spends a fixed 128 against it
    is only testing the rule on the days the arithmetic happens to line up.

    What must not move is the rule: a league that has already spent its
    slice today is refused, whatever the slice is worth. So spend exactly
    that day's slice, on that day, and ask again.

    This is the assertion that turns the earlier fault into an honest
    signal. A calendar-dependent case fails on some mornings and not
    others, which reads as flakiness in the code; this one fails on no day
    of the month or on all thirty, which reads as what it is."""
    state = ob.BudgetState(remaining=62092, last_refresh_ts=0.0,
                           last_seen_iso="2026-09-10T17:27:48")
    cost = 6 * ob.credits_per_event("mlb")
    for day in range(1, 31):
        ts = dt.datetime(2026, 9, day, 17, 27, 48).timestamp()
        # The day's own ceiling, floored at one pull exactly as
        # `should_refresh` floors it.
        ceiling = max(int(ob.daily_allowance(state, dt.date(2026, 9, day))
                          * 0.093), cost)
        ok, why = _verdict(_ledger(THE_DAY + [("live_event", "mlb", ceiling)],
                                   when=ts), now=ts)
        assert not ok, f"Sep {day}: {why}"
        assert "budget is spent for this slate" in why, f"Sep {day}: {why}"
        # …and the same day's FIRST pull is still affordable, so this is
        # not passing because the whole month refuses everything.
        ok, why = _verdict(_ledger(THE_DAY, when=ts), now=ts)
        assert ok, f"Sep {day}, first pull: {why}"


def test_football_is_unchanged_by_any_of_this():
    """The league that never hit the bug must not move. Its own harvest
    is small and its ceiling is four times baseball's, so the verdict on
    an ordinary NFL day is the same before and after."""
    p = _ledger([("live_event", "nfl", 204), ("live_board", "nfl", 3)])
    assert ob.spent_today(THE_DAY_TS, path=p, sport="nfl") == 207
    assert ob.spent_today(THE_DAY_TS, path=p, sport="nfl",
                          exclude=ob.HARVEST_KINDS) == 207


def test_the_month_reserve_still_refuses_everything():
    """The exclusion touches the DAY's ceiling and nothing above it. A
    plan spent down to its reserve says no, harvest or no harvest."""
    ok, why = _verdict(_ledger(THE_DAY), remaining=ob.RESERVE - 1,
                       last_refresh_ts=THE_DAY_TS)
    assert not ok, why
    assert "quota nearly exhausted" in why, why


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
