"""Tests for the historical database + ingestion (in-memory SQLite, fixtures)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ingest


def _conn():
    return db.connect(":memory:")


# --- schema + CRUD ----------------------------------------------------------
def test_schema_and_upsert_roundtrip():
    conn = _conn()
    rows = [
        {"sport": "nfl", "season": 2023, "period": "005", "game_id": "GB-005",
         "player": "Josh Jacobs", "team": "GB", "opponent": "CHI", "position": "RB",
         "home": 1, "market": "rush_yds", "value": 96.0},
    ]
    assert db.upsert_player_logs(conn, rows) == 1
    got = list(conn.execute("SELECT * FROM player_game_logs"))
    assert len(got) == 1 and got[0]["value"] == 96.0


def test_upsert_is_idempotent():
    conn = _conn()
    row = {"sport": "nfl", "season": 2023, "period": "005", "game_id": "GB-005",
           "player": "P", "team": "GB", "opponent": "CHI", "position": "RB",
           "home": 1, "market": "rush_yds", "value": 50.0}
    db.upsert_player_logs(conn, [row])
    row["value"] = 88.0                       # same key, new value
    db.upsert_player_logs(conn, [row])
    rows = list(conn.execute("SELECT value FROM player_game_logs"))
    assert len(rows) == 1 and rows[0]["value"] == 88.0   # replaced, not duplicated


def test_entries_for_market_grouping_and_order():
    conn = _conn()
    logs = []
    for wk, val in [(3, 1), (1, 3), (2, 2)]:   # inserted out of order
        logs.append({"sport": "mlb", "season": 2024, "period": f"{wk:04d}",
                     "game_id": f"P-{wk}", "player": "Hitter", "team": "A",
                     "opponent": "B", "position": "1B", "home": 1,
                     "market": "total_bases", "value": val})
    db.upsert_player_logs(conn, logs)
    entries = db.entries_for_market(conn, "mlb", "total_bases", min_games=3)
    assert len(entries) == 1
    assert entries[0]["name"] == "Hitter"
    assert entries[0]["values"] == [3, 2, 1]          # chronological
    # Each value carries its game's period, so a backtest can line the game up
    # with the book price offered that day.
    assert entries[0]["dates"] == ["0001", "0002", "0003"]
    # min_games filter drops short histories
    assert db.entries_for_market(conn, "mlb", "total_bases", min_games=4) == []


def test_odds_history_stores_and_finds_the_closing_price():
    """Harvested book prices are what make a backtest market-relative."""
    conn = _conn()
    rows = [
        {"sport": "mlb", "taken_at": "2026-07-20T18:00:00Z", "event_id": "e1",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "home_runs", "book": "DraftKings", "line": 0.5,
         "over_odds": 340, "under_odds": -450},
        {"sport": "mlb", "taken_at": "2026-07-20T22:45:00Z", "event_id": "e1",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "home_runs", "book": "DraftKings", "line": 0.5,
         "over_odds": 300, "under_odds": -400},      # later = the close
    ]
    assert db.upsert_odds_history(conn, rows) == 2
    # Already-harvested snapshots are detectable, so they're never paid for twice.
    assert db.have_odds_snapshot(conn, "mlb", "e1", "2026-07-20T18:00:00Z") is True
    assert db.have_odds_snapshot(conn, "mlb", "e1", "2026-07-19T18:00:00Z") is False

    close = db.closing_odds_for(conn, "mlb", "home_runs")
    assert close[("aaron judge", "home_runs")]["over_odds"] == 300   # the latest


# --- NFL parsers ------------------------------------------------------------
def test_nfl_game_rows_filters_and_negates_spread():
    sched = [
        {"season": "2022", "week": "5", "home_team": "KC", "away_team": "NO",
         "spread_line": "3", "total_line": "43", "roof": "outdoors",
         "surface": "grass", "temp": "70", "wind": "5"},
        {"season": "2019", "week": "5", "home_team": "X", "away_team": "Y"},  # filtered
    ]
    rows = ingest.nfl_game_rows(sched, {2020, 2021, 2022})
    assert len(rows) == 1
    assert rows[0]["spread"] == -3.0 and rows[0]["game_id"] == "NO@KC"
    assert rows[0]["season"] == 2022 and rows[0]["period"] == "005"


def test_nfl_player_log_rows_maps_markets():
    stats = [{
        "player_display_name": "Josh Jacobs", "position": "RB",
        "recent_team": "GB", "opponent_team": "CHI", "week": "5", "season": "2023",
        "season_type": "REG", "rushing_yards": "96", "receiving_yards": "0",
        "passing_yards": "0", "receptions": "0",
    }]
    rows = ingest.nfl_player_log_rows(stats, 2023)
    rush = [r for r in rows if r["market"] == "rush_yds"]
    assert rush and rush[0]["value"] == 96.0 and rush[0]["player"] == "Josh Jacobs"


def test_nfl_td_rows_sum_rushing_and_receiving_only():
    """anytime_td = TDs SCORED: rushing + receiving, never passing — a QB's
    3 passing TDs don't cash his anytime-scorer prop."""
    stats = [{
        "player_display_name": "Jalen Hurts", "position": "QB",
        "recent_team": "PHI", "opponent_team": "DAL", "week": "5",
        "passing_tds": "3", "rushing_tds": "1", "receiving_tds": "0",
    }]
    rows = ingest.nfl_td_rows(stats, 2025)
    assert len(rows) == 1
    r = rows[0]
    assert (r["market"], r["value"], r["period"]) == ("anytime_td", 1.0, "005")


# --- ingest orchestration (stubbed sources) ---------------------------------
def test_ingest_nfl_offline(monkeypatch=None):
    conn = _conn()
    import engine.sources.nflverse as nv
    sched = [{"season": "2023", "week": "1", "home_team": "KC", "away_team": "DET",
              "spread_line": "-4", "total_line": "53", "roof": "outdoors",
              "surface": "grass", "temp": "72", "wind": "6"}]
    stats = [{"player_display_name": "Player One", "position": "WR",
              "recent_team": "DET", "opponent_team": "KC", "week": "1",
              "season": "2023", "season_type": "REG", "receiving_yards": "85",
              "rushing_yards": "0", "passing_yards": "0", "receptions": "6"}]
    saved = (nv.load_schedules, nv.load_weekly_stats)
    nv.load_schedules = lambda: sched
    nv.load_weekly_stats = lambda season: stats
    try:
        res = ingest.ingest_nfl(conn, [2023])
        assert res["games"] == 1 and res["player_logs"] >= 1
        s = db.summary(conn)
        assert s["games"]["nfl"] == 1 and s["seasons"]["nfl"] == [2023]
    finally:
        nv.load_schedules, nv.load_weekly_stats = saved


def test_db_feeds_backtest():
    # Populate a DB with synthetic MLB logs, then backtest straight off it.
    conn = _conn()
    logs = []
    for p in range(6):
        for g in range(1, 16):
            logs.append({"sport": "mlb", "season": 2024, "period": f"{g:04d}",
                         "game_id": f"P{p}-{g}", "player": f"P{p}", "team": "A",
                         "opponent": "B", "position": "1B", "home": 1,
                         "market": "total_bases", "value": (p + g) % 4})
    db.upsert_player_logs(conn, logs)
    entries = db.entries_for_market(conn, "mlb", "total_bases", min_games=9)
    assert len(entries) == 6
    from engine.mlb.backtest import backtest_from_logs
    report = backtest_from_logs(entries, "total_bases", min_history=8)
    assert report.n > 0


def test_closing_odds_by_date_keeps_each_days_close():
    """The backtest join needs a price for EVERY harvested game-day, not just a
    player's single most-recent snapshot — the per-player-latest view silently
    threw away a month of purchased history (coverage 330 -> 348 after a
    29-day harvest)."""
    conn = _conn()
    rows = [
        # Two snapshots on the 10th (later one is that day's close) + the 20th.
        {"sport": "mlb", "taken_at": "2026-06-10T18:00:00Z", "event_id": "e1",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "total_bases", "book": "DraftKings", "line": 1.5,
         "over_odds": -120, "under_odds": 100},
        {"sport": "mlb", "taken_at": "2026-06-10T22:50:00Z", "event_id": "e1",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "total_bases", "book": "DraftKings", "line": 1.5,
         "over_odds": -135, "under_odds": 115},
        {"sport": "mlb", "taken_at": "2026-06-20T22:45:00Z", "event_id": "e2",
         "home": "NYY", "away": "TBR", "player": "aaron judge",
         "market": "total_bases", "book": "FanDuel", "line": 2.5,
         "over_odds": 105, "under_odds": -125},
    ]
    db.upsert_odds_history(conn, rows)

    by_date = db.closing_odds_by_date(conn, "mlb", "total_bases")
    assert set(by_date) == {("aaron judge", "2026-06-10"),
                            ("aaron judge", "2026-06-20")}
    # Within a date, the later snapshot is the close.
    assert by_date[("aaron judge", "2026-06-10")]["over_odds"] == -135
    assert by_date[("aaron judge", "2026-06-20")]["line"] == 2.5
    # The latest-only view keeps just one entry — exactly why it can't be the
    # backtest join.
    assert len(db.closing_odds_for(conn, "mlb", "total_bases")) == 1


def test_upsert_games_merges_instead_of_clobbering():
    """Results rows carry scores, slate rows carry weather — whichever lands
    second must not NULL out the other's columns. A blind REPLACE here is how
    every final score in a 1,565-game table silently vanished."""
    conn = _conn()
    result_row = {"sport": "mlb", "season": 2026, "period": "2026-06-10",
                  "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
                  "home_score": 5, "away_score": 3, "spread": 0.0,
                  "total": None, "roof": "open", "surface": "grass",
                  "temp": None, "wind": None, "extra": "yankee"}
    slate_row = {"sport": "mlb", "season": 2026, "period": "2026-06-10",
                 "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
                 "home_score": None, "away_score": None, "spread": 0.0,
                 "total": 8.5, "roof": "open", "surface": "grass",
                 "temp": 78.0, "wind": 9.0, "extra": "yankee"}
    db.upsert_games(conn, [result_row])
    db.upsert_games(conn, [slate_row])       # the layer that used to clobber
    g = conn.execute("SELECT * FROM games").fetchone()
    assert g["home_score"] == 5 and g["away_score"] == 3   # scores survived
    assert g["temp"] == 78.0 and g["total"] == 8.5         # context merged in

    # Same key arriving the other way round also merges.
    conn2 = _conn()
    db.upsert_games(conn2, [slate_row])
    db.upsert_games(conn2, [result_row])
    g2 = conn2.execute("SELECT * FROM games").fetchone()
    assert g2["home_score"] == 5 and g2["temp"] == 78.0

    s = db.summary(conn)
    assert s["games"]["mlb"] == 1 and s["scored_games"]["mlb"] == 1


def test_date_ranges_exposes_logs_vs_odds_coverage_gap():
    """Purchased odds are useless without settled games to join to; the spans
    make that gap visible (June 1-12 odds bought while logs started June 13
    yielded almost nothing — invisible until the ranges sat side by side)."""
    conn = _conn()
    db.upsert_player_logs(conn, [
        {"sport": "mlb", "season": 2026, "period": "2026-06-13",
         "game_id": "g1", "player": "P", "team": "A", "opponent": "B",
         "position": "1B", "home": 1, "market": "total_bases", "value": 2},
        {"sport": "mlb", "season": 2026, "period": "2026-07-20",
         "game_id": "g2", "player": "P", "team": "A", "opponent": "B",
         "position": "1B", "home": 1, "market": "total_bases", "value": 1},
    ])
    db.upsert_odds_history(conn, [
        {"sport": "mlb", "taken_at": "2026-06-01T23:00:00Z", "event_id": "e1",
         "home": "A", "away": "B", "player": "p", "market": "total_bases",
         "book": "DK", "line": 1.5, "over_odds": -110, "under_odds": -110},
    ])
    r = db.date_ranges(conn)
    assert r["mlb_logs"] == ("2026-06-13", "2026-07-20")
    lo, hi, n = r["mlb_odds"]
    assert (lo, hi, n) == ("2026-06-01", "2026-06-01", 1)
    # The gap: odds begin before logs do.
    assert lo < r["mlb_logs"][0]


# ── the schema is run once per file per process, not per connection ──

def test_a_fresh_file_always_gets_its_schema():
    """The one way this optimisation could be catastrophic: memoise too
    eagerly and a caller opening a NEW database gets a connection with no
    tables in it. Every path is its own answer."""
    import tempfile
    for _ in range(3):
        path = os.path.join(tempfile.mkdtemp(), "fresh.db")
        conn = db.connect(path)
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert names, "a new database came back with no tables"


def test_the_second_connection_to_the_same_file_skips_the_schema():
    """THE POINT. `executescript(SCHEMA)` and the ALTER probes under it
    are all WRITES — a failing `ADD COLUMN` still takes SQLite's exclusive
    lock, discovers the column exists, and releases it. Seven or eight of
    those on every connection, on a box running concurrent builds against
    one file on one core, is the difference this removes."""
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "twice.db")
    conn = db.connect(path)                 # the first one does the work
    assert db.needs_schema(conn, path) is False
    assert db.needs_schema(db.connect(path), path) is False


def test_the_tables_are_still_there_on_the_skipped_connection():
    """Behavioural, because the assertion above is about a flag and this
    is about whether the database works. A connection that skipped the
    schema must be indistinguishable from one that ran it."""
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "shared.db")
    first = db.connect(path)
    first.execute("INSERT OR IGNORE INTO games (sport, season, period, home, "
                  "away) VALUES ('mlb', 2026, '2026-09-15', 'LAD', 'SD')")
    first.commit()
    second = db.connect(path)
    got = second.execute("SELECT home FROM games").fetchone()
    assert got and got[0] == "LAD", got


def test_memory_databases_always_run_it():
    """`:memory:` is a brand new empty database on every connect, so it
    can never be skipped. Getting this wrong would empty the suite."""
    import sqlite3
    assert db.needs_schema(sqlite3.connect(":memory:"), ":memory:") is True
    assert db.needs_schema(sqlite3.connect(":memory:"), ":memory:") is True
    conn = db.connect(":memory:")
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()


def test_a_schema_changed_underneath_us_is_migrated_again():
    """THE CORRECTNESS ARGUMENT for the whole memo, and the case that
    caught the first version of it before it shipped.

    A path-only memo turns a real migration into a silent no-op the
    moment anything else alters the file — the connection comes back
    "already done" over a database missing the column the migration was
    for. Keying on `PRAGMA schema_version`, which SQLite bumps on every
    schema change, means the memo NOTICES and simply migrates again.

    `tests/test_refit_capture` does this for real on the journal; this
    states it as the invariant rather than leaving it as a side effect
    of another file's fixture."""
    import sqlite3
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "drifted.db")
    conn = db.connect(path)
    assert db.needs_schema(conn, path) is False
    conn.close()

    # Something else alters the file — a rollback, a hand-edit, another
    # version of the code.
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE games ADD COLUMN scratch TEXT")
    raw.commit()
    raw.close()

    again = sqlite3.connect(path)
    assert db.needs_schema(again, path) is True, \
        "the memo did not notice the schema move underneath it"


def test_the_version_is_recorded_after_the_work_not_before():
    """Running the schema IS a schema change. A version stamped up front
    is the one we were about to move off, so every later connection
    would find a mismatch and redo everything — the memo would exist and
    save nothing."""
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "stamped.db")
    first = db.connect(path)
    assert db.needs_schema(first, path) is False, \
        "the first connection did not record the version it left behind"


def test_the_journal_and_the_history_keep_separate_books():
    """They own different schemas, over what may be different files. One
    shared set would let a journal connection skip its own schema on the
    strength of a history connection having run a different one."""
    from engine import ledger
    assert ledger._SCHEMA_DONE is not db._SCHEMA_DONE
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "both.db")
    conn = db.connect(path)                 # history has now migrated it
    assert db.needs_schema(conn, path, db._SCHEMA_DONE) is False
    # The journal has not seen this path, whatever the history did.
    assert db.needs_schema(conn, path, ledger._SCHEMA_DONE) is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
