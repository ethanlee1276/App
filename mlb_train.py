#!/usr/bin/env python3
"""Train the MLB learned multiplier model.

    python3 mlb_train.py --synthetic --out data/models/mlb_multiplier.json

Real training assembles examples from the historical database (each past game's
park / weather / pitcher / Statcast context + the player's baseline + actual) —
the historical-database phase. This CLI demonstrates the learner end to end on a
**synthetic** season with injected relationships, printing the learned
coefficients so you can confirm it recovers the right signs (park HR and the
xSLG gap lift total bases; opponent K rate and CSW% lift strikeouts). Feed real
rows to engine.mlb.ml.build_examples / fit for a production model.
"""

from __future__ import annotations

import argparse
import math
import random

from engine.mlb.ml import build_examples, fit, report_summary, extract_features, vectorize, FEATURE_ORDER
from engine.mlb.models import (
    MLBProp, MLBGame, MLBWeather, Pitcher, StatcastProfile,
    TOTAL_BASES, STRIKEOUTS,
)
from engine.mlb.parks import PARKS

# Injected log-space coefficients (what a good model should roughly recover).
TRUE = {
    TOTAL_BASES: {"park_hr": 0.6, "wind": 0.03, "platoon": 0.05,
                  "pit_slg": 0.5, "lineup": 1.0, "xslg_gap": 0.8, "barrel": 0.6},
    STRIKEOUTS: {"park_k": 0.4, "opp_k": 1.2, "csw": 1.5},
}


def _synth_rows(market: str, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    park_keys = list(PARKS)
    rows = []
    for _ in range(n):
        wdir = rng.choice(["out", "in", "cross"])
        game = MLBGame(
            home="H", away="A", park=rng.choice(park_keys),
            weather=MLBWeather(temp_f=rng.uniform(55, 92),
                               wind_mph=rng.uniform(4, 20), wind_dir_rel=wdir),
            pitchers={"A": Pitcher("SP", rng.choice("LR"),
                                   slg_allowed_vs_l=rng.uniform(0.33, 0.55),
                                   slg_allowed_vs_r=rng.uniform(0.33, 0.55),
                                   k_rate=rng.uniform(0.16, 0.30))},
            bullpen_rank={"A": rng.randint(1, 30)},
            team_k_rate={"A": rng.uniform(0.18, 0.28)},
        )
        if market == TOTAL_BASES:
            sc = StatcastProfile(xslg=rng.uniform(0.35, 0.62),
                                 slg=rng.uniform(0.35, 0.62),
                                 barrel_pct=rng.uniform(0.03, 0.18))
            prop = MLBProp("H", "H", "A", "1B", market, [], 1.8, None, [],
                           bats=rng.choice("LR"), lineup_spot=rng.randint(1, 9),
                           statcast=sc)
            baseline = 1.8
        else:
            sc = StatcastProfile(csw_pct=rng.uniform(0.24, 0.34))
            prop = MLBProp("SP", "H", "A", "SP", market, [], 6.5, None, [],
                           throws="R", lineup_spot=1, statcast=sc)
            baseline = 6.5

        feat = extract_features(prop, game)
        y = sum(TRUE[market].get(k, 0.0) * feat[k] for k in FEATURE_ORDER)
        y += rng.gauss(0, 0.05)                       # small noise
        actual = baseline * math.exp(y)
        rows.append({"prop": prop, "game": game, "baseline": baseline, "actual": actual})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the MLB learned multiplier model.")
    ap.add_argument("--synthetic", action="store_true",
                    help="train on a synthetic season (demo)")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--l2", type=float, default=0.3)
    ap.add_argument("--out", default="data/models/mlb_multiplier.json")
    args = ap.parse_args()

    if not args.synthetic:
        print("Real training needs historical rows (park/weather/pitcher/Statcast "
              "+ baseline + actual per past game) — the historical-database phase.\n"
              "Run with --synthetic to demonstrate the learner and save a model.")
        return

    rows = _synth_rows(TOTAL_BASES, args.n, 7) + _synth_rows(STRIKEOUTS, args.n, 11)
    data = build_examples(rows)
    model, report = fit(data, l2=args.l2, min_examples=30)
    print(report_summary(report))
    model.save(args.out)
    print(f"\nSaved model → {args.out}")
    print("(synthetic demo — the learner recovered the injected signal signs; "
          "train on real history for a production model)")


if __name__ == "__main__":
    main()
