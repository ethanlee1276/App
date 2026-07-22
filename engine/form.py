"""Recent-form weighting.

Season averages hide streaks. This module blends several look-back windows
(last game, last 3, last 5, last 10, full season) plus career and
opponent-history baselines into a single form-adjusted mean, and reports a
trend so the explanation can say "heating up" or "cooling off".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import GameLog
from .statmath import weighted_mean, sample_std

# How much each look-back window contributes. Recent games are weighted more
# heavily than the season, but the season still anchors the estimate so one
# fluke game does not dominate.
WINDOW_WEIGHTS = {
    "last1": 0.14,
    "last3": 0.24,
    "last5": 0.20,
    "last10": 0.14,
    "season": 0.16,
    "career": 0.06,
    "vs_opp": 0.06,
}


@dataclass
class FormResult:
    mean: float
    std: float
    trend: str            # "up", "down", or "flat"
    trend_delta: float    # last-3 avg minus prior-season avg, in stat units
    sample_games: int


def _avg(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def compute_form(
    logs: list[GameLog],
    career_avg: float,
    vs_opponent_avg: Optional[float],
) -> FormResult:
    """Blend look-back windows into a form-adjusted mean and a variance
    estimate. ``logs`` are ordered most-recent first."""
    vals = [g.value for g in logs]

    windows = {
        "last1": _avg(vals[:1]),
        "last3": _avg(vals[:3]),
        "last5": _avg(vals[:5]),
        "last10": _avg(vals[:10]),
        "season": _avg(vals),
        "career": career_avg,
        "vs_opp": vs_opponent_avg,
    }

    pairs = [
        (v, WINDOW_WEIGHTS[k])
        for k, v in windows.items()
        if v is not None
    ]
    mean = weighted_mean(pairs)

    # Variance from the observed game log; fall back to a position-agnostic
    # coefficient of variation if we have too few games.
    std = sample_std(vals[:10])
    if std <= 0 and mean > 0:
        std = 0.35 * mean

    # Trend: recent 3 games versus the rest of the season.
    recent = _avg(vals[:3])
    prior = _avg(vals[3:]) if len(vals) > 3 else career_avg
    trend_delta = 0.0
    trend = "flat"
    if recent is not None and prior:
        trend_delta = recent - prior
        rel = trend_delta / prior if prior else 0.0
        if rel > 0.10:
            trend = "up"
        elif rel < -0.10:
            trend = "down"

    return FormResult(
        mean=mean,
        std=std,
        trend=trend,
        trend_delta=trend_delta,
        sample_games=len(vals),
    )
