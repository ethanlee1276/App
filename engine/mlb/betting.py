"""MLB betting model.

Reuses the shared odds stack (best-line shopping, de-vig, EV, confidence,
fractional-Kelly, grading) but prices each market with the right distribution:
a normal model for total bases / hits / strikeouts, and a **Poisson** model
for home runs — a 0.5 HR line is P(at least one homer), which a normal
approximation gets badly wrong at λ ≈ 0.2.
"""

from __future__ import annotations

import math

from ..betting import (
    Recommendation, _confidence_score, _grade, _kelly_stake,
    _trend_alignment, pick_side, temper_edge,
)
from ..calibrate import apply_temperature, temperature_for
from ..odds import expected_value
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


def evaluate_mlb_prop(prop: MLBProp, proj: MLBProjection,
                      allow_synthetic_line: bool = False) -> Recommendation:
    def p_over_at(line: float) -> float:
        if prop.market == HOME_RUNS:
            return _poisson_over(line, proj.mean)
        return prob_over(line, proj.mean, proj.std)

    side, best, hit_raw, fair, edge_raw = pick_side(prop.lines, p_over_at)
    # Correct the stated probability with whatever calibration was fitted from
    # real settled outcomes (1.0 = none fitted yet, so this is a no-op).
    hit_raw = apply_temperature(hit_raw, temperature_for("mlb", prop.market))
    hit, edge, credible = temper_edge(hit_raw, fair, best.book, allow_synthetic_line)
    ev = expected_value(hit, best.odds)
    trend_align = _trend_alignment(side, proj.form.trend)
    confidence = _confidence_score(edge, hit, proj, trend_align)
    grade = _grade(confidence, edge) if credible else "Pass"
    stake = _kelly_stake(hit, best.odds) if grade != "Pass" else 0.0

    reasons = list(proj.reasons)
    if not credible:
        reasons.insert(0, "No credible market edge — line unavailable or price looks off")
    elif side == "UNDER":
        reasons.insert(0, f"Model sides UNDER — projects {proj.mean:g} under the {best.line:g} line")

    return Recommendation(
        player=prop.player, team=prop.team, opponent=prop.opponent,
        market=prop.market, side=side,
        book=best.book, line=best.line, odds=best.odds,
        projection=round(proj.mean, 2),
        proj_low=round(max(0.0, proj.mean - proj.std), 2),
        proj_high=round(proj.mean + proj.std, 2),
        hit_prob=round(hit, 4), fair_prob=round(fair, 4),
        edge=round(edge, 4), ev_per_unit=round(ev, 4),
        confidence=confidence, stake_units=round(stake, 2), grade=grade,
        reasons=reasons, trend=proj.form.trend,
    )
