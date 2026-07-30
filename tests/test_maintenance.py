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



def test_weekly_backup_zips_and_prunes(monkeypatch):
    """Weekly backup: sqlite-safe copies, irreplaceable files included,
    old archives pruned, and a same-week rerun is a no-op."""
    import sqlite3
    import zipfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data" / "cache").mkdir(parents=True)
    db = sqlite3.connect(str(tmp / "data" / "history.db"))
    db.execute("CREATE TABLE t (x)"); db.execute("INSERT INTO t VALUES (42)")
    db.commit(); db.close()
    (tmp / "data" / "cache" / "line_history.jsonl").write_text('{"ts": 1}\n')

    backups = tmp / "data" / "backups"
    state: dict = {}
    logs: list = []
    today = dt.date(2026, 7, 26)
    maintenance._maybe_backup(state, today, logs.append, root=tmp,
                              backup_dir=backups)
    zips = list(backups.glob("backup_*.zip"))
    assert len(zips) == 1 and state["last_backup"] == "2026-07-26"
    names = zipfile.ZipFile(zips[0]).namelist()
    assert "data/history.db" in names
    assert "data/cache/line_history.jsonl" in names
    # The zipped DB is a valid sqlite copy, not a torn file.
    import io
    raw = zipfile.ZipFile(zips[0]).read("data/history.db")
    probe = tmp / "probe.db"; probe.write_bytes(raw)
    assert sqlite3.connect(str(probe)).execute("SELECT x FROM t").fetchone()[0] == 42

    # Three days later: still inside the week, nothing new.
    maintenance._maybe_backup(state, dt.date(2026, 7, 29), logs.append,
                              root=tmp, backup_dir=backups)
    assert len(list(backups.glob("backup_*.zip"))) == 1

    # Simulate months of weekly backups: only the newest 6 survive.
    for wk in range(8):
        state.pop("last_backup", None)
        maintenance._maybe_backup(state, dt.date(2026, 8, 1) + dt.timedelta(days=7 * wk),
                                  logs.append, root=tmp, backup_dir=backups)
    assert len(list(backups.glob("backup_*.zip"))) == maintenance.BACKUP_KEEP


# --- Intraday auto-settle ---------------------------------------------------
def _ledger_with(open_days, settled=3):
    """An in-memory journal holding one open pick per given slate date."""
    from engine import ledger
    conn = ledger.connect(":memory:")
    for d in open_days:
        conn.execute(
            "INSERT INTO bets (sport, date, player, market, status, category) "
            "VALUES ('mlb', ?, ?, 'total_bases', 'open', 'main')", (d, "P" + d))
    conn.commit()
    return conn


def _stub_settle(monkeypatch, calls, lconn, settled=3):
    from engine import ingest, ledger, db
    monkeypatch.setattr(ledger, "connect", lambda path=None: lconn)
    monkeypatch.setattr(db, "connect", lambda path=None: None)

    def fake_ingest(conn, start, end, with_logs=True, progress=None):
        calls.append(("ingest", start, end))
        return {"games": 4, "player_logs": 90, "skipped": []}

    def fake_settle(conn, hist_conn, sport=None):
        calls.append(("settle",))
        return settled

    monkeypatch.setattr(ingest, "ingest_mlb_results", fake_ingest)
    monkeypatch.setattr(ledger, "settle_from_history", fake_settle)
    monkeypatch.setattr(ledger, "export_json", lambda c, p: calls.append(("export",)))


def test_autosettle_grades_tonights_open_picks(monkeypatch):
    """The whole point: a pick placed today gets graded today, without
    anyone running --settle."""
    calls, logs = [], []
    today = dt.date(2026, 7, 27)
    lconn = _ledger_with([today.isoformat()])
    _stub_settle(monkeypatch, calls, lconn)
    with tempfile.TemporaryDirectory() as td:
        n = maintenance.settle_open(log=logs.append, state_path=Path(td) / "m.json",
                                    today=today, now=1000.0)
    assert n == 3
    # It ingests TODAY, which the daily chores never do.
    assert ("ingest", "2026-07-27", "2026-07-27") in calls
    assert ("settle",) in calls and ("export",) in calls


def test_autosettle_throttles_between_passes(monkeypatch):
    calls, logs = [], []
    today = dt.date(2026, 7, 27)
    lconn = _ledger_with([today.isoformat()])
    _stub_settle(monkeypatch, calls, lconn)
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "m.json"
        maintenance.settle_open(log=logs.append, state_path=state,
                                today=today, now=1000.0)
        before = len(calls)
        # A minute later — inside the window, so nothing happens.
        assert maintenance.settle_open(log=logs.append, state_path=state,
                                       today=today, now=1060.0) == 0
        assert len(calls) == before
        # Past the window, it runs again.
        maintenance.settle_open(log=logs.append, state_path=state, today=today,
                                now=1000.0 + maintenance.SETTLE_EVERY_S + 1)
        assert len(calls) > before


def test_autosettle_startup_ignores_the_throttle(monkeypatch):
    """Launching the site is an explicit 'catch me up'."""
    calls, logs = [], []
    today = dt.date(2026, 7, 27)
    lconn = _ledger_with([today.isoformat()])
    _stub_settle(monkeypatch, calls, lconn)
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "m.json"
        maintenance.settle_open(log=logs.append, state_path=state,
                                today=today, now=1000.0)
        before = len(calls)
        maintenance.settle_open(log=logs.append, state_path=state, today=today,
                                now=1001.0, force=True)
        assert len(calls) > before


def test_autosettle_does_nothing_when_nothing_is_open(monkeypatch):
    calls, logs = [], []
    today = dt.date(2026, 7, 27)
    _stub_settle(monkeypatch, calls, _ledger_with([]))
    with tempfile.TemporaryDirectory() as td:
        assert maintenance.settle_open(log=logs.append,
                                       state_path=Path(td) / "m.json",
                                       today=today, now=1000.0) == 0
    assert not [c for c in calls if c[0] == "ingest"]


def test_autosettle_ignores_picks_older_than_the_lookback(monkeypatch):
    """Stale open picks are the daily job's problem — an intraday pass must
    not quietly re-ingest a month of history on every cycle."""
    calls, logs = [], []
    today = dt.date(2026, 7, 27)
    lconn = _ledger_with(["2026-06-01", today.isoformat()])
    _stub_settle(monkeypatch, calls, lconn)
    with tempfile.TemporaryDirectory() as td:
        maintenance.settle_open(log=logs.append, state_path=Path(td) / "m.json",
                                today=today, now=1000.0)
    start, end = [c for c in calls if c[0] == "ingest"][0][1:]
    floor = (today - dt.timedelta(days=maintenance.SETTLE_LOOKBACK_DAYS - 1)).isoformat()
    assert start >= floor, f"reached back to {start}, past the {floor} floor"
    assert end == today.isoformat()
    # And it spans only days that actually hold open picks — the June entry
    # is excluded outright rather than dragging the range back with it.
    assert start == today.isoformat()


def test_autosettle_never_raises(monkeypatch):
    """A chore that can crash the launcher is worse than one that skips."""
    calls, logs = [], []
    from engine import ledger

    def boom(path=None):
        raise RuntimeError("journal is locked")

    monkeypatch.setattr(ledger, "connect", boom)
    with tempfile.TemporaryDirectory() as td:
        assert maintenance.settle_open(log=logs.append,
                                       state_path=Path(td) / "m.json",
                                       today=dt.date(2026, 7, 27), now=1.0) == 0
    assert any("auto-settle failed" in m for m in logs)



def test_prune_cache_never_touches_irreplaceable_state(_mp=None):
    """The cache directory holds BOTH refetchable per-game files and state
    that cannot be recovered: line_history.jsonl (CLV's line-movement
    record), depth_snapshots.json (camp watch's daily depth charts),
    odds_budget.json (credit accounting), and pbp_*.csv (~100MB). The
    pruner works from an allowlist, so age alone can never delete them."""
    import os, tempfile, time
    from pathlib import Path
    from engine.maintenance import prune_cache

    root = Path(tempfile.mkdtemp())
    old = time.time() - 90 * 86400
    everything = [
        # prunable, old -> should go
        "mlb_box_777.json", "mlb_line_777.json", "mlb_schedule_2026-01-02.json",
        "mlb_log_hitting_1_2026.json", "nba_box_x.json", "espn_mma_ath_9.json",
        "meteo_coors.json", "mlb_results_2026-01-01_2026-01-07.json",
        # prunable but RECENT -> must stay
        "mlb_box_recent.json",
        # never prunable at any age -> must stay
        "line_history.jsonl", "depth_snapshots.json", "odds_budget.json",
        "pbp_2025.csv", "games.csv", "sleeper_players_nfl.json",
        "calibration.json",
    ]
    for name in everything:
        p = root / name
        p.write_text("{}")
        if name != "mlb_box_recent.json":
            os.utime(p, (old, old))          # age everything but the recent one

    n, freed = prune_cache(max_age_days=30, cache_dir=root)
    left = {f.name for f in root.iterdir()}
    assert n == 8, f"pruned {n}, expected 8"
    # Irreplaceable state and expensive downloads survive despite being old.
    for keep in ("line_history.jsonl", "depth_snapshots.json",
                 "odds_budget.json", "pbp_2025.csv", "games.csv",
                 "sleeper_players_nfl.json", "calibration.json"):
        assert keep in left, f"pruner destroyed {keep}"
    # A recent per-game file is kept too.
    assert "mlb_box_recent.json" in left
    assert "mlb_box_777.json" not in left
    # Missing directory is a no-op, not a crash.
    assert prune_cache(cache_dir=root / "nope") == (0, 0)


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
