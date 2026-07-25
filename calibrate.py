#!/usr/bin/env python3
"""Fit the model's probability calibration from real settled outcomes.

    python3 calibrate.py --from-db data/history.db                 # all markets
    python3 calibrate.py --from-db data/history.db --market hits   # just one
    python3 calibrate.py --show                                    # what's fitted now

Calibration is the part of "does this model have an edge" that can be checked
with **outcomes alone** — it needs no historical sportsbook prices. It asks: when
the model says 60%, does it actually hit 60%? If not, every edge it reports is
wrong by that gap and the stakes are wrong with it.

This walks the history DB forward (projecting each game only from earlier
games), compares predictions to what really happened, fits a temperature
correction per market, and saves it to data/models/calibration.json. The betting
engine picks it up automatically on the next run.

Ingest real history first, e.g.:
    python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01
"""

from __future__ import annotations

import argparse

from engine import calibrate as cal
from engine import db as _db
from engine.mlb.backtest import backtest_from_logs
from engine.mlb.models import MARKET_LABELS

MLB_MARKETS = ["total_bases", "hits", "home_runs", "strikeouts"]


def fit_market(conn, market: str, min_history: int, min_samples: int):
    entries = _db.entries_for_market(conn, "mlb", market, min_games=min_history + 2)
    if not entries:
        return None, "no player history in the DB for this market"
    report = backtest_from_logs(entries, market, min_history=min_history)
    if not report.pairs:
        return None, "no settled predictions (need more games per player)"
    c = cal.fit(report.pairs, sport="mlb", market=market, min_samples=min_samples)
    return (c, report), None


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit probability calibration from real outcomes.")
    ap.add_argument("--from-db", dest="db", default=str(_db.DEFAULT_DB),
                    help="history DB to learn from (default: data/history.db)")
    ap.add_argument("--market", default=None, help="fit a single market only")
    ap.add_argument("--min-history", type=int, default=8,
                    help="games of history before a player is projected")
    ap.add_argument("--min-samples", type=int, default=200,
                    help="settled props required before a correction is trusted")
    ap.add_argument("--show", action="store_true", help="print the current calibration and exit")
    args = ap.parse_args()

    if args.show:
        current = cal.load()
        if not current:
            print("No calibration fitted yet — the model runs uncorrected.")
        else:
            print("Fitted calibration:")
            for key, t in sorted(current.items()):
                print(f"  {key:28} T = {t}")
        return

    conn = _db.connect(args.db)
    markets = [args.market] if args.market else MLB_MARKETS

    fitted: dict[str, cal.Calibration] = {}
    print(f"Fitting calibration from {args.db}\n")
    for market in markets:
        label = MARKET_LABELS.get(market, market)
        got, err = fit_market(conn, market, args.min_history, args.min_samples)
        if err:
            print(f"  {label:16} skipped — {err}")
            continue
        c, report = got
        print(f"  {label:16} {c.samples:>5} settled   "
              f"Brier {c.brier_before:.4f} → {c.brier_after:.4f}   "
              f"T = {c.temperature}  bias = {c.intercept:+.2f}")
        if c.samples < args.min_samples:
            print(f"  {'':16} (under {args.min_samples} samples — left uncorrected)")
        else:
            print(f"  {'':16} {c.verdict}")
            if c.bias_note:
                print(f"  {'':16} {c.bias_note}")
            if c.at_boundary:
                print(f"  {'':16} ⚠️  fit hit the edge of the search range — treat "
                      f"this market's model as unreliable, not merely miscalibrated")
        fitted[f"mlb:{market}"] = c

    if not fitted:
        print("\nNothing fitted. Ingest history first, e.g.:\n"
              "  python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01")
        return

    path = cal.save(fitted)
    cal.reset_cache()
    print(f"\nWrote {path}")
    print("The betting engine will apply this on the next build.")


if __name__ == "__main__":
    main()
