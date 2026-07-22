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
def settle(conn, actuals: dict[tuple[str, str], float], sport: str | None = None,
           date: str | None = None, closing: dict[tuple[str, str], float] | None = None) -> int:
    """Grade open bets against actual results. ``actuals`` maps (player, market)
    -> the stat the player posted; ``closing`` optionally supplies closing lines
    for CLV. Updates each settled bet's P&L and advances the bankroll."""
    closing = closing or {}
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
        actual = float(actuals[key])
        if actual > b["line"]:
            status, pnl_u = "won", (american_to_decimal(b["odds"]) - 1.0) * b["stake_units"]
        elif actual < b["line"]:
            status, pnl_u = "lost", -b["stake_units"]
        else:
            status, pnl_u = "push", 0.0
        pnl_d = round(pnl_u / b["stake_units"] * b["stake_dollars"], 2) if b["stake_units"] else 0.0
        conn.execute(
            "UPDATE bets SET status=?, actual=?, pnl_units=?, pnl_dollars=?, closing_line=? WHERE id=?",
            (status, actual, round(pnl_u, 4), pnl_d, closing.get(key), b["id"]))
        set_cfg(conn, "bankroll", round(bankroll(conn) + pnl_d, 2))
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
    clvs = [b["closing_line"] - b["line"] for b in bets if b["closing_line"] is not None]

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
    return "\n".join(lines)
