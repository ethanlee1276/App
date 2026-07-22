#!/usr/bin/env python3
"""Backtest the MLB model — walk-forward calibration on game logs.

    python3 mlb_backtest.py                       # sample slate's real logs
    python3 mlb_backtest.py --synthetic           # a larger synthetic season
    python3 mlb_backtest.py --market total_bases --min-history 6

Reports projection MAE/RMSE, probability calibration (reliability bins, Brier,
ECE) and betting ROI on the recommended bets. For a real season, feed logs from
the MLB Stats API (engine/mlb/sources/statslogs) into
engine.mlb.backtest.backtest_from_logs — the same function this CLI calls.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from engine.mlb.backtest import backtest_from_logs
from engine.mlb.models import MARKET_LABELS
from engine.rules import RuleConfig

ROOT = Path(__file__).parent
SLATE = ROOT / "data" / "mlb_sample_slate.json"


def entries_from_slate(market: str) -> list[dict]:
    data = json.loads(SLATE.read_text())
    entries = []
    for prop in data["props"]:
        if prop["market"] != market:
            continue
        # slate logs are most-recent-first with a 'game' index; chronological asc
        logs = sorted(prop["logs"], key=lambda g: g["game"])
        entries.append({"name": prop["player"],
                        "values": [g["value"] for g in logs],
                        "spot": prop.get("lineup_spot", 3)})
    return entries


def synthetic_entries(market: str, n_players: int = 40, n_games: int = 60,
                      seed: int = 7) -> list[dict]:
    """A synthetic season with a deliberately overconfident-free generator, so
    a well-calibrated model lands near the diagonal."""
    rng = random.Random(seed)
    means = {"total_bases": 1.6, "hits": 1.0, "home_runs": 0.28, "strikeouts": 6.2}
    mu0 = means.get(market, 1.5)
    entries = []
    for p in range(n_players):
        skill = rng.uniform(0.7, 1.4)
        lam = mu0 * skill
        vals = []
        for _ in range(n_games):
            if market == "home_runs":
                vals.append(1 if rng.random() < min(0.6, lam) else 0)
            elif market == "strikeouts":
                vals.append(max(0, round(rng.gauss(lam, lam * 0.35))))
            else:
                # bounded count-ish outcome
                vals.append(max(0, round(rng.gauss(lam, lam * 0.85))))
        entries.append({"name": f"Player {p+1}", "values": vals, "spot": 3})
    return entries


def main() -> None:
    ap = argparse.ArgumentParser(description="MLB walk-forward backtest.")
    ap.add_argument("--market", default="total_bases",
                    choices=list(MARKET_LABELS))
    ap.add_argument("--synthetic", action="store_true",
                    help="use a generated season instead of the sample slate")
    ap.add_argument("--min-history", type=int, default=6)
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    args = ap.parse_args()

    entries = (synthetic_entries(args.market) if args.synthetic
               else entries_from_slate(args.market))
    if not entries:
        print(f"No {args.market} logs found in the sample slate — try --synthetic "
              f"or a different --market.")
        return

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    report = backtest_from_logs(entries, args.market,
                                min_history=args.min_history, config=config)

    src = "synthetic season" if args.synthetic else "sample slate"
    print(f"\nMLB backtest · {MARKET_LABELS[args.market]} · {src}")
    print(report.summary())


if __name__ == "__main__":
    main()
