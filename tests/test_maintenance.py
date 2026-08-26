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
    # The WNBA day-ingest hits the network; these tests are about the
    # scheduling, not the feed.
    monkeypatch.setattr(maintenance, "_wnba_day", None)


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

        # Next day: runs again. With no database to consult (db.connect is
        # stubbed to None here) the start falls back to the full week —
        # idempotent, so re-covering costs nothing. The DB-derived resume
        # point has its own test below.
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=state,
                                      today=today + dt.timedelta(days=1)) is True
        assert calls[-2] == ("ingest", "2026-07-19", "2026-07-25")


def test_catch_up_resumes_from_the_databases_own_last_final(monkeypatch):
    """THE EIGHT-DAY-GAP REGRESSION. Ethan's laptop was closed 8/11–8/18
    and the fixed one-week window dropped the first missing day, which
    ended in a hand-typed --from/--to backfill. The window is now derived
    from the DB's last stored final, so any gap heals itself — and a
    machine that was off for a season is capped, not ground to dust."""
    calls, logs = [], []
    from engine import db, ingest, ledger

    def fake_ingest(conn, start, end, with_logs=True, progress=None):
        calls.append(("ingest", start, end))
        return {"games": 3, "player_logs": 50, "skipped": []}

    with tempfile.TemporaryDirectory() as td:
        hconn = db.connect(Path(td) / "h.db")
        db.upsert_games(hconn, [{
            "sport": "mlb", "season": 2026, "period": "2026-07-16",
            "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
            "home_score": 5, "away_score": 2, "spread": 0.0, "total": None,
            "roof": "open", "surface": "grass", "temp": None, "wind": None,
            "extra": None,
        }])
        monkeypatch.setattr(ingest, "ingest_mlb_results", fake_ingest)
        monkeypatch.setattr(ledger, "settle_from_history",
                            lambda c, h, sport=None: 0)
        monkeypatch.setattr(ledger, "connect", lambda path=None: None)
        monkeypatch.setattr(db, "connect", lambda path=None: hconn)
        monkeypatch.setattr(maintenance, "_wnba_day", None)
        today = dt.date(2026, 7, 25)          # nine days past the last final
        assert maintenance.run_if_due(harvest=False, log=logs.append,
                                      state_path=Path(td) / "m.json",
                                      today=today) is True
    # 2026-07-16 itself is re-read (late games), then the gap through
    # yesterday — one day MORE than the old week window could reach.
    assert calls[0] == ("ingest", "2026-07-16", "2026-07-24")


def test_a_season_long_gap_is_capped_not_ground_through(monkeypatch):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, period TEXT, "
                 "home_score INT)")
    conn.execute("INSERT INTO games VALUES ('mlb', '2026-04-01', 4)")
    yesterday = dt.date(2026, 7, 24)
    start = maintenance._catch_up_start(conn, "mlb", yesterday)
    assert (yesterday - start).days == maintenance.MAX_CATCH_UP_DAYS - 1
    # And a sport the DB has never seen falls back to the one-week floor.
    start = maintenance._catch_up_start(conn, "nba", yesterday)
    assert (yesterday - start).days == maintenance.CATCH_UP_DAYS - 1


def test_the_settle_clock_is_five_minutes(monkeypatch):
    """Ethan, 2026-08-18: "it should be automatic like every 5 mins scan
    if props have been won or lost". The pass is a throttled no-op when
    nothing recent is open, so the clock is the promise."""
    assert maintenance.SETTLE_EVERY_S == 300


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
    monkeypatch.setattr(maintenance, "_wnba_day", None)

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


def test_weekly_backup_covers_other_peoples_data(_mp=None):
    """accounts.db and the pre-account profiles are in the weekly zip.

    They were not, for the whole first day accounts existed: BACKUP_FILES
    was written before the file did, and nothing re-read it. Everything
    else on that list costs us a re-ingest if it burns. This one costs
    other people their accounts, their synced bet logs and the customer_id
    that says who is paying us — none of which we can reconstruct from any
    source we hold. It is the only entry on the list that is not ours.
    """
    import sqlite3
    import zipfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data" / "profiles").mkdir(parents=True)
    acc = sqlite3.connect(str(tmp / "data" / "accounts.db"))
    acc.execute("CREATE TABLE users (id, email)")
    acc.execute("INSERT INTO users VALUES (1, 'ethan@example.com')")
    acc.commit(); acc.close()
    (tmp / "data" / "profiles" / "ethans-mac.json").write_text('{"mybets": []}')

    backups = tmp / "data" / "backups"
    maintenance._maybe_backup({}, dt.date(2026, 8, 15), lambda _m: None,
                              root=tmp, backup_dir=backups)
    names = zipfile.ZipFile(next(backups.glob("backup_*.zip"))).namelist()
    assert "data/accounts.db" in names
    assert "data/profiles/ethans-mac.json" in names

    # And it went through the sqlite backup API like the others, so a
    # backup taken mid-write is a readable database rather than a torn file.
    raw = zipfile.ZipFile(next(backups.glob("backup_*.zip"))).read("data/accounts.db")
    probe = tmp / "probe.db"; probe.write_bytes(raw)
    assert sqlite3.connect(str(probe)).execute(
        "SELECT email FROM users").fetchone()[0] == "ethan@example.com"


def test_weekly_backup_survives_a_missing_profiles_directory(_mp=None):
    """Nobody has synced a profile yet: glob a directory that isn't there."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data").mkdir(parents=True)
    backups = tmp / "data" / "backups"
    maintenance._maybe_backup({}, dt.date(2026, 8, 15), lambda _m: None,
                              root=tmp, backup_dir=backups)
    assert len(list(backups.glob("backup_*.zip"))) == 1


def test_check_says_when_the_newest_backup_has_no_accounts(_mp=None):
    """--check reads the archive, not the list of files we meant to zip.

    The bug this guards was invisible from inside the code: BACKUP_FILES
    looked complete, the log said "3 file(s)", and the zip was missing the
    one that mattered. So the check opens the newest archive and looks.
    Four states, because a health check that only handles the happy path
    is the kind that goes quiet exactly when it is needed.
    """
    import io
    import contextlib
    import sqlite3
    import zipfile
    import launch
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data" / "backups").mkdir(parents=True)

    def run(backups):
        buf = io.StringIO()
        was, launch.ROOT = launch.ROOT, tmp
        try:
            with contextlib.redirect_stdout(buf):
                launch._check_backup_covers_accounts(backups, "OK", "WARN")
        finally:
            launch.ROOT = was
        return buf.getvalue()

    # No accounts database at all: silent. Nobody has signed up, there is
    # nothing to lose, and a warning here would be noise on every run.
    old = tmp / "data" / "backups" / "backup_2026-08-01.zip"
    with zipfile.ZipFile(old, "w") as z:
        z.writestr("data/ledger.db", b"x")
    assert run([old]) == ""

    c = sqlite3.connect(str(tmp / "data" / "accounts.db"))
    c.execute("CREATE TABLE users (id, email)")
    c.execute("INSERT INTO users VALUES (1, 'a@b.c')")
    c.commit(); c.close()

    # Accounts, but the newest archive predates the fix — the state every
    # existing install was in the moment accounts shipped.
    out = run([old])
    assert "WARN" in out and "1 account(s)" in out and "backup_2026-08-01" in out

    # Accounts and no archive at all.
    assert "WARN" in run([])

    new = tmp / "data" / "backups" / "backup_2026-08-15.zip"
    with zipfile.ZipFile(new, "w") as z:
        z.writestr("data/accounts.db", b"x")
    assert "OK" in run([old, new])

    # A truncated or half-written zip reports itself rather than throwing
    # and taking the rest of --check down with it.
    junk = tmp / "data" / "backups" / "backup_2026-08-16.zip"
    junk.write_bytes(b"not a zip")
    assert "WARN" in run([junk])


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



def test_prune_can_never_reach_stats_journal_or_models(_mp=None):
    """The structural guarantee behind "we never delete stats": every
    permanent store lives OUTSIDE the cache directory, so the pruner —
    which only iterates that one directory — cannot see them at any age.
    A refactor that moved a DB under data/cache/ would fail here."""
    from pathlib import Path
    from engine import db, ledger, calibrate
    from engine.sources.fetch import CACHE_DIR
    from engine import maintenance

    cache = Path(CACHE_DIR).resolve()
    for label, p in (("history DB", db.DEFAULT_DB),
                     ("ledger DB", ledger.DEFAULT_DB),
                     ("calibration", calibrate.DEFAULT_PATH)):
        assert cache not in Path(p).resolve().parents, \
            f"{label} sits inside the prunable cache directory"

    # And even if a stats-shaped file WERE dropped in the cache, no
    # prunable prefix matches a database or model file.
    for name in ("history.db", "ledger.db", "calibration.json",
                 "line_history.jsonl", "depth_snapshots.json",
                 "odds_budget.json", "pbp_2025.csv"):
        assert not name.startswith(maintenance.PRUNABLE_CACHE_PREFIXES), \
            f"{name} would be deleted by the pruner"


def test_the_season_boundary_backfill_is_guarded_and_september_only(_mp=None):
    """Ethan circled the card's confession (2026-08-26): "Red-zone usage
    inferred … play-by-play not ingested". The chores now backfill the
    PRIOR season once per box in Aug-Sep — weekly stats, usage, TD rows,
    snaps and pbp in one guarded pull — so measured red-zone roles and
    carried TD histories exist on a droplet nobody ever SSH'd into to
    run the ingest by hand. Pinned structurally: the guard queries for
    existing rz rows (run once, not nightly), the month gate exists, and
    a failure logs a warning instead of taking the chores down."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "engine", "maintenance.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("The season-boundary backfill")
    block = src[i:i + 2400]
    assert "today.month in (8, 9)" in block
    assert "market='rz_tgt'" in block, "the run-once guard left"
    assert "ingest_nfl(_bconn, [prior])" in block
    assert "backfill failed" in block, "a failed backfill would crash the chores"
    assert "prior = today.year - 1" in block


def test_the_closes_harvest_follows_the_journal_not_a_hardcode(monkeypatch):
    """The season-readiness audit's finding (2026-08-25): the nightly
    harvest ran `harvest_odds.py mlb --markets total_bases,h2h` whatever
    had been bet, so every NFL bet of the coming season would have
    settled with no closing line — no CLV, no process grade, none of the
    learning the ladder feeds on. Targets now come from the journal:
    each sport that bet that day, exactly the markets it bet, with the
    game-bet vocabulary translated to the API's."""
    import engine.ledger as ledger
    d = tempfile.mkdtemp()
    path = os.path.join(d, "l.db")
    conn = ledger.connect(path)
    day = dt.date(2026, 9, 13)
    rows = [("nfl", "rec_yds"), ("nfl", "moneyline"), ("nfl", "spread"),
            ("mlb", "total_bases"),
            ("cfb", "moneyline"),          # journals, but never harvests
            ("nfl", "rush_yds")]
    for sport, market in rows:
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, stake_units, stake_dollars, status, category)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-09-13T09:00:00", sport, day.isoformat(), "X", market,
             "OVER", 1.5, "DK", -110, 1.0, 0.0, "open", "props"))
    conn.commit(); conn.close()
    monkeypatch.setattr(ledger, "DEFAULT_DB", path)
    got = dict(maintenance._harvest_targets(day))
    assert got["mlb"] == "total_bases"
    assert got["nfl"] == "h2h,rec_yds,rush_yds,spreads", got["nfl"]
    # CFB stays out ON PURPOSE — the odds-history parsers have no team
    # map for it (built at run time inside cfb_build; docs/IDEAS.md).
    assert "cfb" not in got
    assert "cfb" not in maintenance._HARVEST_SPORTS
    # A day nobody bet owes no credits.
    assert maintenance._harvest_targets(dt.date(2026, 9, 14)) == []


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
