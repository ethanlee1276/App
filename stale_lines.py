#!/usr/bin/env python3
"""Speed edge: which books lag the market, and by how much?

    python3 stale_lines.py

The prop model lost to the closing line, so out-forecasting the market
is off the table. Staleness is the opposite kind of bet: it needs no
view on the player at all. When most books have moved to a new number
and one has not, the laggard is offering a price the market has already
disagreed with — and you take it before it catches up.

Measured from the harvested per-book time series:

  * **lag** — at each moment, every book's implied probability against
    the consensus of the others. A book persistently on one side of
    consensus is soft, not slow; a book that is far off and then
    CONVERGES was stale, and that gap was takeable.
  * **convergence** — of the moments where a book sat >=1 point off
    consensus, how often did it later move toward consensus rather than
    the market moving to it? That ratio is the whole question: if the
    laggard is usually right, it is not stale, it is early.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from engine import db as _db
from engine.odds import american_to_prob

MIN_BOOKS = 3          # consensus needs a crowd
GAP_PT = 1.0           # a gap worth calling stale, in probability points


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--sport", default="mlb")
    args = ap.parse_args()

    conn = _db.connect(args.db)
    rows = conn.execute(
        "SELECT taken_at, player, market, book, line, over_odds "
        "FROM odds_history WHERE sport=? AND over_odds IS NOT NULL "
        "AND over_odds != 0 ORDER BY taken_at", (args.sport,)).fetchall()
    if not rows:
        print(f"No harvested odds for {args.sport}.")
        return

    # (player, market, line) -> ordered [(stamp, {book: implied})]
    series: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        book = (r["book"] or "").strip()
        if book.lower() in ("", "best", "proxy", "consensus"):
            continue
        key = (r["player"], r["market"], r["line"])
        stamp = (r["taken_at"] or "")[:13]
        series[key].setdefault(stamp, {})[book] = american_to_prob(
            int(r["over_odds"]))

    lag_sum: dict[str, float] = defaultdict(float)
    lag_n: dict[str, int] = defaultdict(int)
    stale_events = 0
    converged = 0
    market_moved_to_them = 0
    checked = 0

    for key, snaps in series.items():
        stamps = sorted(snaps)
        for i, stamp in enumerate(stamps):
            quotes = snaps[stamp]
            if len(quotes) < MIN_BOOKS:
                continue
            for book, p in quotes.items():
                others = [v for b, v in quotes.items() if b != book]
                consensus = sum(others) / len(others)
                gap = (p - consensus) * 100      # +ve = book prices it higher
                lag_sum[book] += gap
                lag_n[book] += 1
                # A gap only matters if it later resolves. Look at the next
                # snapshot: did the laggard move toward consensus (it was
                # stale) or did everyone else move toward it (it was early)?
                if abs(gap) >= GAP_PT and i + 1 < len(stamps):
                    nxt = snaps[stamps[i + 1]]
                    if book not in nxt or len(nxt) < MIN_BOOKS:
                        continue
                    checked += 1
                    stale_events += 1
                    new_gap = (nxt[book] - sum(
                        v for b, v in nxt.items() if b != book)
                        / max(1, len(nxt) - 1)) * 100
                    # Binary and exhaustive: either the gap shrank (the
                    # laggard came to the field — it was stale) or it grew
                    # (the field left, or the book doubled down — it was
                    # early). Requiring a HALVING to count as convergence
                    # dumped every partial catch-up into a third bucket
                    # and then divided by it, which understated the signal.
                    if abs(new_gap) < abs(gap):
                        converged += 1
                    elif abs(new_gap) > abs(gap):
                        market_moved_to_them += 1
                    else:
                        checked -= 1          # unchanged: no information

    print(f"\n{len(rows):,} quotes · {len(series):,} prop lines tracked over time\n")
    print("HOW EACH BOOK PRICES vs THE CONSENSUS OF THE OTHERS")
    print("  (positive = prices the over HIGHER than the field, i.e. a worse "
          "price to back)\n")
    ranked = sorted(((lag_sum[b] / lag_n[b], b, lag_n[b])
                     for b in lag_n if lag_n[b] >= 50), key=lambda t: t[0])
    for avg, book, n in ranked:
        side = "cheaper than the field" if avg < 0 else "richer than the field"
        print(f"  {book:<16} {avg:+6.2f} pts   {side:<24} (n={n:,})")

    if checked:
        print(f"\nWHEN A BOOK IS {GAP_PT:.0f}+ POINTS OFF CONSENSUS "
              f"({stale_events:,} occurrences)")
        resolved = converged + market_moved_to_them
        print(f"  (of {resolved:,} that actually resolved)")
        print(f"  it moved back toward the field   {converged:,} "
              f"({converged / max(1, resolved):.1%})  ← was stale, gap was takeable")
        print(f"  the field moved toward IT        {market_moved_to_them:,} "
              f"({market_moved_to_them / max(1, resolved):.1%})  ← it was early, not slow")
        edge = converged / resolved if resolved else 0.0
        print("\n  A stale-line strategy needs the first number to dominate.")
        import math as _m
        if resolved:
            z = (converged - resolved / 2) / _m.sqrt(resolved * 0.25)
            print(f"\n  z = {z:.1f} against a coin flip"
                  f"{'  — not chance' if abs(z) > 3 else ''}")
        if edge > 0.55:
            print("  It does — laggards mostly catch up, so the gap was real "
                  "and takeable.")
        else:
            print("  It does not. Off-consensus books are about as often right "
                  "as wrong,\n  so a gap by itself is not a signal — you would "
                  "be betting noise.")
    else:
        print("\nNot enough repeated snapshots of the same line to measure "
              "convergence.\n  Staleness needs the SAME prop sampled several "
              "times before first pitch —\n  the harvester currently takes one "
              "closing snapshot per prop.")


if __name__ == "__main__":
    main()
