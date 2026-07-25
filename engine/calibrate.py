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
    """Persist ``{"<sport>:<market>": Calibration}`` as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: c.to_dict() for k, c in calibrations.items()}, indent=2))
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
                   path: Path | str = DEFAULT_PATH) -> tuple[float, float]:
    """Look up ``(temperature, intercept)``, defaulting to no correction."""
    global _cache
    if not _enabled:
        return (1.0, 0.0)
    if _cache is None:
        _cache = load(path)
    return _cache.get(f"{sport}:{market}", _cache.get(sport, (1.0, 0.0)))


def temperature_for(sport: str, market: str, path: Path | str = DEFAULT_PATH) -> float:
    """The temperature alone (kept for callers that don't need the bias)."""
    return correction_for(sport, market, path)[0]


def reset_cache() -> None:
    """Drop the cached calibration file (used by tests and after refitting)."""
    global _cache
    _cache = None
