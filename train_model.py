#!/usr/bin/env python3
"""Train the learned multiplier model on historical nflverse weeks.

    python3 train_model.py 2024 --weeks 2-13 --out data/models/multiplier_2024.json
    python3 train_model.py 2024 --weeks 2-13 --eval-weeks 14-17   # train + compare

Needs weekly stats for the season (release-gated → drop a CSV at
data/cache/player_stats_<season>.csv; see the README). Training is walk-forward
and leakage-free. With --eval-weeks it runs the backtest on held-out weeks with
the hand-tuned rules vs the learned model so you can see the effect on
calibration (ECE) and ROI before trusting it.
"""

from __future__ import annotations

import argparse
import sys

from engine.ml.train import train
from engine.backtest import backtest_from_stats
from engine.sources.fetch import DataUnavailable
from engine.rules import RuleConfig
from backtest import parse_weeks


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the learned multiplier model.")
    ap.add_argument("season", type=int)
    ap.add_argument("--weeks", default="2-13", help="training weeks, e.g. 2-13")
    ap.add_argument("--l2", type=float, default=1.0, help="ridge regularization strength")
    ap.add_argument("--out", default=None, help="where to save the model JSON")
    ap.add_argument("--eval-weeks", default=None,
                    help="held-out weeks to backtest rules vs learned (e.g. 14-17)")
    args = ap.parse_args()

    weeks = parse_weeks(args.weeks)
    try:
        model, report = train(args.season, weeks, l2=args.l2)
    except DataUnavailable as exc:
        print("⚠️  Training needs weekly stats.\n")
        print(exc)
        sys.exit(2)

    print(report.summary())

    out = args.out or f"data/models/multiplier_{args.season}.json"
    model.save(out)
    print(f"\nSaved model → {out}")

    if args.eval_weeks:
        eval_weeks = parse_weeks(args.eval_weeks)
        cfg = RuleConfig()
        print(f"\nHeld-out backtest on weeks {eval_weeks[0]}–{eval_weeks[-1]}:\n")
        rules = backtest_from_stats(args.season, eval_weeks, cfg, model=None)
        learned = backtest_from_stats(args.season, eval_weeks, cfg, model=model)
        print("── Hand-tuned rules ──")
        print(rules.summary())
        print("\n── Learned model ──")
        print(learned.summary())
        d_ece = learned.ece - rules.ece
        d_roi = learned.roi - rules.roi
        print(f"\nΔ ECE {d_ece:+.3f} (lower is better)   Δ ROI {d_roi:+.1%}")


if __name__ == "__main__":
    main()
