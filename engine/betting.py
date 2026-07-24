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
from .odds import best_over_line, best_under_line, devig_two_way, expected_value
from .statmath import prob_over, prob_over_discrete, clamp

# --- calibration guards -----------------------------------------------------
# The prop model is not yet calibrated to real outcomes, and live feeds
# sometimes attach a mismatched/one-sided line. Two guards keep the output
# honest:
#   1. shrink the model's probability toward the market price, so a raw edge is
#      damped to a realistic size while the model is still uncalibrated, and
#   2. treat a raw edge beyond MAX_CREDIBLE_EDGE (or a placeholder "proxy" line)
#      as a data error, not alpha — in an efficient prop market a 20%+ edge is
#      always bad data. Those are graded Pass instead of shown as strong plays.
MARKET_SHRINK = 0.5
MAX_CREDIBLE_EDGE = 0.10


def temper_edge(hit_raw: float, fair: float, book: str) -> tuple[float, float, bool]:
    """Shrink the model probability toward the market and judge credibility.

    Returns ``(hit, edge, credible)`` where ``hit`` is the tempered win
    probability, ``edge = hit - fair``, and ``credible`` is False when the line
    is a placeholder or the raw disagreement is implausibly large."""
    hit = clamp(fair + MARKET_SHRINK * (hit_raw - fair), 1e-6, 1.0 - 1e-6)
    credible = (book or "").lower() != "proxy" and abs(hit_raw - fair) <= MAX_CREDIBLE_EDGE
    return hit, hit - fair, credible


@dataclass
class Recommendation:
    player: str
    team: str
    opponent: str
    market: str
    side: str                 # "OVER" or "UNDER" — whichever side has the edge
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


def _confidence_score(edge: float, hit_prob: float, proj: Projection,
                      trend_align: float = 0.0) -> float:
    """Blend edge, absolute hit probability, sample size and variance into a
    0–10 score. Edge is the main driver; the rest are quality discounts.

    ``trend_align`` nudges the score for betting with (or against) the player's
    recent-form trend — see ``_trend_alignment``."""
    # Edges are tempered toward the market (see temper_edge), so the credible
    # range is a few percent — a 4.5% tempered edge earns full weight here.
    edge_component = clamp(edge / 0.045, 0.0, 1.0) * 6.0          # up to 6 pts
    prob_component = clamp((hit_prob - 0.5) / 0.35, 0.0, 1.0) * 2.5  # up to 2.5

    # Data-quality discount: thin samples and high relative variance cost points.
    games = proj.form.sample_games
    sample_q = clamp(games / 8.0, 0.3, 1.0)
    rel_var = proj.std / proj.mean if proj.mean > 0 else 1.0
    var_q = clamp(1.0 - (rel_var - 0.30), 0.4, 1.0)
    quality = 1.5 * sample_q * var_q                              # up to 1.5

    total = edge_component + prob_component + quality + trend_align
    return round(clamp(total, 0.0, 10.0), 1)


def _trend_alignment(side: str, trend: str) -> float:
    """Confidence nudge for betting with — or against — the player's trend.

    Backing an OVER on a cooling player (or an UNDER on a heating one) fights
    the direction of recent form and takes a real haircut; riding the trend
    earns a small bonus. This is the piece that makes the model stop
    recommending a name that has stopped producing."""
    if trend == "flat":
        return 0.0
    with_trend = (side == "OVER" and trend == "up") or (side == "UNDER" and trend == "down")
    against_trend = (side == "OVER" and trend == "down") or (side == "UNDER" and trend == "up")
    if with_trend:
        return 0.5
    if against_trend:
        return -1.2
    return 0.0


def pick_side(lines, p_over_at):
    """Shop both sides and return the one with the larger edge.

    ``p_over_at(line) -> P(stat > line)`` is supplied by the caller so each
    sport prices with its own distribution (normal, discrete, Poisson…).
    Returns ``(side, best_line, win_prob, fair_prob, edge)`` where ``win_prob``
    is the probability the chosen bet cashes."""
    over = best_over_line(lines)
    under = best_under_line(lines)

    p_over_at_over = clamp(p_over_at(over.line), 1e-6, 1.0 - 1e-6)
    over_edge = p_over_at_over - over.fair_prob

    p_over_at_under = clamp(p_over_at(under.line), 1e-6, 1.0 - 1e-6)
    under_win = 1.0 - p_over_at_under
    under_edge = under_win - under.fair_prob

    if over_edge >= under_edge:
        return "OVER", over, p_over_at_over, over.fair_prob, over_edge
    return "UNDER", under, under_win, under.fair_prob, under_edge


def _grade(confidence: float, edge: float) -> str:
    # Thresholds sized for tempered edges (a few percent is a genuine play).
    if confidence >= 8.0 and edge >= 0.04:
        return "Strong Play"
    if confidence >= 6.5 and edge >= 0.025:
        return "Play"
    if confidence >= 4.5 and edge >= 0.012:
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
    def p_over_at(line: float) -> float:
        if prop.market == RECEPTIONS:
            return prob_over_discrete(line, proj.mean, proj.std)
        return prob_over(line, proj.mean, proj.std)

    side, best, hit_raw, fair, edge_raw = pick_side(prop.lines, p_over_at)
    hit, edge, credible = temper_edge(hit_raw, fair, best.book)
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
        player=prop.player,
        team=prop.team,
        opponent=prop.opponent,
        market=prop.market,
        side=side,
        book=best.book,
        line=best.line,
        odds=best.odds,
        projection=round(proj.mean, 1),
        proj_low=round(proj.mean - proj.std, 1),
        proj_high=round(proj.mean + proj.std, 1),
        hit_prob=round(hit, 4),
        fair_prob=round(fair, 4),
        edge=round(edge, 4),
        ev_per_unit=round(ev, 4),
        confidence=confidence,
        stake_units=round(stake, 2),
        grade=grade,
        reasons=reasons,
        trend=proj.form.trend,
    )
