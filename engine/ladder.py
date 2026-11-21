"""Is the grade ladder a conviction, or only a ranking?

`engine.backtest` has computed the answer per grade since 2026-08-27 and
prints it at the bottom of a terminal report:

    A              59 bets   claimed 54.2% → landed 57.6%
    B+            218 bets   claimed 53.8% → landed 57.8%
    ⚠️  the top band lands no more often than the bottom one —
       this ladder is a ranking, not a conviction

Pooled across four ingested NFL seasons the reading is not marginal:

    season   A lands   B+ lands
    2022      46.4%     50.8%
    2023      49.1%     55.7%
    2024      57.6%     57.8%
    2025      45.9%     61.1%

    A   123/248 = 49.6% against a claimed 54.2%
    B+  432/765 = 56.5% against a claimed 53.8%

WHY THIS MODULE EXISTS. That measurement reached a terminal and stopped.
The BOARD went on presenting A above B+, because the ladder's order is
hard-coded and nothing on the pricing path had ever seen the record. A
reader opening the app leads with the A's — the band that has landed
below its own claim in three of four seasons — and the page tells them
that band is the confident one.

It is the same failure this codebase keeps finding in itself: a rule
measured in one place and enforced nowhere. `engine.gamecal` fixed it for
the market haircut by persisting the fit where the pricing path reads it;
this does the same for the conviction ladder.

WHAT IT DOES NOT DO. It does not reorder, resize or suppress anything.
The stake stopped depending on the grade when Kelly-times-grade was
retired (`engine.staking`, on a record where conviction was
anti-correlated with results), so there is no size here to cut — A and
B+ already take the same fraction. What is left is a CLAIM, made to a
reader, and this makes the board tell the truth about it.

Whether the ladder should be reordered is a `engine.prereg` question and
is registered as one. A note is not a decision.

Standard library only.
"""

from __future__ import annotations

import json
import os

from . import feedstate as _feedstate

STATE_PATH = _feedstate.path("ladder.json")

#: Top to bottom, as the board presents them.
GRADE_ORDER = ("A+", "A", "B+")

#: Settled bets in a band before it may be read at all. A band with forty
#: bets can be eight points out of order on noise alone, and a warning
#: that fires on noise trains a reader to ignore warnings.
MIN_BAND_N = 100

#: How far out of order a pair must be before the board says so, in
#: landing rate. Below this the bands are indistinguishable and calling
#: that an inversion would be reading the last decimal place.
MIN_GAP = 0.02


def _blank(value) -> bool:
    return value is None or value == ""


def pooled(reports: list) -> dict:
    """``{grade: {n, claimed, landed}}`` over several seasons' reports.

    Takes `engine.backtest.BacktestReport.grade_calibration` dicts and
    pools them by weight, because four seasons of one band is the sample
    the question needs and one season of it is not.
    """
    totals: dict = {}
    for bands in reports or []:
        for grade, band in (bands or {}).items():
            n = int(band.get("n") or 0)
            if n <= 0:
                continue
            slot = totals.setdefault(grade, {"n": 0, "claimed": 0.0,
                                             "wins": 0.0})
            slot["n"] += n
            slot["claimed"] += float(band.get("claimed") or 0.0) * n
            slot["wins"] += float(band.get("landed") or 0.0) * n
    out: dict = {}
    for grade, slot in totals.items():
        n = slot["n"]
        out[grade] = {"n": n,
                      "claimed": round(slot["claimed"] / n, 4),
                      "landed": round(slot["wins"] / n, 4)}
        out[grade]["gap"] = round(out[grade]["landed"]
                                  - out[grade]["claimed"], 4)
    return out


def inversion(bands: dict) -> dict | None:
    """The worst out-of-order pair in the ladder, or None.

    "Out of order" means a band the board puts ABOVE another one lands
    LESS often than it. Only bands with `MIN_BAND_N` behind them are
    compared, and only gaps past `MIN_GAP` count.
    """
    ranked = [(g, bands[g]) for g in GRADE_ORDER
              if g in (bands or {}) and int(bands[g].get("n") or 0) >= MIN_BAND_N]
    worst = None
    for i, (upper, up) in enumerate(ranked):
        for lower, low in ranked[i + 1:]:
            gap = float(low.get("landed") or 0.0) - float(up.get("landed") or 0.0)
            if gap >= MIN_GAP and (worst is None or gap > worst["gap"]):
                worst = {"upper": upper, "lower": lower, "gap": round(gap, 4),
                         "upper_landed": up.get("landed"),
                         "lower_landed": low.get("landed"),
                         "upper_claimed": up.get("claimed"),
                         "upper_n": up.get("n"), "lower_n": low.get("n")}
    return worst


def note_for(sport: str, path: str | None = None) -> str | None:
    """The sentence a card or a board should carry, or None.

    None when the ladder has never been measured, when the sample is too
    thin, and — the case that matters — when the ladder IS ordered. A
    note that only ever appears is not information.
    """
    bands = load(path).get(sport) or {}
    bad = inversion(bands)
    if not bad:
        return None
    return (f"Measured on four seasons: {bad['upper']} props land "
            f"{bad['upper_landed']:.1%} against a claimed "
            f"{bad['upper_claimed']:.1%}, while {bad['lower']} — the band "
            f"below — lands {bad['lower_landed']:.1%} on "
            f"{bad['lower_n']:,} bets. This ladder ranks; it does not "
            f"promise, and the top of it is not the safe end")


def load(path: str | None = None) -> dict:
    """``{sport: {grade: band}}``, or ``{}``. Never raises."""
    try:
        with open(path or STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data.get("sports", {}) if isinstance(data, dict) else {}


def save(sport: str, bands: dict, path: str | None = None) -> int:
    """Merge one sport's measured ladder into the store.

    Merge, not replace: each sport's ladder is measured by its own
    backtest on its own cadence, and one of them running must not erase
    the others.
    """
    path = path or STATE_PATH
    try:
        current = load(path)
        current[str(sport)] = bands
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"sports": current}, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)      # atomic: a torn file is worse than none
        return sum(int(b.get("n") or 0) for b in bands.values())
    except OSError:
        return 0


def refresh(seasons=None, weeks: str = "6-17", path: str | None = None) -> list:
    """Re-measure the NFL ladder from ingested history. Log lines out.

    Slow — a season is minutes, because it replays every prop week by
    week — so this belongs in the weekly deep refit and not in a nightly.
    """
    from .backtest import backtest_from_stats
    from .rules import RuleConfig

    seasons = list(seasons or ())
    if not seasons:
        import datetime as _dt
        year = _dt.date.today().year
        seasons = [year - n for n in (4, 3, 2, 1)]
    lo, hi = (int(x) for x in str(weeks).split("-"))
    window = list(range(lo, hi + 1))
    reports, skipped = [], []
    for season in seasons:
        try:
            report = backtest_from_stats(int(season), window, RuleConfig())
        except Exception as exc:                          # noqa: BLE001
            # A season with no ingested weekly stats is a skip, not a
            # failure — the fit reports what it could reach.
            skipped.append(f"{season}: {exc}")
            continue
        if report.grade_calibration:
            reports.append(report.grade_calibration)
    if not reports:
        return [f"grade ladder: nothing to measure ({'; '.join(skipped[:2])})"]
    bands = pooled(reports)
    save("nfl", bands, path)
    bad = inversion(bands)
    lines = [f"grade ladder: nfl measured over {len(reports)} season(s) — "
             + ", ".join(f"{g} {bands[g]['landed']:.1%} on {bands[g]['n']}"
                         for g in GRADE_ORDER if g in bands)]
    lines.append("  ⚠️  the ladder is out of order: " + note_for("nfl", path)
                 if bad else "  the ladder is ordered — no note on the board")
    return lines


__all__ = ["STATE_PATH", "GRADE_ORDER", "MIN_BAND_N", "MIN_GAP", "pooled",
           "inversion", "note_for", "load", "save", "refresh"]
