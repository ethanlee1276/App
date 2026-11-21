#!/usr/bin/env python3
"""What data the box already owns, counted — the research lab's data audit, its half that only the box can answer.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/audit_box.py

Research spec Part 3 / Task 1 (Ethan, 2026-10-17). research/sources.json
lists every source and what could be verified from the sandbox; this counts
what the droplet has actually stored, so the lab can decide what it still
has to buy before spending anything:

  odds_history (data/history.db)   harvested snapshots per sport: rows,
                                   events, books, markets (props vs game
                                   lines), first and last snapshot
  line_history.jsonl               our own quotes each pull, streamed
  the journal (data/ledger.db)     picks per sport and book: settled, with a
                                   market fair at pick time, with a close
  player_game_logs                 outcomes per sport: seasons and rows
  game_officials, ufc_fights ...   row counts of the newer tables

Every database is opened READ-ONLY; nothing is written.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME_MARKETS = ("h2h", "spreads", "totals", "moneyline", "spread", "total", "team_total")


def _ro(path: Path):
    if not path.exists():
        return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _has(conn, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def odds_history(conn) -> list[str]:
    if not _has(conn, "odds_history"):
        return ["  odds_history: no table"]
    out = ["odds_history (harvested snapshots):"]
    for r in conn.execute(
            "SELECT sport, COUNT(*) n, COUNT(DISTINCT event_id) ev, COUNT(DISTINCT book) books, "
            "COUNT(DISTINCT taken_at) snaps, MIN(taken_at) lo, MAX(taken_at) hi FROM odds_history GROUP BY sport"):
        out.append(f"  {r['sport']:<6} {r['n']:>9,} rows  {r['ev']:>6,} events  {r['books']:>2} books  "
                   f"{r['snaps']:>6,} snapshots  {r['lo']} → {r['hi']}")
        props = conn.execute(
            "SELECT market, COUNT(*) n, COUNT(DISTINCT event_id) ev FROM odds_history WHERE sport=? "
            "GROUP BY market ORDER BY n DESC", (r["sport"],)).fetchall()
        game = sum(p["n"] for p in props if p["market"] in GAME_MARKETS)
        out.append(f"         game lines {game:,} rows; player markets {sum(p['n'] for p in props) - game:,} rows: "
                   + ", ".join(f"{p['market']} {p['ev']}ev" for p in props if p["market"] not in GAME_MARKETS)[:400])
    return out


def line_history(path: Path) -> list[str]:
    if not path.exists():
        return ["line_history.jsonl: not present"]
    n, lo, hi = 0, None, None
    markets, books = defaultdict(int), set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            n += 1
            ts = r.get("ts")
            if isinstance(ts, (int, float)):
                lo = ts if lo is None else min(lo, ts)
                hi = ts if hi is None else max(hi, ts)
            markets[r.get("market")] += 1
            books.add(r.get("book"))

    def day(t):
        return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).date().isoformat() if t else "?"
    top = sorted(markets.items(), key=lambda kv: -kv[1])[:10]
    return [f"line_history.jsonl: {n:,} quotes, {len(books)} books, {day(lo)} → {day(hi)}, "
            f"{path.stat().st_size / 1e6:.0f} MB",
            "  top markets: " + ", ".join(f"{m} {c:,}" for m, c in top)]


def journal(conn) -> list[str]:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    fair = "SUM(fair_consensus IS NOT NULL)" if "fair_consensus" in cols else "0"
    close = "SUM(closing_odds IS NOT NULL OR closing_line IS NOT NULL)" if "closing_odds" in cols else "SUM(closing_line IS NOT NULL)"
    out = ["the journal (data/ledger.db), by sport and book:"]
    for r in conn.execute(
            f"SELECT sport, category, COUNT(*) n, SUM(status IN ('won','lost')) settled, {fair} fair, {close} closed, "
            f"MIN(date) lo, MAX(date) hi FROM bets GROUP BY sport, category ORDER BY sport, n DESC"):
        out.append(f"  {r['sport']:<6} {r['category']:<12} {r['n']:>7,} picks  {r['settled'] or 0:>7,} settled  "
                   f"{r['fair'] or 0:>7,} with a market fair  {r['closed'] or 0:>7,} with a close  {r['lo']} → {r['hi']}")
    if _has(conn, "forecast_log"):
        out.append(f"  forecast_log (sealed before the game): {conn.execute('SELECT COUNT(*) FROM forecast_log').fetchone()[0]:,} rows")
    return out


def outcomes(conn) -> list[str]:
    out = ["player_game_logs (outcomes):"]
    for r in conn.execute("SELECT sport, MIN(season) lo, MAX(season) hi, COUNT(*) n, COUNT(DISTINCT market) m "
                          "FROM player_game_logs GROUP BY sport"):
        out.append(f"  {r['sport']:<6} seasons {r['lo']}-{r['hi']}  {r['n']:>10,} rows  {r['m']} markets")
    extra = []
    for t in ("game_officials", "ufc_fights", "nhl_shots", "nba_shots", "mlb_pitches", "carries", "targets", "kicks"):
        if _has(conn, t):
            extra.append(f"{t} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,}")
    out.append("  other tables: " + ", ".join(extra))
    return out


def main() -> int:
    print(f"Box data audit — {_dt.date.today().isoformat()}")
    hist = _ro(ROOT / "data" / "history.db")
    if hist is not None:
        for line in odds_history(hist) + outcomes(hist):
            print(line)
        hist.close()
    else:
        print("data/history.db: not present")
    for line in line_history(ROOT / "data" / "cache" / "line_history.jsonl"):
        print(line)
    led = _ro(ROOT / "data" / "ledger.db")
    if led is not None and _has(led, "bets"):
        for line in journal(led):
            print(line)
        led.close()
    else:
        print("data/ledger.db: not present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
