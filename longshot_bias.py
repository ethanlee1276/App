#!/usr/bin/env python3
"""Do the books overprice longshots? The oldest edge in gambling, tested.

    python3 longshot_bias.py

The favourite-longshot bias is the best-documented inefficiency in
betting markets: bettors overpay for big payouts, so books shade
longshot prices and the short side of the same market becomes cheap.
If it holds in baseball props, the play needs no forecast whatsoever —
you simply avoid plus-money overs and prefer the unders they imply.

This joins harvested prices straight to what actually happened. No
projection, no calibration, no model: for every book quote we can settle,
bucket by the price's implied probability and compare it with the rate
that side actually hit.

Reading it:

  * **implied > actual** in the longshot buckets, and **implied ≈ actual**
    among favourites → the classic bias, and the money is on the short
    side of longshot markets.
  * **implied ≈ actual everywhere** → the bias is arbitraged away in this
    market and there is nothing here.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from engine import db as _db
from engine.odds import american_to_prob
from engine.sources.oddsapi import normalize_name

# Price bands, by the OVER's implied probability.
BANDS = [(0.00, 0.10, "huge longshot  (+900 and out)"),
         (0.10, 0.20, "longshot       (+400 to +900)"),
         (0.20, 0.35, "big underdog   (+185 to +400)"),
         (0.35, 0.50, "underdog       (+100 to +185)"),
         (0.50, 0.65, "favourite      (-100 to -185)"),
         (0.65, 1.01, "heavy favourite(-185 and shorter)")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--sport", default="mlb")
    args = ap.parse_args()
    conn = _db.connect(args.db)

    # What actually happened: (player, market, date) -> value
    actuals: dict[tuple, float] = {}
    for r in conn.execute(
            "SELECT player, market, period, value FROM player_game_logs "
            "WHERE sport=?", (args.sport,)):
        actuals[(normalize_name(r["player"]), r["market"], r["period"])] = \
            float(r["value"])
    print(f"{len(actuals):,} settled player-game results loaded")

    rows = conn.execute(
        "SELECT taken_at, player, market, line, over_odds, book "
        "FROM odds_history WHERE sport=? AND over_odds IS NOT NULL "
        "AND over_odds != 0", (args.sport,)).fetchall()

    buckets: dict[str, list] = defaultdict(list)
    matched = 0
    for r in rows:
        date = (r["taken_at"] or "")[:10]
        key = (normalize_name(r["player"] or ""), r["market"], date)
        if key not in actuals:
            continue
        line = float(r["line"])
        actual = actuals[key]
        if actual == line:
            continue                          # push
        matched += 1
        implied = american_to_prob(int(r["over_odds"]))
        hit = 1 if actual > line else 0
        for lo, hi, label in BANDS:
            if lo <= implied < hi:
                buckets[label].append((implied, hit))
                break

    print(f"{len(rows):,} quotes · {matched:,} joined to a real outcome\n")
    if not matched:
        print("No quotes could be matched to results — the harvested dates "
              "and the ingested game logs don't overlap.")
        return

    hdr = f"{'price band':<32}{'n':>8}{'implied':>10}{'actual':>10}{'gap':>9}{'over ROI':>10}"
    print(hdr)
    print("-" * len(hdr))
    for _, _, label in BANDS:
        rowsb = buckets.get(label) or []
        if len(rowsb) < 30:
            continue
        n = len(rowsb)
        imp = sum(p for p, _ in rowsb) / n
        act = sum(h for _, h in rowsb) / n
        # ROI from backing the OVER at that price, flat stakes.
        roi = sum((1 / p - 1) if h else -1 for p, h in rowsb) / n
        print(f"{label:<32}{n:>8,}{imp:>9.1%}{act:>10.1%}"
              f"{(act - imp) * 100:>+8.1f}{roi:>+9.1%}")

    print("\nGap = actual minus implied. NEGATIVE means that side hit LESS "
          "often than\nits price claimed — i.e. it was overpriced, and the "
          "other side was the value.")
    # The verdict must be read in RELATIVE terms, not absolute points.
    # Every band comes back negative because every quoted price carries
    # the book's margin — that is the vig, not a bias. The bias shows up
    # as the margin being far heavier on longshots than on favourites,
    # which is exactly what flat-stake ROI measures.
    def band_roi(pred):
        rows = [x for lo, hi, lb in BANDS if pred(lo, hi)
                for x in (buckets.get(lb) or [])]
        if len(rows) < 30:
            return None, 0
        return (sum((1 / p - 1) if h else -1 for p, h in rows) / len(rows),
                len(rows))

    lroi, ln = band_roi(lambda lo, hi: hi <= 0.35)
    froi, fn = band_roi(lambda lo, hi: lo >= 0.5)
    if lroi is not None and froi is not None:
        print(f"\n  backing longshot overs (under 35%): {lroi:+.1%} "
              f"(n={ln:,})")
        print(f"  backing favourite overs (over 50%): {froi:+.1%} "
              f"(n={fn:,})")
        print(f"  longshots cost {lroi / froi:.1f}x as much per unit staked")
        if lroi < froi - 0.03:
            print("\n  → The favourite-longshot bias IS present. Both sides lose"
                  " to the vig,\n    but longshots lose far more: the books "
                  "shade big payouts heavily.\n    Never back plus-money overs; "
                  "the value is on the other side of\n    those markets.")
        else:
            print("\n  → No clear favourite-longshot bias: the cost of backing "
                  "the over is\n    about the same at every price, so there is "
                  "no free side to take.")


if __name__ == "__main__":
    main()
