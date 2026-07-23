"""Game-level bets — moneyline.

Everything so far prices a single *player*. This module prices the *game*: it
turns a model win probability into a moneyline recommendation, measured against
the book's de-vigged price with the same edge / confidence / fractional-Kelly
discipline as the player model.

The win probability itself comes from a light team-strength model:

* **NFL** — each team carries a rating in *net points per game vs league
  average* (0 = average). Projected margin = home_rating − away_rating + home
  field, and P(home win) = Φ(margin / σ) with σ ≈ 13.5, the historical
  standard deviation of an NFL game's final margin.
* **MLB** — each team carries a rating in *expected run differential per game*.
  The projected run margin adds home field and a starting-pitcher edge from the
  two starters' expected ERA, then P(home win) = Φ(margin / σ) with σ ≈ 4.0.

Both models are deliberately independent of the book's number, so an edge shows
up only when our team strength disagrees with the market — never manufactured
by simply inverting the line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .statmath import normal_cdf, clamp
from .odds import devig_two_way, expected_value
from .betting import _grade, _kelly_stake

# NFL: SD of a game's final margin. MLB: SD of the run margin used for win prob.
NFL_MARGIN_SD = 13.5
MLB_MARGIN_SD = 4.0
NFL_HOME_FIELD = 1.6          # points
MLB_HOME_FIELD = 0.18         # runs
LEAGUE_AVG_XERA = 4.10


def nfl_win_prob(home_rating: float, away_rating: float) -> float:
    """P(home win) from net-point ratings (points/game vs league average)."""
    margin = (home_rating - away_rating) + NFL_HOME_FIELD
    return clamp(normal_cdf(margin / NFL_MARGIN_SD), 0.01, 0.99)


def mlb_win_prob(home_rating: float, away_rating: float,
                 home_xera: float = LEAGUE_AVG_XERA,
                 away_xera: float = LEAGUE_AVG_XERA) -> float:
    """P(home win) from run-diff ratings plus a starting-pitcher edge.

    A starter better than league average (lower xERA) suppresses the opponent's
    runs, so the *away* starter's quality helps the away side and vice versa.
    """
    home_sp = (LEAGUE_AVG_XERA - home_xera)     # +ve = better than average
    away_sp = (LEAGUE_AVG_XERA - away_xera)
    sp_edge = (home_sp - away_sp) * 0.25        # runs, dampened
    margin = (home_rating - away_rating) + MLB_HOME_FIELD + sp_edge
    return clamp(normal_cdf(margin / MLB_MARGIN_SD), 0.03, 0.97)


@dataclass
class MoneylineRec:
    home: str
    away: str
    pick: str                 # team abbreviation we back
    pick_is_home: bool
    win_prob: float           # model probability the pick wins
    fair_prob: float          # book's de-vigged probability for the pick
    edge: float               # win_prob - fair_prob
    odds: int                 # American odds for the pick
    ev_per_unit: float
    confidence: float         # 0..10
    stake_units: float
    grade: str
    reasons: list[str] = field(default_factory=list)


def _ml_confidence(edge: float, win_prob: float) -> float:
    """0–10 confidence for a moneyline. Edge is the main driver; a clearer
    favorite adds a little certainty. Tuned so a ~4% edge grades a Play."""
    edge_component = clamp(edge / 0.07, 0.0, 1.0) * 6.5
    prob_component = clamp((win_prob - 0.5) / 0.35, 0.0, 1.0) * 2.0
    return round(clamp(edge_component + prob_component, 0.0, 10.0), 1)


def price_moneyline(home: str, away: str, win_prob_home: float,
                    home_ml: int, away_ml: int,
                    context: list[str] | None = None) -> MoneylineRec:
    """Price both sides of a moneyline and back the one with the edge."""
    fair_home, fair_away = devig_two_way(home_ml, away_ml)
    wp_home = clamp(win_prob_home, 0.01, 0.99)
    wp_away = 1.0 - wp_home

    home_edge = wp_home - fair_home
    away_edge = wp_away - fair_away

    if home_edge >= away_edge:
        pick, is_home, wp, ml, fair, edge = home, True, wp_home, home_ml, fair_home, home_edge
    else:
        pick, is_home, wp, ml, fair, edge = away, False, wp_away, away_ml, fair_away, away_edge

    ev = expected_value(wp, ml)
    confidence = _ml_confidence(edge, wp)
    grade = _grade(confidence, edge)
    stake = _kelly_stake(wp, ml) if grade != "Pass" else 0.0

    reasons = list(context or [])
    reasons.insert(0, f"Model win probability {wp:.0%} vs book's {fair:.0%} "
                      f"— a {edge:+.1%} edge on {pick}")

    return MoneylineRec(
        home=home, away=away, pick=pick, pick_is_home=is_home,
        win_prob=round(wp, 4), fair_prob=round(fair, 4), edge=round(edge, 4),
        odds=ml, ev_per_unit=round(ev, 4), confidence=confidence,
        stake_units=round(stake, 2), grade=grade, reasons=reasons,
    )


def moneyline_to_dict(rec: MoneylineRec) -> dict:
    """Serialize a moneyline rec for the pipeline JSON / web UI."""
    return {
        "bet_type": "moneyline",
        "market": "moneyline",
        "market_label": "Moneyline",
        "home": rec.home,
        "away": rec.away,
        "pick": rec.pick,
        "pick_is_home": rec.pick_is_home,
        "matchup": f"{rec.away} @ {rec.home}",
        "win_prob": rec.win_prob,
        "fair_prob": rec.fair_prob,
        "edge": rec.edge,
        "odds": rec.odds,
        "ev_per_unit": rec.ev_per_unit,
        "confidence": rec.confidence,
        "stake_units": rec.stake_units,
        "grade": rec.grade,
        "headline": f"{rec.pick} Moneyline ({rec.odds:+d})",
        "reasons": rec.reasons,
    }
