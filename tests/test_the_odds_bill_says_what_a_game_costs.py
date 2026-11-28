"""What one game really costs, by league, on the heartbeat (step AEM, 24 November 2026).

Ethan's decision A, 24 November 2026: "yes more" college games with priced props. The answer turns on what one more
game costs, and our price table (engine/oddsbudget.EVENT_CREDITS: 13 credits a college basketball game, 14 a college
football one) is a model; the API states each call's real cost (`x-requests-last`, booked on the ledger since 30
October). The heartbeat now carries, for the last day's game-by-game calls of each league, how many there were, what
the API billed, what we priced them at, and how many calls billed each amount, so a game the books post no player
prop on can be seen to bill the same as one they do, or not.

Offline. Run directly: `python3 tests/test_the_odds_bill_says_what_a_game_costs.py`
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import oddsbudget as OB                                  # noqa: E402

NOW = 1795600000.0


def _row(kind, sport, credits, est, ago=3600, billed=True):
    return {"ts": NOW - ago, "kind": kind, "sport": sport, "credits": credits, "est": est, "billed": billed}


def test_each_league_s_game_calls_are_counted_with_what_the_api_billed():
    rows = [_row("live_event", "cbb", 13, 13), _row("live_event", "cbb", 3, 13), _row("live_event", "cbb", 13, 13),
            _row("live_event", "cfb", 14, 14),
            _row("live_board", "cbb", 3, 3),                          # the slate's lines: not a game call
            _row("live_event", "nba", 20, 20, billed=False),          # priced by our table alone: not the API's
            {"ts": NOW, "kind": "live_event", "sport": "nfl", "credits": 26},   # before the API's bill was booked
            _row("live_event", "nhl", 12, 12, ago=90000)]             # older than the day
    got = OB.event_bills(rows, since=NOW - 86400)
    assert got == {"cbb": {"calls": 3, "billed": 29, "est": 39, "each": {"13": 2, "3": 1}},
                   "cfb": {"calls": 1, "billed": 14, "est": 14, "each": {"14": 1}}}, got
    assert OB.event_bills([], since=NOW) == {} and OB.event_bills([None, "x", {"kind": "live_event"}]) == {}


def test_the_heartbeat_reads_the_ledger_at_most_every_ten_minutes_and_never_fails():
    import launch
    calls = []
    keep = OB.event_bills
    OB.event_bills = lambda since=None, rows=None: calls.append(since) or {"cbb": {"calls": 1}}
    try:
        launch._ODDS_BILL.clear()
        assert launch._odds_bill_public() == {"cbb": {"calls": 1}}
        assert launch._odds_bill_public() == {"cbb": {"calls": 1}} and len(calls) == 1, "kept for ten minutes"
        assert abs(calls[0] - (time.time() - 86400)) < 5, "the last day's calls"
        launch._ODDS_BILL["at"] = time.time() - launch.ODDS_BILL_EVERY_S - 1
        launch._odds_bill_public()
        assert len(calls) == 2, "read again once its ten minutes are up"

        def broken(since=None, rows=None):
            raise RuntimeError("ledger gone")
        OB.event_bills = broken
        launch._ODDS_BILL.clear()
        assert launch._odds_bill_public() == {}
    finally:
        OB.event_bills = keep
        launch._ODDS_BILL.clear()
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"odds_bill": _odds_bill_public(),' in src, "on the heartbeat"


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
