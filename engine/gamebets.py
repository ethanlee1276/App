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
from .betting import _grade, _kelly_stake, temper_edge, MAX_CREDIBLE_EDGE

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


def _sd(table: dict, sport: str, what: str) -> float:
    """This sport's variance, or a refusal — never another sport's.

    Every one of these tables is a `.get(sport, default)` away from pricing
    college football with the NFL's 13.5-point margin and no home field at
    all, and the failure is silent: you get a confident number with the
    wrong physics behind it. CFB DOES register its own (engine.cfb.ratings
    calls install() at import and again after each fit), so today every real
    build is correct — but "correct as long as somebody imported the right
    module first" is not a property, it is a coincidence waiting to lapse.

    Same fault as the moneyline backtest that fell back to `nfl_win_prob`
    for any sport it did not know. Refusing by name is the whole fix.
    """
    try:
        return table[sport]
    except KeyError:
        raise ValueError(
            f"no {what} registered for {sport!r} — pricing it against another "
            f"league's variance would produce a confident wrong number. "
            f"Register it (see engine.cfb.ratings.install) before pricing."
        ) from None


def nfl_win_prob(home_rating: float, away_rating: float) -> float:
    """P(home win) from net-point ratings (points/game vs league average)."""
    margin = (home_rating - away_rating) + NFL_HOME_FIELD
    return clamp(normal_cdf(margin / NFL_MARGIN_SD), 0.01, 0.99)


def cfb_win_prob(home_rating: float, away_rating: float) -> float:
    """P(home win) for college football, off ITS OWN registered numbers.

    Deliberately not written like `nfl_win_prob`. That one closes over
    two module constants; college football's home field and margin
    spread are MEASURED and re-installed by `engine.cfb.ratings.install`
    after every fit, so reading the live tables through `_sd` is what
    keeps this curve and the board's spread pricing describing the same
    sport. It also means the curve refuses by name rather than quietly
    pricing college through the NFL's 13.5-point margin — the exact
    fault `_sd` exists for, and the one `gamecal` refused to work around
    by leaving CFB out of its curve table entirely.

    The clamp is wider than the NFL's because college is: a 40-point
    September mismatch is an ordinary Saturday, and pinning it at 99%
    would price a certainty the sport does produce.
    """
    margin = ((home_rating - away_rating)
              + _sd(HOME_FIELD, "cfb", "home-field edge"))
    return clamp(normal_cdf(margin / _sd(MARGIN_SD, "cfb", "margin spread")),
                 0.005, 0.995)


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


#: Post-haircut edge that saturates the confidence scale. It is half of the
#: 0.07 this used before, and the halving is not a loosening — edges reaching
#: this function are now shrunk 50% toward the market, so 0.035 here is the
#: same REAL model-vs-market disagreement 0.07 used to be. Leaving it at 0.07
#: would have quietly doubled the bar rather than kept it.
CONFIDENCE_SATURATES_AT = 0.035


def _ml_confidence(edge: float, win_prob: float) -> float:
    """0–10 confidence for a game bet, from the TEMPERED edge.

    Worth being honest about what this is: a hand-drawn curve, never fitted
    to outcomes. Combined with the credibility ceiling it leaves a narrow
    qualifying band — a raw disagreement of roughly 7% to 10%, which is 2.4
    to 3.5 points on an NFL total. Betting only in the strip just below
    "this is a rating error" is an uncomfortable place to live, and it is
    the honest read of a layer that has not yet been graded against results.
    Until gamebacktest.py has run these markets over real closing lines,
    treat a graded game bet as journaled, not earned.
    """
    edge_component = clamp(edge / CONFIDENCE_SATURATES_AT, 0.0, 1.0) * 6.5
    prob_component = clamp((win_prob - 0.5) / 0.35, 0.0, 1.0) * 2.0
    return round(clamp(edge_component + prob_component, 0.0, 10.0), 1)


# Sharp-anchor thresholds: bet only when the soft price beats the sharp
# book's de-vigged fair value by at least MIN, and treat gaps beyond MAX as
# broken prices (in-play or suspended market) rather than edges — the same
# too-good-to-be-true guard the backtest needed.
#
# Between SUSPECT and MAX the number is *plausible but not believable*: a
# 7%+ EV gap on a major-league market means the sharp book repriced on
# news (a scratch, an injury) and the soft quote in our snapshot hadn't
# caught up yet — by the time anyone reads the card, that price is gone or
# the news explains it. Betting into it is adverse selection, so the card
# renders with its full story but grades Pass and stakes zero: verify the
# price still stands before a dollar moves.
SHARP_MIN_EV = 0.02
SHARP_SUSPECT_EV = 0.07
SHARP_MAX_EV = 0.15

_SUSPECT_NOTE = ("Gap too large to trust ({ev:+.1%} EV): a disagreement this "
                 "big between books usually means the sharp side repriced on "
                 "news (scratch, injury, weather) and this quote is stale — "
                 "not free money. Shown for transparency, graded Pass; verify "
                 "the live price before betting anything")


def sharp_anchor_two_way(sharp_a: int, sharp_b: int,
                         soft_a: int, soft_b: int):
    """Which side of a two-way market, if either, is +EV vs the sharp de-vig?

    Returns ``(index, fair_prob, ev)`` — index 0 = first side — or ``None``
    when no side clears ``SHARP_MIN_EV`` or the gap exceeds the broken-price
    cap."""
    fair_a, fair_b = devig_two_way(sharp_a, sharp_b)
    best = None
    for i, (fair, soft) in enumerate(((fair_a, soft_a), (fair_b, soft_b))):
        ev = fair * american_to_decimal(soft) - 1.0
        if SHARP_MIN_EV <= ev <= SHARP_MAX_EV and (best is None or ev > best[2]):
            best = (i, fair, ev)
    return best


def _sharpify(card: dict, fair: float, soft_odds: int, ev: float,
              pick_desc: str) -> dict:
    """Rewrite a game-bet card so its numbers come from the sharp anchor:
    probability = sharp fair, edge = fair minus the soft implied, grade by EV."""
    implied = american_to_prob(soft_odds)
    card["win_prob"] = round(fair, 4)
    card["fair_prob"] = round(implied, 4)
    card["edge"] = round(fair - implied, 4)
    card["ev_per_unit"] = round(ev, 4)
    if ev > SHARP_SUSPECT_EV:
        card["grade"] = "Pass"
        card["stake_units"] = 0.0
        card["suspect_gap"] = True
        card["reasons"].insert(0, _SUSPECT_NOTE.format(ev=ev))
        return card
    card["grade"] = ("Strong Play" if ev >= 0.06 else
                     "Play" if ev >= 0.035 else "Lean")
    card["stake_units"] = round(_kelly_stake(fair, soft_odds), 2)
    card["reasons"].insert(0, f"Sharp anchor: {pick_desc} implies "
                              f"{implied:.0%} but the sharp book's fair is "
                              f"{fair:.0%} — {ev:+.1%} EV on the price alone")
    return card


def price_total_sharp(home: str, away: str, line: float,
                      over_odds: int, under_odds: int,
                      sharp_over: int, sharp_under: int,
                      units: str = "points",
                      context: list[str] | None = None) -> dict | None:
    """Game-total pick from price disagreement with the sharp book. Both
    books must be quoting the SAME line for the comparison to mean anything —
    the caller checks that."""
    pick = sharp_anchor_two_way(sharp_over, sharp_under, over_odds, under_odds)
    if pick is None:
        return None
    i, fair, ev = pick
    side = "Over" if i == 0 else "Under"
    odds = over_odds if i == 0 else under_odds
    card = _game_bet("total", "Total", home, away, fair,
                     american_to_prob(odds), fair - american_to_prob(odds),
                     odds, pick_label=f"{side} {line:g}", side=side, line=line,
                     reasons=list(context or []),
                     headline=f"{side} {line:g} {units}")
    return _sharpify(card, fair, odds, ev, f"{side} {line:g}")


def price_spread_sharp(home: str, away: str, home_spread: float,
                       home_odds: int, away_odds: int,
                       sharp_home_odds: int, sharp_away_odds: int,
                       context: list[str] | None = None) -> dict | None:
    """Spread / run-line pick from price disagreement with the sharp book,
    at a matching line (caller-checked)."""
    pick = sharp_anchor_two_way(sharp_home_odds, sharp_away_odds,
                                home_odds, away_odds)
    if pick is None:
        return None
    i, fair, ev = pick
    team = home if i == 0 else away
    line = home_spread if i == 0 else -home_spread
    odds = home_odds if i == 0 else away_odds
    label = f"{team} {line:+g}"
    card = _game_bet("spread", "Run Line" if abs(home_spread) == 1.5 else "Spread",
                     home, away, fair, american_to_prob(odds),
                     fair - american_to_prob(odds), odds,
                     pick_label=label, team=team, line=line,
                     reasons=list(context or []), headline=label)
    return _sharpify(card, fair, odds, ev, label)


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
    if ev > SHARP_SUSPECT_EV:
        grade, stake = "Pass", 0.0
        reasons = [_SUSPECT_NOTE.format(ev=ev)]
    else:
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
                    context: list[str] | None = None,
                    sport: str = "") -> MoneylineRec:
    """Price both sides of a moneyline and back the one with the edge.

    ``sport`` is optional and only selects the measured market haircut
    (`engine.gamecal`); without it the flat prior applies, which is what
    every caller got before the calibration existed.
    """
    fair_home, fair_away = devig_two_way(home_ml, away_ml)
    wp_home = clamp(win_prob_home, 0.01, 0.99)
    wp_away = 1.0 - wp_home

    home_edge = wp_home - fair_home
    away_edge = wp_away - fair_away

    if home_edge >= away_edge:
        pick, is_home, raw, ml, fair = home, True, wp_home, home_ml, fair_home
    else:
        pick, is_home, raw, ml, fair = away, False, wp_away, away_ml, fair_away
    wp, edge, credible = temper(raw, fair, sport, "moneyline")

    ev = expected_value(wp, ml)
    confidence = _ml_confidence(edge, wp)
    grade = _grade(confidence, edge) if credible else "Pass"
    stake = _kelly_stake(wp, ml) if grade != "Pass" else 0.0

    reasons = list(context or [])
    reasons.insert(0, f"Model win probability {wp:.0%} vs book's {fair:.0%} "
                      f"— a {edge:+.1%} edge on {pick} after the market haircut")
    reasons.extend(_calibration_note(sport, "moneyline"))
    if not credible:
        reasons.insert(0, f"Model disagrees with the market by more than "
                          f"{MAX_CREDIBLE_EDGE:.0%} — a rating error, not an edge")

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
        # The moneyline is the one game market that never grew the
        # fabricated-price bug — `_game_bets` has always refused to price
        # it without `g.home_ml and g.away_ml`. It still has to SAY so,
        # or `journal_skip_reason` sees None here and cannot tell this
        # card apart from one built on an invented number.
        "has_market": True,
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
    return _sd(SCORING_BASELINE, sport, "scoring baseline") + off + opp_def


def project_total(sport: str, home_off: float, home_def: float,
                  away_off: float, away_def: float) -> float:
    """Projected combined score: each side's offense meets the other's defense."""
    base = _sd(SCORING_BASELINE, sport, "scoring baseline")
    # home pts = base + home_off + away_def ; away pts = base + away_off + home_def
    return 2 * base + home_off + away_off + home_def + away_def


def game_margin(sport: str, home_rating: float, away_rating: float) -> float:
    """Projected home scoring margin (points/runs), including home field."""
    return (home_rating - away_rating) + _sd(HOME_FIELD, sport, "home field")


def temper(raw_win: float, fair: float, sport: str = "",
           market: str = "") -> tuple[float, float, bool]:
    """The prop layer's §2.5/§3 discipline, applied to a GAME bet.

    It was missing here, and the asymmetry was visible on one screen: a
    passing-yards prop 13 points clear of the market was graded Pass, while
    four spreads and totals with the SAME size disagreement sat above it
    graded Play at +12% to +21% EV. Only the prop layer had the guards.

    Two things happen, both borrowed rather than reinvented:

    1. Shrink halfway to the market. An uncalibrated model that disagrees
       with a closing NFL line by four points is far more likely to be four
       points wrong than four points right — the line is the aggregate of
       everyone who bet it, and we are one model.
    2. Refuse a raw disagreement over MAX_CREDIBLE_EDGE. A 4-point gap on
       an NFL total is 11.7% raw; spreads and totals are the most efficiently
       priced markets in American sport, and an 11.7% edge in one is a
       statement about our ratings, not about the market.

    THE 0.5 IS NOW A FALLBACK, NOT THE RULE. "Shrink halfway to the
    market" was a reasonable guess made when nobody could measure the
    real fraction, because no closing numbers were stored. They are now,
    and `engine.gamecal` regresses the market's own error on this
    model's disagreement over every graded game in our history: the
    coefficient IS the fraction of a disagreement that has held up. Where
    a sport and market have been measured on enough games, that number is
    used in place of the guess; where they have not, the guess stands.

    The first fit, over 899 NFL games, put both the spread and the total
    slope within a standard error of zero — so on those two markets this
    now shrinks nearly all the way to the close, and the board goes quiet.
    That is the intended behaviour of an honest model with no measured
    edge, and it is why the measurement is allowed to lower the shrink
    but never (see gamecal.MAX_ADOPTED) to raise it above the old guess.

    Returns ``(tempered_win, edge_vs_fair, credible)``.
    """
    shrink = None
    if sport and market:
        try:
            from .gamecal import shrink_for
            shrink = shrink_for(sport, market)
        except Exception:                                 # noqa: BLE001
            shrink = None            # never let a calibration cost a board
    return temper_edge(raw_win, fair, book="", allow_synthetic_line=True,
                       shrink=shrink)


def _calibration_note(sport: str, market: str) -> list[str]:
    """The measured-haircut line for a card, or ``[]``.

    A board that quietly stopped recommending spreads would be the worst
    version of this change: the user sees fewer plays and is told
    nothing. The reason goes on the card, in the same reasons list as
    every other piece of evidence.
    """
    if not (sport and market):
        return []
    try:
        from .gamecal import note_for
        return [n for n in (note_for(sport, market),) if n]
    except Exception:                                     # noqa: BLE001
        return []


def _real_price(*odds) -> bool:
    """Did a book actually post every price this card was built on?

    0 means NOT OFFERED (see engine/models.Game). A game bet that has
    never carried `has_market` cannot be refused by
    `ledger.journal_skip_reason`, whose proxy guard tests `is False` — and
    None is not False, so every game bet slipped past a check the prop
    layer has always applied.
    """
    return all(bool(o) for o in odds)


def _game_bet(bet_type, market_label, home, away, win, fair, edge, odds,
              pick_label, reasons, team="", side="", line=0.0, headline="",
              credible=True, has_market=True):
    ev = expected_value(win, odds)
    confidence = _ml_confidence(edge, win)
    grade = _grade(confidence, edge) if credible else "Pass"
    stake = _kelly_stake(win, odds) if grade != "Pass" else 0.0
    if not credible:
        reasons = [f"Model disagrees with the market by more than "
                   f"{MAX_CREDIBLE_EDGE:.0%} — in a market this efficiently "
                   f"priced that is a rating error, not an edge"] + list(reasons)
    return {
        "bet_type": bet_type,
        "market": bet_type,
        # NOW SET, and it never was. `ledger.journal_skip_reason` refuses
        # a proxy-priced row with `if r.get("has_market") is False` — and
        # a game bet returned None, which is not False, so every one of
        # them walked past a guard the prop layer has always applied.
        "has_market": bool(has_market),
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
        "credible": credible,
        "headline": headline or pick_label,
        "reasons": reasons,
    }


def price_total(sport: str, home: str, away: str, proj_total: float,
                market_total: float, over_odds: int = -110, under_odds: int = -110,
                units: str = "points", context: list[str] | None = None) -> dict:
    """Price the game total (over/under) from the projected combined score."""
    fair_over, fair_under = devig_two_way(over_odds, under_odds)
    sd = _sd(TOTAL_SD, sport, "total SD")
    p_over = clamp(normal_cdf((proj_total - market_total) / sd), 0.02, 0.98)
    over_edge = p_over - fair_over
    under_edge = (1.0 - p_over) - fair_under

    if over_edge >= under_edge:
        side, raw, odds, fair = "Over", p_over, over_odds, fair_over
    else:
        side, raw, odds, fair = "Under", 1.0 - p_over, under_odds, fair_under
    win, edge, credible = temper(raw, fair, sport, "total")

    reasons = list(context or [])
    reasons.insert(0, f"Model projects {proj_total:.1f} {units} vs the {market_total:g} "
                      f"total — {side} ({edge:+.1%} edge after the market haircut)")
    reasons.extend(_calibration_note(sport, "total"))
    return _game_bet("total", "Total", home, away, win, fair, edge, odds,
                     pick_label=f"{side} {market_total:g}", side=side, line=market_total,
                     reasons=reasons, headline=f"{side} {market_total:g} {units}",
                     credible=credible,
                     has_market=_real_price(over_odds, under_odds))


def price_team_total(sport: str, team: str, home: str, away: str,
                     proj_points: float, line: float,
                     over_odds: int = -110, under_odds: int = -110,
                     units: str = "points", context: list[str] | None = None) -> dict:
    """Price a single team's total (over/under) from its projected scoring."""
    fair_over, fair_under = devig_two_way(over_odds, under_odds)
    sd = _sd(TEAM_TOTAL_SD, sport, "team-total SD")
    p_over = clamp(normal_cdf((proj_points - line) / sd), 0.02, 0.98)
    over_edge = p_over - fair_over
    under_edge = (1.0 - p_over) - fair_under

    if over_edge >= under_edge:
        side, raw, odds, fair = "Over", p_over, over_odds, fair_over
    else:
        side, raw, odds, fair = "Under", 1.0 - p_over, under_odds, fair_under
    win, edge, credible = temper(raw, fair, sport, "total")

    reasons = list(context or [])
    reasons.insert(0, f"Model projects {team} for {proj_points:.1f} {units} vs the "
                      f"{line:g} team total — {side} ({edge:+.1%} edge after the "
                      f"market haircut)")
    reasons.extend(_calibration_note(sport, "total"))
    return _game_bet("team_total", "Team total", home, away, win, fair, edge, odds,
                     pick_label=f"{team} {side} {line:g}", team=team, side=side, line=line,
                     reasons=reasons, headline=f"{team} team {side} {line:g}",
                     credible=credible,
                     has_market=_real_price(over_odds, under_odds))


def price_spread(sport: str, home: str, away: str, proj_margin: float,
                 home_spread: float, home_odds: int = -110, away_odds: int = -110,
                 context: list[str] | None = None) -> dict:
    """Price the spread (NFL points) / run line (MLB) from the projected margin.

    ``home_spread`` is the home team's number (negative = home favored). Home
    covers when the actual margin beats it, i.e. margin + home_spread > 0.
    """
    fair_home, fair_away = devig_two_way(home_odds, away_odds)
    sd = _sd(MARGIN_SD, sport, "margin SD")
    p_home = clamp(normal_cdf((proj_margin + home_spread) / sd), 0.02, 0.98)
    home_edge = p_home - fair_home
    away_edge = (1.0 - p_home) - fair_away

    if home_edge >= away_edge:
        team, spread, raw, odds, fair = home, home_spread, p_home, home_odds, fair_home
    else:
        team, spread, raw, odds, fair = away, -home_spread, 1.0 - p_home, away_odds, fair_away
    win, edge, credible = temper(raw, fair, sport, "spread")

    reasons = list(context or [])
    reasons.insert(0, f"Model margin {proj_margin:+.1f} vs the {home} {home_spread:+g} "
                      f"line — {team} {spread:+g} ({edge:+.1%} edge after the "
                      f"market haircut)")
    reasons.extend(_calibration_note(sport, "spread"))
    return _game_bet("spread", "Spread", home, away, win, fair, edge, odds,
                     pick_label=f"{team} {spread:+g}", team=team, line=spread,
                     reasons=reasons, headline=f"{team} {spread:+g}",
                     credible=credible,
                     has_market=_real_price(home_odds, away_odds))
