#!/usr/bin/env python3
"""Fit the projection's recency dial from real settled outcomes.

    python3 formfit.py --from-db data/history.db                 # all markets
    python3 formfit.py --from-db data/history.db --market hits   # just one
    python3 formfit.py --show                                    # what's fitted now

Rung two of the self-tuning loop. calibrate.py corrects the model's
confidence AFTER a projection exists; this fits the recipe the projection
is built from — how much the blend trusts a player's recent form versus
his long-run track record. One dial per market: 0 is the hand-tuned spec
curve, positive leans recent, negative leans long-run. The fit walks the
history DB forward (each game projected only from earlier games), scores
every dial setting by Brier on raw probabilities, and ADOPTS a move only
when it beats the spec curve by a real margin on a real sample. A dial
the record examined and left alone is a result too — the page says
"default kept", not nothing.

Run order matters: run this BEFORE calibrate.py. The temperature is a
correction for the model as it actually runs, and adopting new weights
changes that model.

Home runs are excluded: projection.py already replaced form blending
there with an empirical-Bayes rate, so the dial has nothing to act on.
"""

from __future__ import annotations

import argparse

from engine import calibrate as _cal
from engine import db as _db
from engine import formfit as ff
from engine.mlb.models import MARKET_LABELS as _MLB_LABELS
from engine.models import MARKET_LABELS as _GEN_LABELS

MARKET_LABELS = {**_GEN_LABELS, **_MLB_LABELS}
# No home_runs (rare-event path replaced form blending) and no
# anytime_td (same reason, NFL's rare-event market).
SPORT_MARKETS = {
    "mlb": ["total_bases", "hits", "strikeouts"],
    "nfl": ["pass_yds", "rush_yds", "rec_yds", "receptions"],
    # Hoops props go through their own pricing machinery but land in the
    # SAME history table, keyed (sport, market) — so the deep fit works
    # here the moment game logs are ingested. It was never wired up, which
    # is why `--learning` showed zeros for both: `--sport` validates
    # against this dict, so nba was not even a legal value to type.
    "nba": ["pts", "reb", "ast", "fg3m", "pra"],
    "wnba": ["pts", "reb", "ast", "fg3m", "pra"],
    # COLLEGE JOINED 2026-09-04, and the line it replaces was true when
    # it was written: college was priced at game level only, with no
    # player props for a fitter to walk. It has both now —
    # `engine/cfb/props.py` builds the props and the ingest holds 62,752
    # receiving-yard and 47,926 rushing-yard player-games — so the fit
    # this table was refusing to offer is one that runs.
    #
    # IT WAS NOT A HARMLESS OMISSION. `--sport` validates against this
    # dict, so cfb was not a legal value to type and no fitter could
    # reach it; `calibrate.correction_for("cfb", "rush_yds")` therefore
    # returned the neutral (1.0, 0.0) on every college prop the board
    # priced. The first live college board showed what that costs: the
    # model claimed 63% on an under where 4,852 comparable settled spots
    # went 80%, and the edges that produced (0.10-0.17) sailed past
    # MAX_CREDIBLE_EDGE, so every one of the 22 priced props was refused
    # as not credible. An uncalibrated market does not merely price
    # badly — it prices itself off the board.
    #
    # The same shape of gap `engine.rankfit.MARKETS` had, found the same
    # way, and closed the same way: measured on college's own logs.
    "cfb": ["pass_yds", "rush_yds", "rec_yds", "receptions"],
    # UFC stays absent: it has no game logs at all, so it learns from the
    # journal only and listing it would offer a fit that can never run.
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fit the recency dial from real outcomes.")
    ap.add_argument("--from-db", dest="db", default=str(_db.DEFAULT_DB),
                    help="history DB to learn from (default: data/history.db)")
    ap.add_argument("--sport", default="mlb", choices=sorted(SPORT_MARKETS),
                    help="which sport's dial to fit (default: mlb)")
    ap.add_argument("--market", default=None, help="fit a single market only")
    ap.add_argument("--min-history", type=int, default=None,
                    help="games of history before a player is projected "
                         "(default: the sport's own floor)")
    ap.add_argument("--show", action="store_true",
                    help="print the current fits and exit")
    args = ap.parse_args()

    if args.show:
        rows = ff.report(ff.DEFAULT_PATH)
        if not rows:
            print("No dial fitted yet — every market runs the spec curve.")
        for m in rows:
            print(f"  {m['sport']}:{m['market']:16} r = {m['r']:+.1f}  "
                  f"{m['reading']}  (n={m['samples']:,})")
        return

    conn = _db.connect(args.db)
    sport = args.sport
    markets = [args.market] if args.market else SPORT_MARKETS[sport]
    min_games = (args.min_history or (8 if sport == "mlb" else 4)) + 2

    fits: dict[str, ff.FormFit] = {}
    print(f"Fitting the {sport} recency dial from {args.db}")
    print(f"(one walk-forward per grid point — {len(ff.GRID)} per market; "
          "this is the slow fit)\n")
    for market in markets:
        label = MARKET_LABELS.get(market, market)
        entries = _db.entries_for_market(conn, sport, market,
                                         min_games=min_games)
        if not entries:
            print(f"  {label:16} skipped — no player history in the DB")
            continue
        f = ff.fit(entries, market, sport=sport,
                   min_history=args.min_history)
        if f is None:
            print(f"  {label:16} skipped — no settled predictions")
            continue
        print(f"  {label:16} {f.samples:>6,} settled   "
              f"Brier {f.brier_default:.4f} → {f.brier_fitted:.4f}   "
              f"r = {f.r:+.1f}")
        print(f"  {'':16} {f.verdict}")
        fits[f"{sport}:{market}"] = f

    if not fits:
        print("\nNothing fitted. Ingest history first, e.g.:\n"
              "  python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01")
        return

    path = ff.save(fits, ff.DEFAULT_PATH)
    print(f"\nWrote {path}")
    if any(f.adopted for f in fits.values()):
        print("Adopted weights change the model — refit its temperature "
              "next, on the new model:")
        print(f"  python3 calibrate.py --from-db {args.db}")
        _cal.reset_cache()
    else:
        print("Every dial stayed at the spec curve; no temperature refit "
              "needed on its account.")


if __name__ == "__main__":
    main()
