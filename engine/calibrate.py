"""Probability calibration — make the stated confidence match reality.

A model can rank bets well and still be badly *calibrated*: if everything it
calls 60% actually hits 70% (or 50%), then every edge it reports is wrong by
that gap, and stake sizing is wrong with it. Calibration is the part of "does
the model have an edge" that can be measured with **outcomes alone** — no
historical market prices needed — which makes it the first thing worth fixing.

The correction here is *temperature scaling*: a single parameter ``T`` applied
in log-odds space.

    T = 1   → unchanged
    T > 1   → pull probabilities toward 50% (the model was over-confident)
    T < 1   → push them away from 50% (the model was under-confident)

One parameter can't overfit the way a flexible curve can, which matters when a
season of props is only a few thousand samples. ``fit_temperature`` picks the T
that minimises the Brier score on held-out outcomes.

Standard library only.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "models" / "calibration.json"

# Search grid: 0.4 (sharpen hard) .. 6.0 (flatten hard).
#
# The upper end is deliberately generous. A badly over-confident model needs a
# large temperature, and if the grid stops short the fit silently returns the
# boundary — which looks like a real answer but means the correction was capped.
# Real data hit the old 2.5 ceiling on two markets, so the range now extends far
# enough that a boundary result genuinely signals something, and ``at_boundary``
# reports it when it happens.
_GRID = [round(0.40 + 0.02 * i, 2) for i in range(281)]
GRID_MIN, GRID_MAX = _GRID[0], _GRID[-1]

#: The two fitters that write this store, named so an entry can say which
#: one made it. journalfit.BASIS is the other half of the pair.
BASIS_HISTORY = "history"


def apply_temperature(p: float, temperature: float, intercept: float = 0.0) -> float:
    """Rescale a probability in log-odds space.

    ``logit(p') = logit(p) / temperature + intercept``

    The temperature controls *spread* (how far predictions sit from 50%); the
    intercept controls *bias* (which way they lean overall). Both are needed:
    temperature alone has 50% as a fixed point, so a model whose predictions
    cluster near 50% while outcomes run at 42% cannot be corrected by
    temperature at any value — real data showed exactly that, with the fit
    running to the search ceiling while the gap survived untouched.
    """
    if temperature <= 0:
        return p
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    if temperature == 1.0 and intercept == 0.0:
        return p
    odds = p / (1.0 - p)
    scaled = odds ** (1.0 / temperature)
    if intercept:
        scaled *= math.exp(intercept)
    return scaled / (1.0 + scaled)


def undo_temperature(p: float, temperature: float,
                     intercept: float = 0.0) -> float:
    """The exact inverse of :func:`apply_temperature`.

    ``logit(p) = temperature * (logit(p') - intercept)``

    This exists so a corrected market can be refitted honestly. Once a
    correction ships, every later journal row is post-correction, and
    fitting a temperature on post-correction claims learns a correction
    for an already-corrected number and compounds — which is why
    journalfit.fit_temperatures leaves owned keys alone. Recovering the
    model's own claim removes that objection: un-correct each row with
    the correction that was live when the bet was logged, and the whole
    history becomes one clean sample of the uncorrected model again.

    Round-trips to within floating-point error, so an un-correct followed
    by a re-correct is a no-op. The clamp in apply_temperature is the one
    lossy step: a claim outside [1e-6, 1-1e-6] does not come back.
    """
    if temperature <= 0:
        return p
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    if temperature == 1.0 and intercept == 0.0:
        return p
    scaled = p / (1.0 - p)
    if intercept:
        scaled /= math.exp(intercept)
    odds = scaled ** temperature
    return odds / (1.0 + odds)


def brier(pairs: list[tuple[float, int]], temperature: float = 1.0,
          intercept: float = 0.0) -> float:
    """Mean squared error of predicted probabilities against 0/1 outcomes."""
    if not pairs:
        return 0.0
    return sum((apply_temperature(p, temperature, intercept) - o) ** 2
               for p, o in pairs) / len(pairs)


# Intercept search: how far the whole distribution is shifted in log-odds.
# ±1.2 covers roughly a 25-point swing at the centre, far more than any
# believable model bias.
_INTERCEPTS = [round(-1.2 + 0.02 * i, 2) for i in range(121)]


def fit_temperature(pairs: list[tuple[float, int]], min_samples: int = 200) -> float:
    """Backwards-compatible: the temperature alone, ignoring any bias."""
    return fit_correction(pairs, min_samples=min_samples)[0]


def _odds_of(pairs: list) -> tuple[list, list]:
    """`(odds, outcomes)` — the part of the input the grid never changes.

    `apply_temperature` clamps p and forms `p / (1 - p)` on every call,
    and the grid calls it once per pair per candidate. The odds are a
    property of the pair, not of the candidate.
    """
    odds, outs = [], []
    for p, o in pairs:
        q = min(max(p, 1e-6), 1.0 - 1e-6)
        odds.append(q / (1.0 - q))
        outs.append(o)
    return odds, outs


def _brier_odds(odds: list, outs: list, temperature: float,
                intercept: float) -> float:
    """Brier from precomputed odds — the grid's inner loop.

    IDENTICAL ARITHMETIC TO `brier(pairs, t, b)`, in the same order, so
    this returns the same float rather than a close one. What it removes
    is work that never varied per pair: the clamp and the division above,
    and — the expensive one — `math.exp(intercept)`, which
    apply_temperature computed INSIDE the per-pair call. Across a fit
    that was 293 million exponentials where 1,608 would do.

    Measured on tests/test_isotonic.py, which is nothing but this loop:
    161s to 22s, and the same seven fits come back bit-identical. It
    matters off the test bench too — fit_correction runs on every deep
    calibration sweep, and the sweep is the thing that decides whether
    the board's probabilities are honest.
    """
    if temperature <= 0:
        return sum((o - p) ** 2 for p, o in zip(odds, outs)) / len(odds)
    n = len(odds)
    if temperature == 1.0 and intercept == 0.0:
        total = 0.0
        for d, o in zip(odds, outs):
            p = d / (1.0 + d)
            total += (p - o) ** 2
        return total / n
    inv = 1.0 / temperature
    eb = math.exp(intercept) if intercept else 1.0
    total = 0.0
    for d, o in zip(odds, outs):
        scaled = d ** inv
        if intercept:
            scaled *= eb
        total += (scaled / (1.0 + scaled) - o) ** 2
    return total / n


def fit_correction(pairs: list[tuple[float, int]],
                   min_samples: int = 200) -> tuple[float, float]:
    """Find ``(temperature, intercept)`` minimising Brier.

    Fitted by coordinate descent rather than a full 2-D sweep: the two
    parameters are close to independent (one sets spread, the other the
    centre), so alternating passes converge in a few rounds and stay cheap in
    pure Python.

    Returns ``(1.0, 0.0)`` — no correction — below the sample floor, since a
    handful of games can't establish either effect.
    """
    if len(pairs) < min_samples:
        return 1.0, 0.0

    odds, outs = _odds_of(pairs)
    t, b = 1.0, 0.0
    best = _brier_odds(odds, outs, t, b)
    for _ in range(4):
        moved = False
        for cand in _GRID:                       # spread
            score = _brier_odds(odds, outs, cand, b)
            if score < best:
                best, t, moved = score, cand, True
        for cand in _INTERCEPTS:                 # bias
            score = _brier_odds(odds, outs, t, cand)
            if score < best:
                best, b, moved = score, cand, True
        # A ROUND THAT MOVED NOTHING CANNOT MOVE ANYTHING NEXT TIME.
        # Both passes are deterministic in (t, b), and a full round
        # leaving both unchanged means the next round starts from the
        # identical state and scans the identical grid to the identical
        # answer. Stopping there is the same result, not an approximation
        # of it — the fits typically settle in two rounds and the other
        # two were re-deriving a decision already made.
        if not moved:
            break
    return t, b


@dataclass
class Calibration:
    temperature: float = 1.0
    intercept: float = 0.0
    samples: int = 0
    brier_before: float = 0.0
    brier_after: float = 0.0
    market: str = ""
    sport: str = ""
    #: When this correction was fitted, ISO date. Every journal row logged
    #: after it was priced UNDER it, and every row before it was not — which
    #: is the single fact a refit needs in order to un-correct the right
    #: rows and leave the rest alone. It was missing, so the first refit has
    #: to infer it from the store's mtime; nothing fitted from here on does.
    fitted_at: str = ""
    #: WHICH fitter produced this, and it is load-bearing. Two of them write
    #: to this one store: the deep fitter (calibrate.py) on hundreds of
    #: thousands of ingested player-game outcomes, and the journal fitter
    #: (journalfit.py) on a few hundred settled bets. They are not
    #: interchangeable and the journal one must never overwrite the other —
    #: 479 bets replacing 282,862 samples is a loss of three orders of
    #: magnitude of evidence. An entry with no basis is treated as NOT the
    #: journal fitter's, because the ones already on disk are the deep
    #: fitter's and guessing the other way is the expensive mistake.
    basis: str = ""
    #: The isotonic curve, when one won the bake-off — ``{}`` otherwise.
    #: Stored beside the temperature rather than instead of it, so an
    #: entry always carries a readable one-number summary and a reader
    #: who ignores this field gets the old behaviour rather than none.
    curve: dict = field(default_factory=dict)
    #: How the winner was chosen: held-out scores for every candidate,
    #: including the "apply nothing" baseline it had to beat. Kept so the
    #: decision is reconstructable from the store instead of trusted.
    bake_off: dict = field(default_factory=dict)

    @property
    def at_boundary(self) -> bool:
        """Did the fit land on the edge of the search range?

        That means the data wanted a correction larger than the search allowed,
        so the stored temperature is a cap rather than an optimum — and it
        usually indicates the underlying model is badly miscalibrated rather
        than that this particular number is right.
        """
        return self.temperature in (GRID_MIN, GRID_MAX)

    @property
    def bias_note(self) -> str:
        """The systematic lean, in probability points at the centre."""
        if abs(self.intercept) < 0.02:
            return ""
        centre = apply_temperature(0.5, self.temperature, self.intercept)
        pts = (centre - 0.5) * 100
        lean = "optimistic" if pts < 0 else "pessimistic"
        return (f"systematic {lean} bias of {abs(pts):.0f} points corrected "
                f"(a stated 50% becomes {centre:.0%})")

    @property
    def verdict(self) -> str:
        if self.temperature >= GRID_MAX:
            return ("model is SEVERELY over-confident — the fit hit the search "
                    "ceiling, so even this much flattening may not be enough")
        if self.temperature > 1.05:
            return "model was over-confident — probabilities pulled toward 50%"
        if self.temperature < 0.95:
            return "model was under-confident — probabilities sharpened"
        return "model was already well calibrated"

    def to_dict(self) -> dict:
        return {
            "temperature": self.temperature, "intercept": self.intercept,
            "samples": self.samples,
            "brier_before": round(self.brier_before, 5),
            "brier_after": round(self.brier_after, 5),
            "market": self.market, "sport": self.sport,
            "fitted_at": self.fitted_at, "basis": self.basis,
            "curve": self.curve, "bake_off": self.bake_off,
        }


#: Share of the sample held back to judge the two candidate correctors.
#: Chronological, not random: `logwalk.walk` emits pairs in time order and
#: a random split leaks the same weeks into both halves, which is how a
#: flexible fit passes a test it should fail.
HOLDOUT_FRACTION = 0.30
#: Below this the held-out slice cannot separate anything and the bake-off
#: is skipped — temperature only, as before.
MIN_HOLDOUT = 400


def bake_off(pairs: list[tuple[float, int]],
             min_samples: int = 200) -> tuple[str, dict]:
    """Temperature vs isotonic vs nothing, judged out of sample.

    Ethan, 2026-08-16, after asking what more the self-learning could do.
    The answer his own Record page gives: the calibrator has one knob and
    the error has more than one sign. A single temperature is a monotone
    squeeze around 50%, so above 50% its correction is one-signed — and
    MLB hits needs 66% pushed UP by 21 points and 83% pulled DOWN by 2.
    Measured on that shape, the temperature fit takes a claimed 83% to
    95% against a realised 81%: it makes the band FOURTEEN POINTS WORSE
    than applying nothing at all, while still improving the average
    because 92% of the samples sit in one middle bucket.

    So both are fitted on the earlier part of the sample and scored on the
    later part, and the winner has to beat doing NOTHING on that later
    part or neither is adopted. Isotonic can bend where the data bends,
    which also means it can bend where the noise bends; the held-out slice
    is the only thing standing between those two, and it is not optional.

    Returns ``(winner, detail)`` with winner in {"none", "temperature",
    "isotonic"} and detail carrying every score, so the decision is
    reconstructable from the store rather than trusted.
    """
    from . import isotonic as iso

    n = len(pairs)
    cut = int(n * (1.0 - HOLDOUT_FRACTION))
    train, test = pairs[:cut], pairs[cut:]
    if len(test) < MIN_HOLDOUT or len(train) < min_samples:
        t, b = fit_correction(pairs, min_samples=min_samples)
        return ("temperature" if (t, b) != (1.0, 0.0) else "none",
                {"ran": False,
                 "reason": f"held-out judge needs {MIN_HOLDOUT} later samples, "
                           f"has {len(test)}"})

    t, b = fit_correction(train, min_samples=min_samples)
    curve = iso.fit(train)
    scores = {"none": brier(test, 1.0, 0.0),
              "temperature": brier(test, t, b),
              "isotonic": iso.brier(test, curve) if curve else float("inf")}
    winner = min(scores, key=scores.get)
    return winner, {
        "ran": True, "train_n": len(train), "test_n": len(test),
        "knots": len(curve.knots),
        "held_out": {k: round(v, 5) for k, v in scores.items()
                     if v != float("inf")},
        "margin": round(scores["none"] - scores[winner], 5),
    }


def fit(pairs: list[tuple[float, int]], sport: str = "", market: str = "",
        min_samples: int = 200) -> Calibration:
    """Fit a calibration from settled predictions.

    Two candidate correctors compete and a held-out slice picks the
    winner — see :func:`bake_off`. Whichever form wins is then refitted on
    the WHOLE sample, which is the standard split: the held-out part
    chooses the model, and the full data estimates it. Refitting is safe
    here precisely because the choice was already made without it.
    """
    from . import isotonic as iso

    winner, detail = bake_off(pairs, min_samples=min_samples)
    t, b = fit_correction(pairs, min_samples=min_samples)
    curve = iso.fit(pairs) if winner == "isotonic" else iso.Curve()
    if winner == "none":
        t, b = 1.0, 0.0
    after = (iso.brier(pairs, curve) if winner == "isotonic"
             else brier(pairs, t, b))
    return Calibration(
        temperature=t, intercept=b, samples=len(pairs),
        brier_before=brier(pairs, 1.0), brier_after=after,
        sport=sport, market=market,
        curve=curve.to_dict() if curve else {}, bake_off=detail,
    )


# --- persistence ------------------------------------------------------------
def save(calibrations: dict[str, Calibration], path: Path | str = DEFAULT_PATH) -> Path:
    """Merge ``{"<sport>:<market>": Calibration}`` into the JSON store.

    Merge, not replace: the file is shared by every sport's fitter (the
    MLB deep fit, the NFL walk, the journal fitter's hoops/college keys),
    and one sport's run must not erase corrections it never fitted."""
    path = Path(path)
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}
    stored.update({k: c.to_dict() for k, c in calibrations.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, indent=2))
    return path


def load(path: Path | str = DEFAULT_PATH) -> dict:
    """Load ``{"<sport>:<market>": (temperature, intercept)}``.

    Missing file = no correction. Older files stored a temperature only; those
    still load, with a zero intercept."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    out: dict = {}
    for key, val in raw.items():
        if isinstance(val, dict) and "temperature" in val:
            try:
                out[key] = (float(val["temperature"]), float(val.get("intercept", 0.0)))
            except (TypeError, ValueError):
                continue
    return out


def load_curves(path: Path | str = DEFAULT_PATH) -> dict:
    """``{"<sport>:<market>": Curve}`` for the entries that carry one.

    Deliberately a SECOND accessor rather than a wider return from
    `load`. That function's contract — a plain (temperature, intercept)
    per key — is depended on by the runtime path, the journal fitter and
    every test, and widening it to accommodate a shape most entries do
    not have is how a small addition becomes a large one. An entry with
    no curve is simply absent here.
    """
    from .isotonic import Curve
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    out: dict = {}
    for key, val in raw.items():
        if isinstance(val, dict) and val.get("curve"):
            c = Curve.from_dict(val["curve"])
            if c:
                out[key] = c
    return out


_cache: dict | None = None
_enabled = True


def set_enabled(flag: bool) -> None:
    """Turn the stored correction on or off process-wide.

    Fitting **must** see the model's raw, uncorrected probabilities. If the
    current calibration is still applied while new parameters are being fitted,
    each run learns a correction for already-corrected input and then applies it
    to raw input — the corrections compound and the numbers stop meaning
    anything. Real runs showed this directly: a fit reporting "a stated 50%
    becomes 44%" was followed by a backtest whose predictions rose to 53%.
    """
    global _enabled
    _enabled = flag


class disabled:
    """Context manager: evaluate with calibration switched off (for fitting)."""

    def __enter__(self):
        set_enabled(False)
        return self

    def __exit__(self, *exc):
        set_enabled(True)
        return False


def correction_for(sport: str, market: str,
                   path: Path | str | None = None) -> tuple[float, float]:
    """Look up ``(temperature, intercept)``, defaulting to no correction.

    ``path=None`` resolves DEFAULT_PATH at CALL time — a default argument
    binds at import, so a repointed store (tests, tools) was silently
    ignored. Sixth appearance of this exact trap in the codebase."""
    global _cache
    if not _enabled:
        return (1.0, 0.0)
    if _cache is None:
        _cache = load(DEFAULT_PATH if path is None else path)
    temp, bias = _cache.get(f"{sport}:{market}", _cache.get(sport, (1.0, 0.0)))
    if temp in (GRID_MIN, GRID_MAX):
        # A boundary fit is the search failing, not a correction. Applying
        # it does real damage: measured on 21,271 home-run player-games,
        # the raw model said 10.2% against a realised 10.5% — essentially
        # perfect — and the stored boundary temperature dragged that to
        # 1.1%. The fit is kept on disk so is_reliable() can still flag
        # the market as unbettable, but it is never applied.
        return (1.0, 0.0)
    return (temp, bias)


_curves: dict | None = None


def calibrated(sport: str, market: str, p: float,
               path: Path | str | None = None) -> float:
    """Apply whatever correction this market carries. THE entry point.

    A stored isotonic curve wins over the temperature, because the curve
    only exists when it beat the temperature on a held-out slice (see
    `bake_off`). Everything else — the disable switch, the boundary rule
    that refuses to apply a capped fit — behaves exactly as it does for
    the temperature, since those are statements about whether a
    correction may be trusted at all rather than about its shape.

    A market with no curve takes the old path unchanged, so an entry
    written before any of this existed prices identically to before.
    """
    global _curves
    if not _enabled:
        return float(p)
    if _curves is None:
        _curves = load_curves(DEFAULT_PATH if path is None else path)
    temp, bias = correction_for(sport, market, path)
    if (temp, bias) == (1.0, 0.0):
        # correction_for neutralises a boundary fit; a curve fitted on the
        # same unreliable market must not sneak past that veto.
        curve = _curves.get(f"{sport}:{market}")
        stored = load(DEFAULT_PATH if path is None else path).get(
            f"{sport}:{market}")
        if stored and stored[0] in (GRID_MIN, GRID_MAX):
            return float(p)
        if curve:
            return curve.apply(p)
        return float(p)
    curve = _curves.get(f"{sport}:{market}")
    if curve:
        return curve.apply(p)
    return apply_temperature(p, temp, bias)


def is_reliable(sport: str, market: str,
                path: Path | str | None = None) -> bool:
    """False when this market's fit ran to the edge of the search range.

    A boundary fit means the data wanted a bigger correction than the
    search allowed, so the stored temperature is a cap, not an optimum —
    the fitter's own way of saying "this model is unreliable here, not
    merely miscalibrated". Home runs printed exactly that warning while
    still claiming ~25% on props the market prices near 12%.

    Betting a market whose calibration is capped is betting a number
    nobody can vouch for, so the engines treat this as a hard pass."""
    if not _enabled:
        return True
    global _cache
    if _cache is None:
        _cache = load(DEFAULT_PATH if path is None else path)
    # Read the STORED value, not correction_for() — that neutralises a
    # boundary fit before returning it, which would hide exactly the
    # condition this function exists to report.
    temp, _ = _cache.get(f"{sport}:{market}", _cache.get(sport, (1.0, 0.0)))
    return temp not in (GRID_MIN, GRID_MAX)


def temperature_for(sport: str, market: str, path: Path | str = DEFAULT_PATH) -> float:
    """The temperature alone (kept for callers that don't need the bias)."""
    return correction_for(sport, market, path)[0]


def reset_cache() -> None:
    """Drop the cached calibration file (used by tests and after refitting)."""
    global _curves
    _curves = None
    global _cache
    _cache = None
