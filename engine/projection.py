"""Projection assembly.

Combines the base form mean with the multiplicative adjustments from the
matchup, weather and injury modules to produce a final projected mean and a
standard deviation for the prop's market. Every contributing factor is kept so
the explanation and the UI can show the full chain of reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Prop, Game, Team
from .form import compute_form, FormResult
from .weather import evaluate_weather, WeatherEffect
from .injuries import evaluate_injuries, InjuryEffect
from .matchup import evaluate_matchup, MatchupEffect
from .statmath import clamp

# Realistic game-to-game variance floors, expressed as a coefficient of
# variation (std / mean) per market. Player game logs are often too smooth to
# capture true prop variance, so we never let the estimated std fall below
# these market-typical levels — this is what keeps hit probabilities honest.
CV_FLOOR = {
    "pass_yds": 0.16,
    "rush_yds": 0.42,
    "rec_yds": 0.48,
    "receptions": 0.34,
}


@dataclass
class Projection:
    mean: float
    std: float
    form: FormResult
    matchup: MatchupEffect
    weather: WeatherEffect
    injury: InjuryEffect
    reasons: list[str] = field(default_factory=list)


def build_projection(prop: Prop, game: Game, opponent_team: Team, model=None,
                     context: dict | None = None) -> Projection:
    """``context`` (NFL Phase 2) carries measured team tendency:
    ``{"profiles": {team: profile}, "league": {...}}`` from
    engine.teamcontext. Absent = the model prices exactly as before, which
    is what makes the whole layer A/B-testable against the backtest
    baseline instead of shipped on faith."""
    form = compute_form(prop.logs, prop.career_avg, prop.vs_opponent_avg)

    matchup = evaluate_matchup(prop, opponent_team.defense, game,
                               measured_context=bool(context))
    weather = evaluate_weather(game.weather)
    injury = evaluate_injuries(prop, game.injuries)

    weather_mult = weather.multipliers.get(prop.market, 1.0)

    # Hand-tuned total multiplier, bounded so no single factor runs away with
    # the projection. Kept tight because sportsbook lines are efficient.
    rule_mult = clamp(
        matchup.multiplier * weather_mult * injury.multiplier,
        0.85, 1.18,
    )

    # Measured team tendency — pace, pass rate, offensive efficiency. Kept
    # OUTSIDE rule_mult's clamp on purpose: that clamp exists to stop the
    # hand-tuned factors compounding, and this is a different kind of
    # input with its own bound. Folding it in would make a fast, pass-heavy
    # offence indistinguishable from a merely favourable matchup.
    ctx_mult, ctx_reasons = 1.0, []
    if context:
        from .teamcontext import context_multiplier, drift_multiplier
        team = prop.team
        if context.get("mode") == "drift":
            ctx_mult, ctx_reasons = drift_multiplier(
                (context.get("profiles") or {}).get(team),
                (context.get("baseline") or {}).get(team), prop.market)
        else:
            ctx_mult, ctx_reasons = context_multiplier(
                (context.get("profiles") or {}).get(team),
                context.get("league") or {}, prop.market)

    reasons: list[str] = []
    if model is not None and model.has(prop.market):
        # Learned magnitude replaces the hand-tuned matchup/weather multipliers;
        # injuries stay on top (they're a separate, sparse signal the model
        # isn't trained on). The rule modules still supply the reasons below.
        from .ml.features import extract_features, vectorize
        feat = vectorize(extract_features(prop, game, opponent_team.defense))
        learned = model.predict_multiplier(feat, prop.market)
        total_mult = clamp(learned * injury.multiplier, 0.70, 1.40)
        reasons.append(f"Learned model adjustment ×{learned:.2f} (trained on historical data)")
    else:
        total_mult = rule_mult

    # Recency shade: a sustained hot/cold streak pulls the projection toward
    # recent form (bounded in form.py), so the model stops leaning on stale
    # early-season numbers for a player who has cooled off.
    mean = form.mean * total_mult * form.trend_mult * ctx_mult

    # Uncertainty: never below the market-typical variance floor, and it grows
    # as we push further from the player's own baseline.
    cv_floor = CV_FLOOR.get(prop.market, 0.35) * max(form.mean, 1.0)
    base_std = max(form.std, cv_floor)
    adj_std = base_std * (1.0 + 0.5 * abs(total_mult - 1.0)
                          + 0.5 * abs(ctx_mult - 1.0))
    if form.sample_games < 4:
        adj_std *= 1.20

    reasons += ctx_reasons
    reasons += matchup.reasons
    reasons += weather.reasons
    reasons += injury.reasons

    # Recent-form narrative — the cool-off case is tied to the actual shade.
    if form.trend == "up":
        reasons.append(f"Trending up — last 3 games {form.trend_delta:+.0f} vs prior form")
    elif form.trend == "down":
        reasons.append(
            f"Cooling off — last 3 games {form.trend_delta:+.0f} vs prior form "
            f"(projection shaded {form.trend_mult - 1:+.0%})"
        )

    return Projection(
        mean=mean,
        std=adj_std,
        form=form,
        matchup=matchup,
        weather=weather,
        injury=injury,
        reasons=reasons,
    )
