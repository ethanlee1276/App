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
    "total_bases": 2, "hits": 2,
    "home_runs": 3,
}

# §9's examples, verbatim: outs LOW · 6+ Ks MEDIUM · 2+ TB HIGH · HR EXTREME.
MLB_VOLATILITY = {
    "strikeouts": "MEDIUM",
    "total_bases": "HIGH", "hits": "HIGH",
    "home_runs": "EXTREME",
}


def mlb_tier(market: str) -> int:
    return MLB_MARKET_TIER.get(market, 2)


def mlb_tier_shrink(market: str) -> float:
    return TIER_SHRINK[mlb_tier(market)]


def mlb_tier_min_edge(market: str) -> float:
    return TIER_MIN_EDGE[mlb_tier(market)]


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

    # Edge (40): tier minimum earns half credit, twice the minimum full.
    edge_pts = clamp(edge / (2.0 * TIER_MIN_EDGE[tier]), 0.0, 1.0) * 40.0

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
