"""Tests for the daily self-maintenance loop (stubbed chores, temp state)."""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import maintenance


def _stub_chores(monkeypatch, calls):
    from engine import ingest, ledger, db

    def fake_ingest(conn, start, end, with_logs=True, progress=None):
        calls.append(("ingest", start, end))
        return {"games": 12, "player_logs": 300, "skipped": []}

    def fake_settle(conn, hist_conn, sport=None):
        calls.append(("settle",))
        return 2

    monkeypatch.setattr(ingest, "ingest_mlb_results", fake_ingest)
    monkeypatch.setattr(ledger, "settle_from_history", fake_settle)
    monkeypatch.setattr(ledger, "connect", lambda path=None: None)
    monkeypatch.setattr(db, "connect", lambda path=None: None)


def test_runs_once_per_day_and_catches_up(monkeypatch):
    calls, logs = [], []
    _stub_chores(monkeypatch, calls)
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "m.json"
        today = dt.date(2026, 7, 25)

        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state, today=today) is True
        # Fresh state: catches up a full week, through yesterday.
        assert calls[0] == ("ingest", "2026-07-18", "2026-07-24")
        assert ("settle",) in calls

        # Same day again: no-op.
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state, today=today) is False
        assert len([c for c in calls if c[0] == "ingest"]) == 1

        # Next day: runs again, re-ingesting from the last maintained day
        # (its games may have finished after that run) — not the whole week.
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state,
                                      today=today + dt.timedelta(days=1)) is True
        assert calls[-2] == ("ingest", "2026-07-24", "2026-07-25")


def test_failed_ingest_retries_next_cycle(monkeypatch):
    calls, logs = [], []
    from engine import ingest, ledger, db

    def boom(conn, start, end, with_logs=True, progress=None):
        calls.append("boom")
        raise RuntimeError("feed down")

    monkeypatch.setattr(ingest, "ingest_mlb_results", boom)
    monkeypatch.setattr(ledger, "settle_from_history", lambda c, h, sport=None: 0)
    monkeypatch.setattr(ledger, "connect", lambda path=None: None)
    monkeypatch.setattr(db, "connect", lambda path=None: None)

    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "m.json"
        today = dt.date(2026, 7, 25)
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state, today=today) is True
        # The day was NOT marked done, so the next cycle tries again.
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state, today=today) is True
        assert calls == ["boom", "boom"]
        assert any("failed" in l for l in logs)


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        mp = MP()
        try:
            fn(mp); print(f"  ok  {name}")
        finally:
            mp.undo()
    print(f"\n{len(fns)} tests passed.")
