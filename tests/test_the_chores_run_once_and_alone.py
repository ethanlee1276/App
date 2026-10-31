"""The daily chores run once, alone, and never re-buy a harvest.

Audit 2026-09-30, F-5 / F-8 (roadmap #27). `run_if_due` had no lock and
marked the day only at the end: the startup thread and the refresher ran it
side by side at every restart, and a failed MLB ingest re-ran the whole
chore list every cycle all day — re-invoking the PAID harvest on a fresh
budget each time and rewriting the same backup zip in place. The weekly zip
also ran on the refresher thread while every board waited.
"""

import datetime as dt
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import maintenance  # noqa: E402


def _stub(mp, calls, ingest_ok=True):
    from engine import ingest, ledger, db

    def fake_ingest(conn, start, end, with_logs=True, progress=None):
        calls.append("ingest")
        return {"games": 12 if ingest_ok else 0, "player_logs": 0,
                "skipped": [] if ingest_ok else ["feed down"]}
    mp.setattr(ingest, "ingest_mlb_results", fake_ingest)
    mp.setattr(ledger, "settle_from_history", lambda *a, **k: 0)
    mp.setattr(ledger, "connect", lambda path=None: None)
    mp.setattr(db, "connect", lambda path=None: None)
    mp.setattr(maintenance, "_wnba_day", None)
    mp.setattr(maintenance, "_maybe_harvest", lambda day, log, **k: calls.append("harvest"))


def test_a_second_runner_returns_at_once(mp):
    calls, logs = [], []
    _stub(mp, calls)
    state = Path(tempfile.mkdtemp()) / "m.json"
    held = maintenance._chore_lock(state)
    assert held is not None
    try:
        assert maintenance.run_if_due(harvest=True, log=logs.append, state_path=state,
                                      today=dt.date(2026, 7, 25)) is False
        assert calls == [] and any("already running" in l for l in logs)
    finally:
        maintenance._release(held)
    assert maintenance.run_if_due(harvest=True, log=logs.append, state_path=state,
                                  today=dt.date(2026, 7, 25)) is True


def test_a_failed_ingest_reruns_the_chores_but_never_the_harvest(mp):
    calls = []
    _stub(mp, calls, ingest_ok=False)
    state = Path(tempfile.mkdtemp()) / "m.json"
    for _ in range(3):
        assert maintenance.run_if_due(harvest=True, log=lambda *_: None,
                                      state_path=state, today=dt.date(2026, 7, 25)) is True
    assert calls.count("ingest") == 3, "the retry still retries the free part"
    assert calls.count("harvest") == 1, "the paid harvest was bought again"


def test_a_day_that_already_has_closes_is_not_bought_again(mp):
    asked = []
    mp.setattr(maintenance, "_harvest_targets", lambda day: [("mlb", ["h2h"]), ("nfl", ["h2h"])])
    mp.setattr(maintenance, "_backfill_days", lambda day, h: [])
    mp.setattr(maintenance, "_day_has_closes", lambda h, sport, day: sport == "mlb")
    mp.setattr(maintenance, "_run_harvest", lambda sport, d, m, budget, log: asked.append(sport))

    class St:
        remaining = 20000
    import engine.oddsbudget as ob
    mp.setattr(ob, "load", lambda **k: St())
    mp.setattr(ob, "is_measured", lambda st: True)
    old = os.environ.get("ODDS_API_KEY")
    os.environ["ODDS_API_KEY"] = "test-not-a-key"
    try:
        maintenance._maybe_harvest(dt.date(2026, 7, 24), lambda *_: None, hconn=object())
    finally:
        if old is None:
            os.environ.pop("ODDS_API_KEY", None)
        else:
            os.environ["ODDS_API_KEY"] = old
    assert asked == ["nfl"]


def test_the_zip_is_checked_then_renamed_and_the_weekly_run_is_detached(mp):
    root = Path(tempfile.mkdtemp())
    (root / "data").mkdir()
    (root / "data" / "note.txt").write_text("x" * 1000)
    mp.setattr(maintenance, "BACKUP_FILES", ["data/note.txt"])
    mp.setattr(maintenance, "BACKUP_GLOBS", [])
    out = Path(tempfile.mkdtemp())
    maintenance._maybe_backup({}, dt.date(2026, 7, 25), lambda *_: None, root=root, backup_dir=out)
    z = out / "backup_2026-07-25.zip"
    assert z.exists() and not list(out.glob("*.tmp"))
    with zipfile.ZipFile(z) as zf:
        assert zf.testzip() is None and zf.namelist() == ["data/note.txt"]
    import inspect
    src = inspect.getsource(maintenance._run_chores)
    assert '_spawn_module("engine.backupzip"' in src and "_maybe_backup(state" not in src
    from engine import backupzip
    assert callable(backupzip.main)


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        m = MP()
        try:
            fn(m); print(f"  ok  {name}")
        finally:
            m.undo()
    print(f"\n{len(fns)} tests passed.")
