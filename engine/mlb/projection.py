"""MLB projection assembly.

Recent-form baseline (reusing the shared form-blending module) × park ×
weather × matchup multipliers → projected mean + standard deviation per
market. Baseball's per-game variance is enormous relative to its means, so the
coefficient-of-variation floors here are much higher than the NFL's — that is
what keeps hit probabilities honest against efficient lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..form import compute_form, FormResult
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


def build_mlb_projection(prop: MLBProp, game: MLBGame, model=None) -> MLBProjection:
    # Shared recent-form blend (last 1/3/5/10 + season + career + vs pitcher).
    logs = [GameLog(week=g.game, opponent=g.opponent, value=g.value, home=g.home)
            for g in prop.logs]
    form = compute_form(logs, prop.career_avg, prop.vs_pitcher_avg)

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
    mean = form.mean * total_mult * form.trend_mult

    cv_floor = CV_FLOOR.get(prop.market, 0.6) * max(form.mean, 0.1)
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
