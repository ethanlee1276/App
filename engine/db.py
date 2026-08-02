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
-- Who started each game. The game-level models are dominated by starting
-- pitchers in MLB; without this the moneyline backtest replays every game
-- as bullpen-vs-bullpen (measured: Brier worse than the base rate).
CREATE TABLE IF NOT EXISTS game_starters (
    sport TEXT, season INTEGER, period TEXT, game_id TEXT, team TEXT,
    pitcher TEXT, throws TEXT,
    PRIMARY KEY (sport, season, period, game_id, team)
);
-- Home-plate umpire per game. Umpire zone size measurably moves strikeouts
-- and the run environment; profiles are computed from this table joined to
-- final scores and starter K logs.
CREATE TABLE IF NOT EXISTS game_umpires (
    sport TEXT, season INTEGER, period TEXT, game_id TEXT, umpire TEXT,
    PRIMARY KEY (sport, season, period, game_id)
);
-- Team-week aggregates from play-by-play: volume (plays), intent (PROE —
-- pass rate over expectation), efficiency (EPA per play, offense with
-- pass/rush splits and defense allowed), and neutral pace (seconds per
-- snap, game in the balance). The measured coaching/efficiency layer.
CREATE TABLE IF NOT EXISTS team_weeks (
    sport TEXT, season INTEGER, period TEXT, team TEXT,
    plays INTEGER, proe REAL,
    off_epa REAL, pass_epa REAL, rush_epa REAL, def_epa REAL, pace REAL,
    PRIMARY KEY (sport, season, period, team)
);
-- Every calibration sweep, kept. "Are we getting better?" was
-- unanswerable: each run printed to a terminal and vanished, so a model
-- change could be evaluated on the forward bet record (see MODEL_ERAS)
-- but never on whether the PROBABILITIES improved — which is the thing
-- the change was actually trying to fix, and the thing that moves years
-- before a P&L sample gets large enough to say anything.
--
-- One row per market per run. `code` is the git SHA, so a jump in ECE
-- can be tied to a commit instead of a memory.
CREATE TABLE IF NOT EXISTS calibration_runs (
    ts TEXT, code TEXT, sport TEXT, market TEXT,
    n INTEGER, brier REAL, ece REAL,
    base_rate REAL, skill REAL, hedged REAL,
    bins TEXT, note TEXT,
    PRIMARY KEY (ts, sport, market)
);
CREATE INDEX IF NOT EXISTS idx_calib_runs
    ON calibration_runs (sport, market, ts);
CREATE INDEX IF NOT EXISTS idx_odds_hist_lookup
    ON odds_history (sport, market, player, taken_at);
CREATE INDEX IF NOT EXISTS idx_logs_lookup
    ON player_game_logs (sport, market, player, season, period);
CREATE INDEX IF NOT EXISTS idx_games_lookup
    ON games (sport, season, period);
-- The context joins below key on (sport, period, ...), which is NOT a prefix
-- of either table's primary key — those lead with season. Without these,
-- SQLite falls back to matching on sport alone and re-scans the whole
-- context table once per log row. Measured on a six-season MLB history:
-- one platoon-split call went from >10 minutes to under two seconds. The
-- ordinary cost of holding more history is disk; this was the cost of
-- holding it in a shape the queries could not use.
CREATE INDEX IF NOT EXISTS idx_starters_team
    ON game_starters (sport, period, team);
CREATE INDEX IF NOT EXISTS idx_starters_game
    ON game_starters (sport, period, game_id);
CREATE INDEX IF NOT EXISTS idx_umpires_game
    ON game_umpires (sport, period, game_id);
CREATE INDEX IF NOT EXISTS idx_logs_period
    ON player_game_logs (sport, market, period, player);
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
    # Migrations for columns added after a table shipped (CREATE IF NOT
    # EXISTS won't touch an existing table).
    for col in ("off_epa", "pass_epa", "rush_epa", "def_epa", "pace"):
        try:
            conn.execute(f"ALTER TABLE team_weeks ADD COLUMN {col} REAL")
            conn.commit()
        except sqlite3.OperationalError:
            pass                     # already there
    try:
        conn.execute("ALTER TABLE game_starters ADD COLUMN throws TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass                              # column already there
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
    """Merge game rows: a NULL in the new row never erases a known value.

    Two ingest layers write the same (sport, season, period, game_id) keys —
    ranged results carry final scores but no weather, per-day slates carry
    park/weather context but NULL scores. A plain INSERT OR REPLACE meant
    whichever ran second wiped the other's columns; the slate loop runs after
    results, which silently blanked every final score in the table (and with
    them team ratings and the moneyline backtest).
    """
    if not rows:
        return 0
    keys = ("sport", "season", "period", "game_id")
    placeholders = ", ".join(f":{c}" for c in GAME_COLS)
    updates = ", ".join(f"{c}=COALESCE(excluded.{c}, games.{c})"
                        for c in GAME_COLS if c not in keys)
    sql = (f"INSERT INTO games ({', '.join(GAME_COLS)}) VALUES ({placeholders}) "
           f"ON CONFLICT({', '.join(keys)}) DO UPDATE SET {updates}")
    conn.executemany(sql, [{c: r.get(c) for c in GAME_COLS} for r in rows])
    conn.commit()
    return len(rows)


def drop_games(conn, rows: list[dict]) -> int:
    """Remove game rows that are never going to happen on this date.

    A postponed game keeps its schedule entry, so it lands in the table as
    a row with no score — indistinguishable from a game still in progress,
    which is exactly what the settle guard looks for. Every bet on either
    team that night then waits forever on a game that will not be played.

    Only ever called with games the schedule API positively reports as
    postponed/cancelled. Scorelessness alone must NOT reach here: a game in
    progress looks the same, and deleting its row would remove the guard
    that stops bets grading against a partial line. The game returns to the
    table on its make-up date, ingested normally, where it belongs.
    """
    if not rows:
        return 0
    dropped = 0
    for r in rows:
        cur = conn.execute(
            "DELETE FROM games WHERE sport=? AND period=? AND game_id=? "
            # Never delete something that has a result — if a score is
            # present the game was played, whatever the schedule says now.
            "AND home_score IS NULL",
            (r["sport"], r["period"], r["game_id"]))
        dropped += cur.rowcount
    conn.commit()
    return dropped


def upsert_player_logs(conn, rows: list[dict]) -> int:
    return _upsert(conn, "player_game_logs", LOG_COLS, rows)


def upsert_odds_history(conn, rows: list[dict]) -> int:
    return _upsert(conn, "odds_history", ODDS_HIST_COLS, rows)


STARTER_COLS = ["sport", "season", "period", "game_id", "team", "pitcher",
                "throws"]
UMPIRE_COLS = ["sport", "season", "period", "game_id", "umpire"]
TEAM_WEEK_COLS = ["sport", "season", "period", "team", "plays", "proe",
                  "off_epa", "pass_epa", "rush_epa", "def_epa", "pace"]


def upsert_team_weeks(conn, rows: list[dict]) -> int:
    return _upsert(conn, "team_weeks", TEAM_WEEK_COLS, rows)


def upsert_game_starters(conn, rows: list[dict]) -> int:
    return _upsert(conn, "game_starters", STARTER_COLS, rows)


def upsert_game_umpires(conn, rows: list[dict]) -> int:
    return _upsert(conn, "game_umpires", UMPIRE_COLS, rows)


def starters_by_game(conn, sport: str) -> dict:
    """``{(period, game_id): {team: pitcher}}`` for every stored starter."""
    out: dict = {}
    for r in conn.execute(
            "SELECT period, game_id, team, pitcher FROM game_starters "
            "WHERE sport=?", (sport,)):
        out.setdefault((r["period"], r["game_id"]), {})[r["team"]] = r["pitcher"]
    return out


def have_odds_snapshot(conn, sport: str, event_id: str, taken_at: str) -> bool:
    """Has this exact snapshot already been harvested?

    Historical calls are billed at a premium and a past price is immutable, so
    the harvester checks here before spending a credit re-fetching one.
    """
    row = conn.execute(
        "SELECT 1 FROM odds_history WHERE sport=? AND event_id=? AND taken_at=? LIMIT 1",
        (sport, event_id, taken_at)).fetchone()
    return row is not None


def closing_odds_by_date(conn, sport: str, market: str) -> dict:
    """Latest harvested price per (player, market) on EACH date.

    ``closing_odds_for`` below keeps only a player's single most-recent
    snapshot — right for "what's the close right now", but as a backtest join
    it discards every earlier harvested day: a player with 25 harvested
    game-days contributes exactly one matchable date, which is how a month of
    purchased history produced almost no extra coverage.

    Returns ``{(player, YYYY-MM-DD): {"line", "over_odds", "under_odds",
    "book", "taken_at"}}`` — within each date, the last snapshot wins, which is
    the closest thing to that day's closing number.
    """
    q = ("SELECT player, book, line, over_odds, under_odds, taken_at "
         "FROM odds_history WHERE sport=? AND market=? ORDER BY taken_at")
    out: dict = {}
    for r in conn.execute(q, (sport, market)):
        date = str(r["taken_at"])[:10]
        # Ordered by taken_at, so later same-date rows overwrite earlier ones.
        out[(r["player"], date)] = {
            "line": r["line"], "over_odds": r["over_odds"],
            "under_odds": r["under_odds"], "book": r["book"],
            "taken_at": r["taken_at"],
        }
    return out


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


def date_ranges(conn) -> dict:
    """First/last dates present in each store, so coverage gaps are visible.

    The results store (free) and odds store (metered) grow independently; a
    backtest is only market-relative where they OVERLAP. Seeing the two spans
    side by side is how you spot purchased odds with no settled games to join
    to — or vice versa."""
    out: dict = {}
    for sport in ("nfl", "mlb"):
        lo, hi = conn.execute(
            "SELECT MIN(period), MAX(period) FROM player_game_logs WHERE sport=?",
            (sport,)).fetchone()
        out[f"{sport}_logs"] = (lo, hi)
        lo, hi, n = conn.execute(
            "SELECT MIN(substr(taken_at,1,10)), MAX(substr(taken_at,1,10)), "
            "COUNT(*) FROM odds_history WHERE sport=?", (sport,)).fetchone()
        out[f"{sport}_odds"] = (lo, hi, n)
    return out


#: Reported first, in this order, whether or not they have rows — a board
#: with an EMPTY history is the single most useful thing this summary can
#: say, and omitting it makes "no data" and "no such sport" identical.
CORE_SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba")


def sports_present(conn) -> list[str]:
    """Every sport with rows, core boards first.

    This used to be the literal tuple ("nfl", "mlb"), which meant a two-hour
    NBA backfill finished by printing a summary that did not mention
    basketball — leaving no way to tell a completed ingest from a broken
    one except by opening SQLite.
    """
    found = set()
    for table in ("games", "player_game_logs"):
        try:
            found.update(r[0] for r in conn.execute(
                f"SELECT DISTINCT sport FROM {table}") if r[0])
        except Exception:                     # table may not exist yet
            continue
    rest = sorted(found - set(CORE_SPORTS))
    return list(CORE_SPORTS) + rest


#: A day with fewer distinct players than this had a partial ingest. A full
#: MLB slate stores several hundred; a handful means the log layer stopped
#: part-way through, which looks identical to a quiet day from the outside.
THIN_DAY_PLAYERS = 120


def coverage_gaps(conn, sport: str = "mlb", start: str | None = None,
                  end: str | None = None) -> list[dict]:
    """Days INSIDE the stored span that are incomplete. Read-only, no network.

    ``date_ranges`` reports first and last, which is the wrong shape for the
    failure that actually happens. A span of 2021 to 2026 is printed with no
    complaint while three days in the middle of it hold nothing — and those
    holes are not cosmetic: a bet whose result was never ingested cannot
    settle, and a day whose finals are missing is exactly the state that let
    the settler grade props against the wrong game.

    Four kinds of hole, named separately because they need different fixes:

      * ``no_finals``  — games are stored for that day and none has a score.
        The scores layer ran and came back empty.
      * ``some_finals`` — some of the day's games have scores and some do not.
        Usually a genuinely suspended game, occasionally a partial run.
      * ``no_logs``    — the day's games are final but no player logs exist.
        The scores layer worked and the log layer did not, which is the
        expensive one: props have nothing to settle against.
      * ``thin_logs``  — logs exist but from too few players to be a slate.

    Empty days are NOT reported. Off days, the All-Star break and the
    offseason all look like an empty day, and a report that cries wolf on
    every Monday in November stops being read. What is reported is a day the
    database itself says is half-finished.

    TWO RESTRICTIONS, both learned from the first run against a real DB,
    which returned 519 days and a five-year repair walk:

    **Only inside each season's own logged window.** Spring training is in
    the schedule and its games have finals, but the ingest deliberately
    never stores player logs for them — so every day from March 1st was
    reported as a hole, 14 games at a time. The window is taken from the
    data rather than from a calendar: the first and last day of that season
    that HAS logs. Anything outside it is scope, not absence.

    **Only what a re-ingest can actually fill.** ``parse_results`` returns
    completed, scored games and nothing else, so a scoreless row on a past
    date is a postponed, cancelled or suspended game that will never be
    scored. Running the ingest again cannot fix it, and listing it next to
    a repairable hole under one heading is how a report sends someone on a
    five-year walk for nothing. Those days are still returned, flagged
    ``repairable=False``, so the caller can report them under their own
    heading with their own remedy.
    """
    where = "sport=?"
    args: list = [sport]
    if start:
        where += " AND period>=?"
        args.append(start)
    if end:
        where += " AND period<=?"
        args.append(end)
    rows = conn.execute(
        f"SELECT period, season, COUNT(*) AS n, "
        f"COALESCE(SUM(home_score IS NOT NULL), 0) AS fin "
        f"FROM games WHERE {where} GROUP BY period, season ORDER BY period",
        args).fetchall()
    logs = {r[0]: (r[1], r[2]) for r in conn.execute(
        f"SELECT period, COUNT(*), COUNT(DISTINCT player) "
        f"FROM player_game_logs WHERE {where} GROUP BY period", args)}
    # The window each season's LOGS actually cover. Derived, not assumed:
    # a hardcoded "regular season starts in April" would be wrong the year
    # the league moves opening day, and would say nothing about a season
    # whose backfill genuinely stopped in July.
    window = {int(s): (lo, hi) for s, lo, hi in conn.execute(
        f"SELECT season, MIN(period), MAX(period) FROM player_game_logs "
        f"WHERE {where} GROUP BY season", args)}
    out: list[dict] = []
    for r in rows:
        day, n, fin = r["period"], int(r["n"] or 0), int(r["fin"] or 0)
        lo, hi = window.get(int(r["season"] or 0), (None, None))
        if lo and not (lo <= day <= hi):
            continue                    # outside this season's logged scope
        n_logs, n_players = logs.get(day, (0, 0))
        if not fin:
            kind, detail, ok = ("no_finals",
                                f"{n} game(s) stored, none with a score", False)
        elif fin < n:
            kind, detail, ok = ("some_finals",
                                f"{fin} of {n} game(s) have a score", False)
        elif not n_logs:
            kind, detail, ok = ("no_logs",
                                f"{n} final game(s), no player logs", True)
        elif n_players < THIN_DAY_PLAYERS:
            kind, detail, ok = ("thin_logs",
                                f"{n_players} player(s) logged across {n} "
                                f"game(s) — a full slate stores several "
                                f"hundred", True)
        else:
            continue
        out.append({"date": day, "kind": kind, "games": n, "finals": fin,
                    "log_rows": n_logs, "players": n_players,
                    "repairable": ok, "detail": detail})
    return out


def summary(conn) -> dict:
    out: dict = {"games": {}, "scored_games": {}, "player_logs": {}, "seasons": {}}
    for sport in sports_present(conn):
        out["games"][sport] = conn.execute(
            "SELECT COUNT(*) FROM games WHERE sport=?", (sport,)).fetchone()[0]
        # Games with a final score — what team ratings and the moneyline
        # backtest actually run on. A big gap vs the raw count means an ingest
        # layer erased results.
        out["scored_games"][sport] = conn.execute(
            "SELECT COUNT(*) FROM games WHERE sport=? AND home_score IS NOT NULL "
            "AND away_score IS NOT NULL", (sport,)).fetchone()[0]
        out["player_logs"][sport] = conn.execute(
            "SELECT COUNT(*) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()[0]
        out["seasons"][sport] = seasons_present(conn, sport)
    return out


def nfl_game_winds(conn, season: int) -> dict[str, float]:
    """``{game_id: wind_mph}`` for one NFL season, game_id being ``AWAY@HOME``.

    This is what fills the conditions column in a player's past-performance
    table (redesign spec §6.4). The weekly player feed carries no weather at
    all — it is the `games` table, populated by a separate ingest, that knows
    the wind — so the table showed a column of em dashes until this join
    existed.

    Keyed by game_id alone rather than (period, game_id): a matchup happens
    at most twice a season and the second meeting is at the other venue, so
    the id already differs. Weeks are therefore not needed to disambiguate,
    and not requiring them means a log whose week numbering is off by a
    playoff round still finds its game.
    """
    out: dict[str, float] = {}
    for row in conn.execute(
            "SELECT game_id, wind FROM games WHERE sport='nfl' AND season=? "
            "AND wind IS NOT NULL", (season,)):
        out[str(row["game_id"])] = float(row["wind"])
    return out
