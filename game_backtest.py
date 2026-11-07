#!/usr/bin/env python3
"""Grade the spread / total / moneyline model against real closing numbers.

    python3 game_backtest.py mlb                  # every market
    python3 game_backtest.py nfl --market total
    python3 game_backtest.py mlb --min-games 25   # stricter history bar

This is the measurement the game-bet layer never had. Player props have been
backtested for a long time; spreads and totals shipped on an argument,
because the closing numbers they would have to be graded against were never
stored. The build asked the odds API for h2h, spreads and totals every day,
attached all three, priced bets off all three — and journaled only h2h.

That is fixed in two directions:

  * FORWARD, free: every build now writes the spread and total it already
    pulled (engine.lineledger). Run the app for a few weeks and this
    command has something to chew on, at no API cost.
  * BACKWARD, paid: harvest_odds.py stores them for past dates now too.
    Credits scale with markets, so ask for only what you need.

What the numbers mean, in the order they matter:

  Projection off the closing number  — the honest headline. If the model
    sits four points off the market on average, no downstream gate saves
    it, and every "edge" on the board is that error wearing a percentage.
  Refused  — games where the disagreement exceeded the credibility ceiling.
    A high count is not a haul of missed bets; it is the model telling you
    its ratings are off.
  ROI  — last, and meaningless under ~100 bets. The summary says so itself.
"""

from __future__ import annotations

import argparse
import sys

from engine import db
from engine.gamebacktest import backtest_game_lines, backtest_moneylines

MARKETS = ("total", "spread", "moneyline")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sport", choices=["nfl", "mlb", "cfb", "nba", "wnba"])
    ap.add_argument("--market", default="all", choices=("all",) + MARKETS)
    ap.add_argument("--min-games", type=int, default=15,
                    help="prior games each team needs before a bet is priced "
                         "(default 15 — below that the ratings are noise)")
    ap.add_argument("--db", default=None, help="path to history.db")
    args = ap.parse_args()

    # CFB registers its own variance on import; without this the pricer
    # refuses rather than borrowing the NFL's, which is the correct
    # behaviour but a confusing way to learn about an import.
    if args.sport == "cfb":
        import engine.cfb.ratings          # noqa: F401

    conn = db.connect(args.db) if args.db else db.connect()
    wanted = MARKETS if args.market == "all" else (args.market,)
    ran = False
    for market in wanted:
        print()
        try:
            if market == "moneyline":
                r = backtest_moneylines(conn, args.sport,
                                        min_team_games=args.min_games)
            else:
                r = backtest_game_lines(conn, args.sport, market,
                                        min_team_games=args.min_games)
        except ValueError as exc:
            # A sport with no curve or no registered variance says so by
            # name instead of being replayed through another league's.
            print(f"{args.sport.upper()} {market}: {exc}")
            continue
        print(r.summary())
        ran = True

    if not ran:
        sys.exit(1)
    print("\nRead the projection error first. ROI on a few dozen bets is a "
          "coin flip with a decimal point.")


if __name__ == "__main__":
    main()
