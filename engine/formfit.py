"""Fit the model's own recipe: how much recent form is actually worth.

Rung two of the self-tuning ladder. The temperature refit (calibrate.py)
corrects the model's CONFIDENCE after the fact; this fits the blend the
projection is built from in the first place — the window weights in
``engine/form.py`` that decide whether a player's number leans on his last
week or his long-run track record. Those weights came from the spec
(docs/MLB_MODEL.md §6), which is to say from a human. Now the record gets
a vote.

**One dial, not seven free weights.** Fitting seven window weights
independently on a season of data is an overfitting machine — with enough
knobs the fit will explain noise and call it insight. The search space
here is a single recency dial ``r``:

    r = 0    exactly the spec's hand-tuned curve — the default survives
             unless the record beats it
    r > 0    interpolate toward ANCHOR_HOT (recent games dominate)
    r < 0    interpolate toward ANCHOR_STEADY (long run dominates)

Every candidate curve is a convex blend of normalized curves, so weights
always sum to one. The fit walks the history DB forward exactly like the
temperature fit — each game projected only from earlier games, scored by
Brier on the model's RAW probabilities (calibration disabled, or we'd fit
a recipe for an already-corrected model and compound).

**±1.0 is a wall, not a search cap.** ``r`` interpolates between the spec
curve and a named endpoint, so ``r = +1.0`` IS :data:`ANCHOR_HOT`
exactly — there is no "further" to go. Extrapolating past it is an affine
combination with a negative coefficient on the base curve, and the first
step out (r = 1.1 on the MLB curve) already drives ``vs_opp`` to −0.01: a
negative weight means subtracting a player's own history from his
projection, which is not a stronger lean on recent form, it is nonsense.
``family`` clamps for that reason. So a dial resting at ±1.0 must never be
read as "widen the grid". The two readings that ARE available: if the fit
was adopted, the model wants a hotter recipe than this family contains and
:data:`ANCHOR_HOT` itself is the thing to revisit; if it was not adopted —
and :attr:`FormFit.plateau` says most of the grid tied — the surface is
flat and the argmin simply landed on an edge, which is what argmins do.

**Adoption is earned, not automatic.** A fitted dial is stored but only
APPLIED when it beat the spec curve by at least :data:`MIN_GAIN` Brier on
at least :data:`MIN_SAMPLES` settled predictions. In-sample argmin of a
21-point grid will always find SOME winner; the margin and floor are what
separate "the record moved the dial" from "the noise did". A dial at the
grid edge is flagged the way a boundary temperature is: wanting more than
the family allows means something is wrong upstream, not that the family
should stretch.

Order matters: refit the temperature (calibrate.py) AFTER adopting new
weights — the old correction was learned for the old model.

Home runs are excluded by design: the rare-event path in projection.py
already replaced form blending there (an empirical-Bayes rate), so a
recency dial has nothing to act on.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from pathlib import Path

from . import modelstate as _modelstate

DEFAULT_PATH = Path(_modelstate.path("formfit.json"))

#: Settled walk-forward predictions required before a fitted dial may be
#: applied — same floor the temperature fit uses.
MIN_SAMPLES = 200
#: The fitted curve must beat the spec curve by at least this much Brier
#: to be adopted. Below it, the honest reading is "the spec curve is
#: fine" — a tie goes to the simpler story.
MIN_GAIN = 0.0005
#: The dial grid. Symmetric around the spec curve at 0.
GRID = [round(-1.0 + 0.1 * i, 1) for i in range(21)]

#: The two ends of the family. Both normalized; every interpolation
#: between a normalized base and these stays normalized.
ANCHOR_HOT = {"last1": 0.25, "last3": 0.35, "last5": 0.25,
              "last10": 0.10, "season": 0.05, "career": 0.0, "vs_opp": 0.0}
ANCHOR_STEADY = {"last1": 0.0, "last3": 0.05, "last5": 0.10,
                 "last10": 0.30, "season": 0.35, "career": 0.10,
                 "vs_opp": 0.10}


def family(base: dict, r: float) -> dict:
    """The candidate curve at dial ``r``: the base curve pulled toward the
    hot anchor (r>0) or the steady anchor (r<0). r=0 IS the base."""
    r = max(-1.0, min(1.0, float(r)))
    anchor = ANCHOR_HOT if r >= 0 else ANCHOR_STEADY
    t = abs(r)
    return {k: round((1.0 - t) * base.get(k, 0.0) + t * anchor.get(k, 0.0), 6)
            for k in set(base) | set(anchor)}


def _brier(pairs) -> float:
    return sum((p - won) ** 2 for p, won in pairs) / len(pairs)


@dataclasses.dataclass
class FormFit:
    sport: str
    market: str
    r: float                    # the fitted dial
    samples: int
    brier_default: float        # spec curve (r=0), same walk-forward
    brier_fitted: float         # best curve on the grid
    adopted: bool               # did it EARN application?
    weights: dict               # the curve the dial produces
    curve: dict = dataclasses.field(default_factory=dict)   # r -> Brier

    @property
    def at_boundary(self) -> bool:
        return abs(self.r) >= GRID[-1] - 1e-9

    @property
    def plateau(self) -> int:
        """How many grid points score within MIN_GAIN of the best.

        The argmin alone cannot say whether a dial MEANT it. A search over
        21 points always returns a winner, and on a flat surface the winner
        is wherever the noise happened to dip — the edges as readily as the
        middle. This is the honest counterweight: 21 of 21 within the
        adoption margin means the curve barely responds to the dial and the
        argmin is decoration; 2 of 21 means there is a real slope.

        Zero when the curve was not recorded (a fit from an older store).
        """
        if not self.curve:
            return 0
        best = min(self.curve.values())
        return sum(1 for v in self.curve.values() if v - best < MIN_GAIN)

    @property
    def verdict(self) -> str:
        if not self.adopted:
            s = "default kept — the spec curve was not beaten by enough to matter"
            if self.at_boundary and self.plateau:
                # An unadopted boundary is not the dial straining at a
                # limit — nothing was applied. Say which it is.
                s += (f"; the argmin sat at the grid edge, but {self.plateau} "
                      f"of {len(self.curve)} dial settings scored within the "
                      f"same margin, so that is where a flat search landed")
            return s
        lean = "recent form" if self.r > 0 else "the long run"
        s = f"the record moved the dial {self.r:+.1f} toward {lean}"
        if self.at_boundary:
            s += (" — AT THE GRID EDGE; wanting more than the family allows "
                  "usually means a problem upstream, not a stronger lean")
        return s

    def to_dict(self) -> dict:
        return {"sport": self.sport, "market": self.market, "r": self.r,
                "samples": self.samples,
                "brier_default": round(self.brier_default, 5),
                "brier_fitted": round(self.brier_fitted, 5),
                "adopted": self.adopted, "weights": self.weights,
                # The whole Brier-vs-dial curve, not just its argmin. The
                # fit already computes all 21 points and used to throw 20
                # of them away, which left "dial +1.0, at the edge"
                # unreadable: a dial pressed hard against the wall and a
                # flat surface whose argmin happened to land there look
                # identical from the winner alone. Costs nothing to keep.
                "curve": {str(k): round(v, 6)
                          for k, v in sorted(self.curve.items())},
                "fitted": _dt.datetime.now().isoformat(timespec="seconds")}


def base_for(sport: str) -> dict:
    """The sport's hand-tuned spec curve — the dial's zero point."""
    from .form import WINDOW_WEIGHTS, MLB_WINDOW_WEIGHTS
    return MLB_WINDOW_WEIGHTS if sport == "mlb" else WINDOW_WEIGHTS


def fit(entries: list[dict], market: str, base: dict | None = None,
        min_history: int | None = None, sport: str = "mlb") -> FormFit | None:
    """Grid-search the dial by walk-forward Brier on raw probabilities.

    ``entries`` are the same player histories calibrate.py fits from. One
    backtest per grid point — this is the expensive fit (≈21× a
    temperature fit), which is why it runs from a CLI/nightly chore and
    never inside a page build. The harness comes from ``logwalk.walk``,
    so any sport with game logs and an engine fits through the same door.
    """
    from . import calibrate as cal
    from .logwalk import walk

    if base is None:
        base = base_for(sport)
    scores: dict[float, tuple[float, int]] = {}
    with cal.disabled():
        for r in GRID:
            report = walk(sport, entries, market,
                          min_history=min_history,
                          form_weights=family(base, r))
            if not report.pairs:
                return None
            scores[r] = (_brier(report.pairs), len(report.pairs))

    brier_default, samples = scores[0.0]
    # Ties break toward 0: the spec curve keeps the benefit of the doubt,
    # and among equals the smaller |r| is the simpler story.
    best_r = min(scores, key=lambda r: (scores[r][0], abs(r)))
    brier_fitted = scores[best_r][0]
    # A BOUNDARY DIAL IS REPORTED, NOT REFUSED, and the difference was
    # worth getting wrong once. nfl:rush_yds and nfl:rec_yds both fit to
    # r=+1.0 while nfl:receptions (-0.6) and nfl:pass_yds (-0.5) landed
    # inside, and the first two are exactly the markets shut for AUC 0.47
    # against a real book. That correspondence invites a guard refusing
    # the grid edge, the way `calibrate.is_reliable` refuses a boundary
    # temperature.
    #
    # It does not survive contact. Measured on the stored curves,
    # rush_yds has the LARGEST gradient of the four — a span of 0.00589
    # across the dial against ~0.0016 for the rest — so it is not a flat
    # search landing at the edge by noise. It genuinely wants the hot
    # end, and two tests here build ramps where recent form really does
    # predict and the hot end really is the answer.
    #
    # The reason it wants the hot end is upstream of this file. `fit`
    # scores through `logwalk.walk`, which prices every game against
    # `_naive_line` — the player's own trailing average. A recency curve
    # is then being asked which windows best predict a number computed
    # from those same windows, and the hot end wins because it is closest
    # to being the same object. The fix is the one `engine/propcal` made
    # for the calibrations: score against harvested book closes instead.
    # Until then the dial is honest about a question that is not the one
    # the board asks, and a guard here would only hide that.
    adopted = (samples >= MIN_SAMPLES
               and brier_default - brier_fitted >= MIN_GAIN
               and best_r != 0.0)
    return FormFit(sport=sport, market=market, r=best_r, samples=samples,
                   brier_default=brier_default, brier_fitted=brier_fitted,
                   adopted=adopted,
                   weights=family(base, best_r) if adopted else dict(base),
                   curve={r: b for r, (b, _) in scores.items()})


# --- persistence and the projection-time lookup ------------------------------
def save(fits: dict[str, FormFit], path=None) -> Path:
    """Merge these fits into the store. Merge, not replace: the store is
    shared by every sport, and an NFL fitting run must not erase the MLB
    keys it never looked at."""
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        stored = json.loads(p.read_text()) if p.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}
    stored.update({k: f.to_dict() for k, f in fits.items()})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stored, indent=1))
    return p


_cache: dict = {}


def _load(path=None) -> dict:
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if key in _cache:
        return _cache[key]
    try:
        raw = json.loads(p.read_text())
        out = raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        out = {}
    _cache.clear()
    _cache[key] = out
    return out


def weights_for(sport: str, market: str, path=None) -> dict | None:
    """The adopted curve for this market, or None for "use the default".

    The adoption rules are re-checked here, not only at fit time — a store
    edited by hand, or written by an older fitter, still can't smuggle an
    unearned curve into the projection path."""
    d = _load(path).get(f"{sport}:{market}")
    if not isinstance(d, dict) or not d.get("adopted"):
        return None
    w = d.get("weights")
    if not isinstance(w, dict) or not w:
        return None
    if int(d.get("samples", 0) or 0) < MIN_SAMPLES:
        return None
    total = sum(float(v) for v in w.values())
    if not 0.99 <= total <= 1.01:      # a curve that isn't a blend is a bug
        return None
    return w


def report(path=None) -> list[dict]:
    """Every stored fit, for the Record page — adopted or not. A dial the
    record examined and left alone is part of the story."""
    out = []
    for key, d in sorted(_load(path).items()):
        if not isinstance(d, dict):
            continue
        sport, _, market = key.partition(":")
        r = float(d.get("r", 0.0) or 0.0)
        curve = d.get("curve") if isinstance(d.get("curve"), dict) else {}
        vals = []
        for v in curve.values():
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        best = min(vals) if vals else None
        out.append({
            "sport": d.get("sport") or sport,
            "market": d.get("market") or market or key,
            "r": r, "adopted": bool(d.get("adopted")),
            "samples": int(d.get("samples", 0) or 0),
            "brier_default": d.get("brier_default"),
            "brier_fitted": d.get("brier_fitted"),
            "at_boundary": abs(r) >= GRID[-1] - 1e-9,
            # How many dial settings tied the winner, and out of how many.
            # Without this the argmin cannot be told from a coin flip on a
            # flat surface — see FormFit.plateau. 0/0 = fitted before the
            # curve was recorded; the page must not read that as a verdict.
            "plateau": (sum(1 for v in vals if v - best < MIN_GAIN)
                        if best is not None else 0),
            "grid_n": len(vals),
            "fitted": d.get("fitted"),
            "reading": ("leans on recent form" if d.get("adopted") and r > 0
                        else "leans on the long run" if d.get("adopted")
                        else "default kept"),
        })
    return out
