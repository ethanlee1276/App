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
from .statmath import weighted_mean, sample_std, clamp

# How much each look-back window contributes. Re-fit to the spec's recency
# rule (docs/NFL_MODEL.md §5: last 2 ≈ 45%, last 4 ≈ 35%, season ≈ 20%):
# season averages blend September's team with December's — recent games
# describe the team that will actually play Sunday. Mapped onto our window
# structure, the recent windows (1/3/5) now carry ~75% and the long anchors
# (10/season/career/opponent) ~25%.
WINDOW_WEIGHTS = {
    "last1": 0.22,
    "last3": 0.33,
    "last5": 0.20,
    "last10": 0.10,
    "season": 0.09,
    "career": 0.03,
    "vs_opp": 0.03,
}

# MLB runs a GENTLER recency curve (docs/MLB_MODEL.md §6: last 7 ≈ 40% ·
# last 15 ≈ 30% · season 20% · vs-pitcher 10%): baseball's nightly variance
# is so large that a hot week means far less than a hot fortnight in the
# NFL, and batter-vs-pitcher history stays a small input because most of
# it is noise. Mapped onto the same window structure.
MLB_WINDOW_WEIGHTS = {
    "last1": 0.08,
    "last3": 0.17,
    "last5": 0.15,
    "last10": 0.30,
    "season": 0.20,
    "career": 0.00,
    "vs_opp": 0.10,
}


@dataclass
class FormResult:
    mean: float
    std: float
    trend: str            # "up", "down", or "flat"
    trend_delta: float    # last-3 avg minus prior-season avg, in stat units
    sample_games: int
    trend_mult: float = 1.0   # shade the projection toward recent form


def _avg(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def compute_form(
    logs: list[GameLog],
    career_avg: float,
    vs_opponent_avg: Optional[float],
    weights: dict | None = None,
) -> FormResult:
    """Blend look-back windows into a form-adjusted mean and a variance
    estimate. ``logs`` are ordered most-recent first. ``weights`` selects the
    sport's recency curve (default: the NFL spec's; MLB passes its own)."""
    weights = weights or WINDOW_WEIGHTS
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
        (v, weights[k])
        for k, v in windows.items()
        if v is not None and weights.get(k, 0) > 0
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
    trend_mult = 1.0
    if recent is not None and prior:
        trend_delta = recent - prior
        rel = trend_delta / prior if prior else 0.0
        if rel > 0.10:
            trend = "up"
        elif rel < -0.10:
            trend = "down"
        # Downward-only recency shade: a sustained cool-off pulls the projection
        # toward recent form (to -10%), so the model stops leaning on stale
        # early-season numbers for a player who's stopped producing. We do NOT
        # inflate hot streaks — books price recent heat fast and chasing it is a
        # classic bettor trap — so a hot bat instead earns a small *confidence*
        # bonus (see betting._trend_alignment), not a bigger projected number.
        trend_mult = clamp(1.0 + 0.30 * clamp(rel, -0.5, 0.0), 0.90, 1.0)

    return FormResult(
        mean=mean,
        std=std,
        trend=trend,
        trend_delta=trend_delta,
        sample_games=len(vals),
        trend_mult=trend_mult,
    )
