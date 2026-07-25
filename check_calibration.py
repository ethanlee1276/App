#!/usr/bin/env python3
"""Is the fitted calibration actually reaching the betting engine?

    python3 check_calibration.py

A calibration that is fitted but not applied is invisible: the file exists, the
fit reports a correction, and the model keeps stating the same probabilities.
This prints the file the engine reads, the temperature it resolves per market,
and what that does to a sample probability — so "fitted" and "applied" can't be
confused for each other.
"""

from __future__ import annotations

from pathlib import Path

from engine import calibrate as cal

MARKETS = [("mlb", m) for m in ("total_bases", "hits", "home_runs", "strikeouts")]
MARKETS += [("nfl", m) for m in ("pass_yds", "rush_yds", "rec_yds", "receptions")]


def main() -> None:
    path = Path(cal.DEFAULT_PATH)
    print("Calibration file the ENGINE reads:")
    print(f"  {path}")
    print(f"  exists: {path.is_file()}")
    if not path.is_file():
        print("\nNo calibration fitted yet — the model runs uncorrected.")
        print("  Fit one with:  python3 calibrate.py --from-db data/history.db")
        return

    cal.reset_cache()
    raw = cal.load(path)
    if not raw:
        print("\n⚠️  The file exists but no usable temperatures were read from it.")
        print("    Re-fit with: python3 calibrate.py --from-db data/history.db")
        return

    print(f"\nTemperatures the engine resolves ({len(raw)} stored):")
    any_applied = False
    for sport, market in MARKETS:
        t = cal.temperature_for(sport, market, path)
        if t == 1.0:
            continue
        any_applied = True
        sample = 0.66
        corrected = cal.apply_temperature(sample, t)
        direction = "pulled toward 50%" if t > 1 else "sharpened"
        print(f"  {sport}:{market:14} T = {t:<5} → a stated {sample:.0%} becomes "
              f"{corrected:.0%}  ({direction})")

    if not any_applied:
        print("  (every market resolves to T = 1.0 — no correction is being applied)")
    else:
        print("\nThese corrections apply on the next build or backtest.")


if __name__ == "__main__":
    main()
