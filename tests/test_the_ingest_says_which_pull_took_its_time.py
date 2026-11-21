"""The settle pass's ingest says which league's pull took the time
(engine/maintenance.ingest_for_open_bets' ``parts``; settle_open's
phases["ingest_parts"]).

With grading down to seconds, the 18:10 settle pass on Saturday 7 November
spent 45.6 seconds in its ingest, and the phase is every league's pull at
once: baseball's results, each basketball and hockey day, the NFL's weekly
file, the football finals off the scoreboard and the box scores of finished
football games. What these hold:

  * each pull that ran is timed under its own name, and one that did not
    run is not named;
  * what the ingest returned before is still there;
  * the settle pass puts the parts on its phases as ``ingest_parts``.

Run directly: `python3 tests/test_the_ingest_says_which_pull_took_its_time.py`
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle                                       # noqa: E402
from engine import maintenance as M                                # noqa: E402
from engine.sources import livescores                              # noqa: E402


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.val)

    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def test_each_pull_that_ran_is_timed_under_its_own_name():
    open_in = {"nba", "cfb"}
    asked = []
    swaps = [
        _Swap(M, "_has_open", lambda lconn, sport, days: sport in open_in),
        _Swap(M, "_nba_day", lambda h, d: asked.append(("nba", d))),
        _Swap(M, "_wnba_day", lambda h, d: asked.append(("wnba", d))),
        _Swap(M, "_nhl_day", lambda h, d: asked.append(("nhl", d))),
        _Swap(livescores, "ingest_finals", lambda h, lg: (asked.append(("finals", lg))
                                                          or {"games": 2, "skipped": []})),
        _Swap(boxsettle, "ingest_for_open", lambda l, h, lg, log=None: (
            asked.append(("box", lg)) or {"games": 1, "rows": 40, "purged": 0, "skipped": []})),
    ]
    for s in swaps:
        s.__enter__()
    try:
        res = M.ingest_for_open_bets(None, None, ["2026-11-06", "2026-11-07"], log=lambda *_: None)
    finally:
        for s in reversed(swaps):
            s.__exit__()
    assert ("nba", "2026-11-06") in asked and ("finals", "cfb") in asked and ("box", "cfb") in asked
    assert not any(a[0] in ("wnba", "nhl") for a in asked)
    parts = res["parts"]
    assert set(parts) <= {"nba", "finals_cfb", "box_cfb", "nfl_stats"}, parts
    assert all(isinstance(v, float) and v >= 0.0 for v in parts.values()), parts
    assert "mlb" not in parts and "nhl" not in parts and "box_nfl" not in parts
    assert res["games"] == 0, "what the ingest returned before is still there"


def test_a_slow_pull_shows_its_seconds():
    import time

    def slow(h, d):
        time.sleep(0.12)
    swaps = [
        _Swap(M, "_has_open", lambda lconn, sport, days: sport == "nhl"),
        _Swap(M, "_nhl_day", slow),
    ]
    for s in swaps:
        s.__enter__()
    try:
        res = M.ingest_for_open_bets(None, None, ["2026-11-07"], log=lambda *_: None)
    finally:
        for s in reversed(swaps):
            s.__exit__()
    assert res["parts"].get("nhl", 0) >= 0.1, res["parts"]


def test_the_settle_pass_puts_them_on_its_phases():
    from engine import db, ledger
    real = (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
            ledger.export_json)
    real_db, saved_ingest = db.connect, M.ingest_for_open_bets
    conn = ledger.connect(":memory:")
    conn.execute("INSERT INTO bets (sport, date, player, market, status, category) "
                 "VALUES ('nba', '2026-11-07', 'P', 'points', 'open', 'main')")
    conn.commit()
    ledger.connect = lambda path=None: conn
    db.connect = lambda path=None: None
    ledger.settle_from_history = lambda lconn, hconn, sport=None: 0
    ledger.resettle_mismatches = lambda lconn, hconn, since=None: []
    ledger.export_json = lambda c, p: None
    M.ingest_for_open_bets = lambda l, h, days, log: {"games": 0, "parts": {"nba": 3.4, "box_cfb": 21.0}}
    try:
        with tempfile.TemporaryDirectory() as td:
            M.settle_open(log=lambda *_: None, state_path=Path(td) / "m.json",
                          today=dt.date(2026, 11, 7), now=1000.0, force=True)
    finally:
        (ledger.connect, ledger.settle_from_history, ledger.resettle_mismatches,
         ledger.export_json) = real
        db.connect, M.ingest_for_open_bets = real_db, saved_ingest
    assert M.LAST_SETTLE_PHASES["ingest_parts"] == {"nba": 3.4, "box_cfb": 21.0}


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
