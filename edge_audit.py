#!/usr/bin/env python3
"""Is the edge bar hiding winners? Measure it, don't argue about it.

    python3 edge_audit.py                     # total_bases (the harvested market)
    python3 edge_audit.py --market hits

The board shows plenty of props that are "credible" but die at the edge
gate. This report answers whether that gate is earning its keep: it replays
the model walk-forward against every HARVESTED real book price (no
survivorship — near-misses included), bands every prop by how much net edge
the model claimed at that moment, and prints what a flat 1-unit bet on the
model's side actually returned in each band.

How to read it:

  * If the "below the bar" band loses money, the bar is protecting you —
    those props LOOK like value but the juice eats them, which is exactly
    what it was tuned against.
  * If that band is clearly profitable (positive ROI, z above ~2), the bar
    is too strict and should come down — with this table as the evidence.
  * The z-score is the standard "is this luck?" measure: wins versus the
    break-even the prices implied. Between -2 and +2, the honest reading
    is "not enough data to say".

Only markets with harvested closes can be audited (the auto-harvest stores
total_bases). Home-run props are measured separately by the long-shot
journal, which already tracks every board pick at a flat stake.
"""

from __future__ import annotations

import argparse
import math

from engine import db as _db
from engine.betting import favourite_surcharge, MARKET_SHRINK, MAX_CREDIBLE_EDGE
from engine.mlb.backtest import settled_props_from_logs
from engine.odds import american_to_decimal, american_to_prob

# Grading bar for the lowest tier (Lean): net edge past break-even, before
# the favourite surcharge — keep in sync with engine.betting.BASE_THRESHOLDS.
LEAN_NET = 0.003


def _bands(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Band by net edge relative to the bar each prop actually faced."""
    def under(x):
        return 0 <= x["net"] < x["need"]
    ceiling = MARKET_SHRINK * MAX_CREDIBLE_EDGE
    return [
        ("model says price beats us (net < 0)",
         [x for x in rows if x["net"] < 0]),
        ("BELOW THE BAR — positive net, under the grading bar",
         [x for x in rows if under(x)]),
        ("cleared the bar by < 1pt",
         [x for x in rows if x["need"] <= x["net"] < x["need"] + 0.01]),
        ("cleared the bar by 1-3pt",
         [x for x in rows if x["need"] + 0.01 <= x["net"] < x["need"] + 0.03]),
        (f"3pt+ past the bar (edges above {ceiling:.0%} grade Pass as bad data)",
         [x for x in rows if x["net"] >= x["need"] + 0.03]),
    ]


def _agg(rows: list[dict]) -> dict | None:
    graded = [x for x in rows if x["won"] is not None]
    if not graded:
        return None
    wins = sum(1 for x in graded if x["won"])
    exp = sum(x["be"] for x in graded)
    var = sum(x["be"] * (1 - x["be"]) for x in graded)
    net_units = sum((american_to_decimal(x["odds"]) - 1.0) if x["won"] else -1.0
                    for x in graded)
    return {
        "n": len(graded), "wins": wins,
        "hit": wins / len(graded),
        "be": exp / len(graded),
        "roi": net_units / len(graded),
        "units": net_units,
        "z": (wins - exp) / math.sqrt(var) if var > 0 else 0.0,
    }


def _print_table(title: str, groups: list[tuple[str, list[dict]]]) -> None:
    print(f"\n{title}")
    print(f"  {'':<52} {'bets':>5}  {'hit':>6}  {'b/e':>6}  "
          f"{'ROI':>7}  {'units':>7}  {'z':>5}")
    for label, rows in groups:
        a = _agg(rows)
        if a is None:
            print(f"  {label:<52} {'—':>5}")
            continue
        print(f"  {label:<52} {a['n']:>5}  {a['hit']:>6.1%}  {a['be']:>6.1%}  "
              f"{a['roi']:>+7.1%}  {a['units']:>+7.1f}  {a['z']:>+5.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--market", default="total_bases")
    ap.add_argument("--min-history", type=int, default=8)
    args = ap.parse_args()

    conn = _db.connect()
    entries = _db.entries_for_market(conn, "mlb", args.market,
                                     min_games=args.min_history + 1)
    real = _db.closing_odds_by_date(conn, "mlb", args.market)
    if not entries or not real:
        print(f"Nothing to audit: {len(entries)} players with logs, "
              f"{len(real)} harvested prices for {args.market}.")
        print("The audit needs both — run the launcher (results ingest daily) "
              "and harvest closes (harvest_odds.py) first.")
        return

    print(f"Replaying the model against {len(real):,} harvested "
          f"{args.market} prices ({len(entries)} players)…")
    settled, used = settled_props_from_logs(
        entries, args.market, min_history=args.min_history, real_lines=real)

    rows = []
    for s in settled:
        if s.basis != "book":
            continue                    # only real prices answer this question
        be = american_to_prob(s.odds)
        rows.append({
            "net": s.hit_prob - be,
            "need": LEAN_NET + favourite_surcharge(s.odds),
            "be": be, "odds": s.odds,
            "won": s.outcome, "grade": s.grade or "Pass",
        })
    if not rows:
        print("No walk-forward game lined up with a harvested price — "
              "the odds and results stores don't overlap yet.")
        return

    print(f"{len(rows):,} prop-games priced at a real book number "
          f"(every one included — no survivorship).")

    _print_table("By net edge vs the grading bar (flat 1u on the model's side):",
                 _bands(rows))

    grades = {}
    for x in rows:
        grades.setdefault(x["grade"], []).append(x)
    order = ["Strong Play", "Play", "Lean", "Pass"]
    _print_table("By the grade the engine assigned at that moment:",
                 [(g, grades[g]) for g in order if g in grades])

    below = _agg([x for x in rows if 0 <= x["net"] < x["need"]])
    if below:
        if below["z"] >= 2 and below["roi"] > 0:
            verdict = ("the below-the-bar band IS profitable — the bar looks "
                       "too strict; worth lowering, this table is the evidence")
        elif below["z"] <= -2:
            verdict = ("the below-the-bar band loses more than chance — the "
                       "bar is protecting the record, leave it alone")
        else:
            verdict = (f"inconclusive at {below['n']} bets (z {below['z']:+.1f})"
                       " — the honest answer is 'not enough data yet'; "
                       "the harvest grows it daily")
        print(f"\nVerdict on the props the bar hides: {verdict}.")


if __name__ == "__main__":
    main()
