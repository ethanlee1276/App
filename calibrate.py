#!/usr/bin/env python3
"""Fit the model's probability calibration from real settled outcomes.

    python3 calibrate.py --from-db data/history.db                 # all markets
    python3 calibrate.py --from-db data/history.db --market hits   # just one
    python3 calibrate.py --show                                    # what's fitted now

Calibration is the part of "does this model have an edge" that can be checked
with **outcomes alone** — it needs no historical sportsbook prices. It asks: when
the model says 60%, does it actually hit 60%? If not, every edge it reports is
wrong by that gap and the stakes are wrong with it.

This walks the history DB forward (projecting each game only from earlier
games), compares predictions to what really happened, fits a temperature
correction per market, and saves it to data/models/calibration.json. The betting
engine picks it up automatically on the next run.

Ingest real history first, e.g.:
    python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01
"""

from __future__ import annotations

import argparse
import datetime as _dt

from engine import calibrate as cal
from engine import db as _db
from engine.logwalk import walk
from engine.mlb.models import MARKET_LABELS as _MLB_LABELS
from engine.models import MARKET_LABELS as _GEN_LABELS

MARKET_LABELS = {**_GEN_LABELS, **_MLB_LABELS}
SPORT_MARKETS = {
    "mlb": ["total_bases", "hits", "home_runs", "strikeouts"],
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
MLB_MARKETS = SPORT_MARKETS["mlb"]        # kept for older callers


def fit_market(conn, market: str, min_history, min_samples: int,
               sport: str = "mlb"):
    entries = _db.entries_for_market(
        conn, sport, market,
        min_games=(min_history or (8 if sport == "mlb" else 4)) + 2)
    if not entries:
        return None, "no player history in the DB for this market"
    # Fit on the model's RAW probabilities. With the existing calibration still
    # applied, each run would learn a correction for already-corrected input and
    # then apply it to raw input, compounding every time it's re-run.
    with cal.disabled():
        report = walk(sport, entries, market, min_history=min_history)
    if not report.pairs:
        return None, "no settled predictions (need more games per player)"
    c = cal.fit(report.pairs, sport=sport, market=market, min_samples=min_samples)
    return (c, report), None


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit probability calibration from real outcomes.")
    ap.add_argument("--from-db", dest="db", default=str(_db.DEFAULT_DB),
                    help="history DB to learn from (default: data/history.db)")
    ap.add_argument("--sport", default="mlb", choices=sorted(SPORT_MARKETS),
                    help="which sport to fit (default: mlb)")
    ap.add_argument("--market", default=None, help="fit a single market only")
    ap.add_argument("--min-history", type=int, default=None,
                    help="games of history before a player is projected "
                         "(default: the sport's own floor)")
    ap.add_argument("--min-samples", type=int, default=200,
                    help="settled props required before a correction is trusted")
    ap.add_argument("--show", action="store_true", help="print the current calibration and exit")
    args = ap.parse_args()

    if args.show:
        current = cal.load()
        if not current:
            print("No calibration fitted yet — the model runs uncorrected.")
        else:
            print("Fitted calibration:")
            for key, t in sorted(current.items()):
                print(f"  {key:28} T = {t}")
        return

    conn = _db.connect(args.db)
    sport = args.sport
    markets = [args.market] if args.market else SPORT_MARKETS[sport]

    fitted: dict[str, cal.Calibration] = {}
    print(f"Fitting {sport} calibration from {args.db}\n")
    for market in markets:
        label = MARKET_LABELS.get(market, market)
        got, err = fit_market(conn, market, args.min_history,
                              args.min_samples, sport=sport)
        if err:
            print(f"  {label:16} skipped — {err}")
            continue
        c, report = got
        # Stamp who fitted this and when. The journal fitter reads the basis
        # to decide what it may refit, and an unstamped entry is treated as
        # this fitter's — correct for the ones already on disk, but only a
        # stamp makes it true rather than assumed.
        c.basis = cal.BASIS_HISTORY
        c.fitted_at = _dt.date.today().isoformat()
        print(f"  {label:16} {c.samples:>5} settled   "
              f"Brier {c.brier_before:.4f} → {c.brier_after:.4f}   "
              f"T = {c.temperature}  bias = {c.intercept:+.2f}")
        if c.samples < args.min_samples:
            print(f"  {'':16} (under {args.min_samples} samples — left uncorrected)")
        else:
            print(f"  {'':16} {c.verdict}")
            if c.bias_note:
                print(f"  {'':16} {c.bias_note}")
            if c.at_boundary:
                print(f"  {'':16} ⚠️  fit hit the edge of the search range — treat "
                      f"this market's model as unreliable, not merely miscalibrated")
        fitted[f"{sport}:{market}"] = c

    if not fitted:
        print("\nNothing fitted. Ingest history first, e.g.:\n"
              "  python3 ingest.py mlb --from 2026-04-01 --to 2026-07-01")
        return

    path = cal.save(fitted)
    cal.reset_cache()
    print(f"\nWrote {path}")
    print("The betting engine will apply this on the next build.")


if __name__ == "__main__":
    main()
