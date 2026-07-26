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
        else:
            continue                     # run-line journaling: future work
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


# Long-shot markets we can actually settle from ingested game logs. NFL
# anytime-TD boards join here once a TD market exists in the NFL logs —
# journaling unsettleable bets would just accumulate rows stuck open forever.
SETTLEABLE_LONGSHOTS = {"home_runs"}


def log_longshots(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the Long Shots board — separately from the main record.

    Everything the board shows (strict value picks AND the watchlist) is
    tracked at a small flat stake with ZERO dollar exposure: the point is
    measurement — does the model's HR probability beat the market's implied
    one? — not a claim these are bets worth placing. ``category='longshot'``
    keeps them out of the headline record entirely.
    """
    sport = result.get("sport", "mlb")
    date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    rows = (list(result.get("long_shots") or [])
            + list(result.get("longshot_watch") or []))
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
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'longshot')",
            (now, sport, date, r["player"], market, "OVER", 0.5,
             r.get("book", ""), odds, None, r.get("model_prob"),
             r.get("edge", r.get("ev_per_unit")), r.get("confidence"),
             r.get("grade", "Watch"), flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


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
        if b["market"] == "moneyline":
            # player = the team picked; the game's final score settles it.
            g = hist_conn.execute(
                "SELECT home, away, home_score, away_score FROM games "
                "WHERE sport=? AND period=? AND (home=? OR away=?) "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL",
                (b["sport"], b["date"], b["player"], b["player"])).fetchone()
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
                "SELECT home_score, away_score FROM games "
                "WHERE sport=? AND period=? AND game_id=? "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL",
                (b["sport"], b["date"], b["player"])).fetchone()
            if g is None:
                continue
            _settle_one(conn, b, float(g["home_score"]) + float(g["away_score"]), None)
            settled += 1
            continue
        row = hist_conn.execute(
            "SELECT value FROM player_game_logs WHERE sport=? AND period=? "
            "AND market=? AND player=?",
            (b["sport"], b["date"], b["market"], b["player"])).fetchone()
        if row is None:
            # Name-shape fallback (feeds disagree on accents/suffixes).
            target = normalize_name(b["player"])
            row = next(
                (c for c in hist_conn.execute(
                    "SELECT player, value FROM player_game_logs "
                    "WHERE sport=? AND period=? AND market=?",
                    (b["sport"], b["date"], b["market"]))
                 if normalize_name(c["player"]) == target), None)
        if row is None:
            continue

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
    conn.commit()
    return settled


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
    """The Long Shots scoreboard: flat-stake record plus the calibration
    readout that actually answers "is the board finding value" — the model's
    average claimed probability vs the books' implied vs what really hit."""
    p = performance(conn, category="longshot")
    row = conn.execute(
        "SELECT AVG(hit_prob) AS model_p, "
        "AVG(100.0 / (odds + 100.0)) AS implied_p, "
        "AVG(CASE WHEN status='won' THEN 1.0 ELSE 0.0 END) AS actual_p "
        "FROM bets WHERE category='longshot' AND status IN ('won','lost') "
        "AND odds > 0").fetchone()
    p["avg_model_prob"] = round(row["model_p"], 4) if row["model_p"] is not None else None
    p["avg_implied_prob"] = round(row["implied_p"], 4) if row["implied_p"] is not None else None
    p["actual_hit_rate"] = round(row["actual_p"], 4) if row["actual_p"] is not None else None
    p["recent"] = recent_settled(conn, limit=15, category="longshot")
    return p


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
        "calibration": calibration(conn),
        "account_health": account_health(conn),
    }
    p = _Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(out, indent=2))
