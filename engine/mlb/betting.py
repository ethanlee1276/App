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
    Recommendation, _kelly_stake, net_edge, favourite_surcharge,
    pick_side, temper_edge,
)
from ..calibrate import apply_temperature, correction_for, is_reliable
from ..losspatterns import veto as lp_veto
from ..odds import expected_value
from ..statmath import prob_over, clamp
from .models import MLBProp, HOME_RUNS, STRIKEOUTS, PITCHER_MARKETS
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


def _pitcher_certainty(prop: MLBProp, proj: MLBProjection, game=None) -> float:
    """§5: grade the pitcher first, always. For a pitcher's own prop this is
    how well-sampled and steady his log is; for a hitter prop it is whether
    tonight's opposing probable is even KNOWN — an unconfirmed starter makes
    every opposing hitter number a guess about a matchup that may not exist."""
    if prop.market in PITCHER_MARKETS:
        sample_q = clamp(proj.form.sample_games / 8.0, 0.3, 1.0)
        cv = (proj.form.std / proj.form.mean) if proj.form.mean > 0 else 1.0
        var_q = clamp(0.28 / cv, 0.4, 1.0) if cv > 0 else 1.0
        return sample_q * var_q
    if game is not None and getattr(game, "pitchers", None):
        if game.pitchers.get(prop.opponent):
            return 0.9
    return 0.55


def _lineup_certainty(prop: MLBProp, game=None) -> float:
    """§2.3: hitter props are conditional until the lineup is confirmed —
    the #2 hitter gets ~0.7 more PAs than the #7 hitter, so slot IS the
    projection. Pitcher props care less (the probable is the condition)."""
    confirmed = bool(getattr(game, "lineups_confirmed", True)) if game is not None else True
    if prop.market in PITCHER_MARKETS:
        return 1.0 if confirmed else 0.85
    if prop.lineup_spot and confirmed:
        return 1.0
    if prop.lineup_spot:
        return 0.7                     # projected slot, lineup not posted
    return 0.35                        # not in any posted/projected lineup


def evaluate_mlb_prop(prop: MLBProp, proj: MLBProjection,
                      allow_synthetic_line: bool = False,
                      game=None) -> Recommendation:
    """docs/MLB_MODEL.md §3 end to end: shop the ladder, devig, price with
    the market's own distribution, haircut by tier, gate on the tier
    minimum, grade 0–100 with baseball's weights, size with fractional
    Kelly. ``game`` supplies lineup/probable/umpire context (None → neutral)."""
    from .quality import (mlb_tier, mlb_tier_shrink, mlb_tier_min_edge,
                          mlb_volatility, mlb_quality_score, letter,
                          STAKE_CAP_U)
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
    hit, edge, credible = temper_edge(hit_raw, fair, best.book,
                                      allow_synthetic_line,
                                      shrink=mlb_tier_shrink(prop.market))
    has_market = allow_synthetic_line or (best.book or "").lower() != "proxy"
    if not has_market:
        # No real price to beat — don't report a number that reads as an edge.
        edge = 0.0
    ev = expected_value(hit, best.odds)
    net = net_edge(hit, best.odds)

    # Environment: park × weather for this market, times the umpire's zone
    # (K-factor for strikeout props, run environment for hitter markets) —
    # haircut-sized in the ABS era, but not zero.
    env_mult = (proj.park.multipliers.get(prop.market, 1.0)
                * proj.weather.multipliers.get(prop.market, 1.0))
    if game is not None:
        env_mult *= (getattr(game, "ump_k_factor", 1.0) if prop.market == STRIKEOUTS
                     else getattr(game, "ump_run_factor", 1.0))

    quality, quality_notes = mlb_quality_score(
        edge=edge, market=prop.market, side=side,
        pitcher_certainty=_pitcher_certainty(prop, proj, game),
        lineup_certainty=_lineup_certainty(prop, game),
        env_mult=env_mult, matchup_mult=proj.matchup.multiplier)
    confidence = round(quality / 10.0, 1)

    # The gates, in order of what they mean:
    #  calibration — a market whose calibration fit ran to the edge of its
    #    search range cannot be priced; the stored temperature is a cap,
    #    not a correction. Bet nothing there until the model is fixed.
    #  credible    — a >10% raw disagreement is bad data, not alpha (§2.5)
    #  tier edge   — §3's minimum post-haircut edge for this market's tier
    #  net         — the REAL price must still clear break-even (plus the
    #                measured favourite surcharge). Not a second edge bar:
    #                the old +0.010 requirement sat above the tier minimums
    #                at standard juice and silently overrode them.
    #  quality     — below 70 is no bet, not a lean (§10)
    calibration_ok = is_reliable("mlb", prop.market)
    # One level finer than the market gate above: the loss-pattern miner
    # closes SLICES (a side, a price band) whose stated probabilities
    # systematically missed, under false-discovery control. Same contract
    # as a boundary temperature — the record itself refuses the bet.
    from ..losspatterns import minutes_until
    _env = {}
    if game is not None:
        # The same park/wind measurements the journal records — a closed
        # "wind out hard" slice must be able to refuse the NEXT wind-out
        # pick, not just explain the last one.
        from .pipeline import _env_of
        _env = _env_of(game)
    if prop.market not in PITCHER_MARKETS:
        _env["lineup_slot"] = int(prop.lineup_spot or 0)
        _env["lineup_conf"] = bool(
            getattr(game, "lineups_confirmed", True)) if game is not None \
            else False
    # Bullpen workload behind both sides — the same bands the board shows,
    # so a convicted pocket refuses the NEXT matching pick. The backtest
    # calls this with no game at all, which is an unmeasured pen rather
    # than a fresh one.
    _pen = (game.bullpen_fatigue or {}) if game is not None else {}
    pattern_block = lp_veto("mlb", prop.market, side=side, odds=best.odds,
                            prob=hit, book=best.book, horizon_days=0,
                            lead_min=minutes_until(
                                getattr(game, "kickoff", None)),
                            pen_own=_pen.get(prop.team),
                            pen_opp=_pen.get(prop.opponent),
                            **_env)
    tier = mlb_tier(prop.market)
    min_edge = mlb_tier_min_edge(prop.market)
    gate_ok = (credible and calibration_ok and pattern_block is None
               and has_market and edge >= min_edge
               and net > favourite_surcharge(best.odds))
    grade = letter(quality) if gate_ok else "Pass"
    fraction = 0.5 if (grade == "A+" and tier == 1) else 0.25
    stake = (_kelly_stake(hit, best.odds, fraction, STAKE_CAP_U[grade])
             if grade != "Pass" else 0.0)

    reasons = list(proj.reasons)
    if pattern_block:
        reasons.insert(0, pattern_block)
    if not calibration_ok:
        reasons.insert(0, "This market's calibration fit hit the edge of its "
                          "search range — the model can't price it reliably, "
                          "so nothing here is bettable until it's fixed")
    if not credible:
        reasons.insert(0, "No credible market edge — line unavailable or price looks off")
    elif side == "UNDER":
        if proj.mean <= best.line:
            reasons.insert(0, f"Model sides UNDER — projects {proj.mean:.2f} under the {best.line:g} line")
        else:
            # The empirical distribution chose the under even though the MEAN
            # sits above the line — §8: averages lie on right-skewed stats,
            # and the old text claimed a projection that wasn't true.
            reasons.insert(0, f"Model sides UNDER — the mean is {proj.mean:.2f} but a "
                              f"few big games inflate it; his actual game log clears "
                              f"{best.line:g} less often than the price implies")
    if credible and calibration_ok and has_market and 0 < edge < min_edge:
        reasons.append(f"Edge {edge:+.1%} is under the Tier {tier} bar "
                       f"({min_edge:.1%} post-haircut) — pass, not a lean")
    reasons.extend(quality_notes)

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
        quality=quality, tier=tier, volatility=mlb_volatility(prop.market),
    )
