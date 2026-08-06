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
from dataclasses import dataclass
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

    t, b = 1.0, 0.0
    best = brier(pairs, t, b)
    for _ in range(4):
        for cand in _GRID:                       # spread
            score = brier(pairs, cand, b)
            if score < best:
                best, t = score, cand
        for cand in _INTERCEPTS:                 # bias
            score = brier(pairs, t, cand)
            if score < best:
                best, b = score, cand
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
            "fitted_at": self.fitted_at,
        }


def fit(pairs: list[tuple[float, int]], sport: str = "", market: str = "",
        min_samples: int = 200) -> Calibration:
    """Fit a calibration from settled predictions."""
    t, b = fit_correction(pairs, min_samples=min_samples)
    return Calibration(
        temperature=t, intercept=b, samples=len(pairs),
        brier_before=brier(pairs, 1.0), brier_after=brier(pairs, t, b),
        sport=sport, market=market,
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
    global _cache
    _cache = None
