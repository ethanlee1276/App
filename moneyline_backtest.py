#!/usr/bin/env python3
"""Backtest the game-winner model against harvested closing moneylines.

    python3 moneyline_backtest.py mlb
    python3 moneyline_backtest.py mlb --min-games 20
    python3 moneyline_backtest.py nfl
    python3 moneyline_backtest.py cfb      # the sharp-anchor replay only

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
    ap.add_argument("sport", nargs="?", default="mlb", choices=["mlb", "nfl", "cfb"])
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--min-games", type=int, default=15,
                    help="both teams need this many completed games before "
                         "their matchup is priced (default 15)")
    args = ap.parse_args()

    conn = db.connect(args.db)
    if args.sport == "cfb":
        # COLLEGE'S MODEL WALK LIVES ELSEWHERE. `backtest_moneylines`
        # walks `teamrates.ratings_for_season` — the plain shrunk-margin
        # rating the pro leagues ship. College ships opponent-adjusted
        # ratings with a fitted home field and a recruiting prior, and
        # its measurement against the close is `engine.gamecal --sport
        # cfb` (the slopes) and `engine.gamerank.measure_cfb` (the
        # ranking); printing the plain walk here would grade a model the
        # college board does not run. What college shares with the other
        # two is the strategy below, which has no model in it at all.
        print("CFB moneyline backtest · the college model is measured by "
              "`python3 -m engine.gamecal --sport cfb` and "
              "`engine.gamerank.measure_cfb`, not by this walk — "
              "sharp-anchor replay only")
    else:
        report = backtest_moneylines(conn, args.sport, min_team_games=args.min_games)
        print(report.summary())

    # A/B: same games, same prices, plus each starter's walk-forward quality.
    if args.sport == "mlb":
        if db.starters_by_game(conn, "mlb"):
            print()
            print(backtest_moneylines(conn, "mlb", min_team_games=args.min_games,
                                      use_pitchers=True).summary())
        else:
            print("\n  (no starting pitchers stored — re-run "
                  "`python3 ingest.py mlb --from <start> --to <end>` to add "
                  "them, then this prints a pitcher-aware A/B)")

    # Sharp anchor: no model at all — just soft books disagreeing with the
    # sharp book's de-vigged fair price.
    from engine.gamebacktest import backtest_sharp_anchor
    print()
    print(backtest_sharp_anchor(conn, args.sport).summary())


if __name__ == "__main__":
    main()
