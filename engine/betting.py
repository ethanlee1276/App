"""Betting model.

Turns a projection into a bettable recommendation: it shops for the best line,
computes the model's hit probability, measures the edge against the book's
de-vigged price, sizes a stake with a fractional-Kelly rule, and rolls
everything into a 0–10 confidence score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Prop, RECEPTIONS
from .projection import Projection
from .odds import best_over_line, devig_two_way, expected_value
from .statmath import prob_over, prob_over_discrete, clamp


@dataclass
class Recommendation:
    player: str
    team: str
    opponent: str
    market: str
    side: str                 # "OVER" (this MVP surfaces overs)
    book: str
    line: float
    odds: int
    projection: float
    proj_low: float
    proj_high: float
    hit_prob: float
    fair_prob: float          # book's de-vigged implied probability
    edge: float               # hit_prob - fair_prob
    ev_per_unit: float
    confidence: float         # 0..10
    stake_units: float
    grade: str                # "Strong Play" / "Play" / "Lean" / "Pass"
    reasons: list[str] = field(default_factory=list)
    trend: str = "flat"


def _confidence_score(edge: float, hit_prob: float, proj: Projection) -> float:
    """Blend edge, absolute hit probability, sample size and variance into a
    0–10 score. Edge is the main driver; the rest are quality discounts."""
    edge_component = clamp(edge / 0.12, 0.0, 1.0) * 6.0          # up to 6 pts
    prob_component = clamp((hit_prob - 0.5) / 0.35, 0.0, 1.0) * 2.5  # up to 2.5

    # Data-quality discount: thin samples and high relative variance cost points.
    games = proj.form.sample_games
    sample_q = clamp(games / 8.0, 0.3, 1.0)
    rel_var = proj.std / proj.mean if proj.mean > 0 else 1.0
    var_q = clamp(1.0 - (rel_var - 0.30), 0.4, 1.0)
    quality = 1.5 * sample_q * var_q                              # up to 1.5

    return round(clamp(edge_component + prob_component + quality, 0.0, 10.0), 1)


def _grade(confidence: float, edge: float) -> str:
    if confidence >= 8.5 and edge >= 0.06:
        return "Strong Play"
    if confidence >= 7.0 and edge >= 0.035:
        return "Play"
    if confidence >= 5.5 and edge >= 0.02:
        return "Lean"
    return "Pass"


def _kelly_stake(model_prob: float, odds: int, fraction: float = 0.25) -> float:
    """Fractional Kelly stake in units, capped for safety."""
    from .odds import american_to_decimal
    b = american_to_decimal(odds) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - model_prob
    kelly = (b * model_prob - q) / b
    return round(clamp(kelly * fraction, 0.0, 0.05) * 100, 2) / 100 * 20  # -> ~0..1 unit


def evaluate_prop(prop: Prop, proj: Projection) -> Recommendation:
    best = best_over_line(prop.lines)

    if prop.market == RECEPTIONS:
        hit = prob_over_discrete(best.line, proj.mean, proj.std)
    else:
        hit = prob_over(best.line, proj.mean, proj.std)

    edge = hit - best.fair_prob
    ev = expected_value(hit, best.odds)
    confidence = _confidence_score(edge, hit, proj)
    grade = _grade(confidence, edge)
    stake = _kelly_stake(hit, best.odds) if grade != "Pass" else 0.0

    return Recommendation(
        player=prop.player,
        team=prop.team,
        opponent=prop.opponent,
        market=prop.market,
        side="OVER",
        book=best.book,
        line=best.line,
        odds=best.odds,
        projection=round(proj.mean, 1),
        proj_low=round(proj.mean - proj.std, 1),
        proj_high=round(proj.mean + proj.std, 1),
        hit_prob=round(hit, 4),
        fair_prob=round(best.fair_prob, 4),
        edge=round(edge, 4),
        ev_per_unit=round(ev, 4),
        confidence=confidence,
        stake_units=round(stake, 2),
        grade=grade,
        reasons=proj.reasons,
        trend=proj.form.trend,
    )
