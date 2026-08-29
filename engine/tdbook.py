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


__all__ = ["BANDS", "MIN_BAND", "MIN_FIT", "joined", "bands", "report_lines",
           "fit", "fit_lines"]
