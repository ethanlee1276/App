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

import math

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


#: Blocks the walk-forward score is measured over. Each block is scored
#: by a correction fitted only on the pairs BEFORE it.
CV_BLOCKS = 4


def walk_forward_brier(pairs: list, min_train: int = 200) -> dict:
    """Score the correction on pairs it was not fitted on.

    WHY THE STORED NUMBERS CANNOT ANSWER THIS. `calibrate.fit` reports
    `brier_before`/`brier_after` over the WHOLE sample with the
    temperature fitted on that same sample. Its held-out judge exists
    only to pick the FORM (temperature vs isotonic vs nothing) and needs
    `MIN_HOLDOUT` = 400 test rows; at 409, 490 and 643 pairs it did not
    run on a single NFL prop market. So `brier_after` is in-sample, and
    comparing it to a zero-parameter constant is a race the two-parameter
    fit wins on noise alone — expected optimism is about 2k*var/n, which
    at n=409 is 0.0024 against a measured margin of 0.0029.

    Expanding window, never random: the pairs arrive in week order and a
    random split puts the same week on both sides, which is how a fit
    passes a test it should fail (`calibrate.HOLDOUT_FRACTION` says the
    same thing about the same data).

    The constant it is scored against is also honest — the base rate of
    the TRAINING pairs, not of the block being scored, because a
    baseline that peeks is not a baseline.
    """
    from . import calibrate as cal
    n = len(pairs)
    start = max(min_train, n // 2)
    if n - start < CV_BLOCKS:
        return {"ran": False, "reason": f"{n} pairs is too few to score "
                                        f"{CV_BLOCKS} blocks out of sample"}
    size = (n - start) / float(CV_BLOCKS)
    fit_err = base_err = 0.0
    diffs: list = []
    scored = 0
    for i in range(CV_BLOCKS):
        lo = start + int(round(i * size))
        hi = start + int(round((i + 1) * size))
        if hi <= lo:
            continue
        train, test = pairs[:lo], pairs[lo:hi]
        t, b = cal.fit_correction(train, min_samples=min_train)
        rate = sum(o for _p, o in train) / float(len(train))
        for raw, out in test:
            f = (cal.apply_temperature(raw, t, b) - out) ** 2
            c = (rate - out) ** 2
            fit_err += f
            base_err += c
            diffs.append(c - f)          # positive = the fit did better
        scored += len(test)
    if not scored:
        return {"ran": False, "reason": "no block could be scored"}
    mean = sum(diffs) / scored
    # Paired, because both scores are computed on the SAME pairs and the
    # pair-to-pair variation is shared. The unpaired spread of either
    # score alone is an order of magnitude larger and would call
    # everything a tie.
    var = (sum((d - mean) ** 2 for d in diffs) / (scored - 1)
           if scored > 1 else 0.0)
    se = math.sqrt(var / scored) if var > 0 else 0.0
    return {"ran": True, "n": scored, "trained_from": start,
            "fitted": fit_err / scored, "constant": base_err / scored,
            "margin": mean, "se": se,
            "t": (mean / se) if se else 0.0}


def discrimination(pairs: list) -> dict:
    """Does the model rank a hit above a miss? Calibration cannot say.

    THE QUESTION THE BRIER NUMBERS CANNOT REACH. A temperature is a
    monotone squeeze: it changes how confident a claim is, never which
    of two players the model prefers. So a market can fail every
    calibration test for two completely different reasons — the ordering
    is right and the confidence is wrong (recalibrate), or the ordering
    itself carries nothing (rebuild). rush_yds and rec_yds both fitted to
    the top of the grid and still lost to a constant, and that result is
    identical under both causes.

    AUC answers it directly: the chance a randomly chosen hit is ranked
    above a randomly chosen miss. 0.5 is a coin, below 0.5 means the
    model's preference is backwards, and it is untouched by any
    recalibration because it depends only on the order.

    Computed by ranks with ties averaged, which is the Mann-Whitney
    identity — no sampling, and it is exact rather than estimated.
    """
    pos = [p for p, o in pairs if o]
    neg = [p for p, o in pairs if not o]
    if not pos or not neg:
        return {"ran": False, "reason": "one outcome never occurred"}
    order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and pairs[order[j + 1]][0] == pairs[order[i]][0]:
            j += 1
        shared = (i + j) / 2.0 + 1.0                  # 1-based, ties averaged
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    rank_sum = sum(r for r, (_p, o) in zip(ranks, pairs) if o)
    n_pos, n_neg = len(pos), len(neg)
    auc = (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    # SE under the null of no discrimination (AUC = 0.5).
    se = math.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    return {"ran": True, "auc": auc, "se": se, "z": (auc - 0.5) / se,
            "hits": n_pos, "misses": n_neg}


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

    out: dict = {"season": season, "fitted": {}, "refused": {}, "dropped": []}
    fitted: dict = {}
    save_pairs({m: book_pairs(report, m) for m in markets}, season)
    stale: list = []
    stored = cal.load(path or cal.DEFAULT_PATH)
    raw_store = _stored_basis(path or cal.DEFAULT_PATH)
    for market in markets:
        key = f"nfl:{market}"
        pairs = book_pairs(report, market)
        if len(pairs) < min_pairs:
            why = f"{len(pairs)} book-priced pairs, needs {min_pairs}"
            if key in stored and raw_store.get(key) != cal.BASIS_BOOK:
                stale.append(key)
                why += (" — dropping the proxy-fitted correction it was "
                        "carrying, so the market runs uncorrected")
            else:
                why += " — the market keeps no correction"
            out["refused"][market] = why
            continue
        c = cal.fit(pairs, sport="nfl", market=market)
        c.basis = cal.BASIS_BOOK
        import datetime as _dt
        c.fitted_at = _dt.date.today().isoformat()
        fitted[key] = c
        rate = sum(o for _p, o in pairs) / float(len(pairs))
        out["fitted"][market] = {
            "n": len(pairs), "temperature": c.temperature,
            "intercept": c.intercept,
            "knots": len((c.curve or {}).get("knots") or []),
            "brier_before": c.brier_before, "brier_after": c.brier_after,
            "base_rate": rate, "baseline": rate * (1.0 - rate),
            "at_boundary": bool(c.at_boundary),
            "walk_forward": walk_forward_brier(pairs),
            "discrimination": discrimination(pairs),
        }
    if fitted:
        cal.save(fitted, path or cal.DEFAULT_PATH)
    if stale:
        out["dropped"] = cal.drop(stale, path or cal.DEFAULT_PATH)
    if fitted or stale:
        cal.reset_cache()
    return out


def _stored_basis(path) -> dict:
    """``{key: basis}`` straight off disk — `cal.load` drops the field."""
    import json
    from pathlib import Path
    try:
        raw = json.loads(Path(path).read_text())
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: (v.get("basis") or "") for k, v in raw.items()
            if isinstance(v, dict)}


#: Where the book-priced pairs are kept after a walk. Per-box and
#: gitignored, like everything else under data/models.
PAIRS_FILE = "propcal_pairs.json"


def pairs_path(path=None):
    from pathlib import Path
    from . import modelstate
    return Path(path) if path else Path(modelstate.path(PAIRS_FILE))


def save_pairs(by_market: dict, season, path=None):
    """Keep the pairs the walk produced, so the next question is free.

    The replay costs eight minutes and every question asked of it so far
    — is the margin real, is it significant, does the model even order
    the players correctly — has needed the same 1,542 pairs and nothing
    else. Re-deriving them per question is how an analysis loop turns
    into a day.
    """
    import json
    out = {"season": season,
           "markets": {m: [[round(p, 6), int(o)] for p, o in v]
                       for m, v in by_market.items()}}
    dest = pairs_path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out))
    return dest


def load_pairs(path=None) -> dict:
    """``{"season": int, "markets": {market: [(p, outcome)]}}`` or ``{}``."""
    import json
    src = pairs_path(path)
    if not src.is_file():
        return {}
    try:
        raw = json.loads(src.read_text())
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("markets"), dict):
        return {}
    return {"season": raw.get("season"),
            "markets": {m: [(float(p), int(o)) for p, o in v]
                        for m, v in raw["markets"].items()}}


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
        # THE LINE ABOVE IS NOT A VERDICT, and read alone it flatters.
        # A correction that erases the model entirely improves Brier
        # towards 0.25 from anywhere worse, so "0.2949 → 0.2533" can mean
        # "fixed" or "gave up" and the arrow looks the same either way.
        # Always predicting the base rate scores b(1-b) while knowing
        # NOTHING about any individual player, so that is the number a
        # fit has to beat before the word skill applies.
        # THE VERDICT COMES FROM THE WALK-FORWARD, NEVER FROM THE LINE
        # ABOVE. `brier_after` is scored on the pairs the temperature was
        # fitted to, so against a constant — which fits nothing — it wins
        # by roughly 2k*var/n on noise alone. The first version of this
        # block compared exactly those two numbers and called a 0.0029
        # in-sample margin skill, at a sample size whose fitting artifact
        # is 0.0024.
        wf = d.get("walk_forward") or {}
        if not wf.get("ran"):
            lines.append(f"        no out-of-sample score — {wf.get('reason')}")
        elif wf["margin"] <= 0:
            lines.append(
                f"        ⚠️  no skill out of sample — over {wf['n']:,} pairs "
                f"it had not seen, the correction scores {wf['fitted']:.4f} "
                f"against {wf['constant']:.4f} for a constant "
                f"{d['base_rate']:.1%}. It is not fixing this model, it is "
                f"cancelling it.")
        else:
            firm = ("" if abs(wf.get("t") or 0) >= 2 else
                    " — inside the noise, so this is not yet a measured edge")
            lines.append(
                f"        beats a constant by {wf['margin']:.4f} ± "
                f"{wf.get('se', 0):.4f} (t={wf.get('t', 0):+.1f}) out of "
                f"sample, over {wf['n']:,} unseen pairs{firm}")
        # ORDERING, which no temperature can change and no Brier
        # number separates from confidence. A market that lost to a
        # constant needs rebuilding if this is 0.5 and recalibrating if
        # it is not, and those are months apart.
        #
        # THE DIAGNOSIS DEPENDS ON BOTH NUMBERS, not on this one alone.
        # The first version of this block read the AUC by itself and
        # printed "the problem is the model and not its confidence"
        # underneath receptions — a market that had just beaten a
        # constant out of sample at t=+2.4. A borderline AUC on a market
        # that PASSED is weak discrimination, which is a different
        # sentence from a broken model, and printing the second one there
        # made the report argue with itself.
        g = d.get("discrimination") or {}
        if g.get("ran"):
            passed = wf.get("ran") and (wf.get("t") or 0) >= 2
            if g["z"] < -2:
                verdict = ("BACKWARDS — it ranks misses above hits, and no "
                           "recalibration can fix an ordering")
            elif g["z"] <= 2:
                verdict = "too close to a coin to call at this sample"
                if not passed:
                    verdict += (", and the market failed out of sample too — "
                                "so the ordering is the problem and "
                                "recalibration cannot reach it")
                else:
                    verdict += (", so the edge above rests on the "
                                "calibration rather than on strong ranking")
            else:
                verdict = "it ranks hits above misses"
            lines.append(f"        AUC {g['auc']:.3f} (z={g['z']:+.1f}) — "
                         f"{verdict}")
        base = d.get("baseline")
        if base is not None and d["brier_after"] < base <= d["brier_before"]:
            lines.append(
                f"        (in sample it beat a constant by "
                f"{base - d['brier_after']:.4f}; that number is fitted to "
                f"the pairs it is scored on and is not evidence)")
        if d.get("at_boundary"):
            lines.append(
                "        ⚠️  fit ran to the edge of the search grid — the "
                "data wanted more correction than the grid allows, so "
                "`is_reliable` fails this market and the board passes it")
    # FOUR MARKETS WERE TESTED, so a single t of 2 is not the 1-in-20 it
    # looks like. Said once at the bottom rather than hedged into every
    # line, because the correction is to the reader's threshold and not
    # to any one market's number.
    tested = len(out.get("fitted") or {})
    claimed = [m for m, d in (out.get("fitted") or {}).items()
               if ((d.get("walk_forward") or {}).get("t") or 0) >= 2]
    if claimed and tested > 1:
        lines.append(f"    ({tested} markets were tested, so t=2 on any one "
                     f"of them is not a 1-in-20 result — "
                     f"{', '.join(sorted(claimed))} clears the bar but sits "
                     f"near it, and a second season is what would settle it)")
    for market, why in sorted((out.get("refused") or {}).items()):
        lines.append(f"    {market}: refused — {why}")
    for key in (out.get("dropped") or []):
        lines.append(f"    dropped {key} — it was fitted against a proxy line")
    return lines


__all__ = ["MIN_BOOK_PAIRS", "MARKETS", "book_pairs", "fit",
           "report_lines", "walk_forward_brier", "discrimination",
           "save_pairs", "load_pairs", "pairs_path"]
