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
    ap.add_argument("--from-db", default=None,
                    help="read entries from the history DB (data/history.db) instead")
    ap.add_argument("--real-lines", action="store_true",
                    help="Price against harvested historical book lines "
                         "(see harvest_odds.py) instead of a naive baseline.")
    ap.add_argument("--min-history", type=int, default=6)
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--model", default=None, help="Path to a trained MLB model JSON.")
    args = ap.parse_args()

    if args.from_db:
        from engine import db as _db
        conn = _db.connect(args.from_db)
        real_lines = {}
        if args.real_lines:
            for (player, _m), q in _db.closing_odds_for(conn, "mlb", args.market).items():
                real_lines[(player, str(q["taken_at"])[:10])] = q
            print(f"Using {len(real_lines)} harvested book line(s).")
        entries = _db.entries_for_market(conn, "mlb", args.market,
                                         min_games=args.min_history + 1)
        source = "history DB"
    elif args.synthetic:
        entries = synthetic_entries(args.market)
        source = "synthetic season"
    else:
        entries = entries_from_slate(args.market)
        source = "sample slate"
    if not entries:
        print(f"No {args.market} entries found ({source}) — try --synthetic, a "
              f"different --market, or ingest data first (python3 ingest.py).")
        return

    model = None
    if args.model:
        from engine.ml.model import MultiplierModel
        model = MultiplierModel.load(args.model)

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    report = backtest_from_logs(entries, args.market,
                                min_history=args.min_history, config=config, model=model,
                                real_lines=locals().get("real_lines"))

    print(f"\nMLB backtest · {MARKET_LABELS[args.market]} · {source}")
    print(report.summary())


if __name__ == "__main__":
    main()
