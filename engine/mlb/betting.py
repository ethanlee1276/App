"""MLB betting model.

Reuses the shared odds stack (best-line shopping, de-vig, EV, confidence,
fractional-Kelly, grading) but prices each market with the right distribution:
a normal model for total bases / hits / strikeouts, and a **Poisson** model
for home runs — a 0.5 HR line is P(at least one homer), which a normal
approximation gets badly wrong at λ ≈ 0.2.
"""

from __future__ import annotations

import math

from ..betting import Recommendation, _confidence_score, _grade, _kelly_stake
from ..odds import best_over_line, expected_value
from ..statmath import prob_over
from .models import MLBProp, HOME_RUNS
from .projection import MLBProjection


def _poisson_over(line: float, lam: float) -> float:
    """P(X > line) for X ~ Poisson(lam) with a half-point line."""
    k_needed = math.floor(line) + 1          # over 0.5 → 1+, over 1.5 → 2+
    # P(X >= k) = 1 - CDF(k-1)
    cdf = 0.0
    term = math.exp(-lam)
    for i in range(k_needed):
        if i > 0:
            term *= lam / i
        cdf += term
    return max(0.0, 1.0 - cdf)


def evaluate_mlb_prop(prop: MLBProp, proj: MLBProjection) -> Recommendation:
    best = best_over_line(prop.lines)

    if prop.market == HOME_RUNS:
        hit = _poisson_over(best.line, proj.mean)
    else:
        hit = prob_over(best.line, proj.mean, proj.std)

    edge = hit - best.fair_prob
    ev = expected_value(hit, best.odds)
    confidence = _confidence_score(edge, hit, proj)
    grade = _grade(confidence, edge)
    stake = _kelly_stake(hit, best.odds) if grade != "Pass" else 0.0

    return Recommendation(
        player=prop.player, team=prop.team, opponent=prop.opponent,
        market=prop.market, side="OVER",
        book=best.book, line=best.line, odds=best.odds,
        projection=round(proj.mean, 2),
        proj_low=round(max(0.0, proj.mean - proj.std), 2),
        proj_high=round(proj.mean + proj.std, 2),
        hit_prob=round(hit, 4), fair_prob=round(best.fair_prob, 4),
        edge=round(edge, 4), ev_per_unit=round(ev, 4),
        confidence=confidence, stake_units=round(stake, 2), grade=grade,
        reasons=list(proj.reasons), trend=proj.form.trend,
    )
