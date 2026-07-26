#!/usr/bin/env python3
"""What is line shopping actually worth — and how often does the Scanner fire?

    python3 shopping_value.py

Both questions come off the same harvested rows, and both matter more
than the prop model does: shopping and structural plays are *mechanical*
edges. They need no forecast, so they can't be wrong about the future —
which is exactly the failure mode the backtest just exposed everywhere
else.

Measured here, per (player, market, line, day) where two or more books
quoted the same number:

  * **shopping gain** — implied probability at the BEST price vs the
    average book. That gap is break-even you don't have to earn: at
    −110 you need 52.38%, at −105 only 51.22%, so a 1.16-point gain is
    1.16 points of edge handed over for free.
  * **shopped hold** — best over + best under across all books, against
    the hold inside a single book. When the shopped hold goes at or
    below zero that is an arbitrage; just above it is a low-hold pair.
  * **who wins** — how often each book posts the best number, which is
    the practical answer to "where should I actually have accounts".
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from engine import db as _db
from engine.odds import american_to_prob


def _rows(conn, sport: str):
    return conn.execute(
        "SELECT taken_at, player, market, book, line, over_odds, under_odds "
        "FROM odds_history WHERE sport=? AND over_odds IS NOT NULL",
        (sport,)).fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--sport", default="mlb")
    args = ap.parse_args()

    conn = _db.connect(args.db)
    rows = _rows(conn, args.sport)
    if not rows:
        print(f"No harvested odds rows for {args.sport} in {args.db}.")
        return

    # Prices are only shoppable if you could have taken them AT THE SAME
    # TIME. Grouping by day instead of by moment compares a 10am quote at
    # one book against a 7pm quote at another and calls the gap an edge —
    # it is line movement, and it manufactured an 11.7% "arbitrage" rate
    # (reality is well under 1%) plus a 38-point "shopping gain".
    #
    # Quotes are bucketed to the harvest timestamp, truncated to the hour
    # so that snapshots written a few seconds apart still pair up.
    groups: dict[tuple, list] = defaultdict(list)
    skipped_books = 0
    for r in rows:
        book = (r["book"] or "").strip().lower()
        # "best" and "proxy" are pipeline placeholders, not sportsbooks.
        if book in ("", "best", "proxy", "consensus"):
            skipped_books += 1
            continue
        stamp = (r["taken_at"] or "")[:13]        # YYYY-MM-DDTHH
        groups[(stamp, r["player"], r["market"], r["line"])].append(r)
    if skipped_books:
        print(f"  (ignored {skipped_books:,} rows from placeholder "
              f"'best'/'proxy' entries — not real books)")

    multi = {k: v for k, v in groups.items() if len({x["book"] for x in v}) > 1}
    print(f"\n{len(rows):,} harvested quotes · {len(groups):,} prop-moments · "
          f"{len(multi):,} with 2+ books quoting the same number "
          f"at the same time\n")
    if not multi:
        print("Not enough multi-book coverage to measure shopping value.")
        return

    gains, holds_shopped, holds_single, books_won = [], [], [], defaultdict(int)
    arbs = lowholds = 0
    for key, quotes in multi.items():
        overs = [(int(q["over_odds"]), q["book"]) for q in quotes
                 if q["over_odds"] is not None]
        unders = [(int(q["under_odds"]), q["book"]) for q in quotes
                  if q["under_odds"] is not None]
        if len(overs) < 2:
            continue
        # Best price = highest American odds = lowest implied probability.
        best_over, best_book = max(overs, key=lambda t: _payout(t[0]))
        avg_imp = sum(american_to_prob(o) for o, _ in overs) / len(overs)
        gains.append((avg_imp - american_to_prob(best_over)) * 100)
        books_won[best_book] += 1

        if unders:
            best_under, _ = max(unders, key=lambda t: _payout(t[0]))
            shopped = american_to_prob(best_over) + american_to_prob(best_under)
            holds_shopped.append((shopped - 1.0) * 100)
            # Best hold available inside any single book.
            per_book = {}
            for q in quotes:
                if q["over_odds"] is not None and q["under_odds"] is not None:
                    per_book[q["book"]] = (american_to_prob(int(q["over_odds"]))
                                           + american_to_prob(int(q["under_odds"])))
            if per_book:
                holds_single.append((min(per_book.values()) - 1.0) * 100)
            if shopped < 1.0:
                arbs += 1
            elif shopped <= 1.02:
                lowholds += 1

    if not gains:
        print("No two-sided multi-book quotes found.")
        return
    gains.sort()
    n = len(gains)
    mean_gain = sum(gains) / n
    print("LINE SHOPPING — taking the best price vs the average book")
    print(f"  {n:,} shoppable props")
    print(f"  average gain   {mean_gain:+.2f} points of implied probability")
    print(f"  median         {gains[n // 2]:+.2f}   p90 {gains[n * 9 // 10]:+.2f}"
          f"   best {gains[-1]:+.2f}")
    print(f"  → roughly {mean_gain:.2f} points of break-even you never have to "
          f"earn.\n    On a −110 bet that is {mean_gain / 2.38 * 100:.0f}% of "
          f"the entire house edge, for free.")

    if holds_shopped:
        hs = sum(holds_shopped) / len(holds_shopped)
        print("\nSTRUCTURAL PLAYS — combining the best over and best under")
        print(f"  hold inside the best single book   {sum(holds_single) / max(1, len(holds_single)):+.2f}%")
        print(f"  hold when shopped across books     {hs:+.2f}%")
        print(f"  arbitrage pairs (hold < 0)         {arbs:,} "
              f"({arbs / len(holds_shopped):.2%} of pairs)")
        print(f"  low-hold pairs (0-2%)              {lowholds:,} "
              f"({lowholds / len(holds_shopped):.2%})")

    print("\nWHERE THE BEST NUMBER LIVES")
    total = sum(books_won.values())
    for book, wins in sorted(books_won.items(), key=lambda kv: -kv[1])[:10]:
        bar = "█" * max(1, round(40 * wins / total))
        print(f"  {book:<18} {wins / total:6.1%}  {bar}")
    print("\nA book that almost never posts the best number is an account you "
          "don't need;\none that often does is where the free edge lives.")


def _payout(odds: int) -> float:
    """Decimal payout — higher is a better price for the bettor."""
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / abs(odds))


if __name__ == "__main__":
    main()
