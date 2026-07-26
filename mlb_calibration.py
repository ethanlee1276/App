#!/usr/bin/env python3
"""Per-market calibration sweep — the honest health check on the model.

    python3 mlb_calibration.py                # every market, from the DB
    python3 mlb_calibration.py --naive        # skip harvested book lines

Runs the walk-forward backtest across every MLB prop market at once and
prints one compact table, because the question that matters isn't "is
the model good" but "WHICH markets can it price". Today's board showed
the model claiming implausible edges on 42% of props and overstating
favourites by ~21 points; this says where that comes from, market by
market, on thousands of real games instead of a few dozen bets.

Read the output like this:

  * **ECE** (expected calibration error) — average gap between what the
    model said and what happened. Under ~0.03 is trustworthy, over ~0.08
    means the probabilities are fiction in that market.
  * **Brier** — overall forecast accuracy, lower is better. Always
    compare it to the base-rate column: beating 0.25 on a coin-flip
    market is easy, beating the base rate is not.
  * **Bins** — "said 63% → actual 78%" is the readout that matters. Said
    ABOVE actual means overconfident: the source of every guard we've
    had to bolt on.
  * **real lines** — how much of the betting result was priced against a
    number a bettor could actually have taken. Low coverage means the
    ROI column is "beats a trailing average", not "beats the book".
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine import db as _db
from engine.mlb.backtest import backtest_from_logs
from engine.mlb.models import MARKET_LABELS
from engine.rules import RuleConfig

MARKETS = ("total_bases", "hits", "home_runs", "strikeouts")
ROOT = Path(__file__).parent


def sweep(db_path: str, markets=MARKETS, min_history: int = 6,
          use_real_lines: bool = True) -> list[dict]:
    from engine.sources.oddsapi import normalize_name
    conn = _db.connect(db_path)
    rows = []
    for market in markets:
        entries = _db.entries_for_market(conn, "mlb", market,
                                         min_games=min_history + 1)
        if not entries:
            rows.append({"market": market, "n": 0})
            continue
        real_lines = {}
        if use_real_lines:
            for (player, date), q in _db.closing_odds_by_date(
                    conn, "mlb", market).items():
                real_lines[(normalize_name(player), date)] = q
        rep = backtest_from_logs(entries, market, min_history=min_history,
                                 config=RuleConfig(), real_lines=real_lines)
        d = rep.__dict__ if hasattr(rep, "__dict__") else dict(rep)
        d["market"] = market
        rows.append(d)
    return rows


def _get(d, *names, default=None):
    for n in names:
        v = d.get(n) if isinstance(d, dict) else getattr(d, n, None)
        if v is not None:
            return v
    return default


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--min-history", type=int, default=6)
    ap.add_argument("--naive", action="store_true",
                    help="ignore harvested book lines (baseline pricing only)")
    args = ap.parse_args()

    rows = sweep(args.db, min_history=args.min_history,
                 use_real_lines=not args.naive)

    print(f"\nMLB per-market calibration · walk-forward on {args.db}\n")
    hdr = (f"{'market':<14}{'props':>8}{'Brier':>9}{'ECE':>8}"
           f"{'bets':>7}{'win%':>7}{'ROI':>9}{'real lines':>12}")
    print(hdr)
    print("-" * len(hdr))
    for d in rows:
        label = MARKET_LABELS.get(d["market"], d["market"])[:13]
        n = _get(d, "n", default=0)
        if not n:
            print(f"{label:<14}{'—':>8}   (no rows — try a wider --min-history)")
            continue
        brier = _get(d, "brier", default=float("nan"))
        ece = _get(d, "ece", default=float("nan"))
        bets = _get(d, "n_bets", default=0)
        wins = _get(d, "wins", default=0)
        roi = _get(d, "roi", default=0.0)
        used = _get(d, "used_real_lines", default=0)
        winpct = (wins / bets * 100) if bets else 0.0
        print(f"{label:<14}{n:>8,}{brier:>9.4f}{ece:>8.3f}"
              f"{bets:>7}{winpct:>6.1f}%{roi:>+8.1%}{used:>12,}")

    # The distinction that decides whether any of this is real: bets priced
    # against a harvested BOOK line are the only ones that answer "would
    # this have beaten the market?". Baseline-priced bets only show the
    # model beats a trailing average, which no sportsbook offers.
    print("\nBets priced against a REAL book line vs a naive baseline:")
    hdr2 = (f"{'market':<14}{'basis':<10}{'bets':>7}{'win%':>7}{'ROI':>9}"
            f"{'net u':>9}")
    print(hdr2)
    print("-" * len(hdr2))
    any_book = False
    for d in rows:
        segs = _get(d, "segments", default=None) or {}
        for basis in ("book", "naive"):
            g = segs.get(basis)
            if not g or not g.get("n_bets"):
                continue
            if basis == "book":
                any_book = True
            label = MARKET_LABELS.get(d["market"], d["market"])[:13]
            n = g["n_bets"]
            wr = g.get("wins", 0) / n * 100 if n else 0.0
            staked = g.get("staked", 0.0)
            net = g.get("net", 0.0)
            roi = (net / staked) if staked else 0.0
            tag = "vs BOOK" if basis == "book" else "baseline"
            print(f"{label:<14}{tag:<10}{n:>7}{wr:>6.1f}%{roi:>+8.1%}{net:>+9.2f}")
    if not any_book:
        print("  (no harvested book lines matched — the ROI column above is "
              "predictive skill only, NOT an edge over the market)")

    print("\nReliability — what the model said vs what happened:")
    for d in rows:
        bins = _get(d, "bins", default=None)
        if not bins:
            continue
        print(f"\n  {MARKET_LABELS.get(d['market'], d['market'])}")
        for b in bins:
            lo, hi = _get(b, "lo", default=0.0), _get(b, "hi", default=0.0)
            pred = _get(b, "mean_pred", "predicted")
            act = _get(b, "hit_rate", "actual")
            cnt = _get(b, "n", default=0)
            if pred is None or act is None or not cnt:
                continue
            gap = (act - pred) * 100
            verdict = ("overconfident" if gap < -3 else
                       "under-confident" if gap > 3 else "well calibrated")
            print(f"    p {lo:.1f}-{hi:.1f}: said {pred:5.1%} → actual {act:5.1%}"
                  f"  (n={cnt:,})  {gap:+5.1f}pts  {verdict}")

    print("\nECE under ~0.03 = trustworthy · over ~0.08 = the probabilities are "
          "fiction in that market.\n'said' above 'actual' is overconfidence — "
          "the thing every guard we added is compensating for.")


if __name__ == "__main__":
    main()
