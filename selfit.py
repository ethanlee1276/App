#!/usr/bin/env python3
"""Fit the selection correction, and try to fail it out of sample.

    python3 selfit.py                   # fit, hold out, report. Writes nothing.
    python3 selfit.py --sport mlb

This is steps 2 and 3 of docs/SELECTION_CORRECTION.md §10. It does NOT
apply anything and does not touch any store — step 4 is a separate
decision, and §8 says out loud that applying this may empty the board.

WHY THERE IS A HELD-OUT HALF AT ALL
-----------------------------------
A temperature fitted on a sample will improve that sample. That is what
fitting is; it demonstrates nothing. `guardfit` already produced one
confident recommendation off an in-sample fit that turned out to be an
artifact of forcing a line through a hinge, and the only reason it was
caught was that somebody checked the model against data it had not seen.

So the journal is split by date. The correction is fitted on the earlier
half and measured on the later half, which it has never touched.

THE BAR, WRITTEN DOWN BEFORE THE ANSWER
---------------------------------------
Chosen from the arithmetic, not from the result. The held-out half is
about 124 bets claiming near 58%, so the 2-sigma bar on its gap is roughly

    2 * sqrt(0.58 * 0.42 / 124) = +/- 8.9 points

which is wide enough that "it got a bit better" would be indistinguishable
from noise. Hence :data:`PASS_GAP` and :data:`FAIL_GAP`:

  * held-out gap falls below **+5.0 points** AND at least half the original
    gap is gone -> PASS. Ship-able, subject to §6's caps.
  * held-out gap stays at or above **+8.0 points** -> FAIL. The correction
    is fitting noise. §9 says abandon.
  * anything between -> INCONCLUSIVE. Not a soft pass. Wait for bets.

These constants are the contract. Changing them after seeing a run is
exactly the move this file exists to prevent, so they live at the top
where a diff shows them moving.

HOW OFTEN THIS TEST IS RIGHT — measured, not assumed
----------------------------------------------------
Simulated over 300 synthetic journals with claims spread 0.50-0.70, which
is roughly the real board's shape:

  ================================  ======  =============  ======
  truth                             PASS    INCONCLUSIVE   FAIL
  ================================  ======  =============  ======
  a real 12-point over-claim, 124   55%     26%            15%
  a real 12-point over-claim, 250   70%     20%             9%
  honest model (no over-claim)       6%      5%            11%
  ================================  ======  =============  ======

(The honest row's remaining 79% is NOTHING TO CORRECT, which is the right
answer there.)

Read that before reading any verdict this prints. **At the journal's
current size the test finds a real effect only about half the time**, and
it returns FAIL on a genuinely correctable one 15% of the time. A FAIL is
therefore not proof the correction is worthless; it is one draw. A PASS is
worth more, because the false-positive rate on an honest model is 6%.

The other thing that simulation showed: the fitted temperature is barely
identified at this sample size. Its 5th-95th range across those runs was
**0.70 to 6.00** — the top of which is the search grid's ceiling, i.e. no
answer at all. §6's cap is not a nicety; it is load-bearing, and a fit
that lands on the boundary should never be shipped.

WHAT IT FITS
------------
One pooled (S, c) per sport, not per market — §5. Selection bias is a
property of the selection process, not of the market, and 247 bets will
not support four separate pairs.

Standard library only.
"""

from __future__ import annotations

import argparse
import math
import sys

from engine import calibrate as cal
from engine import journalfit as jf
from engine import ledger

#: Held-out gap below this, with at least HALVED of the gap removed, passes.
PASS_GAP = 0.050
#: Held-out gap at or above this fails outright.
FAIL_GAP = 0.080
#: …and a pass must also remove at least this share of the original gap.
#: Without it, a journal that started at +5.5 points could "pass" by not
#: moving at all.
HALVED = 0.50
#: A mid-journal calibration change only threatens the comparison if
#: enough rows carry it. Eleven rows in 126 cannot move a half's mean claim
#: by more than about 1.8 points however hard they are shrunk, so below
#: this share the change is reported and explicitly not blamed.
BASIS_SHARE = 0.20
#: Fewer than this on either side of the date split and the comparison is
#: not worth running. Well below journalfit's 200: this is a diagnostic
#: that ships nothing, and the alternative to a wide-barred answer here is
#: no answer at all.
MIN_SIDE = 80


def load(conn, sport: str, category: str = "main") -> list[dict]:
    """Settled, journalled, carrying a claim and a date. Selected side only.

    The correction is FOR the selected population — that is the whole
    hypothesis — so `loose` is not training data. It reappears later as a
    control, never as a fit input.
    """
    q = ("SELECT sport, market, side, hit_prob, status, date, ts, "
         "cal_temp, cal_bias "
         "FROM bets WHERE status IN ('won','lost') AND hit_prob IS NOT NULL "
         "AND category=?")
    args: list = [category]
    if sport and sport != "all":
        q += " AND sport=?"
        args.append(sport)
    rows = [dict(r) for r in conn.execute(q, args)]
    return sorted((r for r in rows if r.get("date")), key=lambda r: r["date"])


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split by DATE, never by row index.

    Splitting on the row index would cut a slate in half and put the same
    night on both sides of the boundary. Nights are correlated — one
    pitcher, one park, one weather — so that leaks the thing being held
    out. Whole dates only, at the date closest to a 50/50 split.
    """
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return rows, []
    best, best_diff = dates[0], len(rows)
    for d in dates[1:]:
        n_early = sum(1 for r in rows if r["date"] < d)
        diff = abs(n_early - (len(rows) - n_early))
        if diff < best_diff:
            best, best_diff = d, diff
    return ([r for r in rows if r["date"] < best],
            [r for r in rows if r["date"] >= best])


def _pairs(rows: list[dict]) -> list[tuple[float, int]]:
    """Restated as P(over), the one quantity the fit runs on."""
    out = []
    for r in rows:
        pair = jf.as_over(r["hit_prob"], r["side"], r["status"])
        if pair is not None:
            out.append(pair)
    return out


def corrected(r: dict, temp: float, icept: float) -> float:
    """A row's claim with the selection layer applied, back in its own
    orientation.

    The fit lives in P(over) space; a bet on the UNDER claims 1-p there and
    must come back through the same mirror, or the correction lands with
    the wrong sign on half the board.
    """
    p = float(r["hit_prob"])
    side = (r.get("side") or "").strip().lower()
    if side.startswith("u"):
        return 1.0 - cal.apply_temperature(1.0 - p, temp, icept)
    return cal.apply_temperature(p, temp, icept)


def measure(rows: list[dict], temp: float = 1.0, icept: float = 0.0) -> dict:
    """Claimed vs landed, with the Poisson-binomial bar — same statistic
    selcheck reports, so the two can be read against each other."""
    n = len(rows)
    if not n:
        return {"n": 0, "claimed": 0.0, "landed": 0.0, "gap": 0.0, "se": 0.0}
    ps = [corrected(r, temp, icept) for r in rows]
    claimed = sum(ps) / n
    landed = sum(1 for r in rows if r["status"] == "won") / n
    var = sum(p * (1 - p) for p in ps)
    return {"n": n, "claimed": claimed, "landed": landed,
            "gap": claimed - landed,
            "se": math.sqrt(var) / n if var > 0 else 0.0}


def compose(rows: list[dict], temp: float = 1.0, icept: float = 0.0) -> dict:
    """What a half is MADE OF, and how hard the correction bites it.

    The first real run needed this and did not have it. The fitted pair
    moved the in-sample gap 11.7 points and the held-out gap 3.3, and a
    single correction cannot bite that differently unless the two halves
    differ in composition. They did: a negative intercept is a lean toward
    the UNDER, so it cuts an OVER claim by 6.5-19.7 points and leaves an
    UNDER claim almost alone. Without this table the run looks like a
    correction that failed to generalise, when what it really shows is a
    correction that learned a direction rather than a shrink.
    """
    n = len(rows)
    if not n:
        return {"n": 0}
    unders = sum(1 for r in rows
                 if (r.get("side") or "").strip().lower().startswith("u"))
    raw = sum(float(r["hit_prob"]) for r in rows) / n
    adj = sum(corrected(r, temp, icept) for r in rows) / n
    # Which DEEP correction was live when each row was logged. hit_prob is
    # the shipped claim, i.e. already through calibrate.py's temperature —
    # so it is only a consistent quantity while that temperature holds
    # still. When it moves mid-journal the two halves are denominated in
    # different things, and a selection layer fitted across the change is
    # fitted on a moving target. journalfit has un-corrected per row since
    # the refit-capture work for exactly this reason; this reports whether
    # the same hazard is present here.
    temps = [float(r["cal_temp"]) for r in rows if r.get("cal_temp") is not None]
    return {"n": n, "unders": unders, "p_under": unders / n,
            "claim_raw": raw, "claim_adj": adj, "moved": adj - raw,
            "dates": len({r["date"] for r in rows if r.get("date")}),
            "n_cal": len(temps),
            "cal_temp": (sum(temps) / len(temps)) if temps else None}


def _fit_pair(pairs, fitter, min_samples):
    """One place that turns training rows into (temperature, intercept).

    Both estimators take a `fitter` so the SAME held-out machinery judges
    both functional forms. Giving the shift form its own copy of the
    estimators would be how the two quietly stop being comparable.
    """
    if fitter == "shift":
        return fit_shift(pairs, min_samples)
    c = cal.fit(pairs, sport="mlb", market="selection", min_samples=min_samples)
    return c.temperature, c.intercept


def crossval(rows: list[dict], folds: int = 4, fitter: str = "temp") -> dict:
    """Every bet held out exactly once, folds cut on whole dates.

    **This was added AFTER the single split returned FAIL, and that has to
    stay attached to it.** Changing the statistic once you have seen the
    answer is the move this file exists to prevent, so the single split
    stays the pre-registered verdict and this is reported beside it as a
    second opinion, never in place of it. If the two disagree the reading
    is "unresolved, get more bets" — not "it passed on the better test".

    What it genuinely buys, and the reason it is worth having at all: the
    single split judged 126 held-out bets and threw the other 121 away.
    This judges all 247 out of sample, and averages over the luck of where
    the boundary happened to land — which mattered here, because balancing
    the split by bet count put three days on one side and ten on the other.
    """
    dates = sorted({r["date"] for r in rows if r.get("date")})
    if len(dates) < folds * 2:
        return {"n": 0, "folds": 0}
    blocks: list[list[str]] = [[] for _ in range(folds)]
    for i, d in enumerate(dates):
        blocks[i % folds].append(d)

    held: list[dict] = []
    fits = []
    for blk in blocks:
        out = [r for r in rows if r["date"] in set(blk)]
        train = [r for r in rows if r["date"] not in set(blk)]
        pairs = _pairs(train)
        if len(pairs) < MIN_SIDE or not out:
            continue
        t, b = _fit_pair(pairs, fitter, MIN_SIDE)
        fits.append((t, b, t >= 6.0))
        for r in out:
            held.append({**r, "_p": corrected(r, t, b)})
    if not held:
        return {"n": 0, "folds": 0}

    n = len(held)
    landed = sum(1 for r in held if r["status"] == "won") / n
    adj = sum(r["_p"] for r in held) / n
    raw = sum(float(r["hit_prob"]) for r in held) / n
    var = sum(r["_p"] * (1 - r["_p"]) for r in held)
    return {"n": n, "folds": len(fits), "fits": fits,
            "gap_before": raw - landed, "gap_after": adj - landed,
            "se": math.sqrt(var) / n if var > 0 else 0.0}


def walkforward(rows: list[dict], min_train: int = MIN_SIDE,
                fitter: str = "temp") -> dict:
    """Rolling origin: fit on every date BEFORE d, judge date d, roll on.

    Every prediction is made by a fit that saw only earlier dates, so this
    is what a live board would actually have done — refit nightly, bet the
    next slate — rather than what a retrospective split can arrange.

    **IT WAS BUILT ON A PREMISE THE SIMULATION THEN REFUTED, and that
    belongs here rather than in a commit message nobody re-reads.** The
    reasoning was: the board drifted (claim level 64.9% to 51.2%), so the
    single split is comparing two different populations and ``crossval``
    interleaves dates and therefore leaks the future. Measured over 60
    synthetic journals per world, 14 dates, 20 bets a date:

        honest board, drift 14 pts        PASS   FAIL
          single split                      4     20
          interleaved CV                   10      0
          walk-forward                      9      3

        honest board, no drift            PASS   FAIL
          single split                      4     23
          interleaved CV                    7      0
          walk-forward                      7     11

    Drift barely moves any of them: 4 to 4, 7 to 10, 7 to 9. **The drift
    is not what made the real hold-out fail**, and any explanation resting
    on it — including the one this function was written to fix — is not
    supported. (The simulation drifts claim level only. The real board also
    moved its UNDER share 44% to 25%, which this does not model, so the
    door is not fully closed.)

    What the same sweep says about power, with a real +12 to find:

        over-claim +12, drift            PASS   FAIL
          single split                     24     20
          interleaved CV                   59      0
          walk-forward                     42      4

    So walk-forward is **not** strictly better than what it was meant to
    replace. It has a similar false-alarm rate to the interleaved CV and
    less power. It is kept for one property the table shows plainly:
    interleaved CV returns FAIL **zero times in any world**, including
    worlds where the correction actively damages the held-out half. It
    cannot convict. Walk-forward can, and it is causal, so it is reported
    as a third opinion — not as the better test.

    **THE READING THAT MATTERS MOST.** All three carry a false-alarm rate
    between 7% and 17%. ``PASS_GAP`` and ``FAIL_GAP`` are absolute
    thresholds on a gap, never calibrated as a significance level, so a
    lone PASS is far weaker evidence than the word suggests — roughly one
    honest journal in seven produces one. Agreement across all three is the
    only reading worth acting on, and a single PASS should move nothing.

    Cost, stated plainly: the early dates are spent as training and never
    judged, and each fit sees less data than the full journal. So NOTHING
    TO CORRECT here means "not enough yet", never "nothing there".

    **Added after the single split returned FAIL, like ``crossval`` before
    it, and it carries the same standing.** It does not replace the
    pre-registered verdict and does not overturn it. Its bars are the same
    PASS_GAP / FAIL_GAP / HALVED, so it is a different estimator of the
    same pre-registered quantity rather than a new question asked until one
    of them says yes. If it disagrees with the single split, the reading is
    "unresolved, get more bets".
    """
    dates = sorted({r["date"] for r in rows if r.get("date")})
    if len(dates) < 3:
        return {"n": 0, "steps": 0}

    held: list[dict] = []
    fits = []
    for i, d in enumerate(dates):
        if i == 0:
            continue
        train = [r for r in rows if r["date"] < d]
        out = [r for r in rows if r["date"] == d]
        pairs = _pairs(train)
        if len(pairs) < min_train or not out:
            continue
        t, b = _fit_pair(pairs, fitter, min_train)
        fits.append((d, len(train), t, b))
        for r in out:
            held.append({**r, "_p": corrected(r, t, b)})
    if not held:
        return {"n": 0, "steps": 0, "dates": len(dates)}

    n = len(held)
    landed = sum(1 for r in held if r["status"] == "won") / n
    adj = sum(r["_p"] for r in held) / n
    raw = sum(float(r["hit_prob"]) for r in held) / n
    var = sum(r["_p"] * (1 - r["_p"]) for r in held)
    return {"n": n, "steps": len(fits), "fits": fits, "dates": len(dates),
            "gap_before": raw - landed, "gap_after": adj - landed,
            "se": math.sqrt(var) / n if var > 0 else 0.0}


def fit_shift(pairs: list[tuple[float, int]],
              min_samples: int = MIN_SIDE) -> tuple[float, float]:
    """Fit the INTERCEPT alone, temperature pinned at 1.0.

    **Why a second functional form exists at all**, measured on the real
    journal 2026-08-07 and not guessed:

    ``apply_temperature`` is ``logit(p)/T + c``, and the ``/T`` term has 50%
    as a fixed point — it moves a claim in proportion to how far that claim
    already sits from even money. This board does not sit far from even
    money. 92 of 123 held-out bets claim under 55%, averaging 47.9%, and
    they landed 32.6%.

    On that band the fitted (T 3.6, c -0.14) did this:

        raw                     47.9%
        temperature alone       49.4%     <- UP, toward 50%
        intercept alone         44.4%
        both, as fitted         45.9%
        what actually landed    32.6%

    The temperature does not merely fail to help below 50%, it pushes the
    other way and cancels part of the intercept. The band came out +15.2%
    before and +15.3% after: the correction made the largest part of the
    held-out half fractionally worse.

    Meanwhile the early half it trained on claims 64.1%, where the same
    temperature moves 10 points on its own. So Brier minimisation bought
    spread — the parameter that pays on the training half — and starved the
    only parameter that can move a claim sitting at even money. An
    intercept of about -0.64 would have matched what the big band landed;
    the joint fit chose -0.14.

    ``calibrate.apply_temperature`` has warned about exactly this since it
    was written: "a model whose predictions cluster near 50% while outcomes
    run at 42% cannot be corrected by temperature at any value". The run
    printed the other half of that signature too — the fold temperatures
    reached the grid ceiling at 6.00.

    So this is not a new test of the same model, it is the model the
    diagnosis points at, judged by the same pre-registered bars.
    """
    if len(pairs) < min_samples:
        return 1.0, 0.0
    best_b, best = 0.0, cal.brier(pairs, 1.0, 0.0)
    b = -1.5
    while b <= 1.5001:
        s = cal.brier(pairs, 1.0, b)
        if s < best:
            best, best_b = s, b
        b += 0.01
    return 1.0, best_b


#: Claim-level bands for :func:`by_claim`. A global temperature assumes the
#: over-claim is the same shape everywhere; these are how that gets checked
#: rather than assumed.
CLAIM_BANDS = ((0.0, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 1.0))


def by_claim(rows: list[dict], temp: float = 1.0,
             icept: float = 0.0) -> list[dict]:
    """The gap inside each claim band, before and after the correction.

    The reason this is worth its lines: the board's drift was measured as a
    fall in CLAIM LEVEL, 64.9% to 51.2%. If the over-claim is uniform in
    claim level, that drift is harmless to a global correction and the
    single split's FAIL was about something else. If instead the gap is
    concentrated at high claims, a correction fitted on an early
    high-claiming board is being tested on a late low-claiming one, and one
    temperature was never the right shape.

    Those are different diagnoses with different repairs, and no amount of
    staring at a pooled number separates them.
    """
    out = []
    for lo, hi in CLAIM_BANDS:
        band = [r for r in rows if lo <= float(r["hit_prob"]) < hi]
        if not band:
            continue
        raw = measure(band)
        adj = measure(band, temp, icept)
        out.append({"lo": lo, "hi": hi, "n": raw["n"],
                    "claimed": raw["claimed"], "landed": raw["landed"],
                    "gap_before": raw["gap"], "gap_after": adj["gap"],
                    "se": raw["se"]})
    return out


def verdict(before: float, after: float) -> tuple[str, str]:
    """The pre-registered decision. No arguments beyond the two numbers, so
    it cannot quietly consult anything else.

    **Every bar here is on the ABSOLUTE gap, and the first cut of this
    function got that wrong.** It compared the signed gap against a
    positive threshold, so driving the claim far BELOW what landed counted
    as success: a synthetic where the model over-claimed early and was
    honest later had the correction take a clean -1.1% held-out gap to
    -18.2%, and the verdict called it INCONCLUSIVE rather than harmful. An
    under-claim is not a free lunch — it is the same miscalibration with
    the sign flipped, and it silently kills good bets instead of taking bad
    ones. Same absolute-vs-relative family of fault as the loss miner's
    closure bar and the Lab's ROI tile.
    """
    b, a = abs(before), abs(after)
    removed = (b - a) / b if b > 0 else 0.0
    # Damage is checked BEFORE "nothing to correct", and the order matters:
    # the first cut had them the other way round, so a correction that took
    # an already-honest -1.1% held-out half to -18.2% was excused as having
    # nothing to demonstrate. Wrecking a clean half is the loudest possible
    # failure, not an absence of evidence.
    #
    # "Materially" is what keeps that from being hair-trigger: a gap that
    # drifts from +1.0% to +1.5% is worse and means nothing, so the damage
    # must also carry the result past the pass line before it convicts.
    if a > b and a >= PASS_GAP:
        return "FAIL", (f"the correction made the held-out half WORSE: "
                        f"{before:+.1%} -> {after:+.1%}")
    if b < PASS_GAP:
        return "NOTHING TO CORRECT", (
            f"the held-out half was already within {PASS_GAP:.1%} "
            f"({before:+.1%}); this journal cannot demonstrate anything")
    if a >= FAIL_GAP:
        return "FAIL", (f"held-out gap {after:+.1%} is {a:.1%} from honest, "
                        f"at or past the {FAIL_GAP:.1%} fail line")
    if a < PASS_GAP and removed >= HALVED:
        return "PASS", (f"held-out gap {after:+.1%} is within {PASS_GAP:.1%} "
                        f"of honest and {removed:.0%} of the miss is gone")
    return "INCONCLUSIVE", (
        f"held-out gap {after:+.1%} sits between the bars "
        f"({PASS_GAP:.1%} / {FAIL_GAP:.1%}); {removed:.0%} of the miss removed")


def report(conn, sport: str = "mlb") -> int:
    rows = load(conn, sport)
    if len(rows) < 2 * MIN_SIDE:
        print(f"Need {2 * MIN_SIDE} settled selected bets; have {len(rows)}.")
        return 0
    early, late = split(rows)
    if len(early) < MIN_SIDE or len(late) < MIN_SIDE:
        print(f"Date split is too lopsided: {len(early)} early, {len(late)} "
              f"late, and {MIN_SIDE} is the minimum per side.")
        return 0

    print("=" * 74)
    print(f"SELECTION CORRECTION — fit on the past, tested on the future")
    print("=" * 74)
    print(f"  {sport}   {len(rows)} settled selected bets   "
          f"{rows[0]['date']} to {rows[-1]['date']}")
    print(f"  fit on   {len(early):4} bets  {early[0]['date']} to {early[-1]['date']}")
    print(f"  held out {len(late):4} bets  {late[0]['date']} to {late[-1]['date']}")
    print()
    print(f"  BAR, fixed before this ran:  pass under {PASS_GAP:.1%} with "
          f"{HALVED:.0%}+ removed;  fail at {FAIL_GAP:.1%}+")
    print()

    pairs = _pairs(early)
    if len(pairs) < MIN_SIDE:
        print(f"  Only {len(pairs)} of {len(early)} early bets could be "
              f"restated as P(over) — nothing to fit.")
        return 0
    c = cal.fit(pairs, sport=sport, market="selection", min_samples=MIN_SIDE)
    print("=" * 74)
    print("WHAT THE EARLY HALF ASKS FOR")
    print("=" * 74)
    print(f"  temperature {c.temperature:.4f}   intercept {c.intercept:+.4f}"
          f"   on {c.samples} bets")
    print(f"  Brier {c.brier_before:.5f} -> {c.brier_after:.5f}")
    if c.at_boundary:
        print("  ** the fit ran to the edge of the search grid. That is not a")
        print("     parameter, it is a failure to converge, and §6's cap would")
        print("     be binding immediately. Treat what follows as suspect. **")
    print()

    for label, part in (("early (fitted on)", early), ("held out", late)):
        b = measure(part)
        a = measure(part, c.temperature, c.intercept)
        print(f"  {label:20} n {b['n']:4}   "
              f"gap {b['gap']:+6.1%} -> {a['gap']:+6.1%}   "
              f"(2σ ±{2 * a['se']:.1%})")
    print()
    print("  The first line is the correction grading its own homework and is")
    print("  expected to improve. Only the second line is evidence.")
    print()

    # Composition. One correction cannot move two halves by different
    # amounts unless the halves differ — and if it does, the interesting
    # question stops being "did it generalise" and becomes "what did it
    # actually learn".
    print("=" * 74)
    print("WHAT EACH HALF IS MADE OF")
    print("=" * 74)
    print("                       n   days   UNDERs   mean claim   after   moved"
          "   deep T")
    print("  " + "-" * 76)
    ce = compose(early, c.temperature, c.intercept)
    cl = compose(late, c.temperature, c.intercept)
    for label, x in (("early (fitted on)", ce), ("held out", cl)):
        dt = (f"{x['cal_temp']:.2f} ({x['n_cal']}/{x['n']})"
              if x["cal_temp"] is not None else "  — (0 logged)")
        print(f"  {label:18} {x['n']:4}   {x['dates']:4}   {x['p_under']:6.0%}   "
              f"{x['claim_raw']:10.1%}   {x['claim_adj']:5.1%}   "
              f"{100 * x['moved']:+5.1f}pt   {dt}")
    print()
    # The claim LEVEL is the dominant driver of how hard the correction
    # bites, and it is worth saying so plainly because the first cut of
    # this warning blamed the side mix and was wrong on the real journal:
    # the held-out half had FEWER unders (25% against 44%), which would
    # bite harder, and it moved less anyway. What actually separated the
    # halves was a 13.7-point difference in mean claim.
    if abs(ce["claim_raw"] - cl["claim_raw"]) > 0.05:
        print(f"  ** The two halves claim very different things on average:")
        print(f"     {ce['claim_raw']:.1%} early against {cl['claim_raw']:.1%} "
              f"held out. A temperature bites in")
        print("     proportion to how far a claim sits from 50%, so the same")
        print("     (S, c) is a far larger correction on one half than the")
        print("     other. The verdict below is partly measuring that rather")
        print("     than generalisation.")
        print()
    # A row with no logged cal_temp had NO deep correction live, which is
    # 1.0 — the identity. Comparing only when both sides carry a number
    # would miss the loudest version of this: nothing live early, a
    # correction live later. That is a change from 1.0, and it is exactly
    # what a mid-journal calibration release looks like.
    et = ce["cal_temp"] if ce["cal_temp"] is not None else 1.0
    lt = cl["cal_temp"] if cl["cal_temp"] is not None else 1.0
    share = max(ce["n_cal"] / max(ce["n"], 1), cl["n_cal"] / max(cl["n"], 1))
    if abs(et - lt) > 0.05:
        # How much of the halves' claim-level difference this change could
        # POSSIBLY account for. On the real journal the answer was 11 rows
        # in 126, which cannot move a mean by more than about 1.8 points
        # however hard it shrinks them — against an observed 13.7. A
        # warning that fires on a real but tiny basis change, and reads as
        # though it explains the whole table, is the same overstatement
        # this file keeps finding elsewhere. So it is quoted with its own
        # ceiling attached, and only escalates when it can actually matter.
        print("  ** The deep correction is not the same on both halves.")
        print(f"     Mean cal_temp {et:.2f} early against {lt:.2f} held out, "
              f"on {ce['n_cal']}/{ce['n']} and {cl['n_cal']}/{cl['n']} rows.")
        if share < BASIS_SHARE:
            print(f"     Too few rows carry it to matter: at most "
                  f"{share:.0%} of a half,")
            print("     so it can shift that half's mean claim by around")
            print(f"     {share * 20:.1f} points at the very outside. Noted, "
                  f"not the explanation")
            print("     for anything larger. The verdict is not unsafe on this.")
        else:
            print("     `hit_prob` is the SHIPPED claim, already through")
            print("     calibrate.py, so it only means one thing while that")
            print("     temperature holds still. Across a change the halves")
            print("     are denominated differently and a layer fitted on one")
            print("     and tested on the other chases a moving target — the")
            print("     hazard journalfit solves with undo_temperature and")
            print("     selfit does not. Treat the verdict as UNSAFE rather")
            print("     than merely under-powered.")
        print()
    elif ce["n_cal"] == 0 and cl["n_cal"] == 0:
        print("  (No row carries a logged cal_temp, so no deep correction was")
        print("   live during this window and the claims are on one basis.)")
        print()
    if ce["dates"] < 5:
        print(f"  ** The fit saw only {ce['dates']} dates. Balancing the split by")
        print("     BET COUNT can put a handful of heavy slates on one side —")
        print("     nights are correlated, so this is far less training data")
        print("     than the bet count suggests. Read the verdict accordingly.")
        print()

    b_late = measure(late)
    a_late = measure(late, c.temperature, c.intercept)
    v, why = verdict(b_late["gap"], a_late["gap"])
    print("=" * 74)
    print(f"VERDICT: {v}")
    print("=" * 74)
    print(f"  {why}")
    print()
    if v == "PASS":
        print("  Next is step 4, and it is a decision rather than a script:")
        print("  §8 says correcting a 12-point over-claim honestly may not")
        print("  trim the board but empty it. That is the correct outcome if")
        print("  the measurement is right, and it should be chosen on purpose.")
    elif v == "FAIL":
        print("  §9: the held-out gap did not close, so the correction is")
        print("  fitting noise. Do not apply it. The over-claim is real —")
        print("  guardfit and selcheck both measure it — but this is not")
        print("  the instrument for it.")
    else:
        print("  Not a soft pass. The honest reading is that this journal")
        print("  cannot yet tell a working correction from a lucky one, and")
        print("  the answer is more settled bets rather than a decision.")
    print()

    cv = crossval(rows)
    if cv.get("n"):
        cv_v, cv_why = verdict(cv["gap_before"], cv["gap_after"])
        print("=" * 74)
        print("SECOND OPINION — every bet held out once (added after the above)")
        print("=" * 74)
        print(f"  {cv['folds']} folds cut on whole dates, {cv['n']} bets each "
              f"scored by a fit that never saw its night")
        print(f"  gap {cv['gap_before']:+.1%} -> {cv['gap_after']:+.1%}   "
              f"(2σ ±{2 * cv['se']:.1%})     would read: {cv_v}")
        ts = sorted(f[0] for f in cv["fits"])
        print(f"  temperatures across folds: {ts[0]:.2f} to {ts[-1]:.2f}"
              + ("   ** one or more hit the grid ceiling **"
                 if any(f[2] for f in cv["fits"]) else ""))
        print()
        print("  This judges all the bets instead of half, and averages over")
        print("  where the split boundary happened to land. It is NOT the")
        print("  pre-registered verdict and cannot overturn it — it was built")
        print("  after seeing that one, which is exactly the move this file")
        print("  exists to prevent. If the two disagree, the reading is")
        print("  UNRESOLVED and the answer is more bets.")
        if cv_v != v:
            print()
            print(f"  → they DISAGREE ({v} vs {cv_v}). Unresolved. Do not apply.")
        print()

    bands = by_claim(late, c.temperature, c.intercept)
    if len(bands) > 1:
        print("=" * 74)
        print("IS ONE TEMPERATURE THE RIGHT SHAPE?  (held-out half, by claim)")
        print("=" * 74)
        print("   claim band      n   claimed    landed    gap    after")
        print("  " + "-" * 56)
        for bd in bands:
            print(f"   {bd['lo']:.0%}-{bd['hi']:.0%}    {bd['n']:7d}   "
                  f"{bd['claimed']:7.1%}   {bd['landed']:7.1%}  "
                  f"{bd['gap_before']:+6.1%}  {bd['gap_after']:+6.1%}")
        print()
        wide = [b for b in bands if b["n"] >= 25]
        if len(wide) > 1:
            spread = max(b["gap_before"] for b in wide) - \
                min(b["gap_before"] for b in wide)
            print(f"  Spread across bands with 25+ bets: {spread:.1%}")
            print()
            if spread > 0.10:
                print("  The over-claim is NOT flat in claim level, so a single")
                print("  temperature is the wrong shape and the fit is being")
                print("  asked to average two different faults. That is a")
                print("  better explanation of a failed hold-out than drift.")
            else:
                print("  Flat enough that one temperature is a fair shape, so")
                print("  a failed hold-out is not explained by this either.")
        else:
            print("  Only one band carries 25+ bets, so the bands cannot be")
            print("  compared with each other.")
        # A COMPARISON needs two bands. A reading of the band the board
        # actually lives in needs one — and the first cut of this printed
        # "no reading" and swallowed the single most useful line in the
        # report: on the real journal the biggest band held 92 of 123
        # held-out bets and the correction moved it +15.2% to +15.3%.
        # Silence about the dominant band is not caution, it is a
        # missing answer.
        big = max(bands, key=lambda b: b["n"])
        share = big["n"] / sum(b["n"] for b in bands)
        if share >= 0.40:
            moved = abs(big["gap_before"]) - abs(big["gap_after"])
            print()
            print(f"  The board lives in {big['lo']:.0%}-{big['hi']:.0%}: "
                  f"{big['n']} of {sum(b['n'] for b in bands)} held-out bets "
                  f"({share:.0%}),")
            print(f"  claiming {big['claimed']:.1%} and landing "
                  f"{big['landed']:.1%}. The correction moved that band's")
            print(f"  gap by {moved:+.1%}.")
            if abs(moved) < 0.02:
                print()
                print("  That is the finding. A temperature has 50% as a fixed")
                print("  point, so it cannot move a claim sitting at even")
                print("  money — and below 50% it pushes UP, against the")
                print("  intercept. Three quarters of this board sits there,")
                print("  so the instrument is inert exactly where the bets")
                print("  are. See the second functional form below.")
        print()

    wf = walkforward(rows)
    wf_v = None
    if wf.get("n"):
        wf_v, wf_why = verdict(wf["gap_before"], wf["gap_after"])
        print("=" * 74)
        print("THIRD OPINION — walk-forward, the one a live board would have run")
        print("=" * 74)
        print(f"  {wf['steps']} nightly refits across {wf['dates']} dates; "
              f"{wf['n']} bets each priced by a fit that saw only")
        print("  earlier nights — no future data anywhere in it")
        print(f"  gap {wf['gap_before']:+.1%} -> {wf['gap_after']:+.1%}   "
              f"(2σ ±{2 * wf['se']:.1%})     would read: {wf_v}")
        ts = sorted(f[2] for f in wf["fits"])
        print(f"  temperatures across refits: {ts[0]:.2f} to {ts[-1]:.2f}")
        print()
        print("  Built on the theory that the board's DRIFT was what broke")
        print("  the hold-out. Simulated against 60 synthetic journals, that")
        print("  theory did not hold: drift moves every estimator's false-")
        print("  alarm rate by a point or two, not by the margin needed to")
        print("  explain a FAIL. It is kept because the interleaved CV above")
        print("  returns FAIL in ZERO simulated worlds — it cannot convict,")
        print("  even of a correction that damages the held-out half — and")
        print("  because this is the causal question. It is NOT the better")
        print("  test: it has less power than the CV and a similar false-")
        print("  alarm rate.")
        print()

    # --- the second functional form ------------------------------------
    st, sb = fit_shift(_pairs(early))
    s_late = measure(late, st, sb)
    s_v, _s_why = verdict(b_late["gap"], s_late["gap"])
    s_cv = crossval(rows, fitter="shift")
    s_wf = walkforward(rows, fitter="shift")
    s_cv_v = (verdict(s_cv["gap_before"], s_cv["gap_after"])[0]
              if s_cv.get("n") else None)
    s_wf_v = (verdict(s_wf["gap_before"], s_wf["gap_after"])[0]
              if s_wf.get("n") else None)

    print("=" * 74)
    print("SECOND FUNCTIONAL FORM — intercept only, temperature pinned at 1")
    print("=" * 74)
    print(f"  intercept {sb:+.3f}   — the joint fit above chose "
          f"{c.intercept:+.3f} alongside temperature {c.temperature:.2f}")
    print()
    print("  logit(p)/T has 50% as a FIXED POINT, so the temperature moves a")
    print("  claim in proportion to how far it already sits from even money.")
    print("  This board does not sit far from even money, and below 50% the")
    print("  temperature pushes UP — against the intercept — so it spends the")
    print("  fit's capacity where it cannot pay and cancels part of what can.")
    print()
    print(f"  held out            gap {b_late['gap']:+.1%} -> "
          f"{s_late['gap']:+.1%}     would read: {s_v}")
    if s_cv_v:
        print(f"  interleaved CV      gap {s_cv['gap_before']:+.1%} -> "
              f"{s_cv['gap_after']:+.1%}     would read: {s_cv_v}")
    if s_wf_v:
        print(f"  walk-forward        gap {s_wf['gap_before']:+.1%} -> "
              f"{s_wf['gap_after']:+.1%}     would read: {s_wf_v}")
    print()

    votes = [x for x in (v, cv_v, wf_v) if x]
    if len(votes) > 1:
        print("=" * 74)
        print("READING ALL OF IT")
        print("=" * 74)
        print(f"  temperature + intercept    split {v} | CV {cv_v or '—'} "
              f"| walk-forward {wf_v or '—'}")
        print(f"  intercept only             split {s_v} | CV {s_cv_v or '—'} "
              f"| walk-forward {s_wf_v or '—'}")
        print()
        print(f"  That is TWO functional forms by THREE estimators — six")
        print(f"  looks at one {len(rows)}-bet journal. Each estimator hands a")
        print("  PASS to an honest journal 7-17% of the time, so across six")
        print("  looks a stray PASS is likelier than not. The bar for any")
        print("  single cell went UP when this table got wider, not down.")
        print()
        if len(set(votes)) == 1:
            print(f"  The pre-registered form's three agree: {votes[0]}.")
        else:
            print("  They do not agree, and that is the finding. Every one of")
            print("  these carries a 7-17% false-alarm rate — the bars are")
            print("  absolute gaps, never calibrated as a significance level")
            print("  — so roughly one honest journal in seven hands you a")
            print("  PASS from one of them. A lone PASS moves nothing.")
        print()
        print("  Do not apply a correction on anything short of agreement.")
        print()
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default="mlb")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
