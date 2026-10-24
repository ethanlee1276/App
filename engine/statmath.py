"""Small statistics helpers implemented with the standard library only.

Keeping this dependency-free means the engine runs anywhere Python 3 runs,
with no pip install step — important for a tool meant to be picked up and run
quickly. If numpy/scipy are later added for the ML phase they can back these
same function signatures.
"""

from __future__ import annotations

import math
from typing import Sequence


def normal_cdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Cumulative distribution function of a normal via the error function."""
    if sigma <= 0:
        return 0.0 if x < mu else 1.0
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def prob_over(line: float, mu: float, sigma: float) -> float:
    """P(X > line) for X ~ Normal(mu, sigma)."""
    return 1.0 - normal_cdf(line, mu, sigma)


def prob_over_discrete(line: float, mu: float, sigma: float) -> float:
    """P(X > line) for a count stat (e.g. receptions) using a continuity
    correction. A prop "Over 4.5 receptions" hits on 5+, so we integrate the
    normal tail above the half-point, which the standard ``prob_over`` already
    does for a .5 line; this wrapper exists to make intent explicit."""
    return prob_over(line, mu, sigma)


def weighted_mean(pairs: Sequence[tuple[float, float]]) -> float:
    """Weighted mean of (value, weight) pairs. Ignores zero total weight."""
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return 0.0
    return sum(v * w for v, w in pairs) / total_w


def sample_std(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1). Returns 0 for < 2 values."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
