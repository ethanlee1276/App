"""Where the touchdown model disagrees with the market, by price.

THE SHAPE THE WEEK 1 BOARD SHOWED. Every value pick sat ABOVE the book
by about four points at +300 to +650, while the watchlist sat six to
eleven points BELOW it on favourites priced -150 to -265:

    Jahmyr Gibbs     model 0.576   book 0.685
    Derrick Henry    model 0.565   book 0.629
    Jonathan Taylor  model 0.502   book 0.587
    Jauan Jennings   model 0.283   book 0.236
    Greg Dortch      model 0.165   book 0.126

A model flatter than the market at both ends. That is not a judgement
about any player; it is a statement about the shape of the curve, and it
decides whether a +0.047 edge on a +300 longshot is an edge at all.

We already know which end is wrong. The board's 51 book-priced touchdown
bets were all in that tail: it claimed 30.5% and delivered 11.8%, while
the market implied 12-25%. The outcome landed on the market's side.

`engine.tdbacktest` grades the model against OUTCOMES and cannot see
this — a model can be well calibrated on average while being wrong in
exactly the band it chooses to bet. So this joins the replayed
probabilities to the harvested closing prices and reports, per band of
the MARKET's implied probability, what the model said, what the market
said, and what actually happened. Three numbers per band; whichever of
the first two the third sits nearer is the one to believe.

Needs a database with `odds_history` — the box that bought the closes.

Standard library only.
"""

from __future__ import annotations

#: Market implied-probability bands. Split where the money is: the
#: long-shot tail the board actually bets is the first two.
BANDS = ((0.00, 0.15), (0.15, 0.25), (0.25, 0.40), (0.40, 0.60), (0.60, 1.01))

#: A band needs this many joined player-weeks before its hit rate means
#: anything. At 40 a 20% band still carries about eight scorers.
MIN_BAND = 40


def _prob(odds: int) -> float | None:
    """American price to implied probability, vig included."""
    from .odds import american_to_prob
    try:
        odds = int(odds)
    except (TypeError, ValueError):
        return None
    return american_to_prob(odds) if odds else None


def joined(conn, sport: str = "nfl", seasons=None) -> list:
    """``[(model, market, scored)]`` for player-weeks with a real close."""
    from . import db as _db
    from .backtest import _norm
    from .tdbacktest import run

    closes = _db.closing_odds_by_date(conn, sport, "anytime_td")
    if not closes:
        return []
    # Closes are keyed by date; the replay knows season and week. The
    # schedule bridges them, keyed by team because a week holds a
    # Thursday, a Sunday and a Monday.
    from .formbook import game_dates
    dates = game_dates(seasons)

    rows: list = []
    def _collect(r):
        date = dates.get((r["season"], int(r["week"]), r["team"]))
        if not date:
            return
        quote = closes.get((_norm(r["player"]), date))
        if not quote:
            return
        market = _prob(quote.get("over_odds"))
        if market is None:
            return
        rows.append((r["prob"], market, r["scored"]))

    run(conn, sport=sport, seasons=seasons, collect=_collect)
    return rows


#: Depths the board is priced at, matching `tdbacktest.BOARD_DEPTHS` so
#: the hit rate and the ROI can be read on the same line.
#:
#: THE SHALLOW END IS WHY THIS GREW. Over 95 replayed slates the single
#: most likely scorer landed 67.4%, well clear of the 60.0% it claimed —
#: a much smaller and sharper board than the top five, and the place the
#: ranking is most likely to outrun the price. Nothing was pricing it
#: until now.
ROI_DEPTHS = (1, 2, 3, 5, 10, 20, 40)

#: Raised with the depth count. The verdict below is read off a
#: Bonferroni-corrected tail, and at 0.05/7 two-sided that percentile
#: sits three resamples from the end of a 600-draw bootstrap — an
#: interval bound decided by three numbers is not one.
ROI_RESAMPLES = 2000

#: The whole family is 0.05, split across the depths asked. Seven looks
#: at the same board is seven chances to be surprised, and a single
#: "profitable" flag at a plain 95% across seven depths is close to a
#: one-in-three coin flip. `devigfit.BAND_Z` and `calibrate.CURVE_Z`
#: carry the same correction for the same reason; this is that
#: discipline applied to the one report that would put money on a board.
ROI_FAMILY_ALPHA = 0.05


def board_priced(conn, sport: str = "nfl", seasons=None, fitter=None) -> list:
    """Replayed board rows with the price a shopper could have taken.

    `joined` above keeps (model, market, scored) and drops the identity,
    so it can measure calibration against the book and cannot rank a
    slate. This keeps season, week, the corrected probability and the
    LONGEST price on the screen — everything an ROI needs.
    """
    from . import db as _db
    from .backtest import _norm
    from .betting import MAX_CREDIBLE_EDGE
    from .formbook import game_dates
    from .likely import MIN_PROB
    from .longshots import ONE_SIDED_HOLD
    from .tdbacktest import board_rows, run

    closes = _db.closing_odds_all_books(conn, sport, "anytime_td")
    if not closes:
        return []
    dates = game_dates(seasons)
    rows: list = []
    run(conn, sport=sport, seasons=seasons, collect=rows.append)
    board_rows(rows, fitter=fitter)

    #: The funnel, published rather than inferred. A harness that quietly
    #: measures a different population than the page is the failure this
    #: file has now had three times.
    seen = {"replayed": len(rows), "priced": 0, "thin": 0, "incredible": 0}
    out: list = []
    for r in rows:
        try:
            date = dates.get((r["season"], int(r["week"]), r["team"]))
        except (TypeError, ValueError):
            continue
        quotes = closes.get((_norm(r["player"]), date)) if date else None
        if not quotes:
            continue
        priced = [o for o in (q.get("over_odds") for q in quotes) if o]
        if not priced:
            continue
        # The longest price on the screen — what `odds.best_over_line`
        # publishes, and the only price a shopping board actually takes.
        #
        # A NUMERIC MAX IS THE RIGHT ONE, which is worth saying because
        # American odds look like they need a special case and do not:
        # any plus price beats any minus price, +900 beats +650, and -110
        # beats -200. All three are the same comparison.
        best = max(int(o) for o in priced)
        seen["priced"] += 1

        # THE PAGE'S OWN REFUSALS, APPLIED HERE TOO — and the first three
        # versions of this harness applied none of them, which made every
        # number it produced a claim about a board the site never
        # publishes.
        #
        # The tell was the claimed-ROI column: +72% at top 10, which
        # backs out to a 48% model probability against a +259 price. That
        # is a twenty-point disagreement with the market, and
        # `betting.MAX_CREDIBLE_EDGE` exists to refuse exactly it — a gap
        # that size in a heavily bet market is our error far more often
        # than a discovery. `likely.build` drops those rows before a
        # reader ever sees them; this measured them and called the result
        # the Most Likely board.
        #
        # Same population as the page, or the comparison is fiction.
        implied = _prob(best)
        if implied is None:
            continue
        fair = implied / ONE_SIDED_HOLD
        if r["cal"] < MIN_PROB:
            seen["thin"] += 1
            continue
        if abs(r["cal"] - fair) > MAX_CREDIBLE_EDGE:
            seen["incredible"] += 1
            continue
        out.append({"season": r["season"], "week": r["week"],
                    "cal": r["cal"], "rank": r["rank"], "fair": fair,
                    "player": r["player"], "odds": int(best),
                    "scored": r["scored"]})
    board_priced.funnel = dict(seen, kept=len(out))
    return out


def _decimal(odds: int) -> float:
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / abs(odds))


def roi_lines(rows: list, depths=ROI_DEPTHS, seed: int = 5) -> list:
    """Flat-stake ROI at the top of the board, per depth.

    THE QUESTION THIS ANSWERS, and the one nothing else could. Ethan,
    2026-08-30: "why are we not putting money on the most likely and long
    shots. i feel like we should expecially since we learned the ROI is
    higher with the most likely bets."

    We had not learned that. What was measured is RANKING (0.72 AUC on
    who scores) and CALIBRATION (the top five rows of a slate land 60.2%
    against 53.4% claimed). Neither is profit. A board that sorts the
    field perfectly still loses money if it pays -200 for a 60% shot, and
    whether it beats the price is the 0.468-AUC quantity that tests as
    noise. This is the join that settles it: the rows the board would
    have shown, at the prices actually on the screen, against what
    happened.

    Ranked WITHIN a slate and bootstrapped BY slate, for the same reason
    `board_report` is: rows in one slate share games and scripts, and
    resampling rows would report an interval several times too tight.
    """
    import random

    slates: dict = {}
    for r in rows:
        slates.setdefault((r["season"], r["week"]), []).append(r)
    groups = list(slates.values())
    if not groups:
        return ["  no priced board rows — this box has no odds_history, or "
                "no season is ingested"]

    def roi(sample, k):
        # WHAT THE BOARD CLAIMED IT WOULD RETURN, priced bet by bet at
        # that bet's OWN odds — and the third summary this column has
        # had, because the first two compressed a vector into a scalar
        # and lost the plot doing it.
        #
        # The first averaged AMERICAN odds, which are not a linear
        # scale: the live harvest printed "+396" beside a 48% hit rate
        # and a -11.86% ROI, three numbers that cannot all be true.
        #
        # The second was `n / sum(decimal)` — the uniform win rate a flat
        # portfolio breaks even at. Arithmetically exact, and meaningless
        # the moment the prices differ: nine bets at -140 beside one at
        # +2000 "break even at 27.5%" when the favourites each need 58.3%
        # and the lottery ticket needs 4.8%. It printed "needs 15.6%"
        # against a 48% hit rate and a losing ROI, which is the same
        # impossible triple in a subtler costume.
        #
        # A per-bet expectation has no such problem. Each row claims
        # `p*(d-1) - (1-p)` at its own price; the mean of those is the
        # ROI the board says it should return, and the realised ROI beside
        # it is the answer.
        staked = ret = hits = n = claim = 0.0
        for g in sample:
            top = sorted(g, key=lambda r: -r["cal"])[:k]
            if len(top) < k:
                continue
            for r in top:
                staked += 1.0
                hits += r["scored"]
                d = _decimal(r["odds"])
                p = float(r["cal"])
                claim += p * (d - 1.0) - (1.0 - p)
                ret += (d - 1.0) if r["scored"] else -1.0
                n += 1
        if not staked:
            return None
        return (ret / staked, hits / n, int(n), claim / n)

    rng = random.Random(seed)
    out = [f"NFL likelihood board · ROI at the price on the screen "
           f"({len(groups)} slates)",
           "  depth        bets     hit   claimed    actual      gap"
           "    95% by slate"]
    for k in depths:
        got = roi(groups, k)
        if not got:
            continue
        r_all, hit, n, claimed = got
        boot = []
        for _ in range(ROI_RESAMPLES):
            draw = [groups[rng.randrange(len(groups))] for _ in groups]
            g = roi(draw, k)
            if g:
                boot.append(g[0])
        boot.sort()
        lo = boot[int(0.025 * len(boot))]
        hi = boot[int(0.975 * len(boot)) - 1]
        # DESCRIBED AT 95%, JUDGED AT THE CORRECTED LEVEL. The printed
        # interval is the familiar one; the word beside it has to clear a
        # bar raised for the number of depths being asked.
        tail = ROI_FAMILY_ALPHA / max(1, len(depths)) / 2.0
        clo = boot[int(tail * len(boot))]
        chi = boot[int((1.0 - tail) * len(boot)) - 1]
        verdict = ("   <-- profitable" if clo > 0 else
                   "   <-- losing" if chi < 0 else "   inside the noise")
        out.append(f"   top {k:<8d} {n:5d}  {hit:6.1%}  {claimed:+7.2%}  "
                   f"{r_all:+7.2%}  {r_all - claimed:+7.2%}   "
                   f"[{lo:+.1%},{hi:+.1%}]{verdict}")
    out.append("  Flat one unit a row at the LONGEST price quoted, ranked "
               "within each slate.")
    out.append("  CLAIMED is what the board says these rows return, priced "
               "bet by bet at their")
    out.append("  own odds. ACTUAL is what they did. GAP is the whole "
               "question — a board can")
    out.append("  rank the field perfectly and still lose if the price "
               "already knew.")
    out.append("  An interval spanning zero is not a green light: it is the "
               "data declining to say.")
    m = len(depths)
    if m > 1:
        out.append(f"  The interval shown is 95%; the WORD beside it is "
                   f"judged at {ROI_FAMILY_ALPHA:.0%} split across")
        out.append(f"  {m} depths, because asking the same board {m} times "
                   f"is {m} chances to be fooled.")
    else:
        out.append("  One depth asked, so the interval and the verdict are "
                   "the same 95%.")
    return out


def bands(rows: list, min_band: int = MIN_BAND) -> list:
    """Per market band: model mean, market mean, realised rate, n."""
    out = []
    for lo, hi in BANDS:
        got = [r for r in rows if lo <= r[1] < hi]
        if len(got) < min_band:
            out.append({"lo": lo, "hi": hi, "n": len(got), "thin": True})
            continue
        n = float(len(got))
        out.append({
            "lo": lo, "hi": hi, "n": len(got), "thin": False,
            "model": sum(r[0] for r in got) / n,
            "market": sum(r[1] for r in got) / n,
            "actual": sum(r[2] for r in got) / n,
        })
    return out


def report_lines(rows: list, min_band: int = MIN_BAND) -> list:
    """The table, and which side the outcome fell on."""
    if not rows:
        return ["  anytime_td: no player-week joined a harvested close"]
    lines = [f"  anytime_td: {len(rows):,} player-weeks with a real close",
             f"      {'market band':<14}{'n':>7}{'model':>9}{'market':>9}"
             f"{'actual':>9}   how wrong we were"]
    for b in bands(rows, min_band):
        label = f"{b['lo']:.0%}-{b['hi']:.0%}"
        if b["thin"]:
            lines.append(f"      {label:<14}{b['n']:>7}      too few to read")
            continue
        # MODEL AGAINST OUTCOME, and nothing else. The first version of
        # this report also scored the MARKET against the outcome and
        # named whichever landed nearer, which was wrong twice over.
        # `anytime_td` is a Yes-only market (maintenance.HOLD_MARKETS):
        # there is no under price, so the implied probability keeps its
        # whole hold and reads high by construction. Scoring that against
        # reality convicts the book of its own vig. And the hold cannot
        # be removed without the other side, so the honest move is to
        # print the market as context and grade only ourselves.
        err = b["model"] / b["actual"] - 1.0 if b["actual"] else 0.0
        # A hair either side of zero must not print "-0%", which reads
        # as a direction it does not have.
        how = ("matches reality" if abs(err) < 0.005
               else f"model {err:+.0%} vs reality")
        lines.append(f"      {label:<14}{b['n']:>7}{b['model']:>9.3f}"
                     f"{b['market']:>9.3f}{b['actual']:>9.3f}   {how}")
    lines.append("      (market implied is Yes-only and keeps its whole "
                 "hold — context, not a competitor)")
    return lines


#: Book-priced player-weeks the fit needs. Well above calibrate.fit's
#: own floor, for propcal's reason: a correction fitted here replaces one
#: that is already live.
MIN_FIT = 800


def fit(conn, sport: str = "nfl", seasons=None, path=None, min_fit: int = MIN_FIT):
    """Fit the touchdown correction on the players a book actually prices.

    THE POPULATION MISMATCH THIS FIXES, and it is the fourth of its shape
    in this codebase. `tdbacktest.fit_calibration` fits over EVERY
    ingested player-week — 22,168 of them, overwhelmingly deep-bench
    players with a near-zero probability and a near-zero outcome. The
    board bets none of those. It bets players a book bothered to hang a
    price on, and within those, the long-shot tail.

    Fitted on everything, the correction that came back (T=1.12,
    bias=+0.20) improved average Brier from 0.1458 to 0.1435 and made the
    band the board actually bets nearly twice as wrong:

        band       model   actual   raw err   after that correction
        0-15%      0.063    0.051     +24%          +94%
        15-25%     0.122    0.173     -29%            0%
        25-40%     0.205    0.290     -29%           -8%

    Which is precisely what `calibrate.bake_off` warns about in its own
    docstring — a fit that improves the average while wrecking a band,
    because most of the sample sits somewhere else.

    So this fits on the joined subset instead. Same fitter, same
    bake-off, same held-out judge; only the population changes, and it
    changes to the one that gets bet.

    IT IS NOT ENOUGH, AND THE REPORT SAYS SO. Narrowing the population
    helps the middle bands and still leaves the tail worse than
    uncorrected — measured on a synthetic with the real shape, +23%
    becomes +81%. That is not a fitter defect. Brier is a squared error,
    so being three points wrong at p=0.05 costs 0.0009 while being
    twelve points wrong at p=0.6 costs 0.0144: any Brier-minimising fit
    will sell the long-shot band to buy the top one, and both the
    temperature and the isotonic curve do exactly that. A board that
    bets only the tail cannot take its correction from an objective that
    prices the tail at nothing.

    So `fit_lines` prints what the fit does to every band, and the
    decision of whether to keep it stays with a person. Adopting on the
    Brier line alone is how this went wrong the first time.
    """
    from . import calibrate
    rows = joined(conn, sport=sport, seasons=seasons)
    if len(rows) < min_fit:
        return None, rows
    pairs = [(m, s) for m, _k, s in rows]
    got = calibrate.fit(pairs, sport=sport, market="anytime_td")
    got.basis = calibrate.BASIS_BOOK
    import datetime as _dt
    got.fitted_at = _dt.date.today().isoformat()
    calibrate.save({f"{sport}:anytime_td": got},
                   path or calibrate.DEFAULT_PATH)
    calibrate.reset_cache()
    return got, rows


def fit_lines(got, rows) -> list:
    """What the fit did, and what it does to each band."""
    if got is None:
        return [f"  anytime_td: refused — {len(rows):,} book-priced "
                f"player-weeks, needs {MIN_FIT:,}"]
    from .calibrate import apply_temperature
    from . import isotonic as _iso
    curve = _iso.Curve.from_dict(got.curve) if got.curve else None
    shape = (f"isotonic, {len(got.curve.get('knots') or [])} knots" if curve
             else f"T={got.temperature} bias={got.intercept:+.2f}")
    lines = [f"  anytime_td: fitted on {len(rows):,} BOOK-PRICED "
             f"player-weeks — {shape}",
             f"      Brier {got.brier_before:.4f} → {got.brier_after:.4f}"]
    for b in bands(rows):
        if b["thin"]:
            continue
        corrected = (curve.apply(b["model"]) if curve
                     else apply_temperature(b["model"], got.temperature,
                                            got.intercept))
        was = b["model"] / b["actual"] - 1.0
        now = corrected / b["actual"] - 1.0
        lines.append(f"      {b['lo']:.0%}-{b['hi']:.0%}  n={b['n']:<5} "
                     f"{b['model']:.3f} → {corrected:.3f} against "
                     f"{b['actual']:.3f}   ({was:+.0%} → {now:+.0%})")
    return lines


__all__ = ["BANDS", "MIN_BAND", "MIN_FIT", "ROI_DEPTHS", "joined", "bands",
           "board_priced", "report_lines", "roi_lines", "fit", "fit_lines"]


if __name__ == "__main__":                       # pragma: no cover
    import sys
    from . import db as _db
    from .betting import MAX_CREDIBLE_EDGE
    from .likely import MIN_PROB
    argv = sys.argv[1:]
    conn = _db.connect()
    if "--roi" in argv:
        print("joining the likelihood board to the prices on the screen...")
        rows = board_priced(conn)
        f = getattr(board_priced, "funnel", {})
        if f:
            # THE POPULATION, STATED. Three earlier versions of this
            # report measured every replayed player rather than the ones
            # the page publishes, and nothing in the output said so.
            print(f"  {f['replayed']:,} replayed  ->  {f['priced']:,} with a "
                  f"real close  ->  {f['kept']:,} the board would show")
            print(f"     dropped: {f['thin']:,} under the {MIN_PROB:.0%} "
                  f"floor, {f['incredible']:,} disagreeing with the market "
                  f"by more than {MAX_CREDIBLE_EDGE:.0%}\n")
        else:
            print(f"  {len(rows):,} board rows with a real close\n")
        for line in roi_lines(rows):
            print(line)
    else:
        rows = joined(conn)
        if not rows:
            print("  no joined player-weeks — this box has no odds_history, "
                  "or no season is ingested")
            sys.exit(1)
        for line in report_lines(rows):
            print(line)
        print("\n  --roi to price the board instead of grading its bands.")
    conn.close()
