"""Fit the NFL prop calibrations against REAL book lines.

WHAT WENT WRONG, and it reached the board.

`calibrate.py` fits every prop market by walking the history through
`engine.logwalk`, which prices each game against a PROXY line — the
player's trailing average, rounded to the half and shaded half a point
down (`logwalk._naive_line`), at a synthetic -110. The correction it
learns is therefore "how wrong is the model about a trailing-average
line", and it is then applied live to decisions priced against a real
book's number. Those are different questions.

Yardage is right-skewed, so a line near the recent MEAN sits above the
MEDIAN and the under wins more often than half the time. Measured over
2,626 settled 2025 props with the model ignored entirely:

    rec_yds     59.0% under        pass_yds    53.4% under
    rush_yds    57.4% under        receptions  36.9% under

The fitted curves, read off the droplet on 2026-08-28:

    market      proxy under%   ceiling of the fitted correction
    rec_yds        59.0%         0.470
    rush_yds       57.4%         0.402
    pass_yds       53.4%         no curve at all
    receptions     36.9%         0.788

Rank for rank. The two markets whose ceiling fell BELOW 0.5 are exactly
the two whose proxy line skewed under hardest — and a correction that
cannot output more than 0.470 can never call an over more likely than
not, so those two markets could only ever be bet one way. Ethan found it
from the front end: a card siding UNDER 58.5 on a player projected for
71.6 yards.

The curve was not lying about its own training data. Against a trailing
average, a model claiming 60% over really is right only 40% of the time.
It is the wrong opponent, and nothing said so.

WHAT THIS DOES INSTEAD. `engine.backtest.backtest_from_stats` already
replays the season against harvested closing lines — it takes
`real_lines` and tags each settled prop `basis: "book"` or `"naive"`.
This fits the correction on the BOOK-priced subset alone, which is the
same question the live board asks. Markets without enough book-priced
history are refused outright and say so, because a correction fitted on
the wrong opponent is worse than none: the model runs uncorrected either
way, and only one of the two also inverts sides.

Standard library only.
"""

from __future__ import annotations

#: Book-priced settled props a market needs before its correction is
#: trusted. Deliberately higher than `calibrate.fit`'s own floor of 200:
#: a correction fitted here overrides one that is already live, and the
#: whole lesson of the proxy-line fit is that a confident number from the
#: wrong sample is more dangerous than no number.
MIN_BOOK_PAIRS = 400

#: The markets this fits. `anytime_td` is absent on purpose — it has no
#: line for a projection to be compared against, and `engine.tdbacktest`
#: fits it through its own front door.
MARKETS = ("receptions", "rec_yds", "rush_yds", "pass_yds")


def book_pairs(report, market: str = "") -> list:
    """``[(claimed, 0/1)]`` for the BOOK-priced settled props only.

    A push is excluded, the same way `calibrate.fit`'s own callers
    exclude it: a prop that landed exactly on the number decided nothing
    and carries no outcome to learn from.
    """
    out = []
    for s in (getattr(report, "settled", None) or []):
        if s.basis != "book":
            continue
        if market and s.market != market:
            continue
        if s.outcome is None:                     # push
            continue
        p = s.raw_prob if s.raw_prob is not None else s.hit_prob
        if p is None:
            continue
        out.append((float(p), int(s.outcome)))
    return out


def _tick(msg) -> None:
    """Progress, FLUSHED.

    A bare `print` is block-buffered whenever stdout is not a terminal,
    which is every backgrounded run — so a walk that ticks once a minute
    shows nothing at all until the process exits, and reads as hung.
    `run_tests.py` runs its children with `-u` and says why: "Python
    buffers stdout when it is not a tty, so every `ok <name>` a hung file
    had printed sat in an 8KB buffer and died with the process". Same
    trap, one flag away, and the default has to be the safe one because
    the caller is usually a person waiting.
    """
    print(msg, flush=True)


def fit(conn, season: int | None = None, weeks=None,
        markets=MARKETS, min_pairs: int = MIN_BOOK_PAIRS,
        path=None, log=_tick) -> dict:
    """Refit each market from book-priced history. Returns what changed.

    ``conn`` is the history DB — it supplies the harvested closes. The
    walk itself runs with the existing calibration DISABLED, for the
    reason `calibrate.py` gives: fitting a correction on already
    corrected input and then applying it to raw input compounds the
    correction every time it is re-run.
    """
    from . import calibrate as cal
    from .backtest import backtest_from_stats
    from .lab import nfl_real_lines, _seasons_to_try

    weeks = list(weeks or range(6, 18))
    real = nfl_real_lines(conn)
    if not real:
        return {"skipped": "no harvested NFL prop closes in this database — "
                           "nothing can be fitted against a real book line"}

    report = None
    for candidate in _seasons_to_try(season):
        try:
            with cal.disabled():
                report = backtest_from_stats(candidate, weeks,
                                             real_lines=real, log=log)
        except Exception as exc:                          # noqa: BLE001
            log(f"  propcal: {candidate} skipped — {exc}")
            continue
        if report.n:
            season = candidate
            break
        report = None
    if report is None:
        return {"skipped": "no season replayed"}

    out: dict = {"season": season, "fitted": {}, "refused": {}}
    fitted: dict = {}
    for market in markets:
        pairs = book_pairs(report, market)
        if len(pairs) < min_pairs:
            out["refused"][market] = (
                f"{len(pairs)} book-priced pairs, needs {min_pairs} — the "
                f"market keeps whatever correction it has rather than "
                f"gaining one fitted against a proxy line")
            continue
        c = cal.fit(pairs, sport="nfl", market=market)
        c.basis = cal.BASIS_HISTORY
        import datetime as _dt
        c.fitted_at = _dt.date.today().isoformat()
        fitted[f"nfl:{market}"] = c
        out["fitted"][market] = {
            "n": len(pairs), "temperature": c.temperature,
            "intercept": c.intercept,
            "knots": len((c.curve or {}).get("knots") or []),
            "brier_before": c.brier_before, "brier_after": c.brier_after,
        }
    if fitted:
        cal.save(fitted, path or cal.DEFAULT_PATH)
        cal.reset_cache()
    return out


def report_lines(out: dict) -> list:
    """The refit as log lines."""
    if out.get("skipped"):
        return [f"prop calibration: skipped — {out['skipped']}"]
    lines = [f"prop calibration: {out['season']} book-priced history"]
    for market, d in sorted((out.get("fitted") or {}).items()):
        shape = ("isotonic" if d["knots"] else
                 f"T={d['temperature']} bias={d['intercept']:+.2f}")
        lines.append(f"    {market}: {d['n']:,} pairs · {shape} · Brier "
                     f"{d['brier_before']:.4f} → {d['brier_after']:.4f}")
    for market, why in sorted((out.get("refused") or {}).items()):
        lines.append(f"    {market}: refused — {why}")
    return lines


__all__ = ["MIN_BOOK_PAIRS", "MARKETS", "book_pairs", "fit", "report_lines"]
