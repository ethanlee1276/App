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
from .models import MLBProp, MLBGame, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS
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


def _rare_event_rate(prop: MLBProp, form: FormResult) -> float:
    """Empirical-Bayes rate for a rare binary market.

    Shrinks the observed per-game rate toward the player's career rate in
    proportion to how little evidence there is, instead of amplifying the
    most recent game."""
    vals = [g.value for g in prop.logs]
    n = len(vals)
    if not n:
        return form.mean
    observed = float(sum(vals))
    prior = prop.career_avg if prop.career_avg else observed / n
    k = RARE_EVENT_PRIOR_GAMES
    return (k * prior + observed) / (k + n)


def build_mlb_projection(prop: MLBProp, game: MLBGame, model=None) -> MLBProjection:
    # Shared recent-form blend (last 1/3/5/10 + season + career + vs pitcher).
    logs = [GameLog(week=g.game, opponent=g.opponent, value=g.value, home=g.home)
            for g in prop.logs]
    # MLB recency curve (docs/MLB_MODEL.md §6): gentler than the NFL's —
    # ~40% on the last week, ~30% on the fortnight, 20% season, 10% vs this
    # pitcher — because a hot baseball week is mostly noise, and most
    # batter-vs-pitcher history is an anecdote, not evidence.
    form = compute_form(logs, prop.career_avg, prop.vs_pitcher_avg,
                        weights=MLB_WINDOW_WEIGHTS)

    park = evaluate_park(get_park(game.park))
    weather = evaluate_weather(game.weather)
    matchup = evaluate_matchup(prop, game)

    park_mult = park.multipliers.get(prop.market, 1.0)
    weather_mult = weather.multipliers.get(prop.market, 1.0)

    # Home-plate umpire: a wide zone lifts strikeouts directly; the run
    # environment nudges hitter counting stats a little. Unknown ump = 1.0.
    if prop.market == STRIKEOUTS:
        ump_mult = game.ump_k_factor
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
    mean = base_mean * total_mult * trend_mult

    cv_floor = CV_FLOOR.get(prop.market, 0.6) * max(base_mean, 0.1)
    base_std = max(form.std, cv_floor)
    adj_std = base_std * (1.0 + 0.4 * abs(total_mult - 1.0))
    if form.sample_games < 5:
        adj_std *= 1.15

    reasons: list[str] = []
    reasons += learned_reason
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
