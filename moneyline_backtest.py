#!/usr/bin/env python3
"""Backtest the game-winner model against harvested closing moneylines.

    python3 moneyline_backtest.py mlb
    python3 moneyline_backtest.py mlb --min-games 20

Uses only data already in the local database: completed games (free ingest)
joined to h2h moneylines harvested by harvest_odds.py. Team ratings are built
walk-forward — each game is priced from results strictly before its date — and
settled with the real final score, so the ROI is market-relative: would the
production moneyline model have beaten the closing price?
"""

from __future__ import annotations

import argparse

from engine import db
from engine.gamebacktest import backtest_moneylines


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Walk-forward moneyline backtest vs harvested closes.")
    ap.add_argument("sport", nargs="?", default="mlb", choices=["mlb", "nfl"])
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--min-games", type=int, default=15,
                    help="both teams need this many completed games before "
                         "their matchup is priced (default 15)")
    args = ap.parse_args()

    conn = db.connect(args.db)
    report = backtest_moneylines(conn, args.sport, min_team_games=args.min_games)
    print(report.summary())


if __name__ == "__main__":
    main()
