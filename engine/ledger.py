"""Bet-tracking ledger + bankroll — the self-evaluation system.

Logs every recommendation the model makes, grades each against the real outcome
as results come in, and tracks running performance and bankroll over time. This
is the piece that answers, over a real season, "is the model actually any good?"

  * **Bankroll-aware sizing** — each unit is a configurable percent of the
    *current* bankroll, so dollar stakes scale with the roll (proper bankroll
    management); the model's fractional-Kelly ``stake_units`` sets how many units.
  * **Grading** — an Over hits when the actual clears the line; pushes are
    returned; P&L is computed from the American price.
  * **Reporting** — record (W-L-P), ROI, units and dollars won, closing-line
    value, and breakdowns by grade and market.

SQLite (stdlib), a separate ``data/ledger.db`` from the data warehouse. Logging
is idempotent per (sport, date, player, market).
"""

from __future__ import annotations

import datetime
import re
import sqlite3
from pathlib import Path

from .odds import american_to_decimal

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "ledger.db"

# ``category`` separates the headline record ('main' — picks we stand
# behind) from measurement-only buckets ('longshot' — the HR board, tracked
# to learn whether it finds value, never mixed into the record). It is part
# of the unique key so a player recommended AND watchlisted the same night
# journals in both buckets.
_BETS_TABLE = """
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT,
    side TEXT, line REAL, book TEXT, odds INTEGER,
    projection REAL, hit_prob REAL, edge REAL, confidence REAL, grade TEXT,
    stake_units REAL, stake_dollars REAL,
    status TEXT DEFAULT 'open', actual REAL,
    pnl_units REAL, pnl_dollars REAL, closing_line REAL,
    category TEXT DEFAULT 'main',
    UNIQUE (sport, date, player, market, category)
);
"""

SCHEMA = _BETS_TABLE + """
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {"starting_bankroll": "1000", "unit_pct": "1.0", "bankroll": "1000"}


def _migrate(conn) -> None:
    """Rebuild a pre-category bets table in place, preserving every row.

    SQLite can't alter a UNIQUE constraint, so the one-time upgrade renames,
    recreates with ``category`` in the key, copies, and drops."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)").fetchall()]
    if not cols or "category" in cols:
        return
    keep = ("id, ts, sport, date, player, market, side, line, book, odds, "
            "projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status, actual, pnl_units, pnl_dollars, closing_line")
    conn.executescript(
        "ALTER TABLE bets RENAME TO bets_v1;\n"
        + _BETS_TABLE +
        f"INSERT INTO bets ({keep}, category) "
        f"SELECT {keep}, 'main' FROM bets_v1;\n"
        "DROP TABLE bets_v1;")


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    conn.executescript(SCHEMA)
    for k, v in DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    return conn


# --- config / bankroll ------------------------------------------------------
def get_cfg(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row[0] if row else DEFAULTS.get(key, "")


def set_cfg(conn, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def configure_bankroll(conn, starting: float | None = None, unit_pct: float | None = None) -> None:
    if starting is not None:
        set_cfg(conn, "starting_bankroll", starting)
        set_cfg(conn, "bankroll", starting)     # reset current to starting
    if unit_pct is not None:
        set_cfg(conn, "unit_pct", unit_pct)


def bankroll(conn) -> float:
    return float(get_cfg(conn, "bankroll"))


# --- logging ----------------------------------------------------------------
# Markets that are long shots by nature — plus-money, low-probability
# swings. They are measured in their own bucket at a flat nominal stake
# and must NEVER enter the headline record: a board of +650 home-run
# darts loses most nights by design, and mixing that into the main W-L
# and ROI makes the record describe the dart board instead of the picks
# the model actually stands behind. ``log_longshots`` journals them.
LONGSHOT_MARKETS = {"home_runs", "anytime_td"}


def log_recommendations(conn, result: dict, only_recommended: bool = True) -> int:
    """Insert open bets from a pipeline result dict. Stake dollars are sized
    from the current bankroll: stake_units × unit_pct% × bankroll."""
    sport = result.get("sport", "nfl")
    date = result.get("date", "")
    unit_dollars = float(get_cfg(conn, "unit_pct")) / 100.0 * bankroll(conn)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for r in result.get("recommendations", []):
        if only_recommended and not r.get("recommended"):
            continue
        # A proxy-priced "edge" isn't a price anyone can bet; journaling it
        # would pollute the learning data with fictional P&L.
        if r.get("has_market") is False:
            continue
        # Long shots live in their own bucket, even when they clear the
        # main board's bar — see LONGSHOT_MARKETS.
        if r.get("market") in LONGSHOT_MARKETS:
            continue
        stake_units = float(r.get("stake_units", 0) or 0)
        # A zero-stake "pick" is not a bet — journaling it would pad the
        # record with rows that can never win or lose a unit, making the
        # W-L column describe something nobody wagered on.
        if stake_units <= 0:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open')",
            (now, sport, date, r["player"], r["market"], r.get("side", "OVER"),
             r["line"], r.get("book", ""), r.get("odds", -110), r.get("projection"),
             r.get("hit_prob"), r.get("edge"), r.get("confidence"), r.get("grade"),
             stake_units, round(stake_units * unit_dollars, 2)))
        n += cur.rowcount
    # Recommended game bets journal too (sharp-anchor picks live or die by
    # forward results). Moneylines store player = the team picked, line 0.5,
    # side OVER, actual 1/0 — so the standard grader applies. Totals store
    # player = the matchup key (AWAY@HOME) with the real line and side.
    for r in result.get("game_bets", []):
        if not r.get("recommended"):
            continue
        bt = r.get("bet_type")
        if bt == "moneyline":
            player, market = r.get("pick", ""), "moneyline"
            side, line = "OVER", 0.5
        elif bt == "total":
            player = (r.get("matchup") or "").replace(" ", "")
            market = "total"
            side, line = (r.get("side") or "OVER").upper(), float(r.get("line") or 0)
        elif bt == "spread":
            # player = the team laid. The line is stored NEGATED so the
            # standard side-aware grader applies unchanged: a spread bet
            # covers when the team's margin beats the number, i.e.
            # margin > -spread — so actual = margin, line = -spread,
            # side = OVER, and margin == -spread grades as the push it is.
            player, market = r.get("team", ""), "spread"
            side, line = "OVER", -float(r.get("line") or 0)
        elif bt == "team_total":
            player = r.get("team", "")
            market = "team_total"
            side, line = (r.get("side") or "OVER").upper(), float(r.get("line") or 0)
        else:
            continue
        if not player:
            continue
        stake_units = float(r.get("stake_units", 0) or 0)
        if stake_units <= 0:
            continue                     # not a bet — see above
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open')",
            (now, sport, date, player, market, side, line,
             r.get("book", "best"), r.get("odds", -110), None,
             r.get("win_prob"), r.get("edge"), r.get("confidence"),
             r.get("grade"), stake_units, round(stake_units * unit_dollars, 2)))
        n += cur.rowcount
    conn.commit()
    return n


# Long-shot markets we can actually settle from ingested game logs —
# journaling unsettleable bets would just accumulate rows stuck open
# forever. anytime_td settles from the weekly-stats TD rows
# (engine.ingest.nfl_td_rows) that maintenance ingests all season.
SETTLEABLE_LONGSHOTS = {"home_runs", "anytime_td"}


def log_longshots(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the Long Shots board — picks and watchlist in SEPARATE buckets.

    The picks (three per night at most — the bets the board actually
    recommends) go to ``category='longshot'``: that is the record the Record
    page scores. The watchlist — EVERY real-priced HR on the slate, often
    100+ names — goes to ``category='longshot_watch'``: a calibration sample
    only ("does the model's claimed probability beat the market's implied
    one?"), never a record. One bucket used to hold both, and that made the
    Long Shots W-L describe the dart board instead of the picks: journal a
    couple hundred homers a night and a handful always land.

    Both buckets track at a small flat stake with ZERO dollar exposure.
    """
    sport = result.get("sport", "mlb")
    date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = _journal_longshot_rows(conn, result.get("long_shots") or [],
                               sport, date, now, "longshot", flat_stake)
    n += _journal_longshot_rows(conn, result.get("longshot_watch") or [],
                                sport, date, now, "longshot_watch", flat_stake)
    conn.commit()
    return n


def _journal_longshot_rows(conn, rows, sport, date, now, category,
                           flat_stake) -> int:
    n = 0
    for r in rows:
        market = r.get("market", "home_runs")
        if market not in SETTLEABLE_LONGSHOTS:
            continue
        try:
            odds = int(r.get("odds") or 0)
        except (TypeError, ValueError):
            continue
        # Plus-money and real: the boards already filter, but the journal is
        # the last line of defense against a proxy or mis-lined price.
        if not r.get("player") or odds <= 100 or (r.get("book") or "").lower() == "proxy":
            continue
        # A projected-lineup hitter is a guess about who plays, not a bet.
        # The board still shows him (caveated); the journal waits for the
        # confirmed lineup — otherwise every rest day strands a third of
        # the night's rows as no-shows that can never settle.
        if r.get("lineup_confirmed") is False:
            continue
        if category == "longshot_watch":
            # A pick also sits on the watchlist. One measurement per bet —
            # the record bucket already has him tonight.
            dup = conn.execute(
                "SELECT 1 FROM bets WHERE sport=? AND date=? AND player=? "
                "AND market=? AND category='longshot'",
                (sport, date, r["player"], market)).fetchone()
            if dup:
                continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?)",
            (now, sport, date, r["player"], market, "OVER", 0.5,
             r.get("book", ""), odds, None, r.get("model_prob"),
             r.get("edge", r.get("ev_per_unit")), r.get("confidence"),
             r.get("grade", "Watch"), flat_stake, 0.0, category))
        n += cur.rowcount
    return n


# Stale-line flags journal only on markets whose results we actually ingest;
# anything else would sit open forever and eventually void wrongly. NFL
# yardage markets settle from the weekly stats maintenance ingests Aug–Feb;
# NBA stat markets from the CDN boxscores it ingests Oct–Jun.
STALE_SETTLEABLE = {"total_bases", "hits", "home_runs",
                    "pass_yds", "rush_yds", "rec_yds", "receptions",
                    "pts", "reb", "ast", "fg3m"}


def log_stale_flags(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the scanner's stale-line flags — the sampler for our best-
    measured signal.

    A book pricing a side ≥1pt cheaper than the field's consensus beat the
    eventual close 64.8% of the time (+1.49pt CLV, z=11.6) on 30k harvested
    quotes. That was measured on CLOSES; this bucket measures the thing
    that matters — does TAKING the flagged price make money at settlement?
    Flat stake, zero dollars, category='stale', never in the headline
    record. Pre-game flags only: an in-play price is stale for reasons the
    scanner can't see.

    The journal key has no side column, so if both sides of one prop are
    flagged the same day, only the larger gap (rows arrive gap-sorted)
    journals — fine for a measurement bucket.
    """
    sport = result.get("sport", "mlb")
    slate_date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    rows = ((result.get("market_scan") or {}).get("stale")) or []
    n = 0
    for r in rows:
        if r.get("live") or r.get("started"):
            continue
        market = r.get("market") or ""
        if market not in STALE_SETTLEABLE or not r.get("player"):
            continue
        try:
            odds = int(r.get("odds"))
            line = float(r.get("line"))
        except (TypeError, ValueError):
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'stale')",
            # Slate-level date first: it's the key settling maps to the
            # history DB (NFL journals '2025-W05', not the game's ISO day).
            (now, sport, slate_date or r.get("date"), r["player"], market,
             (r.get("side") or "OVER").upper(), line, r.get("book", ""), odds,
             None,
             # hit_prob = the field's consensus implied — what the flag
             # claims the true price is; edge = the gap being sampled.
             r.get("consensus"), (r.get("gap_pts") or 0) / 100.0,
             None, "Stale", flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def stale_report(conn) -> dict:
    """The stale-line sampler's scoreboard: flat-stake record, hit rate vs
    the break-even the taken prices implied, and the consensus the flags
    claimed. If hit rate can't beat the taken price's break-even, the
    measured CLV never cashes and the signal stays display-only."""
    p = performance(conn, category="stale")
    row = conn.execute(
        "SELECT AVG(CASE WHEN odds > 0 THEN 100.0 / (odds + 100.0) "
        "            ELSE -odds / (100.0 - odds) END) AS taken_p, "
        "AVG(hit_prob) AS consensus_p, AVG(edge) AS avg_gap, "
        "SUM(status='won') AS w, COUNT(*) AS n "
        "FROM bets WHERE category='stale' AND status IN ('won','lost')"
    ).fetchone()
    p["avg_taken_implied"] = round(row["taken_p"], 4) if row["taken_p"] is not None else None
    p["avg_consensus_implied"] = (round(row["consensus_p"], 4)
                                  if row["consensus_p"] is not None else None)
    p["avg_gap_pts"] = round(row["avg_gap"] * 100, 2) if row["avg_gap"] is not None else None
    p["actual_hit_rate"] = round(row["w"] / row["n"], 4) if row["n"] else None
    p["recent"] = recent_settled(conn, limit=15, category="stale")
    return p


def log_form_picks(conn, result: dict, team_form: dict,
                   flat_stake: float = 0.1) -> int:
    """The team-form sampler: for every slate game where a HOT team meets a
    COLD one (form gap ≥ the bar), journal the hot side's moneyline at the
    REAL book price, flat 0.1u, category='form'.

    This is the measurement the "we're missing hot teams" instinct needs:
    streaks are the most public stat in sports, so the default assumption is
    the market already prices them. The sampler finds out — at the prices we
    could actually bet — and the fixed promotion bar (100+ graded, z ≥ 2,
    positive ROI) decides whether form ever becomes a recommendation input.
    Settles automatically through the existing moneyline path (player = the
    team picked, line 0.5, side OVER, actual 1/0).
    """
    from .mlb.teamform import FORM_GAP_BAR, form_score
    sport = result.get("sport", "mlb")
    slate_date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    scores = {t: form_score(f) for t, f in (team_form or {}).items()}
    n = 0
    for g in result.get("games", []):
        home, away = g.get("home"), g.get("away")
        sh, sa = scores.get(home), scores.get(away)
        if sh is None or sa is None or abs(sh - sa) < FORM_GAP_BAR:
            continue
        hot, hot_score = (home, sh) if sh > sa else (away, sa)
        odds = g.get("home_ml") if hot == home else g.get("away_ml")
        if not odds:
            continue                      # no real price — nothing to sample
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'form')",
            (now, sport, slate_date or g.get("date"), hot, "moneyline",
             "OVER", 0.5, "best", int(odds), None,
             # edge column carries the form gap being sampled.
             None, round(abs(sh - sa), 3), None, "Form", flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def form_report(conn) -> dict:
    """The form sampler's scoreboard: does backing hot teams at real prices
    make money? Mirrors stale_report; graded nightly with everything else."""
    p = performance(conn, category="form")
    row = conn.execute(
        "SELECT AVG(CASE WHEN odds > 0 THEN 100.0 / (odds + 100.0) "
        "            ELSE -odds / (100.0 - odds) END) AS taken_p, "
        "AVG(edge) AS avg_gap, SUM(status='won') AS w, COUNT(*) AS n "
        "FROM bets WHERE category='form' AND status IN ('won','lost')"
    ).fetchone()
    p["avg_taken_implied"] = round(row["taken_p"], 4) if row["taken_p"] is not None else None
    p["avg_form_gap"] = round(row["avg_gap"], 3) if row["avg_gap"] is not None else None
    p["actual_hit_rate"] = round(row["w"] / row["n"], 4) if row["n"] else None
    p["recent"] = recent_settled(conn, limit=15, category="form")
    return p


def log_ufc_picks(conn, result: dict) -> int:
    """Journal the UFC card's picks — category='ufc', its own probation
    bucket (docs pattern: a newly opened gate earns its way into any
    headline through its own graded record, never by assertion).

    player = the fighter picked, market = moneyline, line 0.5, side OVER,
    actual 1/0 — the standard grader applies. Real prices only."""
    if result.get("status") != "card" or not result.get("picks"):
        return 0
    date = result.get("event_date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for p in result["picks"]:
        odds = p.get("odds")
        if not odds or not p.get("pick") or not date:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'ufc')",
            (now, "ufc", date, p["pick"], "moneyline", "OVER", 0.5,
             p.get("book", ""), int(odds), None, p.get("p_final"),
             p.get("edge"), None, "Pick",
             float(p.get("stake_units") or 0), 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def settle_ufc(conn, fetch_result=None) -> int:
    """Settle open UFC picks from post-card results.

    ``fetch_result(name, since_date)`` defaults to the ESPN MMA lookup;
    injectable for tests. won → 1/0 through the standard side-aware
    grader; a draw/NC voids, exactly as a book would."""
    import datetime as _dt
    if fetch_result is None:
        from .sources.espnmma import latest_result as fetch_result
    settled = 0
    for b in conn.execute("SELECT * FROM bets WHERE status='open' "
                          "AND sport='ufc'").fetchall():
        try:
            since = _dt.date.fromisoformat(b["date"])
        except (TypeError, ValueError):
            continue
        try:
            res = fetch_result(b["player"], since)
        except Exception:
            continue
        if not res:
            continue                       # card not fought/ingested yet
        if res.get("won") is None:
            conn.execute("UPDATE bets SET status='void', pnl_units=0, "
                         "pnl_dollars=0 WHERE id=?", (b["id"],))
        else:
            _settle_one(conn, b, 1.0 if res["won"] else 0.0, None)
        settled += 1
    conn.commit()
    return settled


def ufc_report(conn) -> dict:
    """The UFC bucket's scoreboard — same shape the other probation
    buckets export, graded fight by fight."""
    p = performance(conn, category="ufc")
    p["recent"] = recent_settled(conn, limit=15, category="ufc")
    return p


# --- settling ---------------------------------------------------------------
def _settle_one(conn, b, actual: float, closing_line: float | None) -> None:
    """Grade one open bet SIDE-AWARE and advance the bankroll.

    ``actual > line`` is only a win for an OVER — grading unders with the
    over's rule inverts half the journal, the same bug that once inverted the
    backtest's P&L."""
    side = (b["side"] or "OVER").upper()
    if actual > b["line"]:
        over = 1
    elif actual < b["line"]:
        over = 0
    else:
        over = None
    if over is None:
        status, pnl_u = "push", 0.0
    else:
        won = (over == 1) if side == "OVER" else (over == 0)
        if won:
            status, pnl_u = "won", (american_to_decimal(b["odds"]) - 1.0) * b["stake_units"]
        else:
            status, pnl_u = "lost", -b["stake_units"]
    pnl_d = round(pnl_u / b["stake_units"] * b["stake_dollars"], 2) if b["stake_units"] else 0.0
    conn.execute(
        "UPDATE bets SET status=?, actual=?, pnl_units=?, pnl_dollars=?, closing_line=? WHERE id=?",
        (status, actual, round(pnl_u, 4), pnl_d, closing_line, b["id"]))
    set_cfg(conn, "bankroll", round(bankroll(conn) + pnl_d, 2))


def _snapshot_closes() -> dict:
    """``{(normalized player, market, date): closing line}`` from the free
    line-move snapshots. The fallback CLV source: harvested odds_history
    closes cost credits and only exist for backtested dates, while these
    snapshots accrue on every paid live pull anyway."""
    try:
        from .linemoves import load_history, closing_lines_by_date
        return closing_lines_by_date(load_history())
    except Exception:            # never let CLV bookkeeping block settling
        return {}


# NFL slates journal under the week label the site shows ('2025-W05');
# results land in the history DB as period '005' within a season.
_NFL_WEEK_DATE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def _hist_where(b) -> tuple[str, list]:
    """SQL fragment + args locating this bet's results in the history DB.

    MLB journals ISO dates that ARE the log period, so sport+period is
    enough. An NFL bet's '2025-W05' maps to period '005' — and a bare
    week number repeats every season, so the season must join too or a
    2026 bet could settle against a 2025 stat line."""
    m = _NFL_WEEK_DATE.match(b["date"] or "")
    if b["sport"] == "nfl" and m:
        return ("sport=? AND season=? AND period=?",
                [b["sport"], int(m.group(1)), f"{int(m.group(2)):03d}"])
    return "sport=? AND period=?", [b["sport"], b["date"]]


def settle_from_history(conn, hist_conn, sport: str | None = None) -> int:
    """Auto-settle open bets straight from the history database.

    Actuals come from ``player_game_logs`` (each bet's slate date + market),
    closing lines from harvested ``odds_history`` — no hand-built actuals
    file. Run it any time after results ingest; bets whose games haven't been
    ingested yet simply stay open.
    """
    from .sources.oddsapi import normalize_name
    from . import db as hist_db

    q = "SELECT * FROM bets WHERE status='open'"
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)

    closes_cache: dict = {}
    settled = 0
    for b in conn.execute(q, args).fetchall():
        where, wargs = _hist_where(b)
        if b["market"] == "moneyline":
            # player = the team picked; the game's final score settles it.
            g = hist_conn.execute(
                f"SELECT home, away, home_score, away_score FROM games "
                f"WHERE {where} AND (home=? OR away=?) "
                f"AND home_score IS NOT NULL AND away_score IS NOT NULL",
                (*wargs, b["player"], b["player"])).fetchone()
            if g is None:
                continue
            pick_home = g["home"] == b["player"]
            won = (g["home_score"] > g["away_score"]) == pick_home
            # Stored as line 0.5 / side OVER: actual 1.0 = pick won.
            _settle_one(conn, b, 1.0 if won else 0.0, None)
            settled += 1
            continue
        if b["market"] == "total":
            # player = the matchup key (AWAY@HOME); actual = combined runs.
            g = hist_conn.execute(
                f"SELECT home_score, away_score FROM games "
                f"WHERE {where} AND game_id=? "
                f"AND home_score IS NOT NULL AND away_score IS NOT NULL",
                (*wargs, b["player"])).fetchone()
            if g is None:
                continue
            _settle_one(conn, b, float(g["home_score"]) + float(g["away_score"]), None)
            settled += 1
            continue
        if b["market"] in ("spread", "team_total"):
            # player = the team; its own margin (spread) or score (team
            # total) is the actual the grader compares to the stored line.
            g = hist_conn.execute(
                f"SELECT home, away, home_score, away_score FROM games "
                f"WHERE {where} AND (home=? OR away=?) "
                f"AND home_score IS NOT NULL AND away_score IS NOT NULL",
                (*wargs, b["player"], b["player"])).fetchone()
            if g is None:
                continue
            home_side = g["home"] == b["player"]
            if b["market"] == "spread":
                actual = (g["home_score"] - g["away_score"]) if home_side \
                    else (g["away_score"] - g["home_score"])
            else:
                actual = g["home_score"] if home_side else g["away_score"]
            _settle_one(conn, b, float(actual), None)
            settled += 1
            continue
        rows = hist_conn.execute(
            f"SELECT value FROM player_game_logs WHERE {where} "
            f"AND market=? AND player=?",
            (*wargs, b["market"], b["player"])).fetchall()
        if not rows:
            # Name-shape fallback (feeds disagree on accents/suffixes).
            target = normalize_name(b["player"])
            rows = [c for c in hist_conn.execute(
                        f"SELECT player, value FROM player_game_logs "
                        f"WHERE {where} AND market=?",
                        (*wargs, b["market"]))
                    if normalize_name(c["player"]) == target]
        if not rows:
            continue
        if len(rows) > 1:
            # DOUBLEHEADER day: the player has one stat row per game and the
            # journal doesn't know which leg this bet was for. Settle only
            # when the outcome is the same either way; an ambiguous bet
            # stays open rather than being graded against the wrong game.
            def _wins(v):
                over = (b["side"] or "OVER").upper() != "UNDER"
                if v == b["line"]:
                    return "push"
                return (v > b["line"]) == over
            outcomes = {_wins(float(r["value"])) for r in rows}
            if len(outcomes) > 1:
                continue
        row = rows[0]

        ck = (b["sport"], b["market"])
        if ck not in closes_cache:
            closes_cache[ck] = hist_db.closing_odds_by_date(hist_conn, *ck)
        close = closes_cache[ck].get((normalize_name(b["player"]), b["date"]))
        close_line = float(close["line"]) if close else None
        if close_line is None:
            # No harvested close for this date — fall back to our own
            # recorded snapshots, so CLV accrues without spending credits.
            if "_snapshots" not in closes_cache:
                closes_cache["_snapshots"] = _snapshot_closes()
            close_line = closes_cache["_snapshots"].get(
                (normalize_name(b["player"]), b["market"], b["date"]))
        _settle_one(conn, b, float(row["value"]), close_line)
        settled += 1

    # --- Void the no-shows ---------------------------------------------
    # A pick journaled from a projected lineup whose player never took the
    # field has no result and never will — the book voids that bet, and the
    # journal mirrors the book. Strictly gated: only on a day whose slate
    # is FULLY final and ingested (anything less is "not settled yet"), and
    # only when the player has no stat row of any kind that day. Voids
    # carry zero P&L and are excluded from every record aggregate.
    day_state: dict = {}
    day_players: dict = {}
    voided = 0
    for b in conn.execute(q, args).fetchall():
        # Team-level markets never void via the no-show rule — teams play.
        if b["market"] in ("moneyline", "total", "spread", "team_total") \
                or not b["date"]:
            continue
        key = (b["sport"], b["date"])
        where, wargs = _hist_where(b)
        if key not in day_state:
            r = hist_conn.execute(
                f"SELECT COUNT(*), SUM(CASE WHEN home_score IS NOT NULL "
                f"THEN 1 ELSE 0 END) FROM games WHERE {where}",
                wargs).fetchone()
            day_state[key] = (int(r[0] or 0), int(r[1] or 0))
        tot, fin = day_state[key]
        if not tot or fin < tot:
            continue
        if key not in day_players:
            day_players[key] = {normalize_name(p["player"]) for p in hist_conn.execute(
                f"SELECT DISTINCT player FROM player_game_logs "
                f"WHERE {where}", wargs)}
        if normalize_name(b["player"]) in day_players[key]:
            continue            # he played — the normal settle path owns him
        conn.execute("UPDATE bets SET status='void', pnl_units=0, pnl_dollars=0 "
                     "WHERE id=?", (b["id"],))
        voided += 1

    conn.commit()
    return settled + voided


def settle(conn, actuals: dict[tuple[str, str], float], sport: str | None = None,
           date: str | None = None, closing: dict[tuple[str, str], float] | None = None) -> int:
    """Grade open bets against actual results. ``actuals`` maps (player, market)
    -> the stat the player posted. Updates each settled bet's P&L and advances
    the bankroll.

    ``closing`` supplies closing lines for CLV; when omitted they're derived
    automatically from the recorded line-move snapshots, so closing-line value
    accrues without any manual bookkeeping."""
    if closing is None:
        try:
            from .linemoves import load_history, closing_lines
            closing = closing_lines(load_history())
        except Exception:      # never let CLV bookkeeping block settling
            closing = {}
    q = "SELECT * FROM bets WHERE status='open'"
    args: list = []
    if sport:
        q += " AND sport=?"; args.append(sport)
    if date:
        q += " AND date=?"; args.append(date)

    settled = 0
    for b in conn.execute(q, args).fetchall():
        key = (b["player"], b["market"])
        if key not in actuals:
            continue
        _settle_one(conn, b, float(actuals[key]), closing.get(key))
        settled += 1
    conn.commit()
    return settled


# --- reporting --------------------------------------------------------------
def _bet_clv(b) -> float | None:
    """Side-aware closing-line value for one settled bet, in line points.

    An over wants the line to RISE after the bet, an under wants it to fall;
    positive always means the market moved our way."""
    if b["closing_line"] is None:
        return None
    move = b["closing_line"] - b["line"]
    return move if (b["side"] or "OVER").upper() == "OVER" else -move


def process_grade(b) -> str | None:
    """Grade the DECISION, not the outcome.

    A won bet that closed worse than we took it got lucky; a lost bet that
    beat the close was a good bet that didn't land. Judging bets by result
    alone is how people talk themselves into bad process — this column is
    the antidote. None when no closing line is known."""
    clv = _bet_clv(b)
    if clv is None:
        return None
    if clv > 0:
        return "good"
    return "flat" if clv == 0 else "bad"


def performance(conn, sport: str | None = None, category: str = "main") -> dict:
    # ``stake_units > 0`` everywhere below: rows staked at zero were never
    # bets (an old grading bug shipped picks the vig had already eaten).
    # Counting them would inflate the W-L column with wagers nobody could
    # have won a unit on. They're reported separately as ``unstaked``.
    q = ("SELECT * FROM bets WHERE status IN ('won','lost','push') "
         "AND category=? AND stake_units > 0")
    args: list = [category]
    if sport:
        q += " AND sport=?"; args.append(sport)
    bets = conn.execute(q, args).fetchall()

    uq = ("SELECT COUNT(*) FROM bets WHERE status IN ('won','lost','push') "
          "AND category=? AND (stake_units IS NULL OR stake_units <= 0)")
    uargs: list = [category]
    if sport:
        uq += " AND sport=?"; uargs.append(sport)
    unstaked = conn.execute(uq, uargs).fetchone()[0]

    wins = sum(1 for b in bets if b["status"] == "won")
    losses = sum(1 for b in bets if b["status"] == "lost")
    pushes = sum(1 for b in bets if b["status"] == "push")
    graded = wins + losses
    staked_u = sum(b["stake_units"] for b in bets if b["status"] != "push")
    net_u = sum(b["pnl_units"] or 0 for b in bets)
    net_d = sum(b["pnl_dollars"] or 0 for b in bets)
    clvs = [c for c in (_bet_clv(b) for b in bets) if c is not None]
    # Process record: of the bets where we know the close, how many were
    # good decisions regardless of result — plus the two honesty counters
    # (wins that got lucky, losses that were still good bets).
    process = {"good": 0, "flat": 0, "bad": 0,
               "lucky_wins": 0, "unlucky_losses": 0}
    for b in bets:
        g = process_grade(b)
        if g is None:
            continue
        process[g] += 1
        if b["status"] == "won" and g == "bad":
            process["lucky_wins"] += 1
        elif b["status"] == "lost" and g == "good":
            process["unlucky_losses"] += 1

    def bucket(field):
        out: dict[str, dict] = {}
        clv_lists: dict[str, list] = {}
        for b in bets:
            k = b[field] or "?"
            d = out.setdefault(k, {"w": 0, "l": 0, "net_u": 0.0})
            if b["status"] == "won": d["w"] += 1
            elif b["status"] == "lost": d["l"] += 1
            d["net_u"] += b["pnl_units"] or 0
            c = _bet_clv(b)
            if c is not None:
                clv_lists.setdefault(k, []).append(c)
        # CLV per bucket — the spec's "which module is actually earning"
        # readout, available long before the win-loss record means anything.
        for k, moves in clv_lists.items():
            out[k]["avg_clv"] = round(sum(moves) / len(moves), 3)
        return out

    return {
        "settled": len(bets), "wins": wins, "losses": losses, "pushes": pushes,
        "win_rate": (wins / graded) if graded else 0.0,
        "units_staked": round(staked_u, 2), "net_units": round(net_u, 2),
        "roi": (net_u / staked_u) if staked_u else 0.0,
        "net_dollars": round(net_d, 2),
        "starting_bankroll": float(get_cfg(conn, "starting_bankroll")),
        "bankroll": bankroll(conn),
        "open": conn.execute(
            "SELECT COUNT(*) FROM bets WHERE status='open' AND category=? "
            "AND stake_units > 0", (category,)).fetchone()[0],
        "unstaked": unstaked,
        "avg_clv": (sum(clvs) / len(clvs)) if clvs else None,
        "process": process,
        "by_grade": bucket("grade"), "by_market": bucket("market"),
        "by_side": bucket("side"), "by_book": bucket("book"),
    }


def summary(conn, sport: str | None = None) -> str:
    p = performance(conn, sport)
    roll_delta = p["bankroll"] - p["starting_bankroll"]
    lines = [
        f"Ledger{f' · {sport.upper()}' if sport else ''}: "
        f"{p['settled']} settled ({p['wins']}-{p['losses']}-{p['pushes']}), "
        f"{p['open']} open",
        f"  Win rate {p['win_rate']:.1%}   ROI {p['roi']:+.1%}   "
        f"net {p['net_units']:+.2f}u",
        f"  Bankroll ${p['starting_bankroll']:.0f} → ${p['bankroll']:.2f} "
        f"({roll_delta:+.2f}, {roll_delta / p['starting_bankroll']:+.1%})",
    ]
    if p["avg_clv"] is not None:
        lines.append(f"  Closing-line value {p['avg_clv']:+.2f} pts avg")
    if p["by_grade"]:
        lines.append("  By grade:")
        for g, d in sorted(p["by_grade"].items(), key=lambda kv: -(kv[1]["w"] + kv[1]["l"])):
            lines.append(f"    {g:>11}: {d['w']}-{d['l']}  ({d['net_u']:+.2f}u)")
    if p["by_side"]:
        parts = [f"{s or '?'} {d['w']}-{d['l']} ({d['net_u']:+.2f}u)"
                 for s, d in sorted(p["by_side"].items())]
        lines.append("  By side:  " + "   ".join(parts))
    return "\n".join(lines)


def pnl_curve(conn, sport: str | None = None) -> list[dict]:
    """Cumulative settled P&L by slate date — the Record page's equity curve.

    One point per date with anything settled: that day's net units, the
    running total, and how many bets graded."""
    q = ("SELECT date, SUM(pnl_units) AS day_u, COUNT(*) AS n FROM bets "
         "WHERE status IN ('won','lost','push') AND category='main' "
         "AND stake_units > 0")
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)
    q += " GROUP BY date ORDER BY date"
    out, cum = [], 0.0
    for r in conn.execute(q, args):
        cum += r["day_u"] or 0.0
        out.append({"date": r["date"], "day_u": round(r["day_u"] or 0.0, 2),
                    "cum_u": round(cum, 2), "n": r["n"]})
    return out


def drawdown_factor(conn, sport: str | None = None,
                    drawdown_u: float = 10.0) -> float:
    """§10 drawdown circuit-breaker (docs/NFL_MODEL.md).

    After a 10-unit peak-to-trough drawdown (10% of bankroll at the standard
    1u = 1%), every stake is cut in half until the peak is recovered.
    Drawdowns are when systems start chasing; halving stakes makes the worst
    case survivable and removes the mathematical possibility of ruin.

    Returns 0.5 while in drawdown, else 1.0. Measured on the settled main
    journal — the same numbers the Record page shows."""
    peak = cum = 0.0
    for point in pnl_curve(conn, sport=sport):
        cum = point["cum_u"]
        peak = max(peak, cum)
    return 0.5 if (peak - cum) >= drawdown_u else 1.0


def recent_settled(conn, limit: int = 30, category: str = "main") -> list[dict]:
    """The last settled picks, newest first — the site's receipts.

    Each row carries its side-aware CLV and process grade so the page can
    show "won but got lucky" / "lost but beat the close" honestly."""
    rows = conn.execute(
        "SELECT date, sport, player, market, side, line, odds, grade, status, "
        "pnl_units, hit_prob, closing_line, stake_units FROM bets "
        "WHERE status IN ('won','lost','push') AND category=? "
        "AND stake_units > 0 "
        "ORDER BY date DESC, id DESC LIMIT ?", (category, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        c = _bet_clv(r)
        d["clv"] = round(c, 3) if c is not None else None
        d["process"] = process_grade(r)
        out.append(d)
    return out


def calibration(conn, category: str = "main", bucket_pts: int = 5) -> dict:
    """Predicted vs realized, in probability buckets — the public honesty page.

    Groups every settled won/lost bet by the model's claimed hit probability
    (5-point buckets by default) and reports what actually happened in each,
    with a ±1.96·√(p(1−p)/n) band so small samples read as "too early", not
    as verdicts. Also scores the model's Brier against the market's own fair
    probability ON THE SAME BETS (fair = hit_prob − edge, since edge was
    stored as model-minus-fair at bet time): if we can't out-forecast the
    de-vigged close on our own selections, the edge story is fiction."""
    from math import sqrt
    rows = conn.execute(
        "SELECT hit_prob, edge, status FROM bets "
        "WHERE status IN ('won','lost') AND category=? AND hit_prob IS NOT NULL",
        (category,)).fetchall()
    nb = max(1, 100 // bucket_pts)
    buckets: list[dict] = [{"lo": i * bucket_pts, "hi": (i + 1) * bucket_pts,
                            "n": 0, "_p": 0.0, "_w": 0} for i in range(nb)]
    se_model = 0.0
    se_market = 0.0
    n_market = 0
    for r in rows:
        p = min(max(float(r["hit_prob"]), 0.0), 1.0)
        won = 1.0 if r["status"] == "won" else 0.0
        b = buckets[min(int(p * 100) // bucket_pts, nb - 1)]
        b["n"] += 1
        b["_p"] += p
        b["_w"] += won
        se_model += (p - won) ** 2
        if r["edge"] is not None:
            fair = min(max(p - float(r["edge"]), 0.01), 0.99)
            se_market += (fair - won) ** 2
            n_market += 1
    out_buckets = []
    for b in buckets:
        if not b["n"]:
            continue
        pred = b["_p"] / b["n"]
        act = b["_w"] / b["n"]
        ci = 1.96 * sqrt(pred * (1.0 - pred) / b["n"])
        out_buckets.append({
            "lo": b["lo"], "hi": b["hi"], "n": b["n"],
            "predicted": round(pred, 4), "actual": round(act, 4),
            "ci": round(ci, 4), "in_band": abs(act - pred) <= ci})
    n = len(rows)
    return {
        "n": n, "bucket_pts": bucket_pts, "buckets": out_buckets,
        "brier_model": round(se_model / n, 4) if n else None,
        "brier_market": round(se_market / n_market, 4) if n_market else None,
        # Positive = the model out-forecasts the de-vigged market prices on
        # its own picks; negative = the market knew better.
        "brier_edge": (round(se_market / n_market - se_model / n, 4)
                       if n and n_market else None),
    }


# Account-health scoring weights — how much each behavior pattern
# contributes to a book's 0–100 limit-risk estimate.
HEALTH_MIN_BETS = 5
HEALTH_W_CLV = 45          # books limit closing-line beaters first
HEALTH_W_CONCENTRATION = 25  # living in one low-limit prop market
HEALTH_W_STAKES = 15       # precise, model-sized stakes read sharp
HEALTH_W_VOLUME = 15       # sheer graded volume at one shop


def account_health(conn) -> dict:
    """Estimate, per book, how 'sharp' this journal looks to a risk desk.

    Books don't publish limit criteria, but the patterns they act on are
    well known: consistently beating the close, hammering one prop market,
    and precise non-round stakes. This scores OUR OWN journaled behavior
    against those patterns — 0 (recreational-looking) to 100 (walking
    limit-risk) — with the drivers and the concrete actions that would
    lower it. It is inference from our own betting record, nothing more:
    no insider knowledge of any book's actual risk rules."""
    bets = conn.execute(
        "SELECT * FROM bets WHERE status IN ('won','lost','push') "
        "AND category='main'").fetchall()
    by_book: dict[str, list] = {}
    for b in bets:
        by_book.setdefault(b["book"] or "?", []).append(b)

    books = []
    for book, rows in by_book.items():
        if len(rows) < HEALTH_MIN_BETS:
            continue
        # CLV beat rate — the strongest limit signal a book can see.
        clvs = [c for c in (_bet_clv(b) for b in rows) if c is not None]
        beat_rate = (sum(1 for c in clvs if c > 0) / len(clvs)) if clvs else None
        clv_pts = (beat_rate if beat_rate is not None else 0.5) * HEALTH_W_CLV
        # Market concentration — share of volume in the single busiest market.
        mkts: dict[str, int] = {}
        for b in rows:
            mkts[b["market"] or "?"] = mkts.get(b["market"] or "?", 0) + 1
        top_market, top_n = max(mkts.items(), key=lambda kv: kv[1])
        conc = top_n / len(rows)
        conc_pts = conc * HEALTH_W_CONCENTRATION
        # Stake pattern — fraction of dollar stakes that aren't round $5s.
        staked = [b["stake_dollars"] for b in rows if b["stake_dollars"]]
        sharp_stakes = (sum(1 for s in staked if abs(s / 5.0 - round(s / 5.0)) > 1e-9)
                        / len(staked)) if staked else 0.0
        stake_pts = sharp_stakes * HEALTH_W_STAKES
        # Volume exposure — graded bets at this one shop, saturating at 100.
        vol_pts = min(len(rows) / 100.0, 1.0) * HEALTH_W_VOLUME

        score = round(clv_pts + conc_pts + stake_pts + vol_pts)
        band = "low" if score < 35 else ("moderate" if score <= 65 else "elevated")

        drivers = []
        if beat_rate is not None:
            drivers.append(f"beats the close on {beat_rate:.0%} of tracked bets"
                           + (" — the #1 pattern risk desks act on"
                              if beat_rate >= 0.55 else ""))
        drivers.append(f"{conc:.0%} of volume is {top_market}")
        if sharp_stakes > 0.5:
            drivers.append("stakes are precise model-sized amounts, not round numbers")
        actions = []
        if conc >= 0.5:
            actions.append(f"mix in main-line bets (sides/totals) so {top_market} "
                           f"isn't {conc:.0%} of your volume here")
        if sharp_stakes > 0.5:
            actions.append("round stakes to the nearest $5 — precision costs "
                           "almost nothing in EV and reads recreational")
        if len(by_book) == 1:
            actions.append("open a second book and split volume — one outlet "
                           "is a single point of failure")
        if score > 65:
            actions.append("route your most limit-prone plays (props with big "
                           "CLV) to the book you care least about keeping")
        books.append({
            "book": book, "bets": len(rows), "score": score, "band": band,
            "beat_close_rate": round(beat_rate, 3) if beat_rate is not None else None,
            "avg_clv": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "top_market": top_market, "concentration": round(conc, 3),
            "sharp_stake_rate": round(sharp_stakes, 3),
            "drivers": drivers, "actions": actions})
    books.sort(key=lambda d: -d["score"])
    return {
        "books": books,
        "disclaimer": ("Inferred from your own journaled betting patterns — "
                       "an estimate of how sharp your action looks, not "
                       "knowledge of any sportsbook's actual risk rules."),
    }


def longshot_report(conn) -> dict:
    """The Long Shots scoreboard.

    The W-L / ROI record covers ONLY ``category='longshot'`` — the board's
    actual picks. The calibration readout ("does the model's claimed
    probability beat the books' implied?") deliberately spans picks AND the
    watchlist: it is a measurement, and the bigger sample is what made the
    MIN_MODEL_PROB quartile analysis possible. The watchlist's own burn
    rate is reported separately so nobody mistakes it for a record.
    """
    p = performance(conn, category="longshot")
    row = conn.execute(
        "SELECT COUNT(*) AS n, AVG(hit_prob) AS model_p, "
        "AVG(100.0 / (odds + 100.0)) AS implied_p, "
        "AVG(CASE WHEN status='won' THEN 1.0 ELSE 0.0 END) AS actual_p "
        "FROM bets WHERE category IN ('longshot', 'longshot_watch') "
        "AND status IN ('won','lost') AND odds > 0").fetchone()
    p["calibration_n"] = row["n"] or 0
    p["avg_model_prob"] = round(row["model_p"], 4) if row["model_p"] is not None else None
    p["avg_implied_prob"] = round(row["implied_p"], 4) if row["implied_p"] is not None else None
    p["actual_hit_rate"] = round(row["actual_p"], 4) if row["actual_p"] is not None else None
    p["recent"] = recent_settled(conn, limit=15, category="longshot")
    # The watchlist sample, kept visibly apart: every real-priced homer on
    # the slate, graded at a nominal flat stake purely to tune the model.
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(status='won'), 0) AS w, "
        "COALESCE(SUM(pnl_units), 0) AS u, COALESCE(SUM(stake_units), 0) AS s "
        "FROM bets WHERE category='longshot_watch' "
        "AND status IN ('won','lost')").fetchone()
    p["watch"] = {
        "graded": row["n"] or 0, "wins": row["w"] or 0,
        "net_units": round(row["u"], 2),
        "roi": round(row["u"] / row["s"], 4) if row["s"] else 0.0,
        "open": conn.execute(
            "SELECT COUNT(*) FROM bets WHERE category='longshot_watch' "
            "AND status='open'").fetchone()[0],
    }
    # Which long-shot markets carry the bucket, and at what price. Average
    # odds matter here in a way they don't for the main record: a +250
    # board and a +900 board that both hit 12% are wildly different bets.
    row = conn.execute(
        "SELECT COUNT(*) n, AVG(odds) avg_odds, MIN(odds) min_odds, "
        "MAX(odds) max_odds FROM bets WHERE category='longshot' "
        "AND status IN ('won','lost')").fetchone()
    p["avg_odds"] = round(row["avg_odds"]) if row["avg_odds"] is not None else None
    p["odds_range"] = ([row["min_odds"], row["max_odds"]]
                       if row["n"] else None)
    p["by_sport"] = {}
    for r in conn.execute(
            "SELECT sport, COUNT(*) n, SUM(status='won') w, "
            "COALESCE(SUM(pnl_units),0) u FROM bets WHERE category='longshot' "
            "AND status IN ('won','lost') GROUP BY sport"):
        p["by_sport"][r["sport"]] = {"n": r["n"], "w": r["w"],
                                     "net_u": round(r["u"], 2)}
    return p


def open_by_day(conn, today: str) -> list[dict]:
    """Open picks grouped by slate date, newest first.

    "70 open" is never a useful number on its own: tonight's picks are
    supposed to be open, picks from a finished day are a symptom, and the
    two are indistinguishable in a total. Each entry carries ``stale``
    (the day is over, so these should already have graded) so a caller can
    say which kind it is looking at.
    """
    rows = conn.execute(
        "SELECT date, category, COUNT(*) FROM bets WHERE status='open' "
        "GROUP BY date, category ORDER BY date DESC").fetchall()
    by_day: dict = {}
    for r in rows:
        d, cat, n = r[0], r[1], r[2]
        by_day.setdefault(d or "", {})[cat or "main"] = n
    return [{"date": d, "counts": by_day[d], "total": sum(by_day[d].values()),
             "stale": bool(d) and d < today}
            for d in sorted(by_day, reverse=True)]


def unstaked_scorecard(conn) -> dict:
    """Were the 0.00-unit picks actually profitable? Measure, don't argue.

    They win often — that's not the question. The question is whether they
    won often enough to beat the prices they were offered at. This reports
    the realized hit rate against the average break-even those odds imply,
    plus the flat-stake P&L they would have produced."""
    rows = conn.execute(
        "SELECT odds, status FROM bets WHERE category='main' "
        "AND (stake_units IS NULL OR stake_units <= 0) "
        "AND status IN ('won','lost')").fetchall()
    if not rows:
        return {"n": 0}
    wins = sum(1 for r in rows if r["status"] == "won")
    be = sum(1.0 / american_to_decimal(r["odds"]) for r in rows) / len(rows)
    net = sum((american_to_decimal(r["odds"]) - 1.0) if r["status"] == "won"
              else -1.0 for r in rows)
    hit = wins / len(rows)
    return {"n": len(rows), "wins": wins, "losses": len(rows) - wins,
            "hit_rate": round(hit, 4), "break_even": round(be, 4),
            "edge_pts": round((hit - be) * 100, 2),
            "roi": round(net / len(rows), 4)}


def resize_unstaked(conn, stake_units: float = 0.1) -> int:
    """Give already-journaled zero-stake picks a flat stake and real P&L.

    A grading bug once shipped picks the vig had already eaten, and Kelly
    sized them at 0.00 units — so they sat in the journal as wins and
    losses worth nothing, and the profit (or loss) they actually produced
    never showed on the record. This sizes every one of them at a flat
    ``stake_units`` and recomputes P&L from the price and result, exactly
    like the long-shot bucket: units only, no dollars, measurement not
    a claim that money was placed."""
    rows = conn.execute(
        "SELECT id, odds, status FROM bets "
        "WHERE category='main' AND (stake_units IS NULL OR stake_units <= 0)"
    ).fetchall()
    n = 0
    for r in rows:
        if r["status"] == "won":
            pnl = round((american_to_decimal(r["odds"]) - 1.0) * stake_units, 4)
        elif r["status"] == "lost":
            pnl = -stake_units
        else:
            pnl = 0.0            # push, or still open
        conn.execute(
            "UPDATE bets SET stake_units=?, pnl_units=? WHERE id=?",
            (stake_units, pnl if r["status"] in ("won", "lost", "push") else None,
             r["id"]))
        n += 1
    conn.commit()
    return n


def recompute_bankroll(conn) -> float:
    """Rebuild the bankroll from the main journal's realized dollars.

    The running value is advanced bet-by-bet as things settle, so any
    repair that moves or re-sizes rows leaves it stale. This restates it
    from what the record actually says."""
    start = float(get_cfg(conn, "starting_bankroll"))
    total = conn.execute(
        "SELECT COALESCE(SUM(pnl_dollars), 0) FROM bets WHERE category='main' "
        "AND status IN ('won','lost','push')").fetchone()[0] or 0.0
    val = round(start + total, 2)
    set_cfg(conn, "bankroll", val)
    return val


def split_watch_from_longshots(conn) -> int:
    """Repair: move watchlist rows out of the Long Shots record bucket.

    The journal used to put the ENTIRE watchlist — every real-priced homer
    on the slate, often 100+ names a night — into ``category='longshot'``
    alongside the (max three) picks, so the Long Shots W-L was scoring the
    dart board. Watchlist rows are identifiable by their grade ('Watch';
    picks always carry a real grade) and move to ``longshot_watch`` with
    their settled P&L intact. Safe to run every build — a no-op once clean.
    """
    rows = conn.execute(
        "SELECT id, sport, date, player, market FROM bets "
        "WHERE category='longshot' AND grade='Watch'").fetchall()
    moved = 0
    for r in rows:
        dup = conn.execute(
            "SELECT id FROM bets WHERE sport=? AND date=? AND player=? "
            "AND market=? AND category='longshot_watch'",
            (r["sport"], r["date"], r["player"], r["market"])).fetchone()
        if dup:
            conn.execute("DELETE FROM bets WHERE id=?", (r["id"],))
        else:
            conn.execute(
                "UPDATE bets SET category='longshot_watch' WHERE id=?",
                (r["id"],))
        moved += 1
    conn.commit()
    return moved


def move_longshots_out_of_main(conn, stake_units: float = 0.1) -> int:
    """Relocate already-journaled long-shot markets into their own bucket.

    Home-run and anytime-TD props that cleared the main board were being
    journaled twice — once in the headline record, once in the long-shot
    bucket. The headline record is supposed to describe the picks the
    model stands behind, not a board of plus-money darts, so the main
    copies are moved out (or dropped when the long-shot copy already
    exists) and the bankroll is restated."""
    marks = ",".join("?" for _ in LONGSHOT_MARKETS)
    rows = conn.execute(
        f"SELECT * FROM bets WHERE category='main' AND market IN ({marks})",
        tuple(LONGSHOT_MARKETS)).fetchall()
    moved = 0
    for r in rows:
        dup = conn.execute(
            "SELECT id FROM bets WHERE sport=? AND date=? AND player=? "
            "AND market=? AND category='longshot'",
            (r["sport"], r["date"], r["player"], r["market"])).fetchone()
        if dup:
            conn.execute("DELETE FROM bets WHERE id=?", (r["id"],))
        else:
            if r["status"] == "won":
                pnl = round((american_to_decimal(r["odds"]) - 1.0) * stake_units, 4)
            elif r["status"] == "lost":
                pnl = -stake_units
            elif r["status"] == "push":
                pnl = 0.0
            else:
                pnl = None                    # still open
            conn.execute(
                "UPDATE bets SET category='longshot', stake_units=?, "
                "stake_dollars=0, pnl_units=?, pnl_dollars=0 WHERE id=?",
                (stake_units, pnl, r["id"]))
        moved += 1
    conn.commit()
    recompute_bankroll(conn)
    return moved


def export_json(conn, path) -> None:
    """Write the journal's performance to a JSON file the website renders.

    Called after every settle, so the Track Record page always reflects the
    latest graded picks without anyone touching a terminal."""
    import datetime as _dt
    import json as _json
    from pathlib import Path as _Path
    out = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "overall": performance(conn),
        "mlb": performance(conn, "mlb"),
        "nfl": performance(conn, "nfl"),
        "curve": pnl_curve(conn),
        "recent": recent_settled(conn),
        "longshots": longshot_report(conn),
        "stale_flags": stale_report(conn),
        "form_sampler": form_report(conn),
        "ufc_record": ufc_report(conn),
        "calibration": calibration(conn),
        "account_health": account_health(conn),
    }
    p = _Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(out, indent=2))
