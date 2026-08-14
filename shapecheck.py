#!/usr/bin/env python3
"""Is ONE parameter the right shape for the claim gap — and is it stable?

Ethan, 2026-08-13, after `launch.py --haircut --refit` put the pooled cut
live: "yeah build it."

THE HAIRCUT FITS A BIAS. `engine/selectionfit.py` moves every claim by the
same amount in log-odds — one number, pooled over markets, per sport. That
is the right first correction and it just went live at -0.301. But it
assumes something it has never checked: that the over-claim is UNIFORM in
log-odds. Two other shapes are possible and they want different fixes:

    a bias      we are 8 points high everywhere      → one parameter, done
    a slope     3 points high at 52%, 15 at 70%      → the model's
                                                       CONFIDENCE is wrong
                                                       and a bias
                                                       over-corrects one
                                                       end while
                                                       under-correcting
                                                       the other
    a step      one market or price band carries     → a per-band fit, and
                it and the rest is fine                the pool hides it

So this fits a second parameter and asks whether it earns its place:

    model A   logit(p') = logit(p) + b           (what is live now)
    model B   logit(p') = a·logit(p) + b         (bias AND slope)

THE DECISION RULE IS WRITTEN ABOVE THE RESULTS, not below them. A second
parameter ALWAYS fits the training data better — that is arithmetic, not
evidence — so the only question that means anything is whether it predicts
better on bets it has never seen. :data:`ADOPT` states every condition in
advance and all of them must hold.

AND IT CHECKS THE FIRST PARAMETER TOO, which is the part that came out of
tonight's refit rather than out of theory. The pooled fit passed its
held-out test (gap 4.9 → 3.5) while the MLB fit — 423 of the pool's 451
rows, so very nearly the same data — was REFUSED by the same test (gap
4.4 → 4.9). Two verdicts that disagree on 94% shared rows are not two
findings about two populations; they are one finding sitting on a knife
edge, and the edge is where the single 70/30 cut happens to fall. A
walk-forward runs the same question from several origins so the answer
stops depending on one boundary.

READ-ONLY. Opens the ledger immutably and writes nothing. It reports; it
does not change what the board prices with.

    python3 shapecheck.py
    python3 shapecheck.py --sport mlb
    python3 shapecheck.py --since 2026-06-01
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import selectionfit as sf                          # noqa: E402

#: The books the record is scored on — the published board, money or not.
BOOKS = sf.LEARNING_CATEGORIES

#: Claim bands, by the model's RAW probability. Chosen to straddle the
#: -110 break-even (52.4%), because "does the gap change across the bar we
#: actually bet at" is the question the bands exist to answer.
BANDS = [(0.00, 0.50, "under 50%"),
         (0.50, 0.55, "50 – 55%"),
         (0.55, 0.60, "55 – 60%"),
         (0.60, 0.65, "60 – 65%"),
         (0.65, 0.70, "65 – 70%"),
         (0.70, 1.01, "70% and up")]

#: EVERY CONDITION FOR ADOPTING THE SLOPE, FIXED BEFORE THE FIRST RUN.
#: Each one closes a specific way of being fooled; the comments are the
#: reason each is here, not decoration.
ADOPT = {
    # A second parameter fits the training data better by construction.
    # Only out-of-sample counts, and both scoring rules must agree —
    # Brier alone can improve while log loss worsens when a model gets
    # sharper and wronger at the tails.
    "out_of_sample_brier": True,
    "out_of_sample_logloss": True,
    # A slope of 1.02 is the same model wearing a second parameter.
    "min_slope_distance": 0.10,
    # The paired bootstrap asks how often the improvement survives
    # resampling the held-out rows. Below this it is one lucky block.
    "bootstrap_share": 0.95,
    # THE ONE MOST LIKELY TO BIND. A slope is only identifiable if the
    # claims SPREAD. If every bet we make claims 52-58%, the data has no
    # leverage on how the error grows with confidence, and any fitted
    # slope is an extrapolation dressed as a measurement. 0.60 logits is
    # roughly a 50%→65% span between the quartiles.
    "min_logit_iqr": 0.60,
}

#: Walk-forward: the sample is cut into this many chronological blocks,
#: and every block after the first two is predicted from everything
#: before it. Five gives three scored blocks at ~450 rows — enough that
#: no single boundary decides the verdict, few enough that the earliest
#: training window is not tiny.
BLOCKS = 5
BOOTSTRAP = 2000
#: Grids for the two-parameter search. The slope grid deliberately spans
#: below and above 1: a model can be UNDER-confident, and a grid that
#: cannot express that would find over-confidence by construction.
_SLOPES = [round(0.20 + 0.02 * i, 2) for i in range(91)]        # 0.20…2.00
_BIASES = [round(-1.20 + 0.02 * i, 2) for i in range(121)]      # -1.20…1.20


# --- reading the journal ----------------------------------------------------
def _rows(db, sport=None, since=None):
    """Settled picks with their claims, oldest first.

    Opened read-only. The claim is recovered RAW: a row logged after a
    haircut shipped carries a `hit_prob` that already has the cut in it,
    and measuring the shape of the error on corrected numbers would
    describe the correction rather than the model. `selectionfit._pairs`
    owns that inverse, so it is called rather than reimplemented.
    """
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    q = ("SELECT sport, market, side, hit_prob, odds, status, ts, date "
         f"FROM bets WHERE status IN ('won','lost') "
         f"AND category IN ({','.join('?' * len(BOOKS))})")
    args = list(BOOKS)
    if sport:
        q += " AND sport = ?"; args.append(sport)
    if since:
        q += " AND date >= ?"; args.append(since)
    rows = list(conn.execute(q + " ORDER BY ts, rowid", args))
    conn.close()

    stored = sf.load()
    stamp = stored.get("fitted_at") or ""
    per_sport = {k: (v or {}).get("shift", 0.0)
                 for k, v in (stored.get("sports") or {}).items()}
    pooled = (stored.get("pooled") or {}).get("shift", 0.0)

    out = []
    for r in rows:
        s = (r["sport"] or "").lower()
        prior = per_sport.get(s) or 0.0
        if not prior and sf._borrowed(stored, s):
            prior = pooled
        pair = sf._pairs([r], prior, stamp)
        if pair:
            out.append(pair[0])
    return out


# --- the two models ---------------------------------------------------------
def _apply(p, a, b):
    """logit(p') = a·logit(p) + b — model B, and model A when a = 1."""
    return sf._sigmoid(a * sf._logit(p) + b)


def _xo(pairs):
    """(logit of the claim, outcome) — computed ONCE.

    The grid search evaluates a few hundred (a, b) pairs against every
    row, and recomputing the logit inside that loop is most of the cost
    for none of the meaning.
    """
    return [(sf._logit(p), o) for p, o in pairs]


def _brier_xo(xo, a, b):
    if not xo:
        return 0.0
    t = 0.0
    for x, o in xo:
        q = sf._sigmoid(a * x + b)
        t += (q - o) ** 2
    return t / len(xo)


def _brier(pairs, a, b):
    return _brier_xo(_xo(pairs), a, b)


def _gap(pairs, a, b):
    """Mean claim minus mean outcome — the over-claim, signed.

    This is the quantity the haircut exists to close, and the one this
    tool did not print on its first run. Negative means we still claim
    more than we land; zero means the board's average claim is honest.
    """
    if not pairs:
        return 0.0
    claimed = sum(_apply(p, a, b) for p, _ in pairs) / len(pairs)
    landed = sum(o for _, o in pairs) / len(pairs)
    return landed - claimed


def _logloss(pairs, a, b):
    """Log loss, clipped. Reported alongside Brier because the two
    disagree exactly where it matters: a model that gets sharper and
    wronger at the tails can improve one while worsening the other."""
    if not pairs:
        return 0.0
    t = 0.0
    for p, o in pairs:
        q = min(max(_apply(p, a, b), 1e-6), 1.0 - 1e-6)
        t += -(math.log(q) if o else math.log(1.0 - q))
    return t / len(pairs)


def _fit_bias(pairs):
    """Model A: the live haircut's own fit, unshrunk."""
    xo = _xo(pairs)
    return 1.0, min(_BIASES, key=lambda b: _brier_xo(xo, 1.0, b))


def _fit_slope(pairs):
    """Model B: slope and bias together, by Brier on the training rows.

    Coarse then fine over the same range the grids describe. The Brier
    surface in (a, b) is smooth and single-basined, so a two-pass search
    lands on the same cell as the exhaustive one at a fraction of the
    cost — and the cost is what decides whether this tool is runnable on
    a laptop while the games are on.
    """
    xo = _xo(pairs)
    best, arg = None, (1.0, 0.0)
    for a in [round(0.2 + 0.1 * i, 2) for i in range(19)]:      # 0.2…2.0
        for b in [round(-1.2 + 0.1 * i, 2) for i in range(25)]:  # -1.2…1.2
            s = _brier_xo(xo, a, b)
            if best is None or s < best:
                best, arg = s, (a, b)
    ca, cb = arg
    for i in range(-5, 6):
        a = round(ca + 0.02 * i, 3)
        if not (_SLOPES[0] <= a <= _SLOPES[-1]):
            continue
        for j in range(-5, 6):
            b = round(cb + 0.02 * j, 3)
            if not (_BIASES[0] <= b <= _BIASES[-1]):
                continue
            s = _brier_xo(xo, a, b)
            if s < best:
                best, arg = s, (a, b)
    return arg


# --- leverage ---------------------------------------------------------------
def _logit_iqr(pairs):
    """How far apart our claims actually are, in log-odds.

    The whole slope question is "does the error grow with confidence",
    and that is only answerable if the confidences differ. This is the
    measurement that says whether the sample can answer it at all.
    """
    if len(pairs) < 4:
        return 0.0
    xs = sorted(sf._logit(p) for p, _ in pairs)
    q1 = xs[len(xs) // 4]
    q3 = xs[(3 * len(xs)) // 4]
    return q3 - q1


# --- walk-forward -----------------------------------------------------------
def _walk_forward(pairs, blocks=BLOCKS):
    """Fit on everything before each block, score the block itself.

    One 70/30 cut asks the question once and gives the boundary a vote.
    This asks it from several origins, so a correction has to help on
    bets it has never seen more than once to be called stable.
    """
    n = len(pairs)
    if n < blocks * 8:
        return []
    edges = [round(n * i / blocks) for i in range(blocks + 1)]
    out = []
    for i in range(2, blocks):                 # blocks 3..N get a verdict
        train, test = pairs[:edges[i]], pairs[edges[i]:edges[i + 1]]
        if len(train) < 20 or len(test) < 10:
            continue
        _, b = _fit_bias(train)
        a2, b2 = _fit_slope(train)
        out.append({
            "train_n": len(train), "test_n": len(test),
            "bias": b, "slope": a2, "slope_bias": b2,
            # THE GAP IS WHAT THE CUT IS AIMED AT, and it was missing from
            # this table on the first run — see `report` for why that
            # made the walk-forward answer the wrong question.
            "gap_none": _gap(test, 1.0, 0.0),
            "gap_a": _gap(test, 1.0, b),
            "gap_b": _gap(test, a2, b2),
            "brier_none": _brier(test, 1.0, 0.0),
            "brier_a": _brier(test, 1.0, b),
            "brier_b": _brier(test, a2, b2),
            "logloss_none": _logloss(test, 1.0, 0.0),
            "logloss_a": _logloss(test, 1.0, b),
            "logloss_b": _logloss(test, a2, b2),
            "rows": test,
            "fit_a": (1.0, b), "fit_b": (a2, b2),
        })
    return out


def _paired(steps, rounds=BOOTSTRAP, seed=11):
    """How model B does against model A on rows neither has seen.

    PAIRED, and that is the whole design: each row contributes ONE
    number — its squared error under A minus its squared error under B —
    so a resample cannot favour a model by happening to draw easy rows.
    Precomputing those differences also makes the resampling a sum over
    floats rather than two model evaluations per row per round.

    Returns the bootstrap share, the effect in standard errors, the
    number of held-out rows, and HOW MANY WOULD BE NEEDED to settle it.
    That last number is the one that keeps a null result honest: "the
    slope did not clear the bar" and "no sample this size could have
    cleared the bar" are different sentences, and only the second one is
    usually true here.
    """
    diffs = [((_apply(p, *s["fit_a"]) - o) ** 2
              - (_apply(p, *s["fit_b"]) - o) ** 2)
             for s in steps for (p, o) in s["rows"]]
    n = len(diffs)
    if n < 2:
        return {"share": 0.0, "z": 0.0, "n": n, "needed": None}
    rnd = random.Random(seed)
    wins = 0
    for _ in range(rounds):
        if sum(diffs[rnd.randrange(n)] for _ in range(n)) > 0:
            wins += 1                      # B's error is the smaller one
    m = sum(diffs) / n
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    se = (var / n) ** 0.5
    z = (m / se) if se > 0 else 0.0
    # n scales as 1/z²: to reach a one-sided 1.645 from an observed z.
    needed = int(n * (1.645 / z) ** 2) if z > 0.05 else None
    return {"share": wins / rounds, "z": z, "n": n, "needed": needed}


# --- reporting --------------------------------------------------------------
def _band_table(pairs):
    print(f"\n  IS THE GAP THE SAME SIZE EVERYWHERE?")
    print(f"    {'claim band':<12}{'bets':>6}{'claimed':>9}{'landed':>8}"
          f"{'gap':>8}{'±se':>7}")
    shown = 0
    for lo, hi, name in BANDS:
        v = [(p, o) for p, o in pairs if lo <= p < hi]
        if not v:
            continue
        shown += 1
        c = sum(p for p, _ in v) / len(v)
        l = sum(o for _, o in v) / len(v)
        se = math.sqrt(max(l * (1 - l), 1e-9) / len(v))
        print(f"    {name:<12}{len(v):>6}{c * 100:>8.1f}%{l * 100:>7.1f}%"
              f"{(l - c) * 100:>+7.1f}p{se * 100:>6.1f}p")
    if shown < 2:
        print("    every settled bet sits in ONE band — there is no shape to "
              "read here,\n    only a level, which is what the haircut "
              "already fits.")
    return shown


def report(pairs, name):
    n = len(pairs)
    print(f"\n  {name} — {n} settled bet(s)")
    if n < 60:
        print(f"    too few to ask a two-parameter question. Nothing is "
              f"reported rather\n    than reported thinly.")
        return
    shown = _band_table(pairs)

    iqr = _logit_iqr(pairs)
    lo = sf._sigmoid(sorted(sf._logit(p) for p, _ in pairs)[n // 4])
    hi = sf._sigmoid(sorted(sf._logit(p) for p, _ in pairs)[(3 * n) // 4])
    print(f"\n  HOW MUCH LEVERAGE THE SAMPLE HAS")
    print(f"    the middle half of our claims runs {lo * 100:.1f}% to "
          f"{hi * 100:.1f}%  ·  {iqr:.2f} logits")
    enough = iqr >= ADOPT["min_logit_iqr"]
    if not enough:
        print(f"    BELOW THE {ADOPT['min_logit_iqr']:.2f} BAR. A slope "
              f"describes how the error grows with\n    confidence, and this "
              f"board barely varies its confidence. Any slope\n    fitted "
              f"here is an extrapolation wearing a measurement's clothes.")

    steps = _walk_forward(pairs)
    if not steps:
        print("\n    not enough history for a walk-forward — no verdict.")
        return

    print(f"\n  WALK-FORWARD — each block predicted from everything before it")
    print(f"    {'train':>6}{'test':>6}   {'gap none':>9}{'→ A':>8}   "
          f"{'Brier none':>11}{'→ A':>8}   slope")
    for s in steps:
        print(f"    {s['train_n']:>6}{s['test_n']:>6}   "
              f"{s['gap_none'] * 100:>+8.1f}p{s['gap_a'] * 100:>+7.1f}p   "
              f"{s['brier_none']:>11.4f}{s['brier_a']:>8.4f}   "
              f"a={s['slope']:.2f}")

    tot = sum(s["test_n"] for s in steps)
    agg = {k: sum(s[k] * s["test_n"] for s in steps) / tot
           for k in ("brier_none", "brier_a", "brier_b",
                     "logloss_none", "logloss_a", "logloss_b",
                     "gap_none", "gap_a", "gap_b")}
    a_beats_none = sum(1 for s in steps if s["brier_a"] < s["brier_none"])
    a_closes_gap = sum(1 for s in steps
                       if abs(s["gap_a"]) < abs(s["gap_none"]))
    print(f"\n    over all {tot} held-out bets   "
          f"Brier {agg['brier_none']:.4f} → A {agg['brier_a']:.4f} "
          f"→ B {agg['brier_b']:.4f}")
    print(f"    {'':<21}log loss {agg['logloss_none']:.4f} → A "
          f"{agg['logloss_a']:.4f} → B {agg['logloss_b']:.4f}")

    # --- the first parameter, which is the one that is live -----------
    #
    # TWO METRICS, AND THE FIRST RUN OF THIS TOOL ONLY PRINTED THE
    # STRICTER ONE — which made it answer a question the cut was never
    # aimed at.
    #
    # Brier asks "does each individual claim predict its own outcome
    # better". A pooled bias cannot do much for that: it moves every
    # claim the same distance, so it improves the rows that lost and
    # worsens the ones that won, and on a book near 50% those nearly
    # cancel. Judging the cut on Brier alone sets it a test it was never
    # built to pass.
    #
    # The GAP asks "is the board's average claim honest" — which is
    # exactly what the haircut was fitted to fix and exactly what the
    # over-claim costs us, because every edge, EV and stake on the board
    # is computed from that claim. Both are reported; neither is hidden;
    # the gap is the one that matches the correction's purpose.
    print(f"\n  IS THE LIVE ONE-PARAMETER CUT STABLE?")
    print(f"    over all {tot} held-out bets the over-claim went "
          f"{agg['gap_none'] * 100:+.1f}p → {agg['gap_a'] * 100:+.1f}p")
    print(f"    it CLOSED THE GAP in {a_closes_gap} of {len(steps)} blocks "
          f"· it improved Brier in {a_beats_none} of {len(steps)}")
    if a_closes_gap == len(steps):
        print("    Every origin agrees on the thing the cut is FOR: the "
              "board's average\n    claim is closer to what lands. That is "
              "the correction working.")
    elif a_closes_gap == 0:
        print("    NO origin agrees, on its own objective. The single 70/30 "
              "pass that put\n    this live does not reproduce, and that is "
              "a reason to take it off.")
    else:
        print(f"    It closes the gap at some origins and not others — the "
              f"over-claim is not\n    a constant, it comes and goes. The "
              f"70/30 test that put the cut live is one\n    of these "
              f"blocks, not a summary of them.")
    if a_beats_none < len(steps):
        print(f"    Brier disagreeing is not a contradiction: a pooled shift "
              f"moves every\n    claim the same distance, helping the losers "
              f"and hurting the winners, so\n    it can be neutral per-bet "
              f"while still making the board's number honest.")

    # --- the second parameter, judged by the rule written above -------
    slope = sum(s["slope"] * s["test_n"] for s in steps) / tot
    pair = _paired(steps)
    share = pair["share"]
    print(f"\n  DOES THE SLOPE EARN ITS PLACE?")
    print(f"    fitted slope (test-weighted): a = {slope:.2f}   ·   "
          f"bootstrap favours B in {share * 100:.0f}% of resamples")
    checks = [
        (agg["brier_b"] < agg["brier_a"], "out-of-sample Brier improves"),
        (agg["logloss_b"] < agg["logloss_a"], "out-of-sample log loss improves"),
        (abs(slope - 1.0) >= ADOPT["min_slope_distance"],
         f"slope is at least {ADOPT['min_slope_distance']} from 1"),
        (share >= ADOPT["bootstrap_share"],
         f"bootstrap ≥ {ADOPT['bootstrap_share'] * 100:.0f}%"),
        (enough, f"claim spread ≥ {ADOPT['min_logit_iqr']} logits"),
    ]
    for ok, label in checks:
        print(f"      {'PASS' if ok else 'fail'}  {label}")
    if all(ok for ok, _ in checks):
        print(f"\n    ADOPT THE SLOPE. Every preregistered condition holds: "
              f"the error grows\n    with confidence, and one pooled number "
              f"cannot express that.")
    else:
        print(f"\n    ONE PARAMETER IS ENOUGH. The slope fails "
              f"{sum(1 for ok, _ in checks if not ok)} of its "
              f"{len(checks)} conditions,\n    and a second parameter that "
              f"cannot clear a bar written before the run is\n    a way to "
              f"lose money more precisely.")
        # WHY IT FAILED MATTERS MORE THAN THAT IT FAILED. Refusing a
        # slope because the sample is too small to see one is a
        # statement about the sample; refusing it because the slope is
        # not there is a statement about the model. Reporting only the
        # verdict would let the first be read as the second, and the
        # first is what is usually true at these sample sizes.
        if share < ADOPT["bootstrap_share"]:
            if pair["needed"]:
                print(f"\n    HOW MUCH OF THAT IS SAMPLE SIZE: the "
                      f"improvement is {pair['z']:.1f} standard errors on "
                      f"{pair['n']}\n    held-out bets. At this effect size "
                      f"it would take about {pair['needed']:,} held-out\n"
                      f"    bets — roughly {int(pair['needed'] / max(1, pair['n']))}× "
                      f"the journal — before the question is answerable at "
                      f"all.")
            else:
                print(f"\n    And the sample does not lean toward the slope: "
                      f"more data would not\n    make this one true.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--sport")
    ap.add_argument("--since")
    a = ap.parse_args(argv)
    if not os.path.exists(a.db):
        print(f"  No ledger at {a.db}.")
        return 1
    pairs = _rows(a.db, a.sport, a.since)
    scope = " · ".join(filter(None,
                              [a.sport or "every sport",
                               a.since and f"since {a.since}"]))
    print(f"\n  THE SHAPE OF THE CLAIM GAP  ·  {scope}")
    print(f"\n  The live haircut fits ONE number: every claim moves the same "
          f"distance in\n  log-odds. This asks whether that is the right "
          f"shape, and whether the one\n  number itself holds up from more "
          f"than a single split. Claims are read RAW —\n  a row priced after "
          f"a cut shipped has the cut removed before it is measured.")
    report(pairs, "every sport pooled" if not a.sport else a.sport)
    print("\n  read-only; nothing was written. Adoption is a decision, not "
          "an output.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
