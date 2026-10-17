"""The nightly harvest walks back for days that bet and never got a close,
inside one day's budget, down to the floor Ethan set.

Ethan, 2026-09-07: "set the harvest floor to 1000 and day budget 400 and
lets keep going." And, setting the plan those numbers serve: "build the
price history ... grade every card on closing line value first."

A night the harvest was declined left that day's bets settling with no
close, for good. Now the walk reaches back thirty days, newest first,
and every run is told only what is left of the day rather than a fresh
400 each — the old shape would have been N × 400 the first night there
were N days owed.

Run directly: `python3 tests/test_harvest_backfill.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger, maintenance as M, oddsbudget as ob   # noqa: E402

DAY = dt.date(2026, 9, 13)


def _ledger(bets):
    d = tempfile.mkdtemp(); path = os.path.join(d, "l.db")
    conn = ledger.connect(path)
    for sport, market, day in bets:
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds,"
            " stake_units, stake_dollars, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"{day}T09:00:00", sport, day.isoformat(), "X", market, "OVER", 1.5,
             "DK", -110, 1.0, 0.0, "open", "props"))
    conn.commit(); conn.close()
    return path


def _history(closes):
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        {"sport": s, "taken_at": f"{d.isoformat()}T23:00:00Z", "event_id": "e",
         "home": "A", "away": "B", "player": "X", "market": "rec_yds", "book": "best",
         "line": 50.5, "over_odds": -110, "under_odds": -110} for s, d in closes])
    return conn


def _budget(remaining):
    p = os.path.join(tempfile.mkdtemp(), "b.json")
    ob.save(ob.BudgetState(remaining=remaining, used=0, last_seen_iso="2026-09-14T03:00:00Z"), p)
    return p


class _Fake:
    """A harvest that spends `cost` credits per run, seen through the
    budget file the way the real CLI's API responses are."""

    def __init__(self, path, cost):
        self.path, self.cost, self.calls = path, cost, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        st = ob.load(self.path); st.remaining -= self.cost; ob.save(st, self.path)

        class _P:
            stdout, stderr = "Harvested 12 rows\n", ""
        return _P()


def test_the_floor_is_the_one_ethan_set():
    assert M.HARVEST_MIN_REMAINING == 1000 and M.HARVEST_DAY_BUDGET == 400
    assert M.HARVEST_BACKFILL_DAYS == 30


def test_days_that_bet_and_hold_no_close_are_owed_newest_first(monkeypatch):
    two, nine = DAY - dt.timedelta(days=2), DAY - dt.timedelta(days=9)
    monkeypatch.setattr(ledger, "DEFAULT_DB", _ledger([
        ("nfl", "rec_yds", two), ("mlb", "hits", nine), ("nfl", "spread", nine),
        ("nfl", "rec_yds", DAY - dt.timedelta(days=40)),     # past the walk
    ]))
    hist = _history([("nfl", two)])                          # two is closed
    got = M._backfill_days(DAY, hist)
    assert got == [(nine, "mlb", "hits"), (nine, "nfl", "spreads")], got
    assert M._day_has_closes(hist, "nfl", two) and not M._day_has_closes(hist, "nfl", nine)


def test_the_walk_spends_one_days_budget_across_every_day_it_reaches(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "k")
    days = [DAY - dt.timedelta(days=n) for n in (0, 3, 5, 8)]
    monkeypatch.setattr(ledger, "DEFAULT_DB", _ledger([("nfl", "rec_yds", d) for d in days]))
    bp = _budget(5000)
    fake = _Fake(bp, cost=150)
    monkeypatch.setattr(M.subprocess, "run", fake)
    log = []
    M._maybe_harvest(DAY, log.append, budget_path=bp, hconn=_history([]))
    # 400 a day: 150 + 150 spends 300, the third is told it may spend 100,
    # then the walk stops. Never a fresh 400 per run.
    asked = [int(c[c.index("--budget") + 1]) for c in fake.calls]
    assert asked == [400, 250, 100], asked
    assert [c[c.index("--from") + 1] for c in fake.calls] == [d.isoformat() for d in days[:3]]
    assert any("waits for tomorrow" in l for l in log), log


def test_the_walk_never_reaches_below_the_floor(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "k")
    days = [DAY - dt.timedelta(days=n) for n in (0, 1, 2)]
    monkeypatch.setattr(ledger, "DEFAULT_DB", _ledger([("nfl", "rec_yds", d) for d in days]))
    bp = _budget(1150)                       # 150 above the floor
    fake = _Fake(bp, cost=100)
    monkeypatch.setattr(M.subprocess, "run", fake)
    M._maybe_harvest(DAY, lambda *_: None, budget_path=bp, hconn=_history([]))
    asked = [int(c[c.index("--budget") + 1]) for c in fake.calls]
    assert asked == [150, 50], asked            # 1150 → 1050 → 50 left above 1000
    # The third day is never asked: the balance is under the floor now.
    assert len(fake.calls) == 2 and ob.load(bp).remaining == 950


def test_under_the_floor_nothing_runs_and_the_log_says_so(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(ledger, "DEFAULT_DB", _ledger([("nfl", "rec_yds", DAY)]))
    bp = _budget(999)
    fake = _Fake(bp, cost=10)
    monkeypatch.setattr(M.subprocess, "run", fake)
    log = []
    M._maybe_harvest(DAY, log.append, budget_path=bp, hconn=_history([]))
    assert fake.calls == [] and any("reserve 1000" in l for l in log), log


def test_yesterday_comes_before_the_backfill_and_closed_days_are_skipped(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "k")
    old = DAY - dt.timedelta(days=4)
    monkeypatch.setattr(ledger, "DEFAULT_DB", _ledger([
        ("nfl", "rec_yds", old), ("nfl", "rec_yds", DAY), ("nfl", "rec_yds", DAY - dt.timedelta(days=2))]))
    bp = _budget(9000)
    fake = _Fake(bp, cost=10)
    monkeypatch.setattr(M.subprocess, "run", fake)
    M._maybe_harvest(DAY, lambda *_: None, budget_path=bp,
                     hconn=_history([("nfl", DAY - dt.timedelta(days=2))]))
    assert [c[c.index("--from") + 1] for c in fake.calls] == [DAY.isoformat(), old.isoformat()]


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def setenv(self, k, v):
            self._undo.append((os.environ, k, os.environ.get(k))); os.environ[k] = v
        def undo(self):
            for obj, name, val in reversed(self._undo):
                if obj is os.environ:
                    (os.environ.pop(name, None) if val is None else os.environ.__setitem__(name, val))
                else:
                    setattr(obj, name, val)
    import inspect
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        mp = _MP()
        try:
            fn(mp) if "monkeypatch" in inspect.signature(fn).parameters else fn()
        finally:
            mp.undo()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
