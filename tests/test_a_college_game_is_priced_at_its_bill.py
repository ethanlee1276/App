"""A college basketball game is priced at what the odds feed bills for it (step AER, 25 November 2026).

Ethan's decision A, 24 November 2026: "A, yes more" (college games with priced props). The feed bills a game call
for the markets the books have posted, not the ones asked for: the heartbeat's first `odds_bill` that evening had
college basketball's last 30 calls billed 271 credits where our 13 a game said 390. So:

  * college basketball is priced at the average its last week of billed calls came to, rounded up (271 over 30 is
    10), from 20 calls on; with fewer, at its table price; never above it; every other league at its table;
  * the price is read off the ledger at most every ten minutes in a process;
  * a pull prices eight college games, not five, and the month's plan funds them in full from December;
  * the NFL keeps its full cadence first.

Offline. Run directly: `python3 tests/test_a_college_game_is_priced_at_its_bill.py`
"""
import datetime as dt
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import oddsbudget as OB, oddsplan as P                   # noqa: E402

NOW = 1795600000.0


def _calls(n, billed, sport="cbb", ago=3600, kind="live_event"):
    return [{"ts": NOW - ago, "kind": kind, "sport": sport, "credits": billed, "est": 13, "billed": True}
            for _ in range(n)]


def test_the_price_is_the_last_weeks_average_bill_rounded_up():
    rows = _calls(15, 8) + _calls(9, 11) + _calls(3, 12) + _calls(1, 10) + _calls(2, 3)      # the 24 November calls
    assert sum(r["credits"] for r in rows) == 271 and len(rows) == 30
    assert OB.measured_price("cbb", rows, now=NOW) == 10
    assert OB.measured_price("cbb", _calls(19, 8), now=NOW) is None, "fewer than twenty calls: no measured price"
    assert OB.measured_price("cbb", _calls(30, 8, ago=8 * 86400), now=NOW) is None, "older than the week"
    assert OB.measured_price("cbb", _calls(30, 8, kind="live_board"), now=NOW) is None, "game calls only"
    assert OB.measured_price("cbb", [None, "x"], now=NOW) is None


def test_college_basketball_alone_is_priced_at_its_bill_and_never_above_its_table():
    keep = dict(OB._MEASURED)
    try:
        OB._MEASURED.clear()
        OB._MEASURED["cbb"] = (time.time(), 10)
        assert OB.credits_per_event("cbb") == 10
        OB._MEASURED["cbb"] = (time.time(), 15)
        assert OB.credits_per_event("cbb") == OB.EVENT_CREDITS["cbb"] == 13, "never above the table"
        OB._MEASURED["cbb"] = (time.time(), None)
        assert OB.credits_per_event("cbb") == 13, "no measured price: the table"
        assert OB.credits_per_event("nba") == OB.EVENT_CREDITS["nba"], "every other league at its table"
        assert OB.MEASURED_LEAGUES == frozenset({"cbb"})
    finally:
        OB._MEASURED.clear()
        OB._MEASURED.update(keep)


def test_the_ledger_is_read_at_most_every_ten_minutes():
    keep, was = dict(OB._MEASURED), OB.measured_price
    reads = []
    OB.measured_price = lambda sport, rows=None, now=None: reads.append(sport) or 9
    try:
        OB._MEASURED.clear()
        assert OB.credits_per_event("cbb") == 9 and OB.credits_per_event("cbb") == 9 and reads == ["cbb"]
        OB._MEASURED["cbb"] = (time.time() - OB.MEASURED_EVERY_S - 1, 9)
        OB.credits_per_event("cbb")
        assert reads == ["cbb", "cbb"], "read again once its ten minutes are up"
    finally:
        OB.measured_price = was
        OB._MEASURED.clear()
        OB._MEASURED.update(keep)


def test_eight_games_a_pull_are_funded_in_full_from_december_and_the_nfl_keeps_its_cadence():
    import nba_build
    assert nba_build.CBB_PROP_GAMES == P.PULL_CAP["cbb"] == 8
    assert set(P.GAMES_BY_WEEKDAY["cbb"]) == {8} and P.POSTSEASON_GAMES["cbb"] == 8
    keep = dict(OB._MEASURED)
    try:
        OB._MEASURED["cbb"] = (time.time(), 10)
        for day in (dt.date(2026, 12, 1), dt.date(2027, 1, 1), dt.date(2027, 2, 1), dt.date(2027, 3, 1)):
            plan = P.build(day, 100_000)
            cbb, nfl = plan.get("cbb"), plan.get("nfl")
            assert cbb.target == cbb.need > 0, (day, cbb.target, cbb.need)
            assert nfl.target == nfl.need, (day, "the NFL's full cadence first")
        dec = P.build(dt.date(2026, 12, 1), 100_000)
        assert dec.get("cbb").need == 31 * P.day_need("cbb", dt.date(2026, 12, 1))
        assert P.day_need("cbb", dt.date(2026, 12, 1)) == 3 * (8 + 1) * 10 + 12 * 3 + 5 * 3 * 3
    finally:
        OB._MEASURED.clear()
        OB._MEASURED.update(keep)


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
