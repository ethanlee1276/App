#!/usr/bin/env python3
"""Replay the Pick of the Day over stored closes. Did it pay?

    python3 potd_backtest.py mlb
    python3 potd_backtest.py nfl
    python3 potd_backtest.py --all

Ethan, 2026-09-16: "you should not stop until you confirm that the Pick
of the Day we show every day is elite and worth betting on." This is the
confirmation, and it is the only thing in this repository that grades
the PRODUCT rather than the method underneath it — one pick a day,
chosen by `potd.choose` under its own bars, settled by the final score.

Reads only what is already on disk: completed games (free ingest) joined
to moneylines harvested by `harvest_odds.py`. No network, no API credits.
Every caveat the number carries is printed under it and written out in
`engine/potdbacktest`'s header — read them before the ROI.
"""

from __future__ import annotations

import argparse

from engine import db
from engine.potdbacktest import replay_potd, summarize

SPORTS = ("mlb", "nfl", "cfb", "nba", "wnba")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Replay the Pick of the Day against harvested closes.")
    ap.add_argument("sport", nargs="?", default="mlb", choices=SPORTS)
    ap.add_argument("--all", action="store_true",
                    help="every league in TOP_PICK_LEAGUES, one after another")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--sharp", default="Pinnacle",
                    help="the book whose two-way close is de-vigged for the "
                         "fair (default Pinnacle)")
    ap.add_argument("--rank-auc", type=float, default=None,
                    help="ask a what-if: replay as if this sport's moneyline "
                         "had measured this AUC, instead of what it did. The "
                         "report marks a supplied figure so a hypothetical "
                         "cannot be read as a measurement.")
    args = ap.parse_args()

    conn = db.read_only(args.db)
    for sport in (SPORTS if args.all else [args.sport]):
        print(summarize(replay_potd(conn, sport, sharp=args.sharp,
                                    rank_auc=args.rank_auc)))
        print()


if __name__ == "__main__":
    main()
