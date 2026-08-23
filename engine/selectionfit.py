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
blunt instrument fitted on 300 rows can do real damage. Four guards:

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

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "models" / "selection.json"

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
    """Fit the haircut for every sport in the journal, plus the pool."""
    stored = stored or {}
    stamp = stored.get("fitted_at") or ""
    sports_prior = {k: (v or {}).get("shift", 0.0)
                    for k, v in (stored.get("sports") or {}).items()}
    pooled_prior = (stored.get("pooled") or {}).get("shift", 0.0)

    rows = _settled(lconn)
    by_sport: dict[str, list] = {}
    for r in rows:
        by_sport.setdefault((r["sport"] or "").lower(), []).append(r)

    sports, pool = {}, []
    for sport, srows in sorted(by_sport.items()):
        # Which shift was live for THIS sport's rows: its own if it had
        # one, otherwise the pooled one it was borrowing.
        prior = sports_prior.get(sport)
        if not prior:
            prior = pooled_prior if _borrowed(stored, sport) else 0.0
        pairs = _pairs(srows, prior, stamp)
        sports[sport] = _entry(pairs, min_settled)
        pool.extend(pairs)
    return {"sports": sports, "pooled": _entry(pool, min_settled),
            "min_settled": min_settled}


def _borrowed(stored: dict, sport: str) -> bool:
    entry = (stored.get("sports") or {}).get(sport) or {}
    return not entry.get("applied") and bool(
        (stored.get("pooled") or {}).get("applied"))


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
    """
    if not _enabled:
        return 0.0
    blob = load(path)
    own = (blob.get("sports") or {}).get((sport or "").lower()) or {}
    if own.get("applied"):
        return float(own.get("shift") or 0.0)
    pooled = blob.get("pooled") or {}
    if pooled.get("applied"):
        return float(pooled.get("shift") or 0.0)
    return 0.0


def basis_for(sport: str, path=None) -> str:
    """'own' | 'pooled' | '' — which fit a sport is actually using."""
    blob = load(path)
    own = (blob.get("sports") or {}).get((sport or "").lower()) or {}
    if own.get("applied"):
        return "own"
    if (blob.get("pooled") or {}).get("applied"):
        return "pooled"
    return ""


def apply_haircut(sport: str, p: float, path=None) -> float:
    """The one call the betting paths make. No store → returns ``p``."""
    return shift_prob(p, shift_for(sport, path))


def points_at(p: float, sport: str, path=None) -> float:
    """How many probability POINTS the haircut takes off a claim of ``p``.

    Log-odds is the honest frame to fit in and a terrible one to read in.
    Everything user-facing quotes this instead.
    """
    return apply_haircut(sport, p, path) - float(p)


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
    return {"fitted_at": blob.get("fitted_at"),
            "sports": sports, "pooled": pooled,
            "min_settled": blob.get("min_settled", MIN_SETTLED),
            "live": live,
            "using": {sp: basis_for(sp, path) for sp in sports}}
