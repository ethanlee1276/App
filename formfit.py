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
    # COLLEGE, ADDED 2026-09-04, and the comment it replaces was true
    # when it was written:
    #
    #   "CFB and UFC are deliberately absent. College is priced at GAME
    #    level (spread / total / moneyline) and has no player-prop logs
    #    to walk... listing them here would offer a fit that can never
    #    run."
    #
    # Both halves of that are now false. College has 237,242 ingested
    # player-log rows — 38,154 receptions, 37,712 rec_yds, 26,072
    # rush_yds, 7,197 pass_yds — and `cfb_build` prices exactly these
    # four markets through `pipeline.price_props(sport="cfb")`, the same
    # call the NFL board makes. The premise was overtaken by #60 (get the
    # college logs) and the player-props work that followed it, and
    # nobody came back to this dict.
    #
    # THE COST WAS SILENT AND TOTAL. `deepfit.sports_with_history` counts
    # rows only for sports listed HERE, so college's quarter-million rows
    # were never counted and `refit_sport` was never called for it. The
    # three strongest fits this project has — the recency dial, the
    # per-player memory and the probability temperatures — have never run
    # for college football. Not declined on the evidence: never offered
    # the evidence.
    #
    # Each fitter keeps its own adoption gate (minimum sample, Brier
    # margin, plateau check), so listing college asks the question and
    # does not answer it. A market with nothing to say still says nothing.
    #
    # IT HAD A GREAT DEAL TO SAY. Run for the first time against the
    # 2022-26 college logs the day it was listed:
    #
    #   the dial      one market of four moved (pass_yds, +0.8 toward
    #                 recent form, Brier 0.2460 -> 0.2448 on 4,620
    #                 settled); the other three kept the default.
    #
    #   temperatures  ALL FOUR were miscalibrated, and three in the same
    #                 direction and by a lot:
    #
    #     market        settled       T     bias    reading
    #     pass_yds        4,620    0.50   +0.10    claimed 2 points too LITTLE
    #     rush_yds       16,253    0.48   -0.26    claimed 6 points too much
    #     rec_yds        23,681    0.68   -0.26    claimed 6 points too much
    #     receptions     21,259    0.40   -0.30    claimed 7 points too much,
    #                                              and AT THE GRID EDGE
    #
    # A college card reading 57% was really about 50%. The board has been
    # pricing, ranking and recommending on the uncorrected number for as
    # long as college has had player props, because nothing had ever
    # fitted a temperature to correct it — the markets were not declined
    # on the evidence, the evidence was never gathered.
    #
    # `receptions` pins to GRID_MIN, which is `calibrate.is_reliable`'s
    # signal for "unreliable, not merely miscalibrated" — the same
    # refusal that shuts nfl:rush_yds and nfl:rec_yds. On the droplet's
    # own history that market is likely to close, and closing it is the
    # correct outcome rather than a loss.
    #
    # These figures are from this checkout's history and are NOT
    # committed: the droplet fits its own, from more of it, in the weekly
    # deep refit. They are recorded to say what listing college bought.
    #
    # TWO SESSIONS FOUND THIS INDEPENDENTLY ON THE SAME DAY, and the
    # merge is where that became visible: `claude/cfb-player-props-q433qn`
    # added the identical line, for the identical reason, from the other
    # end of the problem. It reached it from the BOARD — the first live
    # college prop board priced 22 props and recommended none, every one
    # graded Pass, the comps saying "model says 63% but 4,852 similar
    # past spots went 80% to the under". An uncalibrated market does not
    # merely price badly: the 0.10-0.17 edges it produces sail past
    # `betting.MAX_CREDIBLE_EDGE`, so it prices itself off the board
    # entirely. That is the cost of this omission, observed rather than
    # reasoned, and it belongs here.
    #
    # THE TWO SESSIONS DISAGREE ON THE ROW COUNTS and neither should be
    # taken as settled. That commit reports "62,752 receiving-yard and
    # 47,926 rushing-yard player-games". Counted against data/history.db
    # on 2026-09-04 the ingested totals are the ones above: 37,712
    # rec_yds and 26,072 rush_yds rows of 237,242 college rows. The
    # source CSVs are play-level (765,288 rows over four seasons) so
    # neither figure is a raw count of those either. The gap is real and
    # unexplained; whichever number a later reader needs, MEASURE IT
    # rather than quoting one of these.
    "cfb": ["pass_yds", "rush_yds", "rec_yds", "receptions"],
    # UFC remains deliberately absent: it has no game logs at all, so a
    # fit here could never run. It learns from the journal only.
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
