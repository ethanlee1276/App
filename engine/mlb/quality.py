"""MLB market tiers, volatility ratings and the unified 0–100 grade —
"Scalpy 2.0" (docs/MLB_MODEL.md §9–§10).

Shares the grade bands, stake caps and haircut/threshold scales with the
NFL implementation (engine.quality) — one discipline, two sports — but the
score's WEIGHTS are baseball's own: the pitcher is the center of the MLB
universe and the lineup card is a projection input, so those two
certainties replace the NFL's usage-stability and game-script components.

    edge 40% · pitcher-grade certainty 15% · lineup/role certainty 15% ·
    market movement 10% · environment (park/weather/ump) 10% · matchup 10%
"""

from __future__ import annotations

from ..statmath import clamp
from ..quality import TIER_SHRINK, TIER_MIN_EDGE, letter, STAKE_CAP_U  # noqa: F401 (re-exported)

# §9: beatability tracks modelability. Tier 1 is driven almost entirely by
# the one player graded most deeply (the starter). Home runs are the
# quarantined long-shot family. (Pitcher outs / F5 / SB markets join their
# tiers when the odds feed carries them.)
MLB_MARKET_TIER = {
    "strikeouts": 1,
    "outs": 1,
    "total_bases": 2, "hits": 2,
    "home_runs": 3,
}

# §9's examples, verbatim: outs LOW · 6+ Ks MEDIUM · 2+ TB HIGH · HR EXTREME.
MLB_VOLATILITY = {
    "strikeouts": "MEDIUM",
    "outs": "LOW",
    "total_bases": "HIGH", "hits": "HIGH",
    "home_runs": "EXTREME",
}


def mlb_tier(market: str) -> int:
    return MLB_MARKET_TIER.get(market, 2)


def mlb_tier_shrink(market: str) -> float:
    return TIER_SHRINK[mlb_tier(market)]


# THE FIRST EVIDENCE-DRIVEN LOOSENING (2026-08-10). The near-miss paper
# book — every prop that fell just short of these exact bars, journaled
# nightly at flat stakes and settled against real results — reached its
# written decision threshold: 453-311 over 764 graded, +1.3% ROI, while
# the main record these bars protect sat at 145-162, −14.9%. The band
# the gates refused outperformed the band they approved by sixteen
# points. Per the rule attached to that bucket the day it was built
# ("profitable over 100+ graded → loosen the real gates"), the MLB bars
# come down one notch — MLB ONLY, because the loose book is MLB-only
# evidence; every other sport keeps the shared TIER_MIN_EDGE until it
# has its own bucket to argue from.
#
# Honesty about the margin: +1.3% on 764 flat stakes carries a wide
# confidence interval — the PROVEN fact is "the refused band is not
# burning money", not "it prints". That is exactly why this is one
# notch and not the door: the newly admitted band journals as MAIN and
# so measures itself from tonight, and the near-miss book automatically
# re-anchors below the NEW bars, testing the next band down. If the
# admitted band burns, these numbers go back up with the same receipt.
# Tier 3 (home runs) is untouched — the Long Shots board owns it.
MLB_TIER_MIN_EDGE = {1: 0.021, 2: 0.026, 3: TIER_MIN_EDGE[3]}
MLB_QUALITY_FLOOR = 66.0
MLB_GRADE_BANDS = (("A+", 90.0), ("A", 80.0), ("B+", MLB_QUALITY_FLOOR))


def mlb_letter(quality: float) -> str:
    """MLB's grade bands — B+ starts at the loosened floor, so the grade
    a pick wears and the gate that admits it stay one fact."""
    for name, floor in MLB_GRADE_BANDS:
        if quality >= floor:
            return name
    return "Pass"


def mlb_tier_min_edge(market: str) -> float:
    return MLB_TIER_MIN_EDGE[mlb_tier(market)]


def mlb_volatility(market: str) -> str:
    return MLB_VOLATILITY.get(market, "HIGH")


def _fit(mult: float, side: str) -> float:
    """Does a multiplier agree with the side we're taking? 10 = strongly
    with, 6 = neutral, 3 = it points the other way."""
    over = side == "OVER"
    if abs(mult - 1.0) < 0.03:
        return 6.0
    return 10.0 if (mult > 1.0) == over else 3.0


def mlb_quality_score(*, edge: float, market: str, side: str,
                      pitcher_certainty: float, lineup_certainty: float,
                      env_mult: float, matchup_mult: float,
                      movement_pts: float | None = None) -> tuple[int, list[str]]:
    """The unified §10 grade. Returns ``(score 0–100, component notes)``.

    ``pitcher_certainty`` (0–1): for pitcher props, how well-sampled and
    steady the starter's own log is; for hitter props, whether tonight's
    opposing probable is even known — grade the pitcher wrong and no hitter
    analysis can save you. ``lineup_certainty`` (0–1): confirmed slot = 1.0;
    projected = partial; not in the posted lineup = conditional. Movement
    is 10% here (books copy each other on MLB props, so movement carries a
    bit less signal than NFL steam); neutral 5.5 until snapshots exist.
    """
    tier = mlb_tier(market)
    notes: list[str] = []

    # Edge (40): the tier minimum earns two-thirds credit; 1.5x the minimum
    # earns full credit — same 2026-07-29 re-tune as the NFL scorer, for the
    # same reason: the edge gate and the quality gate must not double-charge
    # for the same caution, and the credibility cap makes "twice the
    # minimum" unreachable in Tier 2.
    edge_pts = clamp(edge / (1.5 * TIER_MIN_EDGE[tier]), 0.0, 1.0) * 40.0

    pitcher_pts = 15.0 * clamp(pitcher_certainty, 0.0, 1.0)
    if pitcher_certainty < 0.6:
        notes.append("Opposing starter not confirmed — the game's central "
                     "input is a projection, not a fact")

    lineup_pts = 15.0 * clamp(lineup_certainty, 0.0, 1.0)
    if lineup_certainty < 0.6:
        notes.append("Conditional until the lineup posts — a hitter prop "
                     "without a confirmed slot is an IF, not a bet")

    move_pts = 5.5 if movement_pts is None else clamp(movement_pts, 0.0, 10.0)

    env_pts = 7.0 if abs(env_mult - 1.0) < 0.01 else _fit(env_mult, side)
    if env_pts <= 3.0:
        notes.append("Park/weather/umpire environment points the other way")

    matchup_pts = _fit(matchup_mult, side) if abs(matchup_mult - 1.0) >= 0.01 else 6.0
    if matchup_pts <= 3.0:
        notes.append("Platoon/arsenal matchup points the other way")

    total = edge_pts + pitcher_pts + lineup_pts + move_pts + env_pts + matchup_pts
    return int(round(clamp(total, 0.0, 100.0))), notes
