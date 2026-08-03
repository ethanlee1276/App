#!/usr/bin/env python3
"""Fit the per-player memory from real settled outcomes.

    python3 playerfit.py --from-db data/history.db                 # all markets
    python3 playerfit.py --from-db data/history.db --market hits   # just one
    python3 playerfit.py --show                                    # what's stored now

Rung three of the self-tuning loop. The recency dial (formfit.py) fits
how the blend weighs time for everyone; this learns the specific players
it still misreads — anyone whose trajectory the window blend structurally
lags — and corrects their projected mean, shrunk toward 1.0 by evidence
and clamped to ±15%.

The mechanism must earn its keep per market: it is adopted only when
applying the corrections CAUSALLY (each game's correction computed
strictly from that player's earlier games) beat the uncorrected model's
walk-forward Brier by a real margin on a real sample. "Memory off" is a
published result, not a failure.

Run order matters: formfit.py → playerfit.py → calibrate.py. Each fitter
shapes the model the next one measures; the temperature comes last
because it corrects the model that will actually run.

Home runs are excluded: the rare-event path's empirical-Bayes rate
already IS a per-player learner.
"""

from __future__ import annotations

import argparse

from engine import calibrate as _cal
from engine import db as _db
from engine import playerfit as pf
from engine.mlb.models import MARKET_LABELS

# No home_runs — see the module docstring.
MLB_MARKETS = ["total_bases", "hits", "strikeouts", "outs"]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fit per-player corrections from real outcomes.")
    ap.add_argument("--from-db", dest="db", default=str(_db.DEFAULT_DB),
                    help="history DB to learn from (default: data/history.db)")
    ap.add_argument("--market", default=None, help="fit a single market only")
    ap.add_argument("--min-history", type=int, default=8,
                    help="games of history before a player is projected")
    ap.add_argument("--show", action="store_true",
                    help="print the current memory and exit")
    args = ap.parse_args()

    if args.show:
        rows = pf.report(pf.DEFAULT_PATH)
        if not rows:
            print("No player memory fitted yet.")
        for m in rows:
            print(f"  {m['sport']}:{m['market']:16} {m['reading']}  "
                  f"(n={m['samples']:,})")
            for t in m["top"]:
                print(f"    {t['player']:24} ×{t['mult']:.2f} "
                      f"over {t['games']} games")
        return

    conn = _db.connect(args.db)
    markets = [args.market] if args.market else MLB_MARKETS

    fits: dict[str, pf.PlayerFit] = {}
    print(f"Fitting player memory from {args.db}\n")
    for market in markets:
        label = MARKET_LABELS.get(market, market)
        entries = _db.entries_for_market(conn, "mlb", market,
                                         min_games=args.min_history + 2)
        if not entries:
            print(f"  {label:16} skipped — no player history in the DB")
            continue
        f = pf.fit(entries, market, min_history=args.min_history)
        if f is None:
            print(f"  {label:16} skipped — no settled predictions")
            continue
        print(f"  {label:16} {f.samples:>6,} settled   "
              f"Brier {f.brier_baseline:.4f} → {f.brier_corrected:.4f}")
        print(f"  {'':16} {f.verdict}")
        fits[f"mlb:{market}"] = f

    if not fits:
        print("\nNothing fitted. Ingest history first, e.g.:\n"
              "  python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01")
        return

    path = pf.save(fits, pf.DEFAULT_PATH)
    print(f"\nWrote {path}")
    if any(f.adopted for f in fits.values()):
        print("Adopted memory changes the model — refit its temperature "
              "next, on the new model:")
        print(f"  python3 calibrate.py --from-db {args.db}")
        _cal.reset_cache()
    else:
        print("Memory stayed off everywhere; no temperature refit needed "
              "on its account.")


if __name__ == "__main__":
    main()
