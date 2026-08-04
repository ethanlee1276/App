"""MLB projection assembly.

Recent-form baseline (reusing the shared form-blending module) × park ×
weather × matchup multipliers → projected mean + standard deviation per
market. Baseball's per-game variance is enormous relative to its means, so the
coefficient-of-variation floors here are much higher than the NFL's — that is
what keeps hit probabilities honest against efficient lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..form import compute_form, FormResult, MLB_WINDOW_WEIGHTS
from ..models import GameLog
from ..statmath import clamp
from .models import (MLBProp, MLBGame, TOTAL_BASES, HITS, HOME_RUNS,
                     STRIKEOUTS, OUTS)
from .parks import get_park, evaluate_park, ParkEffect
from .weather import evaluate_weather, WeatherEffect
from .matchup import evaluate_matchup, MatchupEffect
from .statcast import evaluate_statcast

# Per-game variance floors (std/mean). A 1.8-TB-per-game hitter routinely
# posts 0 or 5; strikeout counts are the steadiest MLB prop.
CV_FLOOR = {
    TOTAL_BASES: 0.75,
    HITS: 0.70,
    HOME_RUNS: 1.00,     # informational; HRs are priced with Poisson anyway
    STRIKEOUTS: 0.28,
    # §9 rates outs LOW where 6+ Ks is MEDIUM: a starter is pulled by
    # pitch count and score far more than by anything that varies
    # night to night, so the distribution is tighter than his Ks.
    OUTS: 0.20,
}


@dataclass
class MLBProjection:
    mean: float
    std: float
    form: FormResult
    park: ParkEffect
    weather: WeatherEffect
    matchup: MatchupEffect
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Markets where the per-game outcome is a rare 0/1 event rather than a
# quantity. Recency blending is built for quantities: averaging the last
# 1/3/5 games smooths a noisy total-bases line toward current form. Do
# the same to a home run and "last1" is literally 0 or 1, so the blend
# turns *when* a hitter homered into a projection swing of ~43x —
# measured: an identical 2-HR-in-15 hitter projects 0.344 HR/game if the
# homer was yesterday and 0.008 if it was eleven games ago, against a
# true rate of 0.133. That single defect produced the model's "23% edge"
# on +450 home-run props, and no calibration temperature can repair it:
# the error is dispersion, not level, and a temperature only shifts the
# level.
RARE_EVENT_MARKETS = {HOME_RUNS}
# Strength of the prior, in games. A season's worth of shrinkage: with
# ~30 games of prior weight, one recent homer moves the estimate a
# little, which is roughly what one homer is actually worth.
RARE_EVENT_PRIOR_GAMES = 30.0
# League-average HR per game for a lineup regular (~1.15 team HR/game
# across nine spots). The prior of last resort: when a player has no
# career rate on file, shrinking toward his own observed window is not
# shrinking at all — a 3-HR fortnight stayed a 0.2/game projection, and
# rookies without a career line were exactly the pool the receipts
# caught running hot (said 14%, hit 11%).
LEAGUE_HR_RATE = 0.13

#: Floor under a rare-event rate. A hitter who has never homered is not
#: a hitter who cannot: the bottom of a big-league order still runs into
#: one. Small enough that it never manufactures a bet, large enough that
#: the model never states an impossibility.
MIN_RARE_EVENT_RATE = 0.01
# Environment dampening for rare events. Park, weather, Statcast and
# matchup HR effects are each estimated on the thinnest tail of the
# data, and the long-shot board then SELECTS the props where they stack
# — winner's curse by construction. Their compound claim is applied at
# half strength (sqrt on the multiplier) and clamped tighter than the
# quantity markets' band; the calibration boundary (T pinned at 0.40,
# a 22-point optimistic lean) is the measured bill for full strength.
RARE_EVENT_ENV_DAMP = 0.5
RARE_EVENT_ENV_CLAMP = (0.85, 1.18)


def _rare_event_rate(prop: MLBProp, form: FormResult) -> float:
    """Empirical-Bayes rate for a rare binary market.

    Shrinks the observed per-game rate toward the player's career rate in
    proportion to how little evidence there is, instead of amplifying the
    most recent game. A player whose career rate is genuinely UNKNOWN
    (None) shrinks toward the league rate — falling back to his own
    observed window made the prior the noise it existed to damp. A career
    rate of 0.0 is not unknown; see below."""
    vals = [g.value for g in prop.logs]
    n = len(vals)
    if not n:
        return form.mean
    observed = float(sum(vals))
    # `is None`, NOT falsiness. A career rate of 0.0 is a MEASUREMENT —
    # this hitter has not homered — and the falsy test overwrote it with
    # the league average, so a slap hitter with a genuine .000 career
    # projected at 0.056 HR/game while the same hitter carrying 0.01
    # projected at 0.004. Thirteen times more likely to homer for never
    # having homered. The zero-career population is most of a roster and
    # all of a walk-forward's early sample, which is why calibrate.py
    # pinned this market at the edge of its search range while
    # hr_diagnose — filtered to "players with home-run history", the one
    # population where this cannot fire — reported the model healthy.
    prior = prop.career_avg if prop.career_avg is not None else LEAGUE_HR_RATE
    k = RARE_EVENT_PRIOR_GAMES
    rate = (k * prior + observed) / (k + n)
    # …and nobody in a major-league batting order is literally incapable
    # of it, so the shrink is floored rather than allowed to reach zero.
    return max(rate, MIN_RARE_EVENT_RATE)


def reconcile_triple(hits: float, tb: float, hr: float
                     ) -> tuple[float, float, str]:
    """Force one batter's three means into the box real baseball allows.

    The sim's inverter (gamesim.rates_from_means) proved the box on live
    slates: a homer is a hit (hr ≤ hits) and total bases must cover the
    hits and homers claimed (hits + 3·hr ≤ tb ≤ 3·hits + hr, since
    E[TB] − E[H] − 3·E[HR] = E[2B] + 2·E[3B] ≥ 0). Each market's
    projection is built alone, so multipliers could push the trio outside
    the box — ~40 players a night on a real slate — and the reconcile
    gate rightly called it a projection-engine finding.

    Repairs move in ONE direction each: HR only ever comes DOWN (it is
    the market the receipts show running hot) and TB only ever moves the
    minimum the arithmetic demands. Hits — the best-calibrated of the
    three — is never touched. Returns (hr, tb, note); note is "" when
    the trio was already valid baseball.
    """
    notes = []
    if tb < hits:
        tb = hits                       # every hit is at least one base
        notes.append("total bases floored at the hits projection")
    cap = min(hits, (tb - hits) / 3.0)
    if hr > cap + 1e-9:
        hr = max(0.0, cap)
        notes.append("HR capped so the hits/total-bases/HR trio is "
                     "possible baseball")
    if tb > 3.0 * hits + hr + 1e-9:
        tb = 3.0 * hits + hr            # more bases than the hits can carry
        notes.append("total bases capped at what the hits can carry")
    return hr, tb, "; ".join(notes)


def build_mlb_projection(prop: MLBProp, game: MLBGame, model=None,
                         form_weights: dict | None = None,
                         player_mult: float | None = None) -> MLBProjection:
    # Shared recent-form blend (last 1/3/5/10 + season + career + vs pitcher).
    logs = [GameLog(week=g.game, opponent=g.opponent, value=g.value, home=g.home)
            for g in prop.logs]
    # MLB recency curve (docs/MLB_MODEL.md §6): gentler than the NFL's —
    # ~40% on the last week, ~30% on the fortnight, 20% season, 10% vs this
    # pitcher — because a hot baseball week is mostly noise, and most
    # batter-vs-pitcher history is an anecdote, not evidence.
    #
    # That spec curve is the DEFAULT, not the law: engine/formfit.py fits a
    # recency dial per market by walk-forward Brier, and a fit that beat
    # the spec by enough, on enough settled predictions, is adopted here.
    # An explicit ``form_weights`` (the fitter trying candidates) always
    # wins — the fitter must never read the store it is refitting.
    if form_weights is None:
        from ..formfit import weights_for
        form_weights = weights_for("mlb", prop.market)
    form = compute_form(logs, prop.career_avg, prop.vs_pitcher_avg,
                        weights=form_weights or MLB_WINDOW_WEIGHTS)

    park = evaluate_park(get_park(game.park))
    weather = evaluate_weather(game.weather)
    matchup = evaluate_matchup(prop, game)

    park_mult = park.multipliers.get(prop.market, 1.0)
    weather_mult = weather.multipliers.get(prop.market, 1.0)

    # Home-plate umpire: a wide zone lifts strikeouts directly; the run
    # environment nudges hitter counting stats a little. Unknown ump = 1.0.
    if prop.market == STRIKEOUTS:
        ump_mult = game.ump_k_factor
    elif prop.market == OUTS:
        # A wide zone helps a starter go deeper, but far less directly
        # than it lifts his strikeout count — half the effect.
        ump_mult = 1.0 + (game.ump_k_factor - 1.0) * 0.5
    elif prop.market in (HITS, TOTAL_BASES):
        ump_mult = 1.0 + (game.ump_run_factor - 1.0) * 0.5
    else:
        ump_mult = 1.0

    # Statcast: expected-stats regression + quality-of-contact / K stuff.
    statcast_mult = 1.0
    statcast_reasons: list[str] = []
    if prop.statcast is not None:
        eff = evaluate_statcast(prop.statcast, prop.market)
        statcast_mult = eff.multiplier
        statcast_reasons = eff.reasons

    learned_reason: list[str] = []
    if model is not None and model.has(prop.market):
        # Learned magnitude replaces the hand-tuned park/weather/matchup/Statcast
        # product; the modules above still supply the human-readable reasons.
        from .ml import extract_features, vectorize
        feat = vectorize(extract_features(prop, game))
        total_mult = model.predict_multiplier(feat, prop.market)
        learned_reason = [f"Learned model adjustment ×{total_mult:.2f} "
                          f"(trained on historical data)"]
    else:
        # Tight overall clamp: books price parks and platoons in, so real edges
        # come from small compounding angles. Slightly wider than the NFL clamp
        # because park effects (Coors) genuinely run bigger.
        total_mult = clamp(park_mult * weather_mult * matchup.multiplier
                           * statcast_mult * ump_mult,
                           0.78, 1.28)
    if prop.market in RARE_EVENT_MARKETS:
        # Half-strength environment for rare events, learned path included
        # — the tail is where every one of these effects is worst-measured
        # and where the long-shot board's selection bites hardest. See
        # RARE_EVENT_ENV_DAMP; the calibration boundary was the receipt.
        lo, hi = RARE_EVENT_ENV_CLAMP
        total_mult = clamp(total_mult ** RARE_EVENT_ENV_DAMP, lo, hi)
    # Recency shade toward recent form (bounded in form.py) — a cold bat's
    # number comes down instead of riding a stale season line.
    base_mean = form.mean
    trend_mult = form.trend_mult
    if prop.market in RARE_EVENT_MARKETS:
        # …except for rare binary events, where recency blending is actively
        # harmful (see _rare_event_rate). Trend is dropped too: a "hot"
        # streak of one homer in three games is noise, not form.
        base_mean = _rare_event_rate(prop, form)
        trend_mult = 1.0
    # Player memory (engine/playerfit.py): the record's earned correction
    # for players the blend persistently misreads. An explicit
    # ``player_mult`` (the fitter's causal walk, or the baseline's 1.0)
    # always wins — the fitter must never read the store it is refitting.
    if player_mult is None:
        from ..playerfit import mult_for
        player_mult = mult_for("mlb", prop.market, prop.player)
    mean = base_mean * total_mult * trend_mult * player_mult

    cv_floor = CV_FLOOR.get(prop.market, 0.6) * max(base_mean, 0.1)
    base_std = max(form.std, cv_floor)
    adj_std = base_std * (1.0 + 0.4 * abs(total_mult - 1.0))
    if form.sample_games < 5:
        adj_std *= 1.15

    reasons: list[str] = []
    reasons += learned_reason
    if abs(player_mult - 1.0) >= 0.02:
        direction = "high" if player_mult < 1.0 else "low"
        reasons.append(f"Player memory: the record shows the blend runs "
                       f"{direction} on him — corrected ×{player_mult:.2f}")
    reasons += statcast_reasons
    if abs(ump_mult - 1.0) >= 0.02 and game.plate_umpire:
        direction = "elevates" if ump_mult > 1 else "suppresses"
        what = "strikeouts" if prop.market == STRIKEOUTS else "scoring"
        reasons.append(f"Plate ump {game.plate_umpire} {direction} {what} "
                       f"({(ump_mult - 1) * 100:+.0f}% measured over his games)")
    reasons += matchup.reasons
    reasons += park.reasons
    reasons += weather.reasons
    if form.trend == "up":
        reasons.append(f"Hot bat — last 3 games {form.trend_delta:+.1f} vs prior form")
    elif form.trend == "down":
        reasons.append(
            f"Cooling off — last 3 games {form.trend_delta:+.1f} vs prior form "
            f"(projection shaded {form.trend_mult - 1:+.0%})"
        )

    return MLBProjection(
        mean=mean, std=adj_std, form=form,
        park=park, weather=weather, matchup=matchup,
        reasons=reasons, warnings=list(weather.warnings),
    )
