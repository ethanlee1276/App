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

SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT,
    side TEXT, line REAL, book TEXT, odds INTEGER,
    projection REAL, hit_prob REAL, edge REAL, confidence REAL, grade TEXT,
    stake_units REAL, stake_dollars REAL,
    status TEXT DEFAULT 'open', actual REAL,
    pnl_units REAL, pnl_dollars REAL, closing_line REAL,
    UNIQUE (sport, date, player, market)
);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {"starting_bankroll": "1000", "unit_pct": "1.0", "bankroll": "1000"}


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
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
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open')",
            (now, sport, date, r["player"], r["market"], r.get("side", "OVER"),
             r["line"], r.get("book", ""), r.get("odds", -110), r.get("projection"),
             r.get("hit_prob"), r.get("edge"), r.get("confidence"), r.get("grade"),
             stake_units, round(stake_units * unit_dollars, 2)))
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
        _settle_one(conn, b, float(row["value"]),
                    float(close["line"]) if close else None)
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
def performance(conn, sport: str | None = None) -> dict:
    q = "SELECT * FROM bets WHERE status IN ('won','lost','push')"
    args: list = []
    if sport:
        q += " AND sport=?"; args.append(sport)
    bets = conn.execute(q, args).fetchall()

    wins = sum(1 for b in bets if b["status"] == "won")
    losses = sum(1 for b in bets if b["status"] == "lost")
    pushes = sum(1 for b in bets if b["status"] == "push")
    graded = wins + losses
    staked_u = sum(b["stake_units"] for b in bets if b["status"] != "push")
    net_u = sum(b["pnl_units"] or 0 for b in bets)
    net_d = sum(b["pnl_dollars"] or 0 for b in bets)
    # CLV is side-aware: an over wants the line to RISE after the bet, an
    # under wants it to fall.
    clvs = []
    for b in bets:
        if b["closing_line"] is not None:
            move = b["closing_line"] - b["line"]
            clvs.append(move if (b["side"] or "OVER").upper() == "OVER" else -move)

    def bucket(field):
        out: dict[str, dict] = {}
        for b in bets:
            k = b[field] or "?"
            d = out.setdefault(k, {"w": 0, "l": 0, "net_u": 0.0})
            if b["status"] == "won": d["w"] += 1
            elif b["status"] == "lost": d["l"] += 1
            d["net_u"] += b["pnl_units"] or 0
        return out

    return {
        "settled": len(bets), "wins": wins, "losses": losses, "pushes": pushes,
        "win_rate": (wins / graded) if graded else 0.0,
        "units_staked": round(staked_u, 2), "net_units": round(net_u, 2),
        "roi": (net_u / staked_u) if staked_u else 0.0,
        "net_dollars": round(net_d, 2),
        "starting_bankroll": float(get_cfg(conn, "starting_bankroll")),
        "bankroll": bankroll(conn),
        "open": conn.execute("SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0],
        "avg_clv": (sum(clvs) / len(clvs)) if clvs else None,
        "by_grade": bucket("grade"), "by_market": bucket("market"),
        "by_side": bucket("side"),
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
