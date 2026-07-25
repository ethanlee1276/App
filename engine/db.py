"""Historical database — local SQLite store for both sports.

A single dependency-free (stdlib ``sqlite3``) store that persists the raw
material for real model training and backtesting:

  * ``games``            — one row per game with context (scores, spread,
    total, roof/park, surface, weather);
  * ``player_game_logs`` — one row per (player, game, market) with the stat
    value, the atomic unit the projection/backtest walk forward over;
  * ``ingest_log``       — an audit trail of what was ingested and when.

The database grows every season: ingestion is idempotent (``INSERT OR
REPLACE`` on natural keys), so re-running a season overwrites rather than
duplicates. Query helpers turn the store back into the ``entries`` shape the
backtest and ML trainers consume, so training runs off persisted history
instead of re-hitting the network.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    sport TEXT, season INTEGER, period TEXT, game_id TEXT,
    home TEXT, away TEXT, home_score REAL, away_score REAL,
    spread REAL, total REAL, roof TEXT, surface TEXT, temp REAL, wind REAL,
    extra TEXT,
    PRIMARY KEY (sport, season, period, game_id)
);
CREATE TABLE IF NOT EXISTS player_game_logs (
    sport TEXT, season INTEGER, period TEXT, game_id TEXT,
    player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER,
    market TEXT, value REAL,
    PRIMARY KEY (sport, season, period, game_id, player, market)
);
CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT, kind TEXT, detail TEXT, rows INTEGER, ts TEXT
);
-- Point-in-time sportsbook prices. This is what lets a backtest measure the
-- model against the number a bettor could actually have taken, rather than a
-- naive baseline. Historical API calls cost extra credits and a past price
-- never changes, so rows are keyed to be written once and reused forever.
CREATE TABLE IF NOT EXISTS odds_history (
    sport TEXT, taken_at TEXT, event_id TEXT, home TEXT, away TEXT,
    player TEXT, market TEXT, book TEXT,
    line REAL, over_odds INTEGER, under_odds INTEGER,
    PRIMARY KEY (sport, taken_at, event_id, player, market, book)
);
CREATE INDEX IF NOT EXISTS idx_odds_hist_lookup
    ON odds_history (sport, market, player, taken_at);
CREATE INDEX IF NOT EXISTS idx_logs_lookup
    ON player_game_logs (sport, market, player, season, period);
CREATE INDEX IF NOT EXISTS idx_games_lookup
    ON games (sport, season, period);
"""

GAME_COLS = ["sport", "season", "period", "game_id", "home", "away",
             "home_score", "away_score", "spread", "total", "roof", "surface",
             "temp", "wind", "extra"]
LOG_COLS = ["sport", "season", "period", "game_id", "player", "team",
            "opponent", "position", "home", "market", "value"]
ODDS_HIST_COLS = ["sport", "taken_at", "event_id", "home", "away", "player",
                  "market", "book", "line", "over_odds", "under_odds"]


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _upsert(conn, table: str, cols: list[str], rows: list[dict]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, [{c: r.get(c) for c in cols} for r in rows])
    conn.commit()
    return len(rows)


def upsert_games(conn, rows: list[dict]) -> int:
    return _upsert(conn, "games", GAME_COLS, rows)


def upsert_player_logs(conn, rows: list[dict]) -> int:
    return _upsert(conn, "player_game_logs", LOG_COLS, rows)


def upsert_odds_history(conn, rows: list[dict]) -> int:
    return _upsert(conn, "odds_history", ODDS_HIST_COLS, rows)


def have_odds_snapshot(conn, sport: str, event_id: str, taken_at: str) -> bool:
    """Has this exact snapshot already been harvested?

    Historical calls are billed at a premium and a past price is immutable, so
    the harvester checks here before spending a credit re-fetching one.
    """
    row = conn.execute(
        "SELECT 1 FROM odds_history WHERE sport=? AND event_id=? AND taken_at=? LIMIT 1",
        (sport, event_id, taken_at)).fetchone()
    return row is not None


def closing_odds_for(conn, sport: str, market: str,
                     player: str | None = None) -> dict:
    """Latest harvested price per (player, market) — the closing line.

    Returns ``{(player, market): {"line", "over_odds", "under_odds", "book",
    "taken_at"}}``, taking the most recent snapshot for each.
    """
    q = ("SELECT player, market, book, line, over_odds, under_odds, taken_at "
         "FROM odds_history WHERE sport=? AND market=?")
    args: list = [sport, market]
    if player:
        q += " AND player=?"
        args.append(player)
    q += " ORDER BY taken_at"

    out: dict = {}
    for r in conn.execute(q, args):
        # Later rows overwrite earlier ones, so the last seen is the close.
        out[(r["player"], r["market"])] = {
            "line": r["line"], "over_odds": r["over_odds"],
            "under_odds": r["under_odds"], "book": r["book"],
            "taken_at": r["taken_at"],
        }
    return out


def log_ingest(conn, sport: str, kind: str, detail: str, rows: int) -> None:
    import datetime
    conn.execute(
        "INSERT INTO ingest_log (sport, kind, detail, rows, ts) VALUES (?,?,?,?,?)",
        (sport, kind, detail, rows, datetime.datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit()


# --- queries ----------------------------------------------------------------
def seasons_present(conn, sport: str) -> list[int]:
    cur = conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport=? "
        "UNION SELECT DISTINCT season FROM games WHERE sport=? ORDER BY season",
        (sport, sport))
    return [r[0] for r in cur.fetchall()]


def entries_for_market(conn, sport: str, market: str,
                       min_games: int = 8, seasons: list[int] | None = None) -> list[dict]:
    """Chronological per-player values for a market, as the backtest's
    ``entries`` shape: ``[{"name", "values": [...]}, ...]``."""
    q = ("SELECT player, value, period FROM player_game_logs "
         "WHERE sport=? AND market=?")
    args: list = [sport, market]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    q += " ORDER BY player, season, period, game_id"

    grouped: dict[str, list[float]] = {}
    dates: dict[str, list[str]] = {}
    for row in conn.execute(q, args):
        grouped.setdefault(row["player"], []).append(float(row["value"]))
        # ``period`` is the game's real date (see engine.ingest), which is what
        # lets a backtest line each game up with the price offered that day.
        dates.setdefault(row["player"], []).append(str(row["period"]))
    return [{"name": name, "values": vals, "dates": dates.get(name, [])}
            for name, vals in grouped.items() if len(vals) >= min_games]


def summary(conn) -> dict:
    out: dict = {"games": {}, "player_logs": {}, "seasons": {}}
    for sport in ("nfl", "mlb"):
        out["games"][sport] = conn.execute(
            "SELECT COUNT(*) FROM games WHERE sport=?", (sport,)).fetchone()[0]
        out["player_logs"][sport] = conn.execute(
            "SELECT COUNT(*) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()[0]
        out["seasons"][sport] = seasons_present(conn, sport)
    return out
