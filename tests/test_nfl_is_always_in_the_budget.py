"""NFL is always in the odds budget.

Ethan, 2026-10-04: "as ive said before nfl is most important so we need
NFL in the budget at all times." The box that Sunday morning, 10:57:

    today's odds budget is spent for this slate (331 of 528 credits;
    a pull costs 272) — cached prices keep the board filled

College, weighted for its one game day a week, still claimed the largest
slice of a Sunday it does not play, and NFL's slice held one more pull
than it had already spent. Checks, one rule each: on a day with an NFL
kickoff inside 24 hours, NFL's day never caps below
oddsbudget.PRIORITY_PULLS full pulls; past that floor the ceiling still
holds; without a kickoff in the next day the floor does not apply; and
another league gets no floor.

Run directly: `python3 tests/test_nfl_is_always_in_the_budget.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as ob                          # noqa: E402

#: Sunday 2026-10-04, 10:57 Eastern on the box, and its 1 PM kickoff.
NOW = dt.datetime(2026, 10, 4, 10, 57, 0).timestamp()
KICK = dt.datetime(2026, 10, 4, 13, 0, 0).timestamp()
PULL = 272


def _verdict(spent: int, sport: str = "nfl", kickoffs=(KICK,), share: float = 0.05):
    tmp = Path(tempfile.mkdtemp())
    ledger = tmp / "spend.jsonl"
    day = dt.datetime.fromtimestamp(NOW - 3600).isoformat(timespec="seconds")
    with ledger.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": NOW - 3600, "iso": day, "kind": "live_event", "sport": sport,
                             "credits": spent, "detail": ""}) + "\n")
    state = tmp / "budget.json"
    # This league last pulled half an hour ago — after the readiness window
    # opened (10:00), before the inactives one (11:40) — so neither one-pull
    # door is open and the day's ceiling is what decides.
    ob.save(ob.BudgetState(remaining=86681, last_refresh_ts=NOW - 3600,
                           last_seen_iso="2026-10-04T10:52:54",
                           sport_last_refresh={sport: NOW - 1800}), state)
    keep = ob.SPEND_LOG
    ob.SPEND_LOG = ledger
    ob._TODAY_CACHE.clear()
    try:
        return ob.should_refresh(17, now=NOW, path=state, kickoffs=list(kickoffs), sport=sport,
                                 share=share, credits=PULL, today=dt.date(2026, 10, 4))
    finally:
        ob.SPEND_LOG = keep
        ob._TODAY_CACHE.clear()


def test_the_sunday_morning_refusal_is_gone():
    ok, why = _verdict(331)
    assert ok, why


def test_past_the_floor_the_ceiling_still_holds():
    spent = ob.PRIORITY_PULLS["nfl"] * PULL
    ok, why = _verdict(spent)
    assert not ok and "budget is spent for this slate" in why, why


def test_no_kickoff_in_the_next_day_means_no_floor():
    ok, why = _verdict(331, kickoffs=(NOW + 3 * 86400,))
    assert not ok, why


def test_another_league_gets_no_floor():
    ok, why = _verdict(331, sport="nhl")
    assert not ok, why


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
