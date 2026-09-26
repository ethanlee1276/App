#!/usr/bin/env python3
"""Is the edge real, or is it just the outlier book?

    python3 bookcheck.py                 # every settled bet with snapshots
    python3 bookcheck.py --category all
    python3 bookcheck.py --market home_runs

THE STRUCTURE THIS EXAMINES

engine/odds.best_over_line shops for the most bettor-friendly price, and
then de-vigs THAT BOOK'S OWN two-way quote to get the "fair" probability
the edge is measured against:

    fair_over, _ = devig_two_way(ln.over_odds, ln.under_odds)
    ...
    edge = model_prob - best.fair_prob

So the benchmark is the book being bet. That has a consequence worth
stating plainly: the further out of line a book's price is, the more
likely it is selected AND the lower its own de-vigged fair, so the bigger
the edge appears. Shopping for the longest number and then defining fair
from that same number manufactures edge mechanically, before the model has
said anything.

Whether it matters is an empirical question, and the journal can answer it,
because engine/linemoves snapshots every book's price on every pull.

WHAT IS MEASURED

For each settled bet, the consensus implied probability across the books
quoted on that player/market/date, against the implied probability of the
price actually taken:

    outlier = consensus_implied - taken_implied

Positive means the price taken was LONGER than the field — the book we bet
was an outlier in our favour. That gap is edge the shopping produced
rather than the model. Then the honest test: did those bets land at the
rate the TAKEN price implied, or at the rate the CONSENSUS implied? The
first says the outlier was real value. The second says it was the book
knowing something, and the edge was an artifact of measuring against it.

WHAT IT WILL NOT DO

Change the pricing path. Moving `fair` from the taken book to a consensus
is a large change to every number on the board, and it should follow
evidence rather than an argument about how devigging ought to work.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import math
import sys
from collections import defaultdict

MIN_BOOKS = 3          #: a "consensus" of two is not one
MIN_N = 40             #: below this a book's row is shown, never convicted


def _implied(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return (100.0 / (o + 100.0)) if o > 0 else (-o / (-o + 100.0))


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def consensus_by_date(rows: list[dict]) -> dict:
    """{(player, market, date): (median implied, n books, spread in points)}.

    Median rather than mean, for the same reason the close-picker uses one:
    a single stale book should not define the field. The spread is the
    field's own disagreement, which is the context that says whether being
    an outlier means anything on this market.
    """
    from engine.sources.oddsapi import normalize_name
    grouped: dict = defaultdict(dict)
    for r in rows:
        try:
            ts = float(r["ts"])
            p = _implied(r.get("over_odds"))
            if p is None:
                continue
            date = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            key = (normalize_name(r["player"]), r["market"], date)
            book = r.get("book") or "?"
            # Last quote of the day per book — the field as it settled,
            # not an average over a day's drift.
            prev = grouped[key].get(book)
            if prev is None or ts >= prev[0]:
                grouped[key][book] = (ts, p)
        except (KeyError, TypeError, ValueError):
            continue
    out = {}
    for key, books in grouped.items():
        ps = [p for _ts, p in books.values()]
        if len(ps) < MIN_BOOKS:
            continue
        out[key] = (_median(ps), len(ps), max(ps) - min(ps))
    return out


def load(conn, sport=None, market=None, category="main"):
    q = ("SELECT sport, market, player, side, book, odds, hit_prob, status, "
         "date, stake_units, pnl_units FROM bets "
         "WHERE status IN ('won','lost') AND hit_prob IS NOT NULL")
    args = []
    if category != "all":
        q += " AND category=?"
        args.append(category)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if market:
        q += " AND market=?"
        args.append(market)
    return [dict(r) for r in conn.execute(q, args)]


def pair(bets: list[dict], cons: dict) -> list[dict]:
    """Bets we can price against the field, with the outlier gap attached."""
    from engine.sources.oddsapi import normalize_name
    out = []
    for b in bets:
        if (b["side"] or "OVER").upper() != "OVER":
            continue                     # snapshots carry the over price
        c = cons.get((normalize_name(b["player"]), b["market"], b["date"]))
        took = _implied(b["odds"])
        if not c or took is None:
            continue
        median, n_books, spread = c
        out.append({**b, "took": took, "consensus": median,
                    "outlier": median - took, "books": n_books,
                    "spread": spread})
    return out


def _rate_z(rows, field) -> float:
    """Did these land at the rate `field` implied? Poisson-binomial."""
    num = var = 0.0
    for b in rows:
        p = b[field]
        num += (1.0 if b["status"] == "won" else 0.0) - p
        var += p * (1.0 - p)
    return num / math.sqrt(var) if var > 0 else 0.0


def report(paired: list[dict], min_n: int = MIN_N) -> int:
    if not paired:
        print("No settled OVER bets could be matched to a multi-book "
              "snapshot.")
        print("engine/linemoves has to have recorded the field on those "
              "dates; without it there is no consensus to compare against.")
        return 0

    n = len(paired)
    avg_out = sum(b["outlier"] for b in paired) / n
    longer = sum(1 for b in paired if b["outlier"] > 0) / n
    avg_spread = sum(b["spread"] for b in paired) / n
    print("=" * 74)
    print("HOW FAR FROM THE FIELD ARE THE PRICES WE TAKE?")
    print("=" * 74)
    print(f"  {n:,} settled overs matched to a field of "
          f"{sum(b['books'] for b in paired) / n:.1f} books on average")
    print(f"  taken price is LONGER than the field on {longer:.0%} of bets")
    print(f"  average gap  {avg_out:+.2%} implied  "
          f"(the field's own spread is {avg_spread:.2%})")
    print()
    print("  A positive gap is edge the SHOPPING produced, not the model:")
    print("  it is there before the projection says anything, and it grows")
    print("  with how far out of line the chosen book is.")

    print()
    print("=" * 74)
    print("DID THE OUTLIER PAY? — the test that settles it")
    print("=" * 74)
    won = sum(1 for b in paired if b["status"] == "won")
    z_took = _rate_z(paired, "took")
    z_cons = _rate_z(paired, "consensus")
    print(f"  landed {won / n:.1%}")
    print(f"    vs the TAKEN price's implied  "
          f"{sum(b['took'] for b in paired) / n:.1%}   z {z_took:+.2f}")
    print(f"    vs the FIELD's implied        "
          f"{sum(b['consensus'] for b in paired) / n:.1%}   z {z_cons:+.2f}")
    print()
    # Which benchmark did the landing rate FOLLOW? That is the whole
    # question, and it is not "which z is bigger".
    #
    #   the field is right   → we bet a price longer than the truth, so we
    #                          land at the field's rate and BEAT the taken
    #                          price: z_took positive, z_cons about zero.
    #   the outlier is right → we bet the truth, so we land at the taken
    #                          price's rate and MISS the field's: z_took
    #                          about zero, z_cons negative.
    follows_field = z_took > 2 and abs(z_cons) <= 2
    follows_taken = z_cons < -2 and abs(z_took) <= 2
    if follows_taken:
        print("  → THE OUTLIER WAS NOT VALUE. These landed at the rate the")
        print("    PRICE WE TOOK implied, and missed the field's. The longer")
        print("    number was the book knowing something, not the book being")
        print("    wrong — and de-vigging that same book's quote to define")
        print("    fair turned its knowledge into our edge.")
        print()
        print("    The fix is where `fair` comes from: bet the best price,")
        print("    measure against the FIELD. engine/odds.best_over_line")
        print("    currently takes both from one book.")
    elif follows_field:
        print("  → THE OUTLIER WAS REAL VALUE. These landed at the FIELD's")
        print("    rate and beat the price we took, which is exactly what")
        print("    working line shopping looks like. The structure is fine")
        print("    and the shopping is earning its keep.")
    else:
        print("  → NOT SEPARABLE YET. The results did not clearly follow")
        print("    either benchmark on this sample, so the record cannot say")
        print("    whether the outlier was value or the book was right. The")
        print("    gap above is real arithmetic either way; what it BUYS is")
        print("    what needs more bets.")

    # Per book, because concentration is the thing that makes this bite.
    by_book: dict = defaultdict(list)
    for b in paired:
        by_book[b["book"] or "?"].append(b)
    print()
    print("=" * 74)
    print("BY BOOK — where the volume goes and what it was worth")
    print("=" * 74)
    print(f"  {'book':<16}{'n':>6}{'share':>7}{'gap vs field':>14}"
          f"{'landed':>8}{'z vs field':>12}")
    print("  " + "-" * 66)
    for bk, rs in sorted(by_book.items(), key=lambda kv: -len(kv[1])):
        m = len(rs)
        gap = sum(x["outlier"] for x in rs) / m
        land = sum(1 for x in rs if x["status"] == "won") / m
        z = _rate_z(rs, "consensus") if m >= min_n else None
        print(f"  {bk[:15]:<16}{m:>6}{m / n:>7.0%}{gap:>+14.2%}"
              f"{land:>8.1%}" + (f"{z:>+12.2f}" if z is not None
                                 else f"{'thin':>12}"))
    top = max(by_book.values(), key=len)
    if len(top) / n > 0.4:
        name = [k for k, v in by_book.items() if v is top][0]
        print()
        print(f"  ⚠  {len(top) / n:.0%} of these bets are at one book "
              f"({name}).")
        print("     That is what edge-measured-against-the-taken-book does:")
        print("     it selects hardest for the book furthest from the field,")
        print("     so the volume concentrates exactly where the benchmark")
        print("     is least trustworthy.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="Is the edge real, or the outlier book?")
    p.add_argument("--sport")
    p.add_argument("--market")
    p.add_argument("--category", default="main")
    p.add_argument("--min-n", type=int, default=MIN_N)
    p.add_argument("--db")
    a = p.parse_args(argv)

    from engine import ledger
    from engine.linemoves import load_history
    conn = ledger.connect(a.db) if a.db else ledger.connect()
    bets = load(conn, a.sport, a.market, a.category)
    cons = consensus_by_date(load_history())
    return report(pair(bets, cons), a.min_n)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
