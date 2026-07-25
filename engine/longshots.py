"""Long shots — NFL anytime touchdowns and MLB home runs.

These two markets behave differently from yardage props: the outcome is a rare
*event*, so the right model is a Poisson rate (expected scores per game) turned
into P(at least one), not a normal distribution around a mean.

The discipline both engines share, and the reason this module exists:

* **Opportunity over outcomes.** A player is rated on the chances he gets — red
  zone / goal line work, plate appearances and contact quality — never on a
  streak of recent scores. Chasing last week's touchdowns is the single most
  common way to lose money in these markets.
* **Priced against the book, in a sane odds window.** A pick only counts when
  the modelled probability beats the book's implied probability, and only
  inside the odds range where the payout justifies the risk (NFL -150..+200,
  MLB +250..+650 per the strategy specs).
* **Concentration limits.** At most a couple of picks per NFL game and one per
  MLB team, so a single game script or lineup can't sink the whole card.
* **No forced picks.** If nothing clears, the honest answer is an empty board.

What the model can and can't see is stated on each pick: where a factor comes
from a proxy rather than a true measurement (e.g. red-zone share inferred from
opportunity share and team implied total, because play-by-play isn't ingested),
the pick says so rather than implying precision we don't have.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .odds import american_to_prob, devig_two_way, expected_value, american_to_decimal
from .statmath import clamp
from .calibrate import apply_temperature, correction_for
from .betting import MARKET_SHRINK, MAX_CREDIBLE_EDGE

# Odds windows from the strategy specs — outside these the payout doesn't
# justify the variance (or the price implies a probability we can't beat).
NFL_TD_ODDS = (-150, 200)
MLB_HR_ODDS = (250, 650)

# League baselines used to convert a team's implied total into expected TDs.
NFL_AVG_TEAM_POINTS = 22.6
NFL_AVG_TEAM_OFF_TDS = 2.4


@dataclass
class LongShot:
    """One long-shot recommendation, with the reasoning that produced it."""
    player: str
    team: str
    opponent: str
    market: str                 # "anytime_td" | "home_runs"
    market_label: str
    book: str
    odds: int
    model_prob: float           # our probability of the event
    implied_prob: float         # book's de-vigged probability
    edge: float
    ev_per_unit: float
    confidence: float           # 0..10
    stake_units: float
    grade: str
    expected_opportunities: float   # red-zone chances (NFL) / plate appearances (MLB)
    primary_reason: str
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    game_date: str = ""
    game_kickoff: str = ""
    live: bool = False

    def to_dict(self) -> dict:
        return {
            "player": self.player, "team": self.team, "opponent": self.opponent,
            "market": self.market, "market_label": self.market_label,
            "book": self.book, "odds": self.odds,
            "model_prob": round(self.model_prob, 4),
            "implied_prob": round(self.implied_prob, 4),
            "edge": round(self.edge, 4), "ev_per_unit": round(self.ev_per_unit, 4),
            "confidence": self.confidence, "stake_units": self.stake_units,
            "grade": self.grade,
            "expected_opportunities": round(self.expected_opportunities, 2),
            "primary_reason": self.primary_reason,
            "reasons": self.reasons, "caveats": self.caveats,
            "matchup": f"{self.team} vs {self.opponent}",
            "game_date": self.game_date, "game_kickoff": self.game_kickoff,
            "live": self.live,
            "headline": f"{self.player} — {self.market_label} ({self.odds:+d})",
        }


# --- shared helpers ---------------------------------------------------------
def prob_at_least_one(rate: float) -> float:
    """P(at least one event) for a Poisson rate — the right shape for a rare
    event, and much more honest than a normal approximation near zero."""
    return 1.0 - math.exp(-max(rate, 0.0))


def in_odds_window(odds: int, window: tuple[int, int]) -> bool:
    lo, hi = window
    return lo <= odds <= hi


def _confidence(edge: float, opportunities: float, opp_target: float,
                data_quality: float = 1.0) -> float:
    """0–10 confidence. Edge drives it; opportunity volume and data quality are
    discounts, so a thin-sample or low-usage player can't grade highly on a
    lucky projection alone.

    Scaled for *tempered* edges: these markets are efficiently priced, so a
    genuine 5% edge is a strong result and earns full marks here.
    """
    edge_pts = clamp(edge / 0.05, 0.0, 1.0) * 6.5
    opp_pts = clamp(opportunities / opp_target, 0.0, 1.0) * 2.5
    return round(clamp((edge_pts + opp_pts) * clamp(data_quality, 0.7, 1.0), 0.0, 10.0), 1)


def _grade(confidence: float, edge: float) -> str:
    if confidence >= 7.5 and edge >= 0.05:
        return "Strong Play"
    if confidence >= 6.0 and edge >= 0.03:
        return "Play"
    if confidence >= 4.5 and edge >= 0.015:
        return "Lean"
    return "Pass"


def _stake(model_prob: float, odds: int, fraction: float = 0.2) -> float:
    """Fractional Kelly, capped hard. Long shots are high-variance, so the
    Kelly fraction is smaller than the yardage-prop model uses."""
    b = american_to_decimal(odds) - 1.0
    if b <= 0:
        return 0.0
    kelly = (b * model_prob - (1.0 - model_prob)) / b
    return round(clamp(kelly * fraction, 0.0, 0.03) * 20, 2)


def _price(model_prob: float, over_odds: int, under_odds: int | None):
    """De-vig the book's price. With only one side quoted (common for TD/HR
    markets) we strip an assumed hold instead, which is less precise — the
    caller flags that as a caveat."""
    if under_odds is not None:
        implied, _ = devig_two_way(over_odds, under_odds)
        exact = True
    else:
        raw = american_to_prob(over_odds)
        implied = raw / 1.06          # assume ~6% hold on a one-sided quote
        exact = False
    return implied, exact


def build_pick(player: str, team: str, opponent: str, market: str, label: str,
               book: str, odds: int, model_prob: float, under_odds: int | None,
               opportunities: float, opp_target: float, primary_reason: str,
               reasons: list[str], caveats: list[str], sport: str,
               data_quality: float = 1.0) -> LongShot | None:
    """Price a modelled probability against the book and grade it."""
    _t, _b = correction_for(sport, market)
    raw_prob = clamp(apply_temperature(model_prob, _t, _b), 1e-4, 0.999)
    implied, exact = _price(raw_prob, odds, under_odds)
    if not exact:
        caveats = caveats + ["Only one side quoted — the book's true price is estimated"]

    # Same discipline as the yardage-prop model: shrink toward the market while
    # the model is still uncalibrated, and treat an implausibly large
    # disagreement as a data or modelling error rather than found money.
    # Touchdown and home-run markets are heavily bet and efficiently priced —
    # a genuine 15% edge in them essentially does not exist.
    model_prob = clamp(implied + MARKET_SHRINK * (raw_prob - implied), 1e-4, 0.999)
    edge = model_prob - implied
    credible = abs(raw_prob - implied) <= MAX_CREDIBLE_EDGE
    if not credible:
        caveats = caveats + [
            f"Model disagrees with the market by {abs(raw_prob - implied):.0%} — "
            f"too large to trust, treated as a pricing/data error"]

    confidence = _confidence(edge, opportunities, opp_target, data_quality)
    grade = _grade(confidence, edge) if credible else "Pass"
    return LongShot(
        player=player, team=team, opponent=opponent, market=market,
        market_label=label, book=book, odds=odds,
        model_prob=model_prob, implied_prob=implied, edge=edge,
        ev_per_unit=expected_value(model_prob, odds),
        confidence=confidence, stake_units=_stake(model_prob, odds) if grade != "Pass" else 0.0,
        grade=grade, expected_opportunities=opportunities,
        primary_reason=primary_reason, reasons=reasons, caveats=caveats,
    )


def select(picks: list[LongShot], per_key_cap: int, key, limit: int,
           require_edge: bool = True) -> list[LongShot]:
    """Rank by edge and apply the spec's concentration limits.

    Sorting by edge (not by odds) is deliberate: the biggest payout is almost
    never the best bet, and ranking by price is how long-shot cards go broke.
    """
    ranked = sorted(picks, key=lambda p: (p.edge, p.confidence), reverse=True)
    out: list[LongShot] = []
    seen: dict = {}
    for p in ranked:
        if require_edge and (p.edge <= 0 or p.grade == "Pass"):
            continue
        k = key(p)
        if seen.get(k, 0) >= per_key_cap:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(p)
        if len(out) >= limit:
            break
    return out
