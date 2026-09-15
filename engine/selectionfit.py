"""The selection haircut — what OUR PICKS are worth, not what the surface is.

Ethan, 2026-08-12, after `stakecheck.py` put a number on it: "well we
should make it where we get a lower roi then and fix it on the website so
it would display the new number."

The number he is reacting to is this one. Across 310 settled bets the
model claimed its picks would land 51.5% and 59.7% in the two eras; they
landed 42.5% and 49.7%. A ~9–10 point over-claim, twice, on two different
gate configurations, with standard errors of 4.7 and 3.6 points. That is
not variance. Every edge, every EV figure and every Kelly stake on the
board is computed from a probability that is nine points too high, so the
board has been advertising an ROI it has never earned.

WHY THE EXISTING CALIBRATION NEVER CAUGHT IT
-------------------------------------------
It is not that calibration was missing. `calibrate.py` fits a temperature
per (sport, market) on hundreds of thousands of ingested player-games, and
`journalfit.py` refits from settled bets. Both were running. Both were
blind to this, for two separate reasons:

1. **Scope.** journalfit keys on (sport, market) and needs 200 settled
   bets per key. The journal has ~310 bets spread over a dozen markets, so
   no key has ever reached the floor and no journal correction has ever
   shipped. The floor is right for a per-market fit; it just means the
   per-market fit cannot answer a question about the whole board.

2. **Population.** calibrate.py fits on *every prop in the history DB* —
   the model's probability surface. We do not bet the surface. We bet the
   top edges out of it, which is exactly where a noisy estimate is most
   likely to be an overestimate: selecting on `model − market` selects for
   model error in one direction. A model can be perfectly calibrated
   across all props and badly over-confident on the subset it recommends,
   and that gap is invisible to any fit whose sample is the surface.

So this module fits the one thing neither of those can see: **the bets we
actually placed, pooled across markets, per sport.** One parameter, in the
bet's own frame, applied after the side is chosen.

WHAT IT DOES AND DOES NOT TOUCH
-------------------------------
* It runs in the BET frame (claimed probability vs won/lost), not the
  P(over) frame `journalfit.as_over` restates into. That is deliberate and
  it is the difference between two questions. journalfit asks "is the
  model's over-probability surface skewed?", where an over and an under
  claiming 0.58 are opposite claims and must not share a bucket. This asks
  "when we say 58%, how often do we cash?", where they are the same claim
  and must.
* It is applied AFTER `pick_side`, so it can never flip a side. A haircut
  that changed which way we bet would be a different model, not a
  correction to this one.
* It leaves the market temperature baked in. The claimed number it
  measures already contains that temperature, and the correction it
  returns is a correction to the *final* claim. Un-picking the two would
  double-count.

THE RESTRAINTS
--------------
A single pooled number applied to every price is a blunt instrument, and a
blunt instrument fitted on 300 rows can do real damage. Five guards:

* **Floor** (:data:`MIN_SETTLED`) — nothing is applied to a sport under
  100 settled bets. Below it the store says "collecting: n of 100".
* **Shrinkage** — the fitted shift is scaled by the share of the observed
  gap that noise cannot explain, ``1 − (SE/gap)²``, which is zero when the
  gap is inside one standard error and approaches one only when the gap
  dwarfs it. A real 9-point gap on 310 rows keeps ~90% of itself; a
  1-point gap on the same sample keeps none.
* **Cap** (:data:`SHIFT_CAP`) — |shift| ≤ 0.75 in log-odds, about 18
  points at even money. A freak sample cannot empty the board.
* **Downward only** — a fit saying we UNDER-claim is measured, stored and
  shown, but not applied. The two errors are not symmetric: haircutting a
  model that is actually fine costs us some bets we would have won;
  inflating a model on 100 rows of good luck raises stakes on an edge that
  may not exist. We publish the number and refuse to bet it.
* **No borrowing around a refusal** (:data:`POOL_BORROW_MAX_SHARE`) — a
  sport whose own fit was refused does not fall back to the pooled one
  when it IS most of the pooled sample. The fallback exists so a small
  sport can borrow evidence from a large, diverse pool; when the borrower
  is 92% of the pool that sentence runs backwards and the fallback turns
  a refusal into an application.

REFIT SAFETY
------------
Once a shift ships, later journal rows carry claims that already have it
applied. Refitting naively on those measures no remaining gap, stores ~0,
and ERASES a correction that was working — after which the gap returns,
the next refit re-applies it, and the model oscillates between corrected
and not. (Verified: a naive refit of a −0.335 shift on its own corrected
claims fits −0.000.) It is the same failure `calibrate.set_enabled` and
`journalfit.fit_temperatures` document, one data source over. So the
store stamps `fitted_at`, and every refit un-shifts rows logged on or
after that date before measuring — which recovers −0.335 exactly. Rows
that predate it are already raw.

Standard library only. Read by the two betting paths; written by the
settle pass.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

from . import modelstate as _modelstate

DEFAULT_PATH = Path(_modelstate.path("selection.json"))

#: Settled bets a sport needs before its own haircut is applied. Lower
#: than journalfit's 200 because this fit has ONE parameter pooled over
#: every market, where that one has two per market; high enough that a
#: week of baseball cannot set it.
MIN_SETTLED = 100

#: Maximum |shift| in log-odds. 0.75 moves a 50% claim to 32% — far more
#: than any honest fit should ever ask for, which is the point of a cap.
SHIFT_CAP = 0.75

#: Grid for the one-parameter search. Coarse enough to fit in a blink,
#: fine enough that the step (0.01 log-odds ≈ 0.25 points at even money)
#: is smaller than any gap worth correcting.
_GRID = [round(-1.20 + 0.01 * i, 2) for i in range(241)]

_cache: dict = {}
_enabled = True


def set_enabled(flag: bool) -> None:
    """Turn the stored haircut on or off process-wide.

    Two callers need this, for the same underlying reason — a fitted
    correction must not silently change the input to something being
    measured:

    * a future refit path, exactly as ``calibrate.set_enabled`` guards
      the temperature fit;
    * tests that price a synthetic slate and assert on the result. Those
      are testing journaling, the lab, the learning ladder — not the
      haircut — and the store they would otherwise read is whatever last
      night's settle pass fitted on a real journal. A live −0.35 shift
      empties a synthetic board, and the failure surfaces three files
      away from anything to do with calibration.
    """
    global _enabled
    _enabled = flag


class disabled:
    """Context manager: price with the haircut switched off."""

    def __enter__(self):
        set_enabled(False)
        return self

    def __exit__(self, *exc):
        set_enabled(True)
        return False


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def shift_prob(p: float, shift: float) -> float:
    """Move a probability by ``shift`` in log-odds space.

    The same transform as ``calibrate.apply_temperature`` with T=1, kept
    here as its own two-line function because this module's correction is
    a pure bias term and calling a "temperature" API to apply no
    temperature reads as a mistake in the betting path.
    """
    if not shift:
        return float(p)
    return _sigmoid(_logit(p) + shift)


def unshift_prob(p: float, shift: float) -> float:
    """Recover the claim a stored shift was applied to. Exact inverse."""
    if not shift:
        return float(p)
    return _sigmoid(_logit(p) - shift)


def _brier(pairs: list, shift: float) -> float:
    if not pairs:
        return 0.0
    return sum((shift_prob(p, shift) - o) ** 2 for p, o in pairs) / len(pairs)


def fit_shift(pairs: list) -> float:
    """The log-odds bias that best explains these (claim, outcome) pairs.

    Minimises Brier over :data:`_GRID`. Brier and not raw gap-matching
    because a shift is not a subtraction: moving 0.90 down by nine points
    of *probability* is a much larger move in log-odds than moving 0.52
    down by nine, and a board that mixes chalk and dogs needs the
    correction that fits both rather than the one that fixes the average.
    """
    if not pairs:
        return 0.0
    return min(_GRID, key=lambda s: _brier(pairs, s))


def _keep_fraction(gap: float, se: float) -> float:
    """How much of an observed gap survives its own noise.

    ``1 − (SE/gap)²``, floored at zero — the standard shrinkage for a
    noisy effect estimate. At the journal's numbers (gap −0.090, SE
    0.028) it keeps 0.90; at a gap of one SE it keeps nothing.
    """
    if se <= 0 or gap == 0:
        return 0.0
    return max(0.0, 1.0 - (se / abs(gap)) ** 2)


#: The books this fitter learns from: the published board, whether or not
#: money was on it.
#:
#: 'main' is the board with money on it. 'paper' is THE SAME BOARD with
#: the money off — `ledger.log_recommendations` files a row as paper when
#: paper mode is on and changes nothing else about it: same picks, same
#: sizing, same settlement, same CLV. So a paper row is exactly the
#: population this correction is about.
#:
#: Excluding it was a real defect and it was mine. Paper mode went on
#: 2026-08-09; the haircut shipped 2026-08-12 reading 'main' only, which
#: means it fitted on a journal frozen at the day the money came off and
#: could never see another row while paper mode stayed on. Ethan asked
#: exactly the right question — "check to see if we have been learning
#: anything since we turned on the paper bets" — and for this loop the
#: answer was no, structurally.
#:
#: The other books stay out, and they are a different thing: the home-run
#: sampler, the priced-out and loose-book shadows and the stale-line
#: sampler grade signals we deliberately do NOT publish. Pooling those in
#: would fit a correction for a board nobody sees.
LEARNING_CATEGORIES = ("main", "paper")


def _settled(lconn, categories=LEARNING_CATEGORIES) -> list:
    """Settled picks off the published board: claim, side, outcome, when."""
    marks = ",".join("?" * len(categories))
    return lconn.execute(
        f"SELECT sport, market, side, hit_prob, odds, status, ts "
        f"FROM bets WHERE status IN ('won','lost') AND category IN ({marks}) "
        f"ORDER BY ts, rowid", tuple(categories)).fetchall()


def _pairs(rows, prior_shift: float, stamp: str) -> list:
    """(raw claim, did it win) — with any already-applied shift removed.

    A row logged on or after ``stamp`` was priced with ``prior_shift``
    live, so its journaled `hit_prob` is post-haircut and has to be
    un-shifted before it can say anything about the model's own claim.
    Rows before it are raw already. Getting this backwards is how a
    correction compounds itself into the floor.
    """
    out = []
    for r in rows:
        p = r["hit_prob"]
        if p is None or not 0.0 < float(p) < 1.0:
            continue
        p = float(p)
        if prior_shift and stamp and (r["ts"] or "") >= stamp:
            p = unshift_prob(p, prior_shift)
            if not 0.0 < p < 1.0:
                continue
        out.append((p, 1 if r["status"] == "won" else 0))
    return out


#: The held-out share, taken from the END of the journal in time order.
#: docs/SELECTION_CORRECTION.md §7: "Fitted is not validated. Split the
#: journal by date. Fit on the earlier part only. Measure the gap on the
#: LATER part, with and without. Ship only if the held-out gap closes."
HOLDOUT_FRACTION = 0.30

#: HOW MANY ORIGINS THE CORRECTION HAS TO SURVIVE, and why one was not
#: enough. Until 2026-08-23 adoption turned on a SINGLE 70/30 split, and
#: `shapecheck.py --sport mlb` ran the same question from three origins
#: on 606 settled bets and got the opposite answer every time: the live
#: cut closed the gap in 0 of 3 blocks and improved Brier in 0 of 3, on
#: 364 held-out bets it had never seen. One split had put it live and
#: three said it should never have been.
#:
#: A verdict that depends on where a single boundary happens to fall is
#: not a verdict, it is a coin toss with arithmetic around it. The gate
#: now runs the same walk-forward the audit does, and a majority of
#: origins must improve BOTH the gap and Brier, and so must the final
#: 70/30 block. Fewer usable origins than this means no adoption — the
#: floor does not bend for a young journal, and the cost of refusing is
#: that the board prices on its own numbers, which is where it started.
WALK_ORIGINS = 3
MIN_ORIGINS = 2
#: How much of the journal the blocks are cut from. 0.60 puts the three
#: trains at roughly 40/60/80% of the record, which is the shape
#: shapecheck's walk-forward used on the run that found this.
WALK_TAIL = 0.60
#: Below this the held-out half cannot say anything, and a correction that
#: cannot be validated is not applied — the doc's bar, not a softer one.
MIN_HOLDOUT = 30


def _holdout(pairs: list) -> dict:
    """Fit on the earlier bets, score on the later ones. §7's gate.

    Pairs arrive in journal order, so the split is chronological — the
    only split that answers the question being asked, which is whether
    the correction helps bets it has never seen. A random split would
    leak the same nights into both halves.

    Both halves of "better" are required: the Brier score has to improve
    AND the raw claimed-vs-landed gap has to shrink. A shift can flatter
    one while worsening the other, and either alone is a weaker claim
    than the one being made when the board starts betting on it.
    """
    n = len(pairs)
    cut = int(n * (1.0 - HOLDOUT_FRACTION))
    test = pairs[cut:]
    if len(test) < MIN_HOLDOUT:
        return {"ran": False,
                "reason": f"held-out check needs {MIN_HOLDOUT} later bets, "
                          f"has {len(test)}"}

    blocks = [b for b in (_score_block(pairs, a, b) for a, b in _origins(n))
              if b]
    final = _score_block(pairs, cut)

    gap_ok = sum(1 for b in blocks if b["gap_after"] < b["gap_before"])
    brier_ok = sum(1 for b in blocks if b["brier_after"] < b["brier_before"])
    enough = len(blocks) >= MIN_ORIGINS
    passed = (enough
              and gap_ok >= _majority(len(blocks))
              and brier_ok >= _majority(len(blocks))
              and final["gap_after"] < final["gap_before"]
              and final["brier_after"] < final["brier_before"])

    out = dict(final)
    out.update({
        "ran": True,
        "origins": len(blocks),
        "gap_improved_in": gap_ok,
        "brier_improved_in": brier_ok,
        "blocks": [{"train_n": b["train_n"], "test_n": b["test_n"],
                    "shift": b["train_shift"],
                    "gap_before": b["gap_before"], "gap_after": b["gap_after"],
                    "brier_before": b["brier_before"],
                    "brier_after": b["brier_after"]} for b in blocks],
        "improved": bool(passed),
    })
    if not enough:
        out["walk_forward_note"] = (
            f"only {len(blocks)} usable origin(s); a correction has to hold "
            f"from at least {MIN_ORIGINS}")
    return out


def _origins(n: int) -> list:
    """`(train_end, test_end)` for each block: ADJACENT windows over the
    tail, every one fitted on all the history before it.

    Adjacent rather than expanding-to-the-end, which the first cut of
    this got wrong. Scoring every block on all the remaining rows makes
    the blocks overlap almost entirely — the earliest one contains the
    other two — so three "independent" verdicts are mostly one verdict
    counted three times. Equal windows give each block its own period,
    which is what `shapecheck.py`'s walk-forward does and the reason its
    three answers meant something.

    The tail is the last :data:`WALK_TAIL` of the journal. Fewer windows
    are used when the journal cannot fill three of at least
    :data:`MIN_HOLDOUT` bets, and below :data:`MIN_ORIGINS` windows the
    caller refuses to adopt at all — so the effective floor is not
    MIN_SETTLED but "enough bets to be checked from more than one
    starting point", which is the honest floor for this question.
    """
    tail = int(n * WALK_TAIL)
    for k in range(WALK_ORIGINS, MIN_ORIGINS - 1, -1):
        width = tail // k
        if width >= MIN_HOLDOUT:
            first = n - tail
            return [(first + i * width,
                     first + (i + 1) * width if i + 1 < k else n)
                    for i in range(k)]
    return []


def _majority(k: int) -> int:
    return k // 2 + 1


def _score_block(pairs: list, cut: int, upto: int | None = None) -> dict | None:
    """Fit on pairs[:cut], score on pairs[cut:upto]. None if either is thin."""
    train, test = pairs[:cut], pairs[cut:upto]
    if len(train) < MIN_HOLDOUT or len(test) < MIN_HOLDOUT:
        return None
    t_claimed = sum(p for p, _ in train) / len(train)
    t_landed = sum(o for _, o in train) / len(train)
    t_se = math.sqrt(max(t_landed * (1.0 - t_landed), 1e-9) / len(train))
    shift = max(-SHIFT_CAP, min(SHIFT_CAP, fit_shift(train)
                * _keep_fraction(t_landed - t_claimed, t_se)))
    landed = sum(o for _, o in test) / len(test)
    gap_before = abs((sum(p for p, _ in test) / len(test)) - landed)
    gap_after = abs((sum(shift_prob(p, shift) for p, _ in test) / len(test))
                    - landed)
    return {"train_n": len(train), "test_n": len(test),
            "train_shift": round(shift, 3),
            "gap_before": round(gap_before, 4),
            "gap_after": round(gap_after, 4),
            "brier_before": round(_brier(test, 0.0), 5),
            "brier_after": round(_brier(test, shift), 5)}


def _entry(pairs: list, min_settled: int = MIN_SETTLED) -> dict:
    """One population's verdict: what we claimed, what landed, what to do."""
    n = len(pairs)
    if not n:
        return {"n": 0, "applied": False, "reason": "no settled bets"}
    claimed = sum(p for p, _ in pairs) / n
    landed = sum(o for _, o in pairs) / n
    gap = landed - claimed
    se = math.sqrt(max(landed * (1.0 - landed), 1e-9) / n)
    raw = fit_shift(pairs)
    keep = _keep_fraction(gap, se)
    shift = max(-SHIFT_CAP, min(SHIFT_CAP, raw * keep)) + 0.0   # kill -0.0
    capped = abs(raw * keep) > SHIFT_CAP
    out = {
        "n": n,
        "claimed": round(claimed, 4),
        "landed": round(landed, 4),
        "gap": round(gap, 4),
        "se": round(se, 4),
        "shift_raw": round(raw, 3),
        "keep": round(keep, 3),
        "shift": round(shift, 3),
        "capped": capped,
        "brier_before": round(_brier(pairs, 0.0), 5),
        "brier_after": round(_brier(pairs, shift), 5),
        # What the shift does to a 55% claim — the sentence the site
        # prints, computed here so the page never re-derives it.
        "example_55": round(shift_prob(0.55, shift), 4),
        "holdout": _holdout(pairs),
    }
    if n < min_settled:
        out["applied"] = False
        out["reason"] = f"collecting: {n} of {min_settled} settled bets"
    elif keep <= 0:
        # Checked BEFORE the sign test: shrinkage drives a noise-sized gap
        # to exactly 0.0, which compares as non-negative and would other-
        # wise be reported as "we under-claim" — a different finding.
        out["applied"] = False
        out["reason"] = (f"the {abs(gap) * 100:.1f}-point gap is inside one "
                         f"standard error ({se * 100:.1f}) — noise, not bias")
    elif shift >= 0:
        out["applied"] = False
        out["reason"] = ("measured, not applied — the fit says we UNDER-claim,"
                         " and we do not raise stakes on that")
    elif not out["holdout"].get("ran"):
        out["applied"] = False
        out["reason"] = ("fitted but not validated — "
                         + out["holdout"].get("reason", ""))
    elif not out["holdout"]["improved"]:
        # The pre-registered kill condition, honoured rather than
        # explained away: a correction that only improves the data it was
        # fitted on has demonstrated nothing.
        h = out["holdout"]
        k = h.get("origins") or 0
        out["applied"] = False
        if h.get("walk_forward_note"):
            out["reason"] = ("fitted but not validated — "
                             + h["walk_forward_note"])
        else:
            out["reason"] = (
                f"fitted, then refused by its own walk-forward — it closed "
                f"the gap in {h.get('gap_improved_in', 0)} of {k} block(s) "
                f"and improved Brier in {h.get('brier_improved_in', 0)} of "
                f"{k}; on the last {h['test_n']} bets the gap went "
                f"{h['gap_before'] * 100:.1f} → {h['gap_after'] * 100:.1f} "
                f"pts and Brier {h['brier_before']:.4f} → "
                f"{h['brier_after']:.4f}")
    else:
        out["applied"] = True
        # Says what the row's own numbers do NOT: how much of the measured
        # gap survived the shrinkage, and whether the fit scores better for
        # it. Restating claimed/landed here would just print them twice.
        h = out["holdout"]
        out["reason"] = (f"keeps {keep * 100:.0f}% of the gap — the rest is "
                         f"inside the noise · held out on the last "
                         f"{h['test_n']}: gap {h['gap_before'] * 100:.1f} → "
                         f"{h['gap_after'] * 100:.1f} pts")
    return out


def measure(lconn, stored: dict | None = None,
            min_settled: int = MIN_SETTLED) -> dict:
    """Fit the haircut for every sport in the journal, plus the pool.

    OPEN FINDING, 2026-09-02, LEFT AS IT IS ON PURPOSE. The pool below is
    built by walking the sports in NAME order and concatenating them, so
    it is sport-blocked, not chronological — and `_holdout` is documented
    on the assumption that "pairs arrive in journal order". They do,
    within a sport. Across sports they do not: with 808 mlb rows and 69
    wnba ones, every wnba row lands after every mlb row because 'w' sorts
    after 'm', which puts all 69 of them in the walk-forward's last block
    and its final held-out window and none of them in any training
    window.

    It matters. On a reconstruction of the droplet's 2026-09-02 table
    (808 mlb refused 1-of-3, 69 wnba, pooled −0.143 applied), the pooled
    verdict flips with the ORDER of the same 877 rows and nothing else:
    sport-blocked it passes 2-of-3 and the final block; ordered by ts, or
    with wnba first, it fails 1-of-3 exactly as mlb's own does. The fit
    itself is identical — order changes only the exam.

    Not changed here because this commit was scoped to the fallback rule
    and fixing the order changes what the pooled shift IS for every sport
    borrowing it, which is a live pricing change that deserves its own
    run and its own before/after. `POOL_BORROW_MAX_SHARE` already stops
    the case that motivated it; the residue is that sports genuinely
    under the floor still borrow a fit whose gate was scored partly on
    their own rows. The fix, when someone takes it: build `pool` from
    `rows` in the order `_settled` returned them, resolving each row's
    prior shift by its sport, instead of concatenating per-sport lists.
    """
    stored = stored or {}
    stamp = stored.get("fitted_at") or ""

    rows = _settled(lconn)
    by_sport: dict[str, list] = {}
    for r in rows:
        by_sport.setdefault((r["sport"] or "").lower(), []).append(r)

    sports, pool = {}, []
    for sport, srows in sorted(by_sport.items()):
        # Which shift was live for THIS sport's rows — asked of the store
        # that was live, by the same rule the betting path used.
        #
        # It used to be asked a different way: "its own stored shift if
        # that is non-zero, otherwise the pooled one if it borrowed". That
        # reads the same and is not, because a REFUSED fit still stores a
        # shift. On 2026-09-02 MLB's store held −0.117 with applied
        # false, so the refit un-shifted 808 rows by a number the board
        # had never applied to any of them — it was pricing with the
        # pooled −0.143 — and then fitted on claims nobody ever published.
        # A young sport under the floor had the same problem for the same
        # reason. `live_shift` is the betting path's own rule, so the two
        # cannot drift apart again.
        prior = live_shift(stored, sport)
        pairs = _pairs(srows, prior, stamp)
        sports[sport] = _entry(pairs, min_settled)
        pool.extend(pairs)
    return {"sports": sports, "pooled": _entry(pool, min_settled),
            "min_settled": min_settled}


#: How much of the pooled sample a sport may BE and still be allowed to
#: borrow the pooled fit after its own fit was refused.
#:
#: THE TABLE THIS EXISTS FOR — `launch.py --haircut`, droplet, 2026-09-02:
#:
#:     all sports  877  52.7%  48.5%  −4.2p  −0.143  LIVE
#:     mlb         808  52.8%  49.0%  −3.7p  −0.117  off — fitted, then
#:                                                   refused by its own
#:                                                   walk-forward
#:     wnba         69  52.1%  42.0% −10.1p  −0.261  off — collecting
#:
#: MLB is 808 of those 877 rows. Its own walk-forward closed the gap in 1
#: of 3 blocks and improved Brier in 1 of 3, so its fit was refused — and
#: `shift_for` then handed it the pooled one, which is the same 808 rows
#: plus 69 WNBA ones. Every MLB bet on the board, 92% of the volume, was
#: priced with a correction MLB's own data had just declined. A refusal
#: became an application by falling through.
#:
#: WHY THE FALLBACK'S OWN JUSTIFICATION DOES NOT REACH THIS CASE. It is
#: written for a small sport borrowing from a big one: "the thing being
#: corrected is a property of the SELECTION PROCEDURE ... shared by every
#: sport", so evidence from the rest of the board is evidence about the
#: sport that has none of its own. Reverse the sizes and the sentence
#: stops being true. When the borrower IS the pool, the pooled fit is not
#: evidence from elsewhere — it is the borrower's own evidence, re-cut at
#: different block boundaries with 69 foreign rows on the end, answering
#: a question that already came back no. The pool cannot be a second
#: opinion on data that is mostly itself.
#:
#: AND THE TWO VERDICTS ARE NOT EVEN SCORED ON THE SAME BETS. `_origins`
#: cuts by n, so 877 rows put the walk-forward's boundaries at 351/526/701
#: and the final 70/30 cut at 613; 808 rows put them at 324/485/646 and
#: 565. Worse, `measure` builds the pool by sport name — see its own
#: docstring — so all 69 WNBA rows land in the pooled walk-forward's LAST
#: block (39% of it) and its final held-out window (26% of it), and in
#: none of its training windows. The pooled fit passes a gate whose
#: deciding windows are a quarter foreign rows; MLB's fails one scored on
#: MLB alone. Same estimator, different exam.
#:
#: AND THE POOLED CUT IS NOT A BETTER NUMBER FOR MLB EITHER — the
#: question worth asking before treating any of this as bookkeeping. The
#: pooled shift is LARGER than the one MLB's own data asked for (−0.143
#: against −0.117; 3.6 points off a 52.8% claim rather than 2.9) and in
#: the same direction, and the direction is what MLB's walk-forward
#: rejected: on the last 243 MLB bets the claim landed within 0.6 points
#: of the result and the smaller cut moved it to 3.6 points wrong. A
#: correction that overshoots overshoots further when you take more of
#: it, and the error it now makes is an UNDER-claim — bets dropped and
#: stakes shrunk on picks that were priced honestly. Scored on MLB rows
#: only, in MLB's own held-out windows, on the reconstruction in
#: `tests/test_selection_haircut.two_sport_journal`: pooled is worse than
#: own and own is worse than nothing in three of four windows, the most
#: recent included (gap 0.1 → 3.5 → 4.7 points, Brier 0.2452 → 0.2465 →
#: 0.2475). Borrowing here is not a safe default; it is the worst of the
#: three numbers available.
#:
#: 0.50 is the line because "mostly" is the claim being made. Below it the
#: pool is genuinely other sports and the fallback's reasoning holds; at
#: 92% it does not. A sport that is most of the pool and has been refused
#: prices on its own numbers, which is where the board started.
POOL_BORROW_MAX_SHARE = 0.50


def borrow_block(blob: dict, sport: str) -> str:
    """Why ``sport`` may not fall back to the pooled fit — '' if it may.

    ONE PREDICATE, FOUR READERS: the live betting path (`shift_for`),
    what the page is told (`basis_for`, `report`), the terminal table
    (`launch.py --haircut`) and the refit's un-shift (`live_shift`, via
    `measure`). They have to agree exactly. A refit that un-shifted rows
    the board never shifted would measure a claim that was never
    published, which is the oscillation the `fitted_at` stamp exists to
    prevent, arrived at from the other direction.
    """
    sports = blob.get("sports") or {}
    own = sports.get((sport or "").lower()) or {}
    pooled = blob.get("pooled") or {}
    if own.get("applied") or not pooled.get("applied"):
        return ""                  # nothing to borrow, or no need to
    own_n = int(own.get("n") or 0)
    if own_n < int(blob.get("min_settled", MIN_SETTLED)):
        # Under the floor the sport has returned no verdict of its own,
        # so there is none to route around: the pooled fit is the only
        # evidence in the room and it cleared the floor and the
        # walk-forward on its own sample. This is the case the fallback
        # was written for, and it is untouched — including when the
        # sport is a large share of a young pool, because "we have not
        # measured you yet" is not "we measured you and said no".
        return ""
    pooled_n = int(pooled.get("n") or 0)
    share = (own_n / pooled_n) if pooled_n else 0.0
    if share <= POOL_BORROW_MAX_SHARE:
        return ""
    # Deliberately short, and it does not restate the refusal itself:
    # every surface that prints this prints the sport's own row, with its
    # own reason on it, directly above.
    return (f"its own fit was refused and the pooled fit is "
            f"{share * 100:.0f}% the same {own_n} bets")


def live_shift(blob: dict, sport: str) -> float:
    """What a stored blob says this sport's claims were priced with.

    `shift_for` is this against the file on disk; this is it against a
    blob already in hand — `measure`'s, which must un-shift by exactly
    what the board applied, and `shapecheck`'s, which restates the same
    journal. There were three copies of this rule and two of them had
    drifted; now there is one.
    """
    own = (blob.get("sports") or {}).get((sport or "").lower()) or {}
    if own.get("applied"):
        return float(own.get("shift") or 0.0)
    pooled = blob.get("pooled") or {}
    if pooled.get("applied") and not borrow_block(blob, sport):
        return float(pooled.get("shift") or 0.0)
    return 0.0


def refresh(lconn, path=None, min_settled: int = MIN_SETTLED,
            dry_run: bool = False) -> dict:
    """Refit from the journal and store the result. Called at settle time."""
    path = Path(path if path is not None else DEFAULT_PATH)
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}
    out = measure(lconn, stored, min_settled)
    # A journal with nothing settled in it cannot re-fit anything, and
    # writing the empty result would REPLACE a real correction with a
    # blank one. Caught in the suite: a settle-pass test running against
    # an empty ledger overwrote the live store mid-run, after which the
    # rest of the suite priced with no haircut at all and went green.
    if not out["pooled"].get("n") and stored:
        return {**stored, "unchanged": "no settled bets to fit"}
    out["fitted_at"] = _dt.date.today().isoformat()
    out["was"] = {"fitted_at": stored.get("fitted_at"),
                  "pooled": (stored.get("pooled") or {}).get("shift"),
                  "sports": {k: (v or {}).get("shift")
                             for k, v in (stored.get("sports") or {}).items()}}
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2))
        reset_cache()
    return out


def load(path=None) -> dict:
    """The store, cached on mtime."""
    path = Path(path if path is not None else DEFAULT_PATH)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache.pop(str(path), None)
        return {}
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        blob = json.loads(path.read_text())
        if not isinstance(blob, dict):
            blob = {}
    except (ValueError, OSError):
        blob = {}
    _cache[str(path)] = (mtime, blob)
    return blob


def reset_cache() -> None:
    _cache.clear()


def shift_for(sport: str, path=None) -> float:
    """The live haircut for a sport, in log-odds. Never positive.

    A sport with its own applied fit uses it. A sport still under the
    floor borrows the pooled one, because the thing being corrected is a
    property of the SELECTION PROCEDURE — taking the top edges out of a
    noisy estimator — and that procedure is shared by every sport on the
    board. Borrowing is labelled everywhere it is shown.

    What it will not do is borrow around its own refusal: a sport that is
    most of the pooled sample and was refused by its own walk-forward
    gets nothing, because the pool is then not a second opinion. See
    :data:`POOL_BORROW_MAX_SHARE`.
    """
    if not _enabled:
        return 0.0
    return live_shift(load(path), sport)


def basis_for(sport: str, path=None) -> str:
    """'own' | 'pooled' | '' — which fit a sport is actually using.

    '' covers both "nothing was fitted" and "a fit exists and this sport
    is not allowed to use it", which the caller tells apart by asking
    `borrow_block` for the sentence.
    """
    blob = load(path)
    own = (blob.get("sports") or {}).get((sport or "").lower()) or {}
    if own.get("applied"):
        return "own"
    if (blob.get("pooled") or {}).get("applied") and not borrow_block(blob,
                                                                     sport):
        return "pooled"
    return ""


def apply_haircut(sport: str, p: float, path=None) -> float:
    """The one call the betting paths make. No store → returns ``p``."""
    return shift_prob(p, shift_for(sport, path))


def points_at(p: float, sport: str, path=None) -> float:
    """How many probability POINTS the LIVE haircut takes off a claim.

    Log-odds is the honest frame to fit in and a terrible one to read
    in, so this is the reader's frame.

    "Everything user-facing quotes this instead" is what this docstring
    used to say, and the nightly sweep found nothing quoting it at all
    (2026-09-02). What the surfaces actually use is near it but not it:
    `launch.py --haircut` prints `(out - p)` for the fit in the table it
    is drawing, and the site prints `_entry`'s `example_55`. Both are
    deliberate — the table shows what a PARTICULAR fit would do, which
    is not always the live one, and this reads `shift_for`, which is.

    So the sentence was a claim about the codebase rather than about the
    function, and it was wrong. Kept as the one call that answers "what
    is the live cut worth at this price" without the caller re-deriving
    it; described as what it is.
    """
    return apply_haircut(sport, p, path) - float(p)


#: The price bands the haircut is CHECKED against, matching
#: `stakecheck.py`'s so the two tools cannot disagree about which bets
#: are in which bucket. `(label, low, high)`, American odds, high
#: exclusive.
PRICE_BANDS = (
    ("shorter than +100", -100000, 100),
    ("+100 to +119", 100, 120),
    ("+120 to +199", 120, 200),
    ("+200 and longer", 200, 100001),
)


def _band_of(odds) -> str | None:
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    for label, lo, hi in PRICE_BANDS:
        if lo <= o < hi:
            return label
    return None


def bands(lconn, categories=LEARNING_CATEGORIES) -> dict:
    """Does the over-claim depend on the PRICE? Measured, applied to nothing.

    THE QUESTION THIS MODULE'S OWN DOCSTRING RAISES. "A single pooled
    number applied to every price is a blunt instrument" — and the
    droplet's book on 2026-09-02 says the instrument may be too blunt.
    Over 680 settled bets the miss grows monotonically with the price:

        shorter than +100   -2.1 pts   (inside one SE)
        +100 to +119        +0.1
        +120 to +199        -4.6
        +200 and longer    -15.4       (16 bets)

    One shift cannot fit that shape: fitted on the pool it over-corrects
    the short prices, where the claim is already honest, and
    under-corrects the long ones, where the money actually leaks.

    WHY THE FIX IS NOT MODEL CALIBRATION, which is the trap here. The
    raw touchdown model — the plus-money market — UNDER-claims on every
    band of its 22,099 graded player-weeks (claimed .155, landed .200).
    Raising those probabilities to fix the surface would make the
    selected subset worse, because selection is what turns an
    under-claiming surface into an over-claiming board: it picks the
    rows where model minus market is largest, which is where the
    model's error is most positive. That is the winner's curse this
    module was written for, now visible from both ends.

    THIS REPORTS AND CHANGES NOTHING, deliberately. Sixteen bets in the
    band that matters cannot fit a parameter, and a price-dependent
    haircut chosen on the sample that suggested it is the exact mistake
    `_holdout` exists to prevent. The band that would justify one has to
    reach `MIN_SETTLED` on its own and survive its own noise, and this
    is the instrument that says when it has.
    """
    rows = _settled(lconn, categories)
    stored = load()
    out: dict = {"bands": [], "n": 0,
                 "min_settled": MIN_SETTLED,
                 "note": ("report only — no band correction is applied, and "
                          "none will be until a band clears the floor on its "
                          "own and survives its own noise")}
    by_band: dict = {}
    for r in rows:
        label = _band_of(r["odds"])
        if label is None:
            continue
        by_band.setdefault(label, []).append(r)
    for label, lo, hi in PRICE_BANDS:
        got = by_band.get(label) or []
        sp = (stored.get("sports") or {})
        prior = (stored.get("pooled") or {}).get("shift", 0.0) or 0.0
        stamp = (stored.get("fitted_at") or "")
        pairs = _pairs(got, prior, stamp)
        n = len(pairs)
        if not n:
            out["bands"].append({"band": label, "n": 0})
            continue
        claimed = sum(p for p, _ in pairs) / n
        landed = sum(o for _, o in pairs) / n
        gap = landed - claimed
        se = math.sqrt(max(landed * (1.0 - landed), 1e-9) / n)
        out["bands"].append({
            "band": label, "n": n,
            "claimed": round(claimed, 4), "landed": round(landed, 4),
            "gap": round(gap, 4), "se": round(se, 4),
            "keep": round(_keep_fraction(gap, se), 3),
            "enough": n >= MIN_SETTLED,
            "real": bool(_keep_fraction(gap, se) > 0 and n >= MIN_SETTLED),
        })
        out["n"] += n
    return out


def band_lines(got: dict) -> list:
    """The band table as text, for a terminal and a weekly log."""
    lines = [f"selection haircut by price — {got['n']:,} settled bets "
             f"({got['note']})"]
    lines.append(f"  {'band':<20}{'n':>7}{'claimed':>10}{'landed':>9}"
                 f"{'gap':>9}{'1 SE':>8}  verdict")
    for b in got["bands"]:
        if not b.get("n"):
            lines.append(f"  {b['band']:<20}{0:>7}   no settled bets in this band")
            continue
        if not b["enough"]:
            verdict = f"collecting: {b['n']} of {got['min_settled']}"
        elif not b["real"]:
            verdict = "inside one standard error — noise"
        elif b["gap"] < 0:
            verdict = f"over-claiming, keeps {b['keep'] * 100:.0f}% of the gap"
        else:
            verdict = "under-claiming — never acted on"
        lines.append(f"  {b['band']:<20}{b['n']:>7}{b['claimed']:>10.3f}"
                     f"{b['landed']:>9.3f}{b['gap']:>+9.3f}{b['se']:>8.3f}"
                     f"  {verdict}")
    return lines


def report(path=None) -> dict:
    """The site's payload: the store plus the sentences it implies.

    Emitted even when nothing is applied — a page that only shows a
    correction when one exists cannot tell "calibrated" from "never
    measured", and those are very different things to be looking at.
    """
    blob = load(path)
    if not blob:
        return {"fitted_at": None, "sports": {}, "pooled": {"n": 0},
                "min_settled": MIN_SETTLED, "live": False}
    sports = blob.get("sports") or {}
    pooled = blob.get("pooled") or {}
    live = bool(pooled.get("applied")) or any(
        (v or {}).get("applied") for v in sports.values())
    blocked = {sp: borrow_block(blob, sp) for sp in sports}
    return {"fitted_at": blob.get("fitted_at"),
            "sports": sports, "pooled": pooled,
            "min_settled": blob.get("min_settled", MIN_SETTLED),
            "live": live,
            "using": {sp: basis_for(sp, path) for sp in sports},
            # Sports the pooled fit is LIVE for elsewhere and refused to.
            # Without this the page can only say "not applied", which
            # reads as "nothing was measured" — the one thing it is not.
            "not_borrowing": {sp: why for sp, why in blocked.items() if why}}
