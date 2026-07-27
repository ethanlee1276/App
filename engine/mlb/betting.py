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
    Recommendation, _confidence_score, _grade, _kelly_stake, net_edge,
    _trend_alignment, pick_side, temper_edge,
)
from ..calibrate import apply_temperature, correction_for, is_reliable
from ..odds import expected_value
from ..statmath import prob_over, clamp
from .models import MLBProp, HOME_RUNS
from .projection import MLBProjection


def empirical_prob_over(values: list, line: float, fallback: float,
                        min_games: int = 8) -> float:
    """P(stat > line) from how often the player has actually done it.

    Baseball props are low-count discrete stats — a hitter records zero total
    bases in roughly 40% of games — so a normal curve around the mean badly
    overstates a 0.5 line (81% where reality is nearer 58%). That single
    modelling error was inflating edges by 15-20 points across the board.

    The distribution is also right-skewed: a handful of extra-base games pull
    the *mean* well above the median, while prop lines sit near the mean. A
    symmetric model therefore overstates the over badly — on a realistic total
    bases distribution it says 56% where the truth is 30%. Backtesting exposed
    this as the dominant source of error, so the player's own history — which
    encodes the real shape, skew and all — carries most of the weight.

    The parametric estimate still contributes, because it alone carries the
    projection's matchup/park/weather adjustments that raw history cannot see.
    Laplace smoothing keeps a short log off 0%/100%.
    """
    n = len(values)
    if n < min_games:
        return fallback
    hits = sum(1 for v in values if v > line)
    smoothed = (hits + 1.0) / (n + 2.0)
    weight = clamp(n / 25.0, 0.0, 0.85)
    return clamp(weight * smoothed + (1.0 - weight) * fallback, 1e-4, 0.999)


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
    history = [g.value for g in prop.logs] if prop.logs else []
    temp, bias = correction_for("mlb", prop.market)

    def p_over_at(line: float) -> float:
        if prop.market == HOME_RUNS:
            # Home runs are already priced with a discrete (Poisson) model.
            raw = _poisson_over(line, proj.mean)
        else:
            parametric = prob_over(line, proj.mean, proj.std)
            raw = empirical_prob_over(history, line, parametric)
        # Calibrate here, not after the side is chosen: an uncalibrated
        # probability would still decide OVER vs UNDER, so a model known to be
        # over-confident would keep picking the same side and the correction
        # would only ever shave the edge it had already committed to.
        return apply_temperature(raw, temp, bias)

    side, best, hit_raw, fair, edge_raw = pick_side(prop.lines, p_over_at)
    hit, edge, credible = temper_edge(hit_raw, fair, best.book, allow_synthetic_line)
    has_market = allow_synthetic_line or (best.book or "").lower() != "proxy"
    if not has_market:
        # No real price to beat — don't report a number that reads as an edge.
        edge = 0.0
    ev = expected_value(hit, best.odds)
    trend_align = _trend_alignment(side, proj.form.trend)
    confidence = _confidence_score(edge, hit, proj, trend_align)
    # Grade on net edge (vs the real price), not edge-vs-fair — see
    # engine/betting.py._grade. This is what keeps every graded bet
    # sizeable instead of shipping 0.00-unit "recommendations".
    # A market whose own calibration fit ran to the edge of the search
    # range is one we cannot price — the stored temperature is a cap, not
    # a correction. Bet nothing there until the model is fixed.
    calibration_ok = is_reliable("mlb", prop.market)
    grade = (_grade(confidence, net_edge(hit, best.odds), best.odds)
             if credible and calibration_ok else "Pass")
    stake = _kelly_stake(hit, best.odds) if grade != "Pass" else 0.0

    reasons = list(proj.reasons)
    if not calibration_ok:
        reasons.insert(0, "This market's calibration fit hit the edge of its "
                          "search range — the model can't price it reliably, "
                          "so nothing here is bettable until it's fixed")
    if not credible:
        reasons.insert(0, "No credible market edge — line unavailable or price looks off")
    elif side == "UNDER":
        reasons.insert(0, f"Model sides UNDER — projects {proj.mean:.2f} under the {best.line:g} line")

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
        has_market=has_market,
    )
