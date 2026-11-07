#!/usr/bin/env python3
"""Why is the home-run probability still wrong after calibration?

    python3 hr_diagnose.py

The fitted correction now pulls the right way (a stated 50% becomes 27%)
and the bet count collapsed from 229 to 24 — but the reliability bins
still say the model claims ~74% for "no home run" where reality is ~90%,
i.e. it still thinks a homer is ~26% likely against a true ~10%.

Working backwards through the fitted temperature, the RAW probability
going into calibration must be ~49%, which implies a projected ~0.68
home runs per game against a real rate near 0.13. If that's what this
prints, the bug is in the projection, not the calibration — and no
amount of temperature fitting can fix a mean that is five times too
large, it can only paper over it.
"""

from __future__ import annotations

import statistics as stats

from engine import db as _db
from engine.calibrate import apply_temperature, correction_for
from engine.mlb.betting import _poisson_over
from engine.mlb.models import MLBGameLog, MLBProp, HOME_RUNS
from engine.mlb.projection import build_mlb_projection
from engine.mlb.backtest import _neutral_game

LIMIT = 40
MIN_HISTORY = 6


def main() -> None:
    conn = _db.connect("data/history.db")
    entries = _db.entries_for_market(conn, "mlb", HOME_RUNS,
                                     min_games=MIN_HISTORY + 1)
    print(f"{len(entries)} players with home-run history\n")

    game = _neutral_game()
    temp, bias = correction_for("mlb", HOME_RUNS)
    print(f"Fitted correction in use: temperature {temp}, bias {bias:+}\n")

    raws, cals, means, hist_rates, actuals = [], [], [], [], []
    for e in entries[:400]:
        vals = e.get("values", [])
        for i in range(MIN_HISTORY, len(vals)):
            prior = vals[:i][::-1][:LIMIT]
            logs = [MLBGameLog(game=len(prior) - j, opponent="", value=float(v))
                    for j, v in enumerate(prior)]
            prop = MLBProp(player=e["name"], team="HOME", opponent="AWAY",
                           position="", market=HOME_RUNS, logs=logs,
                           career_avg=sum(vals[:i]) / i, vs_pitcher_avg=None,
                           lines=[], lineup_spot=e.get("spot", 3))
            proj = build_mlb_projection(prop, game)
            raw = _poisson_over(0.5, proj.mean)
            raws.append(raw)
            cals.append(apply_temperature(raw, temp, bias))
            means.append(proj.mean)
            hist_rates.append(sum(1 for v in prior if v > 0) / len(prior))
            actuals.append(1 if float(vals[i]) > 0 else 0)

    n = len(raws)
    if not n:
        print("No entries — is data/history.db populated?")
        return

    def line(label, xs):
        xs = sorted(xs)
        print(f"  {label:<34} mean {stats.fmean(xs):6.3f}   "
              f"median {xs[n // 2]:6.3f}   p10 {xs[n // 10]:6.3f}   "
              f"p90 {xs[n * 9 // 10]:6.3f}")

    print(f"Across {n:,} projected player-games:\n")
    line("projected HR per game (proj.mean)", means)
    line("RAW P(home run) from Poisson", raws)
    line("CALIBRATED P(home run)", cals)
    line("player's own recent HR rate", hist_rates)
    print(f"\n  {'ACTUAL rate a homer landed':<34} {stats.fmean(actuals):6.3f}")

    real = stats.fmean(actuals)
    print("\nVerdict:")
    for label, xs in (("projection", [1 - pow(2.718281828, -m) for m in means]),
                      ("raw Poisson", raws), ("after calibration", cals)):
        m = stats.fmean(xs)
        print(f"  {label:<18} says {m:.1%} vs reality {real:.1%}"
              f"   → {m / real if real else float('nan'):.1f}x too high"
              if m > real else
              f"  {label:<18} says {m:.1%} vs reality {real:.1%}")
    print("\nIf the RAW row is already several times reality, calibration is "
          "not the problem —\nthe home-run projection itself is, and that is "
          "where the fix belongs.")


if __name__ == "__main__":
    main()
