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
    ap.add_argument("--show-arbs", type=int, default=0,
                    help="dump N raw arb pairs — the only way to tell a\n                          real opportunity from a data defect")
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
    arbs = lowholds = same_book_bad = 0
    arb_sizes: list[float] = []
    arb_rows: list = []
    arb_books: dict[str, int] = defaultdict(int)
    for key, quotes in multi.items():
        # 0 is the parser's "this book doesn't offer that side" sentinel
        # (home-run props are over-only). Treating it as a price makes
        # american_to_prob return 1.0 and _payout divide by zero, so it
        # must be filtered here exactly as engine/marketscan._dec does.
        overs = [(int(q["over_odds"]), q["book"]) for q in quotes
                 if q["over_odds"]]
        unders = [(int(q["under_odds"]), q["book"]) for q in quotes
                  if q["under_odds"]]
        if len(overs) < 2:
            continue
        # Best price = highest American odds = lowest implied probability.
        best_over, best_book = max(overs, key=lambda t: _payout(t[0]))
        avg_imp = sum(american_to_prob(o) for o, _ in overs) / len(overs)
        gains.append((avg_imp - american_to_prob(best_over)) * 100)
        books_won[best_book] += 1

        # Drop quotes whose own two sides are arithmetically impossible —
        # a fabricated under (over +850 / under -110) is not a price.
        from engine.odds import pair_is_sane
        sane = [q for q in quotes if q["over_odds"] and q["under_odds"]
                and pair_is_sane(int(q["over_odds"]), int(q["under_odds"]))]
        unders = [(int(q["under_odds"]), q["book"]) for q in sane]
        corrupt_pairs_local = len([q for q in quotes if q["over_odds"]
                                   and q["under_odds"]]) - len(sane)
        if corrupt_pairs_local:
            globals()["_corrupt_total"] = globals().get("_corrupt_total", 0) + corrupt_pairs_local
        if unders:
            best_under, _ = max(unders, key=lambda t: _payout(t[0]))
            shopped = american_to_prob(best_over) + american_to_prob(best_under)
            holds_shopped.append((shopped - 1.0) * 100)
            # Best hold available inside any single book.
            # Must be computed over the SAME sane quotes as the shopped
            # hold. Including corrupt pairs here dragged the single-book
            # average down to +2.30% while the shopped figure (already
            # filtered) read +5.35% — implying shopping made you worse
            # off, which is arithmetically impossible.
            per_book = {q["book"]: (american_to_prob(int(q["over_odds"]))
                                    + american_to_prob(int(q["under_odds"])))
                        for q in sane}
            if per_book:
                holds_single.append((min(per_book.values()) - 1.0) * 100)
            bu_book = max(unders, key=lambda t: _payout(t[0]))[1]
            if shopped < 1.0:
                # A "negative hold" inside ONE book is impossible — no book
                # prices both sides of its own market at a loss. When the
                # best over and best under come from the same book, the
                # stored pair is wrong (alternate lines crossed, or a
                # one-sided prop given a bogus under), not an opportunity.
                if bu_book == best_book:
                    same_book_bad += 1
                    continue
                arbs += 1
                arb_sizes.append((1.0 - shopped) * 100)
                arb_books[f"{best_book} / {bu_book}"] += 1
                if len(arb_rows) < args.show_arbs:
                    arb_rows.append((key, (1.0 - shopped) * 100,
                                     sorted((q["book"], q["line"],
                                             q["over_odds"], q["under_odds"])
                                            for q in quotes)))
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
        ct = globals().get("_corrupt_total", 0)
        if ct:
            print(f"  ⚠️  {ct:,} quote(s) had an impossible over/under pair "
                  f"(e.g. over +850 / under -110\n      on a home run — a "
                  f"fabricated side, not a price) and were excluded.")
        if same_book_bad:
            print(f"  ⚠️  {same_book_bad:,} pair(s) showed a negative hold INSIDE a single\n      book — impossible, so those rows have crossed/one-sided odds stored.\n      Excluded from the arbitrage count as data errors, not opportunities.")

    if arb_sizes:
        # Size is what separates a real, bettable arb from a stale quote.
        # Books do disagree on soft player props, but a 3%+ "arbitrage"
        # across US books is nearly always one side that stopped updating
        # — bet it and that leg is voided or already gone.
        arb_sizes.sort()
        m = len(arb_sizes)
        bands = [("under 0.5% (noise — limits/timing eat it)", 0, 0.5),
                 ("0.5-1.5% (plausible, thin but real)", 0.5, 1.5),
                 ("1.5-3% (rare if genuine)", 1.5, 3.0),
                 ("over 3% (almost certainly a stale line)", 3.0, 1e9)]
        print("\n  How big are those 'arbitrage' pairs?")
        for label, lo, hi in bands:
            k = sum(1 for x in arb_sizes if lo <= x < hi)
            print(f"    {label:<44} {k:>5}  ({k / m:6.1%})")
        print(f"    median {arb_sizes[m // 2]:.2f}%   p90 {arb_sizes[m * 9 // 10]:.2f}%"
              f"   max {arb_sizes[-1]:.2f}%")
        real = sum(1 for x in arb_sizes if 0.5 <= x < 3.0)
        print(f"\n  Plausibly bettable (0.5-3%): {real:,} of {m:,} — "
              f"{real / len(holds_shopped):.2%} of all pairs")
        print("  Most common book pairing:")
        for pair, k in sorted(arb_books.items(), key=lambda kv: -kv[1])[:3]:
            print(f"    {pair:<40} {k:>5}")

    if arb_rows:
        print("\nRAW ROWS behind the flagged pairs — read these before\n  believing any of it:")
        for key, size, qs in arb_rows:
            print(f"\n  {key[1]} · {key[2]} · line {key[3]} · {key[0]} "
                  f"→ {size:.1f}% \"arb\"")
            for book, line, oo, uo in qs:
                print(f"      {book:<14} line {line:<6} over {oo!s:<7} under {uo!s}")
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
