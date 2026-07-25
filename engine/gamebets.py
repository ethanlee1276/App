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
from .odds import (american_to_decimal, american_to_prob, devig_two_way,
                   expected_value)
from .betting import _grade, _kelly_stake

# NFL: SD of a game's final margin. MLB: SD of the run margin used for win prob.
NFL_MARGIN_SD = 13.5
MLB_MARGIN_SD = 4.0
NFL_HOME_FIELD = 1.6          # points
MLB_HOME_FIELD = 0.18         # runs
LEAGUE_AVG_XERA = 4.10

# SD of a game's combined total (points/runs) around its projection.
NFL_TOTAL_SD = 13.5
MLB_TOTAL_SD = 4.5
# A single team's scoring SD is tighter than the game total's (≈ total / √2).
TEAM_TOTAL_SD = {"nfl": 9.5, "mlb": 3.2}
# League-average scoring per team per game — the fixed baseline that offense /
# defense ratings are expressed against, so the totals projection stays
# consistent with how teamrates.py computes those ratings.
SCORING_BASELINE = {"nfl": 22.6, "mlb": 4.5}
MARGIN_SD = {"nfl": NFL_MARGIN_SD, "mlb": MLB_MARGIN_SD}
TOTAL_SD = {"nfl": NFL_TOTAL_SD, "mlb": MLB_TOTAL_SD}
HOME_FIELD = {"nfl": NFL_HOME_FIELD, "mlb": MLB_HOME_FIELD}


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


# Sharp-anchor thresholds: bet only when the soft price beats the sharp
# book's de-vigged fair value by at least MIN, and treat gaps beyond MAX as
# broken prices (in-play or suspended market) rather than edges — the same
# too-good-to-be-true guard the backtest needed.
SHARP_MIN_EV = 0.02
SHARP_MAX_EV = 0.15


def price_moneyline_sharp(home: str, away: str,
                          sharp_home: int, sharp_away: int,
                          home_ml: int, away_ml: int,
                          win_prob_home: float | None = None,
                          context: list[str] | None = None) -> MoneylineRec | None:
    """Price a moneyline from price DISAGREEMENT, not model opinion.

    The sharp pair de-vigs to fair probabilities; a soft price paying more
    than fair is +EV regardless of what our model thinks. Returns ``None``
    when no side clears ``SHARP_MIN_EV`` or the gap smells broken — the
    caller falls back to an informational (never recommended) card."""
    fair_home, fair_away = devig_two_way(sharp_home, sharp_away)
    best = None
    for pick, is_home, fair, ml in ((home, True, fair_home, home_ml),
                                    (away, False, fair_away, away_ml)):
        ev = fair * american_to_decimal(ml) - 1.0
        if SHARP_MIN_EV <= ev <= SHARP_MAX_EV and (best is None or ev > best[4]):
            best = (pick, is_home, fair, ml, ev)
    if best is None:
        return None
    pick, is_home, fair, ml, ev = best
    soft_implied = american_to_prob(ml)
    edge = fair - soft_implied            # probability points of value
    confidence = _ml_confidence(edge, fair)
    grade = ("Strong Play" if ev >= 0.06 else
             "Play" if ev >= 0.035 else "Lean")
    stake = _kelly_stake(fair, ml)

    reasons = [f"Sharp anchor: this price implies {soft_implied:.0%} but the "
               f"sharp book prices {pick} at {fair:.0%} fair — {ev:+.1%} EV "
               f"on the price alone"]
    if win_prob_home is not None:
        wp_pick = win_prob_home if is_home else 1.0 - win_prob_home
        reasons.append(f"Model context: rates {pick} at {wp_pick:.0%} to win")
    reasons += list(context or [])

    return MoneylineRec(
        home=home, away=away, pick=pick, pick_is_home=is_home,
        win_prob=round(fair, 4), fair_prob=round(soft_implied, 4),
        edge=round(edge, 4), odds=ml,
        ev_per_unit=round(ev, 4), confidence=confidence,
        stake_units=round(stake, 2), grade=grade, reasons=reasons,
    )


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
        "team": rec.pick,                 # for the team badge in the UI
        "pick": rec.pick,
        "pick_is_home": rec.pick_is_home,
        "pick_label": f"{rec.pick} ML",
        "side": "",
        "line": 0.0,
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


# --- totals & spreads ------------------------------------------------------
def project_team_points(sport: str, off: float, opp_def: float) -> float:
    """Projected points/runs for one team: its offense vs the opponent's defense."""
    return SCORING_BASELINE.get(sport, 0.0) + off + opp_def


def project_total(sport: str, home_off: float, home_def: float,
                  away_off: float, away_def: float) -> float:
    """Projected combined score: each side's offense meets the other's defense."""
    base = SCORING_BASELINE.get(sport, 0.0)
    # home pts = base + home_off + away_def ; away pts = base + away_off + home_def
    return 2 * base + home_off + away_off + home_def + away_def


def game_margin(sport: str, home_rating: float, away_rating: float) -> float:
    """Projected home scoring margin (points/runs), including home field."""
    return (home_rating - away_rating) + HOME_FIELD.get(sport, 0.0)


def _game_bet(bet_type, market_label, home, away, win, fair, edge, odds,
              pick_label, reasons, team="", side="", line=0.0, headline=""):
    ev = expected_value(win, odds)
    confidence = _ml_confidence(edge, win)
    grade = _grade(confidence, edge)
    stake = _kelly_stake(win, odds) if grade != "Pass" else 0.0
    return {
        "bet_type": bet_type,
        "market": bet_type,
        "market_label": market_label,
        "home": home,
        "away": away,
        "team": team,
        "side": side,
        "line": line,
        "pick_label": pick_label,
        "matchup": f"{away} @ {home}",
        "win_prob": round(win, 4),
        "fair_prob": round(fair, 4),
        "edge": round(edge, 4),
        "odds": odds,
        "ev_per_unit": round(ev, 4),
        "confidence": confidence,
        "stake_units": round(stake, 2),
        "grade": grade,
        "headline": headline or pick_label,
        "reasons": reasons,
    }


def price_total(sport: str, home: str, away: str, proj_total: float,
                market_total: float, over_odds: int = -110, under_odds: int = -110,
                units: str = "points", context: list[str] | None = None) -> dict:
    """Price the game total (over/under) from the projected combined score."""
    fair_over, fair_under = devig_two_way(over_odds, under_odds)
    sd = TOTAL_SD.get(sport, 10.0)
    p_over = clamp(normal_cdf((proj_total - market_total) / sd), 0.02, 0.98)
    over_edge = p_over - fair_over
    under_edge = (1.0 - p_over) - fair_under

    if over_edge >= under_edge:
        side, win, odds, fair, edge = "Over", p_over, over_odds, fair_over, over_edge
    else:
        side, win, odds, fair, edge = "Under", 1.0 - p_over, under_odds, fair_under, under_edge

    reasons = list(context or [])
    reasons.insert(0, f"Model projects {proj_total:.1f} {units} vs the {market_total:g} "
                      f"total — {side} ({edge:+.1%} edge)")
    return _game_bet("total", "Total", home, away, win, fair, edge, odds,
                     pick_label=f"{side} {market_total:g}", side=side, line=market_total,
                     reasons=reasons, headline=f"{side} {market_total:g} {units}")


def price_team_total(sport: str, team: str, home: str, away: str,
                     proj_points: float, line: float,
                     over_odds: int = -110, under_odds: int = -110,
                     units: str = "points", context: list[str] | None = None) -> dict:
    """Price a single team's total (over/under) from its projected scoring."""
    fair_over, fair_under = devig_two_way(over_odds, under_odds)
    sd = TEAM_TOTAL_SD.get(sport, 9.5)
    p_over = clamp(normal_cdf((proj_points - line) / sd), 0.02, 0.98)
    over_edge = p_over - fair_over
    under_edge = (1.0 - p_over) - fair_under

    if over_edge >= under_edge:
        side, win, odds, fair, edge = "Over", p_over, over_odds, fair_over, over_edge
    else:
        side, win, odds, fair, edge = "Under", 1.0 - p_over, under_odds, fair_under, under_edge

    reasons = list(context or [])
    reasons.insert(0, f"Model projects {team} for {proj_points:.1f} {units} vs the "
                      f"{line:g} team total — {side} ({edge:+.1%} edge)")
    return _game_bet("team_total", "Team total", home, away, win, fair, edge, odds,
                     pick_label=f"{team} {side} {line:g}", team=team, side=side, line=line,
                     reasons=reasons, headline=f"{team} team {side} {line:g}")


def price_spread(sport: str, home: str, away: str, proj_margin: float,
                 home_spread: float, home_odds: int = -110, away_odds: int = -110,
                 context: list[str] | None = None) -> dict:
    """Price the spread (NFL points) / run line (MLB) from the projected margin.

    ``home_spread`` is the home team's number (negative = home favored). Home
    covers when the actual margin beats it, i.e. margin + home_spread > 0.
    """
    fair_home, fair_away = devig_two_way(home_odds, away_odds)
    sd = MARGIN_SD.get(sport, 13.5)
    p_home = clamp(normal_cdf((proj_margin + home_spread) / sd), 0.02, 0.98)
    home_edge = p_home - fair_home
    away_edge = (1.0 - p_home) - fair_away

    if home_edge >= away_edge:
        team, spread, win, odds, fair, edge = home, home_spread, p_home, home_odds, fair_home, home_edge
    else:
        team, spread, win, odds, fair, edge = away, -home_spread, 1.0 - p_home, away_odds, fair_away, away_edge

    reasons = list(context or [])
    reasons.insert(0, f"Model margin {proj_margin:+.1f} vs the {home} {home_spread:+g} "
                      f"line — {team} {spread:+g} ({edge:+.1%} edge)")
    return _game_bet("spread", "Spread", home, away, win, fair, edge, odds,
                     pick_label=f"{team} {spread:+g}", team=team, line=spread,
                     reasons=reasons, headline=f"{team} {spread:+g}")
