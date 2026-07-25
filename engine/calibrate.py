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


def apply_temperature(p: float, temperature: float) -> float:
    """Rescale a probability in log-odds space. Guards the 0/1 endpoints."""
    if temperature <= 0:
        return p
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    if temperature == 1.0:
        return p
    odds = p / (1.0 - p)
    scaled = odds ** (1.0 / temperature)
    return scaled / (1.0 + scaled)


def brier(pairs: list[tuple[float, int]], temperature: float = 1.0) -> float:
    """Mean squared error of predicted probabilities against 0/1 outcomes."""
    if not pairs:
        return 0.0
    return sum((apply_temperature(p, temperature) - o) ** 2 for p, o in pairs) / len(pairs)


def fit_temperature(pairs: list[tuple[float, int]], min_samples: int = 200) -> float:
    """Find the temperature minimising Brier over ``(probability, outcome)``.

    Returns 1.0 (no correction) when there isn't enough data to fit
    responsibly — a handful of games can't tell us the model is miscalibrated.
    """
    if len(pairs) < min_samples:
        return 1.0
    best_t, best_score = 1.0, brier(pairs, 1.0)
    for t in _GRID:
        score = brier(pairs, t)
        if score < best_score:
            best_t, best_score = t, score
    return best_t


@dataclass
class Calibration:
    temperature: float = 1.0
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
            "temperature": self.temperature, "samples": self.samples,
            "brier_before": round(self.brier_before, 5),
            "brier_after": round(self.brier_after, 5),
            "market": self.market, "sport": self.sport,
        }


def fit(pairs: list[tuple[float, int]], sport: str = "", market: str = "",
        min_samples: int = 200) -> Calibration:
    """Fit a calibration from settled predictions."""
    t = fit_temperature(pairs, min_samples=min_samples)
    return Calibration(
        temperature=t, samples=len(pairs),
        brier_before=brier(pairs, 1.0), brier_after=brier(pairs, t),
        sport=sport, market=market,
    )


# --- persistence ------------------------------------------------------------
def save(calibrations: dict[str, Calibration], path: Path | str = DEFAULT_PATH) -> Path:
    """Persist ``{"<sport>:<market>": Calibration}`` as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: c.to_dict() for k, c in calibrations.items()}, indent=2))
    return path


def load(path: Path | str = DEFAULT_PATH) -> dict[str, float]:
    """Load ``{"<sport>:<market>": temperature}``. Missing file = no correction."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    out: dict[str, float] = {}
    for key, val in raw.items():
        if isinstance(val, dict) and "temperature" in val:
            try:
                out[key] = float(val["temperature"])
            except (TypeError, ValueError):
                continue
    return out


_cache: dict | None = None


def temperature_for(sport: str, market: str, path: Path | str = DEFAULT_PATH) -> float:
    """Look up a fitted temperature, falling back to 1.0 (no correction)."""
    global _cache
    if _cache is None:
        _cache = load(path)
    return _cache.get(f"{sport}:{market}", _cache.get(sport, 1.0))


def reset_cache() -> None:
    """Drop the cached calibration file (used by tests and after refitting)."""
    global _cache
    _cache = None
