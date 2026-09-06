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
from engine.mlb.models import MARKET_LABELS as _MLB_LABELS
from engine.models import MARKET_LABELS as _GEN_LABELS

MARKET_LABELS = {**_GEN_LABELS, **_MLB_LABELS}
# No home_runs / anytime_td — the rare-event paths are already
# per-player learners.
SPORT_MARKETS = {
    "mlb": ["total_bases", "hits", "strikeouts", "outs"],
    "nfl": ["pass_yds", "rush_yds", "rec_yds", "receptions"],
    # College, added 2026-09-04 — 237,242 ingested player-log rows and a
    # board that prices these four through the shared engine. See
    # formfit.SPORT_MARKETS for the premise this corrects and what it
    # cost. UFC stays out: no game logs to walk.
    "cfb": ["pass_yds", "rush_yds", "rec_yds", "receptions"],
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
        description="Fit per-player corrections from real outcomes.")
    ap.add_argument("--from-db", dest="db", default=str(_db.DEFAULT_DB),
                    help="history DB to learn from (default: data/history.db)")
    ap.add_argument("--sport", default="mlb", choices=sorted(SPORT_MARKETS),
                    help="which sport's memory to fit (default: mlb)")
    ap.add_argument("--market", default=None, help="fit a single market only")
    ap.add_argument("--min-history", type=int, default=None,
                    help="games of history before a player is projected "
                         "(default: the sport's own floor)")
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
    sport = args.sport
    markets = [args.market] if args.market else SPORT_MARKETS[sport]
    min_games = (args.min_history or (8 if sport == "mlb" else 4)) + 2

    fits: dict[str, pf.PlayerFit] = {}
    print(f"Fitting {sport} player memory from {args.db}\n")
    for market in markets:
        label = MARKET_LABELS.get(market, market)
        entries = _db.entries_for_market(conn, sport, market,
                                         min_games=min_games)
        if not entries:
            print(f"  {label:16} skipped — no player history in the DB")
            continue
        f = pf.fit(entries, market, min_history=args.min_history, sport=sport)
        if f is None:
            print(f"  {label:16} skipped — no settled predictions")
            continue
        print(f"  {label:16} {f.samples:>6,} settled   "
              f"Brier {f.brier_baseline:.4f} → {f.brier_corrected:.4f}")
        print(f"  {'':16} {f.verdict}")
        fits[f"{sport}:{market}"] = f

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
